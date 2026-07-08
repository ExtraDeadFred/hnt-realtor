"""Census Geocoder client: lat/lon or street address -> census tract GEOID.

Free, no API key. Docs: https://geocoding.geo.census.gov/geocoder/
"""

from __future__ import annotations

import logging
from typing import Any

import requests

from .cache import Cache

log = logging.getLogger(__name__)

GEO_BASE = "https://geocoding.geo.census.gov/geocoder/geographies"
PARAMS_COMMON = {
    "benchmark": "Public_AR_Current",
    "vintage": "Current_Current",
    "format": "json",
}
TIMEOUT = 30


def tract_for_listing(cache: Cache, listing: dict[str, Any]) -> dict[str, str] | None:
    """Return {'geoid', 'state', 'county', 'tract'} for a listing, or None.

    Prefers lat/lon (exact); falls back to the street address.
    """
    lat, lon = listing.get("latitude"), listing.get("longitude")
    if lat is not None and lon is not None:
        key = f"{round(float(lat), 5)},{round(float(lon), 5)}"
        cached = cache.get("tract_geo", key)
        if cached:
            return cached
        result = _from_coordinates(float(lat), float(lon))
    else:
        addr = _one_line_address(listing)
        if not addr:
            return None
        key = addr.lower()
        cached = cache.get("tract_geo", key)
        if cached:
            return cached
        result = _from_address(addr)

    if result:
        cache.set("tract_geo", key, result)
    return result


def _one_line_address(listing: dict[str, Any]) -> str | None:
    parts = [listing.get("street"), listing.get("city"),
             listing.get("state"), str(listing.get("zip_code") or "")]
    parts = [p for p in parts if p]
    return ", ".join(parts) if len(parts) >= 3 else None


def _from_coordinates(lat: float, lon: float) -> dict[str, str] | None:
    try:
        r = requests.get(f"{GEO_BASE}/coordinates",
                         params={**PARAMS_COMMON, "x": lon, "y": lat},
                         timeout=TIMEOUT)
        r.raise_for_status()
        return _parse_tract(r.json())
    except Exception:
        log.exception("geocode by coordinates failed (%s, %s)", lat, lon)
        return None


def _from_address(address: str) -> dict[str, str] | None:
    try:
        r = requests.get(f"{GEO_BASE}/onelineaddress",
                         params={**PARAMS_COMMON, "address": address},
                         timeout=TIMEOUT)
        r.raise_for_status()
        data = r.json()
        matches = (data.get("result", {}).get("addressMatches") or [])
        if not matches:
            return None
        return _parse_tract({"result": matches[0]})
    except Exception:
        log.exception("geocode by address failed (%s)", address)
        return None


def _parse_tract(payload: dict[str, Any]) -> dict[str, str] | None:
    geogs = (payload.get("result", {}).get("geographies")
             or payload.get("geographies") or {})
    tracts = geogs.get("Census Tracts") or []
    if not tracts:
        return None
    t = tracts[0]
    return {
        "geoid": t.get("GEOID"),
        "state": t.get("STATE"),
        "county": t.get("COUNTY"),
        "tract": t.get("TRACT"),
    }
