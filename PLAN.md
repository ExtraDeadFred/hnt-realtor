# NW Louisiana Market Intelligence Pipeline + Website Upgrades

## Context

Catherine Hunt (user's mom, Realtor in Minden/NW Louisiana) pays ~$150/mo to a service mainly for MLS-fed website hosting. The repo already contains a superior static site ([index.html](index.html), [styles.css](styles.css), [script.js](script.js)) ready for GitHub Pages. Goal: build an automated market-intelligence system using the user's Firecrawl API that (1) scrapes area listings daily, (2) computes $/sqft, age, DOM analytics and a price-prediction model with an accuracy feedback loop, (3) surfaces investment opportunities (flip/rental) via email with listing links, (4) drafts copy-paste-ready Facebook posts emailed for her approval (expert in the loop), and (5) powers an interactive market section on the website — all designed so an MLS/IDX API can later replace the scraper without rework.

**Decisions made with user:**
- Pipeline runs on **GitHub Actions** (cron), committing JSON to the repo the static site reads.
- Narrative generation uses the user's **Claude subscription via `claude -p` headless** in a Windows Task Scheduler job on his PC — no Anthropic API key.
- Emails sent from the **user's Gmail (SMTP app password)**, from the PC task, to mom + user.
- Sold-price ground truth: **design a CSV drop-folder ingest** for future MLS exports; rely on scraped signals (off-market transitions) as proxy meanwhile. Parish Clerk of Court conveyance records exist but are behind paid per-parish portals — treat as a possible later adapter, not automated now.

**Key constraints discovered:**
- Louisiana is non-disclosure: scraped "sold" prices are unreliable → model scoring uses last-list-price proxy until MLS CSVs arrive.
- Legal/ToS: republishing scraped Zillow/Realtor listing data publicly is risky (their ToS + MLS display rules). **Public site shows aggregate stats + charts only; listing-level deal data goes to the private emails.** Adapter design makes the public listing browser easy to add once IDX access exists.
- Site forms currently fake success ([script.js:159](script.js#L159)) — leads go nowhere. Highest-value quick fix.

---

## Architecture

```
GitHub Actions (daily cron ~5am CT)
  scrape (Firecrawl) → normalize/dedupe → diff vs yesterday → analyze/model → commit data/*.json
        │
        ├── GitHub Pages site (index.html + new market.html) reads data/*.json → charts & stats
        │
PC Task Scheduler (daily ~7am CT)
  git pull → claude -p (subscription) reads data/ → deal-alert email + FB post drafts
          → send via Gmail SMTP to mom + user
```

### New repo layout
```
pipeline/
  config.yaml            # target cities, thresholds, email recipients
  sources/zillow.py      # Firecrawl adapter → List[Listing]
  sources/realtor.py     # Firecrawl adapter → List[Listing]
  sources/base.py        # Listing dataclass + adapter interface (IDX plugs in here later)
  normalize.py           # address-keyed dedupe/merge across sources
  diff.py                # new / price-cut / pending / off-market / back-on-market
  analyze.py             # market stats, comps model, deal scoring, accuracy metrics
  ingest_mls.py          # reads ingest/mls-solds/*.csv → ground-truth sold table
  run.py                 # orchestrator
data/
  listings.json          # normalized active listings (private-ish: in repo but not rendered publicly)
  snapshots/YYYY-MM-DD.json.gz
  market-stats.json      # per-city medians, $/sqft, DOM, inventory, MoM trends  (public)
  opportunities.json     # scored deals for the email
  predictions.json       # predicted value per active listing
  model-metrics.json     # rolling MAE/MAPE, predicted-vs-actual log       (public accuracy stat)
ingest/mls-solds/        # CSV drop folder (mom's future MLS exports)
.github/workflows/market-data.yml
local/                   # PC-side, gitignored secrets
  daily-brief.ps1        # git pull → claude -p → send email
  prompts/brief.md       # instructions for headless Claude
market.html              # new interactive market dashboard page
```

---

## Phase 1 — Website quick wins (do first, independent of pipeline)

1. **Wire the forms** (valuation + contact) to a real endpoint — Formspree or Web3Forms free tier posting to her email. Replace the `setTimeout` fake in [script.js:133-201](script.js#L133-L201) with a real `fetch` POST, keep the existing success UI.
2. **Replace runtime Unsplash calls** ([script.js:216-253](script.js#L216-L253)): the API key is exposed client-side and demo keys allow 50 req/hr — the cards will randomly break. One-time: download 6 curated photos (or use her real local photos), commit to `assets/`, reference statically. Delete the key.
3. **Fix dead search links**: quick-tags and search button point at `forsalebyhunt.com/quick-search` (the paid service she's leaving). Point them at Zillow/Realtor.com pre-filtered searches for now; swap to IDX later.
4. Note (no action yet): when ready to cancel the $150/mo service, point the `forsalebyhunt.com` DNS at GitHub Pages (CNAME file + A records). **This matters for SEO too** — the existing domain has years of indexing/backlinks; moving it to the new site inherits that authority rather than starting from zero on a `github.io` URL.

## Phase 1b — SEO & discoverability (make Google recommend the site)

Goal: rank for "realtor Minden LA", "homes for sale Minden", parish/neighborhood queries, and Barksdale relocation searches.

1. **Technical SEO**
   - `sitemap.xml` (auto-regenerated by the pipeline when pages change) + `robots.txt`; canonical tags on every page.
   - JSON-LD structured data: `RealEstateAgent` (name, phone, address, areaServed, sameAs → Facebook/Zillow/Instagram profiles), `FAQPage` on the existing FAQ section (rich-result eligible), `BreadcrumbList` on subpages.
   - Open Graph + Twitter Card tags with a real preview image so shared links (especially her Facebook posts linking back) render attractively.
   - The `google-site-verification` meta already exists ([index.html:8](index.html#L8)) — register the property in **Google Search Console**, submit the sitemap, and monitor indexing/queries. Also submit to Bing Webmaster Tools.
   - Performance: static site is already fast; keep committed images compressed/responsive (`loading="lazy"`, width/height attrs) to hold strong Core Web Vitals — a ranking factor.
2. **Local SEO**
   - Create/claim her **Google Business Profile** (biggest lever for "realtor near me" map-pack results) and link it to the site; keep NAP (name/address/phone) identical everywhere on-site and on Zillow/Realtor/Facebook profiles.
   - Per-area landing pages (`minden.html`, `haughton-bossier.html`, `lake-claiborne.html`, …) generated from a shared template: unique intro copy + that area's live stats from `data/market-stats.json`. These target the long-tail searches ("homes for sale Sibley LA", "Lake Claiborne waterfront homes") that big portals under-serve — the Lake Claiborne page especially, since she sells heavily there and lake-specific queries have thin competition.
3. **Content flywheel from the pipeline** — this is the differentiator: the daily pipeline gives the site **fresh, unique, local data no competitor publishes**. Google rewards exactly this.
   - `market.html` and area pages update daily with real numbers → constant freshness signals.
   - Weekly "Market Pulse" posts (the approved narratives) accumulate as dated, indexable pages — an automatic hyper-local blog.
   - Her Facebook posts (from the drafts) should always include a link back to the relevant area page → social signals + referral traffic + backlinks.
4. **Crawlability of data-driven content**: charts render client-side, but the key stats (medians, $/sqft, DOM per city) must also exist as **static HTML text** — have the GitHub Actions pipeline inject the latest numbers into the HTML at commit time (simple placeholder replacement) so bots see the numbers without executing JS.

## Phase 2 — Scraper + data pipeline (GitHub Actions)

1. **Listing schema** (`sources/base.py`): address, city, parish, zip, price, beds, baths, sqft, lot_size, year_built, status, days_on_market, url, photo_url, lat/lng, source, scraped_at. Every source adapter returns this — the IDX/MLS adapter later implements the same interface.
2. **Firecrawl adapters** for Zillow and Realtor.com search-result pages per target area, config-driven in `pipeline/config.yaml`:
   - **Webster Parish**: Minden, Sibley, Dubberly, Doyline, Heflin
   - **Bossier Parish** (hot spot): Haughton, Elm Grove, Bossier City, Benton
   - **Claiborne Parish** (hot spot — Lake Claiborne): Homer, Athens, Haynesville, plus a dedicated Lake Claiborne waterfront search (Zillow/Realtor lake-area queries), tagged `waterfront` so lake properties get their own stats cohort, area page, and deal scoring (waterfront comps only compare against waterfront comps). Use Firecrawl's extract/JSON-schema mode; paginate; be gentle (daily, one pass). Realtor.com is the fallback when Zillow blocks, and cross-source merge improves field coverage.
3. **Normalize + dedupe** by canonicalized address; merge fields preferring the fresher/more complete source.
4. **Diff engine**: compare to yesterday's snapshot → events: `new`, `price_cut` (amount/%), `pending`, `off_market` (sold proxy: record last list price + date), `back_on_market`. Append to an events log.
5. **Workflow** `.github/workflows/market-data.yml`: daily cron + `workflow_dispatch`; `FIRECRAWL_API_KEY` in repo secrets; runs `pipeline/run.py`; commits changed `data/` files with `[skip ci]`.

## Phase 3 — Analytics, model, and feedback loop

1. **Market stats** (`market-stats.json`): per city — median list price, median $/sqft, $/sqft by decade-built cohort, median DOM, active inventory, new/pending/price-cut counts this week, month-over-month deltas.
2. **Price model** (start simple, in `analyze.py`, no ML infra): predicted value = median $/sqft of k-nearest comps (same city, ±20 yrs age, ±30% sqft, prefer pending/off-market recents) × sqft, with small adjustments. Upgrade to a scikit-learn regression once ~200+ resolved outcomes exist.
3. **Deal score** per listing: predicted-vs-list spread %, DOM percentile, cumulative price cuts, $/sqft vs cohort median, and a rental-yield estimate using **HUD Fair Market Rents** (free public data, no scraping) → flags: `flip_candidate`, `rental_candidate`, `underpriced`.
4. **Feedback loop**: when a listing goes off-market, log `(predicted, last_list_price)` as provisional outcome; when an MLS CSV lands in `ingest/mls-solds/`, `ingest_mls.py` matches by address+date and replaces proxies with true sold prices. Compute rolling MAE/MAPE into `model-metrics.json` — displayed honestly on the site ("our estimates have been within X% on average") and used to recalibrate comp weights.

## Phase 4 — Interactive market page (`market.html`)

Client-side JS fetches the repo's `data/*.json` (same origin). Load the **dataviz skill** before building charts.
- Per-city market snapshot cards with real numbers (replaces/augments the static "Market" section links in [index.html:265-350](index.html#L265-L350)).
- **$/sqft vs. year-built scatter** and trend lines per city; DOM and inventory trends over time (snapshots give the time series).
- Model accuracy stat from `model-metrics.json`.
- "Catherine's Market Pulse" — a short narrative block published from a JSON file **only after she approves it via the email flow** (the PC task writes `data/pulse-pending.json`; a one-click "approve" = user copies it to `data/pulse.json` and pushes, or she replies and the next run promotes it). Aggregates publish automatically; narrative and listing-level data do not.
- Link `index.html` nav "Market" to this page/section.

## Phase 5 — PC-side Claude briefs + Gmail emails (expert in the loop)

1. `local/daily-brief.ps1`, run by Windows Task Scheduler daily ~7am:
   - `git pull` (fresh data from the overnight Actions run)
   - Run `claude -p` headless (user's subscription) with `local/prompts/brief.md`, which instructs it to read `data/opportunities.json` + events and produce a single JSON/markdown output containing: (a) investor deal-alert section, (b) 2–3 Facebook post drafts, (c) weekly market-pulse paragraph (Mondays).
   - Python/PowerShell mailer sends via Gmail SMTP (app password stored in a gitignored `local/.env`, never in the repo) to mom + user.
   - **Fallback**: if `claude -p` fails, send a template-rendered email with the raw numbers so the alert never silently drops.
2. **Deal-alert email**: top N opportunities — address, list price, predicted value, spread %, $/sqft vs cohort median, DOM, price-cut history, flip/rental flag, estimated rent (HUD FMR), direct listing link. Threshold-triggered "🔥 high-opportunity" subject when spread exceeds config threshold.
3. **Facebook drafts**: formatted for copy-paste — hook line, listing/market details, CTA with her phone number, hashtags, link. Variants: new-listing spotlight, market-stat post ("Homes in Minden are averaging $X/sqft…"), price-cut spotlight. She reads the email, edits if needed, pastes to Facebook — she stays the expert in the loop.

## Future (designed-for, not built now)
- **IDX/MLS API adapter**: implements `sources/base.py` interface; when credentialed, becomes the primary source, scrapers become validators; public listing browser on `market.html` becomes compliant to ship.
- **Clerk of Court adapter** for parish conveyance records (acts of sale include price) if a workable portal/subscription is found.

## Verification
- Run `pipeline/run.py` locally against one city; inspect `data/listings.json` and `market-stats.json` for sane values (spot-check 3 listings against Zillow by hand).
- Trigger the Actions workflow via `workflow_dispatch`; confirm the commit and that Pages serves the JSON.
- Serve the site locally (`python -m http.server`), open `market.html`, verify charts render from real data and the page works on a phone-width viewport.
- Run `daily-brief.ps1` manually: confirm `claude -p` output, and that the email arrives at the user's own inbox (test recipient) correctly formatted before adding mom.
- Simulate the feedback loop: hand-craft a fake MLS CSV in `ingest/mls-solds/`, run ingest, confirm `model-metrics.json` updates.
- SEO: validate JSON-LD with Google's Rich Results Test; confirm sitemap fetches; `curl` the deployed pages and grep for the injected stat numbers (bot-visible without JS); confirm Search Console shows the sitemap accepted and pages indexed over the following days.

## Suggested build order
Phase 1 (forms + photos + links) → Phase 2 scraper MVP for Minden only → expand to all Webster/Bossier/Claiborne areas incl. Lake Claiborne waterfront → Phase 3 analytics → Phase 4 market page → Phase 5 emails. Each phase ships something usable on its own.

**First implementation step**: copy this plan into the repo as `PLAN.md` (the working document we track progress against as we work through it).
