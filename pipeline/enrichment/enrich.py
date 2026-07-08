"""Orchestrator: enrich a listing with tract trends, HUD proximity,
crime trends, and a composite score."""

from __future__ import annotations

import logging
from typing import Any

import yaml

from .cache import Cache
from . import geocode, acs, hud, crime, scoring

log = logging.getLogger(__name__)


class Enricher:
    def __init__(self, config_path: str):
        raw = yaml.safe_load(open(config_path))
        self.cfg = raw["enrichment"] if "enrichment" in raw else raw
        self.cache = Cache(self.cfg.get("cache_db_path", "data/enrichment_cache.db"))
        self._hud_points: dict[str, list] | None = None
        self._agencies: list | None = None
        self._parish_by_fips = {p["fips"]: p["name"]
                                for p in self.cfg.get("parishes", [])}

    # -- lazy shared datasets -------------------------------------------------
    def hud_points(self) -> dict[str, list]:
        if self._hud_points is None:
            self._hud_points = {
                name: hud.load_points(self.cache, name, url)
                for name, url in (self.cfg.get("hud_layers") or {}).items()
            }
        return self._hud_points

    def agencies(self) -> list:
        if self._agencies is None:
            try:
                self._agencies = crime.agency_directory(self.cache, "LA")
            except Exception:
                log.exception("agency directory unavailable")
                self._agencies = []
        return self._agencies

    # -- main entry -----------------------------------------------------------
    def enrich_listing(self, listing: dict[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {}

        tract = geocode.tract_for_listing(self.cache, listing)
        out["tract"] = tract
        if tract:
            out["parish"] = self._parish_by_fips.get(tract["county"])
            try:
                out["acs_trends"] = acs.tract_trends(
                    self.cache, tract["geoid"],
                    self.cfg.get("acs_years", [2013, 2018, 2023]),
                    tract["state"], tract["county"])
            except Exception:
                log.exception("ACS trends failed for %s", tract["geoid"])

        lat, lon = listing.get("latitude"), listing.get("longitude")
        if lat is not None and lon is not None:
            radius = float(self.cfg.get("hud_radius_miles", 1.0))
            out["hud"] = {
                name: hud.proximity(float(lat), float(lon), pts, radius)
                for name, pts in self.hud_points().items()
            }

        agency = crime.find_agency(self.agencies(), listing.get("city"),
                                   out.get("parish"))
        if agency and agency.get("ori"):
            try:
                out["crime"] = crime.agency_crime_trend(
                    self.cache, agency["ori"],
                    agency.get("agency_name", agency["ori"]),
                    int(self.cfg.get("crime_lookback_years", 5)))
            except Exception:
                log.exception("crime trend failed for %s", agency.get("ori"))

        out["score"] = scoring.score(out)
        return out

    def close(self) -> None:
        self.cache.close()
