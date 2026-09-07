from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal, Protocol

from codeplumb.parse.base import Block

HeadingKind = Literal["section", "table-caption"]


@dataclass(slots=True)
class Heading:
    number: str
    title: str
    depth: int
    kind: HeadingKind = "section"
    remainder: str = ""  # body text that followed an inline heading (PDF style)
    supersedes: str | None = None
    alias: str | None = None  # disambiguator when the same number recurs (OAC instruction letter)


class Profile(Protocol):
    name: str
    definitions_title: re.Pattern[str]

    def match(self, block: Block, ordinal: int) -> Heading | None:
        """Return a Heading if the block is (or begins with) a section heading."""
        ...


_DIGITS = re.compile(r"\d+")


def normalize_number(number: str) -> str:
    """Zero-pad every digit run so lexical sort == numeric sort: 1004.5.1 -> 1004.0005.0001."""
    return _DIGITS.sub(lambda m: m.group(0).zfill(4), number)


def strip_ref_prefix(text: str) -> str:
    """'Section 1004.5' / '§1004.5' / 'Table 1004.5' -> '1004.5'."""
    t = text.strip()
    t = re.sub(r"^(?:section|sec\.?|table|chapter|§)\s*", "", t, flags=re.IGNORECASE)
    return t.rstrip(".").strip()
