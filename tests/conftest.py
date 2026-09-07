from __future__ import annotations

import os
from pathlib import Path

import psycopg
import pytest

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "samples" / "sample-building-code"
TEST_URL = os.environ.get(
    "CODEPLUMB_TEST_DATABASE_URL", "postgresql://codeplumb:codeplumb@127.0.0.1:5432/codeplumb_test"
)

os.environ["CODEPLUMB_DATABASE_URL"] = TEST_URL
os.environ["CODEPLUMB_EMBED_PROVIDER"] = "fake"


def _ensure_test_db() -> bool:
    admin = TEST_URL.rsplit("/", 1)[0] + "/postgres"
    try:
        with psycopg.connect(admin, autocommit=True, connect_timeout=3) as c:
            name = TEST_URL.rsplit("/", 1)[1]
            exists = c.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,)).fetchone()
            if not exists:
                c.execute(f'CREATE DATABASE "{name}"')
        return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def db():
    """Fresh schema + the synthetic corpus (base + amendments), embedded with the fake embedder."""
    if not _ensure_test_db():
        pytest.skip("Postgres not reachable at CODEPLUMB_TEST_DATABASE_URL (docker compose up -d)")
    from codeplumb.db.pool import apply_migrations, connect, drop_all
    from codeplumb.embed import FakeEmbedder
    from codeplumb.ingest import ingest_document

    conn = connect(TEST_URL)
    drop_all(conn)
    emb = FakeEmbedder(768)
    apply_migrations(conn, emb.dimensions)
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO embedding_config (provider, model, dimensions) VALUES (%s, %s, %s)",
            (emb.provider, emb.model, emb.dimensions),
        )
    conn.commit()
    ingest_document(
        conn, SAMPLES / "model-building-code-2026.md", "sample-bc-2026", "base", "ibc", emb,
        title="Model Building Code", version="2026", corpus_title="Model Building Code 2026",
    )
    ingest_document(
        conn, SAMPLES / "local-amendments-2026.md", "sample-bc-2026", "amendment", "ibc", emb,
        title="Local Amendments", version="2026",
    )
    ingest_document(
        conn, ROOT / "samples" / "acme-standards" / "acme-design-standards.md", "acme-standards", "base",
        "generic", emb, title="Acme Design Standards", corpus_title="Acme Engineering Design Standards",
    )
    yield conn, emb
    conn.close()
