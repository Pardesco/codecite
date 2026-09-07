from __future__ import annotations

import json
from pathlib import Path

import typer

from codeplumb.config import get_settings

app = typer.Typer(help="codeplumb: bring-your-own-corpus building-code retrieval + MCP server", no_args_is_help=True)


def _embedder():
    from codeplumb.db.pool import connect
    from codeplumb.embed import get_embedder

    s = get_settings()
    conn = connect(s.database_url)
    with conn.cursor() as cur:
        cur.execute("SELECT provider, model, dimensions FROM embedding_config")
        cfg = cur.fetchone()
    if not cfg:
        typer.echo("database not initialised; run `codeplumb init`", err=True)
        raise typer.Exit(2)
    emb = get_embedder(s, provider=cfg["provider"], model=cfg["model"])
    if emb.dimensions != cfg["dimensions"]:
        typer.echo(
            f"embedding model {emb.name} has {emb.dimensions} dims but the database was initialised "
            f"with {cfg['dimensions']}; refusing to mix models. Re-run `codeplumb init --reset`.",
            err=True,
        )
        raise typer.Exit(2)
    return conn, emb


@app.command()
def init(reset: bool = typer.Option(False, help="drop everything and re-create")):
    """Create the schema, record the embedding model, and warm the local model cache."""
    from codeplumb.db.pool import apply_migrations, connect, drop_all
    from codeplumb.embed import get_embedder

    s = get_settings()
    conn = connect(s.database_url)
    if reset:
        drop_all(conn)
    emb = get_embedder(s)
    applied = apply_migrations(conn, emb.dimensions)
    with conn.cursor() as cur:
        cur.execute("SELECT provider, model, dimensions FROM embedding_config")
        cfg = cur.fetchone()
        if cfg and (cfg["provider"], cfg["model"]) != (emb.provider, emb.model):
            typer.echo(
                f"database already initialised with {cfg['provider']}:{cfg['model']} ({cfg['dimensions']}d); "
                f"config asks for {emb.name}. Use --reset to switch (re-ingest required).",
                err=True,
            )
            raise typer.Exit(2)
        if not cfg:
            cur.execute(
                "INSERT INTO embedding_config (provider, model, dimensions, query_prefix, doc_prefix) VALUES (%s,%s,%s,%s,%s)",
                (emb.provider, emb.model, emb.dimensions, emb.query_prefix, emb.doc_prefix),
            )
    conn.commit()
    typer.echo(f"ok: migrations applied {applied or '(none new)'}; embedding = {emb.name} ({emb.dimensions}d)")


@app.command()
def doctor():
    """Check DB, pgvector, embedding config, model cache, GPU."""
    from codeplumb.db.pool import connect

    s = get_settings()
    ok = True
    try:
        conn = connect(s.database_url)
        with conn.cursor() as cur:
            cur.execute("SELECT version()")
            typer.echo(f"db: ok ({cur.fetchone()['version'].split(',')[0]})")
            cur.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
            r = cur.fetchone()
            typer.echo(f"pgvector: {r['extversion'] if r else 'MISSING (run init)'}")
            ok &= bool(r)
            cur.execute("SELECT to_regclass('embedding_config') IS NOT NULL AS t")
            if cur.fetchone()["t"]:
                cur.execute("SELECT provider, model, dimensions FROM embedding_config")
                cfg = cur.fetchone()
                typer.echo(f"embedding_config: {cfg['provider']}:{cfg['model']} ({cfg['dimensions']}d)" if cfg else "embedding_config: empty (run init)")
            else:
                typer.echo("schema: not initialised (run init)")
                ok = False
    except Exception as e:
        typer.echo(f"db: FAIL {e}")
        ok = False
    if s.embed_provider == "local-st":
        try:
            import torch

            typer.echo(f"torch: {torch.__version__}, cuda={'yes ' + torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'no'}")
        except ImportError:
            typer.echo("torch: not installed (uv sync --extra local)")
            ok = False
    typer.echo("doctor: " + ("all good" if ok else "problems found"))
    raise typer.Exit(0 if ok else 1)


@app.command()
def ingest(
    path: Path,
    corpus: str | None = typer.Option(None, "--corpus", help="required unless --dry-run"),
    layer: str = typer.Option("base", "--layer"),
    profile: str = typer.Option("ibc", "--profile"),
    title: str | None = typer.Option(None, "--title"),
    version: str | None = typer.Option(None, "--version"),
    corpus_title: str | None = typer.Option(None, "--corpus-title"),
    force: bool = typer.Option(False, "--force"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    show_tree: bool = typer.Option(False, "--show-tree"),
    naive: bool = typer.Option(False, "--naive", help="also build the fixed-window baseline corpus '<corpus>__naive' for eval"),
):
    """Index a file or directory into a corpus."""
    from codeplumb.ingest import AlreadyIngested, dry_run_tree, ingest_document

    files = sorted(p for p in ([path] if path.is_file() else path.rglob("*")) if p.suffix.lower() in {".pdf", ".md", ".markdown", ".txt", ".html", ".htm", ".docx"})
    if not files:
        typer.echo(f"no supported files under {path}", err=True)
        raise typer.Exit(1)
    if dry_run:
        for f in files:
            typer.echo(f"== {f}")
            typer.echo(dry_run_tree(f, profile, layer) if show_tree else "(parsed ok)")
        return
    if not corpus:
        typer.echo("--corpus is required", err=True)
        raise typer.Exit(2)
    conn, emb = _embedder()
    for f in files:
        try:
            stats = ingest_document(conn, f, corpus, layer, profile, emb, title=title if len(files) == 1 else None, version=version, corpus_title=corpus_title, force=force)
            typer.echo(f"{f.name}: {json.dumps(stats)}")
            if naive:
                nstats = ingest_document(conn, f, f"{corpus}__naive", layer, profile, emb, title=title if len(files) == 1 else None, version=version, corpus_title=f"{corpus_title or corpus} (naive baseline)", force=force, naive=True)
                typer.echo(f"{f.name} [naive]: {json.dumps(nstats)}")
        except AlreadyIngested as e:
            typer.echo(f"skip: {e}")


@app.command("rm-document")
def rm_document(document_id: int):
    from codeplumb.db.pool import connect

    conn = connect()
    with conn.cursor() as cur:
        cur.execute("DELETE FROM documents WHERE id = %s RETURNING title", (document_id,))
        r = cur.fetchone()
    conn.commit()
    typer.echo(f"deleted {r['title']}" if r else "no such document")


@app.command()
def corpora():
    from codeplumb.db import queries
    from codeplumb.db.pool import connect

    for c in queries.list_corpora(connect()):
        typer.echo(f"{c['id']}: {c['title']} [{c['profile']}] sections={c['sections']} chunks={c['chunks']}")
        for d in c["documents"]:
            typer.echo(f"  #{d['id']} {d['layer']}: {d['title']} {d['version'] or ''}")


@app.command()
def search(
    query: str,
    corpus: list[str] | None = typer.Option(None, "--corpus"),
    k: int = typer.Option(8, "--k"),
    mode: str = typer.Option("hybrid", "--mode"),
    as_json: bool = typer.Option(False, "--json"),
):
    from codeplumb.retrieve import search as _search

    conn, emb = _embedder()
    res = _search(conn, emb, query, corpora=corpus or None, k=k, mode=mode)
    if as_json:
        typer.echo(json.dumps(res, indent=2, default=str))
        return
    for i, h in enumerate(res["hits"], 1):
        kinds = ",".join(sorted({c["kind"] for c in h["matched_chunks"]})) or ("overlay" if h["scores"].get("overlay") else "")
        typer.echo(f"{i}. §{h['section']['number']} {h['section']['title']}  [{kinds}] rrf={h['scores']['rrf']}")
        typer.echo(f"   {h['citation']}")
        typer.echo(f"   {h['content'][:200].replace(chr(10), ' ')}")
    if res["abstain"]:
        typer.echo("(low confidence: the corpus may not cover this)")


@app.command()
def section(number: str, corpus: str | None = typer.Option(None, "--corpus"), children: bool = typer.Option(False, "--children")):
    from codeplumb.db.pool import connect
    from codeplumb.retrieve import get_section

    typer.echo(json.dumps(get_section(connect(), number, corpus, include_children=children), indent=2, default=str))


@app.command("eval")
def eval_cmd(
    golden: Path,
    modes: str = typer.Option("hybrid", "--modes"),
    report: Path | None = typer.Option(None, "--report"),
    fail_under: str | None = typer.Option(None, "--fail-under", help="e.g. hit@5=0.90 (checked on the first mode)"),
):
    from codeplumb.evaluate import load_golden, render_report, run_eval

    conn, emb = _embedder()
    mode_list = [m.strip() for m in modes.split(",") if m.strip()]
    results = run_eval(conn, emb, load_golden(golden), mode_list)
    md = render_report(results, f"codeplumb eval: {golden.name} ({emb.name})")
    if report:
        report.write_text(md, encoding="utf-8")
    typer.echo(md)
    if fail_under:
        metric, thr = fail_under.split("=")
        metric = metric.replace("section-", "")
        val = results[mode_list[0]]["summary"].get(metric) or 0.0
        if val < float(thr):
            typer.echo(f"FAIL: {metric}={val} < {thr}", err=True)
            raise typer.Exit(1)


@app.command()
def serve(transport: str = typer.Option("stdio", "--transport"), host: str = typer.Option("127.0.0.1", "--host"), port: int = typer.Option(8765, "--port")):
    """Run the MCP server (stdio by default)."""
    from codeplumb.mcp_server import run

    run(transport, host, port)


@app.command("fetch-oac")
def fetch_oac(chapter: str = typer.Argument("4101:1"), out: Path = typer.Option(Path("./corpus/oac"), "--out")):
    """Download Ohio Administrative Code rule PDFs (state law, free) from codes.ohio.gov."""
    from codeplumb.fetch.oac import fetch_chapter

    n = fetch_chapter(chapter, out)
    typer.echo(f"saved {n} rule PDFs to {out}")


if __name__ == "__main__":
    app()
