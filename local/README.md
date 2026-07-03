# Local daily brief (runs on Freddie's PC)

Uses the Claude Code subscription (`claude -p`, no API key) to write the
daily deal-alert email + Facebook drafts, and sends it from Gmail.

## One-time setup
1. Set the SMTP_* Windows environment variables (User scope):
   `SMTP_SERVER`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD` (Gmail app
   password), `SMTP_FROM_EMAIL`, and optionally `MAIL_TO` (comma-separated;
   defaults to SMTP_FROM_EMAIL). Alternatively put `NAME=value` lines in a
   `local\.env` file (gitignored) — env vars win over the file for any name
   set in both.
2. Test it: `powershell -File daily-brief.ps1` (leave MAIL_TO unset so the
   test goes only to yourself first).
3. Schedule it: `powershell -File install-task.ps1` (7:00 AM daily).

## Weekly pulse approval
On Mondays the brief includes a website "Market Pulse" draft, staged in
`data/pulse-pending.json`. When Catherine approves the wording, run
`approve-pulse.ps1` to publish it to market.html.
