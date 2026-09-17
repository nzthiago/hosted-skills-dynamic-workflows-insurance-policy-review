$ErrorActionPreference = 'Stop'

$outlookEnabled = azd env get-value ENABLE_OUTLOOK_FALLBACK 2>$null
& ./infra/scripts/disable-outlook-trigger-if-needed.ps1

& ./infra/scripts/configure-dataverse-trigger.ps1

if ($outlookEnabled -eq 'true') {
    & ./infra/scripts/configure-outlook-trigger.ps1
}
else {
    Write-Host "Office 365 Outlook fallback trigger is disabled."
}
