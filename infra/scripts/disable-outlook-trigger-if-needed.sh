#!/usr/bin/env sh

set -eu

outlook_enabled=$(azd env get-value ENABLE_OUTLOOK_FALLBACK 2>/dev/null || true)
if [ "$outlook_enabled" = "true" ]; then
    exit 0
fi

resource_group=$(azd env get-value AZURE_RESOURCE_GROUP_NAME 2>/dev/null || true)
gateway_name=$(azd env get-value DATAVERSE_CONNECTOR_GATEWAY_NAME 2>/dev/null || true)
if [ -z "$resource_group" ] || [ -z "$gateway_name" ]; then
    exit 0
fi

trigger_id=$(az resource list \
    -g "$resource_group" \
    --resource-type Microsoft.Web/connectorGateways/triggerconfigs \
    --query "[?name=='$gateway_name/office365-policy-request-email'].id | [0]" \
    -o tsv)
if [ -n "$trigger_id" ]; then
    az resource delete \
        --ids "$trigger_id" \
        --api-version 2026-05-01-preview
    echo "Existing Office 365 Outlook fallback trigger removed."
fi
