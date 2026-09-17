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
