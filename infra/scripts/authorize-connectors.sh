#!/usr/bin/env sh

set -eu

./infra/scripts/authorize-dataverse.sh

outlook_enabled=$(azd env get-value ENABLE_OUTLOOK_FALLBACK 2>/dev/null || true)
if [ "$outlook_enabled" = "true" ]; then
    ./infra/scripts/authorize-outlook.sh
else
    echo "Office 365 Outlook fallback is disabled."
fi
