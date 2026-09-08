"""Fetch Ohio Administrative Code rule PDFs from codes.ohio.gov. Never touches any ICC domain.

Site shape (checked 2026-09-07): /ohio-administrative-code/4101:1 lists chapter pages
(/chapter-4101:1-10); each chapter page links its rule PDFs directly
(/assets/laws/administrative-code/rules/4101/1/4101$1-10-04_eff_10_15_25.pdf).
"""

from __future__ import annotations

import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin
from urllib.robotparser import RobotFileParser

import httpx

BASE = "https://codes.ohio.gov"
UA = "codecite/0.1 (+https://github.com/pardesco/codecite; polite fetcher, 1 req/s)"
DELAY = 1.0


def fetch_chapter(division: str, out: Path) -> int:
    if not re.fullmatch(r"4101:\d{1,2}", division):
        raise ValueError("argument must look like 4101:1 (an OAC division)")
    rp = RobotFileParser()
    rp.set_url(f"{BASE}/robots.txt")
    rp.read()
    index_url = f"{BASE}/ohio-administrative-code/{division}"
    if not rp.can_fetch(UA, index_url):
        raise RuntimeError("robots.txt disallows fetching the index; download manually")
    out.mkdir(parents=True, exist_ok=True)
    from selectolax.parser import HTMLParser

    def links(html: str) -> list[str]:
        return [a.attributes.get("href", "") for a in HTMLParser(html).css("a[href]")]

    saved = 0
    with httpx.Client(headers={"User-Agent": UA}, follow_redirects=True, timeout=30) as client:
        html = client.get(index_url).raise_for_status().text
        chapter_re = re.compile(rf"/ohio-administrative-code/chapter-{re.escape(division)}-\d+$")
        chapters = sorted({urljoin(BASE, h) for h in links(html) if chapter_re.search(h)})
        if not chapters:
            raise RuntimeError("no chapter links found; codes.ohio.gov layout may have changed, download manually")
        print(f"[fetch-oac] {len(chapters)} chapters under {division}", file=sys.stderr)
        for url in chapters:
            time.sleep(DELAY)
            page = client.get(url).raise_for_status().text
            pdfs = sorted({urljoin(BASE, h) for h in links(page) if h.lower().endswith(".pdf") and "/rules/" in h})
            for pdf_url in pdfs:
                name = pdf_url.rsplit("/", 1)[-1].replace("$", "_")
                dest = out / name
                if dest.exists() or not rp.can_fetch(UA, pdf_url):
                    continue
                time.sleep(DELAY)
                dest.write_bytes(client.get(pdf_url).raise_for_status().content)
                saved += 1
                print(f"[fetch-oac] {name}", file=sys.stderr)
    return saved
