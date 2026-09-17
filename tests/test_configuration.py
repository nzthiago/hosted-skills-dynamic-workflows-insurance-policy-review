from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_agent_uses_manifest_blob_trigger_not_queue() -> None:
    agent = (ROOT / "src/main.agent.md").read_text()
    assert "type: blob_trigger" in agent
    assert "policy-intake/normalized/{name}.json" in agent
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
    assert "storageQueueDataContributorRoleId" not in rbac


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
    disable = (ROOT / "infra/scripts/disable-outlook-trigger-if-needed.sh").read_text()
    assert "configure-connectors.sh" in azure_yaml
    assert "preprovision:" in azure_yaml
    assert "disable-outlook-trigger-if-needed.sh" in azure_yaml
    assert configure.index("disable-outlook-trigger-if-needed.sh") < configure.index(
        "configure-dataverse-trigger.sh"
    )
    assert configure.index("configure-dataverse-trigger.sh") < configure.index(
        "configure-outlook-trigger.sh"
    )
    assert 'if [ "$outlook_enabled" = "true" ]' in configure
    assert "office365-policy-request-email" in disable
    assert "az resource delete" in disable
