# Troubleshooting

## Schema setup fails

Confirm `pac auth who` targets the intended environment and that the account can create
publishers, solutions, tables, and columns. Run a non-mutating check:

```bash
python scripts/setup_dataverse_schema.py \
  --environment-id "<complete environment ID>" \
  --verify-only
```

The script reports missing or incompatible schema components and never logs the PAC
access token.

If environment resolution fails, confirm Azure CLI is signed in and that Global
Discovery returns the ID. Use `--environment-url` only when the organization URL is
already known.

## The Dataverse connection is not authorized

Run `azd provision` again to reopen the interactive Connector Namespace authorization
hook. The connection must show `Connected`.

## A created row does not trigger intake

Confirm:

- the trigger config uses exactly `GetOnNewItems_V2`
- `DATAVERSE_ENVIRONMENT_ID` resolves to the intended organization URL
- `DATAVERSE_TABLE_NAME` is the plural entity-set name
- the authorized account has Global Read on the table
- the row was created after trigger configuration
- at least one five-minute polling interval has elapsed
- the Connector Extension preview bundle loaded

This sample does not support update or delete events. Editing an existing row cannot
start a workflow.

## A row is rejected

All required columns must contain strings. Status fields accept only `received`,
`missing`, or `expired`. Request ID and Policy ID may contain letters, numbers, dot,
underscore, and dash.

Check Application Insights for `Policy Service Request row rejected` without logging
sensitive row contents.

## A duplicate row produces no workflow

This is expected when its Request ID already has a normalized manifest. Connector
retries race on a Blob lease and cannot create another manifest.

## Outlook fallback is not provisioned

Outlook is intentionally disabled by default. Enable it and reprovision:

```bash
azd env set ENABLE_OUTLOOK_FALLBACK true
azd up
```

Authorize the Office 365 connection in the Connector Namespace portal. Confirm the
dedicated folder exists and `OUTLOOK_FOLDER_PATH` uses the connector-recognized path.

## An Outlook message is rejected

Confirm the subject is exactly:

```text
[POLICY-REQUEST] <request-id> | <policy-id> | <driver-name>
```

Non-inline attachments must be named
`<driver_license|signed_request>__<document-id>__<file-name>`, use PDF/JPEG/PNG, and be
10 MiB or smaller. The trigger must include attachment IDs; inline `contentBytes` are
discarded and `GetAttachment_V2` retrieves each attachment explicitly.

## The workflow does not start

Check the `policy-intake/normalized/` prefix and open:

```bash
azd env get-value DURABLE_TASK_DASHBOARD_URL
```

## Live connector testing is blocked

Use manual invocation regardless of which connector mode is provisioned:

```bash
python scripts/demo.py submit-manual --request examples/policy-service-request.json
```

It creates the same metadata-only normalized manifest without Dataverse or Outlook.
