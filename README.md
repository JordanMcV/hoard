# Movies

A personal movie collection inventory. Search TMDB by title, add the match to your collection, and track format, watched status, rating, notes, and storage location. Poster art is downloaded and stored locally.

## Setup

1. Copy `.env.example` to `.env` and set `TMDB_API_KEY`. Get a free key at https://www.themoviedb.org/settings/api. Both the v3 key and the v4 read access token work. Without a key, the app still works with manual entry.
2. Start the server:

```sh
uv run --env-file .env uvicorn app.main:app --reload
```

3. Open http://127.0.0.1:8000

## Docker

The compose file builds the image, reads `.env` if present, and mounts `./data` so your collection survives container rebuilds.

```sh
docker compose up -d
```

Open http://127.0.0.1:8000. To rebuild after code changes, run `docker compose up -d --build`.

## Data

All data lives in `data/`: the SQLite database at `data/movies.db` and poster images in `data/posters/`. Back up that directory to back up your collection.
