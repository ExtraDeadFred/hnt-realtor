# Registers the daily brief as a Windows Scheduled Task (7:00 AM daily).
# Run once from an elevated or normal PowerShell: .\install-task.ps1

$script = Join-Path $PSScriptRoot "daily-brief.ps1"
$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$script`""
$trigger = New-ScheduledTaskTrigger -Daily -At 7:00AM
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -WakeToRun `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
Register-ScheduledTask -TaskName "HNT Realtor Daily Brief" -Action $action `
    -Trigger $trigger -Settings $settings -Force
Write-Host "Task 'HNT Realtor Daily Brief' registered for 7:00 AM daily."
Write-Host "(-StartWhenAvailable runs it late if the PC was asleep at 7.)"
