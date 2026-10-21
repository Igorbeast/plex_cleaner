from dataclasses import dataclass
import requests

from .config import AppConfig, ServiceConfig


@dataclass
class HealthStatus:
    name: str
    online: bool
    status_code: int | None = None
    message: str = ""


def check_service(service: ServiceConfig) -> HealthStatus:
    try:
        headers = {}

        if service.name == "plex" and service.api_key:
            headers["X-Plex-Token"] = service.api_key
            headers["X-Plex-Client-Identifier"] = "plex-cleaner"

        response = requests.get(
            service.url,
            headers=headers,
            timeout=service.timeout_seconds,
        )

        return HealthStatus(
            name=service.name,
            online=True,
            status_code=response.status_code,
            message=f"HTTP {response.status_code}",
        )

    except requests.RequestException as exc:
        return HealthStatus(
            name=service.name,
            online=False,
            message=str(exc),
        )


def check_all_services(config: AppConfig) -> list[HealthStatus]:
    return [
        check_service(service)
        for service in config.services.values()
    ]
