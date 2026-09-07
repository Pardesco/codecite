import pytest

from codeplumb.db import queries as q
from codeplumb.retrieve import get_context, get_section, resolve_reference, search


def _numbers(res):
    return [h["section"]["number"] for h in res["hits"]]


def test_ingest_stats(db):
    conn, _ = db
    corpora = {c["id"]: c for c in q.list_corpora(conn)}
    assert corpora["sample-bc-2026"]["sections"] > 100
    assert corpora["sample-bc-2026"]["chunks"] > 100
    assert {d["layer"] for d in corpora["sample-bc-2026"]["documents"]} == {"base", "amendment"}
    assert corpora["acme-standards"]["profile"] == "generic"
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) AS n FROM cross_refs WHERE to_section_id IS NOT NULL")
        assert cur.fetchone()["n"] > 30
        cur.execute("SELECT kind, count(*) AS n FROM chunks GROUP BY kind")
        kinds = {r["kind"]: r["n"] for r in cur.fetchall()}
    assert kinds["table"] >= 10 and kinds["exception"] >= 20 and kinds["definition"] >= 15


def test_hybrid_finds_table_section(db):
    conn, emb = db
    res = search(conn, emb, "occupant load factor business areas", corpora=["sample-bc-2026"], k=5)
    nums = _numbers(res)
    assert "1004.5" in nums[:3]
    hit = next(h for h in res["hits"] if h["section"]["number"] == "1004.5" and h["document"]["layer"] == "base")
    assert any(c["kind"] == "table" for c in hit["matched_chunks"])
    assert hit["citation"].startswith("Model Building Code §1004.5")
    assert res["provenance"]["retrieval"] == "hybrid-rrf"


def test_amendment_overlay_sits_above_base(db):
    conn, emb = db
    res = search(conn, emb, "occupant load factor business areas", corpora=["sample-bc-2026"], k=5)
    hits = res["hits"]
    idx = [i for i, h in enumerate(hits) if h["section"]["number"] == "1004.5"]
    assert len(idx) == 2
    assert hits[idx[0]]["document"]["layer"] == "amendment"
    assert hits[idx[1]]["document"]["layer"] == "base"
    assert hits[idx[1]]["amended_by"]["section_number"] == "1004.5"
    assert "as amended by" in hits[idx[1]]["citation"]


def test_exact_number_short_circuit(db):
    conn, emb = db
    res = search(conn, emb, "what does 1017.3 say", corpora=["sample-bc-2026"], k=3)
    assert _numbers(res)[0] == "1017.3"


def test_lexical_and_vector_modes(db):
    conn, emb = db
    for mode in ("lexical", "vector"):
        res = search(conn, emb, "handrail circular cross section diameter", corpora=["sample-bc-2026"], k=5, mode=mode)
        assert "1014.3" in _numbers(res), mode


def test_kind_and_layer_filters(db):
    conn, emb = db
    res = search(conn, emb, "corridor width", corpora=["sample-bc-2026"], k=5, kinds=["exception"])
    assert all(c["kind"] == "exception" for h in res["hits"] for c in h["matched_chunks"])
    res = search(conn, emb, "dead end corridor", corpora=["sample-bc-2026"], k=5, layer="amendment")
    assert all(h["document"]["layer"] == "amendment" for h in res["hits"])


def test_unknown_corpus_errors(db):
    conn, emb = db
    with pytest.raises(q.NotFound, match="corpus 'nope' not found; available: acme-standards, sample-bc-2026, sample-bc-2026__naive"):
        search(conn, emb, "anything", corpora=["nope"])


def test_get_section_prefers_amendment_and_lists_extras(db):
    conn, _ = db
    d = get_section(conn, "Section 1020.4", "sample-bc-2026")
    assert d["document"]["layer"] == "amendment"
    base = get_section(conn, "1020.2", "sample-bc-2026", include_children=False)
    assert base["exceptions"] and base["document"]["layer"] == "base"
    tbl = get_section(conn, "§1004.5", "sample-bc-2026")
    assert tbl["document"]["layer"] == "amendment" and tbl["amended_by"] is None
    parent = get_section(conn, "1004", "sample-bc-2026", include_children=True)
    assert [c["number"] for c in parent["children"]][:2] == ["1004.1", "1004.5"]
    assert parent["children"][1]["content"]


def test_get_section_not_found_message(db):
    conn, _ = db
    with pytest.raises(q.NotFound) as ei:
        get_section(conn, "1004.9.9", "sample-bc-2026")
    assert "not found in sample-bc-2026; nearest:" in str(ei.value)


def test_get_context(db):
    conn, _ = db
    ctx = get_context(conn, "1004.5", "sample-bc-2026")
    assert [a["number"] for a in ctx["ancestors"]] == ["10", "1004"]
    assert ctx["previous"]["number"] == "1004.1"
    assert ctx["next"]["number"] == "1004.6"
    assert [c["number"] for c in ctx["children"]] == ["1004.5.1"]
    assert any(r["number"] == "1004.5.1" for r in ctx["referenced_by"])


def test_resolve_reference(db):
    conn, _ = db
    out = resolve_reference(conn, "See Section 1010.1.1 and Table 9999.9 and 1004.5.", "sample-bc-2026")
    found = {r["number"]: r["found"] for r in out}
    assert found["1010.1.1"] is True and found["1004.5"] is True and found["9999.9"] is False


def test_multi_corpus_search(db):
    conn, emb = db
    res = search(conn, emb, "dead-end corridors 20 feet all occupancies", k=8)
    corpora = {h["corpus"] for h in res["hits"]}
    assert "acme-standards" in corpora and "sample-bc-2026" in corpora


def test_reingest_is_noop_without_force(db):
    conn, emb = db
    from codeplumb.ingest import AlreadyIngested, ingest_document
    from tests.conftest import SAMPLES

    with pytest.raises(AlreadyIngested):
        ingest_document(conn, SAMPLES / "model-building-code-2026.md", "sample-bc-2026", "base", "ibc", emb)
