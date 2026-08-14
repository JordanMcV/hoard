import logging
import os

import httpx

from . import db

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
    resp = client.get(f"{API_BASE}{path}", params=params, headers=headers, timeout=15)
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


def fetch_details(tmdb_id: int) -> dict:
    """Fetch full details and download the poster to local storage."""
    with httpx.Client() as client:
        data = _request(client, f"/movie/{tmdb_id}", {"append_to_response": "credits"})
        poster_file = None
        if data.get("poster_path"):
            poster_file = f"tmdb-{tmdb_id}.jpg"
            target = db.POSTER_DIR / poster_file
            if not target.exists():
                try:
                    img = client.get(f"{IMAGE_BASE}{data['poster_path']}", timeout=30)
                    img.raise_for_status()
                    target.write_bytes(img.content)
                except httpx.HTTPError:
                    logger.warning(
                        "[Movies] Poster download failed",
                        extra={"tmdb_id": tmdb_id, "poster_path": data["poster_path"]},
                        exc_info=True,
                    )
                    poster_file = None

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
