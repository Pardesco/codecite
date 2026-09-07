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

Verified in both clients (2026-09-07):

```
$ claude mcp get codeplumb
codeplumb:
  Scope: User config (available in all your projects)
  Status: ✔ Connected
  Type: stdio
  Command: uv
  Args: run --directory C:/Users/Randall/Documents/codeplumb codeplumb serve

$ codex mcp list
codeplumb  uv  run --directory C:/Users/Randall/Documents/codeplumb codeplumb serve  enabled
```

![demo](docs/demo.gif)

## How retrieval works

- **Chunk by section, not by window.** Each chunk is one section body, prefixed with its breadcrumb (`Model Building Code 2026 > 10 Means Of Egress > 1004 Occupant Load > 1004.5 …`) so the vocabulary the body omits is still embedded. Exceptions, tables, and definitions are separate chunks because that is where the answer usually is.
- **Hybrid.** pgvector HNSW cosine candidates plus Postgres full-text (strict AND pass, then OR pass), fused with Reciprocal Rank Fusion (k = 60), collapsed to sections.
- **Amendment overlay.** A same-numbered section on the `amendment` layer is surfaced directly above its base section and named in `amended_by` and in the citation.
- **One embedding model per database.** `init` records it; mixing models is refused.

## Eval

`uv run codeplumb eval evals/sample-bc.yaml --modes naive,vector,lexical,hybrid --report docs/EVALS.md` runs 64 questions (lookup, paraphrase, exception, table, definition, cross-reference, not-in-corpus) against the synthetic corpus. Results with the default local model (`nomic-embed-text-v1.5`, CPU), 2026-09-07:

| mode | hit@1 | hit@3 | hit@5 | MRR | kind@5 | abstain | false abstain |
|---|---|---|---|---|---|---|---|
| naive (512-token windows, no sections) | 0.275 | 0.442 | 0.442 | 0.353 | 0.000 | 1.000 | 0.033 |
| vector only | 0.817 | 0.950 | 0.983 | 0.888 | 0.957 | 1.000 | 0.017 |
| lexical only | 0.717 | 0.883 | 0.917 | 0.808 | 0.957 | 0.000 | 0.000 |
| **hybrid (default)** | **0.817** | **0.950** | **0.983** | **0.880** | **0.957** | **1.000** | **0.000** |

`hit@k`: the expected section (or a descendant, half credit) is in the top k. `kind@5`: the matched chunk was the expected kind (table, exception, definition). `abstain`: the four not-in-corpus questions were flagged low-confidence; `false abstain`: in-corpus questions wrongly flagged. Full per-tag breakdown in [docs/EVALS.md](docs/EVALS.md). CI runs the same gate with a dependency-free hashed-bag-of-words embedder (hybrid hit@5 0.95).

## Ohio profile

`codeplumb fetch-oac 4101:1` downloads the Ohio Administrative Code rule PDFs (state law, free) from `codes.ohio.gov`, politely (robots.txt, 1 req/s, identifies itself). Ingest them with `--profile oac --layer amendment` over your own licensed IBC 2021 PDF on the `base` layer. The tool never touches any ICC domain.

```bash
uv run codeplumb fetch-oac 4101:1 --out corpus/oac
uv run codeplumb ingest corpus/oac --corpus ohio-bc --layer amendment --profile oac --corpus-title "Ohio Building Code (OAC 4101:1)"
uv run codeplumb ingest /path/to/your/IBC-2021.pdf --corpus ohio-bc --layer base --profile ibc --title "IBC 2021" --version 2021
uv run codeplumb eval evals/ohio-bc.yaml --modes hybrid
```

`evals/ohio-bc.yaml` ships questions and expected rule numbers only; it contains no code text.

Run locally on 2026-09-07 against the 35 OAC 4101:1 rules alone (amendment layer, 291 sections, no IBC base layer indexed), 30 questions, `nomic-embed-text-v1.5`:

| mode | hit@1 | hit@3 | hit@5 | MRR |
|---|---|---|---|---|
| hybrid | 0.679 | 0.893 | 0.893 | 0.749 |
| vector only | 0.696 | 0.929 | 0.929 | 0.796 |
| lexical only | 0.625 | 0.786 | 0.804 | 0.694 |

The misses are mostly one-line "modify exception #1" instructions with almost no text of their own, which a base-layer IBC index would give context to. Report in [docs/EVALS-ohio.md](docs/EVALS-ohio.md).

## Full-pipeline test on a real code: New York City

The IBC itself is sold by ICC, but New York City publishes its own IBC-derived Building Code as free chapter PDFs (2014 edition based on IBC 2009; 2022 edition based on IBC 2015), and city law is a government edict. That makes it the cleanest way to exercise the whole pipeline on genuine ICC-layout PDFs. The chapter files are linked from the [2022 Construction Codes page](https://www.nyc.gov/site/buildings/codes/2022-construction-codes.page) and served from `/assets/buildings/codes-pdf/cons_codes_2022/`.

```bash
uv run codeplumb ingest corpus/nyc2022 --corpus nyc-bc-2022 --layer base --profile ibc --version 2022 --corpus-title "New York City Building Code 2022"
uv run codeplumb eval evals/nyc-bc-2022.yaml --modes hybrid,vector,lexical
```

Indexed 2026-09-07: 33 chapters, about 5,700 sections and 6,600 chunks (400+ tables, 500+ exceptions). Egress golden set (24 questions), `nomic-embed-text-v1.5` on CPU:

| mode | hit@1 | hit@3 | hit@5 | MRR |
|---|---|---|---|---|
| hybrid | 0.705 | 0.977 | 0.977 | 0.803 |
| vector only | 0.818 | 0.886 | 0.886 | 0.841 |
| lexical only | 0.614 | 0.750 | 0.750 | 0.676 |

Known parser limits on these PDFs: NYC prints chapter and section titles as running page headers, which the parser strips, so those two levels of the breadcrumb lose their titles (subsections keep theirs). Report in [docs/EVALS-nyc.md](docs/EVALS-nyc.md).

## Legal posture

Operators index documents they already have the right to use. Nothing indexed leaves the machine unless a remote embedding provider is explicitly enabled. See [docs/LEGAL.md](docs/LEGAL.md) for the cases and the reasoning, [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the design, and [docs/WRITEUP.md](docs/WRITEUP.md) for the short version.

## Layout

```
src/codeplumb/   config · db (migrations, queries) · parse · profiles · tree · chunk · extract · embed · retrieve · evaluate · mcp_server · cli · fetch
samples/         synthetic Model Building Code 2026 (+ local amendments) · Acme design standards (generic profile)
evals/           golden question set
tests/           grammar, tree, chunker, extractors, retrieval (real Postgres), MCP over stdio
```

MIT.
