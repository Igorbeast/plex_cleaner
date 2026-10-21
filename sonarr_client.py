import requests
import logging

logger = logging.getLogger(__name__)

class SonarrClient:
    def __init__(self, config):
        self.url = config.url.rstrip("/")
        self.api_key = config.api_key
        self.headers = {"X-Api-Key": self.api_key}
        self.timeout = config.timeout_seconds

    def get_series(self) -> list[dict]:
        endpoint = f"{self.url}/api/v3/series"
        try:
            response = requests.get(endpoint, headers=self.headers, timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Fout bij ophalen series uit Sonarr: {e}")
            return []

    def build_tvdb_index(self) -> dict[int, dict]:
        series_list = self.get_series()
        return {s["tvdbId"]: s for s in series_list if s.get("tvdbId")}

    def delete_series(self, series_id: int) -> None:
        """Verwijdert een serie via Sonarr, inclusief bestanden. Alleen aanroepen
        vanuit een route die al dry_run, goedkeuring en koppeling heeft gecheckt."""
        url = f"{self.url}/api/v3/series/{series_id}"
        response = requests.delete(
            url,
            headers=self.headers,
            params={"deleteFiles": "true", "addImportListExclusion": "false"},
            timeout=self.timeout,
        )
        response.raise_for_status()
