"""
Eenvoudige JSON-opslag voor kandidaten, uitzonderingen en beslissingen.

Belangrijk: dit bestand voert NOOIT een verwijdering uit. Het registreert
alleen beslissingen (uitgesloten / goedgekeurd) zodat een latere,
afzonderlijke fase daarop kan handelen via de Radarr/Sonarr API.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path("/data")
CANDIDATES_FILE = DATA_DIR / "candidates.json"
EXCEPTIONS_FILE = DATA_DIR / "exceptions.json"
DECISIONS_FILE = DATA_DIR / "decisions.json"


def _read_json(path: Path, default):
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


# --- Kandidaten (laatste scan) -------------------------------------------

def save_candidates(results: list[dict]) -> None:
    serializable = []
    for row in results:
        c = row["candidate"]
        item = asdict(c)
        for key in ("added_at", "last_viewed_at"):
            if item.get(key) is not None:
                item[key] = item[key].isoformat()
        serializable.append({"library": row["library"], "candidate": item})

    payload = {
        "scanned_at": datetime.now(tz=timezone.utc).isoformat(),
        "count": len(serializable),
        "results": serializable,
    }
    _write_json(CANDIDATES_FILE, payload)


def load_candidates() -> dict | None:
    if not CANDIDATES_FILE.exists():
        return None
    return _read_json(CANDIDATES_FILE, None)


# --- Uitzonderingen ("nooit voorstellen") ---------------------------------

def load_exceptions() -> set[str]:
    data = _read_json(EXCEPTIONS_FILE, {"rating_keys": []})
    return set(data.get("rating_keys", []))


def load_exceptions_full() -> dict:
    """Geeft de volledige uitzonderingen-data terug (met titel + tijdstip), voor de geschiedenispagina."""
    return _read_json(EXCEPTIONS_FILE, {"rating_keys": [], "details": {}})


def add_exception(rating_key: str, title: str = "") -> None:
    data = _read_json(EXCEPTIONS_FILE, {"rating_keys": [], "details": {}})
    keys = set(data.get("rating_keys", []))
    keys.add(rating_key)
    details = data.get("details", {})
    details[rating_key] = {
        "title": title,
        "excluded_at": datetime.now(tz=timezone.utc).isoformat(),
    }
    _write_json(EXCEPTIONS_FILE, {"rating_keys": sorted(keys), "details": details})


def remove_exception(rating_key: str) -> None:
    data = _read_json(EXCEPTIONS_FILE, {"rating_keys": [], "details": {}})
    keys = set(data.get("rating_keys", []))
    keys.discard(rating_key)
    details = data.get("details", {})
    details.pop(rating_key, None)
    _write_json(EXCEPTIONS_FILE, {"rating_keys": sorted(keys), "details": details})


# --- Beslissingen (goedkeuren) --------------------------------------------

def load_decisions() -> dict:
    return _read_json(DECISIONS_FILE, {})


def record_decision(rating_key: str, action: str, title: str = "") -> None:
    decisions = _read_json(DECISIONS_FILE, {})
    decisions[rating_key] = {
        "action": action,
        "title": title,
        "decided_at": datetime.now(tz=timezone.utc).isoformat(),
    }
    _write_json(DECISIONS_FILE, decisions)
