# Hoard

A personal media collection inventory for movies and games. Search TMDB or IGDB by title, add the match to your collection, and track medium, quality, status, rating, notes, and location. Cover art is downloaded and stored locally. Steam and PlayStation libraries can be imported with one click.

## Features

- Movies: TMDB title search, Plex library sync, medium and quality tracking, watched flag, rating, notes.
- Games: IGDB title search, platform and store tracking, status (Backlog, Playing, Completed, Dropped), playtime, rating, notes.
- Steam sync: imports your library through the official Steam Web API. New games arrive as Backlog. Repeat syncs refresh playtime only.
- PSN sync: imports played PS3/PS4/PS5 titles through the unofficial PSN API (PSNAWP). Same upsert rules as Steam.
- "In collection" badges on search results prevent duplicate adds.
- CSV export for both collections.
- "Pick for me" jumps to a random unwatched movie or backlog game.

## Setup

1. Copy `.env.example` to `.env` and fill in the keys you want. Every integration is optional; the app falls back to manual entry.
   - `TMDB_API_KEY`: movie search. https://www.themoviedb.org/settings/api
   - `IGDB_CLIENT_ID` / `IGDB_CLIENT_SECRET`: game search. Create a Twitch app at https://dev.twitch.tv/console/apps
   - `STEAM_API_KEY` / `STEAM_ID`: Steam sync. Key from https://steamcommunity.com/dev/apikey. The ID accepts a steamid64 or vanity name.
   - `PSN_NPSSO`: PSN sync. Log in at https://www.playstation.com, then copy the token from https://ca.account.sony.com/api/v1/ssocookie. The token expires roughly every two months; paste a fresh one when sync reports an auth error.
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

All data lives in `data/`: the SQLite database at `data/movies.db` and cover images in `data/posters/`. Back up that directory to back up your collection.

## Notes

- Sync runs inline in the request. A large Steam library takes a few minutes on first sync because covers download one by one.
- Sync never deletes rows and never overwrites status, rating, or notes.
