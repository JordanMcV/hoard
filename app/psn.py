import logging
import os

import httpx

from . import db, retry

logger = logging.getLogger(__name__)


def enabled() -> bool:
    return bool(os.environ.get("PSN_NPSSO", "").strip())


def _download_cover(client: httpx.Client, title_id: str, image_url: str | None) -> str | None:
    if not image_url:
        return None
    cover_file = f"psn-{title_id}.jpg"
    target = db.POSTER_DIR / cover_file
    if target.exists():
        return cover_file
    try:
        resp = retry.get(client, image_url, timeout=30)
        resp.raise_for_status()
        target.write_bytes(resp.content)
        return cover_file
    except httpx.HTTPError:
        logger.warning("[Games] PSN cover download failed", extra={"title_id": title_id}, exc_info=True)
        return None


def _platform(category) -> str | None:
    """PS4 or PS5 for games. None for apps, which PSN reports in categories psnawp maps to UNKNOWN."""
    value = str(getattr(category, "value", category) or "").lower()
    if "ps5" in value:
        return "PS5"
    if "ps4" in value:
        return "PS4"
    return None


def _minutes(title) -> int | None:
    if getattr(title, "play_duration", None):
        return int(title.play_duration.total_seconds() // 60) or None
    return None


def sync() -> dict:
    """Import played PSN titles. Insert new games, refresh playtime on known ones.

    PSN reports one entry per title ID, so regional releases and editions of one game arrive
    separately. Entries with the same name and platform become one row with their playtime summed.
    Apps such as Netflix are skipped, and rows from earlier syncs that are apps or duplicates are removed.
    """
    from psnawp_api import PSNAWP

    psnawp = PSNAWP(os.environ["PSN_NPSSO"].strip())
    me = psnawp.me()

    existing = db.game_rows_by_external("PSN")
    groups: dict[tuple[str, str], list] = {}
    app_ids = set()
    for title in me.title_stats():
        platform = _platform(getattr(title, "category", None))
        if platform is None:
            app_ids.add(title.title_id)
            continue
        groups.setdefault((title.name.strip().casefold(), platform), []).append(title)

    added = updated = covers_backfilled = removed = 0
    for title_id in app_ids & existing.keys():
        db.delete_game(existing[title_id]["id"])
        removed += 1

    with httpx.Client() as client:
        for (_, platform), titles in groups.items():
            minutes = sum(_minutes(t) or 0 for t in titles) or None
            known = sorted((existing[t.title_id] for t in titles if t.title_id in existing), key=lambda r: r["id"])
            if known:
                keep, *extra = known
                for row in extra:
                    db.delete_game(row["id"])
                    removed += 1
                fields = {"playtime_minutes": minutes}
                if not keep["cover_file"]:
                    source = next(t for t in titles if t.title_id == keep["external_id"])
                    cover = _download_cover(client, source.title_id, getattr(source, "image_url", None))
                    if cover:
                        fields["cover_file"] = cover
                        covers_backfilled += 1
                db.update_game_by_external("PSN", keep["external_id"], **fields)
                updated += 1
            else:
                primary = max(titles, key=lambda t: _minutes(t) or 0)
                db.add_game(
                    title=primary.name,
                    platform=platform,
                    store="PSN",
                    external_source="PSN",
                    external_id=primary.title_id,
                    playtime_minutes=minutes,
                    cover_file=_download_cover(client, primary.title_id, getattr(primary, "image_url", None)),
                )
                added += 1

    result = {
        "added": added,
        "updated": updated,
        "covers_backfilled": covers_backfilled,
        "removed": removed,
        "apps_skipped": len(app_ids),
    }
    logger.info("[Games] PSN sync finished", extra=result)
    return result
