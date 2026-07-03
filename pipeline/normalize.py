"""Dedupe/merge listings from multiple sources by canonicalized address."""

import re

_ABBREV = {
    "STREET": "ST", "AVENUE": "AVE", "BOULEVARD": "BLVD", "DRIVE": "DR",
    "ROAD": "RD", "LANE": "LN", "COURT": "CT", "CIRCLE": "CIR", "PLACE": "PL",
    "HIGHWAY": "HWY", "PARKWAY": "PKWY", "NORTH": "N", "SOUTH": "S",
    "EAST": "E", "WEST": "W", "TRAIL": "TRL", "COVE": "CV", "POINT": "PT",
}


def canon_key(address, city):
    """'123 North Main Street' / Minden -> '123 N MAIN ST|MINDEN'"""
    a = re.sub(r"[^A-Z0-9 ]", "", (address or "").upper())
    words = [_ABBREV.get(w, w) for w in a.split()]
    return " ".join(words) + "|" + (city or "").upper().strip()


def merge(listings):
    """Merge duplicate listings across sources. Prefers non-null field values;
    on conflict keeps zillow's (arbitrary but stable)."""
    by_key = {}
    for lst in listings:
        key = canon_key(lst["address"], lst["city"])
        if len(key) < 8:  # unparseable address — drop
            continue
        if key not in by_key:
            by_key[key] = dict(lst)
            by_key[key]["key"] = key
            by_key[key]["sources"] = [lst["source"]]
        else:
            cur = by_key[key]
            for f, v in lst.items():
                if v is not None and cur.get(f) is None:
                    cur[f] = v
            cur["waterfront"] = cur["waterfront"] or lst["waterfront"]
            if lst["source"] not in cur["sources"]:
                cur["sources"].append(lst["source"])
    return list(by_key.values())
