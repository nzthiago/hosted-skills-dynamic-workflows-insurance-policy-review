$ErrorActionPreference = 'Stop'

$resourceGroup = azd env get-value AZURE_RESOURCE_GROUP_NAME
$functionName = azd env get-value AZURE_FUNCTION_NAME
$gatewayName = azd env get-value DATAVERSE_CONNECTOR_GATEWAY_NAME
$connectionName = azd env get-value DATAVERSE_CONNECTION_NAME
$environmentUrl = azd env get-value DATAVERSE_ENVIRONMENT_URL 2>$null
$environmentName = azd env get-value DATAVERSE_ENVIRONMENT_NAME 2>$null
$tableName = azd env get-value DATAVERSE_TABLE_NAME

if ([string]::IsNullOrWhiteSpace($environmentUrl) -and -not [string]::IsNullOrWhiteSpace($environmentName)) {
    $token = az account get-access-token `
        --resource https://globaldisco.crm.dynamics.com `
        --query accessToken -o tsv
    $instances = Invoke-RestMethod `
        -Uri 'https://globaldisco.crm.dynamics.com/api/discovery/v2.0/Instances' `
        -Headers @{ Authorization = "Bearer $token" }
    $environmentUrl = $instances.value |
        Where-Object { $_.FriendlyName -ieq $environmentName } |
        Select-Object -First 1 -ExpandProperty Url
}

$environmentUrl = "$environmentUrl".TrimEnd('/')
if ([string]::IsNullOrWhiteSpace($environmentUrl)) {
    throw "Set DATAVERSE_ENVIRONMENT_URL or DATAVERSE_ENVIRONMENT_NAME before deployment."
}

$connectorKey = az functionapp keys list `
    -g $resourceGroup `
    -n $functionName `
    --query systemKeys.connector_extension `
    -o tsv
if ([string]::IsNullOrWhiteSpace($connectorKey)) {
    throw "The connector_extension system key is unavailable. Confirm the Function App started successfully."
}

$encodedKey = [uri]::EscapeDataString($connectorKey)
$callbackUrl = "https://$functionName.azurewebsites.net/runtime/webhooks/connector?functionName=DataversePolicyIntake&code=$encodedKey"

az deployment group create `
    -g $resourceGroup `
    --name dataverse-policy-intake-trigger `
    --template-file infra/app/trigger-config.bicep `
    --parameters `
        connectorGatewayName=$gatewayName `
        connectionName=$connectionName `
        dataset=$environmentUrl `
        tableName=$tableName `
        callbackUrl=$callbackUrl `
    --only-show-errors `
    -o none

if ($LASTEXITCODE -ne 0) {
    throw "Failed to configure the Dataverse created-row trigger."
}

azd env set DATAVERSE_ENVIRONMENT_URL $environmentUrl | Out-Null
Write-Host "Dataverse created-row trigger configured for '$tableName' with a five-minute polling interval." -ForegroundColor Green
