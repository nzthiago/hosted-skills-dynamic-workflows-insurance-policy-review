# Insurance Policy Review with Dynamic Workflows

[![Python](https://img.shields.io/badge/Python-3.13-blue.svg)](https://www.python.org/downloads/)

A markdown-first [Azure Functions hosted skill](https://azure.github.io/azure-functions-agents-runtime/)
that turns created Microsoft Dataverse policy-service-request rows into durable,
human-reviewed document packets. An optional Office 365 Outlook mode preserves
attachment-based intake as a faster fallback.

## What it does

- Polls a Dataverse `Policy Service Request` table through a Connector Namespace trigger.
- Normalizes structured row fields into the sample's existing `documents[]` metadata contract.
- Optionally accepts convention-based Outlook messages and explicitly retrieves attachments.
- Creates one deterministic normalized request manifest in Blob Storage.
- Runs validate → parallel inspect → build → publish as a Dynamic Workflow.
- Produces an HTML report while keeping every policy decision human-owned.

The primary Dataverse path reviews metadata only. The optional Outlook path stages
attachments for reference, but the workflow still does not inspect binary contents,
verify document authenticity, update Dataverse rows, or update an insurance policy.

## Dataverse row contract

Create one row only after all request metadata is ready:

| Display name | Logical name | Required | Example |
| --- | --- | --- | --- |
| Request ID | `ipr_requestid` | Yes | `PSR-2026-00042` |
| Policy ID | `ipr_policyid` | Yes | `AUTO-100042` |
| Driver name | `ipr_drivername` | Yes | `Jordan Lee` |
| Driver licence filename | `ipr_driverlicencefilename` | Yes | `jordan-lee-license.pdf` |
| Driver licence status | `ipr_driverlicencestatus` | Yes | `received` |
| Signed request filename | `ipr_signedrequestfilename` | Yes | `signed-request.pdf` |
| Signed request status | `ipr_signedrequeststatus` | Yes | `missing` |
| Review blob name | `ipr_reviewblobname` | No | `PSR-2026-00042.html` |

Statuses must be `received`, `missing`, or `expired`. Filenames are metadata labels;
the sample does not download the referenced files. The Dataverse row ID is used with
Request ID to build the idempotency key.

Dataverse stores the Request ID as the table's primary-name column, whose platform
metadata uses a maximum length of 850 and does not enforce requiredness. The intake
application still requires and validates a non-empty Request ID before starting a review.

## Prerequisites

- Existing Dataverse/Power Platform environment
- Account with permission to customize the environment
- Connector authorization account with Global Read on the sample table
- Azure subscription, Azure Developer CLI, Azure CLI, Python 3.13, and
  [uv](https://docs.astral.sh/uv/)
- Optional: [Power Platform CLI](https://learn.microsoft.com/power-platform/developer/cli/introduction)
  when PAC authentication is permitted by tenant policy

Every command in this README works from Windows Terminal with PowerShell 7+ (`pwsh`),
macOS/Linux Bash, or zsh. Commands that need a different line-continuation character or
quoting on Windows show a PowerShell block immediately after the Bash block. Install
Azure CLI, `azd`, Python 3.13, and `uv` for Windows from their standard installers (MSI
or `winget`); no WSL is required. Interactive steps — `az login`, `azd auth login`, and
the connector `postprovision` authorization hook — open your default browser the same way
on Windows as on macOS/Linux.

## Create or verify the table

Select the target environment and authenticate with Azure CLI. The environment ID is the
stable input shown in the Power Apps environment URL:

```bash
az login --tenant "<tenant ID>"
python scripts/setup_dataverse_schema.py \
  --environment-id "<complete environment ID>" \
  --auth-source azure-cli
```

```powershell
az login --tenant "<tenant ID>"
python scripts/setup_dataverse_schema.py `
  --environment-id "<complete environment ID>" `
  --auth-source azure-cli
```

Copy the complete environment ID without removing prefixes such as `Default-`.
Azure CLI must be signed in to the tenant that contains the environment so Global
Discovery can resolve it.

For environments where PAC authentication is allowed, authenticate with
`pac auth create --environment "<environment ID or URL>"` and pass
`--auth-source pac`. The default `--auth-source auto` tries PAC first and falls back to
the current Azure CLI login.

The script uses
[`dataverse/policy-service-request.schema.json`](dataverse/policy-service-request.schema.json)
to create or verify a dedicated publisher, unmanaged solution, organization-owned table,
and the eight structured fields. For ID or friendly-name input it uses Dataverse Global
Discovery to resolve the organization URL. It never creates file columns or stores
credentials. Re-run with `--verify-only` for a non-mutating preflight.

If neither CLI authentication path is available, create the same table in an unmanaged
solution at [Power Apps](https://make.preview.powerapps.com/environments), using the
logical names from the schema file.

## Deploy and authorize

```bash
azd auth login
az login --tenant "<tenant ID>"
azd env set DATAVERSE_ENVIRONMENT_ID "<complete environment ID>"
azd env set DATAVERSE_TABLE_NAME "ipr_policyservicerequests"
azd up
```

You can set `DATAVERSE_ENVIRONMENT_URL` directly or use
`DATAVERSE_ENVIRONMENT_NAME` as a final fallback. Resolution precedence is URL, ID,
then friendly name. Values set with `azd env set` remain under the ignored `.azure/`
directory and are not committed to the sample. The
`postprovision` hook opens the Connector Namespace portal for interactive OAuth
authorization. The authorized identity must have Global Read on the table because
`GetOnNewItems_V2` is an Admin Only trigger.

After application deployment, `postdeploy` creates only the proven
`GetOnNewItems_V2` created-row trigger. It uses a five-minute polling interval and does
not claim update or delete support. The broader `SubscribeWebhookTrigger` is intentionally
not configured because Connector Namespace trigger creation is not currently proven.
The same hook creates or updates an Event Grid subscription that forwards only
`BlobCreated` events under `policy-intake/normalized/` to the Blob extension webhook for
the `main` Function. Flex Consumption requires this Event Grid source for Blob triggers.
The callback contains the `blobs_extension` system key and is never printed.

## Optional Outlook fallback

Enable the alternate attachment-based path before provisioning:

```bash
azd env set ENABLE_OUTLOOK_FALLBACK true
azd env set OUTLOOK_FOLDER_PATH "Inbox/Policy Review"
azd up
```

The Connector Namespace then provisions an Office 365 Outlook connection, a read-only
`GetAttachment_V2` MCP surface, and an `OnNewEmailV3` trigger in addition to Dataverse.
Authorization remains interactive. Use a dedicated mailbox folder and send messages with:

```text
Subject: [POLICY-REQUEST] <request-id> | <policy-id> | <driver-name>
Attachment: driver_license__<document-id>__<file-name>
Attachment: signed_request__<document-id>__<file-name>
```

The Outlook intake ignores inline attachment bodies, retrieves each attachment explicitly,
accepts PDF/JPEG/PNG files up to 10 MiB, and stages them under the intake container. Both
connector paths use the same deterministic request manifest, so whichever path accepts a
Request ID first prevents the other path from starting a duplicate workflow.

## Run the demo

1. Complete schema setup, deployment, connector authorization, and trigger configuration
   before the presentation.
2. Create a row with a unique Request ID and wait for the normalized manifest and HTML
   report:

   ```bash
   uv run --with-requirements requirements.txt \
     python scripts/create_dataverse_request.py \
     --azd-environment "<azd environment>" \
     --wait \
     --download-report
   ```

   ```powershell
   uv run --with-requirements requirements.txt `
     python scripts/create_dataverse_request.py `
     --azd-environment "<azd environment>" `
     --wait `
     --download-report
   ```

   The corporate Conditional Access-friendly default reuses the current Azure CLI login
   for Dataverse and Blob Storage. It never prints access tokens. Environment URL/ID,
   table name, storage URL, and container names are read from ignored azd state. Supply
   `--environment-url`, `--environment-id`, or storage arguments explicitly when not
   using azd state.
3. Allow at least one five-minute connector polling interval. The command uses a
   15-minute default timeout and reports these stages separately:
   Dataverse row created → normalized manifest ready → HTML report ready.
4. Open the Durable Task Scheduler dashboard printed by the command, or retrieve it:

   ```bash
   azd env get-value DURABLE_TASK_DASHBOARD_URL -e "<azd environment>"
   ```

5. With `--download-report`, the generated report is saved to
   `output/<request-id>.html`. To download it later:

   ```bash
   export POLICY_REVIEW_STORAGE_URL="$(azd env get-value POLICY_REVIEW_STORAGE_URL -e "<azd environment>")"
   export POLICY_REVIEW_CONTAINER="$(azd env get-value POLICY_REVIEW_CONTAINER -e "<azd environment>")"
   uv run --with-requirements requirements.txt python scripts/demo.py download \
     --blob "reviews/<request-id>.html" \
     --output "output/<request-id>.html"
   ```

   ```powershell
   $env:POLICY_REVIEW_STORAGE_URL = azd env get-value POLICY_REVIEW_STORAGE_URL -e "<azd environment>"
   $env:POLICY_REVIEW_CONTAINER = azd env get-value POLICY_REVIEW_CONTAINER -e "<azd environment>"
   uv run --with-requirements requirements.txt python scripts/demo.py download `
     --blob "reviews/<request-id>.html" `
     --output "output/<request-id>.html"
   ```

Omit `--request-id` to generate a unique value for every run. To control the scenario,
set `--policy-id`, `--driver-name`, `--driver-licence-status`, and
`--signed-request-status`. The script checks for an existing Request ID before POSTing
and never updates or overwrites a Dataverse row.

## Manual fallback

If both connector paths are unavailable or Outlook fallback was not provisioned, submit
the same normalized metadata contract directly:

```bash
export POLICY_REVIEW_STORAGE_URL="$(azd env get-value POLICY_REVIEW_STORAGE_URL)"
export POLICY_INTAKE_CONTAINER="$(azd env get-value POLICY_INTAKE_CONTAINER)"
uv run --with-requirements requirements.txt \
  python scripts/demo.py submit-manual \
  --request examples/policy-service-request.json
```

```powershell
$env:POLICY_REVIEW_STORAGE_URL = azd env get-value POLICY_REVIEW_STORAGE_URL
$env:POLICY_INTAKE_CONTAINER = azd env get-value POLICY_INTAKE_CONTAINER
uv run --with-requirements requirements.txt `
  python scripts/demo.py submit-manual `
  --request examples/policy-service-request.json
```

Reusing a Request ID is rejected so connector retries and manual fallback cannot start
duplicate workflows.

## Local development

Copy the settings template, populate Foundry values, then start Azurite, the Durable Task
Scheduler emulator, and Functions:

```bash
cp src/local.settings.template.json src/local.settings.json
az login
azurite --silent --skipApiVersionCheck --location .azurite
docker run --rm --name dts-emulator \
  -e DTS_TASK_HUB_NAMES=policyreviews \
  -p 8080:8080 -p 8082:8082 \
  mcr.microsoft.com/dts/dts-emulator:latest
cd src && uv run --with-requirements requirements.txt func start
```

```powershell
Copy-Item src/local.settings.template.json src/local.settings.json
az login
azurite --silent --skipApiVersionCheck --location .azurite
docker run --rm --name dts-emulator `
  -e DTS_TASK_HUB_NAMES=policyreviews `
  -p 8080:8080 -p 8082:8082 `
  mcr.microsoft.com/dts/dts-emulator:latest
cd src
uv run --with-requirements requirements.txt func start
```

Run each emulator/tool in its own terminal tab. On Windows, Docker Desktop must be
running (any backend) before the `docker run` command; no direct WSL interaction is
required.

Connector callbacks require a deployed Function App. Test the local workflow with the
manual fallback.

## Live-demo reliability

- Import/verify the table and grant Global Read before the session.
- Authorize the Dataverse connection and create the trigger before inserting the demo row.
- Use a unique Request ID for each rehearsal and live run.
- Budget at least five minutes for polling; do not edit an existing row and expect a run.
- Use `scripts/create_dataverse_request.py --wait` so the demo shows each proven boundary.
- If enabled, pre-authorize Outlook and keep one correctly named attachment message ready.
- Keep `examples/policy-service-request.json` ready for immediate manual fallback.
- Confirm the Durable Task Scheduler dashboard and report download before presenting.

For a full stage runbook — exact minute marks, click-by-click Demo 2 sequence, WOW
moments, and a fallback ladder — see [Demo flow](docs/demo-flow.md).

## How it works

Dataverse `GetOnNewItems_V2` poll (primary) or Outlook `OnNewEmailV3` (optional) →
normalized manifest Blob → hosted skill → Durable Task Scheduler → HTML report Blob.

The normalized manifest is create-only and keyed by Request ID. A Blob lease serializes
concurrent deliveries, and report publication uses a stable overwrite-safe Blob name.

[How it works](docs/how-it-works.md) ·
[Use cases](docs/use-cases.md) ·
[Customize](docs/customize.md) ·
[Deploy](docs/deploy.md) ·
[Troubleshooting](docs/troubleshooting.md) ·
[Demo flow](docs/demo-flow.md)

Clean up Azure resources with `azd down --purge`. Dataverse solution cleanup remains an
explicit environment-owner action.
