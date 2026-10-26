"""Ingest MLS sold-comp CSV exports dropped in ingest/mls-solds/.

Column names are matched loosely so whatever the MLS export calls them works.
Minimum useful columns: address, city, sold price. Also recognized: sold date,
sqft (living area), year built, beds, baths.
"""

import csv
import re
from datetime import date, datetime
from pathlib import Path

from normalize import canon_key, classify_home_type

# A sale belongs to an outcome only if it closed around when the listing left
# the market. Listings drop off the portals ~1 day before closing; allow a
# little slack before and a long tail after for slow closings.
SALE_WINDOW_DAYS = (-30, 180)


def parse_date(s):
    """MLS exports use MM/DD/YYYY, APIs and our own files use ISO."""
    if isinstance(s, date):
        return s
    s = str(s or "")[:10]
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def sale_in_window(sold_date, left_market):
    sold, left = parse_date(sold_date), parse_date(left_market)
    if not (sold and left):
        return False
    lo, hi = SALE_WINDOW_DAYS
    return lo <= (sold - left).days <= hi

_COLUMN_ALIASES = {
    "address": ["address", "street address", "property address", "full address"],
    "city": ["city", "town"],
    "sold_price": ["sold price", "sale price", "close price", "closed price", "selling price"],
    "sold_date": ["sold date", "close date", "closing date", "sale date"],
    "sqft": ["sqft", "living area", "living sqft", "total living area", "sq ft", "heated sqft"],
    "year_built": ["year built", "yr built"],
    "subdivision": ["subdivision", "subdivision name", "neighborhood"],
    # Absent from the "Agent Single Line Sold" export; present if she builds a
    # custom export. Until then sold comps have home_type None (see analyze).
    "property_type": ["property sub type", "property type", "ptype",
                      "prop type", "style", "structure type"],
    "beds": ["beds", "bedrooms", "br", "beds total", "total beds"],
    "baths": ["baths", "bathrooms", "ba", "total baths", "bath total", "baths total"],
}


def _map_columns(header):
    mapping = {}
    for i, col in enumerate(header):
        c = col.strip().lower()
        for field, aliases in _COLUMN_ALIASES.items():
            if field not in mapping and c in aliases:
                mapping[field] = i
    return mapping


def _num(s):
    s = re.sub(r"[^0-9.]", "", str(s or ""))
    return float(s) if s else None


def load_solds(folder="ingest/mls-solds"):
    """Returns sold records shaped like listings (usable as model comps)."""
    solds = []
    for path in sorted(Path(folder).glob("*.csv")):
        with open(path, newline="", encoding="utf-8-sig") as f:
            rows = list(csv.reader(f))
        if not rows:
            continue
        cols = _map_columns(rows[0])
        if "address" not in cols or "sold_price" not in cols:
            print(f"  ingest: skipping {path.name} — no address/sold price columns found")
            continue
        for row in rows[1:]:
            def get(field):
                i = cols.get(field)
                return row[i].strip() if i is not None and i < len(row) else None
            price = _num(get("sold_price"))
            if not price:
                continue
            city = get("city") or ""
            solds.append({
                "key": canon_key(get("address"), city),
                "address": get("address"), "city": city,
                "parish": None, "status": "sold",
                "price": price, "sqft": _num(get("sqft")),
                "year_built": _num(get("year_built")),
                "beds": _num(get("beds")), "baths": _num(get("baths")),
                "subdivision": get("subdivision") or None,
                "home_type": classify_home_type(get("property_type"),
                                                None, get("address")),
                "sold_date": get("sold_date"), "waterfront": False,
            })
    return solds


def apply_to_outcomes(outcomes, solds):
    """Replace provisional (proxy) outcome prices with true sold prices.

    Matching on address alone paired relisted homes (flips, resales) with
    their PREVIOUS sale — all 33 "true solds" before this fix were wrong. The
    sale must close within SALE_WINDOW_DAYS of the listing leaving the market,
    and earlier matches are re-checked against the same rule.
    """
    by_key = {}
    for s in solds:
        by_key.setdefault(s["key"], []).append(s)
    for o in outcomes:
        left = o.get("predicted_at")
        if o.get("sold_date") and not sale_in_window(o["sold_date"], left):
            o["sold_price"] = o["sold_date"] = None
        if o.get("sold_price"):
            continue
        cands = [s for s in by_key.get(o["key"], [])
                 if sale_in_window(s.get("sold_date"), left)]
        if cands:
            s = min(cands, key=lambda s: abs((parse_date(s["sold_date"])
                                              - parse_date(left)).days))
            o["sold_price"] = s["price"]
            o["sold_date"] = parse_date(s["sold_date"]).isoformat()
    return outcomes
