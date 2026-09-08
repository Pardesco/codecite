# Architecture

codecite is a retrieval system, not an answer engine. The server never calls an LLM; the MCP client (Claude Code, Codex) reasons over quoted, cited section text. That one decision shapes everything below: the pipeline optimises for returning the *governing section* with enough surrounding structure that a model can cite it correctly, and it refuses to guess.

```mermaid
flowchart TB
  subgraph ingest["codecite ingest"]
    A[file] --> B[parse/*<br/>Block stream: heading · paragraph · table · list-item]
    B --> C[profiles/*<br/>ibc · oac · generic<br/>match(block) -> Heading]
    C --> D[tree.build_tree<br/>stack-based; monotonic-number guard;<br/>captions attach tables to their section]
    D --> E[chunk.chunk_section<br/>breadcrumb + body, 200-600 tok target, 900 cap<br/>extract/: exceptions · definitions · crossrefs]
    E --> F[embed/*<br/>local-st (default) · fake (CI) · voyage/openai (opt-in)]
    F --> G[(one transaction:<br/>documents · sections · chunks · cross_refs · ingest_runs)]
  end
  subgraph query["search_code / get_section / get_context"]
    Q[query] --> V[pgvector HNSW<br/>top-40 by cosine]
    Q --> L[FTS: websearch AND pass,<br/>then OR pass; exact §numbers injected]
    V --> R[RRF k=60 over chunk ids]
    L --> R
    R --> S[group to sections<br/>max chunk score; matched kinds]
    S --> O[amendment overlay<br/>same number on 'amendment' layer<br/>sits directly above base]
    O --> H[hits with body, exceptions, tables,<br/>cross-refs, citation, confidence]
  end
  G -.-> V
  G -.-> L
```

## Modules

| Module | Responsibility |
|---|---|
| `parse/` | Turn a file into an ordered `Block` stream. PDF uses PyMuPDF font size/bold for heading candidates, drops repeated running headers, extracts tables as Markdown, and aborts on scanned input. Markdown/HTML/DOCX carry explicit heading levels. |
| `profiles/` | Section-number grammar per code family. `ibc` knows `CHAPTER n`, `SECTION nnnn`, `nnnn.n.n Title`, `TABLE nnnn.n` captions, and the inline PDF form `1004.5 Title. Body…`. `oac` recognises `4101:1-10-04` rule headings and applies the `ibc` sub-grammar inside a rule so an Ohio amendment to `1004.5` is a section numbered `1004.5` with `supersedes_number = 1004.5`. `generic` takes numbered headings or falls back to heading levels with synthetic `H2-0007` numbers. |
| `tree.py` | Heading stream to section tree. Body text is everything under a heading up to the next heading at any depth, so children never duplicate parent text. A candidate whose number goes backwards under the same parent is treated as body text (two-column reflow and table cells produce these). |
| `chunk.py` | Section to chunks. Every chunk embeds `breadcrumb + content`; the breadcrumb carries the vocabulary the body omits. Exceptions, tables, and definitions are separate chunks. Long bodies split at paragraph, then sentence boundaries, never mid-sentence. `naive_windows` is the fixed-512-token baseline used only by the eval; a window is credited to the section that contributes most of its tokens, which is the most generous reading a fixed-window index can get. |
| `embed/` | `Embedder` protocol. Local sentence-transformers (nomic prefixes, CUDA if present) is the default; `fake` is a hashed bag-of-words for CI; remote providers refuse to construct unless explicitly allowed. Vectors are L2-normalised. One model per database, recorded in `embedding_config`. |
| `db/` | Plain SQL. Versioned migrations (`{DIM}` templated from the embedder), `queries.py` for the read side (section lookup, ancestors, siblings, referenced-by, overlay, citation). |
| `retrieve.py` | Hybrid search and the section-level API (`get_section`, `get_context`, `resolve_reference`). |
| `evaluate.py` | Golden YAML to per-mode, per-tag metrics (`hit@k`, MRR, `kind@5`, abstain accuracy, false-abstain rate) and a Markdown report. |
| `mcp_server.py` | The MCP surface. Tools return the same JSON the CLI `--json` prints. Errors are short `ToolError` messages, never stack traces. |
| `cli.py` | `init`, `doctor`, `ingest`, `search`, `section`, `eval`, `serve`, `fetch-oac`, `corpora`, `rm-document`. |

## Why these choices

- **Section chunking beats fixed windows.** The eval ships a `naive` mode that indexes the same documents as 512-token windows with no breadcrumb. On the synthetic corpus it loses to section chunking on every metric; see `docs/EVALS.md`. The windows straddle section boundaries and lose the chapter/section vocabulary that questions actually use.
- **Two lexical passes.** `websearch_to_tsquery` ANDs every term, which is right for "Section 1004.5" and wrong for "how long can a dead-end corridor be". The OR pass (a tiny SQL function, `_codecite_or_query`) gives ranked partial matches; RRF sorts out the rest.
- **Abstain is a heuristic, not a promise.** `abstain` is true when no strict full-text match exists and the nearest vector is below a per-embedder cosine floor. The eval reports both abstain accuracy and the false-abstain rate so the floor can be tuned per model.
- **Amendments overlay, not merge.** v1 pairs a base section with a same-numbered amendment and puts the amendment first with a note. Reconciling "amended to read as follows" edits into one text is v2.
- **No ORM, no framework.** Every SQL statement is visible and parameterised. The schema fits on one screen.

## Data flow guarantees

- Ingest is idempotent by `(corpus, sha256)`; re-ingesting the same file is a no-op without `--force`.
- Each document is written in a single transaction; a failure leaves nothing partial and records the error in `ingest_runs`.
- Source files are referenced by path and hash, never copied into the database or the repository.
- Nothing leaves the machine unless a remote embedding provider is deliberately enabled.
