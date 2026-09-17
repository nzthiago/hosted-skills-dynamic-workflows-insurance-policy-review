"""Normalize Outlook policy requests and stage their attachments."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import os
import re
from contextlib import suppress
from datetime import timedelta
from pathlib import PurePath
from typing import Any

import httpx
from azure.core.exceptions import AzureError, HttpResponseError, ResourceExistsError
from azure.identity import DefaultAzureCredential
from azure.identity.aio import DefaultAzureCredential as AsyncDefaultAzureCredential
from azure.storage.blob import BlobLeaseClient, BlobServiceClient, ContentSettings
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

logger = logging.getLogger(__name__)

DEFAULT_INTAKE_CONTAINER = "policy-intake"
SUBJECT_PREFIX = "[POLICY-REQUEST]"
SUBJECT_PATTERN = re.compile(
    r"^\[POLICY-REQUEST\]\s+"
    r"(?P<request_id>[A-Za-z0-9][A-Za-z0-9._-]{0,63})\s+\|\s+"
    r"(?P<policy_id>[A-Za-z0-9][A-Za-z0-9._-]{0,63})\s+\|\s+"
    r"(?P<driver_name>[^|\r\n]{1,120})$"
)
ATTACHMENT_PATTERN = re.compile(
    r"^(?P<document_type>driver_license|signed_request)"
    r"__(?P<document_id>[A-Za-z0-9][A-Za-z0-9._-]{0,63})"
    r"__(?P<file_name>[^/\\]+)$"
)
ALLOWED_CONTENT_TYPES = frozenset({
    "application/pdf",
    "image/jpeg",
    "image/png",
})
MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024


class IntakeRejectedError(ValueError):
    """Raised when an email does not satisfy the intake contract."""


def _storage_service() -> BlobServiceClient:
    if connection_string := os.getenv("AzureWebJobsStorage"):  # noqa: SIM112
        return BlobServiceClient.from_connection_string(connection_string)
    return BlobServiceClient(
        account_url=os.environ["POLICY_REVIEW_STORAGE_URL"],
        credential=DefaultAzureCredential(
            managed_identity_client_id=os.getenv("AZURE_CLIENT_ID")
        ),
    )


def _as_json(value: Any) -> dict[str, Any]:
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, dict):
        raise IntakeRejectedError("The connector payload must be a JSON object.")
    return value


def extract_messages(trigger_data: Any) -> list[dict[str, Any]]:
    """Extract Outlook messages from Connector Extension callback envelopes."""
    payload = _as_json(trigger_data)
    body = payload.get("body", payload)
    if isinstance(body, str):
        body = json.loads(body)
    if not isinstance(body, dict):
        raise IntakeRejectedError("The connector payload body must be an object.")
    values = body.get("value")
    if values is None and "id" in body:
        values = [body]
    if not isinstance(values, list) or not values:
        raise IntakeRejectedError("The connector payload contains no messages.")
    if not all(isinstance(item, dict) for item in values):
        raise IntakeRejectedError("Every connector payload item must be an object.")
    return values


def parse_subject(subject: Any) -> dict[str, str]:
    """Parse the documented policy-request subject convention."""
    if not isinstance(subject, str):
        raise IntakeRejectedError("The email subject is missing.")
    match = SUBJECT_PATTERN.fullmatch(subject.strip())
    if not match:
        raise IntakeRejectedError(
            f"Subject must be '{SUBJECT_PREFIX} <request-id> | <policy-id> | <driver-name>'."
        )
    values = {key: value.strip() for key, value in match.groupdict().items()}
    if not values["driver_name"]:
        raise IntakeRejectedError("Driver name must not be empty.")
    return values


def parse_attachment_metadata(message: dict[str, Any]) -> list[dict[str, Any]]:
    """Validate attachment metadata while intentionally discarding inline content."""
    if not message.get("hasAttachments"):
        raise IntakeRejectedError("The policy request must include attachments.")
    raw_attachments = message.get("attachments")
    if not isinstance(raw_attachments, list) or not raw_attachments:
        raise IntakeRejectedError(
            "The trigger did not provide attachment IDs; GetAttachment_V2 cannot be called."
        )

    attachments: list[dict[str, Any]] = []
    for raw in raw_attachments:
        if not isinstance(raw, dict):
            raise IntakeRejectedError("Attachment metadata must be an object.")
        if raw.get("isInline"):
            continue
        match = ATTACHMENT_PATTERN.fullmatch(str(raw.get("name", "")).strip())
        if not match:
            raise IntakeRejectedError(
                "Attachment names must be '<driver_license|signed_request>"
                "__<document-id>__<file-name>'."
            )
        attachment_id = raw.get("id")
        if not isinstance(attachment_id, str) or not attachment_id:
            raise IntakeRejectedError("Every attachment must include an attachment ID.")
        declared_size = raw.get("size")
        if isinstance(declared_size, int) and declared_size > MAX_ATTACHMENT_BYTES:
            raise IntakeRejectedError(
                f"Attachment '{raw.get('name')}' exceeds the 10 MiB sample limit."
            )
        metadata = match.groupdict()
        metadata.update({
            "attachment_id": attachment_id,
            "declared_content_type": raw.get("contentType"),
            "declared_size": declared_size,
        })
        attachments.append(metadata)

    if not attachments:
        raise IntakeRejectedError("The policy request has no non-inline attachments.")
    document_ids = [item["document_id"] for item in attachments]
    if len(document_ids) != len(set(document_ids)):
        raise IntakeRejectedError("Attachment document IDs must be unique.")
    return attachments


def _message_id(message: dict[str, Any]) -> str:
    value = message.get("id")
    if not isinstance(value, str) or not value:
        raise IntakeRejectedError("The email message ID is missing.")
    return value


def _unwrap_attachment_result(value: Any) -> dict[str, Any] | None:
    if isinstance(value, str):
        with suppress(json.JSONDecodeError):
            return _unwrap_attachment_result(json.loads(value))
    if isinstance(value, dict):
        if isinstance(value.get("contentBytes"), str):
            return value
        for key in ("body", "value", "result", "data"):
            if key in value:
                found = _unwrap_attachment_result(value[key])
                if found is not None:
                    return found
    if isinstance(value, list):
        for item in value:
            found = _unwrap_attachment_result(item)
            if found is not None:
                return found
    return None


def extract_attachment_result(result: Any) -> dict[str, Any]:
    """Extract a GetAttachment_V2 object from an MCP CallToolResult."""
    structured = getattr(result, "structuredContent", None)
    found = _unwrap_attachment_result(structured)
    if found is not None:
        return found

    for block in getattr(result, "content", []):
        text = getattr(block, "text", None)
        if not isinstance(text, str):
            continue
        with suppress(json.JSONDecodeError):
            found = _unwrap_attachment_result(json.loads(text))
            if found is not None:
                return found
    raise RuntimeError("GetAttachment_V2 returned no attachment content.")


async def fetch_attachment(message_id: str, attachment_id: str) -> dict[str, Any]:
    """Call the allow-listed Outlook GetAttachment_V2 Connector MCP operation."""
    endpoint = os.environ["O365_MCP_SERVER_URL"]
    client_id = os.getenv("O365_MCP_CLIENT_ID") or os.getenv("AZURE_CLIENT_ID")
    credential = AsyncDefaultAzureCredential(managed_identity_client_id=client_id)
    try:
        token = await credential.get_token("https://apihub.azure.com/.default")
    finally:
        await credential.close()

    async with httpx.AsyncClient(
        headers={"Authorization": f"Bearer {token.token}"},
        follow_redirects=True,
        timeout=60,
    ) as http_client, streamable_http_client(
        endpoint,
        http_client=http_client,
    ) as (read_stream, write_stream, _), ClientSession(
        read_stream,
        write_stream,
        read_timeout_seconds=timedelta(seconds=60),
    ) as session:
        await session.initialize()
        tools = await session.list_tools()
        candidates = [
            tool.name
            for tool in tools.tools
            if tool.name.lower().replace("-", "_").endswith("getattachment_v2")
        ]
        if len(candidates) != 1:
            raise RuntimeError(
                "Expected exactly one allow-listed GetAttachment_V2 MCP tool; "
                f"found {len(candidates)}."
            )
        result = await session.call_tool(
            candidates[0],
            {
                "messageId": message_id,
                "attachmentId": attachment_id,
            },
        )
        if result.isError:
            raise RuntimeError("GetAttachment_V2 reported an error.")
        return extract_attachment_result(result)


def _decode_attachment(
    result: dict[str, Any],
    expected: dict[str, Any],
) -> tuple[bytes, str]:
    encoded = result.get("contentBytes")
    if not isinstance(encoded, str) or not encoded:
        raise IntakeRejectedError("GetAttachment_V2 returned no content bytes.")
    try:
        content = base64.b64decode(encoded, validate=True)
    except ValueError as exc:
        raise IntakeRejectedError("Attachment content is not valid Base64.") from exc
    if len(content) > MAX_ATTACHMENT_BYTES:
        raise IntakeRejectedError("Retrieved attachment exceeds the 10 MiB sample limit.")

    content_type = result.get("contentType") or expected.get("declared_content_type")
    if not isinstance(content_type, str) or content_type.lower() not in ALLOWED_CONTENT_TYPES:
        raise IntakeRejectedError(
            f"Attachment '{expected['file_name']}' has unsupported content type."
        )
    return content, content_type.lower()


def _safe_segment(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "-", value).strip(".-") or "item"


async def _renew_lease(
    lease: BlobLeaseClient,
    lease_lost: asyncio.Event,
    interval_seconds: float = 20,
) -> None:
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            await asyncio.to_thread(lease.renew)
        except AzureError as exc:
            logger.warning("Policy-request lease renewal failed: %s", exc)
            lease_lost.set()
            return


def _raise_if_lease_lost(
    lease_lost: asyncio.Event,
    renewal_task: asyncio.Task[None],
) -> None:
    if renewal_task.done() and not renewal_task.cancelled():
        exception = renewal_task.exception()
        if exception is not None:
            raise RuntimeError("The policy-request lease renewal task failed.") from exception
    if lease_lost.is_set():
        raise RuntimeError("Lost the policy-request idempotency lease.")


async def _stage_message(
    service: BlobServiceClient,
    container_name: str,
    message: dict[str, Any],
) -> str | None:
    subject = parse_subject(message.get("subject"))
    attachments = parse_attachment_metadata(message)
    message_id = _message_id(message)
    request_id = subject["request_id"]
    manifest_name = f"normalized/{_safe_segment(request_id)}.json"
    container = service.get_container_client(container_name)
    with suppress(ResourceExistsError):
        container.create_container()
    manifest_blob = container.get_blob_client(manifest_name)
    if manifest_blob.exists():
        logger.info("Duplicate policy request ignored: request_id=%s", request_id)
        return None

    lock_blob = container.get_blob_client(f"claims/{_safe_segment(request_id)}.lock")
    with suppress(ResourceExistsError):
        lock_blob.upload_blob(b"", overwrite=False)
    lease = BlobLeaseClient(lock_blob)
    try:
        lease.acquire(lease_duration=60)
    except HttpResponseError as exc:
        if exc.status_code == 409 and exc.error_code == "LeaseAlreadyPresent":
            logger.info("Concurrent policy request ignored: request_id=%s", request_id)
            return None
        raise

    lease_lost = asyncio.Event()
    renewal_task = asyncio.create_task(_renew_lease(lease, lease_lost))
    try:
        if manifest_blob.exists():
            logger.info("Duplicate policy request ignored: request_id=%s", request_id)
            return None

        message_hash = hashlib.sha256(message_id.encode()).hexdigest()
        staged_documents: list[dict[str, Any]] = []
        for position, attachment in enumerate(attachments):
            result = await fetch_attachment(message_id, attachment["attachment_id"])
            _raise_if_lease_lost(lease_lost, renewal_task)
            content, content_type = _decode_attachment(result, attachment)
            file_name = PurePath(attachment["file_name"]).name
            blob_name = (
                f"attachments/{_safe_segment(request_id)}/"
                f"{message_hash}/"
                f"{_safe_segment(attachment['document_type'])}/"
                f"{_safe_segment(attachment['document_id'])}/{_safe_segment(file_name)}"
            )
            _raise_if_lease_lost(lease_lost, renewal_task)
            await asyncio.to_thread(
                container.get_blob_client(blob_name).upload_blob,
                content,
                overwrite=True,
                content_settings=ContentSettings(content_type=content_type),
                metadata={
                    "request_id": request_id,
                    "document_id": attachment["document_id"],
                    "source": "office365-outlook",
                },
            )
            _raise_if_lease_lost(lease_lost, renewal_task)
            staged_documents.append({
                "position": position,
                "document_id": attachment["document_id"],
                "type": attachment["document_type"],
                "file_name": file_name,
                "status": "received",
                "blob_name": blob_name,
                "content_type": content_type,
                "size": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            })

        idempotency_key = hashlib.sha256(
            f"{request_id}\0{message_id}".encode()
        ).hexdigest()
        manifest = {
            "request_id": request_id,
            "policy_id": subject["policy_id"],
            "driver_name": subject["driver_name"],
            "documents": staged_documents,
            "review_blob": f"reviews/{_safe_segment(request_id)}.html",
            "source": {
                "kind": "office365_outlook",
                "message_id_sha256": hashlib.sha256(message_id.encode()).hexdigest(),
            },
            "idempotency_key": idempotency_key,
        }
        _raise_if_lease_lost(lease_lost, renewal_task)
        try:
            await asyncio.to_thread(
                manifest_blob.upload_blob,
                json.dumps(manifest, separators=(",", ":")).encode(),
                overwrite=False,
                content_settings=ContentSettings(
                    content_type="application/json; charset=utf-8"
                ),
            )
        except ResourceExistsError:
            logger.info("Duplicate policy manifest ignored: request_id=%s", request_id)
            return None
        _raise_if_lease_lost(lease_lost, renewal_task)
        logger.info(
            "Policy request normalized: request_id=%s documents=%d",
            request_id,
            len(staged_documents),
        )
        return manifest_name
    finally:
        renewal_task.cancel()
        with suppress(asyncio.CancelledError):
            await renewal_task
        with suppress(HttpResponseError):
            lease.release()


async def process_outlook_trigger(trigger_data: Any) -> list[str]:
    """Process all messages from one callback and return created manifest names."""
    service = _storage_service()
    container_name = os.getenv("POLICY_INTAKE_CONTAINER", DEFAULT_INTAKE_CONTAINER)

    async def process_message(message: dict[str, Any]) -> str | None:
        try:
            return await _stage_message(service, container_name, message)
        except IntakeRejectedError as exc:
            logger.warning("Policy request email rejected: %s", exc)
            return None

    created = await asyncio.gather(
        *(process_message(message) for message in extract_messages(trigger_data))
    )
    return [name for name in created if name is not None]
