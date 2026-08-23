import logging
import os

import httpx

from . import db, retry, tmdb

logger = logging.getLogger(__name__)

REMUX_BYTES = 50 * 1024**3


def base_url() -> str:
    return os.environ.get("PLEX_URL", "").strip().rstrip("/")


def token() -> str:
    return os.environ.get("PLEX_TOKEN", "").strip()


def enabled() -> bool:
    return bool(base_url() and token())


def _get(client: httpx.Client, path: str, params: dict | None = None) -> dict:
    resp = retry.get(
        client,
        f"{base_url()}{path}",
        params={**(params or {}), "X-Plex-Token": token()},
        headers={"Accept": "application/json"},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json().get("MediaContainer", {})


def _classify(item: dict) -> str:
    """Map a Plex item onto one of the QUALITIES values."""
    media = (item.get("Media") or [{}])[0]
    parts = media.get("Part") or [{}]
    filename = " ".join(str(p.get("file") or "") for p in parts).lower()
    size = max(int(p.get("size") or 0) for p in parts)
    resolution = str(media.get("videoResolution") or "").lower()

    is_4k = resolution in ("4k", "2160")
    if "remux" in filename or size > REMUX_BYTES:
        return "4K Remux" if is_4k else "1080p Remux"
    if is_4k:
        return "4K"
    if resolution == "1080":
        return "1080p"
    if resolution == "720":
        return "720p"
    return "SD"


def _tmdb_id(item: dict) -> int | None:
    for guid in item.get("Guid") or []:
        value = str(guid.get("id") or "")
        if value.startswith("tmdb://"):
            suffix = value.removeprefix("tmdb://")
            if suffix.isdigit():
                return int(suffix)
    return None


def _movie_sections(container: dict) -> list[str]:
    return [d["key"] for d in container.get("Directory", []) if d.get("type") == "movie"]


def sync() -> dict:
    """Mirror the Plex movie libraries.

    Inserts films Plex has and hoard does not, refreshes quality on known ones, and
    removes films that have left Plex. Only rows this sync created are ever deleted;
    films added by hand are unlinked instead.
    """
    added = updated = adopted = removed = unlinked = posters_backfilled = 0

    with httpx.Client() as client:
        sections = _movie_sections(_get(client, "/library/sections"))
        if not sections:
            raise ValueError("No Plex library of type 'movie' was found.")

        seen: set[str] = set()
        known = db.movie_plex_keys()
        by_tmdb = db.movie_ids_by_tmdb()

        for section in sections:
            container = _get(client, f"/library/sections/{section}/all", {"includeGuids": 1})
            for item in container.get("Metadata", []):
                plex_key = str(item.get("ratingKey") or "")
                if not plex_key:
                    continue
                seen.add(plex_key)
                quality = _classify(item)

                if plex_key in known:
                    row = known[plex_key]
                    fields = {"quality": quality}
                    if not row["poster_file"] and row["tmdb_id"] and tmdb.enabled():
                        # A poster that failed earlier is retried, not written off.
                        try:
                            poster = tmdb.fetch_details(row["tmdb_id"])["poster_file"]
                            if poster:
                                fields["poster_file"] = poster
                                posters_backfilled += 1
                        except httpx.HTTPError:
                            logger.warning(
                                "[Movies] Poster backfill failed",
                                extra={"tmdb_id": row["tmdb_id"], "plex_key": plex_key},
                                exc_info=True,
                            )
                    db.update_movie(row["id"], **fields)
                    updated += 1
                    continue

                tmdb_id = _tmdb_id(item)
                if tmdb_id is not None and tmdb_id in by_tmdb:
                    # Already in the collection by hand. Link it and record the digital
                    # copy, but leave the medium alone — the disc is still owned.
                    db.update_movie(by_tmdb.pop(tmdb_id), plex_key=plex_key, quality=quality)
                    adopted += 1
                    continue

                details = {
                    "title": item.get("title") or "Untitled",
                    "year": item.get("year"),
                    "tmdb_id": tmdb_id,
                }
                if tmdb_id and tmdb.enabled():
                    try:
                        details = tmdb.fetch_details(tmdb_id)
                    except httpx.HTTPError:
                        logger.warning(
                            "[Movies] TMDB lookup failed during Plex sync",
                            extra={"tmdb_id": tmdb_id, "plex_key": plex_key},
                            exc_info=True,
                        )
                db.add_movie(
                    medium="Digital only",
                    quality=quality,
                    source="Plex",
                    plex_key=plex_key,
                    **details,
                )
                added += 1

    for plex_key, row in known.items():
        if plex_key in seen:
            continue
        if row["source"] == "Plex":
            db.delete_movie(row["id"])
            removed += 1
        else:
            db.unlink_plex(row["id"])
            unlinked += 1

    result = {
        "added": added,
        "updated": updated,
        "adopted": adopted,
        "removed": removed,
        "unlinked": unlinked,
        "posters_backfilled": posters_backfilled,
    }
    logger.info("[Movies] Plex sync finished", extra=result)
    return result
