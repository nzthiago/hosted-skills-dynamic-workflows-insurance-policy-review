"""Normalize created Dataverse policy-service-request rows."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from contextlib import suppress
from typing import Any

from azure.core.exceptions import HttpResponseError, ResourceExistsError
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobLeaseClient, BlobServiceClient, ContentSettings

logger = logging.getLogger(__name__)

DEFAULT_INTAKE_CONTAINER = "policy-intake"
DEFAULT_TABLE_NAME = "ipr_policyservicerequests"
SAFE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
ALLOWED_DOCUMENT_STATUSES = frozenset({"received", "missing", "expired"})

COLUMNS = {
    "request_id": "ipr_requestid",
    "policy_id": "ipr_policyid",
    "driver_name": "ipr_drivername",
    "driver_licence_file_name": "ipr_driverlicencefilename",
    "driver_licence_status": "ipr_driverlicencestatus",
    "signed_request_file_name": "ipr_signedrequestfilename",
    "signed_request_status": "ipr_signedrequeststatus",
    "review_blob": "ipr_reviewblobname",
}


class IntakeRejectedError(ValueError):
    """Raised when a Dataverse row does not satisfy the intake contract."""


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


def extract_rows(trigger_data: Any) -> list[dict[str, Any]]:
    """Extract created rows from the GetOnNewItems_V2 callback envelope."""
    payload = _as_json(trigger_data)
    body = payload.get("body", payload)
    if isinstance(body, str):
        body = json.loads(body)
    if not isinstance(body, dict):
        raise IntakeRejectedError("The connector payload body must be an object.")
    values = body.get("value")
    if values is None:
        values = [body]
    if not isinstance(values, list) or not values:
        raise IntakeRejectedError("The connector payload contains no Dataverse rows.")
    if not all(isinstance(item, dict) for item in values):
        raise IntakeRejectedError("Every Dataverse payload item must be an object.")
    return values


def _required_text(row: dict[str, Any], column: str, label: str) -> str:
    value = row.get(column)
    if not isinstance(value, str) or not value.strip():
        raise IntakeRejectedError(f"{label} ({column}) must be a non-empty string.")
    return value.strip()


def _safe_identifier(value: str, label: str) -> str:
    if not SAFE_ID_PATTERN.fullmatch(value):
        raise IntakeRejectedError(
            f"{label} must contain only letters, numbers, dot, underscore, or dash."
        )
    return value


def _safe_review_blob(value: str, request_id: str) -> str:
    value = value.strip() or f"reviews/{request_id}.html"
    if not value.startswith("reviews/"):
        value = f"reviews/{value}"
    if (
        not value.endswith(".html")
        or ".." in value
        or "\\" in value
        or value.count("/") != 1
    ):
        raise IntakeRejectedError(
            f"{COLUMNS['review_blob']} must name one safe HTML Blob under reviews/."
        )
    return value


def _row_id(row: dict[str, Any]) -> str:
    table = os.getenv("DATAVERSE_TABLE_NAME", DEFAULT_TABLE_NAME)
    singular = table[:-1] if table.endswith("s") else table
    value = row.get("ItemInternalId") or row.get(f"{singular}id")
    if not isinstance(value, str) or not value.strip():
        raise IntakeRejectedError("The Dataverse row ID is missing.")
    return value.strip()


def normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    """Map one Policy Service Request row to the existing workflow schema."""
    row_id = _row_id(row)
    request_id = _safe_identifier(
        _required_text(row, COLUMNS["request_id"], "Request ID"),
        "Request ID",
    )
    policy_id = _safe_identifier(
        _required_text(row, COLUMNS["policy_id"], "Policy ID"),
        "Policy ID",
    )
    driver_name = _required_text(row, COLUMNS["driver_name"], "Driver name")
    driver_licence_file_name = _required_text(
        row,
        COLUMNS["driver_licence_file_name"],
        "Driver licence filename",
    )
    signed_request_file_name = _required_text(
        row,
        COLUMNS["signed_request_file_name"],
        "Signed request filename",
    )
    driver_licence_status = _required_text(
        row,
        COLUMNS["driver_licence_status"],
        "Driver licence status",
    ).lower()
    signed_request_status = _required_text(
        row,
        COLUMNS["signed_request_status"],
        "Signed request status",
    ).lower()
    for label, status in (
        ("Driver licence status", driver_licence_status),
        ("Signed request status", signed_request_status),
    ):
        if status not in ALLOWED_DOCUMENT_STATUSES:
            raise IntakeRejectedError(
                f"{label} must be received, missing, or expired."
            )

    documents = [
        {
            "position": 0,
            "document_id": f"{row_id}-driver-licence",
            "type": "driver_license",
            "file_name": driver_licence_file_name,
            "status": driver_licence_status,
        },
        {
            "position": 1,
            "document_id": f"{row_id}-signed-request",
            "type": "signed_request",
            "file_name": signed_request_file_name,
            "status": signed_request_status,
        },
    ]
    review_blob_value = row.get(COLUMNS["review_blob"], "")
    if review_blob_value is None:
        review_blob_value = ""
    if not isinstance(review_blob_value, str):
        raise IntakeRejectedError(
            f"Review blob name ({COLUMNS['review_blob']}) must be a string."
        )

    return {
        "request_id": request_id,
        "policy_id": policy_id,
        "driver_name": driver_name,
        "documents": documents,
        "review_blob": _safe_review_blob(review_blob_value, request_id),
        "source": {
            "kind": "dataverse",
            "table": os.getenv("DATAVERSE_TABLE_NAME", DEFAULT_TABLE_NAME),
            "row_id": row_id,
        },
        "idempotency_key": hashlib.sha256(
            f"dataverse\0{row_id}\0{request_id}".encode()
        ).hexdigest(),
    }


def _stage_row(
    service: BlobServiceClient,
    container_name: str,
    row: dict[str, Any],
) -> str | None:
    manifest = normalize_row(row)
    request_id = manifest["request_id"]
    manifest_name = f"normalized/{request_id}.json"
    container = service.get_container_client(container_name)
    with suppress(ResourceExistsError):
        container.create_container()
    manifest_blob = container.get_blob_client(manifest_name)
    if manifest_blob.exists():
        logger.info("Duplicate Dataverse request ignored: request_id=%s", request_id)
        return None

    lock_blob = container.get_blob_client(f"claims/{request_id}.lock")
    with suppress(ResourceExistsError):
        lock_blob.upload_blob(b"", overwrite=False)
    lease = BlobLeaseClient(lock_blob)
    try:
        lease.acquire(lease_duration=60)
    except HttpResponseError as exc:
        if exc.status_code == 409 and exc.error_code == "LeaseAlreadyPresent":
            logger.info("Concurrent Dataverse request ignored: request_id=%s", request_id)
            return None
        raise

    try:
        if manifest_blob.exists():
            logger.info("Duplicate Dataverse request ignored: request_id=%s", request_id)
            return None
        try:
            manifest_blob.upload_blob(
                json.dumps(manifest, separators=(",", ":")).encode(),
                overwrite=False,
                content_settings=ContentSettings(
                    content_type="application/json; charset=utf-8"
                ),
            )
        except ResourceExistsError:
            logger.info("Duplicate Dataverse manifest ignored: request_id=%s", request_id)
            return None
        logger.info("Dataverse request normalized: request_id=%s", request_id)
        return manifest_name
    finally:
        with suppress(HttpResponseError):
            lease.release()


def process_dataverse_trigger(trigger_data: Any) -> list[str]:
    """Process a created-row callback and return newly created manifest names."""
    service = _storage_service()
    container_name = os.getenv("POLICY_INTAKE_CONTAINER", DEFAULT_INTAKE_CONTAINER)
    created: list[str] = []
    for row in extract_rows(trigger_data):
        try:
            manifest_name = _stage_row(service, container_name, row)
        except IntakeRejectedError as exc:
            logger.warning("Policy Service Request row rejected: %s", exc)
            continue
        if manifest_name is not None:
            created.append(manifest_name)
    return created
