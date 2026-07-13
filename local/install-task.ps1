# Registers the daily brief as a Windows Scheduled Task (4:30 AM daily,
# hidden window). Re-run any time to update: .\install-task.ps1

$script = Join-Path $PSScriptRoot "daily-brief.ps1"
$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$script`""
$trigger = New-ScheduledTaskTrigger -Daily -At 4:30AM
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -WakeToRun `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30) -Hidden
Register-ScheduledTask -TaskName "HNT Realtor Daily Brief" -Action $action `
    -Trigger $trigger -Settings $settings -Force
Write-Host "Task 'HNT Realtor Daily Brief' registered for 4:30 AM daily (hidden window)."
Write-Host "(-StartWhenAvailable + -WakeToRun: wakes the PC at 4:30, or runs"
Write-Host " hidden later if it was fully off — no console window either way.)"
