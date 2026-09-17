# How it works

## Intake

The Connector Namespace uses the Common Data Service connector operation
`GetOnNewItems_V2`. It polls the configured Dataverse entity set every five minutes and
invokes `DataversePolicyIntake` only for created rows.

[src/dataverse_intake.py](../src/dataverse_intake.py):

1. Parses the Connector Extension `body.value` batch.
2. Validates the eight structured Policy Service Request fields.
3. Maps driver-licence and signed-request fields into the existing `documents[]` schema.
4. Uses the Dataverse row ID and Request ID as the idempotency identity.
5. Creates one deterministic `normalized/<request-id>.json` manifest.

No connector action, file column, attachment lookup, or binary download occurs. Row
values are untrusted data and never agent instructions.

A Blob lease serializes concurrent deliveries. The manifest uses `overwrite=False`, so
connector retries or another row with the same Request ID cannot emit another workflow
trigger.

## Optional Outlook intake

When `ENABLE_OUTLOOK_FALLBACK=true`, `OnNewEmailV3` invokes `OutlookPolicyIntake`.
[src/outlook_intake.py](../src/outlook_intake.py):

1. Validates the `[POLICY-REQUEST]` subject contract and attachment naming convention.
2. Discards inline attachment bodies and calls only allow-listed `GetAttachment_V2`.
3. Validates file type and size, then stages each attachment in Blob Storage.
4. Uses Outlook message ID plus Request ID for source idempotency.
5. Creates the same deterministic `normalized/<request-id>.json` manifest.

The manifest name is shared with Dataverse and manual invocation. The first accepted
source wins; retries or alternate-source delivery with the same Request ID do not start
another workflow.

## Hosted skill and Dynamic Workflow

The normalized manifest Blob triggers [src/main.agent.md](../src/main.agent.md). The first
workflow tool loads the manifest, then the workflow runs:

1. `load_normalized_policy_request`
2. `validate_add_driver_request`
3. `inspect_driver_document` for every metadata record in parallel
4. `build_driver_review_report`
5. `publish_driver_review_report`

The publisher uses a stable report name and `overwrite=True`, making report retries
idempotent.

## Human decision boundary

The generated result always contains:

```json
{
  "review_status": "human_review_required",
  "decision": null
}
```

The sample does not authenticate documents, interpret coverage, write back to Dataverse,
or authorize policy changes.

## Manual fallback

`scripts/demo.py submit-manual` writes the same metadata-only normalized manifest. It
bypasses both connectors without creating another workflow design.
