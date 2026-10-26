"""Market stats, comp-based price model, deal scoring, and model accuracy."""

from datetime import date, timedelta
from statistics import median


def _ppsf(l):
    if l.get("price") and l.get("sqft") and l["sqft"] > 200:
        return l["price"] / l["sqft"]
    return None


def _decade(l):
    yb = l.get("year_built")
    return f"{int(yb) // 10 * 10}s" if yb else None


def market_stats(listings, events, cfg=None):
    """Per-cohort stats. Cohorts: each city, each parish, and 'Waterfront'.

    Headline price figures exclude mobile/manufactured homes: they sell for
    roughly two-thirds the $/sqft of slab-built houses, so including them
    drags the medians and makes "homes here average $X/sqft" misleading in
    Catherine's posts. `inventory` still counts every home on the market, and
    `mobile_count` reports what was held out.
    """
    exclude = set((cfg or {}).get("stats", {}).get("exclude_types") or [])
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
        priced = [l for l in ls if l.get("home_type") not in exclude]
        prices = [l["price"] for l in priced if l.get("price")]
        ppsfs = [p for p in (_ppsf(l) for l in priced) if p]
        doms = [l["days_on_market"] for l in priced if l.get("days_on_market") is not None]
        keys = {l["key"] for l in ls}
        by_decade = {}
        for l in priced:
            d, p = _decade(l), _ppsf(l)
            if d and p:
                by_decade.setdefault(d, []).append(p)
        stats["cohorts"][name] = {
            "inventory": len(ls),
            "mobile_count": sum(1 for l in ls if l.get("home_type") == "mobile"),
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

    subject_mobile = subject.get("home_type") == "mobile"

    def matches(l, scope):
        if l["key"] == subject["key"] or not _ppsf(l):
            return False
        if bool(l.get("waterfront")) != bool(subject.get("waterfront")):
            return False
        # Property type gate. Mobile/manufactured homes sell for roughly
        # two-thirds the $/sqft of slab-built houses here, so mixing them
        # makes mobile homes look wildly underpriced (and drags foundation
        # comps down). A mobile subject comps ONLY against known mobiles.
        #
        # Comps of unknown type (the MLS solds export has no property-type
        # column) are treated as non-mobile: that export is overwhelmingly
        # foundation-built, and mobile is ~5% of inventory. Deliberate
        # approximation — it disappears once a Property Sub Type column is
        # included in the export (ingest_mls.py already reads one).
        comp_mobile = l.get("home_type") == "mobile"
        if comp_mobile != subject_mobile:
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


def predict_prices(listings, solds, cfg, calibration=None):
    """Predicted value = median $/sqft of comps × sqft. Sold records (from MLS
    CSVs) are preferred comps; active/pending listings fill the gap.

    `calibration` (from town_calibration) scales each town's estimate by how
    far past estimates there missed real sales. `predicted_raw` keeps the
    uncorrected value: calibration is always learned from raw estimates, so
    the correction can't feed back on itself.
    """
    pool = solds + listings
    calibration = calibration or {}
    predictions = {}
    for l in listings:
        if not (l.get("sqft") and l.get("price")):
            continue
        comps = _find_comps(l, pool, cfg)
        if len(comps) < 3:
            continue
        ppsf = median([_ppsf(c) for c in comps])
        raw = ppsf * l["sqft"]
        factor = calibration.get(l["city"], {}).get("factor", 1.0)
        predictions[l["key"]] = {
            "predicted": round(raw * factor),
            "predicted_raw": round(raw),
            "calibration": factor,
            "comp_count": len(comps),
            "comp_ppsf": round(ppsf, 1),
        }
    return predictions


def _true_pairs(outcomes):
    """(outcome, raw estimate) for outcomes with a real MLS sale price."""
    return [(o, o.get("predicted_raw") or o["predicted"]) for o in outcomes
            if o.get("sold_price") and (o.get("predicted_raw") or o.get("predicted"))]


def town_calibration(outcomes, cfg):
    """Per-town correction learned from real sales: median(sold ÷ raw
    estimate), shrunk toward 1.0 by k pseudo-sales so a town with few sales
    barely moves. Self-updating: every MLS export adds matched sales.

    Validated Oct 2026 on a time split (train on listings that left the
    market before a cutoff, test after): median miss 13.3% -> 12.7%.
    """
    m = cfg["model"]
    k = m.get("calibration_k", 20)
    lo, hi = m.get("calibration_clamp", [0.8, 1.2])
    by_city = {}
    for o, raw in _true_pairs(outcomes):
        by_city.setdefault(o["city"], []).append(o["sold_price"] / raw)
    out = {}
    for city, ratios in sorted(by_city.items()):
        n = len(ratios)
        factor = (n * median(ratios) + k * 1.0) / (n + k)
        out[city] = {"factor": round(min(max(factor, lo), hi), 3), "n": n}
    return out


def _recent_price_cuts(events, days):
    """key -> largest price-cut % in the last `days` days."""
    if not events:
        return {}
    cutoff = date.today() - timedelta(days=days)
    out = {}
    for e in events:
        if e.get("event") != "price_cut" or not e.get("cut_pct"):
            continue
        try:
            when = date.fromisoformat(e["date"])
        except (ValueError, TypeError):
            continue
        if when >= cutoff:
            out[e["key"]] = max(out.get(e["key"], 0), e["cut_pct"])
    return out


def score_deals(listings, predictions, cfg, events=None):
    """Rank active listings by investment opportunity."""
    d, fmr_table = cfg["deals"], cfg["fmr"]
    recent_cut_pct = _recent_price_cuts(events, d.get("fresh_event_days", 2))
    deals = []
    eligible_types = d.get("eligible_types")
    for l in listings:
        p = predictions.get(l["key"])
        if not p or l["status"] != "active" or (l.get("price") or 0) < d["min_price"]:
            continue
        # Investors here buy slab-built houses to flip or rent — mobile homes,
        # condos, townhomes and land are out of scope for this feed. Unknown
        # type (None) is allowed through: most such listings are houses.
        if eligible_types and l.get("home_type") is not None \
                and l["home_type"] not in eligible_types:
            continue
        spread_pct = 100 * (p["predicted"] - l["price"]) / p["predicted"]
        beds = min(int(l.get("beds") or 3), 4)
        fmr = fmr_table.get(l["parish"], {}).get(beds)
        gross_yield = round(100 * fmr * 12 / l["price"], 1) if fmr else None
        dom = l.get("days_on_market") or 0
        # A spread past ~40% almost always means condition problems the model
        # can't see, not a bargain — cap its contribution to the ranking.
        # Everything else is CONTINUOUS on purpose: flat step bonuses made
        # dozens of deals tie at an identical score, and a stable sort then
        # froze the same picks at the top of the email every single day.
        score = min(spread_pct, 40)
        score += min(dom / d["stale_dom_days"], 2.0) * 5  # long sitters negotiate
        if gross_yield:
            score += max(0.0, min(gross_yield - 8.0, 8.0))  # rental strength
        if recent_cut_pct.get(l["key"]):
            score += min(recent_cut_pct[l["key"]], 10.0)  # motivated seller, right now
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
                                     "home_type", "lat", "lng", "avm_estimate",
                                     "own_listing")},
            "predicted": p["predicted"], "spread_pct": round(spread_pct, 1),
            "comp_count": p["comp_count"], "gross_yield_pct": gross_yield,
            "recent_cut_pct": recent_cut_pct.get(l["key"]),
            "score": round(score, 2), "flags": flags,
        })
    deals.sort(key=lambda x: -x["score"])
    return deals


def _in_focus(listing, d):
    """In Catherine's main working areas (config deals.focus_*)."""
    return (listing.get("parish") in d.get("focus_parishes", [])
            or listing.get("city") in d.get("focus_cities", []))


def _days_since_featured(key, history, today):
    rec = history.get(key)
    if not rec or not rec.get("last_featured"):
        return None
    try:
        return (today - date.fromisoformat(rec["last_featured"])).days
    except (ValueError, TypeError):
        return None


def select_daily_deals(deals, events, history, cfg):
    """Choose which of the qualifying deals to actually send today.

    Sending the raw top-N froze the same houses into the email every day (the
    pool is ~200 deep). Instead: fill some slots with genuinely fresh activity,
    fill the rest by score from deals not featured recently, and only fall back
    to repeats when there is nothing else. Each pick carries a `reason` so the
    email can say WHY it's there and vary its framing.
    """
    d = cfg["deals"]
    top_n = d["top_n"]
    cooldown = d.get("cooldown_days", 10)
    today = date.today()
    fresh_days = d.get("fresh_event_days", 2)
    cutoff = today - timedelta(days=fresh_days)

    fresh_reason = {}
    for e in events or []:
        if e.get("event") not in ("new", "price_cut"):
            continue
        try:
            when = date.fromisoformat(e["date"])
        except (ValueError, TypeError):
            continue
        if when < cutoff:
            continue
        # Each piece of news gets its moment exactly once: if we already
        # featured this listing on or after the event, it isn't news anymore
        # (otherwise the same "fresh" homes refill these slots every day).
        last = (history.get(e["key"]) or {}).get("last_featured")
        if last:
            try:
                if date.fromisoformat(last) >= when:
                    continue
            except (ValueError, TypeError):
                pass
        # a price cut is the stronger story, so let it win over "new"
        if e["event"] == "price_cut" or e["key"] not in fresh_reason:
            fresh_reason[e["key"]] = e["event"]

    def days_since_featured(deal):
        return _days_since_featured(deal["key"], history, today)

    picked, used = [], set()

    def take(deal, reason):
        picked.append({**deal, "reason": reason,
                       "times_featured": (history.get(deal["key"], {})
                                          .get("times_featured", 0))})
        used.add(deal["key"])

    # 1. fresh activity first — new listings and this week's price cuts,
    #    her focus areas ahead of the rest (stable sort keeps score order)
    for deal in sorted(deals, key=lambda x: not _in_focus(x, d)):
        if len(picked) >= min(d.get("fresh_slots", 4), top_n):
            break
        if deal["key"] in fresh_reason and deal["key"] not in used:
            take(deal, fresh_reason[deal["key"]])

    # 1b. top up her focus areas to focus_min from deals outside the cooldown
    focus_min = min(d.get("focus_min", 0), top_n)
    for deal in deals:
        if len(picked) >= top_n or sum(_in_focus(x, d) for x in picked) >= focus_min:
            break
        if deal["key"] in used or not _in_focus(deal, d):
            continue
        since = days_since_featured(deal)
        if since is None or since >= cooldown:
            take(deal, "top_score" if since is None else "resurfacing")

    # 1c. her areas ran dry inside the cooldown? bring back benched focus
    #     deals, longest-unseen first, rather than drift back to Bossier City
    short = focus_min - sum(_in_focus(x, d) for x in picked)
    if short > 0 and len(picked) < top_n:
        benched = [x for x in deals if x["key"] not in used and _in_focus(x, d)]
        benched.sort(key=lambda x: (-(days_since_featured(x) or 0), -x["score"]))
        for deal in benched[: min(short, top_n - len(picked))]:
            take(deal, "still_available")

    # 2. best scores that haven't been featured inside the cooldown window
    for deal in deals:
        if len(picked) >= top_n:
            break
        if deal["key"] in used:
            continue
        since = days_since_featured(deal)
        if since is None or since >= cooldown:
            take(deal, "top_score" if since is None else "resurfacing")

    # 3. still short? bring back benched deals, longest-unseen first
    if len(picked) < top_n:
        benched = [x for x in deals if x["key"] not in used]
        benched.sort(key=lambda x: (-(days_since_featured(x) or 0), -x["score"]))
        for deal in benched[: top_n - len(picked)]:
            take(deal, "still_available")

    return {"updated": today.isoformat(),
            "pool_size": len(deals),
            "high_opportunity": any(x["spread_pct"] >= d["high_opportunity_spread_pct"]
                                    for x in picked),
            "deals": picked}


def select_new_builds(listings, history, cfg):
    """A few new-construction homes for her buyers on the configured weekdays.

    Not investments (new builds rarely score as underpriced), so they bypass
    the deal model. Rotates through the market with its own cooldown, her
    focus areas first, freshest listings first within each group.
    """
    nb = cfg.get("new_builds") or {}
    today = date.today()
    if today.strftime("%A") not in nb.get("weekdays", []):
        return []
    d = cfg["deals"]
    eligible_types = d.get("eligible_types")
    min_year = today.year - nb.get("max_age_years", 1)
    candidates = [
        l for l in listings
        if l.get("status") == "active"
        and (l.get("year_built") or 0) >= min_year
        and (l.get("price") or 0) >= d["min_price"]
        and (not eligible_types or l.get("home_type") is None
             or l["home_type"] in eligible_types)]
    cooldown = nb.get("cooldown_days", 14)

    def since(l):
        return _days_since_featured(l["key"], history, today)

    rested = [l for l in candidates if since(l) is None or since(l) >= cooldown]
    if rested:
        rested.sort(key=lambda l: (not _in_focus(l, d), l.get("days_on_market") or 0))
        chosen = rested
    else:  # everything shown recently: longest-unseen first
        chosen = sorted(candidates, key=lambda l: -(since(l) or 0))
    # one per town first so a single big subdivision can't fill every slot
    count, picks, towns = nb.get("count", 2), [], set()
    for l in chosen:
        if len(picks) < count and l["city"] not in towns:
            picks.append(l)
            towns.add(l["city"])
    picks += [l for l in chosen if l not in picks][: count - len(picks)]
    out = []
    for l in picks:
        out.append({
            **{f: l.get(f) for f in ("key", "address", "city", "parish", "zip",
                                     "price", "beds", "baths", "sqft", "year_built",
                                     "days_on_market", "subdivision", "url",
                                     "own_listing")},
            "ppsf": round(l["price"] / l["sqft"], 1) if l.get("sqft") else None,
        })
    return out


def update_history(history, selection, live_keys):
    """Record what we featured today; forget listings that left the market."""
    today = date.today().isoformat()
    for deal in selection["deals"] + selection.get("new_builds", []):
        rec = history.setdefault(deal["key"], {"first_featured": today,
                                               "times_featured": 0})
        rec["last_featured"] = today
        rec["times_featured"] = rec.get("times_featured", 0) + 1
    return {k: v for k, v in history.items() if k in live_keys}


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
            "predicted_raw": pred.get("predicted_raw", pred["predicted"]),
            "predicted_at": e["date"], "proxy_price": e["last_price"],
            "sold_price": None, "sold_date": None,
        })
    return outcomes


def _accuracy(signed, min_n=1):
    """Summary of signed errors (estimate ÷ actual − 1)."""
    if len(signed) < min_n:
        return None
    errs = [abs(e) for e in signed]
    return {
        "n": len(errs),
        # median is the AVM-standard headline: robust to distressed/teardown
        # sales that no size-based model can price
        "median_err_pct": round(100 * median(errs), 1),
        "lean_pct": round(100 * median(signed), 1),  # + = estimates run high
        "within_10pct": round(100 * sum(1 for e in errs if e <= 0.10) / len(errs), 1),
    }


def _by_city(pairs, min_n=10):
    """pairs of (city, signed error) -> per-town accuracy for towns with min_n."""
    groups = {}
    for city, e in pairs:
        groups.setdefault(city, []).append(e)
    return {c: _accuracy(v) for c, v in sorted(groups.items()) if len(v) >= min_n}


def backtest(solds, cfg, max_n=1000):
    """Leave-one-out accuracy against real MLS sales: predict each sold home
    from the other solds' $/sqft and compare to its actual close price.
    Uses the most recent max_n sales so the number tracks today's market."""
    from ingest_mls import parse_date
    recent = sorted(solds, key=lambda s: parse_date(s.get("sold_date")) or date.min,
                    reverse=True)
    pairs = []
    for s in recent[:max_n]:
        if not (s.get("sqft") and s.get("price")):
            continue
        comps = _find_comps(s, solds, cfg)
        if len(comps) < 3:
            continue
        predicted = median([_ppsf(c) for c in comps]) * s["sqft"]
        pairs.append((s["city"], predicted / s["price"] - 1))
    if not pairs:
        return None
    errs = [abs(e) for _, e in pairs]
    return {
        **_accuracy([e for _, e in pairs]),
        "mape_pct": round(100 * sum(errs) / len(errs), 1),
        "by_city": _by_city(pairs),
    }


def model_metrics(outcomes):
    """Rolling accuracy vs actual (MLS) or proxy (last list) prices, plus the
    live estimates' accuracy against real sales alone, overall and by town."""
    errs = []
    for o in outcomes:
        actual = o.get("sold_price") or o.get("proxy_price")
        if actual and o.get("predicted"):
            errs.append(abs(o["predicted"] - actual) / actual)
    true = [(o["city"], o["predicted"] / o["sold_price"] - 1)
            for o in outcomes if o.get("sold_price") and o.get("predicted")]
    return {
        "updated": date.today().isoformat(),
        "n_outcomes": len(errs),
        "n_true_solds": len(true),
        "mape_pct": round(100 * sum(errs) / len(errs), 1) if errs else None,
        "within_10pct": round(100 * sum(1 for e in errs if e <= 0.10) / len(errs), 1) if errs else None,
        "live_vs_sold": _accuracy([e for _, e in true]),
        "live_by_city": _by_city(true),
    }
