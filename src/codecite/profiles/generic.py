from __future__ import annotations

import re

from codecite.parse.base import Block
from codecite.profiles.base import Heading

NUMBERED = re.compile(r"^(?P<num>\d+(?:\.\d+)*)\.?\s+(?P<title>\S.*?)\s*$")


class GenericProfile:
    """Numbered headings ('3.2.1 Title'), else explicit heading levels with synthetic numbers."""

    name = "generic"
    definitions_title = re.compile(r"\b(definitions?|glossary|terms)\b", re.IGNORECASE)

    def match(self, block: Block, ordinal: int) -> Heading | None:
        if block.kind != "heading":
            return None
        text = block.text.strip()
        m = NUMBERED.match(text)
        if m:
            return Heading(m["num"], m["title"], m["num"].count(".") + 1)
        level = block.level or 1
        return Heading(f"H{level}-{ordinal:04d}", text, level - 1)
