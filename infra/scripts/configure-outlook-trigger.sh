#!/usr/bin/env sh

set -eu

resource_group=$(azd env get-value AZURE_RESOURCE_GROUP_NAME)
function_name=$(azd env get-value AZURE_FUNCTION_NAME)
gateway_name=$(azd env get-value O365_CONNECTOR_GATEWAY_NAME)
connection_name=$(azd env get-value O365_CONNECTION_NAME)
folder_path=$(azd env get-value OUTLOOK_FOLDER_PATH)

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
callback_url="https://$function_name.azurewebsites.net/runtime/webhooks/connector?functionName=OutlookPolicyIntake&code=$encoded_key"

az deployment group create \
    -g "$resource_group" \
    --name outlook-policy-intake-trigger \
    --template-file infra/app/outlook-trigger-config.bicep \
    --parameters \
        connectorGatewayName="$gateway_name" \
        connectionName="$connection_name" \
        folderPath="$folder_path" \
        callbackUrl="$callback_url" \
    --only-show-errors \
    -o none

echo "Office 365 Outlook policy intake trigger configured for '$folder_path'."
