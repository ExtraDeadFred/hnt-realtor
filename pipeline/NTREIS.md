# NTREIS API activation — handoff guide

The adapter (`pipeline/sources/ntreis.py`) is written and wired in but
**dormant** until credentials exist. When Catherine's broker completes the
IDX authorization and NTREIS issues API access, do this:

## 1. What NTREIS will send

A packet containing some or all of:
- an API **base URL** (RESO Web API / OData endpoint)
- either an **OAuth2 client ID + secret** (plus a token URL) or a
  **static access token**
- display/compliance rules for showing listings on the website

## 2. Configure

- In `pipeline/config.yaml` under `ntreis:` fill in `base_url` (and
  `token_url` if they use OAuth2 rather than a static token).
- Add the secrets:
  - **GitHub Actions** (repo → Settings → Secrets → Actions):
    `NTREIS_ACCESS_TOKEN` — or — `NTREIS_CLIENT_ID` + `NTREIS_CLIENT_SECRET`
  - Also add the same name(s) to the `env:` block of the "Scrape and analyze"
    step in `.github/workflows/market-data.yml` (currently only passes
    `FIRECRAWL_API_KEY`).

## 3. Smoke test (locally, before trusting the daily run)

```powershell
$env:NTREIS_ACCESS_TOKEN = "..."   # or CLIENT_ID/SECRET
python pipeline\sources\ntreis.py
```

Expected: a few hundred active/pending listings printed with sane prices and
addresses. If field names look off (empty addresses, null prices), NTREIS's
packet will show their exact RESO field names — adjust `_to_listing` only.

Then a full pipeline run: `python pipeline\run.py` — it will prefer NTREIS
automatically (`scrape_all` checks `ntreis.enabled`) and fall back to the
Firecrawl scrapers on any failure.

## 4. What activates automatically

- NTREIS becomes the **primary listing source**; Zillow/Realtor scrapers stay
  as fallback (no code change needed).
- MLS records carry `subdivision` and `year_built` → comp quality and the
  price model improve immediately.
- `fetch_solds()` pulls closed sales into the model's ground truth **if** the
  feed includes Closed status. Plain IDX feeds often don't — if it returns
  nothing, keep dropping monthly CSV exports in `ingest/mls-solds/` (that
  path stays fully supported either way).

## 5. Follow-ups once stable (not automatic)

- **Public listing browser**: with licensed IDX data, market.html can show
  actual listings. Mind the display rules in NTREIS's packet (attribution
  line, update frequency, which fields may be shown). `url` is left null by
  the adapter on purpose — IDX rules generally require linking to your own
  detail pages, not to Zillow.
- **Photos**: the RESO `Media` resource has them; `photo_url` is left null
  until the display license is confirmed.
- Retire `ingest/my-listings.csv`: her own listings can be found in the feed
  by `ListAgentMlsId`/`ListAgentFullName` instead of a manual export.
