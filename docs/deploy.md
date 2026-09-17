# Deploy to Azure

## Prerequisites

- Existing Dataverse environment and customization permissions
- Power Platform CLI for reproducible schema setup
- Dataverse connector identity with Global Read on the Policy Service Request table
- Azure subscription and role-assignment permissions
- Python 3.13, Azure Developer CLI, and Azure CLI

The Function region must support Flex Consumption, Durable Task Scheduler, and the
configured Foundry model. The Connector Namespace defaults to `westcentralus` and can be
changed with `CONNECTOR_NAMESPACE_LOCATION`.

## Prepare Dataverse

```bash
pac auth create --environment "<environment>" --name insurance-policy-sample
python scripts/setup_dataverse_schema.py \
  --environment-url "https://<org>.crm.dynamics.com"
```

Grant the connector authorization account Global Read on
`ipr_policyservicerequests`. Complete this before deployment or the Admin Only poll
returns 403.

## Deploy

```bash
azd auth login
azd env set DATAVERSE_ENVIRONMENT_NAME "<friendly environment name>"
azd env set DATAVERSE_TABLE_NAME "ipr_policyservicerequests"
azd up
```

Alternatively set the exact `DATAVERSE_ENVIRONMENT_URL`.

The deployment creates Functions, Durable Task Scheduler, Foundry, Storage containers,
Application Insights, managed identity/RBAC, and a Dataverse Connector Namespace
connection. Dataverse does not use connector actions or an MCP server.

The `postprovision` hook opens `connectors.azure.com` for interactive Dataverse OAuth.
The `postdeploy` hook resolves the environment URL, obtains the `connector_extension`
system key, and creates a five-minute `GetOnNewItems_V2` trigger without printing the
callback URL.

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
