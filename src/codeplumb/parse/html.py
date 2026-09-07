from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from codeplumb.parse.base import Block


def parse_html(path: Path) -> Iterator[Block]:
    from selectolax.parser import HTMLParser

    tree = HTMLParser(path.read_text(encoding="utf-8", errors="replace"))
    for sel in ("nav", "header", "footer", "script", "style"):
        for n in tree.css(sel):
            n.decompose()
    body = tree.body or tree.root
    for node in body.traverse(include_text=False):
        tag = node.tag
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            yield Block("heading", node.text(strip=True), level=int(tag[1]))
        elif tag == "p":
            t = node.text(strip=True)
            if t:
                yield Block("paragraph", t)
        elif tag == "li":
            yield Block("list-item", node.text(strip=True))
        elif tag == "table":
            rows = []
            for i, tr in enumerate(node.css("tr")):
                cells = [c.text(strip=True) for c in tr.css("th,td")]
                rows.append("| " + " | ".join(cells) + " |")
                if i == 0:
                    rows.append("|" + "---|" * len(cells))
            yield Block("table", "\n".join(rows))
