from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

from codeplumb.parse.base import Block

_ATX = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_PIPE = re.compile(r"^\s*\|.*\|\s*$")
_LIST = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")


def parse_markdown(path: Path) -> Iterator[Block]:
    return iter(parse_markdown_text(path.read_text(encoding="utf-8")))


def parse_markdown_text(text: str) -> list[Block]:
    blocks: list[Block] = []
    para: list[str] = []
    table: list[str] = []

    def flush_para() -> None:
        if para:
            blocks.append(Block("paragraph", " ".join(s.strip() for s in para)))
            para.clear()

    def flush_table() -> None:
        if table:
            blocks.append(Block("table", "\n".join(table)))
            table.clear()

    for raw in text.splitlines():
        line = raw.rstrip()
        if _PIPE.match(line):
            flush_para()
            table.append(line.strip())
            continue
        flush_table()
        m = _ATX.match(line)
        if m:
            flush_para()
            blocks.append(Block("heading", m.group(2).strip(), level=len(m.group(1))))
            continue
        if not line.strip():
            flush_para()
            continue
        if _LIST.match(line):
            flush_para()
            blocks.append(Block("list-item", line.strip()))
            continue
        para.append(line)
    flush_para()
    flush_table()
    return blocks
