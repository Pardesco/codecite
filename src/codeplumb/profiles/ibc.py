from __future__ import annotations

import re

from codeplumb.parse.base import Block
from codeplumb.profiles.base import Heading

CHAPTER = re.compile(r"^CHAPTER\s+(?P<num>\d{1,2})\s+(?P<title>.+?)\s*$", re.IGNORECASE)
SECTION = re.compile(r"^SECTION\s+(?P<num>\d{3,4})\s+(?P<title>.+?)\s*$", re.IGNORECASE)
TABLE = re.compile(r"^TABLE\s+(?P<num>\d{3,4}(?:\.\d+)*)\s*(?P<title>.*?)\s*$", re.IGNORECASE)
# Heading block form: "1004.5 Areas without fixed seating"
NUMBERED = re.compile(r"^(?P<num>\d{3,4}(?:\.\d+)*)\s+(?P<title>[A-Z][^.]{2,120}?)\.?\s*$")
# Inline (PDF) form: "1004.5 Areas without fixed seating. The number of ..."
INLINE = re.compile(r"^(?P<num>\d{3,4}(?:\.\d+)*)\s+(?P<title>[A-Z][^.]{2,120}?)\.\s+(?P<rest>\S.*)$")


class IBCProfile:
    name = "ibc"
    definitions_title = re.compile(r"\bDEFINITIONS?\b", re.IGNORECASE)

    def match(self, block: Block, ordinal: int) -> Heading | None:
        text = block.text.strip()
        if block.kind == "table":
            return None
        m = CHAPTER.match(text)
        if m:
            return Heading(m["num"], _tc(m["title"]), 0)
        m = SECTION.match(text)
        if m:
            return Heading(m["num"], _tc(m["title"]), 1)
        m = TABLE.match(text)
        if m and block.kind in ("heading", "paragraph"):
            return Heading(m["num"], _tc(m["title"]), depth(m["num"]), kind="table-caption")
        if block.kind == "heading":
            m = NUMBERED.match(text)
            if m:
                return Heading(m["num"], m["title"].strip(), depth(m["num"]))
        if block.kind == "paragraph":
            m = INLINE.match(text)
            if m:
                return Heading(m["num"], m["title"].strip(), depth(m["num"]), remainder=m["rest"])
        return None


def depth(number: str) -> int:
    return number.count(".") + 1


def _tc(title: str) -> str:
    """Title-case an ALL-CAPS heading, leave mixed case alone."""
    return title.title() if title.isupper() else title
