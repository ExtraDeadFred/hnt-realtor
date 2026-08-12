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

# A later catch-up run must not re-send a brief that already went out well.
$okMarker = Join-Path $outDir "ok-$today.marker"
if ((Test-Path $okMarker) -and -not $env:FORCE_BRIEF) {
    Write-Host "Brief already sent successfully today — nothing to do."
    try { Stop-Transcript | Out-Null } catch {}
    exit 0
}

# --- fresh data from the overnight Actions run ---
# Never fatal: git chatters on stderr (which PS 5.1 can escalate to a crash)
# and OneDrive can transiently lock .git — stale data still beats no email.
$ErrorActionPreference = "Continue"
# local test runs dirty the tracked enrichment cache; it's derived state —
# reset it so it can't block the pull
git checkout -- data/enrichment_cache.db *> $null
git pull --ff-only *> $null
$pullExit = $LASTEXITCODE
$ErrorActionPreference = "Stop"
if ($pullExit -ne 0) {
    Write-Warning "git pull failed (exit $pullExit) — continuing with existing data"
}

# --- generate with Claude (headless, uses the Claude subscription) ---
# Pinned to Sonnet: fully capable of writing the brief, and its usage limits
# are far higher than Opus, so this 4:30am job won't hit a cap because of
# heavy interactive Claude use during the day (the cause of the fallback
# emails on 07-21/07-22). stderr is logged, not discarded, so any future
# failure says WHY. One retry absorbs transient blips before falling back.
$emailHtml = $null
$pulseText = $null
$stderrLog = Join-Path $outDir "claude-stderr-$today.log"
$prompt = "Today is $(Get-Date -Format 'dddd, MMMM d, yyyy').`n`n" +
          (Get-Content (Join-Path $PSScriptRoot "prompts\brief.md") -Raw)

# Backoff between attempts. A usage-limit rejection returns instantly and is
# still there 60s later, so the last gap is long enough to outlast a short cap.
$backoff = @(60, 420)
foreach ($attempt in 1..3) {
    try {
        # PS 5.1: pipe prompt via stdin (claude warns on empty stdin); force
        # UTF-8 both directions or em-dashes/quotes arrive as mojibake.
        $prevOut = $OutputEncoding
        $prevConsole = [Console]::OutputEncoding
        $OutputEncoding = [System.Text.Encoding]::UTF8
        [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
        $ErrorActionPreference = "Continue"
        $raw = ($prompt | claude -p --model sonnet 2>$stderrLog | Out-String)
        $claudeExit = $LASTEXITCODE
        $ErrorActionPreference = "Stop"
        $OutputEncoding = $prevOut
        [Console]::OutputEncoding = $prevConsole
        if ($claudeExit -ne 0) {
            # The CLI reports usage limits and similar refusals on STDOUT, not
            # stderr, so log both — otherwise a failure is undiagnosable.
            $why = (Get-Content $stderrLog -Raw -ErrorAction SilentlyContinue)
            $said = if ($raw) { $raw.Trim() } else { "(no stdout)" }
            if ($said.Length -gt 600) { $said = $said.Substring(0, 600) + "..." }
            Write-Warning "claude attempt $attempt exited $claudeExit`n  stderr: $why`n  stdout: $said"
            "[attempt $attempt] exit $claudeExit`nstderr: $why`nstdout: $said`n" |
                Add-Content $stderrLog -Encoding utf8
        }
        elseif ($raw -match "===EMAIL_HTML===\s*([\s\S]*?)\s*===PULSE_TEXT===\s*([\s\S]*)$") {
            $emailHtml = $Matches[1] -replace '^\s*```html?\s*', '' -replace '\s*```\s*$', ''
            $pulseText = $Matches[2].Trim() -replace '^\s*```\s*', '' -replace '\s*```\s*$', ''
            break
        }
        else {
            Write-Warning "claude attempt $attempt returned output without the expected markers"
        }
    } catch {
        $ErrorActionPreference = "Stop"
        Write-Warning "claude attempt $attempt threw: $_"
    }
    if ($attempt -lt 3) { Start-Sleep -Seconds $backoff[$attempt - 1] }
}

# --- template fallback so the alert never silently drops ---
$opps = $null
if (Test-Path "data\opportunities.json") {
    $opps = Get-Content "data\opportunities.json" -Raw | ConvertFrom-Json
}
$isFallback = -not $emailHtml
if ($isFallback) {
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
    $emailHtml = "<p><b>Claude was unavailable this morning after a retry — raw numbers below.</b> " +
                 "See local\out\claude-stderr-$today.log for the reason.</p>" +
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
if ($isFallback) { $subject = "[raw data] $subject" }

Send-Brief $subject $emailHtml
Write-Host "Sent '$subject' to $mailTo"
# Only a real Claude-written brief counts as done; a fallback leaves the
# marker absent so the later catch-up run tries again.
if (-not $isFallback) { Get-Date | Out-File $okMarker -Encoding utf8 }

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
