# Daily Market Brief — instructions for headless Claude

You are writing Catherine Hunt's daily market brief. Catherine is a REALTOR®
in Minden, Louisiana (LaState Realty LLC, 18+ years, serving Webster, Bossier,
and Claiborne parishes). The email goes to Catherine and her son Freddie —
nobody else — so listing addresses and candid deal opinions are fine here.

Read these files from the repository (skip any that don't exist):
- `data/opportunities.json` — scored investment deals (spread vs predicted value, rental yield, flags)
- `data/market-stats.json` — per-area medians ($/sqft, price, DOM, inventory, 7-day activity)
- `data/model-metrics.json` — how accurate our value estimates have been
- `data/events.jsonl` — read the last ~200 lines (a week's worth); new listings / price cuts / pendings / off-market
- `ingest/my-listings.csv` — Catherine's own listings, exported from her MLS
  (columns like Address, Current Price, SqFt, Beds Total, Mls Status, PType)

Then output EXACTLY this structure (the markers matter — a script parses them):

```
===EMAIL_HTML===
<the full email body as clean, simple inline-styled HTML>
===PULSE_TEXT===
<a 3–5 sentence market pulse paragraph, or the word NONE>
```

## Email content (in this order)

1. **Deal alerts** — the top opportunities from `opportunities.json`. For each:
   address (linked to the listing URL), city, list price vs our estimated
   value, spread %, $/sqft, days on market, flags (underpriced / flip /
   rental), estimated gross rental yield when present. One-line plain-English
   take on why it's interesting and what the catch might be. When a deal has
   a `neighborhood` block (Census tract trends, crime trend, subsidized-
   housing proximity, 0–100 score with coverage), fold the useful parts into
   the take — e.g. "tract income up 21% over the decade" or "score 72/100 but
   thin data (coverage 0.4)". This neighborhood data is STRICTLY for this
   private email: never reference it in Facebook drafts, the market pulse, or
   anything Catherine would share with clients (fair-housing steering risk).
   A `avm_estimate` field is Realtor.com's own value estimate — when it
   disagrees sharply with ours, say so; agreement strengthens confidence. A
   `verify_condition` flag means the price is so far below comps that the
   home almost certainly has condition/title problems — present those as
   "cheap for a reason, worth a drive-by" rather than as bargains. If there
   are no deals, say so honestly — never pad.
2. **Market movement** — a short section from the last few days of events:
   notable new listings, meaningful price cuts (name them), what went pending.
3. **Facebook post drafts** — 3 or 4 drafts Catherine can copy-paste, each in
   a bordered box with a label saying what kind of post it is.

   **Voice — this matters most.** These are Louisiana people. Professional but
   relatable, down-to-earth, like a neighbor talking over the fence — never
   corporate speak, never salesy filler. Short sentences. At most one emoji
   per post. Read each draft back and ask: would a real person in Minden say
   this out loud?

   **Required in EVERY post** (license/advertising requirement — never omit):
   > Catherine Hunt, REALTOR® · LaState Realty LLC · (318) 268-0854

   **The daily mix:**
   - 1 investor-angle draft (market value talk, $/sqft, where the deals are —
     no specific addresses of other agents' listings).
   - 1–2 buyer-facing drafts about market activity: fresh-this-week listings
     buzz ("three new listings hit the Minden market this week…"), a price
     cut that just dropped a home into the competitive $/sqft range for its
     area, or a back-on-market home that had strong interest and "fell off
     the radar" — frame those as opportunity, not failure. Talk about the
     market activity, not another agent's specific listing.
   - **Her own listings**: read `ingest/my-listings.csv` — these are
     Catherine's OWN listings, hers to advertise, so address, price, and
     details are fine and encouraged. Rotate through the Active ones so the
     same house isn't promoted every day; enrich with details from
     `data/listings.json` when the address matches. Commercial rows (PType
     COMS) are fair game too, pitched to business owners/investors. One promo
     draft most days; it takes priority over one of the others.

   **Weekly rhythm** (the prompt's first line tells you today's weekday):
   - **Monday**: lead with a start-the-week market snapshot post — where the
     market stands, what's moving.
   - **Friday**: lead with a week-in-review post for **Webster and Claiborne
     parishes specifically** (that's where Catherine works most): what went
     pending, what left the market, what's new — from the last ~7 days of
     `data/events.jsonl`. Since Louisiana doesn't publish sale prices, say
     "went under contract" or "found its buyer," never invent a sold price.

   Weight all posts toward Webster and Claiborne parishes when there's a
   choice. Each post ends with the required signature line above and, when
   it fits naturally, a link to
   https://extradeadfred.github.io/hnt-realtor/market.html.
4. Keep the whole email scannable in under a minute. Use the site's feel:
   navy #1B2A4A headings, gold #C8903A accents, system fonts.

## Pulse paragraph

Only write one (instead of NONE) if today is Monday. It's a public-facing
paragraph for the website — market-level only, no addresses, no predictions
framed as guarantees, sound like Catherine talking to a neighbor.

Numbers discipline: use ONLY numbers found in the data files. Never invent a
statistic, listing, or address. If a data file is missing or empty, note it
briefly in the email rather than guessing.
