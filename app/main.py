import csv
import io
import logging
from pathlib import Path
from urllib.parse import urlencode

import httpx
from fastapi import FastAPI, Form, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import db, igdb, plex, psn, steam, tmdb

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Hoard")
db.init()

BASE_DIR = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
app.mount("/posters", StaticFiles(directory=db.POSTER_DIR), name="posters")
templates = Jinja2Templates(directory=BASE_DIR / "templates")
templates.env.globals.update(
    mediums=db.MEDIUMS,
    qualities=db.QUALITIES,
    locations=db.LOCATIONS,
    platforms=db.PLATFORMS,
    stores=db.STORES,
    statuses=db.STATUSES,
)


def _view_urls(request: Request) -> dict:
    """Links to each view that keep the current filters."""
    params = {k: v for k, v in request.query_params.items() if k != "view"}
    return {
        v: f"{request.url.path}?{urlencode({**params, 'view': v})}"
        for v in ("grid", "list")
    }


# Movies

@app.get("/")
def index(request: Request, q: str = "", medium: str = "", quality: str = "", watched: str = "",
          sort: str = "title", view: str = "grid", msg: str = "", error: str = ""):
    movies = db.list_movies(q=q, medium=medium, quality=quality, watched=watched, sort=sort)
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "movies": movies,
            "stats": db.movie_stats(),
            "q": q,
            "medium": medium,
            "quality": quality,
            "watched": watched,
            "sort": sort,
            "view": view,
            "view_urls": _view_urls(request),
            "msg": msg,
            "error": error,
            "plex_enabled": plex.enabled(),
            "section": "movies",
        },
    )


@app.get("/add")
def add_page(request: Request, q: str = ""):
    results, error = [], None
    if q and tmdb.enabled():
        try:
            results = tmdb.search(q)
        except httpx.HTTPError:
            logger.error("[Movies] TMDB search failed", extra={"query": q}, exc_info=True)
            error = "TMDB search failed. Check your API key or add the movie manually."
    return templates.TemplateResponse(
        request,
        "add.html",
        {
            "q": q,
            "results": results,
            "tmdb_enabled": tmdb.enabled(),
            "error": error,
            "owned_ids": db.movie_tmdb_ids(),
            "section": "movies",
        },
    )


@app.post("/add")
def add_from_tmdb(
    tmdb_id: int = Form(...),
    medium: str = Form("Blu-ray"),
    quality: str = Form("Not backed up"),
):
    details = tmdb.fetch_details(tmdb_id)
    movie_id = db.add_movie(medium=medium, quality=quality, **details)
    logger.info("[Movies] Added from TMDB", extra={"tmdb_id": tmdb_id, "movie_id": movie_id})
    return RedirectResponse(f"/movies/{movie_id}", status_code=303)


@app.post("/add-manual")
def add_manual(
    title: str = Form(...),
    year: int | None = Form(None),
    medium: str = Form("Blu-ray"),
    quality: str = Form("Not backed up"),
    director: str = Form(""),
    notes: str = Form(""),
):
    movie_id = db.add_movie(
        title=title.strip(),
        year=year,
        medium=medium,
        quality=quality,
        director=director.strip() or None,
        notes=notes.strip() or None,
    )
    return RedirectResponse(f"/movies/{movie_id}", status_code=303)


@app.get("/random/movie")
def random_movie():
    movie_id = db.random_movie_id(unwatched_only=True)
    if movie_id is None:
        return RedirectResponse("/?msg=Nothing unwatched to pick from.", status_code=303)
    return RedirectResponse(f"/movies/{movie_id}", status_code=303)


@app.get("/export/movies.csv")
def export_movies():
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["title", "year", "medium", "quality", "director", "genres", "watched",
                     "rating", "location", "source", "notes", "added_at"])
    for m in db.list_movies(sort="title"):
        writer.writerow([m["title"], m["year"], m["medium"], m["quality"], m["director"], m["genres"],
                         m["watched"], m["personal_rating"], m["location"], m["source"],
                         m["notes"], m["added_at"]])
    return Response(
        buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=movies.csv"},
    )


@app.get("/movies/{movie_id}")
def detail(request: Request, movie_id: int, saved: int = 0):
    movie = db.get_movie(movie_id)
    if movie is None:
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(
        request, "detail.html", {"movie": movie, "saved": saved, "section": "movies"}
    )


@app.post("/movies/{movie_id}")
def update(
    movie_id: int,
    medium: str = Form("Blu-ray"),
    quality: str = Form("Not backed up"),
    watched: str = Form("0"),
    personal_rating: int | None = Form(None),
    location: str = Form(""),
    notes: str = Form(""),
):
    db.update_movie(
        movie_id,
        medium=medium,
        quality=quality,
        watched=1 if watched == "1" else 0,
        personal_rating=personal_rating,
        location=location.strip() or None,
        notes=notes.strip() or None,
    )
    return RedirectResponse(f"/movies/{movie_id}?saved=1", status_code=303)


@app.post("/movies/{movie_id}/delete")
def delete(movie_id: int):
    db.delete_movie(movie_id)
    return RedirectResponse("/", status_code=303)


# Games

@app.get("/games")
def games_index(request: Request, q: str = "", platform: str = "", status: str = "",
                pinned: str = "", hidden: str = "", sort: str = "title", view: str = "grid",
                msg: str = "", error: str = ""):
    games = db.list_games(q=q, platform=platform, status=status, pinned=pinned,
                          hidden=hidden, sort=sort)
    return templates.TemplateResponse(
        request,
        "games_index.html",
        {
            "games": games,
            "stats": db.game_stats(),
            "q": q,
            "platform": platform,
            "status": status,
            "pinned": pinned,
            "hidden": hidden,
            "sort": sort,
            "view": view,
            "view_urls": _view_urls(request),
            "msg": msg,
            "error": error,
            "steam_enabled": steam.enabled(),
            "psn_enabled": psn.enabled(),
            "section": "games",
        },
    )


@app.get("/games/add")
def games_add_page(request: Request, q: str = ""):
    results, error = [], None
    if q and igdb.enabled():
        try:
            results = igdb.search(q)
        except httpx.HTTPError:
            logger.error("[Games] IGDB search failed", extra={"query": q}, exc_info=True)
            error = "IGDB search failed. Check your Twitch credentials or add the game manually."
    return templates.TemplateResponse(
        request,
        "games_add.html",
        {
            "q": q,
            "results": results,
            "igdb_enabled": igdb.enabled(),
            "error": error,
            "owned_ids": db.game_external_ids("IGDB"),
            "section": "games",
        },
    )


@app.post("/games/add")
def games_add_from_igdb(igdb_id: int = Form(...), platform: str = Form("PC"), store: str = Form("Steam")):
    details = igdb.fetch_details(igdb_id)
    game_id = db.add_game(platform=platform, store=store, **details)
    logger.info("[Games] Added from IGDB", extra={"igdb_id": igdb_id, "game_id": game_id})
    return RedirectResponse(f"/games/{game_id}", status_code=303)


@app.post("/games/add-manual")
def games_add_manual(
    title: str = Form(...),
    year: int | None = Form(None),
    platform: str = Form("PC"),
    store: str = Form("Other"),
    developer: str = Form(""),
    notes: str = Form(""),
):
    game_id = db.add_game(
        title=title.strip(),
        year=year,
        platform=platform,
        store=store,
        developer=developer.strip() or None,
        notes=notes.strip() or None,
    )
    return RedirectResponse(f"/games/{game_id}", status_code=303)


@app.get("/random/game")
def random_game():
    game_id = db.random_game_id(backlog_only=True)
    if game_id is None:
        return RedirectResponse("/games?msg=No backlog to pick from.", status_code=303)
    return RedirectResponse(f"/games/{game_id}", status_code=303)


@app.get("/export/games.csv")
def export_games():
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["title", "year", "platform", "store", "status", "pinned", "hidden",
                     "playtime_minutes", "rating", "developer", "genres", "notes", "added_at"])
    for g in db.list_games(hidden="all", sort="title"):
        writer.writerow([g["title"], g["year"], g["platform"], g["store"], g["status"], g["pinned"],
                         g["hidden"],
                         g["playtime_minutes"], g["personal_rating"], g["developer"], g["genres"],
                         g["notes"], g["added_at"]])
    return Response(
        buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=games.csv"},
    )


@app.post("/sync/plex")
def sync_plex():
    try:
        result = plex.sync()
    except Exception:
        logger.error("[Movies] Plex sync failed", exc_info=True)
        return RedirectResponse(
            "/?error=Plex sync failed. Check PLEX_URL and PLEX_TOKEN.", status_code=303
        )
    msg = (
        f"Plex sync: {result['added']} added, {result['updated']} updated, "
        f"{result['adopted']} linked, {result['removed']} removed."
    )
    if result["unlinked"]:
        msg += f" {result['unlinked']} hand-added film(s) left Plex and were kept."
    if result["posters_backfilled"]:
        msg += f" {result['posters_backfilled']} missing poster(s) retrieved."
    return RedirectResponse(f"/?msg={msg}", status_code=303)


@app.post("/sync/steam")
def sync_steam():
    try:
        result = steam.sync()
    except Exception:
        logger.error("[Games] Steam sync failed", exc_info=True)
        return RedirectResponse("/games?error=Steam sync failed. Check STEAM_API_KEY and STEAM_ID.", status_code=303)
    msg = f"Steam sync: {result['added']} added, {result['updated']} updated."
    if result["covers_backfilled"]:
        msg += f" {result['covers_backfilled']} missing cover(s) retrieved."
    return RedirectResponse(f"/games?msg={msg}", status_code=303)


@app.post("/sync/psn")
def sync_psn():
    try:
        result = psn.sync()
    except Exception:
        logger.error("[Games] PSN sync failed", exc_info=True)
        return RedirectResponse(
            "/games?error=PSN sync failed. The NPSSO token may have expired; get a fresh one and update .env.",
            status_code=303,
        )
    msg = f"PSN sync: {result['added']} added, {result['updated']} updated."
    if result["covers_backfilled"]:
        msg += f" {result['covers_backfilled']} missing cover(s) retrieved."
    return RedirectResponse(f"/games?msg={msg}", status_code=303)


@app.get("/games/{game_id}")
def game_detail(request: Request, game_id: int, saved: int = 0):
    game = db.get_game(game_id)
    if game is None:
        return RedirectResponse("/games", status_code=303)
    return templates.TemplateResponse(
        request, "games_detail.html", {"game": game, "saved": saved, "section": "games"}
    )


@app.post("/games/{game_id}")
def game_update(
    game_id: int,
    platform: str = Form("PC"),
    store: str = Form("Other"),
    status: str = Form("Backlog"),
    pinned: str = Form("0"),
    hidden: str = Form("0"),
    playtime_minutes: int | None = Form(None),
    personal_rating: int | None = Form(None),
    notes: str = Form(""),
):
    db.update_game(
        game_id,
        platform=platform,
        store=store,
        status=status,
        pinned=1 if pinned == "1" else 0,
        hidden=1 if hidden == "1" else 0,
        playtime_minutes=playtime_minutes,
        personal_rating=personal_rating,
        notes=notes.strip() or None,
    )
    return RedirectResponse(f"/games/{game_id}?saved=1", status_code=303)


@app.post("/games/{game_id}/delete")
def game_delete(game_id: int):
    db.delete_game(game_id)
    return RedirectResponse("/games", status_code=303)
