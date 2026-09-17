$ErrorActionPreference = 'Stop'

$resourceGroup = azd env get-value AZURE_RESOURCE_GROUP_NAME
$functionName = azd env get-value AZURE_FUNCTION_NAME
$storageAccount = azd env get-value AZURE_STORAGE_ACCOUNT_NAME
$containerName = azd env get-value POLICY_INTAKE_CONTAINER
$subscriptionName = 'policy-intake-main'
$subjectPrefix = "/blobServices/default/containers/$containerName/blobs/normalized/"
$blobFunctionName = 'Host.Functions.main'

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

$mainBindingSource = ''
for ($attempt = 1; $attempt -le 12; $attempt++) {
    $mainBindingSource = az functionapp function show `
        -g $resourceGroup `
        -n $functionName `
        --function-name main `
        --query "config.bindings[?type=='blobTrigger'].source | [0]" `
        -o tsv 2>$null
    if ($LASTEXITCODE -eq 0 -and $mainBindingSource -eq 'EventGrid') {
        break
    }
    Start-Sleep -Seconds 10
}
if ($mainBindingSource -ne 'EventGrid') {
    throw "The main Event Grid Blob trigger is not registered with the Function host."
}

$blobExtensionKey = ''
for ($attempt = 1; $attempt -le 12; $attempt++) {
    $blobExtensionKey = az functionapp keys list `
        -g $resourceGroup `
        -n $functionName `
        --query systemKeys.blobs_extension `
        -o tsv 2>$null
    if ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrWhiteSpace($blobExtensionKey)) {
        break
    }
    Start-Sleep -Seconds 10
}
if ([string]::IsNullOrWhiteSpace($blobExtensionKey)) {
    throw "The blobs_extension system key is unavailable. Confirm the Function App started successfully."
}
$encodedKey = [uri]::EscapeDataString($blobExtensionKey)
$callbackUrl = "https://$functionHost/runtime/webhooks/blobs?functionName=$blobFunctionName&code=$encodedKey"

az eventgrid event-subscription show `
    --name $subscriptionName `
    --source-resource-id $storageId `
    --only-show-errors `
    -o none 2>$null
if ($LASTEXITCODE -eq 0) {
    az eventgrid event-subscription delete `
        --name $subscriptionName `
        --source-resource-id $storageId `
        --only-show-errors
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to remove the previous Event Grid subscription."
    }
}

az eventgrid event-subscription create `
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

$configuredEndpoint = az eventgrid event-subscription show `
    --name $subscriptionName `
    --source-resource-id $storageId `
    --include-full-endpoint-url `
    --query destination.endpointUrl `
    -o tsv
$configuredPrefix = az eventgrid event-subscription show `
    --name $subscriptionName `
    --source-resource-id $storageId `
    --query filter.subjectBeginsWith `
    -o tsv
$configuredEventTypes = az eventgrid event-subscription show `
    --name $subscriptionName `
    --source-resource-id $storageId `
    --query "join(',', filter.includedEventTypes)" `
    -o tsv
if (
    $configuredEndpoint -ne $callbackUrl -or
    $configuredPrefix -ne $subjectPrefix -or
    $configuredEventTypes -ne 'Microsoft.Storage.BlobCreated'
) {
    throw "Event Grid subscription verification failed."
}

Write-Host "Event Grid BlobCreated subscription configured for $containerName/normalized/." -ForegroundColor Green
