import logging
import os
import time
from datetime import datetime, timezone

import httpx

from . import db

logger = logging.getLogger(__name__)

TOKEN_URL = "https://id.twitch.tv/oauth2/token"
API_BASE = "https://api.igdb.com/v4"
COVER_BASE = "https://images.igdb.com/igdb/image/upload/t_cover_big"

_token: dict = {"value": None, "expires_at": 0.0}

FIELDS = (
    "name, first_release_date, summary, genres.name, cover.image_id, "
    "involved_companies.company.name, involved_companies.developer"
)


def enabled() -> bool:
    return bool(os.environ.get("IGDB_CLIENT_ID", "").strip() and os.environ.get("IGDB_CLIENT_SECRET", "").strip())


def _headers(client: httpx.Client) -> dict:
    if not _token["value"] or time.time() > _token["expires_at"] - 60:
        resp = client.post(
            TOKEN_URL,
            params={
                "client_id": os.environ["IGDB_CLIENT_ID"].strip(),
                "client_secret": os.environ["IGDB_CLIENT_SECRET"].strip(),
                "grant_type": "client_credentials",
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        _token["value"] = data["access_token"]
        _token["expires_at"] = time.time() + data.get("expires_in", 3600)
    return {
        "Client-ID": os.environ["IGDB_CLIENT_ID"].strip(),
        "Authorization": f"Bearer {_token['value']}",
    }


def _query(client: httpx.Client, body: str) -> list[dict]:
    resp = client.post(f"{API_BASE}/games", headers=_headers(client), content=body, timeout=15)
    resp.raise_for_status()
    return resp.json()


def _parse(item: dict) -> dict:
    year = None
    if item.get("first_release_date"):
        year = datetime.fromtimestamp(item["first_release_date"], tz=timezone.utc).year
    developer = next(
        (
            ic["company"]["name"]
            for ic in item.get("involved_companies", [])
            if ic.get("developer") and ic.get("company", {}).get("name")
        ),
        None,
    )
    image_id = item.get("cover", {}).get("image_id")
    return {
        "igdb_id": item["id"],
        "title": item.get("name", ""),
        "year": year,
        "summary": item.get("summary"),
        "developer": developer,
        "genres": ", ".join(g["name"] for g in item.get("genres", [])) or None,
        "cover_url": f"{COVER_BASE}/{image_id}.jpg" if image_id else None,
    }


def search(query: str) -> list[dict]:
    safe = query.replace("\\", "").replace('"', '\\"')
    body = f'search "{safe}"; fields {FIELDS}; where version_parent = null; limit 12;'
    with httpx.Client() as client:
        return [_parse(item) for item in _query(client, body)]


def fetch_details(igdb_id: int) -> dict:
    """Fetch full details and download the cover to local storage."""
    body = f"fields {FIELDS}; where id = {igdb_id};"
    with httpx.Client() as client:
        items = _query(client, body)
        if not items:
            raise ValueError(f"IGDB game {igdb_id} not found")
        parsed = _parse(items[0])
        cover_file = None
        if parsed["cover_url"]:
            cover_file = f"igdb-{igdb_id}.jpg"
            target = db.POSTER_DIR / cover_file
            if not target.exists():
                try:
                    img = client.get(parsed["cover_url"], timeout=30)
                    img.raise_for_status()
                    target.write_bytes(img.content)
                except httpx.HTTPError:
                    logger.warning(
                        "[Games] IGDB cover download failed",
                        extra={"igdb_id": igdb_id},
                        exc_info=True,
                    )
                    cover_file = None
    return {
        "title": parsed["title"],
        "year": parsed["year"],
        "summary": parsed["summary"],
        "developer": parsed["developer"],
        "genres": parsed["genres"],
        "cover_file": cover_file,
        "external_source": "IGDB",
        "external_id": str(igdb_id),
    }
