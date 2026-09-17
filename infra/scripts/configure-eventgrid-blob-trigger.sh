#!/usr/bin/env sh

set -eu

resource_group=$(azd env get-value AZURE_RESOURCE_GROUP_NAME)
function_name=$(azd env get-value AZURE_FUNCTION_NAME)
storage_account=$(azd env get-value AZURE_STORAGE_ACCOUNT_NAME)
container_name=$(azd env get-value POLICY_INTAKE_CONTAINER)
subscription_name="policy-intake-normalized-main"
subject_prefix="/blobServices/default/containers/$container_name/blobs/normalized/"

storage_id=$(az storage account show \
    -g "$resource_group" \
    -n "$storage_account" \
    --query id \
    -o tsv)
function_app_id=$(az resource show \
    -g "$resource_group" \
    -n "$function_name" \
    --resource-type Microsoft.Web/sites \
    --query id \
    -o tsv)
function_id="$function_app_id/functions/main"

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
    --endpoint-type azurefunction \
    --endpoint "$function_id" \
    --included-event-types Microsoft.Storage.BlobCreated \
    --subject-begins-with "$subject_prefix" \
    --only-show-errors \
    -o none

echo "Event Grid BlobCreated subscription configured for $container_name/normalized/."
