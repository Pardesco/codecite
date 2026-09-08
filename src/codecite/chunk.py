"""Section -> chunks. Breadcrumb-prefixed, 200-600 token target, 900 hard cap, never mid-sentence."""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

from codecite.extract.crossrefs import find_cross_refs
from codecite.extract.definitions import split_definitions
from codecite.extract.exceptions import split_exceptions
from codecite.profiles.base import Profile
from codecite.tree import Section

TARGET = 600
HARD_CAP = 900

_SENT = re.compile(r"(?<=[.;:])\s+(?=[A-Z0-9(])")


@dataclass(slots=True)
class Chunk:
    kind: str  # body | table | definition | exception
    ordinal: int
    text: str  # breadcrumb + content (what gets embedded)
    content: str
    token_count: int
    page_start: int | None = None
    page_end: int | None = None


@lru_cache(maxsize=1)
def _enc():
    import tiktoken

    return tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    return len(_enc().encode(text))


def chunk_section(sec: Section, profile: Profile) -> tuple[list[Chunk], str, list[tuple[str, str, str]]]:
    """Return (chunks, clean_body, cross_refs). clean_body excludes exception blocks."""
    chunks: list[Chunk] = []
    crumb = sec.path

    body_paras, exceptions = split_exceptions(sec.paragraphs)
    is_defs = bool(profile.definitions_title.search(sec.title or ""))
    if not is_defs and len(body_paras) >= 20:
        # title may be lost (PDF running headers); a body that is mostly TERM. lines is a definitions section
        is_defs = len(split_definitions("\n\n".join(body_paras))) >= 10

    def add(kind: str, content: str) -> None:
        ordinal = sum(1 for c in chunks if c.kind == kind)
        text = f"{crumb}\n\n{content}"
        chunks.append(Chunk(kind, ordinal, text, content, count_tokens(text), sec.page_start, sec.page_end))

    if is_defs and body_paras:
        defs = split_definitions("\n\n".join(body_paras))
        if defs:
            for term, definition in defs:
                add("definition", f"Definition of {term}: {definition}")
            body_paras = []  # definitions replace the body chunk

    for piece in split_to_fit(body_paras, crumb):
        add("body", piece)

    for exc in exceptions:
        add("exception", exc)

    for tbl in sec.tables:
        add("table", f"{tbl.caption}\n\n{tbl.markdown}")

    clean_body = "\n\n".join(body_paras + exceptions) if not is_defs else "\n\n".join(sec.paragraphs)
    refs = find_cross_refs(clean_body + "\n" + "\n".join(t.markdown for t in sec.tables))
    return chunks, clean_body, refs


def split_to_fit(paragraphs: list[str], crumb: str) -> list[str]:
    """Pack paragraphs into pieces under HARD_CAP tokens (crumb included), splitting long ones by sentence."""
    if not paragraphs:
        return []
    budget = HARD_CAP - count_tokens(crumb) - 4
    units: list[str] = []
    for p in paragraphs:
        if count_tokens(p) <= budget:
            units.append(p)
        else:
            cur: list[str] = []
            for s in _SENT.split(p):
                if cur and count_tokens(" ".join(cur + [s])) > budget:
                    units.append(" ".join(cur))
                    cur = []
                cur.append(s)
            if cur:
                units.append(" ".join(cur))
    pieces: list[str] = []
    cur_paras: list[str] = []
    cur_tokens = 0
    for u in units:
        t = count_tokens(u)
        if cur_paras and cur_tokens + t > min(TARGET, budget):
            pieces.append("\n\n".join(cur_paras))
            cur_paras, cur_tokens = [], 0
        cur_paras.append(u)
        cur_tokens += t
    if cur_paras:
        pieces.append("\n\n".join(cur_paras))
    return pieces


def naive_windows(sections: list[Section], window: int = 512) -> list[tuple[int, Chunk]]:
    """Baseline chunker: fixed token windows over the concatenated document, no breadcrumb,
    no section awareness. Each window is credited to the section contributing most of its tokens."""
    enc = _enc()
    tokens: list[int] = []
    owner: list[int] = []
    for si, s in enumerate(sections):
        parts = [s.label, s.body] + [f"{t.caption}\n{t.markdown}" for t in s.tables]
        toks = enc.encode("\n".join(p for p in parts if p) + "\n\n")
        tokens.extend(toks)
        owner.extend([si] * len(toks))
    out: list[tuple[int, Chunk]] = []
    per_section_ordinal: dict[int, int] = {}
    for start in range(0, len(tokens), window):
        piece = tokens[start : start + window]
        owners = owner[start : start + window]
        si = max(set(owners), key=owners.count)
        text = enc.decode(piece).strip()
        if not text:
            continue
        k = per_section_ordinal.get(si, 0)
        per_section_ordinal[si] = k + 1
        out.append((si, Chunk("body", k, text, text, len(piece), sections[si].page_start, sections[si].page_end)))
    return out
