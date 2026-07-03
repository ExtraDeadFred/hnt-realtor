# Publishes the pending Market Pulse to the website after Catherine approves
# the draft in the email. Run: .\approve-pulse.ps1

$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo
if (-not (Test-Path "data\pulse-pending.json")) { throw "No pending pulse to approve." }
Copy-Item "data\pulse-pending.json" "data\pulse.json" -Force
git add data/pulse.json
git commit -m "Publish approved Market Pulse"
git push
Write-Host "Pulse published — it will appear on market.html."
