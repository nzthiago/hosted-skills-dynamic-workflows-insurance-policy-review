# Customize

## Change the Dataverse contract

Update the canonical logical names in
[`dataverse/policy-service-request.schema.json`](../dataverse/policy-service-request.schema.json)
and [src/dataverse_intake.py](../src/dataverse_intake.py) together. Add tests before
changing a required column or status value.

Keep the row deterministic and structured. Do not ask the model to infer request fields
from free-form notes.

## Change the Outlook fallback contract

Outlook is an opt-in alternate path. Keep its subject and attachment conventions aligned
across `src/outlook_intake.py`, `infra/app/outlook-trigger-config.bicep`, and the README.
Keep connector operations allow-listed; the current fallback exposes only
`GetAttachment_V2`.

## Use file columns later

The current workflow evaluates metadata only. If binary inspection becomes a real
requirement, retrieve file-column content explicitly and stage it before workflow
execution. Treat that as a separate security and retention design; do not imply that
Dataverse row retrieval includes file bytes.

The Outlook fallback already demonstrates explicit attachment retrieval, but adding
Dataverse file-column retrieval remains a separate capability and security decision.

## Change the workflow

The plan is in [src/main.agent.md](../src/main.agent.md). Preserve:

- load → validate → parallel inspect → build → publish ordering
- JSON-serializable workflow activity results
- idempotent side effects
- `review_status: human_review_required`
- `decision: null`

## Use another trigger

`GetOnNewItems_V2` is the only Dataverse trigger proven by the supplied Connector
Namespace sample. It is Admin Only, deprecated, and created-row only. Do not claim
update/delete support. Replace it with `SubscribeWebhookTrigger` only after a deployed
capability test proves trigger-config creation and callback behavior.
