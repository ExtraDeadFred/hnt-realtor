"""Detect day-over-day listing events: new, price_cut, pending, off_market,
back_on_market."""

from datetime import date


def compute_events(previous, current):
    """previous/current: lists of normalized listings (with `key`).
    Returns a list of event dicts."""
    today = date.today().isoformat()
    prev = {l["key"]: l for l in previous}
    curr = {l["key"]: l for l in current}
    events = []

    def ev(kind, listing, **extra):
        events.append({
            "date": today, "event": kind, "key": listing["key"],
            "address": listing["address"], "city": listing["city"],
            "parish": listing["parish"], "price": listing.get("price"),
            "url": listing.get("url"), **extra,
        })

    for key, l in curr.items():
        old = prev.get(key)
        if old is None:
            ev("new", l)
        else:
            if l.get("price") and old.get("price") and l["price"] < old["price"]:
                ev("price_cut", l, old_price=old["price"],
                   cut_pct=round(100 * (old["price"] - l["price"]) / old["price"], 1))
            if l["status"] in ("pending", "contingent") and old["status"] not in ("pending", "contingent"):
                ev("pending", l)
            if l["status"] == "active" and old["status"] in ("pending", "contingent"):
                ev("back_on_market", l)

    # Off-market detection is skipped when today's scrape looks like a partial
    # failure — otherwise a bad scrape day floods the log with fake solds.
    if previous and len(current) >= 0.5 * len(previous):
        for key, old in prev.items():
            if key not in curr:
                ev("off_market", old, last_price=old.get("price"))

    return events
