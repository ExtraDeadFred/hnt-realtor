"""Offline tests for home-type classification, comp gating, scoring spread,
and daily deal rotation. Run: python pipeline/test_deals.py"""

import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import analyze
from normalize import classify_home_type

CFG = {
    "model": {"min_comps": 5, "comp_year_window": 20, "comp_sqft_window": 0.30},
    "deals": {"underpriced_spread_pct": 12, "high_opportunity_spread_pct": 18,
              "stale_dom_days": 90, "min_price": 30000, "top_n": 10,
              "eligible_types": ["single_family", "multi_family"],
              "cooldown_days": 10, "fresh_slots": 4, "fresh_event_days": 2},
    "fmr": {"Webster": {1: 662, 2: 787, 3: 1035, 4: 1178}},
    "stats": {"exclude_types": ["mobile"]},
}


def house(key, price, sqft=1500, home_type="single_family", **kw):
    return {"key": key, "address": key, "city": "Minden", "parish": "Webster",
            "price": price, "sqft": sqft, "beds": 3, "year_built": 2000,
            "status": "active", "home_type": home_type, "waterfront": False,
            "subdivision": None, "days_on_market": 30, **kw}


def test_classify():
    assert classify_home_type("MOBILE") == "mobile"
    assert classify_home_type("Manufactured Home") == "mobile"
    assert classify_home_type("SINGLE_FAMILY") == "single_family"
    assert classify_home_type("MULTI_FAMILY") == "multi_family"
    assert classify_home_type("CONDOS") == "condo"
    assert classify_home_type("LAND") == "land"
    # free-text fallback for sources with no structured type
    assert classify_home_type(None, "Charming doublewide on 2 acres") == "mobile"
    assert classify_home_type(None, "1998 mobile home, needs work") == "mobile"
    # unknown stays unknown rather than guessing
    assert classify_home_type(None, "Brick ranch with a big yard") is None
    assert classify_home_type("") is None
    print("classify_home_type OK")


def test_comp_type_gate():
    """The bug this fixes: mobile homes valued off slab-built comps looked
    50-88% underpriced."""
    foundations = [house(f"sf{i}", 225000) for i in range(8)]
    mobiles = [house(f"mh{i}", 100000, home_type="mobile") for i in range(8)]
    pool = foundations + mobiles

    mobile_comps = analyze._find_comps(house("subject", 95000, home_type="mobile"), pool, CFG)
    assert mobile_comps, "mobile subject should find its mobile peers"
    assert all(c["home_type"] == "mobile" for c in mobile_comps), \
        "mobile subject must never comp against foundation homes"

    sf_comps = analyze._find_comps(house("subject2", 200000), pool, CFG)
    assert all(c["home_type"] != "mobile" for c in sf_comps), \
        "foundation subject must never draw a mobile comp"

    # unknown-type comps (the MLS solds export) count as non-mobile
    unknown = [house(f"unk{i}", 230000, home_type=None) for i in range(8)]
    assert analyze._find_comps(house("s3", 200000), unknown, CFG), \
        "unknown-type solds must remain usable for foundation subjects"
    assert not analyze._find_comps(house("s4", 90000, home_type="mobile"), unknown, CFG), \
        "unknown-type comps must not be used to value a mobile home"
    print("comp type gate OK")


def test_mobile_excluded_from_deals():
    listings = [house("sf1", 100000), house("mh1", 60000, home_type="mobile"),
                house("condo1", 90000, home_type="condo")]
    preds = {k: {"predicted": 200000, "comp_count": 6} for k in ("sf1", "mh1", "condo1")}
    deals = analyze.score_deals(listings, preds, CFG)
    keys = {d["key"] for d in deals}
    assert "sf1" in keys and "mh1" not in keys and "condo1" not in keys, keys
    print("mobile/condo excluded from deals OK")


def test_scores_are_not_saturated():
    """Flat +5 bonuses made 14 deals tie at exactly 50.0, so a stable sort
    froze the same picks at the top every day."""
    listings = [house(f"h{i}", 80000 + i * 1000, days_on_market=100 + i * 7)
                for i in range(20)]
    preds = {f"h{i}": {"predicted": 200000, "comp_count": 6} for i in range(20)}
    deals = analyze.score_deals(listings, preds, CFG)
    scores = [d["score"] for d in deals]
    top = sorted(scores, reverse=True)[:14]
    assert len(set(top)) > 10, f"scores still bunched: {top}"
    print(f"score spread OK ({len(set(scores))} distinct of {len(scores)})")


def test_rotation():
    deals = [{"key": f"d{i}", "score": 100 - i, "spread_pct": 20}
             for i in range(40)]
    today = date.today()
    yday = (today - timedelta(days=1)).isoformat()
    events = [{"date": yday, "event": "price_cut", "key": "d30", "cut_pct": 8},
              {"date": yday, "event": "new", "key": "d31"}]

    day1 = analyze.select_daily_deals(deals, events, {}, CFG)
    assert len(day1["deals"]) == 10
    reasons = {d["key"]: d["reason"] for d in day1["deals"]}
    assert reasons.get("d30") == "price_cut" and reasons.get("d31") == "new", \
        "fresh activity must claim the reserved slots"

    history = analyze.update_history({}, day1, {d["key"] for d in deals})
    day2 = analyze.select_daily_deals(deals, [], history, CFG)
    repeat = len({d["key"] for d in day1["deals"]} & {d["key"] for d in day2["deals"]})
    assert repeat == 0, f"cooldown ignored — {repeat} repeats next day"

    # a benched deal becomes eligible again once the cooldown expires
    old = (today - timedelta(days=CFG["deals"]["cooldown_days"] + 1)).isoformat()
    stale_history = {"d0": {"last_featured": old, "times_featured": 1}}
    assert "d0" in {d["key"] for d in
                    analyze.select_daily_deals(deals, [], stale_history, CFG)["deals"]}

    # small pool: must still fill the email rather than send a short list
    tiny = analyze.select_daily_deals(deals[:6], [],
                                      {d["key"]: {"last_featured": today.isoformat(),
                                                  "times_featured": 1}
                                       for d in deals[:6]}, CFG)
    assert len(tiny["deals"]) == 6, "should reuse benched deals when the pool is small"
    print("rotation OK")


def test_stats_exclude_mobile():
    listings = ([house(f"sf{i}", 300000, sqft=2000) for i in range(5)] +
                [house(f"mh{i}", 50000, sqft=1000, home_type="mobile") for i in range(5)])
    s = analyze.market_stats(listings, [], CFG)["cohorts"]["Minden"]
    assert s["inventory"] == 10, "inventory must count every home"
    assert s["mobile_count"] == 5
    assert s["median_price"] == 300000, s["median_price"]
    assert s["median_ppsf"] == 150.0, s["median_ppsf"]
    print("stats exclusion OK")


if __name__ == "__main__":
    test_classify()
    test_comp_type_gate()
    test_mobile_excluded_from_deals()
    test_scores_are_not_saturated()
    test_rotation()
    test_stats_exclude_mobile()
    print("\nALL TESTS PASSED")
