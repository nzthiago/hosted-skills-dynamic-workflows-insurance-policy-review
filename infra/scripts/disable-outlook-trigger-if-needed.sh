#!/usr/bin/env sh

set -eu

optional_azd_value() {
    value=$(azd env get-value "$1" 2>/dev/null) || value=
    case "$value" in
        *"ERROR: key not found in environment values:"*)
            value=
            ;;
    esac
    printf '%s' "$value"
}

outlook_enabled=$(optional_azd_value ENABLE_OUTLOOK_FALLBACK)
if [ "$outlook_enabled" = "true" ]; then
    exit 0
fi

resource_group=$(optional_azd_value AZURE_RESOURCE_GROUP_NAME)
gateway_name=$(optional_azd_value DATAVERSE_CONNECTOR_GATEWAY_NAME)
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
