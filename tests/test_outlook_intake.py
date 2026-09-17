from __future__ import annotations

import asyncio
import base64
import json
from types import SimpleNamespace

import pytest
from azure.core.exceptions import (
    HttpResponseError,
    ResourceExistsError,
    ServiceRequestError,
)

import outlook_intake


def _message(request_id: str = "PSR-2026-00042") -> dict:
    return {
        "id": "message-123",
        "subject": f"[POLICY-REQUEST] {request_id} | AUTO-100042 | Jordan Lee",
        "hasAttachments": True,
        "attachments": [
            {
                "id": "attachment-1",
                "name": "driver_license__DOC-001__license.pdf",
                "contentType": "application/pdf",
                "size": 12,
                "isInline": False,
                "contentBytes": "ignored-inline-value",
            },
            {
                "id": "inline-1",
                "name": "signature.png",
                "contentType": "image/png",
                "size": 4,
                "isInline": True,
            },
        ],
    }


def test_extract_messages_supports_connector_envelope() -> None:
    message = _message()
    assert outlook_intake.extract_messages(
        json.dumps({"body": {"value": [message]}})
    ) == [message]


@pytest.mark.parametrize(
    "subject",
    [
        "[POLICY REQUEST] PSR-1 | AUTO-1 | Jordan Lee",
        "[POLICY-REQUEST] missing-fields",
        "[POLICY-REQUEST] PSR-1 | AUTO-1 | ",
    ],
)
def test_parse_subject_rejects_non_contract_subjects(subject: str) -> None:
    with pytest.raises(outlook_intake.IntakeRejectedError):
        outlook_intake.parse_subject(subject)


def test_attachment_metadata_ignores_inline_body_and_requires_ids() -> None:
    attachments = outlook_intake.parse_attachment_metadata(_message())
    assert attachments == [
        {
            "document_type": "driver_license",
            "document_id": "DOC-001",
            "file_name": "license.pdf",
            "attachment_id": "attachment-1",
            "declared_content_type": "application/pdf",
            "declared_size": 12,
        }
    ]
    assert "contentBytes" not in attachments[0]


def test_extract_attachment_result_accepts_structured_content() -> None:
    result = SimpleNamespace(
        structuredContent={
            "body": {
                "contentBytes": base64.b64encode(b"pdf").decode(),
                "contentType": "application/pdf",
            }
        },
        content=[],
    )
    assert outlook_intake.extract_attachment_result(result)["contentType"] == "application/pdf"


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

    def renew(self) -> None:
        pass

    def release(self) -> None:
        pass


def _lease_error(status_code: int, error_code: str) -> HttpResponseError:
    response = SimpleNamespace(
        status_code=status_code,
        reason="test",
        headers={},
    )
    error = HttpResponseError(message=error_code, response=response)
    error.error_code = error_code
    return error


def test_stage_message_is_idempotent_and_retrieves_attachment(monkeypatch) -> None:
    service = FakeService()
    calls: list[tuple[str, str]] = []

    async def fake_fetch(message_id: str, attachment_id: str) -> dict:
        calls.append((message_id, attachment_id))
        return {
            "contentBytes": base64.b64encode(b"%PDF-sample").decode(),
            "contentType": "application/pdf",
        }

    monkeypatch.setattr(outlook_intake, "fetch_attachment", fake_fetch)
    monkeypatch.setattr(outlook_intake, "BlobLeaseClient", FakeLease)

    first = asyncio.run(
        outlook_intake._stage_message(service, "policy-intake", _message())
    )
    second = asyncio.run(
        outlook_intake._stage_message(service, "policy-intake", _message())
    )

    assert first == "normalized/PSR-2026-00042.json"
    assert second is None
    assert calls == [("message-123", "attachment-1")]
    manifest = json.loads(service.container.store[first])
    assert manifest["documents"][0]["blob_name"].startswith(
        "attachments/PSR-2026-00042/"
    )
    assert "/driver_license/DOC-001/" in manifest["documents"][0]["blob_name"]
    assert "message-123" not in manifest["documents"][0]["blob_name"]
    assert manifest["documents"][0]["status"] == "received"
    assert manifest["source"]["message_id_sha256"] != "message-123"


def test_decode_attachment_rejects_unsupported_mime_type() -> None:
    with pytest.raises(outlook_intake.IntakeRejectedError):
        outlook_intake._decode_attachment(
            {
                "contentBytes": base64.b64encode(b"data").decode(),
                "contentType": "application/octet-stream",
            },
            {"file_name": "payload.bin"},
        )


def test_stage_message_aborts_when_idempotency_lease_is_lost(monkeypatch) -> None:
    service = FakeService()

    async def fake_fetch(_: str, __: str) -> dict:
        await asyncio.sleep(0)
        return {
            "contentBytes": base64.b64encode(b"%PDF-sample").decode(),
            "contentType": "application/pdf",
        }

    async def lose_lease(_: FakeLease, lease_lost: asyncio.Event) -> None:
        lease_lost.set()

    monkeypatch.setattr(outlook_intake, "fetch_attachment", fake_fetch)
    monkeypatch.setattr(outlook_intake, "BlobLeaseClient", FakeLease)
    monkeypatch.setattr(outlook_intake, "_renew_lease", lose_lease)

    with pytest.raises(RuntimeError, match="idempotency lease"):
        asyncio.run(
            outlook_intake._stage_message(
                service,
                "policy-intake",
                _message(),
            )
        )

    assert "normalized/PSR-2026-00042.json" not in service.container.store


def test_stage_message_ignores_only_active_lease_conflict(monkeypatch) -> None:
    service = FakeService()

    class ConflictingLease(FakeLease):
        def acquire(self, *, lease_duration: int) -> None:
            raise _lease_error(409, "LeaseAlreadyPresent")

    monkeypatch.setattr(outlook_intake, "BlobLeaseClient", ConflictingLease)

    result = asyncio.run(
        outlook_intake._stage_message(service, "policy-intake", _message())
    )
    assert result is None


def test_stage_message_propagates_non_conflict_lease_failure(monkeypatch) -> None:
    service = FakeService()

    class UnauthorizedLease(FakeLease):
        def acquire(self, *, lease_duration: int) -> None:
            raise _lease_error(403, "AuthorizationFailure")

    monkeypatch.setattr(outlook_intake, "BlobLeaseClient", UnauthorizedLease)

    with pytest.raises(HttpResponseError):
        asyncio.run(
            outlook_intake._stage_message(service, "policy-intake", _message())
        )


def test_renewal_transport_failure_marks_lease_lost() -> None:
    lease_lost = asyncio.Event()

    class TransportFailureLease(FakeLease):
        def renew(self) -> None:
            raise ServiceRequestError("transport unavailable")

    asyncio.run(
        outlook_intake._renew_lease(
            TransportFailureLease(FakeBlob({}, "lock")),
            lease_lost,
            interval_seconds=0,
        )
    )

    assert lease_lost.is_set()


def test_process_trigger_drops_invalid_mail_without_retry(monkeypatch) -> None:
    monkeypatch.setattr(outlook_intake, "_storage_service", FakeService)
    invalid = _message()
    invalid["subject"] = "[POLICY-REQUEST] malformed"
    result = asyncio.run(
        outlook_intake.process_outlook_trigger({"body": {"value": [invalid]}})
    )
    assert result == []
