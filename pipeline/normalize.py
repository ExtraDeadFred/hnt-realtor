"""Dedupe/merge listings from multiple sources by canonicalized address."""

import re

_ABBREV = {
    "STREET": "ST", "AVENUE": "AVE", "BOULEVARD": "BLVD", "DRIVE": "DR",
    "ROAD": "RD", "LANE": "LN", "COURT": "CT", "CIRCLE": "CIR", "PLACE": "PL",
    "HIGHWAY": "HWY", "PARKWAY": "PKWY", "NORTH": "N", "SOUTH": "S",
    "EAST": "E", "WEST": "W", "TRAIL": "TRL", "COVE": "CV", "POINT": "PT",
}


# Explicit property-type labels as the various sources spell them.
_STYLE_MAP = {
    "MOBILE": "mobile", "MANUFACTURED": "mobile", "MOBILE_HOME": "mobile",
    "MANUFACTUREDHOME": "mobile", "MANUFACTURED HOME": "mobile",
    "SINGLE_FAMILY": "single_family", "SINGLEFAMILYRESIDENCE": "single_family",
    "SINGLE FAMILY RESIDENCE": "single_family", "SFR": "single_family",
    "MULTI_FAMILY": "multi_family", "MULTIFAMILY": "multi_family",
    "DUPLEX": "multi_family", "TRIPLEX": "multi_family", "QUADRUPLEX": "multi_family",
    "APARTMENT": "multi_family",
    "CONDOS": "condo", "CONDO": "condo", "CONDOMINIUM": "condo",
    "TOWNHOMES": "townhome", "TOWNHOUSE": "townhome", "TOWNHOME": "townhome",
    "LAND": "land", "LOT": "land", "FARM": "land", "UNIMPROVEDLAND": "land",
}

# Free-text tells, for sources that give no structured type (Firecrawl
# fallback, and any MLS export lacking a Property Sub Type column).
_MOBILE_WORDS = ("mobile home", "manufactured home", "manufactured housing",
                 "trailer home", "doublewide", "double wide", "singlewide",
                 "single wide", "mobile/manufactured", " mfd ", " mh ")


def classify_home_type(style=None, text=None, address=None):
    """-> 'mobile' | 'single_family' | 'multi_family' | 'condo' | 'townhome'
    | 'land' | None.

    An explicit style from the source wins. Otherwise look for mobile-home
    tells in the description/address. Returns None when genuinely unknown —
    callers must decide what to do with that rather than get a wrong guess.
    """
    if style:
        mapped = _STYLE_MAP.get(str(style).strip().upper().replace("-", "_"))
        if mapped:
            return mapped
    blob = f" {(text or '')} {(address or '')} ".lower()
    if any(w in blob for w in _MOBILE_WORDS):
        return "mobile"
    return None


def canon_key(address, city):
    """'123 North Main Street, Minden, LA 71055' / Minden -> '123 N MAIN ST|MINDEN'
    The street part is everything before the first comma — sources differ on
    whether they append city/state/zip."""
    a = re.sub(r"[^A-Z0-9 ]", "", (address or "").split(",")[0].upper())
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
