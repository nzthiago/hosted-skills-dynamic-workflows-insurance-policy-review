$ErrorActionPreference = 'Stop'

$resourceGroup = azd env get-value AZURE_RESOURCE_GROUP_NAME
$gatewayName = azd env get-value O365_CONNECTOR_GATEWAY_NAME
$connectionId = azd env get-value O365_CONNECTION_ID
$subscriptionId = az account show --query id -o tsv

$status = az resource show --ids $connectionId `
    --query properties.overallStatus -o tsv 2>$null
if ($status -eq 'Connected') {
    Write-Host "Office 365 Outlook connection is already authorized." -ForegroundColor Green
    return
}

$portalUrl = "https://connectors.azure.com/$subscriptionId/$resourceGroup/$gatewayName/overview"
Write-Host "Authorize the Office 365 Outlook connection with the dedicated intake mailbox." -ForegroundColor Yellow
Write-Host "Connector Namespace portal: $portalUrl" -ForegroundColor Cyan

try {
    Start-Process $portalUrl | Out-Null
}
catch {
    Write-Host "Open the URL above in a browser." -ForegroundColor Yellow
}

Read-Host "Press Enter after the connection shows Connected in the portal"
$status = az resource show --ids $connectionId `
    --query properties.overallStatus -o tsv 2>$null
if ($status -ne 'Connected') {
    throw "Office 365 Outlook connection is not Connected. Re-run 'azd provision' after authorization."
}

Write-Host "Office 365 Outlook connection is authorized." -ForegroundColor Green
