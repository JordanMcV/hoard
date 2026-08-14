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
"""

FORMATS = ["4K UHD", "Blu-ray", "DVD", "Digital", "VHS", "Other"]

LOCATIONS = ["Shelf", "Drive"]

SORTS = {
    "added": "added_at DESC, id DESC",
    "title": "title COLLATE NOCASE ASC",
    "year": "year DESC, title COLLATE NOCASE ASC",
    "rating": "personal_rating DESC, title COLLATE NOCASE ASC",
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
    sql += " ORDER BY " + SORTS.get(sort, SORTS["added"])
    with connect() as conn:
        return conn.execute(sql, params).fetchall()


def get_movie(movie_id: int) -> sqlite3.Row | None:
    with connect() as conn:
        return conn.execute("SELECT * FROM movies WHERE id = ?", (movie_id,)).fetchone()


def add_movie(**fields) -> int:
    cols = ", ".join(fields)
    marks = ", ".join("?" for _ in fields)
    with connect() as conn:
        cur = conn.execute(f"INSERT INTO movies ({cols}) VALUES ({marks})", list(fields.values()))
        return cur.lastrowid


def update_movie(movie_id: int, **fields) -> None:
    sets = ", ".join(f"{col} = ?" for col in fields)
    with connect() as conn:
        conn.execute(f"UPDATE movies SET {sets} WHERE id = ?", [*fields.values(), movie_id])


def delete_movie(movie_id: int) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM movies WHERE id = ?", (movie_id,))


def stats() -> dict:
    with connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS total, COALESCE(SUM(watched), 0) AS watched FROM movies"
        ).fetchone()
        return {"total": row["total"], "watched": row["watched"]}
