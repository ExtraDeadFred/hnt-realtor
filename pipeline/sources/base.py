"""Common listing schema. Every source adapter (scraper today, IDX/MLS API
later) returns a list of these dicts — downstream code never knows the source."""

from datetime import date

# Fields every adapter must populate (None when unknown)
LISTING_FIELDS = [
    "address", "city", "parish", "zip", "price", "beds", "baths", "sqft",
    "lot_acres", "year_built", "status", "days_on_market", "url", "photo_url",
    "lat", "lng", "waterfront", "source", "scraped_at",
]

# JSON schema handed to Firecrawl's LLM extraction for search-result pages
EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "listings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "address": {"type": "string"},
                    "city": {"type": "string"},
                    "zip": {"type": "string"},
                    "price": {"type": "number"},
                    "beds": {"type": "number"},
                    "baths": {"type": "number"},
                    "sqft": {"type": "number"},
                    "lot_acres": {"type": "number"},
                    "year_built": {"type": "number"},
                    "status": {"type": "string"},
                    "days_on_market": {"type": "number"},
                    "url": {"type": "string"},
                    "photo_url": {"type": "string"},
                },
                "required": ["address", "price"],
            },
        }
    },
    "required": ["listings"],
}

EXTRACT_PROMPT = (
    "Extract every property listing card on this real-estate search results "
    "page. status should be one of: active, pending, contingent, coming_soon. "
    "days_on_market is the 'X days on market/Zillow' number if shown. "
    "url must be the full link to the listing's detail page. Skip ads and "
    "'similar homes' sections."
)


def make_listing(raw, area, source):
    """Normalize one extracted card into the common schema."""
    lst = {f: raw.get(f) for f in LISTING_FIELDS}
    lst["city"] = raw.get("city") or area["city"]
    lst["parish"] = area["parish"]
    lst["waterfront"] = "waterfront" in area.get("tags", [])
    lst["status"] = (raw.get("status") or "active").strip().lower().replace(" ", "_")
    lst["source"] = source
    lst["scraped_at"] = date.today().isoformat()
    for numf in ("price", "beds", "baths", "sqft", "lot_acres", "year_built", "days_on_market"):
        v = lst.get(numf)
        if v is not None:
            try:
                lst[numf] = float(v) if numf in ("baths", "lot_acres") else int(float(v))
            except (TypeError, ValueError):
                lst[numf] = None
    # Extraction fills 0 for fields the search card doesn't show — treat as
    # unknown. (Also days_on_market: a real "listed today" is indistinguishable
    # from "not shown", and the zeros were dragging every DOM median to 0.)
    for numf in ("price", "beds", "baths", "sqft", "lot_acres", "year_built",
                 "days_on_market"):
        if lst.get(numf) == 0:
            lst[numf] = None
    return lst
