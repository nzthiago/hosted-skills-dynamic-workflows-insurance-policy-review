$ErrorActionPreference = 'Stop'

$resourceGroup = azd env get-value AZURE_RESOURCE_GROUP_NAME
$functionName = azd env get-value AZURE_FUNCTION_NAME
$gatewayName = azd env get-value O365_CONNECTOR_GATEWAY_NAME
$connectionName = azd env get-value O365_CONNECTION_NAME
$folderPath = azd env get-value OUTLOOK_FOLDER_PATH

$connectorKey = az functionapp keys list `
    -g $resourceGroup `
    -n $functionName `
    --query systemKeys.connector_extension `
    -o tsv
if ([string]::IsNullOrWhiteSpace($connectorKey)) {
    throw "The connector_extension system key is unavailable. Confirm the Function App started successfully."
}

$encodedKey = [uri]::EscapeDataString($connectorKey)
$callbackUrl = "https://$functionName.azurewebsites.net/runtime/webhooks/connector?functionName=OutlookPolicyIntake&code=$encodedKey"

az deployment group create `
    -g $resourceGroup `
    --name outlook-policy-intake-trigger `
    --template-file infra/app/trigger-config.bicep `
    --parameters `
        connectorGatewayName=$gatewayName `
        connectionName=$connectionName `
        folderPath=$folderPath `
        callbackUrl=$callbackUrl `
    --only-show-errors `
    -o none

if ($LASTEXITCODE -ne 0) {
    throw "Failed to configure the Office 365 Outlook trigger."
}

Write-Host "Office 365 Outlook policy intake trigger configured for '$folderPath'." -ForegroundColor Green
