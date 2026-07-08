"""HUD eGIS client: subsidized-housing point datasets (LIHTC, public
housing) via generic ArcGIS FeatureServer queries.

CLAUDE CODE: the FeatureServer URLs live in config (hud_layers) and are
placeholders until you look them up on hudgis-hud.opendata.arcgis.com
(search "LIHTC" and "Public Housing Developments"; copy the layer's
FeatureServer/<n> URL). This client only assumes standard ArcGIS query
semantics (f=json, outFields=*, geometry envelope filter, pagination via
resultOffset).
"""

from __future__ import annotations

import logging
import math
from typing import Any

import requests

from .cache import Cache

log = logging.getLogger(__name__)

TIMEOUT = 120
PAGE_SIZE = 1000

# Bounding box covering the seven NW Louisiana parishes with margin.
NWLA_BBOX = {"xmin": -94.1, "ymin": 31.8, "xmax": -92.2, "ymax": 33.1}


def load_points(cache: Cache, name: str, layer_url: str,
                bbox: dict[str, float] = NWLA_BBOX) -> list[dict[str, Any]]:
    """Fetch all points for a layer within bbox. Returns
    [{'lat', 'lon', 'name', 'attrs'}]. Cached ~90 days."""
    if "PLACEHOLDER" in layer_url:
        log.warning("hud layer '%s' URL not configured yet; skipping", name)
        return []
    cached = cache.get("hud_points", name)
    if cached is not None:
        return cached

    points: list[dict[str, Any]] = []
    offset = 0
    while True:
        params = {
            "f": "json",
            "where": "1=1",
            "outFields": "*",
            "returnGeometry": "true",
            "outSR": "4326",
            "geometry": f"{bbox['xmin']},{bbox['ymin']},{bbox['xmax']},{bbox['ymax']}",
            "geometryType": "esriGeometryEnvelope",
            "inSR": "4326",
            "spatialRel": "esriSpatialRelIntersects",
            "resultOffset": offset,
            "resultRecordCount": PAGE_SIZE,
        }
        r = requests.get(f"{layer_url}/query", params=params, timeout=TIMEOUT)
        r.raise_for_status()
        data = r.json()
        if "error" in data:
            raise RuntimeError(f"ArcGIS error for {name}: {data['error']}")
        feats = data.get("features", [])
        for f in feats:
            geom = f.get("geometry") or {}
            attrs = f.get("attributes") or {}
            if "y" in geom and "x" in geom:
                points.append({
                    "lat": geom["y"], "lon": geom["x"],
                    "name": _best_name(attrs), "attrs": attrs,
                })
        if not data.get("exceededTransferLimit") and len(feats) < PAGE_SIZE:
            break
        offset += PAGE_SIZE

    cache.set("hud_points", name, points)
    log.info("hud layer '%s': %d points cached", name, len(points))
    return points


def _best_name(attrs: dict[str, Any]) -> str:
    for key in ("PROJECT", "PROJ_NAME", "PROJECT_NAME", "NAME",
                "DEVELOPMENT_NAME", "PROPERTY_NAME"):
        for k, v in attrs.items():
            if k.upper() == key and v:
                return str(v)
    return "unnamed"


def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 3958.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def proximity(listing_lat: float, listing_lon: float,
              points: list[dict[str, Any]], radius_miles: float) -> dict[str, Any]:
    """Nearest distance and count within radius for one point set."""
    if not points:
        return {"nearest_miles": None, "nearest_name": None, "count_within_radius": None}
    nearest, nearest_name, within = float("inf"), None, 0
    for p in points:
        d = haversine_miles(listing_lat, listing_lon, p["lat"], p["lon"])
        if d < nearest:
            nearest, nearest_name = d, p["name"]
        if d <= radius_miles:
            within += 1
    return {"nearest_miles": round(nearest, 2),
            "nearest_name": nearest_name,
            "count_within_radius": within}
