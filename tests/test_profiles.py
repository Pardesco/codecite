import pytest

from codeplumb.parse.base import Block
from codeplumb.profiles import get_profile, normalize_number
from codeplumb.profiles.base import strip_ref_prefix

ibc = get_profile("ibc")


@pytest.mark.parametrize(
    "kind,text,number,title,depth,hkind",
    [
        ("heading", "CHAPTER 10 MEANS OF EGRESS", "10", "Means Of Egress", 0, "section"),
        ("heading", "SECTION 1004 OCCUPANT LOAD", "1004", "Occupant Load", 1, "section"),
        ("heading", "1004.5 Areas without fixed seating", "1004.5", "Areas without fixed seating", 2, "section"),
        ("paragraph", "1004.5.1 Increased occupant load. The occupant load permitted...", "1004.5.1", "Increased occupant load", 3, "section"),
        ("paragraph", "TABLE 1004.5 MAXIMUM FLOOR AREA ALLOWANCES", "1004.5", "Maximum Floor Area Allowances", 2, "table-caption"),
    ],
)
def test_ibc_grammar(kind, text, number, title, depth, hkind):
    h = ibc.match(Block(kind, text), 0)
    assert h is not None
    assert (h.number, h.title, h.depth, h.kind) == (number, title, depth, hkind)


def test_ibc_inline_keeps_remainder():
    h = ibc.match(Block("paragraph", "1004.5.1 Increased occupant load. The occupant load permitted is X."), 0)
    assert h.remainder == "The occupant load permitted is X."


@pytest.mark.parametrize("text", ["See Section 1010.1.1 for doors.", "1004.5 psi", "Exception: none", "The 2021 edition"])
def test_ibc_rejects_non_headings(text):
    assert ibc.match(Block("paragraph", text), 0) is None


def test_oac_rule_and_subgrammar():
    oac = get_profile("oac")
    r = oac.match(Block("heading", "4101:1-10-04 Occupant load."), 0)
    assert r.number == "4101:1-10-04" and r.depth == 0 and r.supersedes is None
    s = oac.match(Block("heading", "1004.5 Areas without fixed seating"), 1)
    assert s.number == "1004.5" and s.supersedes == "1004.5"


def test_generic_numbered_and_synthetic():
    g = get_profile("generic")
    assert g.match(Block("heading", "3.2 Dead-end corridors", level=3), 7).number == "3.2"
    h = g.match(Block("heading", "Introduction", level=2), 7)
    assert h.number == "H2-0007" and h.depth == 1


def test_normalize_number_sorts():
    nums = ["1004.5", "1004.10", "1004.5.1", "1004"]
    assert sorted(nums, key=normalize_number) == ["1004", "1004.5", "1004.5.1", "1004.10"]


@pytest.mark.parametrize("raw,want", [("Section 1004.5", "1004.5"), ("§1004.5", "1004.5"), ("Table 1004.5.", "1004.5"), ("1004.5", "1004.5")])
def test_strip_ref_prefix(raw, want):
    assert strip_ref_prefix(raw) == want


def test_oac_instruction_headings():
    oac = get_profile("oac")
    h = oac.match(Block("heading", "(A)Modify Section 1001.1to add the following sentence at the end of the paragraph:"), 0)
    assert (h.number, h.depth, h.supersedes, h.alias) == ("1001.1", 1, "1001.1", "A")
    assert h.title.startswith("(A) Modify Section 1001.1")
    t = oac.match(Block("heading", "(J) Replace Table 1020.2 with the following:"), 1)
    assert t.number == "1020.2" and t.supersedes == "1020.2"
    assert oac.match(Block("paragraph", "(A) Modify Section 1001.1 ..."), 2) is None  # only bold/heading blocks
