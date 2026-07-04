"""Ingest MLS sold-comp CSV exports dropped in ingest/mls-solds/.

Column names are matched loosely so whatever the MLS export calls them works.
Minimum useful columns: address, city, sold price. Also recognized: sold date,
sqft (living area), year built, beds, baths.
"""

import csv
import re
from pathlib import Path

from normalize import canon_key

_COLUMN_ALIASES = {
    "address": ["address", "street address", "property address", "full address"],
    "city": ["city", "town"],
    "sold_price": ["sold price", "sale price", "close price", "closed price", "selling price"],
    "sold_date": ["sold date", "close date", "closing date", "sale date"],
    "sqft": ["sqft", "living area", "living sqft", "total living area", "sq ft", "heated sqft"],
    "year_built": ["year built", "yr built"],
    "subdivision": ["subdivision", "subdivision name", "neighborhood"],
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
                "sold_date": get("sold_date"), "waterfront": False,
            })
    return solds


def apply_to_outcomes(outcomes, solds):
    """Replace provisional (proxy) outcome prices with true sold prices."""
    by_key = {s["key"]: s for s in solds}
    for o in outcomes:
        s = by_key.get(o["key"])
        if s and not o.get("sold_price"):
            o["sold_price"] = s["price"]
            o["sold_date"] = s.get("sold_date")
    return outcomes
