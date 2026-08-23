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


def _platform(category) -> str:
    value = str(getattr(category, "value", category) or "").lower()
    if "ps5" in value:
        return "PS5"
    if "ps3" in value:
        return "PS3"
    return "PS4"


def sync() -> dict:
    """Import played PSN titles. Insert new games, refresh playtime on known ones."""
    from psnawp_api import PSNAWP

    psnawp = PSNAWP(os.environ["PSN_NPSSO"].strip())
    me = psnawp.me()

    existing = db.game_rows_by_external("PSN")
    added = updated = covers_backfilled = 0
    with httpx.Client() as client:
        for title in me.title_stats():
            title_id = title.title_id
            minutes = None
            if getattr(title, "play_duration", None):
                minutes = int(title.play_duration.total_seconds() // 60) or None
            if title_id in existing:
                fields = {"playtime_minutes": minutes}
                if not existing[title_id]["cover_file"]:
                    cover = _download_cover(client, title_id, getattr(title, "image_url", None))
                    if cover:
                        fields["cover_file"] = cover
                        covers_backfilled += 1
                db.update_game_by_external("PSN", title_id, **fields)
                updated += 1
            else:
                db.add_game(
                    title=title.name,
                    platform=_platform(getattr(title, "category", None)),
                    store="PSN",
                    external_source="PSN",
                    external_id=title_id,
                    playtime_minutes=minutes,
                    cover_file=_download_cover(client, title_id, getattr(title, "image_url", None)),
                )
                added += 1

    result = {"added": added, "updated": updated, "covers_backfilled": covers_backfilled}
    logger.info("[Games] PSN sync finished", extra=result)
    return result
