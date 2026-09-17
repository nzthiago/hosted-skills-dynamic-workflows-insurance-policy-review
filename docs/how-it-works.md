# How it works

## Intake

`OnNewEmailV3` watches the configured Office 365 Outlook folder and invokes
`OutlookPolicyIntake` in [src/function_app.py](../src/function_app.py).

[src/outlook_intake.py](../src/outlook_intake.py):

1. Parses the Connector Extension callback envelope.
2. Enforces the subject and attachment-name contracts.
3. Ignores inline attachments and trigger-provided attachment bodies.
4. Calls the allow-listed Connector MCP `GetAttachment_V2` operation by message ID and
   attachment ID.
5. Validates MIME type/size, decodes Base64, computes SHA-256, and uploads each binary.
6. Creates one deterministic `normalized/<request-id>.json` manifest.

A Blob lease serializes concurrent deliveries. The final manifest is created with
`overwrite=False`, so connector retries and resends with the same request ID do not emit
another manifest.

## Hosted skill and Dynamic Workflow

The normalized manifest Blob triggers [src/main.agent.md](../src/main.agent.md). Because
the runtime's Blob trigger serialization exposes Blob metadata rather than file contents,
the first workflow tool loads the manifest.

The workflow then:

1. `load_normalized_policy_request`
2. `validate_add_driver_request`
3. `inspect_driver_document` for every staged document, in parallel
4. `build_driver_review_report`
5. `publish_driver_review_report`

The activities are synchronous, JSON-serializable `@workflow_tool` functions in
[src/tools/policy_review_tools.py](../src/tools/policy_review_tools.py). The publisher
uses a stable report name and `overwrite=True`, making report retries idempotent.

## Human decision boundary

The generated result always contains:

```json
{
  "review_status": "human_review_required",
  "decision": null
}
```

The sample stages files but inspects metadata only. It does not validate authenticity,
interpret policy coverage, or authorize a policy change.

## Manual fallback

`scripts/demo.py submit-manual` stages local or OneDrive-synced files and writes the same
normalized manifest. This bypasses Outlook without creating a second workflow design.
