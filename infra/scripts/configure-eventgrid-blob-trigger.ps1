$ErrorActionPreference = 'Stop'

$resourceGroup = azd env get-value AZURE_RESOURCE_GROUP_NAME
$functionName = azd env get-value AZURE_FUNCTION_NAME
$storageAccount = azd env get-value AZURE_STORAGE_ACCOUNT_NAME
$containerName = azd env get-value POLICY_INTAKE_CONTAINER
$subscriptionName = 'policy-intake-main'
$subjectPrefix = "/blobServices/default/containers/$containerName/blobs/normalized/"

$storageId = az storage account show `
    -g $resourceGroup `
    -n $storageAccount `
    --query id `
    -o tsv
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($storageId)) {
    throw "Failed to resolve the policy intake storage account."
}

$functionHost = az resource show `
    -g $resourceGroup `
    -n $functionName `
    --resource-type Microsoft.Web/sites `
    --query properties.defaultHostName `
    -o tsv
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($functionHost)) {
    throw "Failed to resolve the Function App hostname."
}

$blobExtensionKey = az functionapp keys list `
    -g $resourceGroup `
    -n $functionName `
    --query systemKeys.blobs_extension `
    -o tsv
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($blobExtensionKey)) {
    throw "The blobs_extension system key is unavailable. Confirm the Function App started successfully."
}
$encodedKey = [uri]::EscapeDataString($blobExtensionKey)
$callbackUrl = "https://$functionHost/runtime/webhooks/blobs?functionName=main&code=$encodedKey"

az eventgrid event-subscription show `
    --name $subscriptionName `
    --source-resource-id $storageId `
    --only-show-errors `
    -o none 2>$null
$operation = if ($LASTEXITCODE -eq 0) { 'update' } else { 'create' }

az eventgrid event-subscription $operation `
    --name $subscriptionName `
    --source-resource-id $storageId `
    --endpoint-type webhook `
    --endpoint $callbackUrl `
    --included-event-types Microsoft.Storage.BlobCreated `
    --subject-begins-with $subjectPrefix `
    --only-show-errors `
    -o none
if ($LASTEXITCODE -ne 0) {
    throw "Failed to configure the Event Grid BlobCreated subscription."
}

Write-Host "Event Grid BlobCreated subscription configured for $containerName/normalized/." -ForegroundColor Green
