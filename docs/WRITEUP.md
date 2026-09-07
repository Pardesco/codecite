# Why a building-code RAG should bring its own corpus

*A short write-up to accompany the codeplumb repository.*

I built codeplumb to answer a narrow question well: when a coding agent is asked "what does the code require here?", can it come back with the governing section, quoted and cited, from a copy of the code the user actually owns? The answer is yes, and the interesting parts are three design choices that each moved a metric.

## Bring your own corpus

Building codes sit in a legal grey zone. Model codes are written by a private organisation, adopted into law by governments, and then sold back to the people bound by them. Whether the adopted text is copyrightable depends on the federal circuit you are in, and the question is live in court and in Congress right now. A project that scraped, cached, or redistributed code text would inherit that whole fight.

codeplumb sidesteps it by being code, not content. The repository ships a pipeline, a schema, an MCP server, tests, and a synthetic "Model Building Code" written for the project. The user points it at the PDF they bought, or at their firm's own design standards, and everything is indexed locally. Nothing leaves the machine unless a remote embedding provider is deliberately enabled. The one network helper downloads Ohio's own amendment rules from the state's website, which are state law and free. This posture is safe under every outcome of the current litigation, because the user is always indexing their own licensed copy. See `docs/LEGAL.md` for the cases.

## Chunk by section, not by window

The default RAG recipe is fixed-size windows with overlap. For a code that is the wrong shape. Codes are trees: chapter, section, subsection, exception, table. Questions are asked at the section level ("what is the occupant load factor for business areas?"), and the answer is one cell of a table attached to one subsection.

codeplumb parses each document into that tree, using a small grammar per code family that recognises `CHAPTER 10`, `SECTION 1004`, `1004.5 Title`, `TABLE 1004.5`, and `Exception:` blocks. The chunk unit is the section body. Every chunk is embedded with its breadcrumb prefixed, so a body about "net floor area" still carries the words "Occupant Load" and "Means Of Egress" that the question will use. Exceptions, tables, and definitions become their own chunks, because burying an exception in a 900-token body is how a retriever misses the one sentence that matters.

The eval harness ships a `naive` mode that indexes the same documents as 512-token windows with no breadcrumb, searched by the same hybrid stack. On the synthetic golden set, section chunking beats it on every metric. The numbers are in `docs/EVALS.md`; the gap is the whole argument.

## Hybrid, fused, then grouped

Vector search alone misses exact section numbers and jargon. Full-text search alone misses paraphrase. codeplumb runs both against Postgres (pgvector HNSW for vectors, `tsvector` for text), fuses the two ranked lists with Reciprocal Rank Fusion, and only then collapses chunks to sections. Two details mattered more than expected:

- Postgres's `websearch_to_tsquery` ANDs every term, which is correct for "Section 1004.5" and hopeless for "how long can a dead-end corridor be". A second OR pass, ranked by `ts_rank_cd`, roughly doubled lexical recall on natural-language questions.
- Any explicit section number in the query is looked up exactly and injected as a top lexical hit, so "what does 1017.3 say" short-circuits to the right place.

Amendments are the last piece. Ohio adopts the IBC and then amends it rule by rule. codeplumb keeps amendments on a separate layer, pairs any same-numbered section with its amendment, and puts the amendment directly above the base hit with a note in the citation. It does not try to merge the texts; deciding which words control is left to the reader in v1.

## What an MCP server needs to expose

The server is deliberately retrieval-only. It offers a search tool whose result is the section, not a blob: number, title, breadcrumb, pages, full body, the exceptions and tables that matched, the cross-references out, the amendment overlay, and a ready-to-paste citation string. It offers an exact lookup, a "what surrounds this" tool, a reference resolver, and resources that let a client pull a section into context by URI. A prompt template tells the client model to search first, quote only from tool results, cite every claim, and say so when the corpus does not cover the question.

Errors are short and actionable ("section '1017.99' not found; nearest: 1017.2, 1017.3") because the model reads them. There is no LLM call on the server side, so there is nothing to inject into; indexed text is data, never instructions.

## What I would do next

A cross-encoder reranker behind a flag, measured by the same eval. Real amendment merging. And a run against a real Ohio corpus, which anyone with a licensed IBC PDF can do in ten minutes with the commands in the README.
