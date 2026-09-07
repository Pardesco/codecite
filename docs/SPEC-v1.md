# codeplumb — Technical Specification, v1

**Status:** Draft for review · **Date:** 2026-09-03 · **Owner:** Randall (Pardesco)
**Working name:** `codeplumb` (a plumb line for building codes). Placeholder — rename freely before the repo goes public.

---

## 0. One-paragraph summary

`codeplumb` is an open-source, bring-your-own-corpus retrieval system for building codes and internal standards. It ingests documents the operator already has the right to use (a purchased PDF of the 2021 IBC, a premiumACCESS export they are licensed for, the free Ohio Administrative Code rule PDFs, a firm's own design standards), parses them into a section tree, chunks by section, indexes into Postgres + pgvector with hybrid (vector + full-text) search, and exposes the whole thing to Claude Code and Codex through an MCP server whose every answer carries a section-level citation. **The repository ships code, schema, tests, an eval harness, and a synthetic demo corpus. It never ships, fetches, scrapes, or redistributes ICC text.**

---

## 1. Goals, non-goals, success criteria

### 1.1 Goals (v1)

1. **Section-faithful retrieval.** A question like "occupant load factor for business areas" returns the governing section (e.g. Table 1004.5 in IBC-style numbering) with its number, title, breadcrumb, page, and full text, not a floating 500-token blob.
2. **Bring your own corpus.** Any PDF / HTML / DOCX / Markdown the operator points at is indexed locally. Multiple corpora coexist (Ohio Building Code, Ohio Residential Code, "Acme Engineering Standards").
3. **MCP-native.** Claude Code and Codex call it as tools; resources expose sections by URI; a prompt template enforces cite-or-abstain behaviour.
4. **Zero-cost default.** Local embeddings and local reranking on the operator's machine. No API key required to run the demo. Remote embedding providers are opt-in and clearly flagged as sending text off-machine.
5. **Measurable.** A checked-in eval harness with a golden question set reports recall@k and MRR for vector-only, FTS-only, and hybrid, so the README shows numbers rather than adjectives.
6. **Portfolio-grade.** Clean repo, one-command Docker setup, architecture diagram, 90-second demo recording, CI green.

### 1.2 Non-goals (v1)

- No hosted/multi-tenant SaaS, no auth, no billing.
- No answer generation inside the server. The server retrieves; the MCP client (Claude/Codex) reasons. This keeps the server model-agnostic and keeps it out of the "is the AI's legal advice correct" question.
- No OCR of scanned PDFs (text-layer PDFs only). Flag scanned input and stop.
- No scraping of any website that requires a login or forbids automated access. No integration with ICC premiumACCESS in any form.
- No automatic code-compliance judgement ("is this stair compliant?"). Retrieval only.
- No cross-jurisdiction diffing ("what did Ohio change versus base IBC") beyond the basic amendment-overlay tagging in §13.

### 1.3 Success criteria

| Criterion | Target |
|---|---|
| `docker compose up` + `codeplumb ingest samples/` + `codeplumb serve` works on a fresh clone | < 10 minutes, no API key |
| Hybrid section-hit recall@5 on the shipped synthetic golden set | ≥ 0.90 |
| Hybrid section-hit recall@5 on a private Ohio set (run locally, numbers only in README) | ≥ 0.80 |
| Claude Code and Codex both list the tools and answer a cited question | verified with screenshots |
| Test suite | ≥ 80% line coverage on parser, chunker, retrieval |
| No ICC-copyrighted text anywhere in the repo, fixtures, or goldens | enforced by a CI grep for known IBC sentences + manual review |

---

## 2. Legal and licensing posture

This section exists because it is the reason the architecture is shaped the way it is. It is written to be lifted into `docs/LEGAL.md` with the sources in Appendix C.

### 2.1 The legal landscape (as of 2026-09-03; verify before publishing)

**The strongest precedent for open access is already law in one circuit.** In *Veeck v. Southern Building Code Congress International* (5th Cir. 2002, en banc), the Fifth Circuit held that once a model code is enacted into law by a government body, the enacted text enters the public domain. The reasoning: the citizen bound by a law is, through the democratic process, its practical author, and a private organisation cannot hold exclusive rights over text people are legally required to obey. The court traced this to the 1834 Supreme Court holding (*Wheaton v. Peters*) that judicial opinions cannot be copyrighted, and extended the logic to statutes. *Veeck* binds Texas, Louisiana, and Mississippi.

**It does not bind Ohio.** Ohio sits in the Sixth Circuit, which has not ruled the same way, and other circuits have split on the related "standards incorporated by reference" question. That split is why *ICC v. UpCodes* was not dismissed outright and instead proceeded, and why the Pro Codes Act (H.R. 4072) is in Congress: the courts have not closed the question, so the standards organisations are trying to close it legislatively. The Pro Codes Act would confirm that a standards developer keeps copyright in a code incorporated by reference provided it offers a free read-only copy.

**Recent direction favours access but is not final.** *Georgia v. Public.Resource.Org* (S. Ct. 2020) held that government edicts, including annotations authored under state authority, are not copyrightable. On 2026-04-07 the Third Circuit in *ASTM v. UpCodes* affirmed denial of a preliminary injunction, holding that UpCodes' verbatim, free republication of standards incorporated into law is *likely* fair use; that UpCodes is a commercial company did not change the outcome because it did not charge for the codes. A preliminary-injunction ruling on likelihood of fair use is not a merits judgment, and it is one circuit.

**ICC's position is a funding argument, not a rent argument.** ICC says code development, testing, and expert revision cost real money; selling access funds that work; and without that revenue either government absorbs the cost or the process becomes more exposed to whichever industry lobby can pay to shape it. Critics (UpCodes, Public.Resource.Org, a fair number of legal scholars) reply that this is a real funding problem attached to the wrong solution: charging people to read a law they are bound by is a bad trade regardless of where the money goes, and "free to view but you cannot copy, paste, or print" mostly protects the business model rather than public access. Both positions are fair to state in LEGAL.md; the project does not need to pick a side to be safe.

**Ohio specifics.** Ohio's building code is Ohio Administrative Code Chapter 4101:1. Rule 4101:1-1-01 incorporates the 2021 International Building Code, Chapters 2–35 and Appendix H, by reference, and 4101:1-34-01 incorporates the 2021 IEBC. Ohio's *amendments* are published as OAC rule text on the state's site and are a government edict. The *unamended IBC body text* is not on the state site; ICC publishes it. ICC premiumACCESS free tier is view-only, with copy, paste, and print disabled by its terms; automating around that is a breach of contract regardless of how the copyright question resolves.

### 2.2 Posture chosen

The project is designed so that it is clean under *every* outcome above, including the one least favourable to open access:

1. **The repo is code, not content.** Pipeline, schema, MCP server, tests, eval harness, and an original synthetic corpus written for this project.
2. **The operator supplies the corpus.** They index files they lawfully possess. The tool does no network fetching of code text by default. The single "fetch" helper (§13) targets only `codes.ohio.gov` OAC rule PDFs, which are state law published by the state.
3. **Nothing indexed ever leaves the operator's machine** unless they explicitly select a remote embedding provider, and then only chunk text goes to that provider under their own account.
4. **Golden eval sets ship question text and expected section numbers only.** Section numbers are facts; no code sentences appear in the repo.
5. **No premiumACCESS interaction of any kind.** No scraper, no browser automation, no "export helper".
6. **README disclaimer:** "This tool indexes documents you provide. You are responsible for holding the rights to index them. Nothing here is legal advice or a substitute for the adopted code and the authority having jurisdiction."

Framed for the portfolio: the design does not depend on winning the *Veeck* argument in the Sixth Circuit. It would be equally lawful if the Pro Codes Act passed tomorrow, because the operator's own licensed copy, indexed privately, is exactly the use the Act contemplates.

---

## 3. Users and scenarios

**U1 — Solo architect / engineer with a purchased IBC PDF.** Drops the PDF and the OAC amendment PDFs into a folder, runs ingest, asks Claude Code "what's the minimum corridor width for an I-2 occupancy under the Ohio code?" and gets a cited answer with the Ohio amendment flagged if one exists.

**U2 — Firm with an internal standards library.** Indexes "Acme Structural Standards v7" (DOCX) as its own corpus alongside the code. Asks Codex "does our standard require a stricter deflection limit than the code section?" The two corpora are searched together, each hit labelled.

**U3 — Hiring manager reading the repo.** Wants to see: sensible schema, real chunking logic (not a `splitlines()`), hybrid search done properly, an MCP server that follows the spec, evals with numbers, and a clean legal story. This user never runs the code.

---

## 4. System overview

```mermaid
flowchart LR
    subgraph Operator machine
        A[Source files<br/>PDF · HTML · DOCX · MD] --> B[Parser plugins]
        B --> C[Section tree<br/>+ tables + definitions]
        C --> D[Chunker<br/>by section]
        D --> E[Embedder<br/>local default]
        E --> F[(Postgres 17<br/>pgvector + tsvector)]
        F --> G[Retriever<br/>hybrid + RRF<br/>optional rerank]
        G --> H[MCP server<br/>stdio / HTTP]
    end
    H <--> I[Claude Code]
    H <--> J[Codex CLI]
    K[CLI: init · ingest · search · eval · serve] --> B
    K --> G
```

Two processes: a **CLI** for ingestion and evaluation (batch, writes to the DB) and an **MCP server** for retrieval (long-running, read-only by default). Both import the same `codeplumb` package.

---

## 5. Tech stack

| Layer | Choice | Why |
|---|---|---|
| Language | Python 3.12, `uv` for env/lock | RAG tooling and PDF parsing are strongest in Python; `uv` gives fast reproducible installs |
| MCP | Official `mcp` Python SDK v2 (its bundled FastMCP server class) | Hiring managers recognise the official SDK; avoids a second framework's version drift. Verify import path against the installed version at M0 |
| Database | Postgres 17 + pgvector ≥ 0.8, via Docker Compose | Single store for vectors, full-text, and relational section tree; HNSW index; nothing exotic to explain |
| DB access | `psycopg` 3 (async) + plain SQL in versioned migration files | Keeps the schema visible in the repo; no ORM magic to defend |
| Migrations | Hand-rolled `migrations/NNN_*.sql` runner (or `yoyo-migrations`) | Small surface; readable |
| PDF parsing | `pymupdf` (fitz) | Fast, gives font size / bold / bbox, which section-heading detection needs |
| HTML parsing | `selectolax` | Fast, small |
| DOCX | `python-docx` | Adequate for headings + paragraphs + tables |
| Embeddings (default) | `sentence-transformers` + `nomic-ai/nomic-embed-text-v1.5` (768-d, Apache-2.0, 8k context, Matryoshka) | Free, runs on CPU or the RTX 5070 Ti; uses `search_document:` / `search_query:` prefixes, a detail worth showing |
| Embeddings (opt-in) | Voyage `voyage-law-2` (1024-d, legal-tuned), OpenAI `text-embedding-3-small` | Provider interface proves pluggability; Voyage is the legal-domain option |
| Reranker (opt-in, v1.1) | `BAAI/bge-reranker-v2-m3` local cross-encoder | Measurable lift on ambiguous queries; local |
| Tokenizer for chunk sizing | `tiktoken` `cl100k_base` as a length proxy | Model-independent, deterministic |
| CLI | `typer` | Standard |
| Config | `pydantic-settings`, `.env` | Standard |
| Tests | `pytest`, `pytest-asyncio`, `testcontainers` for a throwaway Postgres | Real-DB tests for retrieval |
| Lint/format | `ruff` | Standard |
| CI | GitHub Actions: ruff, pytest with Postgres service, eval-on-synthetic with threshold gate | Numbers in CI, not just in the README |

Decision: Python over TypeScript. The parsing and embedding ecosystem is decisively Python; the MCP SDKs are equivalent.

---

## 6. Data model

### 6.1 Concepts

- **Corpus** — a named body of text with one jurisdiction/owner label, e.g. `ohio-bc-2024`, `acme-standards`. Search can target one, several, or all.
- **Document** — one source file inside a corpus, with a `layer`: `base` (e.g. IBC 2021 PDF) or `amendment` (e.g. OAC 4101:1 rule PDF). Version string and SHA-256 recorded.
- **Section** — a node in the document's heading tree. Has a canonical `number` (`1004.5.1`, `4101:1-10-04`, or a synthetic `H3-0007` for unnumbered headings), `title`, `depth`, `parent`, `path` (materialised breadcrumb), `page_start`/`page_end`, and `body` (the text directly under the heading, excluding children).
- **Chunk** — the embedding unit. Normally one section body; long sections split at paragraph / exception boundaries. Carries the breadcrumb prefix that was embedded with it.
- **Table** — extracted as Markdown, attached to a section, chunked separately with `kind = 'table'`.
- **Definition** — a defined term from a definitions chapter, one chunk each, `kind = 'definition'`.
- **CrossRef** — a textual reference from one section to another ("see Section 1010.1.1"), resolved to a section id where possible.

### 6.2 Schema (Postgres)

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE corpora (
  id            text PRIMARY KEY,                -- 'ohio-bc-2024'
  title         text NOT NULL,
  jurisdiction  text,                            -- 'US-OH'
  profile       text NOT NULL,                   -- 'ibc' | 'oac' | 'generic'
  created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE documents (
  id            bigserial PRIMARY KEY,
  corpus_id     text NOT NULL REFERENCES corpora(id) ON DELETE CASCADE,
  title         text NOT NULL,
  layer         text NOT NULL CHECK (layer IN ('base','amendment')),
  version       text,                            -- '2021', 'eff 2025-10-15'
  source_path   text NOT NULL,                   -- local path as given (not copied)
  sha256        text NOT NULL,
  page_count    int,
  ingested_at   timestamptz NOT NULL DEFAULT now(),
  UNIQUE (corpus_id, sha256)
);

CREATE TABLE sections (
  id            bigserial PRIMARY KEY,
  document_id   bigint NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  corpus_id     text NOT NULL REFERENCES corpora(id) ON DELETE CASCADE,
  parent_id     bigint REFERENCES sections(id) ON DELETE CASCADE,
  number        text NOT NULL,                   -- '1004.5.1'
  number_norm   text NOT NULL,                   -- '1004.0005.0001' for sorting
  title         text,
  depth         int NOT NULL,
  path          text NOT NULL,                   -- 'Ch10 > 1004 > 1004.5 > 1004.5.1'
  body          text NOT NULL DEFAULT '',
  page_start    int,
  page_end      int,
  ordinal       int NOT NULL,                    -- document order
  supersedes_number text,                        -- amendment layer: base section it replaces
  UNIQUE (document_id, number)
);
CREATE INDEX sections_corpus_number ON sections (corpus_id, number);
CREATE INDEX sections_parent ON sections (parent_id);

CREATE TABLE chunks (
  id            bigserial PRIMARY KEY,
  section_id    bigint NOT NULL REFERENCES sections(id) ON DELETE CASCADE,
  corpus_id     text NOT NULL REFERENCES corpora(id) ON DELETE CASCADE,
  kind          text NOT NULL CHECK (kind IN ('body','table','definition','exception')),
  ordinal       int NOT NULL,                    -- position within section
  text          text NOT NULL,                   -- what was embedded (breadcrumb + content)
  content       text NOT NULL,                   -- content only, for display
  token_count   int NOT NULL,
  page_start    int,
  page_end      int,
  embedding     vector(768) NOT NULL,            -- dim fixed per install; see §7.4
  tsv           tsvector GENERATED ALWAYS AS (to_tsvector('english', text)) STORED,
  UNIQUE (section_id, kind, ordinal)
);
CREATE INDEX chunks_embedding_hnsw ON chunks
  USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 128);
CREATE INDEX chunks_tsv_gin ON chunks USING gin (tsv);
CREATE INDEX chunks_corpus ON chunks (corpus_id);

CREATE TABLE cross_refs (
  id              bigserial PRIMARY KEY,
  from_section_id bigint NOT NULL REFERENCES sections(id) ON DELETE CASCADE,
  ref_text        text NOT NULL,                 -- 'Section 1010.1.1'
  ref_number      text NOT NULL,                 -- '1010.1.1'
  ref_kind        text NOT NULL,                 -- 'section' | 'table' | 'chapter'
  to_section_id   bigint REFERENCES sections(id) ON DELETE SET NULL
);
CREATE INDEX cross_refs_from ON cross_refs (from_section_id);
CREATE INDEX cross_refs_to ON cross_refs (to_section_id);

CREATE TABLE embedding_config (
  singleton     bool PRIMARY KEY DEFAULT true CHECK (singleton),
  provider      text NOT NULL,                   -- 'local-st' | 'voyage' | 'openai'
  model         text NOT NULL,
  dimensions    int NOT NULL,
  query_prefix  text NOT NULL DEFAULT '',
  doc_prefix    text NOT NULL DEFAULT ''
);

CREATE TABLE ingest_runs (
  id            bigserial PRIMARY KEY,
  document_id   bigint REFERENCES documents(id) ON DELETE SET NULL,
  started_at    timestamptz NOT NULL DEFAULT now(),
  finished_at   timestamptz,
  status        text NOT NULL,                   -- 'running' | 'ok' | 'failed'
  stats         jsonb,                           -- sections, chunks, tables, unresolved refs
  error         text
);
```

Notes:
- One embedding model per database. `embedding_config` is written at `codeplumb init` and the migration templates the `vector(N)` dimension from it. Mixing models in one column is a silent-quality bug; refusing is the right v1 behaviour.
- `path` is a display breadcrumb. Tree walks use `parent_id`; no ltree extension needed at this scale (a full IBC is roughly 5–6k sections).
- Source files are referenced by path and hash, never copied into the DB or repo.

---

## 7. Ingestion pipeline

`codeplumb ingest <path-or-dir> --corpus <id> --layer base|amendment [--profile ibc|oac|generic] [--title ...] [--version ...]`

### 7.1 Stages

1. **Detect & hash.** File type by extension + magic bytes; SHA-256; skip if `(corpus, sha256)` exists unless `--force`.
2. **Extract blocks.** Parser plugin yields an ordered stream of `Block(kind, text, page, font_size, bold, bbox)` where kind ∈ {heading-candidate, paragraph, table, list-item, footnote-candidate}.
   - PDF: PyMuPDF `get_text("dict")` per page; join lines within a block; detect running headers/footers by repetition across pages and drop them; detect tables with `page.find_tables()` and emit as Markdown.
   - HTML: heading tags `h1–h6` + `<table>`; strip nav/boilerplate by a per-profile selector list.
   - DOCX: paragraph styles `Heading N` + tables.
   - Markdown: ATX headings + pipe tables.
   - Scanned PDF (no text layer on > 50% of pages): abort with a clear message. OCR is v2.
3. **Section grammar (profile).** Turns heading candidates into a tree. Profiles are small classes with a `match(block) -> (number, title) | None` and a `depth(number)` rule.
   - `ibc`: `^(?P<num>\d{3,4}(?:\.\d+)*)\s+(?P<title>[A-Z][^.]{2,120})\.?\s` at line start, plus `^CHAPTER\s+(\d+)\s+(.+)$` and `^SECTION\s+(\d{3,4})\s+(.+)$`. Depth = number of dot-separated parts (chapter = 0, `1004` = 1, `1004.5` = 2, …). Also recognises `TABLE 1004.5 ...` captions and `Exception(s):` blocks.
   - `oac`: `^(?P<num>4101:\d-\d{1,2}-\d{2})\s+(?P<title>.+)$` for rule headings; inside a rule body, IBC-style numbers appear again and are parsed with the `ibc` sub-grammar so an Ohio amendment to `1004.5` produces a section with `number = '1004.5'` and `supersedes_number = '1004.5'` on the amendment layer.
   - `generic`: numbered headings `^\d+(\.\d+)*\s+\S`, Markdown/DOCX heading levels, or, failing both, font-size clustering (largest = depth 0, etc.). Unnumbered headings get synthetic numbers `H{depth}-{ordinal:04d}`.
   - Heading validation guards: a candidate must be followed by body text or a child heading; numbers must be monotonic within a parent (with tolerance for one out-of-order jump to survive PDF column reflow); a candidate that appears in a table cell is rejected.
4. **Build tree.** Stack-based: pop until parent depth < candidate depth. Body text is everything between a heading and the next heading at any depth. Page ranges from first/last block.
5. **Special extraction.**
   - **Exceptions.** A paragraph starting `Exception:` or `Exceptions:` and its following numbered items become an `exception` chunk attached to the same section. Exceptions are where the answer usually is, and burying them inside a 900-token body hurts recall.
   - **Tables.** Markdown table + caption → `table` chunk. Caption number (`TABLE 1004.5`) is linked to section `1004.5` if it exists, else to the enclosing section.
   - **Definitions.** If a section title matches `DEFINITIONS` (profile-configurable), split its body on `^[A-Z][A-Z0-9 ,\-/()]{2,60}\.\s` term boundaries into one `definition` chunk per term with `text = "Definition of TERM: ..."`.
   - **Cross-references.** Regex over body: `(Section|Table|Chapter)\s+(\d{3,4}(?:\.\d+)*|\d{1,2})`. Resolve within the same corpus: prefer amendment layer, then base. Unresolved refs are kept with `to_section_id NULL` and counted in `ingest_runs.stats`.
6. **Chunk.** Rules in §7.2.
7. **Embed.** Batched; provider from `embedding_config`; document prefix prepended per provider.
8. **Write.** Single transaction per document. On failure nothing partial remains.

### 7.2 Chunking rules

- Chunk unit is the **section body** (text under a heading, not including children). Children are their own sections.
- Every chunk's embedded `text` = `breadcrumb + "\n\n" + content`, where breadcrumb = `"{corpus title} > Chapter 10 Means of Egress > 1004 Occupant Load > 1004.5 Areas without fixed seating"`. The breadcrumb carries the vocabulary the body omits (a body about "net floor area" never says "occupant load"); it also makes lexical search hit on chapter names.
- Target 200–600 tokens; hard cap 900 tokens.
- If a body exceeds the cap: split at paragraph boundaries, then at sentence boundaries, never mid-sentence. No character overlap; every piece repeats the breadcrumb. Pieces get `ordinal` 0..n.
- A section with an empty body (pure container like `SECTION 1004`) gets no `body` chunk; it still exists as a section for tree navigation and for `get_section` expansion.
- Exceptions, tables, and definitions are separate chunks as described above, in addition to the body chunk.

### 7.3 Idempotency and versioning

- Re-ingesting the same file (same hash) is a no-op. `--force` deletes and re-creates that document's sections and chunks in one transaction.
- A new version of a document (different hash) is a new `documents` row; the operator removes the old one with `codeplumb rm-document <id>` or keeps both and filters by version. No automatic "latest" logic in v1.

### 7.4 Embedding provider interface

```python
class Embedder(Protocol):
    name: str            # 'local-st:nomic-ai/nomic-embed-text-v1.5'
    dimensions: int
    doc_prefix: str      # 'search_document: '
    query_prefix: str    # 'search_query: '
    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...
```

Providers: `LocalSentenceTransformers` (default, device auto: CUDA if available), `VoyageEmbedder`, `OpenAIEmbedder`. Remote providers refuse to construct unless `CODEPLUMB_ALLOW_REMOTE_EMBEDDINGS=1` is set, and log once at startup that chunk text will be sent to the provider. Vectors are L2-normalised before storage so cosine and inner product agree.

---

## 8. Retrieval

`search(query, corpora=None, k=8, filters={chapter?, kinds?, layer?}) -> list[SectionHit]`

### 8.1 Pipeline

1. **Query normalisation.** Trim; detect an explicit section reference (`1004.5`, `Table 1004.5`, `4101:1-10-04`) and, if present, short-circuit to `get_section` semantics with the lexical/vector search still run for neighbours.
2. **Vector candidates.** `embed_query(query)`; `SELECT … ORDER BY embedding <=> $1 LIMIT 40` with `SET LOCAL hnsw.ef_search = 100`, filtered by corpus/kind/layer.
3. **Lexical candidates.** `websearch_to_tsquery('english', $1)` against `tsv`, ranked by `ts_rank_cd`, LIMIT 40. Section numbers in the query are also matched exactly against `sections.number` and injected as top lexical hits.
4. **Fusion.** Reciprocal Rank Fusion, `k = 60`, over chunk ids.
5. **Section grouping.** Collapse chunks to their section; section score = max fused chunk score; keep which chunk kinds hit (body / exception / table / definition).
6. **Amendment overlay.** If a hit section on the `base` layer has a same-number section on an `amendment` layer in the same corpus, attach it as `amended_by` and boost the amendment to sit directly above the base hit.
7. **Optional rerank (v1.1).** Cross-encoder over top 20 sections using `breadcrumb + body` as the passage; final order by reranker score.
8. **Return top k sections** with full body, the hit chunks, breadcrumb, pages, cross-refs out, and score components.

### 8.2 Response shape (also the MCP tool result)

```json
{
  "query": "occupant load factor business areas",
  "hits": [
    {
      "corpus": "ohio-bc-2024",
      "document": {"title": "IBC 2021 (operator copy)", "layer": "base", "version": "2021"},
      "section": {"number": "1004.5", "title": "Areas without fixed seating",
                  "path": "Ch 10 Means of Egress > 1004 Occupant Load > 1004.5",
                  "pages": [235, 236]},
      "content": "…full section body from the operator's own indexed copy…",
      "matched_chunks": [{"kind": "table", "ordinal": 0, "excerpt": "…"}],
      "amended_by": {"corpus": "ohio-bc-2024", "document": "OAC 4101:1-10-04 eff 2025-10-15",
                     "section_number": "1004.5", "note": "Ohio amendment present; read it first"},
      "cross_refs": ["1004.5.1", "Table 1004.5"],
      "scores": {"rrf": 0.0312, "vector_rank": 1, "lexical_rank": 3, "rerank": null},
      "citation": "IBC 2021 §1004.5 (p. 235), as amended by OAC 4101:1-10-04"
    }
  ],
  "provenance": {"embedding_model": "nomic-ai/nomic-embed-text-v1.5", "retrieval": "hybrid-rrf", "reranked": false}
}
```

`citation` is a ready-to-paste string so the client does not have to assemble one.

---

## 9. MCP server

`codeplumb serve [--transport stdio|http] [--host 127.0.0.1 --port 8765] [--corpora a,b]`

Built on the official `mcp` Python SDK. Stdio is the default (what Claude Code and Codex spawn). Streamable HTTP is provided for a shared instance on a LAN; it binds to localhost unless overridden and has no auth in v1, which the README states plainly.

### 9.1 Tools

| Tool | Input | Output | Notes |
|---|---|---|---|
| `search_code` | `query: str`, `corpora?: list[str]`, `k?: int (1–20, default 8)`, `chapter?: str`, `kinds?: list[str]`, `layer?: str` | §8.2 JSON | The workhorse |
| `get_section` | `number: str`, `corpus?: str`, `include_children?: bool`, `include_tables?: bool = true` | Section with body, children (titles + numbers, bodies if requested), tables, exceptions, cross-refs, amendment overlay | Exact lookup; number normalisation handles `1004.5`, `Section 1004.5`, `§1004.5` |
| `get_context` | `number: str`, `corpus?: str` | Parent chain to chapter, previous/next siblings, referenced-by sections | For "what surrounds this" questions |
| `resolve_reference` | `text: str` | List of `{ref_text, number, kind, corpus, found: bool}` | Parses free text for references and says which exist |
| `list_corpora` | — | Corpora with document titles, layers, versions, section/chunk counts, embedding model | Lets the client tell the user what is actually indexed |
| `list_chapters` | `corpus: str` | Chapter numbers + titles | Table of contents |
| `ingest_document` *(disabled unless `CODEPLUMB_ENABLE_INGEST_TOOL=1`)* | `path: str`, `corpus: str`, `layer: str`, `profile?: str` | `ingest_runs` row | Path must be under `CODEPLUMB_INGEST_ROOT`. Off by default because it writes and because it is slow |

Tool descriptions are written for the model, not for humans: each says when to use it, what it returns, and that the result text is quoted from the operator's indexed document and must be cited by section number.

### 9.2 Resources

- `codeplumb://{corpus}/toc` — chapters and sections as an outline (text/markdown).
- `codeplumb://{corpus}/section/{number}` — the section rendered as Markdown with breadcrumb, body, exceptions, tables.
- `codeplumb://{corpus}/document/{id}` — document metadata.

Resource templates let a client pull a section into context by URI after a search.

### 9.3 Prompts

- `code_question(question, corpus?)` — system-style prompt: search first; quote only from tool results; cite `§number` for every claim; if the corpus does not cover it, say so; never infer a requirement that is not in the returned text; mention amendments when `amended_by` is present.
- `compare_to_standard(question, code_corpus, standards_corpus)` — search both, present code requirement and internal standard side by side with citations, flag which is stricter, do not decide compliance.

### 9.4 Error model

Tool errors are returned as MCP tool results with `isError: true` and a short, actionable message (`corpus 'x' not found; available: …`, `section '1004.9' not found in ohio-bc-2024; nearest: 1004.8, 1005`). No stack traces to the model.

### 9.5 Client configuration

Claude Code:

```bash
claude mcp add codeplumb -- uv run --directory C:/Users/Randall/Documents/codeplumb codeplumb serve
```

Codex (`~/.codex/config.toml`; Codex uses TOML, not JSON, and `codex mcp add` is the CLI equivalent):

```toml
[mcp_servers.codeplumb]
command = "uv"
args = ["run", "--directory", "C:/Users/Randall/Documents/codeplumb", "codeplumb", "serve"]
env = { CODEPLUMB_DATABASE_URL = "postgresql://codeplumb:codeplumb@127.0.0.1:5432/codeplumb" }
```

Both snippets go in the README with a screenshot of `/mcp` (Claude Code) and `codex mcp list` showing the tools.

### 9.6 Safety and injection

Indexed text is data, never instructions. The server does no LLM calls, so there is nothing to inject into server-side. The `code_question` prompt tells the client model to treat tool output as quoted material. Ingest tool is off by default and path-restricted when on. Every SQL statement is parameterised. No telemetry, no outbound calls except the operator-chosen embedding provider.

---

## 10. CLI

```
codeplumb init                      # create DB schema, write embedding_config, download local model
codeplumb ingest PATH --corpus ID --layer base|amendment [--profile] [--title] [--version] [--force]
codeplumb ingest PATH --dry-run --show-tree   # print the parsed section tree, write nothing
codeplumb rm-document ID
codeplumb corpora                   # list
codeplumb search "query" [--corpus] [--k] [--json]
codeplumb section 1004.5 [--corpus]
codeplumb eval GOLDEN.yaml [--modes naive,vector,lexical,hybrid,hybrid+rerank] [--report out.md]
codeplumb serve [--transport] [--port]
codeplumb fetch-oac 4101:1 --out ./corpus/oac   # downloads OAC rule PDFs from codes.ohio.gov (state law); see §13
codeplumb doctor                    # DB reachable, extension version, model cached, GPU visible
```

---

## 11. Synthetic demo corpus

`samples/sample-building-code/` — an original, fictional "Model Building Code, 2026 Edition" written for this project. Roughly 12 chapters, 150 sections, IBC-style numbering, a definitions chapter, 8 tables, 20 exceptions, 40 cross-references, and one "Local Amendments" document on the `amendment` layer that overrides six sections. Content is plausible but invented (invented occupancy names, invented numbers). Purpose: every test, every CI eval, and the demo GIF run on this corpus, so the repo is complete without any third-party text. Author it with Claude, then review every section by hand for accidental verbatim IBC phrasing before commit.

A second sample, `samples/acme-standards/` (about 30 sections, DOCX + Markdown), exercises the `generic` profile and the multi-corpus scenario.

---

## 12. Evaluation harness

### 12.1 Golden set format

```yaml
- id: q001
  question: "What is the occupant load factor for business areas?"
  corpus: sample-bc-2026
  expected_sections: ["1004.5"]        # any-of; ancestor match counts at half credit
  expected_kinds: ["table"]            # optional
  tags: [egress, table]
- id: q002
  question: "Are there exceptions to the corridor width requirement in Group I-2?"
  expected_sections: ["1020.2"]
  expected_kinds: ["exception"]
```

Shipped: `evals/sample-bc.yaml` (at least 60 questions across lookup, paraphrase, exception, table, definition, cross-reference, and "not in corpus" categories). Optional local: `evals/ohio-bc.yaml` with questions and expected section numbers only; the operator runs it against their own indexed copy.

### 12.2 Metrics

- **section-hit@k** (k = 1, 3, 5, 10): expected section or descendant appears in top k.
- **MRR** over sections.
- **kind-hit@5**: the matched chunk kind is one of `expected_kinds` when given.
- **abstain accuracy**: for "not in corpus" questions, top-1 RRF score below threshold.
- Reported per mode: `naive` (fixed 512-token windows, no section awareness, as the baseline to beat), `vector`, `lexical`, `hybrid`, `hybrid+rerank`; and per tag.

### 12.3 CI gate

`codeplumb eval evals/sample-bc.yaml --modes hybrid --fail-under section-hit@5=0.90` runs in GitHub Actions against a Postgres service container with the local embedder on CPU. The Markdown report is uploaded as an artifact and the headline table is pasted into the README on each release.

---

## 13. Ohio profile

What the operator can assemble for a real Ohio Building Code corpus:

| Piece | Source | Rights | How it enters codeplumb |
|---|---|---|---|
| Ohio amendments (OAC 4101:1 rule text) | `codes.ohio.gov` rule PDFs, e.g. `4101$1-3-01_eff_10_15_25.pdf` | State law; free | `codeplumb fetch-oac 4101:1` then `ingest --layer amendment --profile oac` |
| 2021 IBC body (Ch 2–35, App H), incorporated by reference | Operator's purchased PDF or licensed export | Operator's licence | `ingest --layer base --profile ibc` |
| 2021 IEBC (for 4101:1-34-01) | same | same | same |
| Ohio Residential Code (OAC 4101:8 + IRC 2021) | same pattern | same | second corpus `ohio-rc-2024` |

The `fetch-oac` helper reads the chapter index page on `codes.ohio.gov`, follows the per-rule PDF links, respects `robots.txt`, rate-limits to one request per second, and saves files locally. It never touches any ICC domain. If Ohio's site layout changes, the helper fails loudly and tells the operator to download manually.

Verify before release: current effective dates of OAC 4101:1 rules (search results show rules effective 2024-03-01 with amendments effective 2025-10-15) and the exact incorporation-by-reference wording in 4101:1-1-01.

Amendment overlay in v1 is **tagging plus adjacency**: an amendment section with the same number as a base section is surfaced next to it and named in `amended_by`. Deciding which text controls is left to the reader in v1. Merging base text with "amended to read as follows" edits into a single reconciled section is v2.

---

## 14. Security, privacy, cost

- Default configuration makes **zero outbound network calls** after `init` downloads the local model (and `fetch-oac`, which is explicit).
- Corpus text is stored only in the operator's Postgres. Database URL from env. Docker Compose binds Postgres to localhost.
- Remote embedding providers gated by an env flag with a startup warning.
- MCP HTTP transport: localhost by default, no auth, documented as LAN-only. Stdio is the recommended transport.
- Ingest tool off by default; when on, path allow-list.
- Cost: $0 to run the demo end to end. Optional Voyage/OpenAI embedding of a full IBC (roughly 1.5M tokens) is cents to a couple of dollars, once.

---

## 15. Repository layout

```
codeplumb/
  README.md                    # pitch, 3-command quickstart, architecture diagram, eval table, legal note
  LICENSE                      # MIT
  pyproject.toml               # uv-managed; console script `codeplumb`
  docker-compose.yml           # postgres:17 + pgvector
  .env.example
  docs/
    SPEC-v1.md                 # this file
    ARCHITECTURE.md            # narrative + diagram
    LEGAL.md                   # §2 expanded, with sources
    EVALS.md                   # latest report
  src/codeplumb/
    config.py
    db/ (migrations/*.sql, pool.py, queries.py)
    parse/ (base.py, pdf.py, html.py, docx.py, markdown.py)
    profiles/ (ibc.py, oac.py, generic.py)
    tree.py                    # heading stream -> section tree
    chunk.py
    extract/ (exceptions.py, tables.py, definitions.py, crossrefs.py)
    embed/ (base.py, local_st.py, voyage.py, openai.py)
    retrieve.py                # hybrid + RRF + overlay (+ rerank)
    mcp_server.py
    cli.py
    fetch/oac.py
  samples/
    sample-building-code/      # synthetic corpus (PDF generated from Markdown source + the Markdown)
    acme-standards/
  evals/
    sample-bc.yaml
    ohio-bc.yaml               # questions + section numbers only
  tests/
    test_profiles.py           # regex/grammar tables
    test_tree.py               # tree building, reflow tolerance
    test_chunk.py              # size rules, breadcrumb, exceptions
    test_extract.py
    test_retrieve.py           # testcontainers Postgres, RRF math, overlay
    test_mcp.py                # spawn server over stdio, list tools, call each
  .github/workflows/ci.yml
```

---

## 16. Milestones

| M | Deliverable | Definition of done |
|---|---|---|
| M0 | Scaffold | `uv sync`, `docker compose up`, `codeplumb init`, `codeplumb doctor` green; CI runs ruff + empty pytest |
| M1 | Parse + tree + chunk | Synthetic corpus PDF and Markdown both produce identical section trees; unit tests for all three profiles; `ingest` writes sections/chunks with dummy zero vectors |
| M2 | Embed + retrieve | Local embedder wired; hybrid search; `codeplumb search` returns cited hits; eval harness runs `naive`/`vector`/`lexical`/`hybrid` on the synthetic set; numbers committed to `docs/EVALS.md` |
| M3 | MCP server | All tools/resources/prompts; stdio verified in Claude Code and Codex; `test_mcp.py` passes; screenshots in README |
| M4 | Ohio profile + overlay | `fetch-oac`, `oac` profile, amendment tagging; private eval on real Ohio corpus run locally, headline numbers in README |
| M5 | Portfolio polish | Architecture doc, LEGAL.md with sources, 90-second demo GIF, release v1.0.0 tag, short write-up post |
| v1.1 | Rerank | `bge-reranker-v2-m3` behind a flag; eval delta reported |

Rough effort at Randall's cadence: M0–M3 is one focused week; M4–M5 a second.

---

## 17. Risks and open decisions

**Risks**

- **PDF heading detection on real ICC PDFs.** Two-column layout, running headers, and tables that contain section-number-like strings will produce false headings. Mitigations: font-size/bold features, monotonic-number guard, table-cell exclusion, and the `--dry-run --show-tree` mode so the operator can eyeball the tree before committing. Budget real time here; it is the hardest part.
- **Amendment semantics.** "Amended to read as follows" vs "add the following exception" vs "delete" are different operations. v1 tags only; README says so.
- **Embedding dimension lock-in.** Changing models means re-init and re-ingest. Acceptable in v1; document it.
- **Legal drift.** Keep LEGAL.md dated and sourced; do not state conclusions stronger than the sources. In particular, do not describe *Veeck* as national law or the Third Circuit ruling as a final merits decision.
- **Scope creep toward an answer engine.** The moment the server calls an LLM, it inherits the accuracy-of-legal-advice problem and a provider dependency. Keep it retrieval-only.

**Decisions for Randall**

1. Project name (working: `codeplumb`).
2. Confirm Python over TypeScript.
3. Default local model: `nomic-embed-text-v1.5` (768-d, prefixes) vs `bge-m3` (1024-d, multilingual). Recommendation: nomic; smaller index, and the prefix convention is a good talking point.
4. Ship the Ohio golden set (questions + section numbers) or keep it private. Recommendation: ship it; numbers are facts, and it shows the tool was tested against a real code.
5. Whether the demo GIF shows the synthetic corpus only (fully safe) or a real Ohio query with the section text blurred. Recommendation: synthetic corpus in the GIF; real-corpus eval numbers in a table.

---

## 18. Portfolio packaging

- **README above the fold:** one sentence, the mermaid diagram, three commands, the eval table, two screenshots (Claude Code and Codex answering with a citation), then the legal note. Positioning language matches the "Design Engineer + AI" framing: plain words, no jargon beyond "hybrid search" and "MCP".
- **Demo recording:** under 60 seconds. Ask Claude Code a question, watch the tool call, see the cited answer, open the section resource. Speed up ingest.
- **Write-up (about 800 words):** why bring-your-own-corpus, why section chunking beats fixed windows (show the eval delta between the `naive` mode and section chunking), and what an MCP server actually needs to expose to be useful to a coding agent.
- **Talking points for interviews:** breadcrumb-in-embedding, exceptions-as-chunks, RRF, amendment overlay, refusing to mix embedding models, the eval gate in CI, and the legal design choice (safe under *Veeck*, safe under the Pro Codes Act, safe under either UpCodes outcome).

---

## Appendix A — Section-number grammar test table (profile `ibc`)

| Input line | Parsed | Depth |
|---|---|---|
| `CHAPTER 10 MEANS OF EGRESS` | chapter 10, "Means of Egress" | 0 |
| `SECTION 1004 OCCUPANT LOAD` | 1004, "Occupant Load" | 1 |
| `1004.5 Areas without fixed seating. The number of…` | 1004.5, "Areas without fixed seating" | 2 |
| `1004.5.1 Increased occupant load. The occupant…` | 1004.5.1, "Increased occupant load" | 3 |
| `TABLE 1004.5 MAXIMUM FLOOR AREA…` | table caption for 1004.5 | — |
| `Exception: …` | exception block | — |
| `See Section 1010.1.1 for…` (in body) | cross-ref → 1010.1.1 | — |
| `1004.5 psi` (in a table cell) | rejected (table context) | — |

## Appendix B — Sample MCP interaction

Claude Code user: *"Under the sample code, what's the max travel distance in a sprinklered B occupancy, and are there exceptions?"*

1. Client calls `search_code({"query": "exit access travel distance sprinklered Group B", "corpora": ["sample-bc-2026"]})`.
2. Server returns §1017.2 with the table chunk and one `exception` chunk, plus `cross_refs: ["1017.3"]`.
3. Client calls `get_section({"number": "1017.3"})` for the referenced section.
4. Client answers with two citations and quotes the exception verbatim from the tool result.

## Appendix C — Sources for §2 and §13 (checked 2026-09-03)

- *Veeck v. Southern Building Code Congress Int'l*, 293 F.3d 791 (5th Cir. 2002) (en banc) — enacted model code enters the public domain. Cite the reporter; confirm pin cites before publishing LEGAL.md.
- *Wheaton v. Peters*, 33 U.S. 591 (1834) — no copyright in judicial opinions; the lineage *Veeck* relies on.
- *Georgia v. Public.Resource.Org*, 590 U.S. ___ (2020) — government edicts doctrine.
- *ASTM v. UpCodes*, 3d Cir. 2026-04-07 (No. 24-2965): https://law.justia.com/cases/federal/appellate-courts/ca3/24-2965/24-2965-2026-04-07.html
- EFF summary of the Third Circuit ruling: https://www.eff.org/deeplinks/2026/04/another-court-rules-copyright-cant-stop-people-reading-and-speaking-law
- Law360 on the Pro Codes Act context: https://www.law360.com/articles/2469911/building-codes-ruling-may-inform-ai-copyright-arguments
- Construction Dive background on *ICC v. UpCodes*: https://www.constructiondive.com/news/icc-v-upcodes-can-a-private-organization-copyright-the-law/558723/
- Ohio Administrative Code 4101:1 index: https://codes.ohio.gov/ohio-administrative-code/4101:1
- OAC 4101:1-1-01 (incorporation by reference of IBC 2021 Ch 2–35, App H): https://codes.ohio.gov/assets/laws/administrative-code/rules/4101/1/4101$1-1-01_eff_3_1_24.pdf
- OAC 4101:1-34-01 (IEBC 2021): https://codes.ohio.gov/assets/laws/administrative-code/rules/4101/1/4101$1-34-01_eff_10_15_25.pdf
- MCP Python SDK: https://github.com/modelcontextprotocol/python-sdk
- Codex CLI MCP config (TOML, `codex mcp add`): https://codex.danielvaughan.com/2026/05/19/codex-cli-mcp-server-management-cli-commands-oauth-streamable-http-production-patterns/
