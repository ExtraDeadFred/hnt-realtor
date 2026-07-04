"""Daily pipeline orchestrator.

  python pipeline/run.py            # scrape via Firecrawl (needs FIRECRAWL_API_KEY)
  FIXTURE_LISTINGS=path python pipeline/run.py   # skip scraping, use fixture JSON

Reads/writes the data/ directory; also injects the latest stats into HTML
elements marked data-stat="Cohort:field" so crawlers see numbers without JS.
"""

import gzip
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import yaml

import analyze
import diff
import ingest_mls
import normalize

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def load_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(path, obj):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(obj, indent=1), encoding="utf-8")


def scrape_all(cfg):
    from sources import realtor, zillow
    listings = []
    for area in cfg["areas"]:
        for mod, name in ((zillow, "zillow"), (realtor, "realtor")):
            try:
                found = mod.fetch(area, cfg)
                print(f"  {name} / {area['city']}{' (waterfront)' if area.get('tags') else ''}: {len(found)}")
                listings.extend(found)
            except Exception as e:
                print(f"  {name} / {area['city']}: FAILED — {e}")
    return listings


def fmt_stat(field, value):
    if value is None:
        return "—"
    if field == "median_price":
        return f"${value:,.0f}"
    if field == "median_ppsf":
        return f"${value:,.0f}/sqft"
    if field == "median_dom":
        return f"{value} days"
    return f"{value}"


def inject_stats(stats, html_files):
    """Replace text inside <... data-stat="Cohort:field" ...>text</...>."""
    pattern = re.compile(r'(<[^>]*\bdata-stat="([^":]+):([^"]+)"[^>]*>)[^<]*(</)')

    def sub(m):
        cohort = stats["cohorts"].get(m.group(2), {})
        return m.group(1) + fmt_stat(m.group(3), cohort.get(m.group(3))) + m.group(4)

    for hf in html_files:
        path = ROOT / hf
        if not path.exists():
            continue
        html = path.read_text(encoding="utf-8")
        new = pattern.sub(sub, html)
        new = re.sub(r'(<[^>]*\bdata-stat-updated\b[^>]*>)[^<]*(</)',
                     rf'\g<1>{stats["updated"]}\g<2>', new)
        if new != html:
            path.write_text(new, encoding="utf-8")
            print(f"  injected stats into {hf}")


def main():
    cfg = yaml.safe_load((ROOT / "pipeline" / "config.yaml").read_text(encoding="utf-8"))
    previous = load_json(DATA / "listings.json", [])

    fixture = os.environ.get("FIXTURE_LISTINGS")
    if fixture:
        raw = json.loads(Path(fixture).read_text(encoding="utf-8"))
        print(f"fixture: {len(raw)} raw listings from {fixture}")
    else:
        raw = scrape_all(cfg)
    if not raw:
        print("No listings scraped — keeping yesterday's data untouched.")
        sys.exit(1)

    current = normalize.merge(raw)
    print(f"{len(raw)} raw -> {len(current)} unique listings")

    events = diff.compute_events(previous, current)
    print(f"{len(events)} events: " + ", ".join(
        f"{k}={sum(1 for e in events if e['event'] == k)}"
        for k in ("new", "price_cut", "pending", "off_market", "back_on_market")))

    solds = ingest_mls.load_solds(ROOT / "ingest" / "mls-solds")
    if solds:
        print(f"{len(solds)} MLS sold comps loaded")

    # Outcomes are frozen against the predictions the model made while the
    # listing was still on the market (yesterday's predictions file).
    prev_predictions = load_json(DATA / "predictions.json", {}).get("predictions", {})
    outcomes = load_json(DATA / "outcomes.json", [])
    outcomes = analyze.update_outcomes(outcomes, events, prev_predictions, previous)
    outcomes = ingest_mls.apply_to_outcomes(outcomes, solds)

    predictions = analyze.predict_prices(current, solds, cfg)
    stats = analyze.market_stats(current, load_events() + events)
    deals = analyze.score_deals(current, predictions, cfg)
    metrics = analyze.model_metrics(outcomes)
    metrics["backtest"] = analyze.backtest(solds, cfg)

    save_json(DATA / "listings.json", current)
    save_json(DATA / "market-stats.json", stats)
    save_json(DATA / "predictions.json",
              {"updated": date.today().isoformat(), "predictions": predictions})
    save_json(DATA / "opportunities.json", deals)
    save_json(DATA / "outcomes.json", outcomes)
    save_json(DATA / "model-metrics.json", metrics)

    # Append today's cohort summary for trend charts (idempotent per day)
    history = load_json(DATA / "history.json", [])
    history = [h for h in history if h["date"] != stats["updated"]]
    history.append({"date": stats["updated"], "cohorts": {
        name: {k: c[k] for k in ("inventory", "median_price", "median_ppsf", "median_dom")}
        for name, c in stats["cohorts"].items()}})
    save_json(DATA / "history.json", history)

    with open(DATA / "events.jsonl", "a", encoding="utf-8") as f:
        for e in events:
            f.write(json.dumps(e) + "\n")

    snap = DATA / "snapshots" / f"{date.today().isoformat()}.json.gz"
    snap.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(snap, "wt", encoding="utf-8") as f:
        json.dump(current, f)

    inject_stats(stats, ["index.html", "market.html"])
    print(f"done: {len(current)} listings, {len(deals['deals'])} opportunities, "
          f"model MAPE {metrics['mape_pct']}% over {metrics['n_outcomes']} outcomes")


def load_events():
    events = []
    try:
        with open(DATA / "events.jsonl", encoding="utf-8") as f:
            events = [json.loads(line) for line in f if line.strip()]
    except FileNotFoundError:
        pass
    return events


if __name__ == "__main__":
    main()
