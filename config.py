from dataclasses import dataclass
from pathlib import Path
import os
import json
import yaml

class ConfigError(Exception):
    pass

@dataclass
class ServiceConfig:
    name: str
    url: str
    api_key: str
    required: bool = True
    timeout_seconds: int = 10

@dataclass
class AppConfig:
    dry_run: bool
    log_level: str
    services: dict[str, ServiceConfig]
    libraries: list[str]
    never_watched_min_age_days: int
    fully_watched_min_days_since_watch: int

API_KEY_ENV = {
    "plex": "PLEX_TOKEN",
    "tautulli": "TAUTULLI_API_KEY",
    "sonarr": "SONARR_API_KEY",
    "radarr": "RADARR_API_KEY",
    "seerr": "SEERR_API_KEY",
}

def load_config(config_path: str = None) -> AppConfig:
    if config_path is None:
        if Path("/config/config.json").exists():
            config_path = "/config/config.json"
        elif Path("/config/config.yaml").exists():
            config_path = "/config/config.yaml"
        else:
            config_path = "/config/config.yaml"

    path = Path(config_path)

    if not path.exists():
        raise ConfigError(f"Configbestand niet gevonden: {path}")

    with path.open("r", encoding="utf-8") as file:
        if path.suffix == ".json":
            raw = json.load(file) or {}
        else:
            raw = yaml.safe_load(file) or {}

    general = raw.get("general", {})
    services_raw = raw.get("services", {})
    retention = raw.get("retention", {})

    services = {}

    for name, service in services_raw.items():
        url = service.get("url")

        if not url:
            raise ConfigError(f"Geen URL ingesteld voor service '{name}'")

        env_name = API_KEY_ENV.get(name)
        api_key = service.get("api_key") or service.get("token") or (os.environ.get(env_name, "") if env_name else "")

        services[name] = ServiceConfig(
            name=name,
            url=url.rstrip("/"),
            api_key=api_key,
            required=service.get("required", True),
            timeout_seconds=service.get("timeout_seconds", 10),
        )

    libraries = raw.get("libraries", ["Movies", "TV Shows"])

    return AppConfig(
        dry_run=general.get("dry_run", True),
        log_level=general.get("log_level", "INFO"),
        services=services,
        libraries=libraries,
        never_watched_min_age_days=retention.get("never_watched_min_age_days", 90),
        fully_watched_min_days_since_watch=retention.get("fully_watched_min_days_since_watch", 60),
    )
