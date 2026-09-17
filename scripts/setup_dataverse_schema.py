"""Create or verify the sample Policy Service Request Dataverse schema."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCHEMA = ROOT / "dataverse" / "policy-service-request.schema.json"


def _run_pac(*args: str) -> str:
    if shutil.which("pac") is None:
        raise RuntimeError(
            "Power Platform CLI is required. Install it, then run "
            "'pac auth create --environment <environment>'."
        )
    result = subprocess.run(
        ["pac", *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _run_az(*args: str) -> str:
    if shutil.which("az") is None:
        raise RuntimeError(
            "Azure CLI is required to resolve a Dataverse environment ID or name."
        )
    result = subprocess.run(
        ["az", *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _select_environment_url(
    instances: list[dict[str, Any]],
    *,
    environment_id: str | None = None,
    environment_name: str | None = None,
) -> str:
    expected_id = environment_id.strip().casefold() if environment_id else None
    expected_name = environment_name.strip().casefold() if environment_name else None
    for instance in instances:
        actual_id = str(instance.get("EnvironmentId", "")).strip().casefold()
        actual_name = str(instance.get("FriendlyName", "")).strip().casefold()
        if expected_id and actual_id == expected_id:
            break
        if expected_name and actual_name == expected_name:
            break
    else:
        identifier = environment_id or environment_name
        raise RuntimeError(
            f"Dataverse environment '{identifier}' was not found by Global Discovery."
        )

    url = instance.get("Url")
    if not isinstance(url, str) or not url.strip():
        raise RuntimeError("Global Discovery returned an environment without a URL.")
    return url.rstrip("/")


def resolve_environment_url(
    *,
    environment_id: str | None = None,
    environment_name: str | None = None,
) -> str:
    token = _run_az(
        "account",
        "get-access-token",
        "--resource",
        "https://globaldisco.crm.dynamics.com",
        "--query",
        "accessToken",
        "-o",
        "tsv",
    )
    if not token:
        raise RuntimeError("Azure CLI returned an empty Global Discovery access token.")
    request = urllib.request.Request(
        "https://globaldisco.crm.dynamics.com/api/discovery/v2.0/Instances",
        headers={
            "Accept": "application/json",
            "Authorization": "Bearer " + token,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Dataverse Global Discovery failed with HTTP {exc.code}: {detail}"
        ) from exc
    instances = payload.get("value") if isinstance(payload, dict) else None
    if not isinstance(instances, list):
        raise RuntimeError("Global Discovery returned an unexpected response.")
    return _select_environment_url(
        [item for item in instances if isinstance(item, dict)],
        environment_id=environment_id,
        environment_name=environment_name,
    )


def _request(
    environment_url: str,
    token: str,
    method: str,
    path: str,
    *,
    body: dict[str, Any] | None = None,
    solution: str | None = None,
    allow_not_found: bool = False,
) -> dict[str, Any] | None:
    headers = {
        "Accept": "application/json",
        "Authorization": "Bearer " + token,
        "OData-MaxVersion": "4.0",
        "OData-Version": "4.0",
        "If-None-Match": "null",
    }
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json; charset=utf-8"
        headers["Prefer"] = "return=representation"
        data = json.dumps(body).encode()
    if solution:
        headers["MSCRM.SolutionUniqueName"] = solution
    request = urllib.request.Request(
        f"{environment_url.rstrip('/')}/api/data/v9.2/{path}",
        data=data,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            content = response.read()
    except urllib.error.HTTPError as exc:
        if allow_not_found and exc.code == 404:
            return None
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Dataverse {method} {path} failed with HTTP {exc.code}: {detail}"
        ) from exc
    if not content:
        return {}
    value = json.loads(content)
    if not isinstance(value, dict):
        raise RuntimeError("Dataverse returned an unexpected non-object response.")
    return value


def _label(value: str) -> dict[str, Any]:
    return {
        "@odata.type": "Microsoft.Dynamics.CRM.Label",
        "LocalizedLabels": [
            {
                "@odata.type": "Microsoft.Dynamics.CRM.LocalizedLabel",
                "Label": value,
                "LanguageCode": 1033,
            }
        ],
    }


def _attribute(column: dict[str, Any]) -> dict[str, Any]:
    value = {
        "@odata.type": "Microsoft.Dynamics.CRM.StringAttributeMetadata",
        "AttributeType": "String",
        "AttributeTypeName": {"Value": "StringType"},
        "SchemaName": column["schemaName"],
        "DisplayName": _label(column["displayName"]),
        "Description": _label(f"{column['displayName']} for the insurance review sample."),
        "RequiredLevel": {
            "Value": (
                "None"
                if column.get("required", True) is False
                else "ApplicationRequired"
            ),
            "CanBeChanged": True,
            "ManagedPropertyLogicalName": "canmodifyrequirementlevelsettings",
        },
        "FormatName": {"Value": "Text"},
        "MaxLength": column["maxLength"],
    }
    if column.get("primaryName"):
        value["IsPrimaryName"] = True
    return value


def _first(value: dict[str, Any] | None) -> dict[str, Any] | None:
    if not value:
        return None
    rows = value.get("value")
    if not isinstance(rows, list) or not rows:
        return None
    row = rows[0]
    return row if isinstance(row, dict) else None


def _find(
    environment_url: str,
    token: str,
    entity_set: str,
    unique_name: str,
    id_column: str,
) -> str | None:
    query = urllib.parse.urlencode({
        "$select": id_column,
        "$filter": f"uniquename eq '{unique_name}'",
    })
    row = _first(_request(environment_url, token, "GET", f"{entity_set}?{query}"))
    if row is None:
        return None
    value = row.get(id_column)
    if not isinstance(value, str) or not value:
        raise RuntimeError(f"Dataverse returned {entity_set} without {id_column}.")
    return value


def ensure_schema(
    environment_url: str,
    token: str,
    schema: dict[str, Any],
    *,
    verify_only: bool,
) -> None:
    publisher = schema["publisher"]
    solution = schema["solution"]
    table = schema["table"]

    publisher_id = _find(
        environment_url,
        token,
        "publishers",
        publisher["uniqueName"],
        "publisherid",
    )
    if publisher_id is None:
        if verify_only:
            raise RuntimeError("The sample Dataverse publisher is missing.")
        created = _request(
            environment_url,
            token,
            "POST",
            "publishers",
            body={
                "uniquename": publisher["uniqueName"],
                "friendlyname": publisher["friendlyName"],
                "customizationprefix": publisher["prefix"],
                "customizationoptionvalueprefix": publisher["optionValuePrefix"],
            },
        )
        publisher_id = str(created["publisherid"])

    solution_id = _find(
        environment_url,
        token,
        "solutions",
        solution["uniqueName"],
        "solutionid",
    )
    if solution_id is None:
        if verify_only:
            raise RuntimeError("The sample Dataverse solution is missing.")
        _request(
            environment_url,
            token,
            "POST",
            "solutions",
            body={
                "uniquename": solution["uniqueName"],
                "friendlyname": solution["friendlyName"],
                "version": solution["version"],
                "publisherid@odata.bind": f"/publishers({publisher_id})",
            },
        )

    table_query = urllib.parse.urlencode({
        "$select": "LogicalName,EntitySetName,OwnershipType",
        "$expand": (
            "Attributes($select=LogicalName,AttributeType,MaxLength,"
            "RequiredLevel,IsPrimaryName)"
        ),
    })
    table_path = f"EntityDefinitions(LogicalName='{table['logicalName']}')?{table_query}"
    existing = _request(
        environment_url,
        token,
        "GET",
        table_path,
        allow_not_found=True,
    )
    if existing is None:
        if verify_only:
            raise RuntimeError("The Policy Service Request table is missing.")
        _request(
            environment_url,
            token,
            "POST",
            "EntityDefinitions",
            solution=solution["uniqueName"],
            body={
                "@odata.type": "Microsoft.Dynamics.CRM.EntityMetadata",
                "SchemaName": table["schemaName"],
                "DisplayName": _label(table["displayName"]),
                "DisplayCollectionName": _label(table["displayCollectionName"]),
                "Description": _label(
                    "Created Policy Service Request rows start the insurance review sample."
                ),
                "OwnershipType": "OrganizationOwned",
                "HasActivities": False,
                "HasNotes": False,
                "IsActivity": False,
                "ChangeTrackingEnabled": True,
                "Attributes": [_attribute(column) for column in table["columns"]],
            },
        )
    else:
        if existing.get("EntitySetName") != table["entitySetName"]:
            raise RuntimeError(
                "The existing table entity-set name does not match the sample schema."
            )
        if existing.get("OwnershipType") != "OrganizationOwned":
            raise RuntimeError(
                "The existing Policy Service Request table must be organization-owned."
            )
        attributes = existing.get("Attributes")
        if not isinstance(attributes, list):
            raise RuntimeError("Dataverse did not return the table attributes.")
        actual = {
            value.get("LogicalName"): value
            for value in attributes
            if isinstance(value, dict) and isinstance(value.get("LogicalName"), str)
        }
        expected = {column["logicalName"] for column in table["columns"]}
        missing = sorted(expected - actual.keys())
        if missing:
            raise RuntimeError(
                "The existing Policy Service Request table is missing columns: "
                + ", ".join(missing)
            )
        for column in table["columns"]:
            attribute = actual[column["logicalName"]]
            required_level = attribute.get("RequiredLevel")
            required_value = (
                required_level.get("Value")
                if isinstance(required_level, dict)
                else required_level
            )
            expected_required = (
                "None"
                if column.get("required", True) is False
                else "ApplicationRequired"
            )
            if (
                attribute.get("AttributeType") != column["type"]
                or attribute.get("MaxLength") != column["maxLength"]
                or required_value != expected_required
                or bool(attribute.get("IsPrimaryName"))
                != bool(column.get("primaryName"))
            ):
                raise RuntimeError(
                    "The existing Dataverse column is incompatible with the sample "
                    f"schema: {column['logicalName']}."
                )

    if not verify_only:
        _request(
            environment_url,
            token,
            "POST",
            "PublishXml",
            body={
                "ParameterXml": (
                    "<importexportxml><entities><entity>"
                    f"{table['logicalName']}"
                    "</entity></entities></importexportxml>"
                )
            },
        )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    environment = parser.add_mutually_exclusive_group(required=True)
    environment.add_argument(
        "--environment-url",
        help="Dataverse organization URL, for example https://org.crm.dynamics.com.",
    )
    environment.add_argument(
        "--environment-id",
        help="Power Platform environment ID resolved through Dataverse Global Discovery.",
    )
    environment.add_argument(
        "--environment-name",
        help="Friendly environment name resolved through Dataverse Global Discovery.",
    )
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Fail if the publisher, solution, table, or required columns are absent.",
    )
    return parser


def main() -> None:
    args = _parser().parse_args()
    schema = json.loads(args.schema.read_text(encoding="utf-8"))
    environment_url = args.environment_url
    if environment_url is None:
        environment_url = resolve_environment_url(
            environment_id=args.environment_id,
            environment_name=args.environment_name,
        )
    _run_pac("auth", "who")
    token = _run_pac("auth", "token")
    if not token:
        raise RuntimeError("Power Platform CLI returned an empty access token.")
    ensure_schema(
        environment_url.rstrip("/"),
        token,
        schema,
        verify_only=args.verify_only,
    )
    action = "verified" if args.verify_only else "created or verified"
    print(f"Policy Service Request Dataverse schema {action}.")


if __name__ == "__main__":
    main()
