from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class Candidate:
    rating_key: str
    title: str
    type: str
    reason: str
    deletable: bool
    tmdb_id: int | None = None
    tvdb_id: int | None = None
    imdb_id: str | None = None
    added_at: datetime | None = None
    last_viewed_at: datetime | None = None
    view_count: int = 0


def _parse_timestamp(value) -> datetime | None:
    if value is None or value == "":
        return None

    try:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value, tz=timezone.utc)

        value = str(value)

        # Plex timestamps are normally Unix timestamps, but support ISO too.
        if value.isdigit():
            return datetime.fromtimestamp(int(value), tz=timezone.utc)

        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)

        return parsed.astimezone(timezone.utc)

    except (ValueError, TypeError, OverflowError):
        return None


def _get(item: dict, *names, default=None):
    for name in names:
        if name in item and item[name] is not None:
            return item[name]
    return default
def _get_external_ids(item: dict) -> tuple[int | None, int | None, str | None]:
    tmdb_id = None
    tvdb_id = None
    imdb_id = None

    for guid in item.get("Guid", []) or []:
        value = guid.get("id", "")

        if value.startswith("tmdb://"):
            try:
                tmdb_id = int(value.removeprefix("tmdb://"))
            except ValueError:
                pass

        elif value.startswith("tvdb://"):
            try:
                tvdb_id = int(value.removeprefix("tvdb://"))
            except ValueError:
                pass

        elif value.startswith("imdb://"):
            imdb_id = value.removeprefix("imdb://")

    return tmdb_id, tvdb_id, imdb_id

def find_candidates(
    plex_items: list[dict],
    never_watched_min_age_days: int,
    fully_watched_min_days_since_watch: int,
) -> list[Candidate]:
    now = datetime.now(timezone.utc)
    candidates: list[Candidate] = []

    for item in plex_items:
        rating_key = str(_get(item, "ratingKey", "rating_key", default=""))
        title = _get(item, "title", default="(onbekende titel)")
        media_type = _get(item, "type", default="")

        if not rating_key:
            continue

        view_count = int(_get(item, "viewCount", "view_count", default=0) or 0)
        tmdb_id, tvdb_id, imdb_id = _get_external_ids(item)
        added_at = _parse_timestamp(
            _get(item, "addedAt", "added_at")
        )
        last_viewed_at = _parse_timestamp(
            _get(item, "lastViewedAt", "last_viewed_at")
        )

        # Nooit bekeken: alleen tonen als informatieve kandidaat.
        # Dit wordt bewust NOOIT als verwijderbaar gemarkeerd.
        if view_count == 0:
            if added_at is None:
                continue

            age_days = (now - added_at).days

            if age_days >= never_watched_min_age_days:
                candidates.append(
                    Candidate(
                        rating_key=rating_key,
                        title=title,
                        type=media_type,
                        reason=f"Onbekeken en oud ({age_days} dagen in bibliotheek)",
                        deletable=False,
                        tmdb_id=tmdb_id,
                        tvdb_id=tvdb_id,
                        imdb_id=imdb_id,
                        added_at=added_at,
                        last_viewed_at=None,
                        view_count=view_count,
                    )
                )

            continue

        # Bekeken maar zonder betrouwbare kijkdatum:
        # niet automatisch als verwijderbaar behandelen.
        if last_viewed_at is None:
            continue

        days_since_watch = (now - last_viewed_at).days

        if days_since_watch < fully_watched_min_days_since_watch:
            continue

        # TV-series mogen alleen verwijderbaar zijn als ALLE
        # afleveringen bekeken zijn.
        if media_type == "show":
            leaf_count = _get(item, "leafCount", "leaf_count")
            viewed_leaf_count = _get(
                item,
                "viewedLeafCount",
                "viewed_leaf_count",
            )

            try:
                leaf_count = int(leaf_count)
                viewed_leaf_count = int(viewed_leaf_count)
            except (TypeError, ValueError):
                continue

            # Ontbrekende/ongeldige tellingen zijn altijd veilig:
            # niet verwijderbaar.
            if leaf_count <= 0:
                continue

            if viewed_leaf_count != leaf_count:
                continue

        candidates.append(
            Candidate(
                rating_key=rating_key,
                title=title,
                type=media_type,
                reason=f"Bekeken ({days_since_watch} dagen geleden)",
                deletable=True,
                tmdb_id=tmdb_id,
                tvdb_id=tvdb_id,
                imdb_id=imdb_id,
                added_at=added_at,
                last_viewed_at=last_viewed_at,
                view_count=view_count,
            )
        )

    return candidates

# Behoud de naam die eventuele nieuwere code verwacht.
def analyze_candidates(
    plex_items: list[dict],
    radarr_index: dict,
    sonarr_index: dict,
    config,
) -> list[dict]:
    """
    Compatibiliteitslaag voor de nieuwere analyse-aanroep.

    De huidige applicatie gebruikt find_candidates(); Radarr/Sonarr
    koppeling wordt bewust nog niet uitgevoerd.
    """
    candidates = find_candidates(
        plex_items,
        config.never_watched_min_age_days,
        config.fully_watched_min_days_since_watch,
    )

    return [
        {
            "title": candidate.title,
            "type": candidate.type,
            "plex_id": candidate.rating_key,
            "reason": candidate.reason,
            "deletable": candidate.deletable,
        }
        for candidate in candidates
    ]
