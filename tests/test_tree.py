from pathlib import Path

from codecite.ingest import parse_to_tree
from codecite.parse.base import Block
from codecite.parse.markdown import parse_markdown_text
from codecite.profiles import get_profile
from codecite.tree import build_tree

SAMPLE = Path(__file__).resolve().parent.parent / "samples" / "sample-building-code" / "model-building-code-2026.md"


def _by_number(sections):
    return {s.number: s for s in sections}


def test_sample_tree_shape():
    secs = parse_to_tree(SAMPLE, "ibc", "MBC")
    by = _by_number(secs)
    assert by["10"].depth == 0 and by["10"].parent is None
    assert by["1004"].parent == by["10"].ordinal
    assert by["1004.5"].parent == by["1004"].ordinal and by["1004.5"].depth == 2
    assert by["1004.5.1"].parent == by["1004.5"].ordinal
    assert by["1004.5"].path == "MBC > 10 Means Of Egress > 1004 Occupant Load > 1004.5 Areas without fixed seating"
    assert len(secs) > 100


def test_table_attached_to_captioned_section():
    by = _by_number(parse_to_tree(SAMPLE, "ibc"))
    assert len(by["1004.5"].tables) == 1
    assert by["1004.5"].tables[0].caption.startswith("Table 1004.5")
    assert "150 gross" in by["1004.5"].tables[0].markdown
    assert by["1004"].tables == []


def test_body_excludes_children():
    by = _by_number(parse_to_tree(SAMPLE, "ibc"))
    assert "Increased occupant load" not in by["1004.5"].body
    assert by["1004"].paragraphs == []  # pure container


def test_amendment_layer_sets_supersedes():
    amend = SAMPLE.parent / "local-amendments-2026.md"
    by = _by_number(parse_to_tree(amend, "ibc", layer="amendment"))
    assert by["1004.5"].supersedes == "1004.5"
    assert by["10"].supersedes is None


def test_inline_pdf_style_heading_and_reflow_guard():
    text = """# CHAPTER 10 MEANS OF EGRESS
## SECTION 1004 OCCUPANT LOAD

1004.5 Areas without fixed seating. Body of 1004.5 here.

1004.2 Backwards number. This should be treated as text, not a heading.

1004.6 Fixed seating. Body of 1004.6.
"""
    secs = build_tree(parse_markdown_text(text), get_profile("ibc"))
    nums = [s.number for s in secs]
    assert nums == ["10", "1004", "1004.5", "1004.6"]
    assert "Backwards number" in _by_number(secs)["1004.5"].body


def test_generic_profile_markdown():
    text = "# Acme Standards\n\nIntro.\n\n## 3 Egress\n\n### 3.1 Corridor width\n\n60 inches.\n\n## Appendix\n\nNotes.\n"
    secs = build_tree(parse_markdown_text(text), get_profile("generic"))
    nums = [s.number for s in secs]
    assert nums[0].startswith("H1-") and "3" in nums and "3.1" in nums
    assert _by_number(secs)["3.1"].parent == _by_number(secs)["3"].ordinal


def test_duplicate_numbers_get_alias():

    blocks = [
        Block("heading", "4101:1-3-01 Occupancy classification and use."),
        Block("heading", "(F) Modify table 307.1(1) as follows:"),
        Block("paragraph", "first"),
        Block("heading", "(G) Modify footnote i to table 307.1(1) to read:"),
        Block("paragraph", "second"),
    ]
    secs = build_tree(blocks, get_profile("oac"))
    assert [s.number for s in secs] == ["4101:1-3-01", "307.1", "307.1(G)"]
    assert all(s.supersedes == "307.1" for s in secs[1:])


def test_pdf_wrapped_heading_merge_rule():
    from codecite.parse.pdf import _continues_heading

    head = Block("heading", "(A)Modify Section 1001.1to add the following sentence at the end of the", font_size=12.0, bold=True)
    assert _continues_heading(head, "paragraph:", 12.0, True)
    assert not _continues_heading(head, "1010.2.16 Temporary door locking devices.", 12.0, True)
    done = Block("heading", "(H) Add Section 1010.2.16 to read as follows:", font_size=12.0, bold=True)
    assert not _continues_heading(done, "anything", 12.0, True)
