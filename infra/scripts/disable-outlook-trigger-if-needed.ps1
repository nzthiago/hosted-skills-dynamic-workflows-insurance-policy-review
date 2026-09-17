$ErrorActionPreference = 'Stop'

$outlookEnabled = azd env get-value ENABLE_OUTLOOK_FALLBACK 2>$null
if ($outlookEnabled -eq 'true') {
    return
}

$resourceGroup = azd env get-value AZURE_RESOURCE_GROUP_NAME 2>$null
$gatewayName = azd env get-value DATAVERSE_CONNECTOR_GATEWAY_NAME 2>$null
if (
    [string]::IsNullOrWhiteSpace($resourceGroup) -or
    [string]::IsNullOrWhiteSpace($gatewayName)
) {
    return
}

$triggerId = az resource list `
    -g $resourceGroup `
    --resource-type Microsoft.Web/connectorGateways/triggerconfigs `
    --query "[?name=='$gatewayName/office365-policy-request-email'].id | [0]" `
    -o tsv
if ($LASTEXITCODE -ne 0) {
    throw "Failed to check for an existing Office 365 Outlook fallback trigger."
}
if (-not [string]::IsNullOrWhiteSpace($triggerId)) {
    az resource delete `
        --ids $triggerId `
        --api-version 2026-05-01-preview
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to remove the disabled Office 365 Outlook fallback trigger."
    }
    Write-Host "Existing Office 365 Outlook fallback trigger removed."
}
