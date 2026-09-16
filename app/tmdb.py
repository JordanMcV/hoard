import logging
import os

import httpx

from . import db, retry

logger = logging.getLogger(__name__)

API_BASE = "https://api.themoviedb.org/3"
IMAGE_BASE = "https://image.tmdb.org/t/p/w500"


def api_key() -> str:
    return os.environ.get("TMDB_API_KEY", "").strip()


def enabled() -> bool:
    return bool(api_key())


def _request(client: httpx.Client, path: str, params: dict | None = None) -> dict:
    key = api_key()
    params = dict(params or {})
    headers = {}
    # v4 read access tokens are JWTs; v3 keys go in the query string.
    if key.startswith("eyJ"):
        headers["Authorization"] = f"Bearer {key}"
    else:
        params["api_key"] = key
    resp = retry.get(client, f"{API_BASE}{path}", params=params, headers=headers, timeout=15)
    resp.raise_for_status()
    return resp.json()


def search(query: str) -> list[dict]:
    with httpx.Client() as client:
        data = _request(client, "/search/movie", {"query": query, "include_adult": "false"})
    results = []
    for item in data.get("results", [])[:12]:
        year = (item.get("release_date") or "")[:4]
        results.append(
            {
                "tmdb_id": item["id"],
                "title": item.get("title", ""),
                "year": int(year) if year.isdigit() else None,
                "overview": item.get("overview", ""),
                "poster_url": f"{IMAGE_BASE}{item['poster_path']}" if item.get("poster_path") else None,
            }
        )
    return results


def _download_poster(client: httpx.Client, poster_path: str | None, filename: str,
                     context: dict) -> str | None:
    """Store a TMDB poster locally and return its filename, or None if it failed."""
    if not poster_path:
        return None
    target = db.POSTER_DIR / filename
    if target.exists():
        return filename
    try:
        img = retry.get(client, f"{IMAGE_BASE}{poster_path}", timeout=30)
        img.raise_for_status()
        target.write_bytes(img.content)
    except httpx.HTTPError:
        logger.warning(
            "[TMDB] Poster download failed",
            extra={**context, "poster_path": poster_path},
            exc_info=True,
        )
        return None
    return filename


def fetch_details(tmdb_id: int) -> dict:
    """Fetch full details and download the poster to local storage."""
    with httpx.Client() as client:
        data = _request(client, f"/movie/{tmdb_id}", {"append_to_response": "credits"})
        poster_file = _download_poster(
            client, data.get("poster_path"), f"tmdb-{tmdb_id}.jpg", {"tmdb_id": tmdb_id}
        )

    director = next(
        (c["name"] for c in data.get("credits", {}).get("crew", []) if c.get("job") == "Director"),
        None,
    )
    year = (data.get("release_date") or "")[:4]
    return {
        "tmdb_id": tmdb_id,
        "title": data.get("title", ""),
        "year": int(year) if year.isdigit() else None,
        "overview": data.get("overview"),
        "director": director,
        "runtime_minutes": data.get("runtime"),
        "genres": ", ".join(g["name"] for g in data.get("genres", [])) or None,
        "poster_file": poster_file,
    }


def search_tv(query: str) -> list[dict]:
    with httpx.Client() as client:
        data = _request(client, "/search/tv", {"query": query, "include_adult": "false"})
    results = []
    for item in data.get("results", [])[:12]:
        year = (item.get("first_air_date") or "")[:4]
        results.append(
            {
                "tmdb_id": item["id"],
                "title": item.get("name", ""),
                "year": int(year) if year.isdigit() else None,
                "overview": item.get("overview", ""),
                "poster_url": f"{IMAGE_BASE}{item['poster_path']}" if item.get("poster_path") else None,
            }
        )
    return results


def fetch_show(tmdb_id: int) -> dict:
    """Fetch a series and the seasons you can add from it.

    Season 0 holds specials, which box sets rarely sell on their own, so it is
    dropped. A season poster falls back to the series poster, because TMDB
    leaves many season posters empty.
    """
    with httpx.Client() as client:
        data = _request(client, f"/tv/{tmdb_id}")

    creator = next((c["name"] for c in data.get("created_by", [])), None)
    network = next((n["name"] for n in data.get("networks", [])), None)
    genres = ", ".join(g["name"] for g in data.get("genres", [])) or None
    show_poster = data.get("poster_path")

    seasons = []
    for season in data.get("seasons", []):
        number = season.get("season_number")
        if not number:
            continue
        year = (season.get("air_date") or "")[:4]
        poster_path = season.get("poster_path") or show_poster
        seasons.append(
            {
                "season_number": number,
                "season_name": season.get("name") or f"Season {number}",
                "year": int(year) if year.isdigit() else None,
                "episode_count": season.get("episode_count"),
                "overview": season.get("overview") or data.get("overview"),
                "poster_path": poster_path,
                "poster_url": f"{IMAGE_BASE}{poster_path}" if poster_path else None,
            }
        )

    first_year = (data.get("first_air_date") or "")[:4]
    return {
        "tmdb_id": tmdb_id,
        "title": data.get("name", ""),
        "year": int(first_year) if first_year.isdigit() else None,
        "overview": data.get("overview"),
        "creator": creator,
        "network": network,
        "genres": genres,
        "seasons": seasons,
    }


def fetch_season_details(tmdb_id: int, season_number: int) -> dict:
    """Build one season record and download its poster."""
    show = fetch_show(tmdb_id)
    season = next((s for s in show["seasons"] if s["season_number"] == season_number), None)
    if season is None:
        raise ValueError(f"Season {season_number} is not on TMDB series {tmdb_id}")

    with httpx.Client() as client:
        poster_file = _download_poster(
            client,
            season["poster_path"],
            f"tmdb-tv-{tmdb_id}-s{season_number}.jpg",
            {"tmdb_id": tmdb_id, "season_number": season_number},
        )

    return {
        "tmdb_id": tmdb_id,
        "title": show["title"],
        "season_number": season_number,
        "season_name": season["season_name"],
        "year": season["year"] or show["year"],
        "overview": season["overview"],
        "creator": show["creator"],
        "network": show["network"],
        "genres": show["genres"],
        "episode_count": season["episode_count"],
        "poster_file": poster_file,
    }
