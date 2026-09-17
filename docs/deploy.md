# Deploy to Azure

## Prerequisites

- Existing Dataverse environment and customization permissions
- Azure CLI authentication with Dataverse customization permissions
- Optional Power Platform CLI when PAC authentication is permitted by tenant policy
- Dataverse connector identity with Global Read on the Policy Service Request table
- Azure subscription and role-assignment permissions
- Python 3.13, Azure Developer CLI, and Azure CLI

The Function region must support Flex Consumption, Durable Task Scheduler, and the
configured Foundry model. The Connector Namespace defaults to `westcentralus` and can be
changed with `CONNECTOR_NAMESPACE_LOCATION`.

## Prepare Dataverse

```bash
az login --tenant "<tenant ID>"
python scripts/setup_dataverse_schema.py \
  --environment-id "<complete environment ID>" \
  --auth-source azure-cli
```

PAC remains available for non-corporate environments:

```bash
pac auth create --environment "<environment ID or URL>" --name insurance-policy-sample
python scripts/setup_dataverse_schema.py \
  --environment-id "<complete environment ID>" \
  --auth-source pac
```

Grant the connector authorization account Global Read on
`ipr_policyservicerequests`. Complete this before deployment or the Admin Only poll
returns 403. `--environment-id` and `--environment-name` resolve the organization URL
through Dataverse Global Discovery; `--environment-url` bypasses discovery. Azure CLI
must be signed in to the environment's tenant. Copy the complete ID from the Power Apps
URL without removing prefixes such as `Default-`.

## Deploy

```bash
azd auth login
az login --tenant "<tenant ID>"
azd env set DATAVERSE_ENVIRONMENT_ID "<complete environment ID>"
azd env set DATAVERSE_TABLE_NAME "ipr_policyservicerequests"
azd up
```

Alternatively set the exact `DATAVERSE_ENVIRONMENT_URL`, or use
`DATAVERSE_ENVIRONMENT_NAME`. Resolution precedence is URL, ID, then friendly name.
The local azd values are stored under ignored `.azure/` state and must not be copied
into tracked parameter defaults.

The deployment creates Functions, Durable Task Scheduler, Foundry, Storage containers,
Application Insights, managed identity/RBAC, and a Dataverse Connector Namespace
connection. Dataverse does not use connector actions or an MCP server.

The `postprovision` hook opens `connectors.azure.com` for interactive Dataverse OAuth.
The `postdeploy` hook resolves the environment URL, obtains the `connector_extension`
system key, and creates a five-minute `GetOnNewItems_V2` trigger without printing the
callback URL. It also idempotently creates or updates an Event Grid subscription from
the storage account to the Blob extension webhook for the `main` Function, filtered to
`Microsoft.Storage.BlobCreated` events whose subject begins with
`/blobServices/default/containers/policy-intake/blobs/normalized/`. The webhook callback
contains the `blobs_extension` system key and is never printed.

## Enable Outlook fallback

Outlook is disabled by default. Enable it before `azd up` when an attachment-based
contingency is required:

```bash
azd env set ENABLE_OUTLOOK_FALLBACK true
azd env set OUTLOOK_FOLDER_PATH "Inbox/Policy Review"
azd up
```

This adds an Office 365 Outlook connection, Function and Connector Namespace identity
access policies, an allow-listed `GetAttachment_V2` MCP server, and an `OnNewEmailV3`
trigger. The combined postprovision hook requires interactive authorization for both
connections. The combined postdeploy hook configures Dataverse first and Outlook second.

Set `ENABLE_OUTLOOK_FALLBACK=false` and run `azd up` to remove the Outlook trigger and
remove its MCP endpoint from Function settings. Azure incremental deployment can retain
the inactive Outlook connection and MCP resource until the resource group is recreated
or cleaned up; without the trigger they cannot initiate policy intake. The preprovision
hook removes a stale Outlook trigger before other provisioning or authorization work can
fail, and postdeploy repeats the check idempotently.

## Outputs

| Output | Purpose |
| --- | --- |
| `POLICY_REVIEW_STORAGE_URL` | Blob service endpoint |
| `POLICY_REVIEW_CONTAINER` | HTML report container |
| `POLICY_INTAKE_CONTAINER` | Normalized manifest container |
| `DATAVERSE_CONNECTOR_GATEWAY_NAME` | Connector Namespace resource |
| `DATAVERSE_CONNECTION_ID` | Authorization/status lookup |
| `DATAVERSE_ENVIRONMENT_URL` | Trigger dataset when supplied directly |
| `DATAVERSE_ENVIRONMENT_ID` | Stable Power Platform ID resolved through Global Discovery |
| `DATAVERSE_ENVIRONMENT_NAME` | Friendly environment lookup |
| `DATAVERSE_TABLE_NAME` | Trigger entity set |
| `ENABLE_OUTLOOK_FALLBACK` | Whether Outlook resources and trigger are enabled |
| `O365_CONNECTION_ID` | Optional Outlook authorization/status lookup |
| `O365_MCP_SERVER_URL` | Optional allow-listed attachment endpoint |
| `OUTLOOK_FOLDER_PATH` | Optional dedicated mailbox folder |
| `DURABLE_TASK_DASHBOARD_URL` | Workflow dashboard |

## Reconfigure the table

```bash
azd env set DATAVERSE_TABLE_NAME "<plural logical entity-set name>"
azd deploy
```

Run the postdeploy hook again after changing the trigger dataset or table.

## Clean up

```bash
azd down --purge
```

This does not delete the Dataverse unmanaged solution or table.
