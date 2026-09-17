#!/usr/bin/env sh

set -eu

resource_group=$(azd env get-value AZURE_RESOURCE_GROUP_NAME)
function_name=$(azd env get-value AZURE_FUNCTION_NAME)
storage_account=$(azd env get-value AZURE_STORAGE_ACCOUNT_NAME)
container_name=$(azd env get-value POLICY_INTAKE_CONTAINER)
subscription_name="policy-intake-main"
subject_prefix="/blobServices/default/containers/$container_name/blobs/normalized/"
blob_function_name="Host.Functions.main"

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

attempt=1
main_binding_source=""
while [ "$attempt" -le 12 ]; do
    main_binding_source=$(az functionapp function show \
        -g "$resource_group" \
        -n "$function_name" \
        --function-name main \
        --query "config.bindings[?type=='blobTrigger'].source | [0]" \
        -o tsv 2>/dev/null || true)
    if [ "$main_binding_source" = "EventGrid" ]; then
        break
    fi
    attempt=$((attempt + 1))
    sleep 10
done
if [ "$main_binding_source" != "EventGrid" ]; then
    echo "The main Event Grid Blob trigger is not registered with the Function host." >&2
    exit 1
fi

attempt=1
blob_extension_key=""
while [ "$attempt" -le 12 ]; do
    blob_extension_key=$(az functionapp keys list \
        -g "$resource_group" \
        -n "$function_name" \
        --query systemKeys.blobs_extension \
        -o tsv 2>/dev/null || true)
    if [ -n "$blob_extension_key" ]; then
        break
    fi
    attempt=$((attempt + 1))
    sleep 10
done
if [ -z "$blob_extension_key" ]; then
    echo "The blobs_extension system key is unavailable. Confirm the Function App started successfully." >&2
    exit 1
fi
encoded_key=$(BLOB_EXTENSION_KEY="$blob_extension_key" python3 -c \
    'import os, urllib.parse; print(urllib.parse.quote(os.environ["BLOB_EXTENSION_KEY"], safe=""))')
callback_url="https://$function_host/runtime/webhooks/blobs?functionName=$blob_function_name&code=$encoded_key"

if az eventgrid event-subscription show \
    --name "$subscription_name" \
    --source-resource-id "$storage_id" \
    --only-show-errors \
    -o none 2>/dev/null; then
    az eventgrid event-subscription delete \
        --name "$subscription_name" \
        --source-resource-id "$storage_id" \
        --only-show-errors
fi

az eventgrid event-subscription create \
    --name "$subscription_name" \
    --source-resource-id "$storage_id" \
    --endpoint-type webhook \
    --endpoint "$callback_url" \
    --included-event-types Microsoft.Storage.BlobCreated \
    --subject-begins-with "$subject_prefix" \
    --only-show-errors \
    -o none

configured_endpoint=$(az eventgrid event-subscription show \
    --name "$subscription_name" \
    --source-resource-id "$storage_id" \
    --include-full-endpoint-url \
    --query destination.endpointUrl \
    -o tsv)
configured_prefix=$(az eventgrid event-subscription show \
    --name "$subscription_name" \
    --source-resource-id "$storage_id" \
    --query filter.subjectBeginsWith \
    -o tsv)
configured_event_types=$(az eventgrid event-subscription show \
    --name "$subscription_name" \
    --source-resource-id "$storage_id" \
    --query "join(',', filter.includedEventTypes)" \
    -o tsv)
if [ "$configured_endpoint" != "$callback_url" ] \
    || [ "$configured_prefix" != "$subject_prefix" ] \
    || [ "$configured_event_types" != "Microsoft.Storage.BlobCreated" ]; then
    echo "Event Grid subscription verification failed." >&2
    exit 1
fi

echo "Event Grid BlobCreated subscription configured for $container_name/normalized/."
