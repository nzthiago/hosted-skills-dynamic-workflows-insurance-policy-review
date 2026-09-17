#!/usr/bin/env sh

set -eu

resource_group=$(azd env get-value AZURE_RESOURCE_GROUP_NAME)
function_name=$(azd env get-value AZURE_FUNCTION_NAME)
storage_account=$(azd env get-value AZURE_STORAGE_ACCOUNT_NAME)
container_name=$(azd env get-value POLICY_INTAKE_CONTAINER)
subscription_name="policy-intake-main"
subject_prefix="/blobServices/default/containers/$container_name/blobs/normalized/"

storage_id=$(az storage account show \
    -g "$resource_group" \
    -n "$storage_account" \
    --query id \
    -o tsv)
function_host=$(az resource show \
    -g "$resource_group" \
    -n "$function_name" \
    --resource-type Microsoft.Web/sites \
    --query properties.defaultHostName \
    -o tsv)
blob_extension_key=$(az functionapp keys list \
    -g "$resource_group" \
    -n "$function_name" \
    --query systemKeys.blobs_extension \
    -o tsv)
if [ -z "$blob_extension_key" ]; then
    echo "The blobs_extension system key is unavailable. Confirm the Function App started successfully." >&2
    exit 1
fi
encoded_key=$(BLOB_EXTENSION_KEY="$blob_extension_key" python3 -c \
    'import os, urllib.parse; print(urllib.parse.quote(os.environ["BLOB_EXTENSION_KEY"], safe=""))')
callback_url="https://$function_host/runtime/webhooks/blobs?functionName=main&code=$encoded_key"

if az eventgrid event-subscription show \
    --name "$subscription_name" \
    --source-resource-id "$storage_id" \
    --only-show-errors \
    -o none 2>/dev/null; then
    operation=update
else
    operation=create
fi

az eventgrid event-subscription "$operation" \
    --name "$subscription_name" \
    --source-resource-id "$storage_id" \
    --endpoint-type webhook \
    --endpoint "$callback_url" \
    --included-event-types Microsoft.Storage.BlobCreated \
    --subject-begins-with "$subject_prefix" \
    --only-show-errors \
    -o none

echo "Event Grid BlobCreated subscription configured for $container_name/normalized/."
