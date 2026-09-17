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
bypasses Dataverse polling without creating another workflow design.
