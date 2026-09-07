"""Fetch Ohio Administrative Code rule PDFs from codes.ohio.gov. Never touches any ICC domain."""

from __future__ import annotations

import re
import time
from pathlib import Path
from urllib.parse import urljoin
from urllib.robotparser import RobotFileParser

import httpx

BASE = "https://codes.ohio.gov"
UA = "codeplumb/0.1 (+https://github.com/pardesco/codeplumb; polite fetcher, 1 req/s)"


def fetch_chapter(chapter: str, out: Path) -> int:
    if not re.fullmatch(r"4101:\d{1,2}", chapter):
        raise ValueError("chapter must look like 4101:1")
    rp = RobotFileParser()
    rp.set_url(f"{BASE}/robots.txt")
    rp.read()
    index_url = f"{BASE}/ohio-administrative-code/{chapter}"
    if not rp.can_fetch(UA, index_url):
        raise RuntimeError("robots.txt disallows fetching the chapter index; download manually")
    out.mkdir(parents=True, exist_ok=True)
    with httpx.Client(headers={"User-Agent": UA}, follow_redirects=True, timeout=30) as client:
        html = client.get(index_url).raise_for_status().text
        from selectolax.parser import HTMLParser

        rule_links = []
        for a in HTMLParser(html).css("a[href]"):
            href = a.attributes.get("href", "")
            if re.search(rf"/ohio-administrative-code/rule-{re.escape(chapter)}-\d+-\d+", href):
                rule_links.append(urljoin(BASE, href))
        rule_links = sorted(set(rule_links))
        if not rule_links:
            raise RuntimeError("no rule links found; codes.ohio.gov layout may have changed, download manually")
        saved = 0
        for url in rule_links:
            time.sleep(1.0)
            page = client.get(url).raise_for_status().text
            m = re.search(r'href="([^"]+\.pdf)"', page)
            if not m:
                continue
            pdf_url = urljoin(BASE, m.group(1))
            if not rp.can_fetch(UA, pdf_url):
                continue
            time.sleep(1.0)
            data = client.get(pdf_url).raise_for_status().content
            name = pdf_url.rsplit("/", 1)[-1].replace("$", "_")
            (out / name).write_bytes(data)
            saved += 1
    return saved
