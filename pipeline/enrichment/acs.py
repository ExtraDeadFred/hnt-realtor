"""Census ACS 5-year client: tract-level metrics across release years.

API key optional (CENSUS_API_KEY env var) but recommended: keyless access
is limited to 500 requests/day. We fetch whole counties per call and cache,
so daily usage is tiny after warm-up.

Selftest (live): python -m enrichment.acs --selftest 22 017
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any

import requests

from .cache import Cache

log = logging.getLogger(__name__)

ACS_BASE = "https://api.census.gov/data/{year}/acs/acs5"
TIMEOUT = 60

# canonical metric -> ACS variable
VARIABLES = {
    "population": "B01003_001E",
    "median_household_income": "B19013_001E",
    "poverty_universe": "B17001_001E",
    "poverty_below": "B17001_002E",
    "housing_units": "B25002_001E",
    "housing_vacant": "B25002_003E",
    "occupied_units": "B25003_001E",
    "owner_occupied": "B25003_002E",
    "median_home_value": "B25077_001E",
}


def county_tract_metrics(cache: Cache, year: int, state: str,
                         county: str) -> dict[str, dict[str, float | None]]:
    """All tract metrics for one county+release year: {geoid: {metric: value}}."""
    ckey = f"{year}:{state}{county}"
    cached = cache.get("acs", ckey)
    if cached:
        return cached

    params = {
        "get": ",".join(VARIABLES.values()),
        "for": "tract:*",
        "in": f"state:{state} county:{county}",
    }
    api_key = os.environ.get("CENSUS_API_KEY")
    if api_key:
        params["key"] = api_key

    r = requests.get(ACS_BASE.format(year=year), params=params, timeout=TIMEOUT)
    r.raise_for_status()
    if not api_key and "Missing Key" in r.text[:500]:
        raise RuntimeError("Census API now requires a key — get a free one at "
                           "https://api.census.gov/data/key_signup.html and set CENSUS_API_KEY")
    rows = r.json()
    header, data = rows[0], rows[1:]
    idx = {name: header.index(var) for name, var in VARIABLES.items()}
    i_state, i_county, i_tract = (header.index(k) for k in ("state", "county", "tract"))

    out: dict[str, dict[str, float | None]] = {}
    for row in data:
        geoid = f"{row[i_state]}{row[i_county]}{row[i_tract]}"
        metrics = {name: _clean(row[i]) for name, i in idx.items()}
        out[geoid] = _derive(metrics)

    cache.set("acs", ckey, out)
    return out


def _clean(v: Any) -> float | None:
    """ACS uses large negative sentinels (-666666666) for suppressed values."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f < -100000 else f


def _derive(m: dict[str, float | None]) -> dict[str, float | None]:
    def ratio(a, b):
        return round(a / b * 100, 1) if (a is not None and b) else None
    m["poverty_rate_pct"] = ratio(m.get("poverty_below"), m.get("poverty_universe"))
    m["vacancy_rate_pct"] = ratio(m.get("housing_vacant"), m.get("housing_units"))
    m["owner_occupancy_pct"] = ratio(m.get("owner_occupied"), m.get("occupied_units"))
    return m


def tract_trends(cache: Cache, geoid: str, years: list[int],
                 state: str, county: str) -> dict[str, Any]:
    """Levels for each release year + change between oldest and newest
    where the tract exists in both (tract boundaries changed in 2020)."""
    levels: dict[int, dict[str, float | None]] = {}
    for year in years:
        try:
            county_data = county_tract_metrics(cache, year, state, county)
        except Exception:
            log.exception("ACS fetch failed for %s county %s", year, county)
            continue
        if geoid in county_data:
            levels[year] = county_data[geoid]

    trends: dict[str, Any] = {"levels": {str(y): levels[y] for y in sorted(levels)}}
    if len(levels) >= 2:
        y0, y1 = min(levels), max(levels)
        trends["trend_years"] = f"{y0}->{y1}"
        for metric in ("median_household_income", "median_home_value",
                       "poverty_rate_pct", "vacancy_rate_pct",
                       "owner_occupancy_pct"):
            a, b = levels[y0].get(metric), levels[y1].get(metric)
            if a is not None and b is not None:
                if metric.endswith("_pct"):
                    trends[f"{metric}_change_pts"] = round(b - a, 1)
                elif a:
                    trends[f"{metric}_change_pct"] = round((b - a) / a * 100, 1)
    else:
        trends["note"] = ("tract not comparable across selected years "
                          "(likely 2020 boundary change)")
    return trends


if __name__ == "__main__":  # pragma: no cover
    if len(sys.argv) == 4 and sys.argv[1] == "--selftest":
        logging.basicConfig(level=logging.INFO)
        c = Cache(":memory:")
        data = county_tract_metrics(c, 2023, sys.argv[2], sys.argv[3])
        gid, m = next(iter(data.items()))
        print(f"{len(data)} tracts; sample {gid}: {m}")
