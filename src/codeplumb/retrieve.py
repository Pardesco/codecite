"""Hybrid retrieval: vector + full-text candidates, RRF fusion, section grouping, amendment overlay."""

from __future__ import annotations

import re
from collections import defaultdict

import psycopg

from codeplumb.config import get_settings
from codeplumb.db import queries as q
from codeplumb.embed.base import Embedder

_SECTION_REF = re.compile(r"(?<![\d.])(\d{3,4}(?:\.\d+)+|4101:\d{1,2}-\d{1,2}-\d{2})(?!\d)(?!\.\d)")

MODES = ("vector", "lexical", "hybrid")


def search(
    conn: psycopg.Connection,
    embedder: Embedder,
    query: str,
    *,
    corpora: list[str] | None = None,
    k: int = 8,
    chapter: str | None = None,
    kinds: list[str] | None = None,
    layer: str | None = None,
    mode: str = "hybrid",
) -> dict:
    s = get_settings()
    query = query.strip()
    k = max(1, min(int(k), 20))
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}")
    if corpora:
        for c in corpora:
            q.require_corpus(conn, c)

    where = ["TRUE"]
    params: list = []
    if corpora:
        where.append("c.corpus_id = ANY(%s)")
        params.append(list(corpora))
    if kinds:
        where.append("c.kind = ANY(%s)")
        params.append(list(kinds))
    if layer:
        where.append("d.layer = %s")
        params.append(layer)
    if chapter:
        where.append("split_part(s.number, '.', 1) LIKE %s")
        params.append(f"{chapter}%")
    filt = " AND ".join(where)
    base_sql = (
        "FROM chunks c JOIN sections s ON s.id = c.section_id JOIN documents d ON d.id = s.document_id"
        f" WHERE {filt}"
    )
    limit = s.candidate_limit

    vector_ranks: dict[int, int] = {}
    lexical_ranks: dict[int, int] = {}
    chunk_meta: dict[int, dict] = {}
    top_similarity = 0.0
    strict_hits = 0

    with conn.transaction():
        with conn.cursor() as cur:
            if mode in ("vector", "hybrid"):
                vec = embedder.embed_query(query)
                cur.execute("SET LOCAL hnsw.ef_search = 100")
                cur.execute(
                    f"SELECT c.id, c.section_id, c.kind, c.ordinal, c.content, 1 - (c.embedding <=> %s::vector) AS sim"
                    f" {base_sql} ORDER BY c.embedding <=> %s::vector LIMIT %s",
                    [vec] + params + [vec, limit],
                )
                for rank, row in enumerate(cur.fetchall(), 1):
                    vector_ranks[row["id"]] = rank
                    chunk_meta[row["id"]] = row
                    top_similarity = max(top_similarity, float(row["sim"]))
            if mode in ("lexical", "hybrid"):
                # exact section-number mentions are injected as top lexical hits
                rank = 0
                for num in _SECTION_REF.findall(query):
                    cur.execute(
                        f"SELECT c.id, c.section_id, c.kind, c.ordinal, c.content {base_sql} AND s.number = %s"
                        " ORDER BY c.kind = 'body' DESC, c.ordinal",
                        params + [num],
                    )
                    for row in cur.fetchall():
                        rank += 1
                        lexical_ranks[row["id"]] = rank
                        chunk_meta[row["id"]] = row
                # strict (AND) pass first, then an OR pass so natural-language questions still surface candidates
                for tsq, arg in (("websearch_to_tsquery('english', %s)", query), ("_codeplumb_or_query(%s)", query)):
                    cur.execute(
                        f"SELECT c.id, c.section_id, c.kind, c.ordinal, c.content, ts_rank_cd(c.tsv, {tsq}) AS r"
                        f" {base_sql} AND c.tsv @@ {tsq} ORDER BY r DESC LIMIT %s",
                        [arg] + params + [arg, limit],
                    )
                    for row in cur.fetchall():
                        if row["id"] in lexical_ranks:
                            continue
                        rank += 1
                        lexical_ranks[row["id"]] = rank
                        chunk_meta[row["id"]] = row
                    if tsq.startswith("websearch"):
                        strict_hits = len(lexical_ranks)
                    if len(lexical_ranks) >= limit:
                        break

    # Reciprocal Rank Fusion over chunk ids
    rrf_k = s.rrf_k
    fused: dict[int, float] = defaultdict(float)
    for cid, r in vector_ranks.items():
        fused[cid] += 1.0 / (rrf_k + r)
    for cid, r in lexical_ranks.items():
        fused[cid] += 1.0 / (rrf_k + r)

    # group to sections
    per_section: dict[int, dict] = {}
    for cid, score in fused.items():
        m = chunk_meta[cid]
        sid = m["section_id"]
        entry = per_section.setdefault(sid, {"score": 0.0, "chunks": [], "vector_rank": None, "lexical_rank": None})
        entry["score"] = max(entry["score"], score)
        entry["chunks"].append({"kind": m["kind"], "ordinal": m["ordinal"], "excerpt": m["content"][:300], "score": score})
        vr, lr = vector_ranks.get(cid), lexical_ranks.get(cid)
        if vr is not None:
            entry["vector_rank"] = vr if entry["vector_rank"] is None else min(entry["vector_rank"], vr)
        if lr is not None:
            entry["lexical_rank"] = lr if entry["lexical_rank"] is None else min(entry["lexical_rank"], lr)

    ranked = sorted(per_section.items(), key=lambda kv: -kv[1]["score"])[: k * 2]

    hits: list[dict] = []
    seen_sections: set[int] = set()
    for sid, entry in ranked:
        if len(hits) >= k:
            break
        if sid in seen_sections:
            continue
        sec = _load_section(conn, sid)
        detail = q.section_detail(conn, sec)
        # amendment overlay: surface the amendment directly above the base hit
        if detail["amended_by"] and sec["layer"] == "base":
            a = q.find_section(conn, sec["number"], sec["corpus_id"], layer="amendment")
            if a and a["id"] not in seen_sections:
                ad = q.section_detail(conn, a)
                ad["matched_chunks"] = []
                ad["scores"] = {"rrf": entry["score"], "vector_rank": None, "lexical_rank": None, "rerank": None, "overlay": True}
                hits.append(ad)
                seen_sections.add(a["id"])
        entry["chunks"].sort(key=lambda c: -c["score"])
        detail["matched_chunks"] = [{k2: v for k2, v in c.items() if k2 != "score"} for c in entry["chunks"]]
        detail["scores"] = {
            "rrf": round(entry["score"], 5),
            "vector_rank": entry["vector_rank"],
            "lexical_rank": entry["lexical_rank"],
            "rerank": None,
        }
        hits.append(detail)
        seen_sections.add(sid)

    # abstain heuristic: no strict full-text match and the nearest vector is far away
    sim_floor = getattr(embedder, "abstain_similarity", s.abstain_similarity)
    if mode == "lexical":
        abstain = strict_hits == 0
    elif mode == "vector":
        abstain = top_similarity < sim_floor
    else:
        abstain = strict_hits == 0 and top_similarity < sim_floor
    return {
        "query": query,
        "hits": hits[:k] if not any(h["scores"].get("overlay") for h in hits) else hits[: k + 1],
        "abstain": abstain,
        "confidence": {"strict_lexical_hits": strict_hits, "top_vector_similarity": round(top_similarity, 4)},
        "provenance": {"embedding_model": embedder.name, "retrieval": f"{mode}-rrf" if mode == "hybrid" else mode, "reranked": False},
    }


def _load_section(conn: psycopg.Connection, section_id: int) -> dict:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT s.*, d.title AS document_title, d.layer, d.version, c.title AS corpus_title"
            " FROM sections s JOIN documents d ON d.id = s.document_id JOIN corpora c ON c.id = s.corpus_id"
            " WHERE s.id = %s",
            (section_id,),
        )
        return cur.fetchone()


def get_section(conn: psycopg.Connection, number: str, corpus: str | None = None, include_children: bool = False, include_tables: bool = True) -> dict:
    if corpus:
        q.require_corpus(conn, corpus)
    sec = q.find_section(conn, number, corpus)
    if not sec:
        near = q.nearest_numbers(conn, number, corpus)
        where = f" in {corpus}" if corpus else ""
        raise q.NotFound(f"section '{number}' not found{where}; nearest: {', '.join(near) or 'none'}")
    return q.section_detail(conn, sec, include_children, include_tables)


def get_context(conn: psycopg.Connection, number: str, corpus: str | None = None) -> dict:
    if corpus:
        q.require_corpus(conn, corpus)
    sec = q.find_section(conn, number, corpus, layer="base") or q.find_section(conn, number, corpus)
    if not sec:
        near = q.nearest_numbers(conn, number, corpus)
        raise q.NotFound(f"section '{number}' not found; nearest: {', '.join(near) or 'none'}")
    prev, nxt = q.siblings(conn, sec)
    return {
        "corpus": sec["corpus_id"],
        "section": {"number": sec["number"], "title": sec["title"], "path": sec["path"]},
        "ancestors": [{"number": a["number"], "title": a["title"]} for a in q.ancestors(conn, sec["id"])],
        "previous": {"number": prev["number"], "title": prev["title"]} if prev else None,
        "next": {"number": nxt["number"], "title": nxt["title"]} if nxt else None,
        "children": [{"number": c["number"], "title": c["title"]} for c in q.section_children(conn, sec["id"])],
        "referenced_by": q.referenced_by(conn, sec["id"]),
        "citation": q.citation(sec),
    }


def resolve_reference(conn: psycopg.Connection, text: str, corpus: str | None = None) -> list[dict]:
    from codeplumb.extract.crossrefs import find_cross_refs

    refs = find_cross_refs(text)
    for num in _SECTION_REF.findall(text):
        if not any(r[1] == num for r in refs):
            refs.append((num, num, "section"))
    out = []
    for ref_text, num, kind in refs:
        sec = q.find_section(conn, num, corpus)
        out.append({"ref_text": ref_text, "number": num, "kind": kind,
                    "corpus": sec["corpus_id"] if sec else None, "found": sec is not None,
                    "title": sec["title"] if sec else None})
    return out
