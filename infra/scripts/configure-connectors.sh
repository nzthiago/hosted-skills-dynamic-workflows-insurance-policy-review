#!/usr/bin/env sh

set -eu

outlook_enabled=$(azd env get-value ENABLE_OUTLOOK_FALLBACK 2>/dev/null || true)
./infra/scripts/disable-outlook-trigger-if-needed.sh

./infra/scripts/configure-dataverse-trigger.sh

if [ "$outlook_enabled" = "true" ]; then
    ./infra/scripts/configure-outlook-trigger.sh
else
    echo "Office 365 Outlook fallback trigger is disabled."
fi
