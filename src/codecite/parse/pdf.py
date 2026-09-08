from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterator
from pathlib import Path

from codecite.parse.base import Block


def parse_pdf(path: Path) -> Iterator[Block]:
    import fitz  # pymupdf

    doc = fitz.open(path)
    pages = []
    text_pages = 0
    for page in doc:
        d = page.get_text("dict")
        lines = []
        for b in d["blocks"]:
            if b.get("type") != 0:
                continue
            for ln in b["lines"]:
                spans = [s for s in ln["spans"] if s["text"].strip()]
                if not spans:
                    continue
                txt = "".join(s["text"] for s in spans).strip()
                size = max(s["size"] for s in spans)
                bold = any("bold" in s["font"].lower() or s["flags"] & 16 for s in spans)
                lines.append((txt, size, bold))
        if lines:
            text_pages += 1
        tables = []
        try:
            for t in page.find_tables():
                md = t.to_markdown().strip()
                if md:
                    tables.append(md)
        except Exception:
            pass
        pages.append((page.number + 1, lines, tables))
    if len(doc) and text_pages < 0.5 * len(doc):
        raise ValueError(
            f"{path.name}: no text layer on more than half the pages (scanned PDF?). "
            "OCR is not supported in v1."
        )

    # running header/footer detection: identical short line on >= 3 pages
    counts = Counter(txt for _, lines, _ in pages for txt, _, _ in lines)
    running = {t for t, c in counts.items() if c >= 3 and len(t) < 80} if len(pages) >= 3 else set()
    body_size = _mode([s for _, lines, _ in pages for _, s, _ in lines]) or 10.0

    for pno, lines, tables in pages:
        para: list[str] = []
        head: Block | None = None  # heading being accumulated (wrapped bold lines)
        for txt, size, bold in lines:
            if txt in running:
                continue
            if size > body_size * 1.15 or bold:
                if para:
                    yield Block("paragraph", " ".join(para), page=pno)
                    para = []
                if head is not None and _continues_heading(head, txt, size, bold):
                    head.text = f"{head.text} {txt}"
                    continue
                if head is not None:
                    yield head
                head = Block("heading", txt, page=pno, font_size=size, bold=bold)
            else:
                if head is not None:
                    yield head
                    head = None
                para.append(txt)
        if head is not None:
            yield head
        if para:
            yield Block("paragraph", " ".join(para), page=pno)
        for md in tables:
            yield Block("table", md, page=pno)


_HEAD_START = re.compile(
    r"^(?:\([A-Z]{1,2}\)|\d{1,4}(?:\.\d+)*\s|TABLE\s|CHAPTER\s|SECTION\s|Exceptions?\s*:"
    r"|[A-Z0-9][A-Z0-9 ,\-/()']{2,60}\.)",  # 'DEAD END.' definition-term lines
    re.IGNORECASE,
)
_STRUCTURAL = re.compile(r"^(?:CHAPTER|SECTION)\s", re.IGNORECASE)


def _continues_heading(head: Block, txt: str, size: float, bold: bool) -> bool:
    """A bold line continues the previous bold line when the first has no terminal punctuation
    and the second does not itself look like the start of a heading."""
    if head.font_size != size or head.bold != bold:
        return False
    if _STRUCTURAL.match(head.text):  # 'SECTION BC 202' never absorbs the next line
        return False
    if head.text.rstrip().endswith((".", ":", ";")):
        return False
    return not _HEAD_START.match(txt)


def _mode(values: list[float]) -> float | None:
    if not values:
        return None
    return Counter(round(v, 1) for v in values).most_common(1)[0][0]
