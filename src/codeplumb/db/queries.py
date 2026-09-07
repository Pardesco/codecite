"""Read-side SQL helpers shared by the CLI, retrieval, and the MCP server."""

from __future__ import annotations

import psycopg

from codeplumb.profiles.base import strip_ref_prefix


class NotFound(Exception):
    pass


def list_corpora(conn: psycopg.Connection) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT c.id, c.title, c.jurisdiction, c.profile,
                   (SELECT count(*) FROM sections s WHERE s.corpus_id = c.id) AS sections,
                   (SELECT count(*) FROM chunks k WHERE k.corpus_id = c.id) AS chunks,
                   COALESCE((SELECT json_agg(json_build_object('id', d.id, 'title', d.title, 'layer', d.layer,
                                'version', d.version, 'source_path', d.source_path) ORDER BY d.id)
                     FROM documents d WHERE d.corpus_id = c.id), '[]'::json) AS documents
            FROM corpora c ORDER BY c.id
            """
        )
        corpora = cur.fetchall()
        cur.execute("SELECT provider, model, dimensions FROM embedding_config")
        cfg = cur.fetchone()
    return [{**c, "embedding": cfg} for c in corpora]


def corpus_ids(conn: psycopg.Connection) -> list[str]:
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM corpora ORDER BY id")
        return [r["id"] for r in cur.fetchall()]


def require_corpus(conn: psycopg.Connection, corpus: str) -> None:
    ids = corpus_ids(conn)
    if corpus not in ids:
        raise NotFound(f"corpus '{corpus}' not found; available: {', '.join(ids) or '(none)'}")


def list_chapters(conn: psycopg.Connection, corpus: str) -> list[dict]:
    require_corpus(conn, corpus)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT s.number, s.title, d.layer, d.title AS document,"
            " (SELECT count(*) FROM sections c WHERE c.parent_id = s.id) AS sections"
            " FROM sections s JOIN documents d ON d.id = s.document_id"
            " WHERE s.corpus_id = %s AND s.depth = 0 ORDER BY d.layer, s.number_norm",
            (corpus,),
        )
        return cur.fetchall()


def find_section(conn: psycopg.Connection, number: str, corpus: str | None = None, layer: str | None = None) -> dict | None:
    """Exact lookup; amendment layer preferred unless a layer is requested."""
    num = strip_ref_prefix(number)
    sql = (
        "SELECT s.*, d.title AS document_title, d.layer, d.version, c.title AS corpus_title"
        " FROM sections s JOIN documents d ON d.id = s.document_id JOIN corpora c ON c.id = s.corpus_id"
        " WHERE s.number = %s"
    )
    params: list = [num]
    if corpus:
        sql += " AND s.corpus_id = %s"
        params.append(corpus)
    if layer:
        sql += " AND d.layer = %s"
        params.append(layer)
    sql += " ORDER BY (d.layer = 'amendment') DESC, s.id LIMIT 1"
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()


def nearest_numbers(conn: psycopg.Connection, number: str, corpus: str | None, n: int = 3) -> list[str]:
    from codeplumb.profiles.base import normalize_number

    norm = normalize_number(strip_ref_prefix(number))
    with conn.cursor() as cur:
        cur.execute(
            "SELECT number FROM sections WHERE (%s::text IS NULL OR corpus_id = %s) AND depth > 0"
            " ORDER BY abs(length(number_norm) - length(%s)), (number_norm < %s) DESC,"
            " CASE WHEN number_norm < %s THEN number_norm END DESC, number_norm ASC LIMIT %s",
            (corpus, corpus, norm, norm, norm, n),
        )
        return [r["number"] for r in cur.fetchall()]


def section_children(conn: psycopg.Connection, section_id: int) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, number, title, depth, body, page_start, page_end FROM sections"
            " WHERE parent_id = %s ORDER BY ordinal",
            (section_id,),
        )
        return cur.fetchall()


def section_chunks(conn: psycopg.Connection, section_id: int, kinds: tuple[str, ...] = ("table", "exception", "definition")) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT kind, ordinal, content, page_start, page_end FROM chunks"
            " WHERE section_id = %s AND kind = ANY(%s) ORDER BY kind, ordinal",
            (section_id, list(kinds)),
        )
        return cur.fetchall()


def cross_refs_out(conn: psycopg.Connection, section_id: int) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT cr.ref_text, cr.ref_number, cr.ref_kind, cr.to_section_id IS NOT NULL AS resolved"
            " FROM cross_refs cr WHERE cr.from_section_id = %s ORDER BY cr.id",
            (section_id,),
        )
        return cur.fetchall()


def referenced_by(conn: psycopg.Connection, section_id: int) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT s.number, s.title FROM cross_refs cr JOIN sections s ON s.id = cr.from_section_id"
            " WHERE cr.to_section_id = %s ORDER BY s.number",
            (section_id,),
        )
        return cur.fetchall()


def ancestors(conn: psycopg.Connection, section_id: int) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            """
            WITH RECURSIVE up AS (
              SELECT id, parent_id, number, title, depth, 0 AS n FROM sections WHERE id = %s
              UNION ALL
              SELECT s.id, s.parent_id, s.number, s.title, s.depth, up.n + 1
              FROM sections s JOIN up ON s.id = up.parent_id
            )
            SELECT id, number, title, depth FROM up WHERE n > 0 ORDER BY depth
            """,
            (section_id,),
        )
        return cur.fetchall()


def siblings(conn: psycopg.Connection, section: dict) -> tuple[dict | None, dict | None]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, number, title FROM sections WHERE document_id = %s AND parent_id IS NOT DISTINCT FROM %s"
            " AND ordinal < %s ORDER BY ordinal DESC LIMIT 1",
            (section["document_id"], section["parent_id"], section["ordinal"]),
        )
        prev = cur.fetchone()
        cur.execute(
            "SELECT id, number, title FROM sections WHERE document_id = %s AND parent_id IS NOT DISTINCT FROM %s"
            " AND ordinal > %s ORDER BY ordinal ASC LIMIT 1",
            (section["document_id"], section["parent_id"], section["ordinal"]),
        )
        return prev, cur.fetchone()


def amendment_for(conn: psycopg.Connection, corpus: str, number: str) -> dict | None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT s.id, s.number, s.title, s.body, d.title AS document_title, d.version"
            " FROM sections s JOIN documents d ON d.id = s.document_id"
            " WHERE s.corpus_id = %s AND d.layer = 'amendment' AND (s.supersedes_number = %s OR s.number = %s)"
            " ORDER BY s.id LIMIT 1",
            (corpus, number, number),
        )
        return cur.fetchone()


def citation(section: dict) -> str:
    doc = section.get("document_title") or section.get("corpus_title") or section["corpus_id"]
    pages = ""
    if section.get("page_start"):
        pages = f" (p. {section['page_start']})"
    return f"{doc} §{section['number']}{pages}"


def section_detail(conn: psycopg.Connection, section: dict, include_children: bool = False, include_tables: bool = True) -> dict:
    extras = section_chunks(conn, section["id"])
    amended = None
    if section.get("layer") == "base":
        a = amendment_for(conn, section["corpus_id"], section["number"])
        if a:
            amended = {
                "corpus": section["corpus_id"],
                "document": f"{a['document_title']}" + (f" {a['version']}" if a.get("version") else ""),
                "section_number": a["number"],
                "note": "Amendment present; read it first",
            }
    cite = citation(section)
    if amended:
        cite += f", as amended by {amended['document']}"
    out = {
        "corpus": section["corpus_id"],
        "document": {"title": section.get("document_title"), "layer": section.get("layer"), "version": section.get("version")},
        "section": {
            "number": section["number"],
            "title": section.get("title"),
            "path": section["path"],
            "pages": [section.get("page_start"), section.get("page_end")] if section.get("page_start") else None,
        },
        "content": section["body"],
        "exceptions": [c["content"] for c in extras if c["kind"] == "exception"],
        "tables": [c["content"] for c in extras if c["kind"] == "table"] if include_tables else [],
        "definitions": [c["content"] for c in extras if c["kind"] == "definition"],
        "amended_by": amended,
        "cross_refs": [r["ref_text"] for r in cross_refs_out(conn, section["id"])],
        "citation": cite,
    }
    if include_children:
        out["children"] = [
            {"number": c["number"], "title": c["title"], "content": c["body"]} for c in section_children(conn, section["id"])
        ]
    else:
        out["children"] = [{"number": c["number"], "title": c["title"]} for c in section_children(conn, section["id"])]
    return out
