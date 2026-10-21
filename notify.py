import os

import requests


def send_discord(message: str) -> bool:
    """Stuurt een bericht naar Discord. False als er geen webhook is of het mislukt."""
    url = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    if not url:
        return False
    try:
        response = requests.post(url, json={"content": message}, timeout=10)
        response.raise_for_status()
        return True
    except requests.RequestException:
        return False
