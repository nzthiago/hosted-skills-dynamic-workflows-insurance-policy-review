from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from scripts import setup_dataverse_schema

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "dataverse" / "policy-service-request.schema.json"


def test_schema_matches_intake_contract() -> None:
    schema = json.loads(SCHEMA_PATH.read_text())
    table = schema["table"]
    assert table["entitySetName"] == "ipr_policyservicerequests"
    assert [column["logicalName"] for column in table["columns"]] == [
        "ipr_requestid",
        "ipr_policyid",
        "ipr_drivername",
        "ipr_driverlicencefilename",
        "ipr_driverlicencestatus",
        "ipr_signedrequestfilename",
        "ipr_signedrequeststatus",
        "ipr_reviewblobname",
    ]
    assert {column["type"] for column in table["columns"]} == {"String"}


def test_optional_review_blob_is_not_required() -> None:
    schema = json.loads(SCHEMA_PATH.read_text())
    review_blob = schema["table"]["columns"][-1]
    attribute = setup_dataverse_schema._attribute(review_blob)
    assert attribute["RequiredLevel"]["Value"] == "None"


def test_primary_name_matches_dataverse_platform_metadata() -> None:
    schema = json.loads(SCHEMA_PATH.read_text())
    request_id = schema["table"]["columns"][0]
    attribute = setup_dataverse_schema._attribute(request_id)

    assert request_id["logicalName"] == "ipr_requestid"
    assert request_id["maxLength"] == 850
    assert request_id["required"] is False
    assert request_id["primaryName"] is True
    assert attribute["MaxLength"] == 850
    assert attribute["RequiredLevel"]["Value"] == "None"
    assert attribute["IsPrimaryName"] is True


def test_environment_id_resolves_organization_url() -> None:
    instances = [
        {
            "EnvironmentId": "environment-123",
            "FriendlyName": "Insurance Demo",
            "Url": "https://insurance.crm.dynamics.com/",
        }
    ]
    assert setup_dataverse_schema._select_environment_url(
        instances,
        environment_id="ENVIRONMENT-123",
    ) == "https://insurance.crm.dynamics.com"


def test_environment_id_takes_precedence_over_friendly_name() -> None:
    instances = [
        {
            "EnvironmentId": "environment-primary",
            "FriendlyName": "Other",
            "Url": "https://primary.crm.dynamics.com",
        },
        {
            "EnvironmentId": "environment-other",
            "FriendlyName": "Insurance Demo",
            "Url": "https://friendly.crm.dynamics.com",
        },
    ]
    assert setup_dataverse_schema._select_environment_url(
        instances,
        environment_id="environment-primary",
        environment_name="Insurance Demo",
    ) == "https://primary.crm.dynamics.com"


def test_environment_resolution_rejects_unknown_id() -> None:
    with pytest.raises(RuntimeError, match="not found"):
        setup_dataverse_schema._select_environment_url(
            [],
            environment_id="environment-missing",
        )


def test_pac_access_token_ignores_banner_output() -> None:
    token = "eyJheader.payload_signature.token-signature"
    output = (
        "Microsoft Power Platform CLI\n"
        "Version: 2.12.2\n"
        "Authenticated as insurance-policy-e2e-mi\u202fto Dataverse\n"
        "\n"
        f"{token}\n"
        "Telemetry collection is enabled.\n"
    )

    assert setup_dataverse_schema._extract_pac_access_token(output) == token


def test_pac_access_token_accepts_pac_2_12_token_prefix() -> None:
    token = "eyJheader.payload_signature.token-signature"
    output = (
        "Connected to insurance-policy-e2e-mi\n"
        "Resource: https://example.crm.dynamics.com\n"
        "Expires On: 2026-09-17 22:00:00Z\n"
        "Expires In: 00:59:59\n"
        f"Token: {token}\n"
    )

    assert setup_dataverse_schema._extract_pac_access_token(output) == token


def test_pac_access_token_rejects_malformed_output() -> None:
    with pytest.raises(RuntimeError, match="exactly one JWT"):
        setup_dataverse_schema._extract_pac_access_token(
            "Microsoft Power Platform CLI\nAuthentication succeeded.\n"
        )


def test_azure_cli_auth_requests_dataverse_resource(monkeypatch) -> None:
    token = "eyJheader.payload_signature.token-signature"
    calls = []

    def fake_run_az(*args):
        calls.append(args)
        return token

    monkeypatch.setattr(setup_dataverse_schema, "_run_az", fake_run_az)

    assert setup_dataverse_schema._acquire_dataverse_access_token(
        "https://example.crm.dynamics.com/",
        "azure-cli",
    ) == token
    assert calls == [
        (
            "account",
            "get-access-token",
            "--resource",
            "https://example.crm.dynamics.com",
            "--query",
            "accessToken",
            "-o",
            "tsv",
        )
    ]


def test_azure_cli_auth_rejects_malformed_token_output(monkeypatch) -> None:
    monkeypatch.setattr(
        setup_dataverse_schema,
        "_run_az",
        lambda *args: "WARNING: authentication output was unavailable",
    )

    with pytest.raises(
        RuntimeError,
        match=r"Azure CLI did not return exactly one JWT access token\.",
    ):
        setup_dataverse_schema._acquire_dataverse_access_token(
            "https://example.crm.dynamics.com",
            "azure-cli",
        )


def test_auto_auth_falls_back_to_azure_cli(monkeypatch, capsys) -> None:
    token = "eyJheader.payload_signature.token-signature"

    def failing_pac(*args):
        raise subprocess.CalledProcessError(1, ["pac", *args])

    monkeypatch.setattr(setup_dataverse_schema, "_run_pac", failing_pac)
    monkeypatch.setattr(setup_dataverse_schema, "_run_az", lambda *args: token)

    assert setup_dataverse_schema._acquire_dataverse_access_token(
        "https://example.crm.dynamics.com",
        "auto",
    ) == token
    assert "using Azure CLI authentication" in capsys.readouterr().err


def test_explicit_pac_auth_remains_supported(monkeypatch) -> None:
    token = "eyJheader.payload_signature.token-signature"
    calls = []

    def fake_run_pac(*args):
        calls.append(args)
        return token if args == ("auth", "token") else "Connected"

    monkeypatch.setattr(setup_dataverse_schema, "_run_pac", fake_run_pac)
    monkeypatch.setattr(
        setup_dataverse_schema,
        "_run_az",
        lambda *args: pytest.fail("Azure CLI fallback must not run"),
    )

    assert setup_dataverse_schema._acquire_dataverse_access_token(
        "https://example.crm.dynamics.com",
        "pac",
    ) == token
    assert calls == [("auth", "who"), ("auth", "token")]


def test_dataverse_request_uses_bearer_token(monkeypatch) -> None:
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def read(self) -> bytes:
            return b"{}"

    def fake_urlopen(request, *, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(setup_dataverse_schema.urllib.request, "urlopen", fake_urlopen)

    assert setup_dataverse_schema._request(
        "https://example.crm.dynamics.com",
        "pac-access-token",
        "GET",
        "WhoAmI",
    ) == {}
    assert captured["request"].get_header("Authorization") == (
        "Bearer pac-access-token"
    )
    assert captured["timeout"] == 60


def test_verify_only_fails_when_publisher_is_missing(monkeypatch) -> None:
    schema = json.loads(SCHEMA_PATH.read_text())
    monkeypatch.setattr(setup_dataverse_schema, "_find", lambda *args: None)
    with pytest.raises(RuntimeError, match="publisher is missing"):
        setup_dataverse_schema.ensure_schema(
            "https://example.crm.dynamics.com",
            "token",
            schema,
            verify_only=True,
        )


def test_verify_rejects_incompatible_existing_column(monkeypatch) -> None:
    schema = json.loads(SCHEMA_PATH.read_text())
    monkeypatch.setattr(
        setup_dataverse_schema,
        "_find",
        lambda *args: "00000000-0000-0000-0000-000000000001",
    )

    def fake_request(*args, **kwargs):
        path = args[3]
        if "/Attributes/" not in path:
            return {
                "EntitySetName": "ipr_policyservicerequests",
                "OwnershipType": "OrganizationOwned",
            }
        return {
            "value": [
                {
                    "LogicalName": column["logicalName"],
                    "AttributeType": "String",
                    "MaxLength": column["maxLength"] + 1,
                    "RequiredLevel": {
                        "Value": (
                            "None"
                            if column.get("required", True) is False
                            else "ApplicationRequired"
                        )
                    },
                    "IsPrimaryName": bool(column.get("primaryName")),
                }
                for column in schema["table"]["columns"]
            ],
        }

    monkeypatch.setattr(setup_dataverse_schema, "_request", fake_request)
    with pytest.raises(RuntimeError, match="incompatible"):
        setup_dataverse_schema.ensure_schema(
            "https://example.crm.dynamics.com",
            "token",
            schema,
            verify_only=True,
        )


def test_verify_reads_string_attributes_from_typed_metadata_path(
    monkeypatch,
) -> None:
    schema = json.loads(SCHEMA_PATH.read_text())
    monkeypatch.setattr(
        setup_dataverse_schema,
        "_find",
        lambda *args: "00000000-0000-0000-0000-000000000001",
    )
    paths = []

    def fake_request(*args, **kwargs):
        path = args[3]
        paths.append(path)
        if "/Attributes/" not in path:
            return {
                "EntitySetName": "ipr_policyservicerequests",
                "OwnershipType": "OrganizationOwned",
            }
        return {
            "value": [
                {
                    "LogicalName": column["logicalName"],
                    "AttributeType": column["type"],
                    "MaxLength": column["maxLength"],
                    "RequiredLevel": {
                        "Value": (
                            "None"
                            if column.get("required", True) is False
                            else "ApplicationRequired"
                        )
                    },
                    "IsPrimaryName": bool(column.get("primaryName")),
                }
                for column in schema["table"]["columns"]
            ]
        }

    monkeypatch.setattr(setup_dataverse_schema, "_request", fake_request)
    setup_dataverse_schema.ensure_schema(
        "https://example.crm.dynamics.com",
        "token",
        schema,
        verify_only=True,
    )

    assert any(
        "/Attributes/Microsoft.Dynamics.CRM.StringAttributeMetadata?"
        in path
        for path in paths
    )
