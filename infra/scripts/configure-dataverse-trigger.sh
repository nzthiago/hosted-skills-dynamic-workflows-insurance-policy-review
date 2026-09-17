#!/usr/bin/env sh

set -eu

resource_group=$(azd env get-value AZURE_RESOURCE_GROUP_NAME)
function_name=$(azd env get-value AZURE_FUNCTION_NAME)
gateway_name=$(azd env get-value DATAVERSE_CONNECTOR_GATEWAY_NAME)
connection_name=$(azd env get-value DATAVERSE_CONNECTION_NAME)
environment_url=$(azd env get-value DATAVERSE_ENVIRONMENT_URL 2>/dev/null || true)
environment_id=$(azd env get-value DATAVERSE_ENVIRONMENT_ID 2>/dev/null || true)
environment_name=$(azd env get-value DATAVERSE_ENVIRONMENT_NAME 2>/dev/null || true)
table_name=$(azd env get-value DATAVERSE_TABLE_NAME)

if [ -z "$environment_url" ] && { [ -n "$environment_id" ] || [ -n "$environment_name" ]; }; then
    token=$(az account get-access-token \
        --resource https://globaldisco.crm.dynamics.com \
        --query accessToken -o tsv)
    environment_url=$(curl -fsS \
        -H "Authorization: Bearer $token" \
        https://globaldisco.crm.dynamics.com/api/discovery/v2.0/Instances |
        jq -r --arg id "$environment_id" --arg name "$environment_name" \
            '.value[] | select(
                (($id != "") and (((.EnvironmentId // "") | ascii_downcase) == ($id | ascii_downcase)))
                or (($id == "") and (((.FriendlyName // "") | ascii_downcase) == ($name | ascii_downcase)))
            ) | .Url' |
        head -n 1)
fi

environment_url=${environment_url%/}
if [ -z "$environment_url" ]; then
    echo "Set DATAVERSE_ENVIRONMENT_URL, DATAVERSE_ENVIRONMENT_ID, or DATAVERSE_ENVIRONMENT_NAME before deployment." >&2
    exit 1
fi

function_host=$(az resource show \
    -g "$resource_group" \
    -n "$function_name" \
    --resource-type Microsoft.Web/sites \
    --query properties.defaultHostName \
    -o tsv)
if [ -z "$function_host" ]; then
    echo "Failed to resolve the Function App hostname." >&2
    exit 1
fi

connector_key=$(az functionapp keys list \
    -g "$resource_group" \
    -n "$function_name" \
    --query systemKeys.connector_extension \
    -o tsv)
if [ -z "$connector_key" ]; then
    echo "The connector_extension system key is unavailable. Confirm the Function App started successfully." >&2
    exit 1
fi

encoded_key=$(CONNECTOR_KEY="$connector_key" python3 -c \
    'import os, urllib.parse; print(urllib.parse.quote(os.environ["CONNECTOR_KEY"], safe=""))')
callback_url="https://$function_host/runtime/webhooks/connector?functionName=DataversePolicyIntake&code=$encoded_key"

az deployment group create \
    -g "$resource_group" \
    --name dataverse-policy-intake-trigger \
    --template-file infra/app/trigger-config.bicep \
    --parameters \
        connectorGatewayName="$gateway_name" \
        connectionName="$connection_name" \
        dataset="$environment_url" \
        tableName="$table_name" \
        callbackUrl="$callback_url" \
    --only-show-errors \
    -o none

azd env set DATAVERSE_ENVIRONMENT_URL "$environment_url" >/dev/null
echo "Dataverse created-row trigger configured for '$table_name' with a five-minute polling interval."
