"""HomeHarvest source adapter — primary listing source.

Pulls structured listing data from Realtor.com's internal API via the
`homeharvest` package: no LLM extraction, no Firecrawl credits, and fields
the scrapers never had (year_built, lat/lon, agent name, descriptions).
The Firecrawl adapters remain the fallback in run.py.
"""

from datetime import date

import pandas as pd

from normalize import classify_home_type

_WATERFRONT_WORDS = ("waterfront", "water front", "lakefront", "lake front",
                     "lake claiborne", "lake bistineau", "boat house",
                     "boathouse", "boat dock", "on the lake", "lake view")

OWN_AGENT = "catherine"  # matched with "hunt" against agent_name, lowercased


def _val(row, key):
    v = row.get(key)
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    return v


def _num(row, key, as_int=False):
    v = _val(row, key)
    if v is None:
        return None
    try:
        return int(float(v)) if as_int else float(v)
    except (TypeError, ValueError):
        return None


def _is_waterfront(row):
    blob = " ".join(str(_val(row, k) or "") for k in ("text", "neighborhoods")).lower()
    return any(w in blob for w in _WATERFRONT_WORDS)


def _to_listing(row, area, status):
    baths = (_num(row, "full_baths") or 0) + 0.5 * (_num(row, "half_baths") or 0)
    lot_sqft = _num(row, "lot_sqft")
    agent = str(_val(row, "agent_name") or "").lower()
    street = " ".join(str(_val(row, k)) for k in ("street", "unit") if _val(row, k))
    return {
        "address": street or None,
        "city": _val(row, "city") or area["city"],
        "parish": area["parish"],
        "zip": _val(row, "zip_code"),
        "price": _num(row, "list_price", as_int=True),
        "beds": _num(row, "beds", as_int=True),
        "baths": baths or None,
        "sqft": _num(row, "sqft", as_int=True),
        "lot_acres": round(lot_sqft / 43560, 2) if lot_sqft else None,
        "year_built": _num(row, "year_built", as_int=True),
        "status": status,
        "days_on_market": _num(row, "days_on_mls", as_int=True),
        "url": _val(row, "property_url"),
        "photo_url": _val(row, "primary_photo"),
        "lat": _num(row, "latitude"),
        "lng": _num(row, "longitude"),
        "waterfront": _is_waterfront(row),
        "subdivision": _val(row, "neighborhoods"),
        "style": _val(row, "style"),
        "home_type": classify_home_type(_val(row, "style"), _val(row, "text"), street),
        "avm_estimate": _num(row, "estimated_value", as_int=True),
        "own_listing": OWN_AGENT in agent and "hunt" in agent,
        "source": "homeharvest",
        "scraped_at": date.today().isoformat(),
    }


def fetch_all(cfg):
    """Active + pending listings for every configured city."""
    from homeharvest import scrape_property
    listings = []
    cities = []
    seen = set()
    for a in cfg["areas"]:
        if a["city"] not in seen:
            seen.add(a["city"])
            cities.append(a)
    for area in cities:
        for listing_type, status in (("for_sale", "active"), ("pending", "pending")):
            try:
                df = scrape_property(location=f"{area['city']}, LA",
                                     listing_type=listing_type)
            except Exception as e:
                print(f"  homeharvest {listing_type} / {area['city']}: FAILED — {e}")
                continue
            rows = [_to_listing(r, area, status) for r in df.to_dict("records")]
            rows = [l for l in rows if l["address"] and l["price"]
                    and l.get("style") != "LAND"]
            print(f"  homeharvest {listing_type} / {area['city']}: {len(rows)}")
            listings.extend(rows)
    return listings


def fetch_sold_events(cfg, past_days=90):
    """Recently sold addresses (+dates). Louisiana withholds prices, so this
    confirms WHEN tracked homes closed; prices still come from MLS CSVs."""
    from homeharvest import scrape_property

    from normalize import canon_key
    events = []
    for city in sorted({a["city"] for a in cfg["areas"]}):
        try:
            df = scrape_property(location=f"{city}, LA", listing_type="sold",
                                 past_days=past_days)
        except Exception as e:
            print(f"  homeharvest sold / {city}: FAILED — {e}")
            continue
        for r in df.to_dict("records"):
            street = _val(r, "street")
            if not street:
                continue
            events.append({
                "key": canon_key(str(street), str(_val(r, "city") or city)),
                "sold_date": str(_val(r, "last_sold_date") or "")[:10] or None,
                "sold_price": _num(r, "sold_price", as_int=True),  # ~always None in LA
            })
    return events
