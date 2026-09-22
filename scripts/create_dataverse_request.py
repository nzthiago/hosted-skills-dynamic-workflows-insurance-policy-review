"""Create a Dataverse Policy Service Request and optionally wait for its report."""

from __future__ import annotations

import argparse
import re
import secrets
import shutil
import subprocess
import sys
import time
import urllib.parse
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from azure.identity import AzureCliCredential
from azure.storage.blob import BlobServiceClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import setup_dataverse_schema  # noqa: E402

DEFAULT_TABLE = "ipr_policyservicerequests"
DEFAULT_INTAKE_CONTAINER = "policy-intake"
DEFAULT_REPORT_CONTAINER = "policy-review-packets"
DEFAULT_TIMEOUT_MINUTES = 15
DEFAULT_POLL_SECONDS = 15
SAFE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def _azd_value(key: str, environment: str | None) -> str | None:
    if shutil.which("azd") is None:
        return None
    command = ["azd", "env", "get-value", key, "-C", str(ROOT), "--no-prompt"]
    if environment:
        command.extend(["--environment", environment])
    result = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
    )
    value = result.stdout.strip()
    if result.returncode != 0 or not value or "key not found" in value.lower():
        return None
    return value


def _resolve_environment(
    *,
    environment_url: str | None,
    environment_id: str | None,
    environment_name: str | None,
    azd_environment: str | None,
) -> tuple[str, str | None]:
    environment_url = environment_url or _azd_value(
        "DATAVERSE_ENVIRONMENT_URL", azd_environment
    )
    environment_id = environment_id or _azd_value(
        "DATAVERSE_ENVIRONMENT_ID", azd_environment
    )
    environment_name = environment_name or _azd_value(
        "DATAVERSE_ENVIRONMENT_NAME", azd_environment
    )
    if environment_url:
        return environment_url.rstrip("/"), environment_id
    if environment_id or environment_name:
        return (
            setup_dataverse_schema.resolve_environment_url(
                environment_id=environment_id,
                environment_name=environment_name,
            ),
            environment_id,
        )
    raise RuntimeError(
        "Set --environment-url, --environment-id, or --environment-name, "
        "or select an azd environment containing the Dataverse settings."
    )


def _safe_identifier(value: str, label: str) -> str:
    value = value.strip()
    if not SAFE_ID_PATTERN.fullmatch(value):
        raise ValueError(
            f"{label} must contain only letters, numbers, dot, underscore, or dash."
        )
    return value


def _required_text(value: str, label: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError(f"{label} must be a non-empty string.")
    return value


def _default_request_id() -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    return f"PSR-DV-{timestamp}-{secrets.token_hex(4).upper()}"


def _default_policy_id() -> str:
    return "AUTO-" + datetime.now(UTC).strftime("%Y%m%d%H%M%S")


def _odata_request(
    environment_url: str,
    token: str,
    method: str,
    path: str,
    *,
    body: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    return setup_dataverse_schema._request(
        environment_url,
        token,
        method,
        path,
        body=body,
    )


def _existing_row_id(
    environment_url: str,
    token: str,
    table_name: str,
    request_id: str,
) -> str | None:
    primary_key = f"{table_name.removesuffix('s')}id"
    query = urllib.parse.urlencode(
        {
            "$select": primary_key,
            "$filter": f"ipr_requestid eq '{request_id}'",
            "$top": "1",
        }
    )
    response = _odata_request(
        environment_url,
        token,
        "GET",
        f"{table_name}?{query}",
    )
    rows = response.get("value") if isinstance(response, dict) else None
    if not isinstance(rows, list) or not rows:
        return None
    row = rows[0]
    if not isinstance(row, dict):
        raise RuntimeError("Dataverse returned an unexpected row response.")
    row_id = row.get(primary_key)
    if not isinstance(row_id, str) or not row_id:
        raise RuntimeError("Dataverse returned an existing row without its row ID.")
    return row_id


def _create_row(
    environment_url: str,
    token: str,
    table_name: str,
    values: dict[str, str],
) -> str:
    request_id = values["ipr_requestid"]
    if _existing_row_id(
        environment_url,
        token,
        table_name,
        request_id,
    ):
        raise RuntimeError(
            f"Request ID {request_id} already exists. Use a new Request ID."
        )

    response = _odata_request(
        environment_url,
        token,
        "POST",
        table_name,
        body=values,
    )
    primary_key = f"{table_name.removesuffix('s')}id"
    row_id = response.get(primary_key) if isinstance(response, dict) else None
    if not isinstance(row_id, str) or not row_id:
        raise RuntimeError("Dataverse created the row but did not return its row ID.")
    return row_id


def _blob_service(storage_url: str) -> BlobServiceClient:
    return BlobServiceClient(
        account_url=storage_url.rstrip("/") + "/",
        credential=AzureCliCredential(),
    )


def _wait_for_blob(
    blob_client: Any,
    *,
    stage: str,
    deadline: float,
    poll_seconds: int,
) -> None:
    started = time.monotonic()
    while True:
        if blob_client.exists():
            elapsed = round(time.monotonic() - started)
            print(f"{stage}: ready after {elapsed}s")
            return
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(f"Timed out waiting for {stage.lower()}.")
        time.sleep(min(poll_seconds, remaining))


def _wait_for_outputs(
    *,
    storage_url: str,
    intake_container: str,
    report_container: str,
    request_id: str,
    report_blob: str,
    timeout_minutes: int,
    poll_seconds: int,
    download_report: bool,
    output_dir: Path,
) -> Path | None:
    service = _blob_service(storage_url)
    manifest_name = f"normalized/{request_id}.json"
    deadline = time.monotonic() + timeout_minutes * 60
    print(
        "Normalized manifest: waiting "
        f"(the connector polls every five minutes; timeout {timeout_minutes} minutes)"
    )
    _wait_for_blob(
        service.get_blob_client(intake_container, manifest_name),
        stage="Normalized manifest",
        deadline=deadline,
        poll_seconds=poll_seconds,
    )
    print("HTML report: waiting for Event Grid, Functions.main, and DTS")
    report = service.get_blob_client(report_container, report_blob)
    _wait_for_blob(
        report,
        stage="HTML report",
        deadline=deadline,
        poll_seconds=poll_seconds,
    )
    if not download_report:
        return None
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{request_id}.html"
    output_path.write_bytes(report.download_blob().readall())
    return output_path


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    environment = parser.add_mutually_exclusive_group()
    environment.add_argument("--environment-url")
    environment.add_argument("--environment-id")
    environment.add_argument("--environment-name")
    parser.add_argument(
        "--azd-environment",
        help="azd environment containing ignored deployment outputs and Dataverse settings.",
    )
    parser.add_argument("--table-name")
    parser.add_argument("--request-id")
    parser.add_argument("--policy-id")
    parser.add_argument("--driver-name", default="Jordan Lee")
    parser.add_argument(
        "--driver-licence-filename",
        default="jordan-lee-license.pdf",
    )
    parser.add_argument(
        "--driver-licence-status",
        choices=("received", "missing", "expired"),
        default="received",
    )
    parser.add_argument(
        "--signed-request-filename",
        default="signed-request.pdf",
    )
    parser.add_argument(
        "--signed-request-status",
        choices=("received", "missing", "expired"),
        default="missing",
    )
    parser.add_argument("--review-blob")
    parser.add_argument(
        "--auth-source",
        choices=("azure-cli", "auto", "pac"),
        default="azure-cli",
        help="Dataverse authentication source. Azure CLI is the corporate CA-friendly default.",
    )
    parser.add_argument(
        "--wait",
        action="store_true",
        help="Wait for both the normalized manifest and generated HTML report.",
    )
    parser.add_argument(
        "--timeout-minutes",
        type=int,
        default=DEFAULT_TIMEOUT_MINUTES,
    )
    parser.add_argument(
        "--poll-seconds",
        type=int,
        default=DEFAULT_POLL_SECONDS,
        help=argparse.SUPPRESS,
    )
    parser.add_argument("--storage-url")
    parser.add_argument("--intake-container")
    parser.add_argument("--report-container")
    parser.add_argument(
        "--download-report",
        action="store_true",
        help="Download the report to output/<request-id>.html; implies --wait.",
    )
    parser.add_argument("--output-dir", type=Path, default=ROOT / "output")
    return parser


def main() -> None:
    args = _parser().parse_args()
    if args.timeout_minutes <= 0 or args.poll_seconds <= 0:
        raise SystemExit("Timeout and polling interval must be positive.")

    environment_url, environment_id = _resolve_environment(
        environment_url=args.environment_url,
        environment_id=args.environment_id,
        environment_name=args.environment_name,
        azd_environment=args.azd_environment,
    )
    table_name = (
        args.table_name
        or _azd_value("DATAVERSE_TABLE_NAME", args.azd_environment)
        or DEFAULT_TABLE
    )
    request_id = _safe_identifier(
        args.request_id or _default_request_id(),
        "Request ID",
    )
    policy_id = _safe_identifier(
        args.policy_id or _default_policy_id(),
        "Policy ID",
    )
    review_blob = args.review_blob or f"reviews/{request_id}.html"
    if (
        not review_blob.startswith("reviews/")
        or not review_blob.endswith(".html")
        or ".." in review_blob
        or "\\" in review_blob
        or review_blob.count("/") != 1
    ):
        raise SystemExit("--review-blob must be one safe HTML Blob under reviews/.")

    token = setup_dataverse_schema._acquire_dataverse_access_token(
        environment_url,
        args.auth_source,
    )
    row_id = _create_row(
        environment_url,
        token,
        table_name,
        {
            "ipr_requestid": request_id,
            "ipr_policyid": policy_id,
            "ipr_drivername": _required_text(args.driver_name, "Driver name"),
            "ipr_driverlicencefilename": _required_text(
                args.driver_licence_filename,
                "Driver licence filename",
            ),
            "ipr_driverlicencestatus": args.driver_licence_status,
            "ipr_signedrequestfilename": _required_text(
                args.signed_request_filename,
                "Signed request filename",
            ),
            "ipr_signedrequeststatus": args.signed_request_status,
            "ipr_reviewblobname": review_blob,
        },
    )

    intake_container = (
        args.intake_container
        or _azd_value("POLICY_INTAKE_CONTAINER", args.azd_environment)
        or DEFAULT_INTAKE_CONTAINER
    )
    report_container = (
        args.report_container
        or _azd_value("POLICY_REVIEW_CONTAINER", args.azd_environment)
        or DEFAULT_REPORT_CONTAINER
    )
    print(f"Request ID: {request_id}")
    print(f"Dataverse row ID: {row_id}")
    print(f"Dataverse environment: {environment_url}")
    if environment_id:
        print(f"Power Apps environment ID: {environment_id}")
    print(f"Expected manifest: {intake_container}/normalized/{request_id}.json")
    print(f"Expected report: {report_container}/{review_blob}")

    should_wait = args.wait or args.download_report
    if not should_wait:
        print(
            "The connector polls every five minutes. Re-run with --wait to monitor "
            "the manifest and report."
        )
        return

    storage_url = args.storage_url or _azd_value(
        "POLICY_REVIEW_STORAGE_URL", args.azd_environment
    )
    if not storage_url:
        raise SystemExit(
            "--wait requires --storage-url or POLICY_REVIEW_STORAGE_URL in azd state."
        )
    try:
        output_path = _wait_for_outputs(
            storage_url=storage_url,
            intake_container=intake_container,
            report_container=report_container,
            request_id=request_id,
            report_blob=review_blob,
            timeout_minutes=args.timeout_minutes,
            poll_seconds=args.poll_seconds,
            download_report=args.download_report,
            output_dir=args.output_dir,
        )
    except TimeoutError as exc:
        raise SystemExit(str(exc)) from exc
    dashboard_url = _azd_value(
        "DURABLE_TASK_DASHBOARD_URL", args.azd_environment
    )
    if dashboard_url:
        print(f"DTS dashboard: {dashboard_url}")
    if output_path:
        print(f"Downloaded report: {output_path.resolve()}")
    print("E2E success: Dataverse row, normalized manifest, and HTML report are ready.")


if __name__ == "__main__":
    main()
