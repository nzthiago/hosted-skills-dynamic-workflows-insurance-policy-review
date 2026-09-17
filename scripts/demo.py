"""Submit a normalized fallback request or download its generated report."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from contextlib import suppress
from pathlib import Path
from typing import Any

from azure.core.exceptions import ResourceExistsError, ResourceNotFoundError
from azure.identity import AzureDeveloperCliCredential
from azure.storage.blob import BlobServiceClient, ContentSettings

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REQUEST = ROOT / "examples" / "policy-service-request.json"
DEFAULT_OUTPUT = ROOT / "output" / "PSR-2026-00042.html"
DEFAULT_BLOB = "reviews/PSR-2026-00042.html"
DEFAULT_CONNECTION = "UseDevelopmentStorage=true"
DEFAULT_CONTAINER = "policy-review-packets"
DEFAULT_INTAKE_CONTAINER = "policy-intake"
SAFE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def _connection_string() -> str:
    return os.environ.get("AzureWebJobsStorage", DEFAULT_CONNECTION)  # noqa: SIM112


def _container_name() -> str:
    return os.environ.get("POLICY_REVIEW_CONTAINER", DEFAULT_CONTAINER)


def _intake_container_name() -> str:
    return os.environ.get("POLICY_INTAKE_CONTAINER", DEFAULT_INTAKE_CONTAINER)


def _blob_service_client() -> BlobServiceClient:
    storage_url = os.environ.get("POLICY_REVIEW_STORAGE_URL")
    if storage_url:
        return BlobServiceClient(
            account_url=storage_url,
            credential=AzureDeveloperCliCredential(),
        )
    return BlobServiceClient.from_connection_string(_connection_string())


def _read_request(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain one JSON object")
    return value


def submit_manual(request_path: Path) -> None:
    request = _read_request(request_path)
    request_id = request.get("request_id")
    if not isinstance(request_id, str) or not SAFE_ID_PATTERN.fullmatch(request_id):
        raise ValueError("request_id must contain only letters, numbers, dot, underscore, or dash")

    service = _blob_service_client()
    container_name = _intake_container_name()
    container = service.get_container_client(container_name)
    with suppress(ResourceExistsError):
        container.create_container()

    documents = request.get("documents", [])
    if not isinstance(documents, list):
        raise ValueError("documents must be an array")
    normalized_documents: list[dict[str, Any]] = []
    for position, document in enumerate(documents):
        if not isinstance(document, dict):
            raise ValueError("documents must contain objects")
        normalized = dict(document)
        normalized.setdefault("position", position)
        normalized_documents.append(normalized)

    request["documents"] = normalized_documents
    request.setdefault("review_blob", f"reviews/{request_id}.html")
    request.setdefault("source", {"kind": "manual_fallback"})
    request.setdefault(
        "idempotency_key",
        hashlib.sha256(f"manual\0{request_id}".encode()).hexdigest(),
    )
    manifest_name = f"normalized/{request_id}.json"
    try:
        container.get_blob_client(manifest_name).upload_blob(
            json.dumps(request, separators=(",", ":")).encode(),
            overwrite=False,
            content_settings=ContentSettings(
                content_type="application/json; charset=utf-8"
            ),
        )
    except ResourceExistsError as exc:
        raise RuntimeError(
            f"Request {request_id} was already submitted; use a new request_id."
        ) from exc

    print(
        f"Submitted fallback request {request_id} "
        f"with {len(normalized_documents)} document records."
    )
    print(f"Manifest: {container_name}/{manifest_name}")
    print(f"Report destination: {_container_name()}/{request['review_blob']}")


def download(blob_name: str, output_path: Path) -> None:
    service = _blob_service_client()
    container_name = _container_name()
    blob = service.get_blob_client(container=container_name, blob=blob_name)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(blob.download_blob().readall())
    print(f"Downloaded {container_name}/{blob_name}")
    print(f"Output: {output_path.resolve()}")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="action", required=True)

    submit_parser = subparsers.add_parser(
        "submit-manual",
        help="Create a normalized metadata request Blob without Dataverse.",
    )
    submit_parser.add_argument(
        "--request",
        type=Path,
        default=DEFAULT_REQUEST,
        help=f"Request JSON path. Default: {DEFAULT_REQUEST}",
    )

    download_parser = subparsers.add_parser(
        "download",
        help="Download the generated HTML review packet.",
    )
    download_parser.add_argument("--blob", default=DEFAULT_BLOB)
    download_parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def main() -> None:
    args = _parser().parse_args()
    if args.action == "submit-manual":
        submit_manual(args.request)
        return
    try:
        download(args.blob, args.output)
    except ResourceNotFoundError as exc:
        raise SystemExit("The report is not available yet.") from exc


if __name__ == "__main__":
    main()
