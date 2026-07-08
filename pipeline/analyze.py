"""Market stats, comp-based price model, deal scoring, and model accuracy."""

from datetime import date
from statistics import median


def _ppsf(l):
    if l.get("price") and l.get("sqft") and l["sqft"] > 200:
        return l["price"] / l["sqft"]
    return None


def _decade(l):
    yb = l.get("year_built")
    return f"{int(yb) // 10 * 10}s" if yb else None


def market_stats(listings, events):
    """Per-cohort stats. Cohorts: each city, each parish, and 'Waterfront'."""
    cohorts = {}
    for l in listings:
        if l["status"] not in ("active", "coming_soon"):
            continue
        groups = [l["city"], f"{l['parish']} Parish"]
        if l.get("waterfront"):
            groups.append("Waterfront")
        for g in groups:
            cohorts.setdefault(g, []).append(l)

    recent = [e for e in events if (date.today() - date.fromisoformat(e["date"])).days <= 7]
    stats = {"updated": date.today().isoformat(), "cohorts": {}}
    for name, ls in sorted(cohorts.items()):
        prices = [l["price"] for l in ls if l.get("price")]
        ppsfs = [p for p in (_ppsf(l) for l in ls) if p]
        doms = [l["days_on_market"] for l in ls if l.get("days_on_market") is not None]
        keys = {l["key"] for l in ls}
        by_decade = {}
        for l in ls:
            d, p = _decade(l), _ppsf(l)
            if d and p:
                by_decade.setdefault(d, []).append(p)
        stats["cohorts"][name] = {
            "inventory": len(ls),
            "median_price": round(median(prices)) if prices else None,
            "median_ppsf": round(median(ppsfs), 1) if ppsfs else None,
            "median_dom": round(median(doms)) if doms else None,
            "ppsf_by_decade": {d: round(median(v), 1) for d, v in sorted(by_decade.items())},
            "new_7d": sum(1 for e in recent if e["event"] == "new" and e["key"] in keys),
            "price_cuts_7d": sum(1 for e in recent if e["event"] == "price_cut" and e["key"] in keys),
            "pending_7d": sum(1 for e in recent if e["event"] == "pending" and e["key"] in keys),
        }
    return stats


def _find_comps(subject, pool, cfg):
    """Comparable listings: same neighborhood if possible, else same city,
    else parish — always similar size/age/beds, waterfront-to-waterfront only.
    Returns the nearest matches by living area."""
    m = cfg["model"]

    def matches(l, scope):
        if l["key"] == subject["key"] or not _ppsf(l):
            return False
        if bool(l.get("waterfront")) != bool(subject.get("waterfront")):
            return False
        if scope == "subdivision":
            if not subject.get("subdivision") or l.get("subdivision") != subject["subdivision"]:
                return False
        if scope == "city" and l["city"] != subject["city"]:
            return False
        if scope == "parish" and l["parish"] != subject["parish"]:
            return False
        if subject.get("year_built") and l.get("year_built"):
            if abs(l["year_built"] - subject["year_built"]) > m["comp_year_window"]:
                return False
        if subject.get("beds") and l.get("beds") and abs(l["beds"] - subject["beds"]) > 1:
            return False
        if subject.get("sqft") and l.get("sqft"):
            if abs(l["sqft"] - subject["sqft"]) > m["comp_sqft_window"] * subject["sqft"]:
                return False
        return True

    comps = []
    for scope in ("subdivision", "city", "parish"):
        comps = [l for l in pool if matches(l, scope)]
        if len(comps) >= m["min_comps"]:
            break
    if subject.get("sqft"):
        comps.sort(key=lambda l: abs((l.get("sqft") or subject["sqft"]) - subject["sqft"]))
    return comps[:10]


def predict_prices(listings, solds, cfg):
    """Predicted value = median $/sqft of comps × sqft. Sold records (from MLS
    CSVs) are preferred comps; active/pending listings fill the gap."""
    pool = solds + listings
    predictions = {}
    for l in listings:
        if not (l.get("sqft") and l.get("price")):
            continue
        comps = _find_comps(l, pool, cfg)
        if len(comps) < 3:
            continue
        ppsf = median([_ppsf(c) for c in comps])
        predictions[l["key"]] = {
            "predicted": round(ppsf * l["sqft"]),
            "comp_count": len(comps),
            "comp_ppsf": round(ppsf, 1),
        }
    return predictions


def score_deals(listings, predictions, cfg):
    """Rank active listings by investment opportunity."""
    d, fmr_table = cfg["deals"], cfg["fmr"]
    deals = []
    for l in listings:
        p = predictions.get(l["key"])
        if not p or l["status"] != "active" or (l.get("price") or 0) < d["min_price"]:
            continue
        spread_pct = 100 * (p["predicted"] - l["price"]) / p["predicted"]
        beds = min(int(l.get("beds") or 3), 4)
        fmr = fmr_table.get(l["parish"], {}).get(beds)
        gross_yield = round(100 * fmr * 12 / l["price"], 1) if fmr else None
        dom = l.get("days_on_market") or 0
        # A spread past ~40% almost always means condition problems the model
        # can't see, not a bargain — cap its contribution to the ranking
        score = min(spread_pct, 40)
        if dom > d["stale_dom_days"]:
            score += 5  # long-sitting sellers negotiate
        if gross_yield and gross_yield > 10:
            score += 5
        flags = []
        if spread_pct >= d["underpriced_spread_pct"]:
            flags.append("underpriced")
        if spread_pct >= d["underpriced_spread_pct"] and (l.get("year_built") or 2100) < 1990:
            flags.append("flip_candidate")
        if gross_yield and gross_yield > 10:
            flags.append("rental_candidate")
        if spread_pct > 40:
            flags.append("verify_condition")
        if not flags:
            continue
        deals.append({
            **{f: l.get(f) for f in ("key", "address", "city", "parish", "zip",
                                     "price", "beds", "baths", "sqft", "year_built",
                                     "days_on_market", "url", "waterfront",
                                     "lat", "lng", "avm_estimate", "own_listing")},
            "predicted": p["predicted"], "spread_pct": round(spread_pct, 1),
            "comp_count": p["comp_count"], "gross_yield_pct": gross_yield,
            "score": round(score, 1), "flags": flags,
        })
    deals.sort(key=lambda x: -x["score"])
    return {"updated": date.today().isoformat(),
            "high_opportunity": any(x["spread_pct"] >= d["high_opportunity_spread_pct"] for x in deals),
            "deals": deals[: d["top_n"]]}


def update_outcomes(outcomes, events, predictions, listings_prev):
    """When a listing leaves the market, freeze its prediction vs last list
    price as a provisional outcome (replaced by true sold price on MLS ingest)."""
    known = {o["key"] for o in outcomes}
    prev = {l["key"]: l for l in listings_prev}
    for e in events:
        if e["event"] != "off_market" or e["key"] in known:
            continue
        pred = predictions.get(e["key"])
        old = prev.get(e["key"], {})
        if not pred or not e.get("last_price"):
            continue
        outcomes.append({
            "key": e["key"], "address": e["address"], "city": e["city"],
            "sqft": old.get("sqft"), "predicted": pred["predicted"],
            "predicted_at": e["date"], "proxy_price": e["last_price"],
            "sold_price": None, "sold_date": None,
        })
    return outcomes


def backtest(solds, cfg, max_n=1000):
    """Leave-one-out accuracy against real MLS sales: predict each sold home
    from the other solds' $/sqft and compare to its actual close price."""
    errs = []
    for s in solds[:max_n]:
        if not (s.get("sqft") and s.get("price")):
            continue
        comps = _find_comps(s, solds, cfg)
        if len(comps) < 3:
            continue
        predicted = median([_ppsf(c) for c in comps]) * s["sqft"]
        errs.append(abs(predicted - s["price"]) / s["price"])
    if not errs:
        return None
    return {
        "n": len(errs),
        # median is the AVM-standard headline: robust to distressed/teardown
        # sales that no size-based model can price
        "median_err_pct": round(100 * median(errs), 1),
        "mape_pct": round(100 * sum(errs) / len(errs), 1),
        "within_10pct": round(100 * sum(1 for e in errs if e <= 0.10) / len(errs), 1),
    }


def model_metrics(outcomes):
    """Rolling accuracy vs actual (MLS) or proxy (last list) prices."""
    errs = []
    for o in outcomes:
        actual = o.get("sold_price") or o.get("proxy_price")
        if actual and o.get("predicted"):
            errs.append(abs(o["predicted"] - actual) / actual)
    return {
        "updated": date.today().isoformat(),
        "n_outcomes": len(errs),
        "n_true_solds": sum(1 for o in outcomes if o.get("sold_price")),
        "mape_pct": round(100 * sum(errs) / len(errs), 1) if errs else None,
        "within_10pct": round(100 * sum(1 for e in errs if e <= 0.10) / len(errs), 1) if errs else None,
    }
