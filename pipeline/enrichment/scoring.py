"""Composite neighborhood score: transparent, tunable, 0-100 with a
per-factor breakdown so the digest can show WHY, not just a number.

Weights are documented starting points — tune with the user. The score
deliberately uses only economic/housing/crime factors; no demographic
composition variables (fair-housing hygiene).
"""

from __future__ import annotations

from typing import Any

WEIGHTS = {
    "income_trend": 0.25,       # median household income change %
    "home_value_trend": 0.20,   # median home value change %
    "poverty_level": 0.15,      # current poverty rate (lower better)
    "vacancy_level": 0.10,      # current vacancy rate (lower better)
    "owner_occupancy": 0.10,    # current owner-occupied % (higher better)
    "crime_trend": 0.10,        # violent crime change % (falling better)
    "subsidized_proximity": 0.10,  # distance to nearest subsidized property
}


def _scale(value: float | None, lo: float, hi: float,
           invert: bool = False) -> float | None:
    """Linear map value in [lo, hi] -> [0, 100], clamped."""
    if value is None:
        return None
    pct = max(0.0, min(1.0, (value - lo) / (hi - lo)))
    if invert:
        pct = 1.0 - pct
    return round(pct * 100, 1)


def score(enrichment: dict[str, Any]) -> dict[str, Any]:
    acs = enrichment.get("acs_trends") or {}
    levels = acs.get("levels") or {}
    latest = levels[max(levels)] if levels else {}
    crime = enrichment.get("crime") or {}
    hud = enrichment.get("hud") or {}
    lihtc = hud.get("lihtc") or {}

    factors: dict[str, float | None] = {
        # +40% income growth over ~10yr -> 100; flat/negative -> low
        "income_trend": _scale(acs.get("median_household_income_change_pct"), -10, 40),
        "home_value_trend": _scale(acs.get("median_home_value_change_pct"), -10, 50),
        # 0% poverty -> 100; 40%+ -> 0
        "poverty_level": _scale(latest.get("poverty_rate_pct"), 0, 40, invert=True),
        "vacancy_level": _scale(latest.get("vacancy_rate_pct"), 0, 30, invert=True),
        "owner_occupancy": _scale(latest.get("owner_occupancy_pct"), 20, 90),
        # -30% violent crime -> 100; +30% -> 0
        "crime_trend": _scale(crime.get("violent-crime_change_pct"), -30, 30,
                              invert=True),
        # 2+ miles from nearest subsidized property -> 100; adjacent -> 0
        "subsidized_proximity": _scale(lihtc.get("nearest_miles"), 0, 2),
    }

    weighted, weight_used = 0.0, 0.0
    for name, w in WEIGHTS.items():
        v = factors.get(name)
        if v is not None:
            weighted += v * w
            weight_used += w

    return {
        "score": round(weighted / weight_used, 1) if weight_used else None,
        "coverage": round(weight_used, 2),  # how much of the model had data
        "factors": factors,
    }
