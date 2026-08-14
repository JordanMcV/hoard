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
    format TEXT NOT NULL DEFAULT 'Blu-ray',
    overview TEXT,
    director TEXT,
    runtime_minutes INTEGER,
    genres TEXT,
    poster_file TEXT,
    watched INTEGER NOT NULL DEFAULT 0,
    personal_rating INTEGER,
    notes TEXT,
    location TEXT,
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
    personal_rating INTEGER,
    notes TEXT,
    added_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(external_source, external_id)
);
"""

FORMATS = ["4K UHD", "Blu-ray", "DVD", "Digital", "VHS", "Other"]

LOCATIONS = ["Shelf", "Drive"]

PLATFORMS = ["PC", "PS5", "PS4", "PS3", "Switch", "Xbox", "Other"]

STORES = ["Steam", "PSN", "Physical", "Battle.net", "GOG", "Other"]

STATUSES = ["Backlog", "Playing", "Completed", "Dropped"]

MOVIE_SORTS = {
    "added": "added_at DESC, id DESC",
    "title": "title COLLATE NOCASE ASC",
    "year": "year DESC, title COLLATE NOCASE ASC",
    "rating": "personal_rating DESC, title COLLATE NOCASE ASC",
}

GAME_SORTS = {
    "added": "added_at DESC, id DESC",
    "title": "title COLLATE NOCASE ASC",
    "year": "year DESC, title COLLATE NOCASE ASC",
    "rating": "personal_rating DESC, title COLLATE NOCASE ASC",
    "playtime": "playtime_minutes DESC, title COLLATE NOCASE ASC",
}


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(exist_ok=True)
    POSTER_DIR.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)


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

def list_movies(q: str = "", fmt: str = "", watched: str = "", sort: str = "added") -> list[sqlite3.Row]:
    where, params = [], []
    if q:
        where.append("(title LIKE ? OR director LIKE ?)")
        params += [f"%{q}%", f"%{q}%"]
    if fmt:
        where.append("format = ?")
        params.append(fmt)
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

def list_games(q: str = "", platform: str = "", status: str = "", sort: str = "added") -> list[sqlite3.Row]:
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


def update_game_by_external(source: str, external_id: str, **fields) -> None:
    sets = ", ".join(f"{col} = ?" for col in fields)
    with connect() as conn:
        conn.execute(
            f"UPDATE games SET {sets} WHERE external_source = ? AND external_id = ?",
            [*fields.values(), source, external_id],
        )


def random_game_id(backlog_only: bool = True) -> int | None:
    sql = "SELECT id FROM games"
    if backlog_only:
        sql += " WHERE status = 'Backlog'"
    sql += " ORDER BY RANDOM() LIMIT 1"
    with connect() as conn:
        row = conn.execute(sql).fetchone()
        return row["id"] if row else None


def game_stats() -> dict:
    with connect() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS total,
                   COALESCE(SUM(status = 'Backlog'), 0) AS backlog,
                   COALESCE(SUM(status = 'Completed'), 0) AS completed,
                   COALESCE(SUM(playtime_minutes), 0) AS playtime_minutes
            FROM games
            """
        ).fetchone()
        return dict(row)
