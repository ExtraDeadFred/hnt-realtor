"""Zillow search-results adapter (via Firecrawl)."""

from firecrawl import scrape_extract
from sources.base import EXTRACT_PROMPT, EXTRACT_SCHEMA, make_listing


def fetch(area, cfg):
    slug = area.get("zillow_slug")
    if not slug:
        return []
    listings = []
    for page in range(1, cfg["scrape"]["max_pages"] + 1):
        url = f"https://www.zillow.com/{slug}/"
        if page > 1:
            url += f"{page}_p/"
        result = scrape_extract(url, EXTRACT_SCHEMA, EXTRACT_PROMPT,
                                cfg["scrape"]["timeout_seconds"])
        cards = (result or {}).get("listings") or []
        for raw in cards:
            u = raw.get("url") or ""
            if u.startswith("/"):
                raw["url"] = "https://www.zillow.com" + u
            listings.append(make_listing(raw, area, "zillow"))
        if len(cards) < 20:  # short page — no further pages
            break
    return listings
