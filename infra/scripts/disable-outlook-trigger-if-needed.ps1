$ErrorActionPreference = 'Stop'

function Get-OptionalAzdValue {
    param([Parameter(Mandatory)][string] $Name)

    $output = @(azd env get-value $Name 2>$null)
    if ($LASTEXITCODE -ne 0) {
        return ''
    }
    $value = ($output -join "`n").Trim()
    if ($value -match '(?m)^ERROR: key not found in environment values:') {
        return ''
    }
    return $value
}

$outlookEnabled = Get-OptionalAzdValue ENABLE_OUTLOOK_FALLBACK
if ($outlookEnabled -eq 'true') {
    return
}

$resourceGroup = Get-OptionalAzdValue AZURE_RESOURCE_GROUP_NAME
$gatewayName = Get-OptionalAzdValue DATAVERSE_CONNECTOR_GATEWAY_NAME
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
