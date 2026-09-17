from __future__ import annotations

import json

import pytest

from tools import policy_review_tools


def _request() -> dict:
    return {
        "request_id": "PSR-1",
        "policy_id": "AUTO-1",
        "driver_name": "<Jordan>",
        "documents": [
            {
                "document_id": "DOC-1",
                "type": "driver_license",
                "file_name": "license.pdf",
                "status": "received",
                "blob_name": "attachments/PSR-1/license.pdf",
            }
        ],
        "review_blob": "reviews/PSR-1.html",
    }


def test_validate_preserves_staged_document_references() -> None:
    result = policy_review_tools.validate_add_driver_request({"request": _request()})
    assert result["documents"][0]["blob_name"] == "attachments/PSR-1/license.pdf"
    assert result["review_blob"] == "reviews/PSR-1.html"


def test_report_is_escaped_and_keeps_human_decision_boundary() -> None:
    request = policy_review_tools.validate_add_driver_request({"request": _request()})
    check = policy_review_tools.inspect_driver_document(
        {"document": request["documents"][0], "position": 0}
    )
    report = policy_review_tools.build_driver_review_report({
        "request": request,
        "document_checks": [{"result": check}],
    })
    assert "&lt;Jordan&gt;" in report["html"]
    assert report["decision"] is None
    assert report["review_status"] == "human_review_required"
    assert report["missing_documents"] == ["signed_request"]


class FakeDownload:
    def readall(self) -> bytes:
        return json.dumps(_request()).encode()


class FakeBlob:
    def download_blob(self) -> FakeDownload:
        return FakeDownload()


class FakeService:
    def get_blob_client(self, *, container: str, blob: str) -> FakeBlob:
        assert container == "policy-intake"
        assert blob == "normalized/PSR-1.json"
        return FakeBlob()


def test_load_normalized_request_reads_triggered_manifest(monkeypatch) -> None:
    monkeypatch.setattr(policy_review_tools, "_blob_service", FakeService)
    result = policy_review_tools.load_normalized_policy_request({
        "blob_name": "policy-intake/normalized/PSR-1.json"
    })
    assert result["request_id"] == "PSR-1"


def test_load_normalized_request_rejects_attachment_blob() -> None:
    with pytest.raises(ValueError):
        policy_review_tools.load_normalized_policy_request({
            "blob_name": "policy-intake/attachments/PSR-1/license.pdf"
        })


def test_validate_rejects_unstaged_received_document() -> None:
    request = _request()
    request["documents"][0].pop("blob_name")
    with pytest.raises(ValueError):
        policy_review_tools.validate_add_driver_request({"request": request})
