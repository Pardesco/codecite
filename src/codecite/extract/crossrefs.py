from __future__ import annotations

import re

_REF = re.compile(
    r"\b(?P<kind>Sections?|Tables?|Chapters?)\s+(?P<num>\d{3,4}(?:\.\d+)*|\d{1,2})(?!\d)(?!\.\d)",
)


def find_cross_refs(text: str) -> list[tuple[str, str, str]]:
    """Return unique (ref_text, number, kind) tuples found in the text."""
    seen: set[str] = set()
    out: list[tuple[str, str, str]] = []
    for m in _REF.finditer(text):
        kind = m["kind"].lower().rstrip("s")
        num = m["num"]
        if kind == "chapter" and len(num) > 2:
            continue
        if kind != "chapter" and len(num) < 3:
            continue
        key = f"{kind}:{num}"
        if key in seen:
            continue
        seen.add(key)
        out.append((m.group(0), num, kind))
    return out
