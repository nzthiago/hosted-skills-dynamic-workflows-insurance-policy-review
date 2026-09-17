#!/usr/bin/env sh

set -eu

resource_group=$(azd env get-value AZURE_RESOURCE_GROUP_NAME)
gateway_name=$(azd env get-value DATAVERSE_CONNECTOR_GATEWAY_NAME)
connection_id=$(azd env get-value DATAVERSE_CONNECTION_ID)
subscription_id=$(az account show --query id -o tsv)

status=$(az resource show --ids "$connection_id" \
    --query properties.overallStatus -o tsv 2>/dev/null || true)
if [ "$status" = "Connected" ]; then
    echo "Dataverse connection is already authorized."
    exit 0
fi

portal_url="https://connectors.azure.com/$subscription_id/$resource_group/$gateway_name/overview"
echo "Authorize the Dataverse connection with an account that has Global Read on the Policy Service Request table."
echo "Connector Namespace portal: $portal_url"

if command -v open >/dev/null 2>&1; then
    open "$portal_url" >/dev/null 2>&1 || true
elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$portal_url" >/dev/null 2>&1 || true
fi

printf "Press Enter after the connection shows Connected in the portal: "
read -r _

status=$(az resource show --ids "$connection_id" \
    --query properties.overallStatus -o tsv 2>/dev/null || true)
if [ "$status" != "Connected" ]; then
    echo "Dataverse connection is not Connected. Re-run 'azd provision' after authorization." >&2
    exit 1
fi

echo "Dataverse connection is authorized."
