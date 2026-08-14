import logging
from pathlib import Path

import httpx
from fastapi import FastAPI, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import db, tmdb

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Movies")
db.init()

BASE_DIR = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
app.mount("/posters", StaticFiles(directory=db.POSTER_DIR), name="posters")
templates = Jinja2Templates(directory=BASE_DIR / "templates")
templates.env.globals["formats"] = db.FORMATS
templates.env.globals["locations"] = db.LOCATIONS


@app.get("/")
def index(request: Request, q: str = "", format: str = "", watched: str = "", sort: str = "added"):
    movies = db.list_movies(q=q, fmt=format, watched=watched, sort=sort)
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "movies": movies,
            "stats": db.stats(),
            "q": q,
            "format": format,
            "watched": watched,
            "sort": sort,
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
        {"q": q, "results": results, "tmdb_enabled": tmdb.enabled(), "error": error},
    )


@app.post("/add")
def add_from_tmdb(tmdb_id: int = Form(...), format: str = Form("Blu-ray")):
    details = tmdb.fetch_details(tmdb_id)
    movie_id = db.add_movie(format=format, **details)
    logger.info("[Movies] Added from TMDB", extra={"tmdb_id": tmdb_id, "movie_id": movie_id})
    return RedirectResponse(f"/movies/{movie_id}", status_code=303)


@app.post("/add-manual")
def add_manual(
    title: str = Form(...),
    year: int | None = Form(None),
    format: str = Form("Blu-ray"),
    director: str = Form(""),
    notes: str = Form(""),
):
    movie_id = db.add_movie(
        title=title.strip(),
        year=year,
        format=format,
        director=director.strip() or None,
        notes=notes.strip() or None,
    )
    return RedirectResponse(f"/movies/{movie_id}", status_code=303)


@app.get("/movies/{movie_id}")
def detail(request: Request, movie_id: int, saved: int = 0):
    movie = db.get_movie(movie_id)
    if movie is None:
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(request, "detail.html", {"movie": movie, "saved": saved})


@app.post("/movies/{movie_id}")
def update(
    movie_id: int,
    format: str = Form("Blu-ray"),
    watched: str = Form("0"),
    personal_rating: int | None = Form(None),
    location: str = Form(""),
    notes: str = Form(""),
):
    db.update_movie(
        movie_id,
        format=format,
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
