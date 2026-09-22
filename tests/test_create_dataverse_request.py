from __future__ import annotations

import re
from pathlib import Path

import pytest
from scripts import create_dataverse_request


def test_default_request_id_is_unique_and_safe(monkeypatch) -> None:
    values = iter(["A1B2C3D4", "E5F6A7B8"])
    monkeypatch.setattr(
        create_dataverse_request.secrets,
        "token_hex",
        lambda _: next(values),
    )

    first = create_dataverse_request._default_request_id()
    second = create_dataverse_request._default_request_id()

    assert first != second
    assert re.fullmatch(r"PSR-DV-\d{8}-\d{6}-[A-F0-9]{8}", first)
    assert create_dataverse_request.SAFE_ID_PATTERN.fullmatch(first)


def test_environment_uses_azd_id_when_url_is_unset(monkeypatch) -> None:
    values = {
        "DATAVERSE_ENVIRONMENT_URL": None,
        "DATAVERSE_ENVIRONMENT_ID": "environment-123",
        "DATAVERSE_ENVIRONMENT_NAME": None,
    }
    monkeypatch.setattr(
        create_dataverse_request,
        "_azd_value",
        lambda key, _: values[key],
    )
    monkeypatch.setattr(
        create_dataverse_request.setup_dataverse_schema,
        "resolve_environment_url",
        lambda **kwargs: "https://insurance.crm.dynamics.com",
    )

    assert create_dataverse_request._resolve_environment(
        environment_url=None,
        environment_id=None,
        environment_name=None,
        azd_environment="test",
    ) == ("https://insurance.crm.dynamics.com", "environment-123")


def test_existing_request_id_prevents_create(monkeypatch) -> None:
    calls = []

    def fake_request(*args, **kwargs):
        calls.append((args, kwargs))
        return {
            "value": [
                {
                    "ipr_policyservicerequestid": (
                        "11111111-2222-3333-4444-555555555555"
                    )
                }
            ]
        }

    monkeypatch.setattr(
        create_dataverse_request,
        "_odata_request",
        fake_request,
    )

    with pytest.raises(RuntimeError, match="already exists"):
        create_dataverse_request._create_row(
            "https://insurance.crm.dynamics.com",
            "token",
            "ipr_policyservicerequests",
            {"ipr_requestid": "PSR-2026-00042"},
        )

    assert len(calls) == 1
    assert calls[0][0][2] == "GET"


def test_create_row_checks_then_posts_without_overwrite(monkeypatch) -> None:
    calls = []

    def fake_request(*args, **kwargs):
        calls.append((args, kwargs))
        if args[2] == "GET":
            return {"value": []}
        return {
            "ipr_policyservicerequestid": (
                "11111111-2222-3333-4444-555555555555"
            )
        }

    monkeypatch.setattr(
        create_dataverse_request,
        "_odata_request",
        fake_request,
    )
    values = {
        "ipr_requestid": "PSR-2026-00042",
        "ipr_policyid": "AUTO-100042",
    }

    row_id = create_dataverse_request._create_row(
        "https://insurance.crm.dynamics.com",
        "token",
        "ipr_policyservicerequests",
        values,
    )

    assert row_id == "11111111-2222-3333-4444-555555555555"
    assert [call[0][2] for call in calls] == ["GET", "POST"]
    assert calls[1][1]["body"] == values


class FakeBlob:
    def __init__(self, states: list[bool], data: bytes = b"") -> None:
        self.states = iter(states)
        self.data = data

    def exists(self) -> bool:
        return next(self.states)

    def download_blob(self):
        return self

    def readall(self) -> bytes:
        return self.data


class FakeService:
    def __init__(self) -> None:
        self.manifest = FakeBlob([False, True])
        self.report = FakeBlob([True], b"<html>ready</html>")

    def get_blob_client(self, container: str, blob: str) -> FakeBlob:
        if container == "policy-intake":
            assert blob == "normalized/PSR-2026-00042.json"
            return self.manifest
        assert container == "policy-review-packets"
        assert blob == "reviews/PSR-2026-00042.html"
        return self.report


def test_wait_reports_each_stage_and_downloads(monkeypatch, tmp_path, capsys) -> None:
    clock = iter([0.0, 0.0, 1.0, 2.0, 2.0, 3.0])
    monkeypatch.setattr(
        create_dataverse_request,
        "_blob_service",
        lambda _: FakeService(),
    )
    monkeypatch.setattr(
        create_dataverse_request.time,
        "monotonic",
        lambda: next(clock),
    )
    monkeypatch.setattr(create_dataverse_request.time, "sleep", lambda _: None)

    output = create_dataverse_request._wait_for_outputs(
        storage_url="https://storage.blob.core.windows.net/",
        intake_container="policy-intake",
        report_container="policy-review-packets",
        request_id="PSR-2026-00042",
        report_blob="reviews/PSR-2026-00042.html",
        timeout_minutes=15,
        poll_seconds=15,
        download_report=True,
        output_dir=tmp_path,
    )

    assert output == Path(tmp_path, "PSR-2026-00042.html")
    assert output.read_text() == "<html>ready</html>"
    stdout = capsys.readouterr().out
    assert "Normalized manifest: ready" in stdout
    assert "HTML report: ready" in stdout
