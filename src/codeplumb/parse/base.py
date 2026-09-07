from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

BlockKind = Literal["heading", "paragraph", "table", "list-item"]


@dataclass(slots=True)
class Block:
    kind: BlockKind
    text: str
    page: int | None = None
    level: int | None = None  # explicit heading level (markdown/docx/html), else None
    font_size: float | None = None
    bold: bool = False


def parse_file(path: Path) -> Iterator[Block]:
    suffix = path.suffix.lower()
    if suffix in {".md", ".markdown", ".txt"}:
        from codeplumb.parse.markdown import parse_markdown

        return parse_markdown(path)
    if suffix == ".pdf":
        from codeplumb.parse.pdf import parse_pdf

        return parse_pdf(path)
    if suffix in {".html", ".htm"}:
        from codeplumb.parse.html import parse_html

        return parse_html(path)
    if suffix == ".docx":
        from codeplumb.parse.docx import parse_docx

        return parse_docx(path)
    raise ValueError(f"unsupported file type: {path.suffix}")
