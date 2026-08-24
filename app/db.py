import sqlite3
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
POSTER_DIR = DATA_DIR / "posters"
DB_PATH = DATA_DIR / "movies.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS movies (
    id INTEGER PRIMARY KEY,
    tmdb_id INTEGER,
    title TEXT NOT NULL,
    year INTEGER,
    medium TEXT NOT NULL DEFAULT 'Blu-ray',
    quality TEXT NOT NULL DEFAULT 'Not backed up',
    overview TEXT,
    director TEXT,
    runtime_minutes INTEGER,
    genres TEXT,
    poster_file TEXT,
    watched INTEGER NOT NULL DEFAULT 0,
    personal_rating INTEGER,
    notes TEXT,
    location TEXT,
    source TEXT,
    plex_key TEXT,
    added_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS games (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    year INTEGER,
    platform TEXT NOT NULL DEFAULT 'PC',
    store TEXT,
    external_source TEXT,
    external_id TEXT,
    summary TEXT,
    developer TEXT,
    genres TEXT,
    playtime_minutes INTEGER,
    cover_file TEXT,
    status TEXT NOT NULL DEFAULT 'Backlog',
    pinned INTEGER NOT NULL DEFAULT 0,
    hidden INTEGER NOT NULL DEFAULT 0,
    personal_rating INTEGER,
    notes TEXT,
    added_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(external_source, external_id)
);
"""

# What you physically own.
MEDIUMS = ["4K UHD Disc", "Blu-ray", "DVD", "VHS", "Digital only", "Other"]

# The best digital copy you hold. "Not backed up" means disc only.
QUALITIES = ["Not backed up", "4K Remux", "4K", "1080p Remux", "1080p", "720p", "SD"]

LOCATIONS = ["Shelf", "Drive"]

PLATFORMS = ["PC", "PS5", "PS4", "PS3", "Switch", "Xbox", "Other"]

STORES = ["Steam", "PSN", "Physical", "Battle.net", "GOG", "Other"]

STATUSES = ["Backlog", "Playing", "Completed", "Dropped"]

# Sort "The Matrix" under M. SQLite's LIKE is case-insensitive for ASCII, and the
# trailing space means "Theatre" and "A.I." keep their first word.
SORT_TITLE = (
    "CASE"
    " WHEN title LIKE 'The %' THEN SUBSTR(title, 5)"
    " WHEN title LIKE 'An %' THEN SUBSTR(title, 4)"
    " WHEN title LIKE 'A %' THEN SUBSTR(title, 3)"
    " ELSE title"
    " END COLLATE NOCASE"
)

MOVIE_SORTS = {
    "added": "added_at DESC, id DESC",
    "title": f"{SORT_TITLE} ASC",
    "year": f"year DESC, {SORT_TITLE} ASC",
    "rating": f"personal_rating DESC, {SORT_TITLE} ASC",
}

# Pinned games lead every ordering, so what you mean to play next stays visible.
GAME_SORTS = {
    "added": "pinned DESC, added_at DESC, id DESC",
    "title": f"pinned DESC, {SORT_TITLE} ASC",
    "year": f"pinned DESC, year DESC, {SORT_TITLE} ASC",
    "rating": f"pinned DESC, personal_rating DESC, {SORT_TITLE} ASC",
    "playtime": f"pinned DESC, playtime_minutes DESC, {SORT_TITLE} ASC",
}


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(exist_ok=True)
    POSTER_DIR.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    """Bring a pre-split database up to the medium/quality schema."""
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(movies)")}
    if not cols:
        return
    backfill = "medium" not in cols

    if "medium" not in cols:
        conn.execute("ALTER TABLE movies ADD COLUMN medium TEXT NOT NULL DEFAULT 'Blu-ray'")
    if "quality" not in cols:
        conn.execute("ALTER TABLE movies ADD COLUMN quality TEXT NOT NULL DEFAULT 'Not backed up'")
    if "source" not in cols:
        conn.execute("ALTER TABLE movies ADD COLUMN source TEXT")
    if "plex_key" not in cols:
        conn.execute("ALTER TABLE movies ADD COLUMN plex_key TEXT")

    game_cols = {r["name"] for r in conn.execute("PRAGMA table_info(games)")}
    if game_cols and "pinned" not in game_cols:
        conn.execute("ALTER TABLE games ADD COLUMN pinned INTEGER NOT NULL DEFAULT 0")
    if game_cols and "hidden" not in game_cols:
        conn.execute("ALTER TABLE games ADD COLUMN hidden INTEGER NOT NULL DEFAULT 0")

    if backfill and "format" in cols:
        conn.execute(
            """
            UPDATE movies SET
                medium = CASE
                    WHEN format = '4K UHD' THEN '4K UHD Disc'
                    WHEN format IN ('Blu-ray', 'DVD', 'VHS') THEN format
                    WHEN format LIKE 'Digital%' THEN 'Digital only'
                    ELSE 'Other'
                END,
                quality = CASE
                    WHEN format LIKE '%Remux%' THEN '4K Remux'
                    WHEN format LIKE 'Digital%' THEN '1080p'
                    ELSE 'Not backed up'
                END
            """
        )
        try:
            conn.execute("ALTER TABLE movies DROP COLUMN format")
        except sqlite3.OperationalError:
            # Older SQLite cannot drop columns. The stale column is harmless.
            pass


def init() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)
        _migrate(conn)
        # After _migrate, so it also covers databases created before plex_key existed.
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_movies_plex_key ON movies(plex_key)"
        )


def _insert(table: str, fields: dict) -> int:
    cols = ", ".join(fields)
    marks = ", ".join("?" for _ in fields)
    with connect() as conn:
        cur = conn.execute(f"INSERT INTO {table} ({cols}) VALUES ({marks})", list(fields.values()))
        return cur.lastrowid


def _update(table: str, row_id: int, fields: dict) -> None:
    sets = ", ".join(f"{col} = ?" for col in fields)
    with connect() as conn:
        conn.execute(f"UPDATE {table} SET {sets} WHERE id = ?", [*fields.values(), row_id])


# Movies

def list_movies(q: str = "", medium: str = "", quality: str = "", watched: str = "", sort: str = "added") -> list[sqlite3.Row]:
    where, params = [], []
    if q:
        where.append("(title LIKE ? OR director LIKE ?)")
        params += [f"%{q}%", f"%{q}%"]
    if medium:
        where.append("medium = ?")
        params.append(medium)
    if quality:
        where.append("quality = ?")
        params.append(quality)
    if watched in ("0", "1"):
        where.append("watched = ?")
        params.append(int(watched))
    sql = "SELECT * FROM movies"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY " + MOVIE_SORTS.get(sort, MOVIE_SORTS["added"])
    with connect() as conn:
        return conn.execute(sql, params).fetchall()


def get_movie(movie_id: int) -> sqlite3.Row | None:
    with connect() as conn:
        return conn.execute("SELECT * FROM movies WHERE id = ?", (movie_id,)).fetchone()


def add_movie(**fields) -> int:
    return _insert("movies", fields)


def update_movie(movie_id: int, **fields) -> None:
    _update("movies", movie_id, fields)


def delete_movie(movie_id: int) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM movies WHERE id = ?", (movie_id,))


def movie_tmdb_ids() -> set[int]:
    with connect() as conn:
        rows = conn.execute("SELECT tmdb_id FROM movies WHERE tmdb_id IS NOT NULL").fetchall()
        return {r["tmdb_id"] for r in rows}


def movie_plex_keys() -> dict[str, sqlite3.Row]:
    """Every movie already linked to Plex, keyed by its Plex ratingKey."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, plex_key, source, tmdb_id, poster_file FROM movies "
            "WHERE plex_key IS NOT NULL"
        ).fetchall()
        return {r["plex_key"]: r for r in rows}


def movie_ids_by_tmdb() -> dict[int, int]:
    """Map tmdb_id to movie id, for adopting films already added by hand."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, tmdb_id FROM movies WHERE tmdb_id IS NOT NULL AND plex_key IS NULL"
        ).fetchall()
        return {r["tmdb_id"]: r["id"] for r in rows}


def unlink_plex(movie_id: int) -> None:
    """Detach a hand-added film from Plex without deleting it."""
    with connect() as conn:
        conn.execute("UPDATE movies SET plex_key = NULL WHERE id = ?", (movie_id,))


def random_movie_id(unwatched_only: bool = True) -> int | None:
    sql = "SELECT id FROM movies"
    if unwatched_only:
        sql += " WHERE watched = 0"
    sql += " ORDER BY RANDOM() LIMIT 1"
    with connect() as conn:
        row = conn.execute(sql).fetchone()
        return row["id"] if row else None


def movie_stats() -> dict:
    with connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS total, COALESCE(SUM(watched), 0) AS watched FROM movies"
        ).fetchone()
        return {"total": row["total"], "watched": row["watched"]}


# Games

def list_games(q: str = "", platform: str = "", status: str = "", pinned: str = "",
               hidden: str = "", sort: str = "added") -> list[sqlite3.Row]:
    where, params = [], []
    if q:
        where.append("(title LIKE ? OR developer LIKE ?)")
        params += [f"%{q}%", f"%{q}%"]
    if platform:
        where.append("platform = ?")
        params.append(platform)
    if status:
        where.append("status = ?")
        params.append(status)
    if pinned == "1":
        where.append("pinned = 1")
    if hidden == "1":
        where.append("hidden = 1")
    elif hidden != "all":
        where.append("hidden = 0")
    sql = "SELECT * FROM games"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY " + GAME_SORTS.get(sort, GAME_SORTS["added"])
    with connect() as conn:
        return conn.execute(sql, params).fetchall()


def get_game(game_id: int) -> sqlite3.Row | None:
    with connect() as conn:
        return conn.execute("SELECT * FROM games WHERE id = ?", (game_id,)).fetchone()


def add_game(**fields) -> int:
    return _insert("games", fields)


def update_game(game_id: int, **fields) -> None:
    _update("games", game_id, fields)


def delete_game(game_id: int) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM games WHERE id = ?", (game_id,))


def game_external_ids(source: str) -> set[str]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT external_id FROM games WHERE external_source = ?", (source,)
        ).fetchall()
        return {r["external_id"] for r in rows}


def game_rows_by_external(source: str) -> dict[str, sqlite3.Row]:
    """Known games for a source, keyed by external id, including cover state."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, external_id, cover_file FROM games WHERE external_source = ?",
            (source,),
        ).fetchall()
        return {r["external_id"]: r for r in rows}


def update_game_by_external(source: str, external_id: str, **fields) -> None:
    sets = ", ".join(f"{col} = ?" for col in fields)
    with connect() as conn:
        conn.execute(
            f"UPDATE games SET {sets} WHERE external_source = ? AND external_id = ?",
            [*fields.values(), source, external_id],
        )


def random_game_id(backlog_only: bool = True) -> int | None:
    sql = "SELECT id FROM games WHERE hidden = 0"
    if backlog_only:
        sql += " AND status = 'Backlog'"
    sql += " ORDER BY RANDOM() LIMIT 1"
    with connect() as conn:
        row = conn.execute(sql).fetchone()
        return row["id"] if row else None


def game_stats() -> dict:
    with connect() as conn:
        row = conn.execute(
            """
            SELECT COALESCE(SUM(hidden = 0), 0) AS total,
                   COALESCE(SUM(hidden = 0 AND status = 'Backlog'), 0) AS backlog,
                   COALESCE(SUM(hidden = 0 AND status = 'Completed'), 0) AS completed,
                   COALESCE(SUM(hidden = 0 AND pinned = 1), 0) AS pinned,
                   COALESCE(SUM(hidden), 0) AS hidden,
                   COALESCE(SUM(CASE WHEN hidden = 0 THEN playtime_minutes ELSE 0 END), 0)
                       AS playtime_minutes
            FROM games
            """
        ).fetchone()
        return dict(row)
