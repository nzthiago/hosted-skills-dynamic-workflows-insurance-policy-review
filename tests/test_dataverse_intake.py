from __future__ import annotations

import json

import pytest
from azure.core.exceptions import HttpResponseError, ResourceExistsError

import dataverse_intake


def _row(request_id: str = "PSR-2026-00042") -> dict:
    return {
        "ItemInternalId": "11111111-2222-3333-4444-555555555555",
        "ipr_requestid": request_id,
        "ipr_policyid": "AUTO-100042",
        "ipr_drivername": "Jordan Lee",
        "ipr_driverlicencefilename": "jordan-lee-license.pdf",
        "ipr_driverlicencestatus": "received",
        "ipr_signedrequestfilename": "signed-request.pdf",
        "ipr_signedrequeststatus": "missing",
        "ipr_reviewblobname": "PSR-2026-00042.html",
    }


def test_extract_rows_supports_connector_envelope() -> None:
    row = _row()
    assert dataverse_intake.extract_rows(
        json.dumps({"body": {"value": [row]}})
    ) == [row]


def test_normalize_row_maps_structured_fields_to_documents() -> None:
    manifest = dataverse_intake.normalize_row(_row())

    assert manifest["request_id"] == "PSR-2026-00042"
    assert manifest["review_blob"] == "reviews/PSR-2026-00042.html"
    assert manifest["source"] == {
        "kind": "dataverse",
        "table": "ipr_policyservicerequests",
        "row_id": "11111111-2222-3333-4444-555555555555",
    }
    assert manifest["documents"] == [
        {
            "position": 0,
            "document_id": (
                "11111111-2222-3333-4444-555555555555-driver-licence"
            ),
            "type": "driver_license",
            "file_name": "jordan-lee-license.pdf",
            "status": "received",
        },
        {
            "position": 1,
            "document_id": (
                "11111111-2222-3333-4444-555555555555-signed-request"
            ),
            "type": "signed_request",
            "file_name": "signed-request.pdf",
            "status": "missing",
        },
    ]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("ipr_requestid", ""),
        ("ipr_policyid", "contains spaces"),
        ("ipr_driverlicencestatus", "approved"),
        ("ipr_signedrequeststatus", "pending"),
        ("ipr_reviewblobname", "../unsafe.html"),
    ],
)
def test_normalize_row_rejects_invalid_contract(field: str, value: str) -> None:
    row = _row()
    row[field] = value
    with pytest.raises(dataverse_intake.IntakeRejectedError):
        dataverse_intake.normalize_row(row)


class FakeBlob:
    def __init__(self, store: dict[str, bytes], name: str) -> None:
        self.store = store
        self.name = name

    def exists(self) -> bool:
        return self.name in self.store

    def upload_blob(self, data: bytes, *, overwrite: bool, **_: object) -> None:
        if not overwrite and self.exists():
            raise ResourceExistsError("exists")
        self.store[self.name] = bytes(data)


class FakeContainer:
    def __init__(self) -> None:
        self.store: dict[str, bytes] = {}

    def create_container(self) -> None:
        raise ResourceExistsError("exists")

    def get_blob_client(self, name: str) -> FakeBlob:
        return FakeBlob(self.store, name)


class FakeService:
    def __init__(self) -> None:
        self.container = FakeContainer()

    def get_container_client(self, _: str) -> FakeContainer:
        return self.container


class FakeLease:
    def __init__(self, _: FakeBlob) -> None:
        pass

    def acquire(self, *, lease_duration: int) -> None:
        assert lease_duration == 60

    def release(self) -> None:
        pass


def test_process_trigger_is_idempotent(monkeypatch) -> None:
    service = FakeService()
    monkeypatch.setattr(dataverse_intake, "_storage_service", lambda: service)
    monkeypatch.setattr(dataverse_intake, "BlobLeaseClient", FakeLease)
    payload = {"body": {"value": [_row()]}}

    first = dataverse_intake.process_dataverse_trigger(payload)
    second = dataverse_intake.process_dataverse_trigger(payload)

    assert first == ["normalized/PSR-2026-00042.json"]
    assert second == []
    manifest = json.loads(service.container.store[first[0]])
    assert manifest["idempotency_key"]
    assert "blob_name" not in manifest["documents"][0]


def test_process_trigger_propagates_storage_lease_failures(monkeypatch) -> None:
    service = FakeService()
    monkeypatch.setattr(dataverse_intake, "_storage_service", lambda: service)

    class FailingLease(FakeLease):
        def acquire(self, *, lease_duration: int) -> None:
            assert lease_duration == 60
            error = HttpResponseError("storage unavailable")
            error.status_code = 503
            error.error_code = "ServerBusy"
            raise error

    monkeypatch.setattr(dataverse_intake, "BlobLeaseClient", FailingLease)

    with pytest.raises(HttpResponseError, match="storage unavailable"):
        dataverse_intake.process_dataverse_trigger(
            {"body": {"value": [_row()]}}
        )


def test_process_trigger_drops_invalid_row_without_retry(monkeypatch) -> None:
    service = FakeService()
    monkeypatch.setattr(dataverse_intake, "_storage_service", lambda: service)
    invalid = _row()
    invalid["ipr_requestid"] = ""
    assert dataverse_intake.process_dataverse_trigger(
        {"body": {"value": [invalid]}}
    ) == []
