from __future__ import annotations

from contextlib import contextmanager, suppress
from pathlib import Path

import psycopg
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row

from codeplumb.config import get_settings

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def connect(database_url: str | None = None) -> psycopg.Connection:
    url = database_url or get_settings().database_url
    conn = psycopg.connect(url, row_factory=dict_row, connect_timeout=10)
    with suppress(psycopg.ProgrammingError):  # extension not created yet (pre-init)
        register_vector(conn)
    return conn


@contextmanager
def transaction(database_url: str | None = None):
    conn = connect(database_url)
    try:
        with conn.transaction():
            yield conn
    finally:
        conn.close()


def apply_migrations(conn: psycopg.Connection, dimensions: int) -> list[str]:
    """Run every migrations/NNN_*.sql not yet recorded. `{DIM}` is templated."""
    with conn.cursor() as cur:
        cur.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations "
            "(name text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
        )
        cur.execute("SELECT name FROM schema_migrations")
        done = {r["name"] for r in cur.fetchall()}
        applied = []
        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            if path.name in done:
                continue
            sql = path.read_text(encoding="utf-8").replace("{DIM}", str(dimensions))
            cur.execute(sql)
            cur.execute("INSERT INTO schema_migrations (name) VALUES (%s)", (path.name,))
            applied.append(path.name)
    conn.commit()
    register_vector(conn)
    return applied


def drop_all(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    conn.commit()
