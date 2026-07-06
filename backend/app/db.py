import os
import re
import sqlite3
from datetime import datetime
from pathlib import Path

# Default to the repo-root macros.db so existing data is picked up unchanged.
DEFAULT_DB = Path(__file__).resolve().parent.parent.parent / "macros.db"


def get_db_path() -> str:
    return os.environ.get("DATABASE_PATH", str(DEFAULT_DB))


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def _existing_columns(cur: sqlite3.Cursor, table: str) -> set[str]:
    cur.execute(f"PRAGMA table_info({table})")
    return {row[1] for row in cur.fetchall()}


def init_db() -> None:
    """Create tables and migrate a pre-existing v1 meals table in place."""
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS meals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            name TEXT NOT NULL,
            calories REAL NOT NULL,
            protein REAL NOT NULL,
            carbs REAL,
            fat REAL
        )
    """)

    # v1 databases have meals without carbs/fat — add them, keeping old rows.
    existing = _existing_columns(cur, "meals")
    for column in ("carbs", "fat"):
        if column not in existing:
            cur.execute(f"ALTER TABLE meals ADD COLUMN {column} REAL")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS foods (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE COLLATE NOCASE,
            serving_size REAL NOT NULL,
            calories REAL NOT NULL,
            protein REAL NOT NULL,
            carbs REAL,
            fat REAL,
            source TEXT NOT NULL DEFAULT 'user'
                CHECK (source IN ('user', 'openfoodfacts')),
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            calorie_goal REAL NOT NULL DEFAULT 2000,
            protein_goal REAL NOT NULL DEFAULT 150,
            carbs_goal REAL NOT NULL DEFAULT 250,
            fat_goal REAL NOT NULL DEFAULT 70,
            track_carbs INTEGER NOT NULL DEFAULT 0,
            track_fat INTEGER NOT NULL DEFAULT 0
        )
    """)
    cur.execute("INSERT OR IGNORE INTO settings (id) VALUES (1)")

    _normalize_meal_dates(cur)

    conn.commit()
    conn.close()


# The v1 app stored some dates in non-ISO formats (e.g. 2026/03/22).
_LEGACY_DATE_FORMATS = ("%Y/%m/%d", "%d/%m/%Y", "%d-%m-%Y")


def _normalize_meal_dates(cur: sqlite3.Cursor) -> None:
    """One-time cleanup: rewrite non-ISO meal dates to YYYY-MM-DD."""
    cur.execute("SELECT DISTINCT date FROM meals")
    for (raw,) in cur.fetchall():
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw or ""):
            continue
        for fmt in _LEGACY_DATE_FORMATS:
            try:
                fixed = datetime.strptime(raw.strip(), fmt).date().isoformat()
            except (ValueError, AttributeError):
                continue
            cur.execute("UPDATE meals SET date = ? WHERE date = ?", (fixed, raw))
            break
