from __future__ import annotations

import json
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


def test_pac_access_token_rejects_malformed_output() -> None:
    with pytest.raises(RuntimeError, match="exactly one JWT"):
        setup_dataverse_schema._extract_pac_access_token(
            "Microsoft Power Platform CLI\nAuthentication succeeded.\n"
        )


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
        return {
            "EntitySetName": "ipr_policyservicerequests",
            "OwnershipType": "OrganizationOwned",
            "Attributes": [
                {
                    "LogicalName": column["logicalName"],
                    "AttributeType": "Integer",
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
