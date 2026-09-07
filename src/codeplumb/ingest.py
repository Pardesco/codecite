"""Ingestion: file -> blocks -> tree -> chunks -> embeddings -> one transaction."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

from codeplumb.chunk import chunk_section
from codeplumb.embed.base import Embedder
from codeplumb.parse import parse_file
from codeplumb.profiles import get_profile
from codeplumb.tree import Section, build_tree, render_tree


class AlreadyIngested(Exception):
    pass


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def ensure_corpus(conn: psycopg.Connection, corpus_id: str, profile: str, title: str | None = None, jurisdiction: str | None = None) -> dict:
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM corpora WHERE id = %s", (corpus_id,))
        row = cur.fetchone()
        if row:
            return row
        cur.execute(
            "INSERT INTO corpora (id, title, jurisdiction, profile) VALUES (%s, %s, %s, %s) RETURNING *",
            (corpus_id, title or corpus_id, jurisdiction, profile),
        )
        return cur.fetchone()


def parse_to_tree(path: Path, profile_name: str, corpus_title: str = "", layer: str = "base") -> list[Section]:
    profile = get_profile(profile_name)
    sections = build_tree(parse_file(path), profile, corpus_title)
    if layer == "amendment":
        for s in sections:
            if s.depth > 0 and s.supersedes is None and not s.number.startswith("4101:"):
                s.supersedes = s.number
    return sections


def ingest_document(
    conn: psycopg.Connection,
    path: Path,
    corpus_id: str,
    layer: str,
    profile_name: str,
    embedder: Embedder,
    *,
    title: str | None = None,
    version: str | None = None,
    corpus_title: str | None = None,
    force: bool = False,
) -> dict:
    if layer not in ("base", "amendment"):
        raise ValueError("layer must be 'base' or 'amendment'")
    digest = sha256_file(path)
    corpus = ensure_corpus(conn, corpus_id, profile_name, corpus_title)
    conn.commit()

    with conn.cursor() as cur:
        cur.execute("SELECT id FROM documents WHERE corpus_id = %s AND sha256 = %s", (corpus_id, digest))
        existing = cur.fetchone()
        if existing and not force:
            raise AlreadyIngested(f"{path.name} already ingested into {corpus_id} as document {existing['id']}; use --force")
        cur.execute("INSERT INTO ingest_runs (status) VALUES ('running') RETURNING id")
        run_id = cur.fetchone()["id"]
    conn.commit()

    try:
        sections = parse_to_tree(path, profile_name, corpus["title"], layer)
        profile = get_profile(profile_name)
        per_section = [chunk_section(s, profile) for s in sections]
        all_chunks = [(si, c) for si, (chunks, _, _) in enumerate(per_section) for c in chunks]
        vectors = embedder.embed_documents([c.text for _, c in all_chunks]) if all_chunks else []
        page_count = max((s.page_end or 0) for s in sections) or None if sections else None

        with conn.transaction():
            with conn.cursor() as cur:
                if existing:
                    cur.execute("DELETE FROM documents WHERE id = %s", (existing["id"],))
                cur.execute(
                    "INSERT INTO documents (corpus_id, title, layer, version, source_path, sha256, page_count)"
                    " VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
                    (corpus_id, title or path.stem, layer, version, str(path), digest, page_count),
                )
                doc_id = cur.fetchone()["id"]
                ids: dict[int, int] = {}
                for si, (s, (_, clean_body, _)) in enumerate(zip(sections, per_section, strict=True)):
                    cur.execute(
                        "INSERT INTO sections (document_id, corpus_id, parent_id, number, number_norm, title, depth,"
                        " path, body, page_start, page_end, ordinal, supersedes_number)"
                        " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                        (
                            doc_id, corpus_id, ids.get(s.parent) if s.parent is not None else None,
                            s.number, s.number_norm, s.title, s.depth, s.path, clean_body,
                            s.page_start, s.page_end, s.ordinal, s.supersedes,
                        ),
                    )
                    ids[si] = cur.fetchone()["id"]
                for (si, c), vec in zip(all_chunks, vectors, strict=True):
                    cur.execute(
                        "INSERT INTO chunks (section_id, corpus_id, kind, ordinal, text, content, token_count,"
                        " page_start, page_end, embedding) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (ids[si], corpus_id, c.kind, c.ordinal, c.text, c.content, c.token_count,
                         c.page_start, c.page_end, vec),
                    )
                unresolved = 0
                n_refs = 0
                for si, (_, _, refs) in enumerate(per_section):
                    for ref_text, num, kind in refs:
                        to_id = resolve_section_id(cur, corpus_id, num)
                        unresolved += to_id is None
                        n_refs += 1
                        cur.execute(
                            "INSERT INTO cross_refs (from_section_id, ref_text, ref_number, ref_kind, to_section_id)"
                            " VALUES (%s,%s,%s,%s,%s)",
                            (ids[si], ref_text, num, kind, to_id),
                        )
                # resolve dangling refs from earlier documents that point at numbers this document defines
                cur.execute(
                    "UPDATE cross_refs cr SET to_section_id = s.id FROM sections s"
                    " WHERE cr.to_section_id IS NULL AND s.document_id = %s AND s.corpus_id = %s"
                    " AND s.number = cr.ref_number AND cr.from_section_id IN"
                    " (SELECT id FROM sections WHERE corpus_id = %s)",
                    (doc_id, corpus_id, corpus_id),
                )
                stats = {
                    "document_id": doc_id,
                    "sections": len(sections),
                    "chunks": len(all_chunks),
                    "tables": sum(len(s.tables) for s in sections),
                    "exceptions": sum(1 for _, c in all_chunks if c.kind == "exception"),
                    "definitions": sum(1 for _, c in all_chunks if c.kind == "definition"),
                    "cross_refs": n_refs,
                    "unresolved_refs": unresolved,
                }
                cur.execute(
                    "UPDATE ingest_runs SET document_id = %s, finished_at = now(), status = 'ok', stats = %s WHERE id = %s",
                    (doc_id, Jsonb(stats), run_id),
                )
        return stats
    except Exception as e:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE ingest_runs SET finished_at = now(), status = 'failed', error = %s WHERE id = %s",
                (str(e)[:2000], run_id),
            )
        conn.commit()
        raise


def resolve_section_id(cur, corpus_id: str, number: str) -> int | None:
    """Prefer the amendment layer, then base."""
    cur.execute(
        "SELECT s.id FROM sections s JOIN documents d ON d.id = s.document_id"
        " WHERE s.corpus_id = %s AND s.number = %s"
        " ORDER BY (d.layer = 'amendment') DESC, s.id LIMIT 1",
        (corpus_id, number),
    )
    row = cur.fetchone()
    return row["id"] if row else None


def dry_run_tree(path: Path, profile_name: str, layer: str = "base") -> str:
    return render_tree(parse_to_tree(path, profile_name, "", layer))


def dump_stats(stats: dict) -> str:
    return json.dumps(stats, indent=2)
