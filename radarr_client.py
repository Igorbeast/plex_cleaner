"""
API-client voor Radarr (v3 API).
"""

from __future__ import annotations
import requests
from ..config import ServiceConfig

class RadarrClient:
    def __init__(self, config: ServiceConfig):
        self.config = config

    def _headers(self) -> dict:
        return {
            "X-Api-Key": self.config.api_key,
            "Accept": "application/json"
        }

    def get_movies(self) -> list[dict]:
        url = f"{self.config.url.rstrip('/')}/api/v3/movie"
        params = {"apikey": self.config.api_key}
        
        response = requests.get(
            url,
            headers=self._headers(),
            params=params,
            timeout=self.config.timeout_seconds
        )
        response.raise_for_status()
        return response.json()

    def build_tmdb_index(self) -> dict[int, dict]:
        movies = self.get_movies()
        return {m["tmdbId"]: m for m in movies if m.get("tmdbId")}

    def delete_movie(self, movie_id: int) -> None:
        """Verwijdert een film via Radarr, inclusief bestand. Alleen aanroepen
        vanuit een route die al dry_run, goedkeuring en koppeling heeft gecheckt."""
        url = f"{self.config.url.rstrip('/')}/api/v3/movie/{movie_id}"
        response = requests.delete(
            url,
            headers=self._headers(),
            params={"deleteFiles": "true", "addImportExclusion": "false"},
            timeout=self.config.timeout_seconds,
        )
        response.raise_for_status()
