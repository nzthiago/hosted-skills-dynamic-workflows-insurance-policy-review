$ErrorActionPreference = 'Stop'

& ./infra/scripts/authorize-dataverse.ps1

$outlookEnabled = azd env get-value ENABLE_OUTLOOK_FALLBACK 2>$null
if ($outlookEnabled -eq 'true') {
    & ./infra/scripts/authorize-outlook.ps1
}
else {
    Write-Host "Office 365 Outlook fallback is disabled."
}
