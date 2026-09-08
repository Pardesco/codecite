from __future__ import annotations

import re

from codecite.parse.base import Block
from codecite.profiles.base import Heading
from codecite.profiles.ibc import IBCProfile

RULE = re.compile(r"^(?P<num>4101:\d{1,2}-\d{1,2}-\d{2})\s+(?P<title>.+?)\s*$")
# '(A) Modify Section 1001.1 to add ...' / '(J) Replace Table 1020.2 with the following:'
# PDF extraction sometimes drops spaces ('1001.1to'), so the number is not anchored on whitespace.
INSTRUCTION = re.compile(
    r"^\((?P<letter>[A-Z]{1,2})\)\s*(?P<text>.*?(?:Sections?|Tables?|Chapters?)\s*(?P<num>\d{1,4}(?:\.\d+)*).*)$",
    re.IGNORECASE | re.DOTALL,
)


class OACProfile:
    """Ohio Administrative Code rule headings, with the IBC sub-grammar inside each rule.

    An amendment to IBC 1004.5 inside rule 4101:1-10-04 becomes a section numbered
    '1004.5' with supersedes='1004.5', so the overlay can pair it with the base section.
    """

    name = "oac"
    definitions_title = IBCProfile.definitions_title

    def __init__(self) -> None:
        self._ibc = IBCProfile()

    def match(self, block: Block, ordinal: int) -> Heading | None:
        text = block.text.strip()
        m = RULE.match(text)
        if m and block.kind in ("heading", "paragraph"):
            return Heading(m["num"], m["title"], 0)
        m = INSTRUCTION.match(text)
        if m and block.kind == "heading":
            num = m["num"]
            return Heading(num, f"({m['letter']}) {m['text'].strip()}", 1, supersedes=num, alias=m["letter"])
        h = self._ibc.match(block, ordinal)
        if h is None:
            return None
        if h.kind == "section" and h.depth > 0:
            h.supersedes = h.number
        return h
