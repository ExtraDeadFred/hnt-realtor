"""Thin Firecrawl REST client (v1 /scrape with LLM extraction)."""

import os
import time

import requests

API_BASE = "https://api.firecrawl.dev/v1"


def scrape_extract(url, schema, prompt, timeout_seconds=90):
    """Scrape `url` and return the extracted object, or None on failure."""
    key = os.environ.get("FIRECRAWL_API_KEY")
    if not key:
        raise RuntimeError("FIRECRAWL_API_KEY is not set")

    body = {
        "url": url,
        "formats": ["extract"],
        "extract": {"schema": schema, "prompt": prompt},
        "timeout": timeout_seconds * 1000,
    }
    for attempt in (1, 2):
        try:
            r = requests.post(
                f"{API_BASE}/scrape",
                json=body,
                headers={"Authorization": f"Bearer {key}"},
                timeout=timeout_seconds + 30,
            )
            if r.status_code == 429:  # rate limited — back off and retry
                time.sleep(15 * attempt)
                continue
            r.raise_for_status()
            data = r.json()
            if data.get("success") and data.get("data", {}).get("extract") is not None:
                return data["data"]["extract"]
            print(f"  firecrawl: no extract for {url}: {str(data)[:200]}")
            return None
        except requests.RequestException as e:
            print(f"  firecrawl: attempt {attempt} failed for {url}: {e}")
            time.sleep(5)
    return None
