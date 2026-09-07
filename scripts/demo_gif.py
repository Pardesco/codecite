"""Render a short terminal-style demo GIF from real CLI output. Run: uv run python scripts/demo_gif.py

Frames are drawn with Pillow (no browser, no terminal recorder), so the result is deterministic
and reproducible in CI. Keep it under 60 seconds.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "demo.gif"
W, H = 960, 560
PAD = 18
LINE_H = 20
MAX_LINES = (H - 2 * PAD) // LINE_H
BG, FG, DIM, ACCENT, PROMPT = (17, 19, 24), (222, 226, 230), (130, 138, 150), (255, 196, 96), (120, 220, 160)

STEPS = [  # (command, hold ms, max output lines)
    ("codeplumb corpora", 900, 8),
    ('codeplumb search "how long can a dead-end corridor be in a sprinklered office?" --corpus sample-bc-2026 --k 3', 2600, 40),
    ('codeplumb search "occupant load factor for business areas" --corpus sample-bc-2026 --k 2', 2600, 40),
    ('codeplumb search "temporary door locking devices in schools" --corpus ohio-bc --k 2', 2600, 40),
    ("claude mcp get codeplumb", 2200, 9),
]


def run(cmd: str) -> str:
    argv = cmd.split(" ", 1)
    if argv[0] == "codeplumb":
        full = [sys.executable, "-m", "codeplumb.cli"] + _split(argv[1] if len(argv) > 1 else "")
    else:
        full = _split(cmd)
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
    p = subprocess.run(full, capture_output=True, text=True, cwd=ROOT, shell=(argv[0] != "codeplumb"), encoding="utf-8", errors="replace", env=env)
    out = (p.stdout or "") + (p.stderr if p.returncode else "")
    return re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", out).rstrip()


def _split(s: str) -> list[str]:
    import shlex

    return shlex.split(s, posix=True)


def font(size: int = 15):
    for name in ("consola.ttf", "DejaVuSansMono.ttf", "Menlo.ttc", "cour.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def wrap(line: str, width: int = 104) -> list[str]:
    return [line[i : i + width] for i in range(0, max(len(line), 1), width)]


def render(lines: list[tuple[str, tuple[int, int, int]]], cursor: bool) -> Image.Image:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    f = font()
    d.rectangle([0, 0, W, 34], fill=(28, 31, 38))
    for i, c in enumerate(((255, 95, 86), (255, 189, 46), (39, 201, 63))):
        d.ellipse([14 + i * 22, 11, 26 + i * 22, 23], fill=c)
    d.text((W // 2 - 60, 9), "codeplumb demo", fill=DIM, font=f)
    y = 44
    for text, color in lines[-(MAX_LINES - 2) :]:
        d.text((PAD, y), text, fill=color, font=f)
        y += LINE_H
    if cursor:
        d.rectangle([PAD, y, PAD + 9, y + 16], fill=FG)
    return img


def main() -> None:
    frames: list[Image.Image] = []
    durations: list[int] = []
    shown: list[tuple[str, tuple[int, int, int]]] = [("$ docker compose up -d && uv run codeplumb init   # done earlier", DIM), ("", FG)]

    def add(img: Image.Image, ms: int) -> None:
        frames.append(img.quantize(colors=64, method=Image.Quantize.MEDIANCUT))
        durations.append(ms)

    add(render(shown, True), 600)
    for cmd, hold, max_lines in STEPS:
        typed = ""
        for ch in cmd:
            typed += ch
            add(render(shown + [("$ " + typed, PROMPT)], True), 28 if ch != " " else 60)
        shown.append(("$ " + cmd, PROMPT))
        add(render(shown, False), 350)
        out_lines = run(cmd).splitlines()
        if len(out_lines) > max_lines:
            out_lines = out_lines[:max_lines] + ["   ..."]
        for raw in out_lines:
            for piece in wrap(raw):
                color = ACCENT if re.match(r"^\s*\d+\. §|^\s*\d+\. .*rrf=", piece) else (DIM if piece.startswith("   ") else FG)
                shown.append((piece, color))
                add(render(shown, False), 45)
        shown.append(("", FG))
        add(render(shown, True), hold)
    add(render(shown + [("# every hit carries a section number, a breadcrumb, and a citation.", ACCENT)], True), 2500)
    frames[0].save(OUT, save_all=True, append_images=frames[1:], duration=durations, loop=0, optimize=True)
    print(f"wrote {OUT} ({len(frames)} frames, {sum(durations)/1000:.1f}s, {OUT.stat().st_size/1e6:.1f} MB)")


if __name__ == "__main__":
    main()
