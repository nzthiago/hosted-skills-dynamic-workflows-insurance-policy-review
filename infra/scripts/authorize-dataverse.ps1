$ErrorActionPreference = 'Stop'

$resourceGroup = azd env get-value AZURE_RESOURCE_GROUP_NAME
$gatewayName = azd env get-value DATAVERSE_CONNECTOR_GATEWAY_NAME
$connectionId = azd env get-value DATAVERSE_CONNECTION_ID
$subscriptionId = az account show --query id -o tsv

$status = az resource show --ids $connectionId `
    --query properties.overallStatus -o tsv 2>$null
if ($status -eq 'Connected') {
    Write-Host "Dataverse connection is already authorized." -ForegroundColor Green
    exit 0
}

$portalUrl = "https://connectors.azure.com/$subscriptionId/$resourceGroup/$gatewayName/overview"
Write-Host "Authorize Dataverse with an account that has Global Read on the Policy Service Request table." -ForegroundColor Yellow
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
    throw "Dataverse connection is not Connected. Re-run 'azd provision' after authorization."
}

Write-Host "Dataverse connection is authorized." -ForegroundColor Green
