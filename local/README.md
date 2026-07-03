# Local daily brief (runs on Freddie's PC)

Uses the Claude Code subscription (`claude -p`, no API key) to write the
daily deal-alert email + Facebook drafts, and sends it from Gmail.

## One-time setup
1. Copy `.env.example` to `.env` and fill in the Gmail app password.
2. Test it: `powershell -File daily-brief.ps1` (set MAIL_TO to yourself first).
3. Schedule it: `powershell -File install-task.ps1` (7:00 AM daily).

## Weekly pulse approval
On Mondays the brief includes a website "Market Pulse" draft, staged in
`data/pulse-pending.json`. When Catherine approves the wording, run
`approve-pulse.ps1` to publish it to market.html.
