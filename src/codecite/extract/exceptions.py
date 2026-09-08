from __future__ import annotations

import re

_EXC = re.compile(r"^\s*Exceptions?\s*:", re.IGNORECASE)
_ITEM = re.compile(r"^\s*(?:\d+[.)]|[-*•])\s+")


def split_exceptions(paragraphs: list[str]) -> tuple[list[str], list[str]]:
    """Pull 'Exception:' / 'Exceptions:' paragraphs (plus their numbered items) out of the body.

    Returns (remaining_body_paragraphs, exception_blocks).
    """
    body: list[str] = []
    exceptions: list[str] = []
    cur: list[str] | None = None
    for p in paragraphs:
        if _EXC.match(p):
            if cur:
                exceptions.append("\n".join(cur))
            cur = [p.strip()]
        elif cur is not None and (_ITEM.match(p) or not cur[-1].rstrip().endswith((".", ";", ":"))):
            cur.append(p.strip())
        else:
            if cur:
                exceptions.append("\n".join(cur))
                cur = None
            body.append(p)
    if cur:
        exceptions.append("\n".join(cur))
    return body, exceptions
