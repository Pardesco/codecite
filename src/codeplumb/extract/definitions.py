from __future__ import annotations

import re

# 'OCCUPANT LOAD. The number of persons ...'  or  '**Occupant load.** The number ...'
# PDF extraction may drop the space after the period ("EGRESS.A continuous ..."), so \s* with a capital lookahead
_TERM = re.compile(r"(?:(?<=\n)|^)\s*\**(?P<term>[A-Z][A-Z0-9 ,\-/()']{2,60}?)\**\.\s*(?=[A-Z(\"“])", re.MULTILINE)


def split_definitions(body: str) -> list[tuple[str, str]]:
    """Split a definitions-chapter body into (TERM, definition) pairs."""
    matches = list(_TERM.finditer(body))
    if len(matches) < 2:
        return []
    out: list[tuple[str, str]] = []
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        definition = body[m.end() : end].strip()
        if definition:
            out.append((m["term"].strip(), definition))
    return out
