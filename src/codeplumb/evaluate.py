"""Eval harness: golden YAML -> per-mode metrics -> Markdown report."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import psycopg
import yaml

from codeplumb.embed.base import Embedder
from codeplumb.retrieve import search

KS = (1, 3, 5, 10)
MODES = ("naive", "vector", "lexical", "hybrid")


def load_golden(path: Path) -> list[dict]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("golden file must be a list of questions")
    return data


def _hit_credit(expected: list[str], got: list[str]) -> list[float]:
    """Per-rank credit: 1.0 exact, 0.5 if the hit is a descendant of an expected section."""
    credits = []
    for g in got:
        c = 0.0
        for e in expected:
            if g == e:
                c = 1.0
                break
            if g.startswith(e + ".") or e.startswith(g + "."):
                c = max(c, 0.5)
        credits.append(c)
    return credits


def run_eval(conn: psycopg.Connection, embedder: Embedder, golden: list[dict], modes: list[str], k: int = 10) -> dict:
    results: dict[str, dict] = {}
    for mode in modes:
        per_tag: dict[str, list[dict]] = defaultdict(list)
        rows = []
        for item in golden:
            expected = [str(x) for x in item.get("expected_sections", [])]
            if mode == "naive":  # fixed-window baseline lives in '<corpus>__naive', searched with the full hybrid stack
                corpora = [f"{item['corpus']}__naive"] if item.get("corpus") else None
                res = search(conn, embedder, item["question"], corpora=corpora, k=k, mode="hybrid")
            else:
                res = search(conn, embedder, item["question"], corpora=[item["corpus"]] if item.get("corpus") else None, k=k, mode=mode)
            got = [h["section"]["number"] for h in res["hits"]]
            credits = _hit_credit(expected, got)
            rec = {"id": item["id"], "expected": expected, "got": got[:5], "tags": item.get("tags", [])}
            if expected:
                rec["false_abstain"] = 1.0 if res["abstain"] else 0.0
                first = next((i for i, c in enumerate(credits) if c > 0), None)
                rec["mrr"] = (credits[first] / (first + 1)) if first is not None else 0.0
                for kk in KS:
                    rec[f"hit@{kk}"] = max(credits[:kk], default=0.0)
                want_kinds = item.get("expected_kinds")
                if want_kinds:
                    kinds_seen = {c["kind"] for h in res["hits"][:5] for c in h["matched_chunks"]}
                    rec["kind@5"] = 1.0 if kinds_seen & set(want_kinds) else 0.0
            else:  # not-in-corpus question: correct iff abstain
                rec["abstain"] = 1.0 if res["abstain"] else 0.0
                rec["top_similarity"] = res["confidence"]["top_vector_similarity"]
            rows.append(rec)
            for t in rec["tags"] or ["untagged"]:
                per_tag[t].append(rec)
        results[mode] = {"rows": rows, "summary": _summarise(rows), "by_tag": {t: _summarise(r) for t, r in per_tag.items()}}
    return results


def _summarise(rows: list[dict]) -> dict:
    def mean(key: str) -> float | None:
        vals = [r[key] for r in rows if key in r]
        return round(sum(vals) / len(vals), 3) if vals else None

    out = {f"hit@{k}": mean(f"hit@{k}") for k in KS}
    out["mrr"] = mean("mrr")
    out["kind@5"] = mean("kind@5")
    out["abstain"] = mean("abstain")
    out["false_abstain"] = mean("false_abstain")
    out["n"] = len(rows)
    return out


def render_report(results: dict, title: str = "codeplumb eval") -> str:
    cols = ["mode", "n", "hit@1", "hit@3", "hit@5", "hit@10", "mrr", "kind@5", "abstain", "false_abstain"]
    lines = [f"# {title}", "", "| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for mode, r in results.items():
        s = r["summary"]
        lines.append("| " + " | ".join([mode] + [_fmt(s.get(c)) for c in cols[1:]]) + " |")
    for mode, r in results.items():
        lines += ["", f"## {mode} by tag", "", "| tag | n | hit@1 | hit@5 | mrr |", "|---|---|---|---|---|"]
        for tag, s in sorted(r["by_tag"].items()):
            lines.append(f"| {tag} | {s['n']} | {_fmt(s['hit@1'])} | {_fmt(s['hit@5'])} | {_fmt(s['mrr'])} |")
        misses = [row for row in r["rows"] if row.get("hit@5", 1.0) < 1.0 and row["expected"]]
        if misses:
            lines += ["", f"### {mode} misses (hit@5 < 1)", ""]
            for row in misses:
                lines.append(f"- `{row['id']}` expected {row['expected']} got {row['got']}")
    return "\n".join(lines) + "\n"


def _fmt(v) -> str:
    return "-" if v is None else (str(v) if isinstance(v, int) else f"{v:.3f}")
