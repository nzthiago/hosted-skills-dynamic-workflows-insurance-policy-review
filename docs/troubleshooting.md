# Troubleshooting

## Schema setup fails

Confirm the authenticated Azure CLI account can create publishers, solutions, tables, and
columns. Run a non-mutating check:

```bash
python scripts/setup_dataverse_schema.py \
  --environment-id "<complete environment ID>" \
  --auth-source azure-cli \
  --verify-only
```

```powershell
python scripts/setup_dataverse_schema.py `
  --environment-id "<complete environment ID>" `
  --auth-source azure-cli `
  --verify-only
```

If PAC authentication is permitted, use `--auth-source pac` and confirm `pac auth who`
targets the intended environment. Corporate Conditional Access policies can block PAC
device-code authentication; use the Azure CLI path in that case.

The script reports missing or incompatible schema components and never logs access
tokens from either authentication source.

## A normalized manifest does not start the workflow

Flex Consumption requires Event Grid delivery for Blob triggers. Re-run `azd deploy api`
so the postdeploy hook recreates and verifies `policy-intake-main`. The subscription
must use the Blob extension webhook for `Host.Functions.main`, include only
`Microsoft.Storage.BlobCreated`, and use the subject prefix
`/blobServices/default/containers/policy-intake/blobs/normalized/`.

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

Run the monitored test command to distinguish connector polling from downstream
processing:

```bash
uv run --with-requirements requirements.txt \
  python scripts/create_dataverse_request.py \
  --azd-environment "<azd environment>" \
  --wait
```

```powershell
uv run --with-requirements requirements.txt `
  python scripts/create_dataverse_request.py `
  --azd-environment "<azd environment>" `
  --wait
```

- If no normalized manifest appears within 15 minutes, inspect connector authorization,
  `GetOnNewItems_V2`, table permissions, and the five-minute polling schedule.
- If the manifest appears but no HTML report does, inspect the `policy-intake-main`
  Event Grid subscription, `Functions.main` telemetry, and the DTS dashboard.
- Event Grid metrics alone are not a sufficient success gate. The authoritative signals
  are the normalized Blob, `Functions.main` execution, DTS completion, and HTML Blob.

## A row is rejected

All required columns must contain strings. Status fields accept only `received`,
`missing`, or `expired`. Request ID and Policy ID may contain letters, numbers, dot,
underscore, and dash.

Check Application Insights for `Policy Service Request row rejected` without logging
sensitive row contents.

## A duplicate row produces no workflow

This is expected when its Request ID already has a normalized manifest. Connector
retries race on a Blob lease and cannot create another manifest.

`scripts/create_dataverse_request.py` also refuses to create a row when its Request ID
already exists. Omit `--request-id` to generate a unique ID for every run.

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
azd env get-value DURABLE_TASK_DASHBOARD_URL -e "<azd environment>"
```

## Live connector testing is blocked

Use manual invocation regardless of which connector mode is provisioned:

```bash
python scripts/demo.py submit-manual --request examples/policy-service-request.json
```

It creates the same metadata-only normalized manifest without Dataverse or Outlook.
