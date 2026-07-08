"""FBI Crime Data Explorer (CDE) client: agency-level offense counts ->
per-capita rates and multi-year trends per jurisdiction.

Why agency-level: NW Louisiana has no incident-level open-data portals, so
city/parish agency totals are the honest granularity. Listings map to an
agency by their city (police dept) with the parish sheriff as fallback.

API key: free from https://api.data.gov/signup/ -> FBI_CDE_API_KEY env var.

CLAUDE CODE: the CDE API has restructured paths before. This targets:
  {CDE_BASE}/agency/byStateAbbr/{state}         -> agency list with ORIs
  {CDE_BASE}/summarized/agency/{ori}/{offense}?from=MM-YYYY&to=MM-YYYY
Verify against https://cde.ucr.cjis.gov/LATEST/webapp/#/pages/docApi and
adjust CDE_BASE / _agency_list / _offense_counts if the shapes differ.
Selftest (live): python -m enrichment.crime --selftest LA
"""

from __future__ import annotations

import logging
import os
import sys
import time
from datetime import date
from typing import Any

import requests

from .cache import Cache

log = logging.getLogger(__name__)

CDE_BASE = "https://api.usa.gov/crime/fbi/cde"
TIMEOUT = 60
OFFENSES = ["violent-crime", "property-crime"]

# city (lowercase) -> agency name fragments to match, per parish fallback.
# Extend as listings surface new towns in the region.
CITY_AGENCY_HINTS = {
    "shreveport": ["shreveport police"],
    "bossier city": ["bossier city police"],
    "benton": ["bossier parish sheriff"],
    "minden": ["minden police"],
    "ruston": ["ruston police"],
    "grambling": ["grambling police"],
    "homer": ["homer police"],
    "mansfield": ["mansfield police"],
    "arcadia": ["arcadia police"],
}
PARISH_SHERIFF_HINTS = {
    "bienville": "bienville parish sheriff",
    "bossier": "bossier parish sheriff",
    "caddo": "caddo parish sheriff",
    "claiborne": "claiborne parish sheriff",
    "de soto": "de soto parish sheriff",
    "lincoln": "lincoln parish sheriff",
    "webster": "webster parish sheriff",
}


def _key(params: dict[str, Any]) -> dict[str, Any]:
    api_key = os.environ.get("FBI_CDE_API_KEY")
    if api_key:
        params["API_KEY"] = api_key
    return params


def agency_directory(cache: Cache, state_abbr: str = "LA") -> list[dict[str, Any]]:
    """All agencies for a state: [{'ori', 'agency_name', 'county', ...}]."""
    cached = cache.get("crime", f"agencies:{state_abbr}")
    if cached is not None:
        return cached
    r = requests.get(f"{CDE_BASE}/agency/byStateAbbr/{state_abbr}",
                     params=_key({}), timeout=TIMEOUT)
    r.raise_for_status()
    data = r.json()
    # payload shape varies: list, or dict keyed by county
    agencies: list[dict[str, Any]] = []
    if isinstance(data, list):
        agencies = data
    elif isinstance(data, dict):
        for v in data.values():
            if isinstance(v, list):
                agencies.extend(v)
    cache.set("crime", f"agencies:{state_abbr}", agencies)
    return agencies


def find_agency(agencies: list[dict[str, Any]], city: str | None,
                parish: str | None) -> dict[str, Any] | None:
    """Best agency for a listing: city PD first, parish sheriff fallback."""
    def match(fragment: str) -> dict[str, Any] | None:
        frag = fragment.lower()
        for a in agencies:
            if frag in str(a.get("agency_name", "")).lower():
                return a
        return None

    if city:
        for frag in CITY_AGENCY_HINTS.get(city.strip().lower(), []):
            hit = match(frag)
            if hit:
                return hit
    if parish:
        frag = PARISH_SHERIFF_HINTS.get(parish.strip().lower())
        if frag:
            return match(frag)
    return None


def agency_crime_trend(cache: Cache, ori: str, agency_name: str,
                       lookback_years: int = 5) -> dict[str, Any]:
    """Annual violent/property counts for one agency + simple trend."""
    ckey = f"trend:{ori}:{lookback_years}"
    cached = cache.get("crime", ckey)
    if cached is not None:
        return cached

    end_year = date.today().year - 1  # last complete year
    start_year = end_year - lookback_years + 1
    out: dict[str, Any] = {"ori": ori, "agency": agency_name,
                           "years": f"{start_year}-{end_year}",
                           "annual": {}, "caveats": []}
    for offense in OFFENSES:
        counts = _offense_counts(ori, offense, start_year, end_year)
        if counts is None:
            out["caveats"].append(f"no {offense} data (reporting gap)")
            continue
        out["annual"][offense] = counts
        yrs = sorted(int(y) for y in counts)
        if len(yrs) >= 2 and counts[str(yrs[0])]:
            first, last = counts[str(yrs[0])], counts[str(yrs[-1])]
            out[f"{offense}_change_pct"] = round((last - first) / first * 100, 1)
        time.sleep(0.5)

    cache.set("crime", ckey, out)
    return out


def _offense_counts(ori: str, offense: str, start_year: int,
                    end_year: int) -> dict[str, int] | None:
    try:
        r = requests.get(
            f"{CDE_BASE}/summarized/agency/{ori}/{offense}",
            params=_key({"from": f"01-{start_year}", "to": f"12-{end_year}",
                         "type": "counts"}),
            timeout=TIMEOUT)
        r.raise_for_status()
        data = r.json()
    except Exception:
        log.exception("CDE fetch failed ori=%s offense=%s", ori, offense)
        return None

    # Typical shape: {"offenses": {"actuals": {"<agency>": {"MM-YYYY": n}}}}
    actuals = (data.get("offenses", {}).get("actuals") or {})
    series = next(iter(actuals.values()), {}) if actuals else {}
    if not series:
        return None
    annual: dict[str, int] = {}
    for month_key, n in series.items():
        year = month_key.split("-")[-1]
        if n is not None:
            annual[year] = annual.get(year, 0) + int(n)
    return annual or None


if __name__ == "__main__":  # pragma: no cover
    if len(sys.argv) == 3 and sys.argv[1] == "--selftest":
        logging.basicConfig(level=logging.INFO)
        c = Cache(":memory:")
        ags = agency_directory(c, sys.argv[2])
        print(f"{len(ags)} agencies")
        hit = find_agency(ags, "shreveport", "caddo")
        print("shreveport ->", hit and {k: hit.get(k) for k in ("ori", "agency_name")})
        if hit:
            print(agency_crime_trend(c, hit["ori"], hit["agency_name"]))
