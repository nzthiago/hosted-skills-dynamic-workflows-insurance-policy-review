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


def test_infrastructure_has_read_only_attachment_operation() -> None:
    gateway = (ROOT / "infra/app/connector-gateway.bicep").read_text()
    trigger = (ROOT / "infra/app/trigger-config.bicep").read_text()
    storage = (ROOT / "infra/app/storage.bicep").read_text()
    rbac = (ROOT / "infra/app/rbac.bicep").read_text()
    assert "GetAttachment_V2" in gateway
    assert "SendEmail" not in gateway
    assert "OnNewEmailV3" in trigger
    assert "includeAttachments" in trigger
    assert "requestQueue" not in storage
    assert "storageQueueDataContributorRoleId" not in rbac
