# Deploy to Azure

## Prerequisites

- Azure subscription and role-assignment permissions
- Python 3.13, Azure Developer CLI, and Azure CLI
- Office 365 account that owns the dedicated intake mailbox/folder

The region must support Flex Consumption, Durable Task Scheduler, the configured Foundry
model, and Connector Namespaces.

## Deploy

```bash
azd auth login
azd env set OUTLOOK_FOLDER_PATH "Inbox/Policy Review"
azd up
```

The deployment creates Functions, Durable Task Scheduler, Foundry, Storage containers,
Application Insights, managed identity/RBAC, and an Office 365 Outlook Connector
Namespace connection plus a `GetAttachment_V2`-only MCP server.

The `postprovision` hook opens `connectors.azure.com`; authorize interactively with the
dedicated mailbox account. The `postdeploy` hook obtains the `connector_extension`
system key and deploys the trigger config. It does not print the callback URL.

## Outputs

| Output | Purpose |
|---|---|
| `POLICY_REVIEW_STORAGE_URL` | Blob service endpoint |
| `POLICY_REVIEW_CONTAINER` | HTML report container |
| `POLICY_INTAKE_CONTAINER` | Staged attachments and normalized manifests |
| `O365_CONNECTOR_GATEWAY_NAME` | Connector Namespace resource |
| `O365_CONNECTION_ID` | Authorization/status lookup |
| `O365_MCP_SERVER_URL` | GetAttachment MCP endpoint |
| `OUTLOOK_FOLDER_PATH` | Trigger folder configuration |
| `DURABLE_TASK_DASHBOARD_URL` | Workflow dashboard |

## Reconfigure the folder

```bash
azd env set OUTLOOK_FOLDER_PATH "<connector folder ID or accepted path>"
azd deploy
```

If only infrastructure parameters changed, run the postdeploy trigger script for the
current platform after provisioning/deployment.

## Clean up

```bash
azd down --purge
```
