"""Heading stream -> section tree."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from codecite.parse.base import Block
from codecite.profiles.base import Heading, Profile, normalize_number


@dataclass(slots=True)
class Table:
    caption: str  # 'Table 1004.5 Maximum floor area allowances'
    number: str | None  # '1004.5' if captioned, else None
    markdown: str
    page: int | None = None


@dataclass(slots=True)
class Section:
    number: str
    title: str
    depth: int
    ordinal: int
    parent: int | None = None  # index into the flat list
    paragraphs: list[str] = field(default_factory=list)
    tables: list[Table] = field(default_factory=list)
    page_start: int | None = None
    page_end: int | None = None
    supersedes: str | None = None
    path: str = ""
    children: list[int] = field(default_factory=list)

    @property
    def body(self) -> str:
        return "\n\n".join(self.paragraphs)

    @property
    def number_norm(self) -> str:
        return normalize_number(self.number)

    @property
    def label(self) -> str:
        return f"{self.number} {self.title}".strip()


def build_tree(blocks: Iterable[Block], profile: Profile, corpus_title: str = "") -> list[Section]:
    """Stack-based tree build. Returns sections in document order with parent indices set."""
    sections: list[Section] = []
    stack: list[int] = []  # indices of open sections
    pending_caption: Heading | None = None
    last_number_at_depth: dict[tuple[int | None, int], str] = {}
    numbers_seen: dict[str, int] = {}

    def current() -> Section | None:
        return sections[stack[-1]] if stack else None

    def touch_page(sec: Section, page: int | None) -> None:
        if page is None:
            return
        sec.page_start = page if sec.page_start is None else min(sec.page_start, page)
        sec.page_end = page if sec.page_end is None else max(sec.page_end, page)

    for ordinal, block in enumerate(blocks):
        h = profile.match(block, ordinal)
        if h is not None and h.kind == "table-caption":
            pending_caption = h
            continue
        if h is not None:
            # find the parent without mutating the stack yet
            keep = len(stack)
            while keep and sections[stack[keep - 1]].depth >= h.depth:
                keep -= 1
            parent = stack[keep - 1] if keep else None
            if block.kind == "paragraph" and not _monotonic_ok(
                last_number_at_depth, parent, h
            ):
                # inline candidate that goes backwards: treat as body text (table cell / reflow)
                sec = current()
                if sec is not None:
                    sec.paragraphs.append(block.text.strip())
                    touch_page(sec, block.page)
                continue
            del stack[keep:]
            last_number_at_depth[(parent, h.depth)] = h.number
            number = h.number
            if number in numbers_seen:  # same number amended twice in one document: keep both
                numbers_seen[number] += 1
                number = f"{number}({h.alias or numbers_seen[number]})"
            else:
                numbers_seen[number] = 1
            sec = Section(
                number=number,
                title=h.title,
                depth=h.depth,
                ordinal=len(sections),
                parent=parent,
                supersedes=h.supersedes,
            )
            touch_page(sec, block.page)
            if h.remainder:
                sec.paragraphs.append(h.remainder.strip())
            sections.append(sec)
            if parent is not None:
                sections[parent].children.append(sec.ordinal)
            stack.append(sec.ordinal)
            pending_caption = None
            continue

        sec = current()
        if sec is None:
            # preamble before the first heading: attach to a synthetic front-matter section
            sec = Section(number="FRONT", title="Front matter", depth=0, ordinal=0)
            sections.append(sec)
            stack.append(0)
        touch_page(sec, block.page)
        if block.kind == "table":
            cap = pending_caption
            pending_caption = None
            caption = f"Table {cap.number} {cap.title}".strip() if cap else f"Table in {sec.label}"
            tbl = Table(caption=caption, number=cap.number if cap else None, markdown=block.text, page=block.page)
            # attach to the captioned section if it exists, else the enclosing section
            target = sec
            if cap:
                for s in sections:
                    if s.number == cap.number:
                        target = s
                        break
            target.tables.append(tbl)
        else:
            if pending_caption is not None:
                # a caption followed by prose, not a table: keep the caption text as body
                sec.paragraphs.append(f"Table {pending_caption.number} {pending_caption.title}".strip())
                pending_caption = None
            if block.kind == "heading" and not sec.title and not sec.paragraphs and _title_like(block.text):
                # "CHAPTER 10" on one line, "MEANS OF EGRESS" on the next (different font size)
                sec.title = block.text.strip().title() if block.text.strip().isupper() else block.text.strip()
                continue
            sec.paragraphs.append(block.text.strip())

    # materialise breadcrumbs
    for sec in sections:
        parts = []
        cur: Section | None = sec
        while cur is not None:
            parts.append(cur.label)
            cur = sections[cur.parent] if cur.parent is not None else None
        parts.reverse()
        if corpus_title:
            parts.insert(0, corpus_title)
        sec.path = " > ".join(parts)
    return sections


def _title_like(text: str) -> bool:
    """Short, no sentence break inside: a title, not a definition or a body line."""
    t = text.strip().rstrip(".")
    return 0 < len(t) <= 80 and "." not in t and not t.endswith(":")


def _monotonic_ok(seen: dict, parent: int | None, h: Heading) -> bool:
    prev = seen.get((parent, h.depth))
    if prev is None:
        return True
    return normalize_number(h.number) > normalize_number(prev)


def render_tree(sections: list[Section]) -> str:
    lines = []
    for s in sections:
        extras = []
        if s.paragraphs:
            extras.append(f"{len(s.body.split())}w")
        if s.tables:
            extras.append(f"{len(s.tables)}t")
        if s.supersedes:
            extras.append(f"amends {s.supersedes}")
        suffix = f"  [{' '.join(extras)}]" if extras else ""
        lines.append(f"{'  ' * s.depth}{s.label}{suffix}")
    return "\n".join(lines)
