CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE corpora (
  id            text PRIMARY KEY,
  title         text NOT NULL,
  jurisdiction  text,
  profile       text NOT NULL,
  created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE documents (
  id            bigserial PRIMARY KEY,
  corpus_id     text NOT NULL REFERENCES corpora(id) ON DELETE CASCADE,
  title         text NOT NULL,
  layer         text NOT NULL CHECK (layer IN ('base','amendment')),
  version       text,
  source_path   text NOT NULL,
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
  number        text NOT NULL,
  number_norm   text NOT NULL,
  title         text,
  depth         int NOT NULL,
  path          text NOT NULL,
  body          text NOT NULL DEFAULT '',
  page_start    int,
  page_end      int,
  ordinal       int NOT NULL,
  supersedes_number text,
  UNIQUE (document_id, number)
);
CREATE INDEX sections_corpus_number ON sections (corpus_id, number);
CREATE INDEX sections_parent ON sections (parent_id);

CREATE TABLE chunks (
  id            bigserial PRIMARY KEY,
  section_id    bigint NOT NULL REFERENCES sections(id) ON DELETE CASCADE,
  corpus_id     text NOT NULL REFERENCES corpora(id) ON DELETE CASCADE,
  kind          text NOT NULL CHECK (kind IN ('body','table','definition','exception')),
  ordinal       int NOT NULL,
  text          text NOT NULL,
  content       text NOT NULL,
  token_count   int NOT NULL,
  page_start    int,
  page_end      int,
  embedding     vector({DIM}) NOT NULL,
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
  ref_text        text NOT NULL,
  ref_number      text NOT NULL,
  ref_kind        text NOT NULL,
  to_section_id   bigint REFERENCES sections(id) ON DELETE SET NULL
);
CREATE INDEX cross_refs_from ON cross_refs (from_section_id);
CREATE INDEX cross_refs_to ON cross_refs (to_section_id);

CREATE TABLE embedding_config (
  singleton     bool PRIMARY KEY DEFAULT true CHECK (singleton),
  provider      text NOT NULL,
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
  status        text NOT NULL,
  stats         jsonb,
  error         text
);
