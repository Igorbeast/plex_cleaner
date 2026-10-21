import requests

from app.config import ServiceConfig


class SeerrClient:
    def __init__(self, config: ServiceConfig):
        self.url = config.url
        self.headers = {"X-Api-Key": config.api_key}
        self.timeout = config.timeout_seconds

    def find_media_id(self, media_type: str, tmdb_id: int):
        kind = "movie" if media_type == "movie" else "tv"
        r = requests.get(f"{self.url}/api/v1/{kind}/{tmdb_id}", headers=self.headers, timeout=self.timeout)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return (r.json().get("mediaInfo") or {}).get("id")

    def delete_media(self, media_id: int) -> None:
        r = requests.delete(f"{self.url}/api/v1/media/{media_id}", headers=self.headers, timeout=self.timeout)
        r.raise_for_status()
