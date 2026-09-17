from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_agent_uses_manifest_blob_trigger_not_queue() -> None:
    agent = (ROOT / "src/main.agent.md").read_text()
    assert "type: blob_trigger" in agent
    assert "policy-intake/normalized/{name}.json" in agent
    assert "source: EventGrid" in agent
    assert "queue_trigger" not in agent


def test_connector_preview_bundle_and_timeout() -> None:
    host = json.loads((ROOT / "src/host.json").read_text())
    assert host["functionTimeout"] == "00:30:00"
    assert host["extensionBundle"]["id"].endswith(".Preview")
    assert host["extensionBundle"]["version"] == "[4.42.0, 5.0.0)"


def test_infrastructure_defaults_to_created_row_dataverse_trigger() -> None:
    gateway = (ROOT / "infra/app/connector-gateway.bicep").read_text()
    dataverse_trigger = (ROOT / "infra/app/trigger-config.bicep").read_text()
    outlook_trigger = (ROOT / "infra/app/outlook-trigger-config.bicep").read_text()
    main = (ROOT / "infra/main.bicep").read_text()
    storage = (ROOT / "infra/app/storage.bicep").read_text()
    rbac = (ROOT / "infra/app/rbac.bicep").read_text()
    assert "commondataservice" in gateway
    assert "GetOnNewItems_V2" in dataverse_trigger
    assert "SubscribeWebhookTrigger" not in dataverse_trigger
    assert "recurrenceInterval string = '5'" in dataverse_trigger
    assert "param enableOutlookFallback bool = false" in main
    assert "OnNewEmailV3" in outlook_trigger
    assert "requestQueue" not in storage
    assert "storageQueueDataContributorRoleId" in rbac
    assert "974c5e8b-45b9-4653-ba55-5f855dd0fb88" in rbac
    assert "resource appQueueRole" in rbac
    assert "17d1049b-9a84-46fb-8f53-869881c3d3ab" not in rbac


def test_dataverse_environment_id_is_local_configuration() -> None:
    parameters = (ROOT / "infra/main.parameters.json").read_text()
    main = (ROOT / "infra/main.bicep").read_text()
    posix = (ROOT / "infra/scripts/configure-dataverse-trigger.sh").read_text()
    powershell = (
        ROOT / "infra/scripts/configure-dataverse-trigger.ps1"
    ).read_text()
    gitignore = (ROOT / ".gitignore").read_text()
    assert "DATAVERSE_ENVIRONMENT_ID" in parameters
    assert "DATAVERSE_ENVIRONMENT_ID" in main
    assert "DATAVERSE_ENVIRONMENT_ID" in posix
    assert "DATAVERSE_ENVIRONMENT_ID" in powershell
    assert ".azure/" in gitignore


def test_outlook_fallback_is_allow_listed_and_optional() -> None:
    requirements = (ROOT / "src/requirements.txt").read_text()
    gateway = (ROOT / "infra/app/connector-gateway.bicep").read_text()
    main = (ROOT / "infra/main.bicep").read_text()
    assert "httpx" in requirements
    assert "\nmcp" in requirements
    assert "connectorName: 'office365'" in gateway
    assert "GetAttachment_V2" in gateway
    assert "if (outlookEnabled)" in gateway
    assert "ENABLE_OUTLOOK_FALLBACK" in main


def test_both_connector_functions_are_registered() -> None:
    function_app = (ROOT / "src/function_app.py").read_text()
    assert 'name="DataversePolicyIntake"' in function_app
    assert 'name="OutlookPolicyIntake"' in function_app


def test_combined_hooks_keep_dataverse_primary() -> None:
    azure_yaml = (ROOT / "azure.yaml").read_text()
    configure = (ROOT / "infra/scripts/configure-connectors.sh").read_text()
    configure_powershell = (
        ROOT / "infra/scripts/configure-connectors.ps1"
    ).read_text()
    disable = (ROOT / "infra/scripts/disable-outlook-trigger-if-needed.sh").read_text()
    eventgrid = (
        ROOT / "infra/scripts/configure-eventgrid-blob-trigger.sh"
    ).read_text()
    eventgrid_powershell = (
        ROOT / "infra/scripts/configure-eventgrid-blob-trigger.ps1"
    ).read_text()
    assert "configure-connectors.sh" in azure_yaml
    assert "preprovision:" in azure_yaml
    assert "disable-outlook-trigger-if-needed.sh" in azure_yaml
    assert configure.index("disable-outlook-trigger-if-needed.sh") < configure.index(
        "configure-eventgrid-blob-trigger.sh"
    )
    assert configure.index("configure-eventgrid-blob-trigger.sh") < configure.index(
        "configure-dataverse-trigger.sh"
    )
    assert configure.index("configure-dataverse-trigger.sh") < configure.index(
        "configure-outlook-trigger.sh"
    )
    assert (
        configure_powershell.index("configure-eventgrid-blob-trigger.ps1")
        < configure_powershell.index("configure-dataverse-trigger.ps1")
    )
    assert 'if [ "$outlook_enabled" = "true" ]' in configure
    assert "office365-policy-request-email" in disable
    assert "az resource delete" in disable
    for script in (eventgrid, eventgrid_powershell):
        assert "policy-intake-normalized-main" in script
        assert "Microsoft.Storage.BlobCreated" in script
        assert "BlobDeleted" not in script
        assert "/blobs/normalized/" in script
        assert "azurefunction" in script
        assert "/functions/main" in script
        assert "event-subscription show" in script
        assert "update" in script
        assert "create" in script


def test_eventgrid_bash_creates_filtered_azure_function_subscription() -> None:
    script = ROOT / "infra/scripts/configure-eventgrid-blob-trigger.sh"
    command = """
azd() {
    case "$3" in
        AZURE_RESOURCE_GROUP_NAME) printf 'rg-test' ;;
        AZURE_FUNCTION_NAME) printf 'func-test' ;;
        AZURE_STORAGE_ACCOUNT_NAME) printf 'sttest' ;;
        POLICY_INTAKE_CONTAINER) printf 'policy-intake' ;;
        *) return 1 ;;
    esac
}
az() {
    case "$1 $2 $3" in
        "storage account show")
            printf '/subscriptions/sub/resourceGroups/rg-test/providers/Microsoft.Storage/storageAccounts/sttest'
            ;;
        "resource show -g")
            printf '/subscriptions/sub/resourceGroups/rg-test/providers/Microsoft.Web/sites/func-test'
            ;;
        "eventgrid event-subscription show")
            return 1
            ;;
        "eventgrid event-subscription create")
            printf '%s\n' "$*" >&2
            ;;
        *)
            printf 'unexpected az command: %s\n' "$*" >&2
            return 98
            ;;
    esac
}
. "$1"
"""
    result = subprocess.run(
        ["sh", "-c", command, "sh", str(script)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "--endpoint-type azurefunction" in result.stderr
    assert (
        "--endpoint /subscriptions/sub/resourceGroups/rg-test/providers/"
        "Microsoft.Web/sites/func-test/functions/main"
    ) in result.stderr
    assert "--included-event-types Microsoft.Storage.BlobCreated" in result.stderr
    assert (
        "--subject-begins-with /blobServices/default/containers/"
        "policy-intake/blobs/normalized/"
    ) in result.stderr


def test_disable_outlook_bash_skips_missing_fresh_environment_outputs() -> None:
    script = ROOT / "infra/scripts/disable-outlook-trigger-if-needed.sh"
    command = """
azd() {
    printf '%s\n' \
        "ERROR: key not found in environment values: '$3'" \
        "Suggestion: Run azd env get-values."
    return 0
}
az() {
    printf 'az must not run for a fresh environment\n' >&2
    return 99
}
. "$1"
"""
    result = subprocess.run(
        ["sh", "-c", command, "sh", str(script)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "az must not run" not in result.stderr


def test_disable_outlook_powershell_skips_missing_fresh_environment_outputs() -> None:
    if shutil.which("pwsh") is None:
        pytest.skip("PowerShell is not installed.")
    script = ROOT / "infra/scripts/disable-outlook-trigger-if-needed.ps1"
    command = """
function global:azd {
    @(
        "ERROR: key not found in environment values: '$($args[2])'",
        "Suggestion: Run azd env get-values."
    )
}
function global:az {
    throw "az must not run for a fresh environment"
}
& $args[0]
"""
    result = subprocess.run(
        ["pwsh", "-NoProfile", "-Command", command, str(script)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "az must not run" not in result.stderr
