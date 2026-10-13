"""PostgreSQL schema for the derived index.

The schema is a rendering of the model, not a place where a fact is authored.
Every column either holds a value extracted from committed bytes or the
provenance of the build that wrote it (`commit_sha`, `model_version`, `digest`).

`reset` drops and recreates the tables, which is what makes "destroy the
database and rebuild from git" a real operation rather than a claim.
"""

from __future__ import annotations

#: Bumped with the DDL below. Written into `index_meta` so a stale or foreign
#: schema can be refused instead of read as if it were current.
INDEX_SCHEMA_VERSION = 1

DDL = """
CREATE TABLE IF NOT EXISTS index_meta (
    id                integer PRIMARY KEY CHECK (id = 1),
    project           text    NOT NULL,
    commit_sha        text    NOT NULL,
    source_rev        text    NOT NULL,
    model_version     integer NOT NULL,
    schema_version    integer NOT NULL,
    digest            text    NOT NULL,
    document_count    integer NOT NULL,
    table_count       integer NOT NULL
);

CREATE TABLE IF NOT EXISTS documents (
    path        text NOT NULL PRIMARY KEY,
    concept_id  text NOT NULL,
    doc_type    text NOT NULL,
    title       text NOT NULL,
    status      text NOT NULL,
    headings    text[] NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS document_fields (
    path  text NOT NULL REFERENCES documents(path) ON DELETE CASCADE,
    key   text NOT NULL,
    value text NOT NULL,
    PRIMARY KEY (path, key)
);

CREATE TABLE IF NOT EXISTS document_links (
    src   text NOT NULL REFERENCES documents(path) ON DELETE CASCADE,
    dst   text NOT NULL,
    ordinal integer NOT NULL,
    PRIMARY KEY (src, ordinal)
);

CREATE TABLE IF NOT EXISTS registry_tables (
    source   text NOT NULL,
    ordinal  integer NOT NULL,
    columns  text[] NOT NULL,
    PRIMARY KEY (source, ordinal)
);

CREATE TABLE IF NOT EXISTS registry_rows (
    source   text NOT NULL,
    ordinal  integer NOT NULL,
    row_index integer NOT NULL,
    PRIMARY KEY (source, ordinal, row_index)
);

CREATE TABLE IF NOT EXISTS registry_cells (
    source    text NOT NULL,
    ordinal   integer NOT NULL,
    row_index integer NOT NULL,
    key       text NOT NULL,
    value     text NOT NULL,
    PRIMARY KEY (source, ordinal, row_index, key)
);

CREATE INDEX IF NOT EXISTS documents_doc_type_idx ON documents (doc_type);
CREATE INDEX IF NOT EXISTS document_fields_key_idx ON document_fields (key);
CREATE INDEX IF NOT EXISTS document_links_dst_idx ON document_links (dst);
"""

#: Dropped in dependency order, children first, so `reset` never fails on a
#: foreign key.
DROP = """
DROP TABLE IF EXISTS registry_cells;
DROP TABLE IF EXISTS registry_rows;
DROP TABLE IF EXISTS registry_tables;
DROP TABLE IF EXISTS document_links;
DROP TABLE IF EXISTS document_fields;
DROP TABLE IF EXISTS documents;
DROP TABLE IF EXISTS index_meta;
"""
