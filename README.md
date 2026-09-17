# Insurance Policy Review with Dynamic Workflows

[![Python](https://img.shields.io/badge/Python-3.13-blue.svg)](https://www.python.org/downloads/)

A markdown-first [Azure Functions hosted skill](https://azure.github.io/azure-functions-agents-runtime/)
that turns insurance-policy request emails into durable, human-reviewed document packets.

## What it does

- Watches a dedicated Office 365 Outlook mailbox folder through a Connector Namespace trigger.
- Validates a strict subject and attachment naming convention.
- Calls the allow-listed `GetAttachment_V2` connector operation for every attachment.
- Stages binary files and one normalized request manifest in Blob Storage.
- Runs validate → parallel inspect → build → publish as a Dynamic Workflow.
- Produces an HTML report while keeping every policy decision human-owned.

The sample records file metadata and Blob references. It does not verify document
authenticity or update a policy.

## Email contract

Send mail to the account that authorizes the Office 365 Outlook connection. Route it to
the configured folder, by mailbox rule if necessary.

Subject:

```text
[POLICY-REQUEST] PSR-2026-00042 | AUTO-100042 | Jordan Lee
```

Non-inline attachment names:

```text
driver_license__DOC-001__jordan-lee-license.pdf
signed_request__DOC-002__signed-request.pdf
```

Only PDF, JPEG, and PNG files up to 10 MiB each are accepted. Request IDs and document
IDs must be unique. Inline signature images are ignored.

## Prerequisites

- Azure subscription
- Python 3.13 and [uv](https://docs.astral.sh/uv/)
- [Azure Developer CLI](https://learn.microsoft.com/azure/developer/azure-developer-cli/install-azd)
- Azure CLI
- Office 365 account for the dedicated intake mailbox

## Deploy and authorize

Choose the mailbox folder before provisioning:

```bash
azd auth login
azd env set OUTLOOK_FOLDER_PATH "Inbox/Policy Review"
azd up
```

`postprovision` opens the Connector Namespace portal. Authorization remains interactive:
sign in as the dedicated mailbox owner and confirm the connection reaches `Connected`.
After application deployment, `postdeploy` creates the `OnNewEmailV3` trigger config
without printing its callback key.

The folder value is connector-defined. Validate the folder ID/path in the Connector
Namespace portal before a live demo; the default is `Inbox/Policy Review`.

## Run the email demo

1. Send a uniquely numbered request email that follows the contract.
2. Follow the run in the Durable Task Scheduler dashboard:

   ```bash
   azd env get-value DURABLE_TASK_DASHBOARD_URL
   ```

3. Load the report settings and download the result:

   ```bash
   export POLICY_REVIEW_STORAGE_URL="$(azd env get-value POLICY_REVIEW_STORAGE_URL)"
   export POLICY_REVIEW_CONTAINER="$(azd env get-value POLICY_REVIEW_CONTAINER)"
   uv run --with-requirements requirements.txt python scripts/demo.py download
   ```

The report is saved to `output/PSR-2026-00042.html`.

## Manual/OneDrive fallback

If the Outlook polling trigger is delayed, use the normalized-request fallback. The
example references a local file; replace `source_path` with a path in a locally synced
OneDrive folder when desired.

```bash
export POLICY_REVIEW_STORAGE_URL="$(azd env get-value POLICY_REVIEW_STORAGE_URL)"
export POLICY_INTAKE_CONTAINER="$(azd env get-value POLICY_INTAKE_CONTAINER)"
uv run --with-requirements requirements.txt \
  python scripts/demo.py submit-manual \
  --request examples/policy-service-request.json
```

The fallback stages files and creates the same `policy-intake/normalized/<request>.json`
manifest consumed by the hosted skill. Reusing a request ID is rejected.

## Local development

Copy the settings template, populate the Foundry and deployed Connector MCP values, then
start Azurite, the Durable Task Scheduler emulator, and Functions:

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

Connector callbacks normally require a deployed Function App. Test the local workflow
with `submit-manual`.

## Live-demo reliability

- Authorize the connector and verify the folder before the session.
- Use a mailbox rule so matching mail reaches the watched folder automatically.
- Use a new request ID for every rehearsal; duplicates intentionally produce no new manifest.
- Keep attachments small and avoid `.msg`, cloud-reference, encrypted, and inline-only files.
- Send the email at least two polling intervals before the workflow walkthrough.
- Keep the manual/OneDrive-synced fallback request ready in another terminal.
- Confirm the DTS dashboard and Blob report download before presenting.

## How it works

Outlook Connector trigger → `OutlookPolicyIntake` → `GetAttachment_V2` → staged attachment
Blobs → normalized manifest Blob → hosted skill → Durable Task Scheduler → HTML report Blob.

The trigger includes attachment metadata so attachment IDs are available, but the intake
code discards any trigger-provided `contentBytes` and explicitly retrieves each file.
A deterministic request manifest and a Blob lease prevent connector retries from starting
another workflow for the same request ID. Report publication remains overwrite-safe.

[How it works](docs/how-it-works.md) ·
[Use cases](docs/use-cases.md) ·
[Customize](docs/customize.md) ·
[Deploy](docs/deploy.md) ·
[Troubleshooting](docs/troubleshooting.md)

Clean up with `azd down --purge`.
