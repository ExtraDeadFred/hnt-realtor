"""NTREIS RESO Web API adapter (IDX feed) — the future primary source.

Inactive until credentials exist. Activation steps: pipeline/NTREIS.md.

Auth (either works):
  NTREIS_ACCESS_TOKEN                        — static bearer token
  NTREIS_CLIENT_ID + NTREIS_CLIENT_SECRET    — OAuth2 client-credentials
Endpoints come from config.yaml `ntreis:` (filled in from NTREIS's packet).

RESO field names follow the RESO Data Dictionary, which NTREIS conforms to.
If their packet shows different casing/names, adjust _to_listing only.
"""

import os
from datetime import date

import requests

from normalize import classify_home_type

_token_cache = {}


def enabled(cfg):
    has_creds = bool(os.environ.get("NTREIS_ACCESS_TOKEN")
                     or (os.environ.get("NTREIS_CLIENT_ID")
                         and os.environ.get("NTREIS_CLIENT_SECRET")))
    return has_creds and bool(cfg.get("ntreis", {}).get("base_url"))


def _token(cfg):
    static = os.environ.get("NTREIS_ACCESS_TOKEN")
    if static:
        return static
    if "token" in _token_cache:
        return _token_cache["token"]
    r = requests.post(cfg["ntreis"]["token_url"], data={
        "grant_type": "client_credentials",
        "client_id": os.environ["NTREIS_CLIENT_ID"],
        "client_secret": os.environ["NTREIS_CLIENT_SECRET"],
        "scope": cfg["ntreis"].get("scope", "api"),
    }, timeout=30)
    r.raise_for_status()
    _token_cache["token"] = r.json()["access_token"]
    return _token_cache["token"]


def _query(cfg, resource, params):
    """OData query with @odata.nextLink pagination. Returns list of records."""
    url = cfg["ntreis"]["base_url"].rstrip("/") + "/" + resource
    headers = {"Authorization": f"Bearer {_token(cfg)}",
               "Accept": "application/json"}
    out = []
    for _ in range(50):  # pagination safety cap
        r = requests.get(url, params=params, headers=headers, timeout=60)
        r.raise_for_status()
        data = r.json()
        out.extend(data.get("value", []))
        url = data.get("@odata.nextLink")
        params = None  # nextLink already carries the query string
        if not url:
            break
    return out


def _num(v):
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _to_listing(rec, parish_by_city):
    """Map a RESO Property record to our common listing schema."""
    status_map = {
        "Active": "active", "Coming Soon": "coming_soon",
        "Active Under Contract": "contingent", "Pending": "pending",
        "Closed": "sold",
    }
    baths = rec.get("BathroomsTotalDecimal")
    if baths is None:
        baths = rec.get("BathroomsTotalInteger")
    city = (rec.get("City") or "").strip()
    sqft = _num(rec.get("LivingArea"))
    address = rec.get("UnparsedAddress")
    if not address:
        parts = [str(rec[k]) for k in ("StreetNumber", "StreetDirPrefix",
                                       "StreetName", "StreetSuffix") if rec.get(k)]
        address = " ".join(parts) or None
    return {
        "address": address,
        "city": city,
        "parish": (rec.get("CountyOrParish") or "").replace(" Parish", "").strip()
                  or parish_by_city.get(city),
        "zip": rec.get("PostalCode"),
        "price": _num(rec.get("ListPrice")),
        "beds": _num(rec.get("BedroomsTotal")),
        "baths": _num(baths),
        "sqft": int(sqft) if sqft else None,
        "lot_acres": _num(rec.get("LotSizeAcres")),
        "year_built": int(_num(rec.get("YearBuilt")) or 0) or None,
        "status": status_map.get(rec.get("StandardStatus"), "active"),
        "days_on_market": int(_num(rec.get("DaysOnMarket")) or 0) or None,
        "url": None,  # IDX display rules: link to our own detail page, not a portal
        "photo_url": None,  # populate from the Media resource if licensed
        "lat": _num(rec.get("Latitude")),
        "lng": _num(rec.get("Longitude")),
        "waterfront": bool(rec.get("WaterfrontYN")),
        "home_type": classify_home_type(
            rec.get("PropertySubType") or rec.get("PropertyType"),
            rec.get("PublicRemarks"), address),
        "subdivision": rec.get("SubdivisionName") or None,
        "source": "ntreis",
        "scraped_at": date.today().isoformat(),
    }


def fetch_all(cfg):
    """All active/pending residential listings for the configured cities.
    Replaces the per-city scrapers when enabled."""
    cities = sorted({a["city"] for a in cfg["areas"]})
    parish_by_city = {a["city"]: a["parish"] for a in cfg["areas"]}
    city_filter = " or ".join(f"City eq '{c}'" for c in cities)
    status_filter = ("StandardStatus eq 'Active' or StandardStatus eq 'Pending' "
                     "or StandardStatus eq 'Active Under Contract' "
                     "or StandardStatus eq 'Coming Soon'")
    records = _query(cfg, "Property", {
        "$filter": f"PropertyType eq 'Residential' and ({city_filter}) and ({status_filter})",
        "$top": 200,
    })
    listings = [_to_listing(r, parish_by_city) for r in records]
    return [l for l in listings if l["address"] and l["price"]]


def fetch_solds(cfg, days=365):
    """Closed sales (model ground truth). NOTE: plain IDX feeds often exclude
    Closed status — if this errors or returns nothing, the feed is IDX-only
    and sold data keeps coming from the manual MLS CSV export."""
    from datetime import timedelta
    cities = sorted({a["city"] for a in cfg["areas"]})
    parish_by_city = {a["city"]: a["parish"] for a in cfg["areas"]}
    since = (date.today() - timedelta(days=days)).isoformat()
    city_filter = " or ".join(f"City eq '{c}'" for c in cities)
    try:
        records = _query(cfg, "Property", {
            "$filter": (f"PropertyType eq 'Residential' and ({city_filter}) "
                        f"and StandardStatus eq 'Closed' and CloseDate ge {since}"),
            "$top": 200,
        })
    except requests.RequestException as e:
        print(f"  ntreis: closed-sales query failed (feed may be IDX-only): {e}")
        return []
    from normalize import canon_key
    solds = []
    for rec in records:
        l = _to_listing(rec, parish_by_city)
        price = _num(rec.get("ClosePrice"))
        if not (l["address"] and price):
            continue
        l.update(price=price, status="sold", sold_date=rec.get("CloseDate"),
                 key=canon_key(l["address"], l["city"]))
        solds.append(l)
    return solds


if __name__ == "__main__":
    # Smoke test once credentials exist:  python pipeline/sources/ntreis.py
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    import json

    import yaml
    cfg = yaml.safe_load((Path(__file__).resolve().parents[2] / "pipeline" / "config.yaml").read_text(encoding="utf-8"))
    if not enabled(cfg):
        sys.exit("Not configured: set NTREIS_* env vars and ntreis.base_url in config.yaml (see pipeline/NTREIS.md)")
    listings = fetch_all(cfg)
    print(f"{len(listings)} active/pending listings")
    print(json.dumps(listings[:2], indent=1))
    solds = fetch_solds(cfg, days=30)
    print(f"{len(solds)} closed sales in last 30 days (0 may mean IDX-only feed)")
