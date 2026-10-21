import requests

from ..config import ServiceConfig


class PlexClient:
    def __init__(self, config: ServiceConfig):
        self.config = config

    def _headers(self):
        return {
            "X-Plex-Token": self.config.api_key,
            "X-Plex-Client-Identifier": "plex-cleaner",
            "Accept": "application/json",
        }

    def get_identity(self):
        response = requests.get(
            f"{self.config.url}/identity",
            headers=self._headers(),
            timeout=self.config.timeout_seconds,
        )
        response.raise_for_status()
        return response.json()

    def get_libraries(self):
        response = requests.get(
            f"{self.config.url}/library/sections",
            headers=self._headers(),
            timeout=self.config.timeout_seconds,
        )
        response.raise_for_status()
        return response.json()

    def get_library_items(self, library_key):
        response = requests.get(
            f"{self.config.url}/library/sections/{library_key}/all",
            headers=self._headers(),
            params={
                "includeGuids": 1,
                "includeOnDeck": 1,
            },
            timeout=self.config.timeout_seconds,
        )
        response.raise_for_status()
        return response.json()
