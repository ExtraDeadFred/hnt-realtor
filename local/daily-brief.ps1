# Daily market brief: pull fresh data, have Claude (subscription, headless)
# write the email + FB drafts, send via Gmail. Scheduled by install-task.ps1.
#
# Requires local\.env (see .env.example): GMAIL_USER, GMAIL_APP_PASSWORD, MAIL_TO

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

# --- load .env ---
$envFile = Join-Path $PSScriptRoot ".env"
if (-not (Test-Path $envFile)) { throw "Missing local\.env — copy .env.example and fill it in." }
$conf = @{}
Get-Content $envFile | Where-Object { $_ -match "^\s*([^#=]+)=(.*)$" } | ForEach-Object {
    $conf[$Matches[1].Trim()] = $Matches[2].Trim()
}

# --- fresh data from the overnight Actions run ---
git pull --ff-only 2>&1 | Out-Null

$today = Get-Date -Format "yyyy-MM-dd"
$outDir = Join-Path $PSScriptRoot "out"
New-Item -ItemType Directory -Force $outDir | Out-Null

# --- generate with Claude (headless, uses the Claude subscription) ---
$emailHtml = $null
$pulseText = $null
try {
    $prompt = Get-Content (Join-Path $PSScriptRoot "prompts\brief.md") -Raw
    $raw = claude -p $prompt 2>$null | Out-String
    if ($raw -match "===EMAIL_HTML===\s*([\s\S]*?)\s*===PULSE_TEXT===\s*([\s\S]*)$") {
        $emailHtml = $Matches[1] -replace '^\s*```html?\s*', '' -replace '\s*```\s*$', ''
        $pulseText = $Matches[2].Trim() -replace '^\s*```\s*', '' -replace '\s*```\s*$', ''
    }
} catch {
    Write-Warning "claude -p failed: $_"
}

# --- template fallback so the alert never silently drops ---
$opps = $null
if (Test-Path "data\opportunities.json") {
    $opps = Get-Content "data\opportunities.json" -Raw | ConvertFrom-Json
}
if (-not $emailHtml) {
    $rows = ""
    if ($opps) {
        foreach ($d in $opps.deals) {
            $rows += "<tr><td><a href='$($d.url)'>$($d.address), $($d.city)</a></td>" +
                     "<td>`$$("{0:N0}" -f $d.price)</td><td>`$$("{0:N0}" -f $d.predicted)</td>" +
                     "<td>$($d.spread_pct)%</td><td>$($d.days_on_market)</td><td>$($d.flags -join ', ')</td></tr>"
        }
    }
    $emailHtml = "<p>(Claude was unavailable this morning — raw numbers below.)</p>" +
                 "<table border='1' cellpadding='6' cellspacing='0'>" +
                 "<tr><th>Listing</th><th>List</th><th>Est. value</th><th>Spread</th><th>DOM</th><th>Flags</th></tr>" +
                 $rows + "</table>"
}
$emailHtml | Out-File (Join-Path $outDir "brief-$today.html") -Encoding utf8

# --- stage Monday pulse for approval (publish with approve-pulse.ps1) ---
if ($pulseText -and $pulseText -ne "NONE") {
    @{ date = $today; text = $pulseText } | ConvertTo-Json |
        Out-File "data\pulse-pending.json" -Encoding utf8
}

# --- send via Gmail SMTP ---
$subject = "Market Brief — $today"
if ($opps -and $opps.high_opportunity) { $subject = "🔥 High-Opportunity Alert — $today" }

$msg = New-Object System.Net.Mail.MailMessage
$msg.From = $conf.GMAIL_USER
foreach ($to in $conf.MAIL_TO -split ",") { $msg.To.Add($to.Trim()) }
$msg.Subject = $subject
$msg.Body = $emailHtml
$msg.IsBodyHtml = $true
$smtp = New-Object System.Net.Mail.SmtpClient("smtp.gmail.com", 587)
$smtp.EnableSsl = $true
$smtp.Credentials = New-Object System.Net.NetworkCredential($conf.GMAIL_USER, $conf.GMAIL_APP_PASSWORD)
$smtp.Send($msg)
Write-Host "Sent '$subject' to $($conf.MAIL_TO)"
