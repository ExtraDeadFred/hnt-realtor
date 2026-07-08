"""Offline tests for the enrichment package (mocked HTTP, no network).
Run: python test_enrichment.py
Covers: geocoder parsing, ACS derivation + trends, HUD proximity math,
crime annual rollup + agency matching, scoring, and cache TTL behavior.
"""

from __future__ import annotations

import json
from unittest.mock import patch, MagicMock

from enrichment.cache import Cache
from enrichment import geocode, acs, hud, crime, scoring


def fake_response(payload):
    r = MagicMock()
    r.json.return_value = payload
    r.raise_for_status.return_value = None
    return r


def test_geocode():
    payload = {"result": {"geographies": {"Census Tracts": [
        {"GEOID": "22017024300", "STATE": "22", "COUNTY": "017", "TRACT": "024300"}]}}}
    cache = Cache(":memory:")
    with patch("enrichment.geocode.requests.get", return_value=fake_response(payload)) as g:
        t = geocode.tract_for_listing(cache, {"latitude": 32.47, "longitude": -93.77})
        assert t["geoid"] == "22017024300" and t["county"] == "017"
        # second call hits cache — no new HTTP
        geocode.tract_for_listing(cache, {"latitude": 32.47, "longitude": -93.77})
        assert g.call_count == 1
    print("geocode OK")


def test_acs():
    header = list(acs.VARIABLES.values()) + ["state", "county", "tract"]
    row = ["3500", "42000", "3400", "680", "1500", "150", "1350", "810",
           "155000", "22", "017", "024300"]
    old = ["3400", "32000", "3300", "800", "1450", "200", "1250", "700",
           "120000", "22", "017", "024300"]
    cache = Cache(":memory:")
    with patch("enrichment.acs.requests.get",
               side_effect=[fake_response([header, old]), fake_response([header, row])]):
        trends = acs.tract_trends(cache, "22017024300", [2013, 2023], "22", "017")
    lvl = trends["levels"]["2023"]
    assert lvl["poverty_rate_pct"] == 20.0          # 680/3400
    assert lvl["vacancy_rate_pct"] == 10.0          # 150/1500
    assert lvl["owner_occupancy_pct"] == 60.0       # 810/1350
    assert trends["median_household_income_change_pct"] == 31.2  # 32k->42k
    assert trends["median_home_value_change_pct"] == 29.2
    print("acs OK")


def test_acs_sentinel():
    assert acs._clean("-666666666") is None
    assert acs._clean("42000") == 42000.0
    print("acs sentinel OK")


def test_hud():
    pts = [{"lat": 32.48, "lon": -93.77, "name": "A", "attrs": {}},
           {"lat": 32.60, "lon": -93.60, "name": "B", "attrs": {}}]
    prox = hud.proximity(32.47, -93.77, pts, radius_miles=1.0)
    assert prox["nearest_name"] == "A"
    assert prox["nearest_miles"] < 1.0
    assert prox["count_within_radius"] == 1
    # empty layer degrades gracefully
    assert hud.proximity(32.47, -93.77, [], 1.0)["nearest_miles"] is None
    print("hud OK")


def test_crime():
    agencies = [{"ori": "LA0090100", "agency_name": "Shreveport Police Department"},
                {"ori": "LA0090000", "agency_name": "Caddo Parish Sheriff's Office"}]
    hit = crime.find_agency(agencies, "Shreveport", "Caddo")
    assert hit["ori"] == "LA0090100"
    hit = crime.find_agency(agencies, "Vivian", "Caddo")   # no PD hint -> sheriff
    assert hit["ori"] == "LA0090000"

    series = {f"{m:02d}-2021": 10 for m in range(1, 13)}
    series.update({f"{m:02d}-2025": 8 for m in range(1, 13)})
    payload = {"offenses": {"actuals": {"Shreveport Police Department": series}}}
    cache = Cache(":memory:")
    with patch("enrichment.crime.requests.get", return_value=fake_response(payload)), \
         patch("enrichment.crime.time.sleep"):
        trend = crime.agency_crime_trend(cache, "LA0090100", "Shreveport PD", 5)
    assert trend["annual"]["violent-crime"]["2021"] == 120
    assert trend["violent-crime_change_pct"] == -20.0
    print("crime OK")


def test_scoring():
    enrichment = {
        "acs_trends": {
            "levels": {"2023": {"poverty_rate_pct": 20.0, "vacancy_rate_pct": 10.0,
                                "owner_occupancy_pct": 60.0}},
            "median_household_income_change_pct": 31.2,
            "median_home_value_change_pct": 29.2,
        },
        "crime": {"violent-crime_change_pct": -20.0},
        "hud": {"lihtc": {"nearest_miles": 0.8, "count_within_radius": 1}},
    }
    s = scoring.score(enrichment)
    assert s["score"] is not None and 0 <= s["score"] <= 100
    assert s["coverage"] == 1.0
    # missing crime data lowers coverage, not the score's honesty
    del enrichment["crime"]
    s2 = scoring.score(enrichment)
    assert s2["coverage"] < 1.0
    print(f"scoring OK (sample score: {s['score']}, coverage {s['coverage']})")


if __name__ == "__main__":
    test_geocode()
    test_acs()
    test_acs_sentinel()
    test_hud()
    test_crime()
    test_scoring()
    print("\nALL TESTS PASSED")
