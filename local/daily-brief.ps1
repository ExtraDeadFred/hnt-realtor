# Daily market brief: pull fresh data, have Claude (subscription, headless)
# write the email + FB drafts, send via Gmail. Scheduled by install-task.ps1.
#
# SMTP config comes from environment variables (SMTP_SERVER, SMTP_PORT,
# SMTP_USERNAME, SMTP_PASSWORD, SMTP_FROM_EMAIL, MAIL_TO), with local\.env
# (see .env.example) as a fallback for any that aren't set.

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

# --- config: env vars first, then local\.env ---
$dotenv = @{}
$envFile = Join-Path $PSScriptRoot ".env"
if (Test-Path $envFile) {
    Get-Content $envFile | Where-Object { $_ -match "^\s*([^#=]+)=(.*)$" } | ForEach-Object {
        $dotenv[$Matches[1].Trim()] = $Matches[2].Trim()
    }
}
function Get-Conf($name, $default) {
    $v = [System.Environment]::GetEnvironmentVariable($name)
    if (-not $v) { $v = $dotenv[$name] }
    if (-not $v) { $v = $default }
    return $v
}
$smtpServer = Get-Conf "SMTP_SERVER" "smtp.gmail.com"
$smtpPort   = [int](Get-Conf "SMTP_PORT" "587")
$smtpUser   = Get-Conf "SMTP_USERNAME" $null
# Gmail shows app passwords grouped with spaces but SMTP rejects them — strip
$smtpPass   = (Get-Conf "SMTP_PASSWORD" $null) -replace '\s', ''
$fromEmail  = Get-Conf "SMTP_FROM_EMAIL" $smtpUser
$mailTo     = Get-Conf "MAIL_TO" $fromEmail
if (-not $smtpUser -or -not $smtpPass) {
    throw "SMTP_USERNAME / SMTP_PASSWORD not found in environment variables or local\.env."
}

function Send-Brief($subject, $body) {
    $msg = New-Object System.Net.Mail.MailMessage
    $msg.From = $fromEmail
    foreach ($to in ($mailTo -split "," | ForEach-Object { $_.Trim() } | Where-Object { $_ })) { $msg.To.Add($to) }
    $msg.Subject = $subject
    $msg.Body = $body
    $msg.IsBodyHtml = $true
    # Default mail encoding is ASCII — force UTF-8 so em-dashes/emoji survive
    $msg.SubjectEncoding = [System.Text.Encoding]::UTF8
    $msg.BodyEncoding = [System.Text.Encoding]::UTF8
    $smtp = New-Object System.Net.Mail.SmtpClient($smtpServer, $smtpPort)
    $smtp.EnableSsl = $true
    $smtp.Credentials = New-Object System.Net.NetworkCredential($smtpUser, $smtpPass)
    $smtp.Send($msg)
}

$today = Get-Date -Format "yyyy-MM-dd"
$outDir = Join-Path $PSScriptRoot "out"
New-Item -ItemType Directory -Force $outDir | Out-Null

# Log the whole run so a failed morning is diagnosable after the fact
try { Start-Transcript -Path (Join-Path $outDir "last-run.log") -Force -ErrorAction SilentlyContinue | Out-Null } catch {}

# From here on, any unexpected crash emails the error instead of dying silently
try {

# --- fresh data from the overnight Actions run ---
# Never fatal: git chatters on stderr (which PS 5.1 can escalate to a crash)
# and OneDrive can transiently lock .git — stale data still beats no email.
$ErrorActionPreference = "Continue"
git pull --ff-only *> $null
$pullExit = $LASTEXITCODE
$ErrorActionPreference = "Stop"
if ($pullExit -ne 0) {
    Write-Warning "git pull failed (exit $pullExit) — continuing with existing data"
}

# --- generate with Claude (headless, uses the Claude subscription) ---
$emailHtml = $null
$pulseText = $null
try {
    $prompt = "Today is $(Get-Date -Format 'dddd, MMMM d, yyyy').`n`n" +
              (Get-Content (Join-Path $PSScriptRoot "prompts\brief.md") -Raw)
    # PS 5.1: stderr redirection on a native exe throws under EAP Stop, and
    # claude warns if piped stdin is empty — pipe the prompt in via stdin.
    # Both directions of that pipe must be UTF-8, or em-dashes/quotes arrive
    # as mojibake (PS 5.1 defaults: ASCII out, OEM codepage in).
    $prevOut = $OutputEncoding
    $prevConsole = [Console]::OutputEncoding
    $OutputEncoding = [System.Text.Encoding]::UTF8
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    $ErrorActionPreference = "Continue"
    $raw = ($prompt | claude -p 2>$null | Out-String)
    $claudeExit = $LASTEXITCODE
    $ErrorActionPreference = "Stop"
    $OutputEncoding = $prevOut
    [Console]::OutputEncoding = $prevConsole
    if ($claudeExit -ne 0) {
        Write-Warning "claude exited with code $claudeExit"
        $raw = ""
    }
    if ($raw -match "===EMAIL_HTML===\s*([\s\S]*?)\s*===PULSE_TEXT===\s*([\s\S]*)$") {
        $emailHtml = $Matches[1] -replace '^\s*```html?\s*', '' -replace '\s*```\s*$', ''
        $pulseText = $Matches[2].Trim() -replace '^\s*```\s*', '' -replace '\s*```\s*$', ''
    }
} catch {
    $ErrorActionPreference = "Stop"
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
            $listPrice = '${0:N0}' -f $d.price
            $estValue = '${0:N0}' -f $d.predicted
            $rows += "<tr><td><a href='$($d.url)'>$($d.address), $($d.city)</a></td>" +
                     "<td>$listPrice</td><td>$estValue</td>" +
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

Send-Brief $subject $emailHtml
Write-Host "Sent '$subject' to $mailTo"

} catch {
    # Never fail silently: log it and email the error so a missing brief
    # always comes with an explanation
    $err = "Daily brief crashed at $(Get-Date): $($_ | Out-String)"
    Write-Warning $err
    $err | Out-File (Join-Path $outDir "error-$today.log") -Encoding utf8
    try {
        Send-Brief "⚠ Daily brief FAILED — $today" ("<p>The daily brief script crashed. Error:</p><pre>" +
            [System.Net.WebUtility]::HtmlEncode("$_") + "</pre><p>Details: local\out\error-$today.log and last-run.log</p>")
    } catch {
        Write-Warning "Could not send failure email: $_"
    }
    try { Stop-Transcript | Out-Null } catch {}
    exit 1
}
try { Stop-Transcript | Out-Null } catch {}
exit 0
