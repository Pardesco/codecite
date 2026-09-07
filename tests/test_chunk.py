from pathlib import Path

from codeplumb.chunk import HARD_CAP, chunk_section, count_tokens, split_to_fit
from codeplumb.ingest import parse_to_tree
from codeplumb.profiles import get_profile
from codeplumb.tree import Section

SAMPLE = Path(__file__).resolve().parent.parent / "samples" / "sample-building-code" / "model-building-code-2026.md"
ibc = get_profile("ibc")


def _sections():
    return {s.number: s for s in parse_to_tree(SAMPLE, "ibc", "MBC")}


def test_breadcrumb_prefix_and_kinds():
    chunks, body, refs = chunk_section(_sections()["1004.5"], ibc)
    kinds = sorted(c.kind for c in chunks)
    assert kinds == ["body", "exception", "table"]
    for c in chunks:
        assert c.text.startswith("MBC > 10 Means Of Egress > 1004 Occupant Load > 1004.5")
        assert c.token_count == count_tokens(c.text)
    body_chunk = next(c for c in chunks if c.kind == "body")
    assert "Exception:" not in body_chunk.content  # exceptions pulled out of the body chunk
    assert "Exception:" in body  # but the stored section body stays complete
    assert any(n == "1004.5" and k == "table" for _, n, k in refs)


def test_numbered_exceptions_are_one_block():
    chunks, _, _ = chunk_section(_sections()["1020.2"], ibc)
    exc = [c for c in chunks if c.kind == "exception"]
    assert len(exc) == 1
    assert "Ninety-six inches" in exc[0].content and exc[0].content.startswith("Exceptions:")


def test_definitions_split_per_term():
    chunks, _, _ = chunk_section(_sections()["202"], ibc)
    defs = [c for c in chunks if c.kind == "definition"]
    assert len(defs) >= 15
    assert any(c.content.startswith("Definition of MEANS OF EGRESS:") for c in defs)
    assert not [c for c in chunks if c.kind == "body"]


def test_empty_container_has_no_chunks():
    chunks, _, _ = chunk_section(_sections()["1004"], ibc)
    assert chunks == []


def test_long_section_splits_under_cap_at_sentences():
    para = " ".join(f"Sentence number {i} says something about egress width and capacity." for i in range(400))
    sec = Section(number="9999.1", title="Long", depth=2, ordinal=0, paragraphs=[para], path="X > 9999.1 Long")
    chunks, _, _ = chunk_section(sec, ibc)
    assert len(chunks) > 1
    for c in chunks:
        assert c.token_count <= HARD_CAP
        assert c.content.endswith(".")
    assert [c.ordinal for c in chunks] == list(range(len(chunks)))
    assert "".join(c.content for c in chunks).replace(" ", "") == para.replace(" ", "")


def test_split_to_fit_packs_short_paragraphs():
    pieces = split_to_fit(["short one.", "short two.", "short three."], "crumb")
    assert pieces == ["short one.\n\nshort two.\n\nshort three."]
