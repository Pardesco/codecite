# codeplumb

Bring-your-own-corpus retrieval for building codes: section-faithful chunking, hybrid search in Postgres, and an MCP server so Claude Code or Codex can answer with `§1004.5`-style citations from **your** licensed copy of a code. The repo ships code, schema, tests, an eval harness, and an original synthetic code. It never ships, fetches, or redistributes ICC text.

```mermaid
flowchart LR
  A[PDF / HTML / DOCX / MD] --> B[parse blocks]
  B --> C[profile grammar<br/>ibc · oac · generic]
  C --> D[section tree]
  D --> E[chunks<br/>body · exception · table · definition]
  E --> F[(Postgres 17<br/>pgvector + FTS)]
  F --> G[hybrid search<br/>RRF + amendment overlay]
  G --> H[MCP server<br/>stdio / http]
  H --> I[Claude Code · Codex]
```

## Quickstart (no API key)

```bash
docker compose up -d
uv sync --extra local                 # local nomic-embed-text-v1.5; or set CODEPLUMB_EMBED_PROVIDER=fake for CI-style runs
uv run codeplumb init
uv run codeplumb ingest samples/sample-building-code/model-building-code-2026.md --corpus sample-bc-2026 --layer base --title "Model Building Code" --version 2026 --corpus-title "Model Building Code 2026"
uv run codeplumb ingest samples/sample-building-code/local-amendments-2026.md --corpus sample-bc-2026 --layer amendment --title "Local Amendments" --version 2026
uv run codeplumb search "occupant load factor for business areas"
```

Then wire it into a client:

```bash
claude mcp add codeplumb -- uv run --directory /path/to/codeplumb codeplumb serve
```

```toml
# ~/.codex/config.toml
[mcp_servers.codeplumb]
command = "uv"
args = ["run", "--directory", "/path/to/codeplumb", "codeplumb", "serve"]
env = { CODEPLUMB_DATABASE_URL = "postgresql://codeplumb:codeplumb@127.0.0.1:5432/codeplumb" }
```

## What the MCP server exposes

| Tool | Use |
|---|---|
| `search_code` | hybrid search; returns governing sections with full text, matched chunk kinds, amendment overlay, cross-refs, and a ready-to-paste citation |
| `get_section` | exact lookup (`1004.5`, `Section 1004.5`, `§1004.5`) with exceptions, tables, definitions, children |
| `get_context` | parent chain, siblings, children, referenced-by |
| `resolve_reference` | which section/table/chapter references in a piece of text actually exist |
| `list_corpora`, `list_chapters` | what is indexed |
| `ingest_document` | off unless `CODEPLUMB_ENABLE_INGEST_TOOL=1`; path-restricted |

Resources: `codeplumb://{corpus}/toc`, `codeplumb://{corpus}/section/{number}`, `codeplumb://{corpus}/document/{id}`.
Prompts: `code_question`, `compare_to_standard` (cite-or-abstain rules baked in).

## How retrieval works

- **Chunk by section, not by window.** Each chunk is one section body, prefixed with its breadcrumb (`Model Building Code 2026 > 10 Means Of Egress > 1004 Occupant Load > 1004.5 …`) so the vocabulary the body omits is still embedded. Exceptions, tables, and definitions are separate chunks because that is where the answer usually is.
- **Hybrid.** pgvector HNSW cosine candidates plus Postgres full-text (strict AND pass, then OR pass), fused with Reciprocal Rank Fusion (k = 60), collapsed to sections.
- **Amendment overlay.** A same-numbered section on the `amendment` layer is surfaced directly above its base section and named in `amended_by` and in the citation.
- **One embedding model per database.** `init` records it; mixing models is refused.

## Eval

`uv run codeplumb eval evals/sample-bc.yaml --modes hybrid,vector,lexical --report docs/EVALS.md` runs 64 questions (lookup, paraphrase, exception, table, definition, cross-reference, not-in-corpus) against the synthetic corpus. See [docs/EVALS.md](docs/EVALS.md) for the latest numbers. CI runs it with the dependency-free hashed-bag-of-words embedder and gates on `hit@5`; the local `nomic-embed-text-v1.5` model scores higher.

## Ohio profile

`codeplumb fetch-oac 4101:1` downloads the Ohio Administrative Code rule PDFs (state law, free) from `codes.ohio.gov`, politely (robots.txt, 1 req/s). Ingest them with `--profile oac --layer amendment` over your own licensed IBC 2021 PDF on the `base` layer. The tool never touches any ICC domain.

## Legal posture

Operators index documents they already have the right to use. Nothing indexed leaves the machine unless a remote embedding provider is explicitly enabled. See `docs/SPEC-v1.md` §2 for the reasoning and sources.

## Layout

```
src/codeplumb/   config · db (migrations, queries) · parse · profiles · tree · chunk · extract · embed · retrieve · evaluate · mcp_server · cli · fetch
samples/         synthetic Model Building Code 2026 (+ local amendments) · Acme design standards (generic profile)
evals/           golden question set
tests/           grammar, tree, chunker, extractors, retrieval (real Postgres), MCP over stdio
```

MIT.
