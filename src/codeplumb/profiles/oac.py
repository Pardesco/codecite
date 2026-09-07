from __future__ import annotations

import re

from codeplumb.parse.base import Block
from codeplumb.profiles.base import Heading
from codeplumb.profiles.ibc import IBCProfile

RULE = re.compile(r"^(?P<num>4101:\d{1,2}-\d{1,2}-\d{2})\s+(?P<title>.+?)\s*$")


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
        h = self._ibc.match(block, ordinal)
        if h is None:
            return None
        if h.kind == "section" and h.depth > 0:
            h.supersedes = h.number
        return h
