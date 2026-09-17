"""Workflow tools for the add-driver policy review."""

import html
import json
import logging
import os
from contextlib import suppress
from typing import Any

from azure.core.exceptions import ResourceExistsError
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient, ContentSettings
from azure_functions_agents import workflow_tool

logger = logging.getLogger(__name__)

REQUIRED_DOCUMENTS = ("driver_license", "signed_request")
ALLOWED_DOCUMENT_STATUSES = frozenset({"received", "missing", "expired"})
DEFAULT_CONTAINER = "policy-review-packets"
DEFAULT_INTAKE_CONTAINER = "policy-intake"


def _blob_service() -> BlobServiceClient:
    if connection_string := os.getenv("AzureWebJobsStorage"):  # noqa: SIM112
        return BlobServiceClient.from_connection_string(connection_string)
    return BlobServiceClient(
        account_url=os.environ["POLICY_REVIEW_STORAGE_URL"],
        credential=DefaultAzureCredential(
            managed_identity_client_id=os.getenv("AZURE_CLIENT_ID")
        ),
    )


@workflow_tool(
    description=(
        "Load one normalized policy request from the intake Blob trigger. "
        "Args: {blob_name: <trigger Blob name>}. Returns the JSON request object."
    )
)
def load_normalized_policy_request(args: dict[str, Any]) -> dict[str, Any]:
    blob_name = str(args["blob_name"])
    prefix = f"{DEFAULT_INTAKE_CONTAINER}/"
    if blob_name.startswith(prefix):
        blob_name = blob_name[len(prefix) :]
    if (
        not blob_name.startswith("normalized/")
        or not blob_name.endswith(".json")
        or ".." in blob_name
        or "\\" in blob_name
    ):
        raise ValueError("Expected a normalized policy-request Blob.")
    container_name = os.getenv("POLICY_INTAKE_CONTAINER", DEFAULT_INTAKE_CONTAINER)
    data = (
        _blob_service()
        .get_blob_client(container=container_name, blob=blob_name)
        .download_blob()
        .readall()
    )
    request = json.loads(data)
    if not isinstance(request, dict):
        raise ValueError("Normalized policy request must be a JSON object.")
    return request


@workflow_tool(
    description=(
        "Validate an add-driver request. Args: {request: <body_json>}. "
        "Returns request_id, policy_id, driver_name, documents, and review_blob."
    )
)
def validate_add_driver_request(args: dict[str, Any]) -> dict[str, Any]:
    request = args["request"]
    if not isinstance(request, dict):
        raise ValueError("request must be an object")
    request_id = request.get("request_id")
    policy_id = request.get("policy_id")
    driver_name = request.get("driver_name")
    documents = request.get("documents", [])
    review_blob = request.get("review_blob", f"reviews/{request_id}.html")
    for field_name, value in (
        ("request_id", request_id),
        ("policy_id", policy_id),
        ("driver_name", driver_name),
    ):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field_name} must be a non-empty string")
    if not isinstance(documents, list):
        raise ValueError("documents must be an array")
    if (
        not isinstance(review_blob, str)
        or not review_blob.startswith("reviews/")
        or not review_blob.endswith(".html")
        or ".." in review_blob
        or "\\" in review_blob
    ):
        raise ValueError("review_blob must be a safe reviews/*.html Blob name")

    for document in documents:
        if not isinstance(document, dict):
            raise ValueError("documents must contain objects")
        for field_name in ("document_id", "type", "file_name"):
            value = document.get(field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"document {field_name} must be a non-empty string")
        if document.get("status") not in ALLOWED_DOCUMENT_STATUSES:
            raise ValueError("document status must be received, missing, or expired")
        blob_name = document.get("blob_name")
        if blob_name is not None and (
            not isinstance(blob_name, str)
            or not blob_name.startswith("attachments/")
            or ".." in blob_name
            or "\\" in blob_name
        ):
            raise ValueError("blob_name must reference a safe staged attachment Blob")

    return {
        "request_id": request_id,
        "policy_id": policy_id,
        "driver_name": driver_name,
        "documents": documents,
        "review_blob": review_blob,
    }


@workflow_tool(
    description=(
        "Inspect one document from an add-driver request. Args: "
        "{document: <document>, position: int}. Returns the document and evidence state."
    )
)
def inspect_driver_document(args: dict[str, Any]) -> dict[str, Any]:
    document = args["document"]
    evidence_state = {
        "received": "present",
        "missing": "missing",
        "expired": "needs_current_copy",
    }[document["status"]]

    return {
        "position": args["position"],
        "document_id": document["document_id"],
        "type": document["type"],
        "file_name": document["file_name"],
        "evidence_state": evidence_state,
    }


@workflow_tool(
    description=(
        "Build HTML from a validated request and the complete document for_each result. "
        "Args: {request: <validation result>, document_checks: <for_each result>}."
    )
)
def build_driver_review_report(args: dict[str, Any]) -> dict[str, Any]:
    request = args["request"]
    checks = [item["result"] for item in args["document_checks"]]
    present = {
        check["type"] for check in checks if check["evidence_state"] == "present"
    }
    missing = [kind for kind in REQUIRED_DOCUMENTS if kind not in present]

    rows = "".join(
        "<tr>"
        f"<td>{check['position'] + 1}</td>"
        f"<td>{html.escape(check['type'])}</td>"
        f"<td>{html.escape(check['file_name'])}</td>"
        f"<td>{html.escape(check['evidence_state'])}</td>"
        "</tr>"
        for check in checks
    ) or '<tr><td colspan="4">No documents submitted.</td></tr>'

    missing_items = "".join(f"<li>{html.escape(kind)}</li>" for kind in missing)
    missing_html = f"<ul>{missing_items}</ul>" if missing else "<p>None.</p>"

    request_id = request["request_id"]
    report_html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Add-driver review {html.escape(request_id)}</title>
  <style>
    body {{ max-width: 800px; margin: 40px auto; font: 16px system-ui; }}
    .notice {{ padding: 12px; background: #fff4ce; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ padding: 8px; border-bottom: 1px solid #ddd; text-align: left; }}
  </style>
</head>
<body>
  <h1>Add-driver document review</h1>
  <p class="notice"><strong>Human review required.</strong> No decision has been made.</p>
  <p><strong>Policy:</strong> {html.escape(request['policy_id'])}<br>
     <strong>Driver:</strong> {html.escape(request['driver_name'])}</p>
  <h2>Documents</h2>
  <table>
    <tr><th>#</th><th>Type</th><th>File</th><th>Status</th></tr>
    {rows}
  </table>
  <h2>Missing required documents</h2>
  {missing_html}
  <p>Verify the documents before updating the policy.</p>
</body>
</html>"""

    return {
        "html": report_html,
        "request_id": request_id,
        "review_status": "human_review_required",
        "decision": None,
        "missing_documents": missing,
    }


@workflow_tool(
    description=(
        "Publish an add-driver review to Blob Storage. Args: "
        "{report: <review report>, blob_name: str}. Overwrites the Blob for safe retries."
    )
)
def publish_driver_review_report(args: dict[str, Any]) -> dict[str, Any]:
    report = args["report"]
    container_name = os.getenv("POLICY_REVIEW_CONTAINER", DEFAULT_CONTAINER)
    service = _blob_service()

    container = service.get_container_client(container_name)
    with suppress(ResourceExistsError):
        container.create_container()
    container.get_blob_client(args["blob_name"]).upload_blob(
        report["html"].encode(),
        overwrite=True,
        content_settings=ContentSettings(content_type="text/html; charset=utf-8"),
    )

    result = {
        "container": container_name,
        "blob_name": args["blob_name"],
        "request_id": report["request_id"],
        "review_status": report["review_status"],
        "decision": report["decision"],
    }
    logger.info("Driver review published: %s", result)
    return result
