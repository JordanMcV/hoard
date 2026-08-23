import logging
import os

import httpx

from . import db, retry

logger = logging.getLogger(__name__)

API_BASE = "https://api.steampowered.com"
CDN_BASE = "https://cdn.cloudflare.steamstatic.com/steam/apps"


def enabled() -> bool:
    return bool(os.environ.get("STEAM_API_KEY", "").strip() and os.environ.get("STEAM_ID", "").strip())


def _resolve_steam_id(client: httpx.Client, key: str, raw: str) -> str:
    if raw.isdigit() and len(raw) == 17:
        return raw
    resp = retry.get(
        client,
        f"{API_BASE}/ISteamUser/ResolveVanityURL/v1/",
        params={"key": key, "vanityurl": raw},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json().get("response", {})
    if data.get("success") != 1:
        raise ValueError(f"Could not resolve Steam vanity name '{raw}'")
    return data["steamid"]


def _download_cover(client: httpx.Client, appid: str) -> str | None:
    cover_file = f"steam-{appid}.jpg"
    target = db.POSTER_DIR / cover_file
    if target.exists():
        return cover_file
    for variant in ("library_600x900.jpg", "header.jpg"):
        try:
            resp = retry.get(client, f"{CDN_BASE}/{appid}/{variant}", timeout=30)
        except httpx.HTTPError:
            logger.warning("[Games] Steam cover download failed",
                           extra={"appid": appid, "variant": variant}, exc_info=True)
            continue
        if resp.status_code == 200:
            target.write_bytes(resp.content)
            return cover_file
        if resp.status_code != 404:
            # Throttled or broken rather than absent. Leave the cover unset so a
            # later sync retries it instead of treating this as final.
            logger.warning("[Games] Steam cover not retrievable",
                           extra={"appid": appid, "variant": variant,
                                  "status": resp.status_code})
    return None


def sync() -> dict:
    """Import the Steam library. Insert new games, refresh playtime on known ones."""
    key = os.environ["STEAM_API_KEY"].strip()
    with httpx.Client() as client:
        steam_id = _resolve_steam_id(client, key, os.environ["STEAM_ID"].strip())
        resp = retry.get(
            client,
            f"{API_BASE}/IPlayerService/GetOwnedGames/v1/",
            params={
                "key": key,
                "steamid": steam_id,
                "include_appinfo": 1,
                "include_played_free_games": 1,
                "format": "json",
            },
            timeout=30,
        )
        resp.raise_for_status()
        games = resp.json().get("response", {}).get("games", [])

        existing = db.game_rows_by_external("Steam")
        added = updated = covers_backfilled = 0
        for g in games:
            appid = str(g["appid"])
            playtime = g.get("playtime_forever") or None
            if appid in existing:
                fields = {"playtime_minutes": playtime}
                if not existing[appid]["cover_file"]:
                    cover = _download_cover(client, appid)
                    if cover:
                        fields["cover_file"] = cover
                        covers_backfilled += 1
                db.update_game_by_external("Steam", appid, **fields)
                updated += 1
            else:
                db.add_game(
                    title=g.get("name") or f"Steam app {appid}",
                    platform="PC",
                    store="Steam",
                    external_source="Steam",
                    external_id=appid,
                    playtime_minutes=playtime,
                    cover_file=_download_cover(client, appid),
                )
                added += 1

    result = {"added": added, "updated": updated, "covers_backfilled": covers_backfilled}
    logger.info("[Games] Steam sync finished", extra=result)
    return result
