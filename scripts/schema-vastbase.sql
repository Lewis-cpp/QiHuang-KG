-- Schema v2: portable relational DDL; JSON is validated UTF-8 TEXT.
-- Run only in a new release schema, in one transaction. No destructive DDL.
CREATE TABLE build (
    id VARCHAR(64) PRIMARY KEY,
    schema_version INTEGER NOT NULL CHECK (schema_version = 2),
    transform_version TEXT NOT NULL,
    created_at TEXT NOT NULL,
    manifest_json TEXT NOT NULL
);
CREATE TABLE dataset (
    id VARCHAR(80) PRIMARY KEY,
    title TEXT NOT NULL,
    version_label TEXT NOT NULL,
    source_url TEXT NOT NULL,
    license_statement TEXT NOT NULL,
    attribution TEXT NOT NULL
);
CREATE TABLE source_record (
    id VARCHAR(160) PRIMARY KEY,
    dataset_id VARCHAR(80) NOT NULL REFERENCES dataset(id),
    filename VARCHAR(160) NOT NULL,
    file_sha256 VARCHAR(64) NOT NULL CHECK (length(file_sha256) = 64),
    record_key VARCHAR(160) NOT NULL,
    record_locator TEXT NOT NULL,
    content_json TEXT NOT NULL,
    UNIQUE (dataset_id, filename, record_key)
);
CREATE TABLE entity (
    id VARCHAR(200) PRIMARY KEY,
    dataset_id VARCHAR(80) NOT NULL REFERENCES dataset(id),
    type VARCHAR(40) NOT NULL CHECK (type IN
        ('herb', 'formula', 'pattern', 'text', 'tcm_term', 'patent_medicine',
         'herbal_piece', 'icd11_code', 'medicinal_property')),
    source_key VARCHAR(160) NOT NULL,
    label TEXT NOT NULL CHECK (length(trim(label)) > 0),
    slug TEXT NOT NULL,
    category TEXT,
    name_norm TEXT NOT NULL,
    search_text_norm TEXT NOT NULL,
    attributes_json TEXT NOT NULL,
    source_record_id VARCHAR(160) NOT NULL REFERENCES source_record(id),
    review_status_raw TEXT,
    review_status VARCHAR(40) NOT NULL CHECK (review_status IN
        ('editor_reviewed', 'draft', 'needs_review', 'unknown')),
    UNIQUE (dataset_id, type, source_key)
);
CREATE INDEX entity_type_name ON entity(type, name_norm, id);
CREATE INDEX entity_name ON entity(name_norm, id);
CREATE TABLE alias (
    entity_id VARCHAR(200) NOT NULL REFERENCES entity(id),
    name TEXT NOT NULL CHECK (length(trim(name)) > 0),
    name_norm VARCHAR(500) NOT NULL,
    source_record_id VARCHAR(160) NOT NULL REFERENCES source_record(id),
    field_path VARCHAR(200) NOT NULL,
    PRIMARY KEY (entity_id, name_norm, source_record_id, field_path)
);
CREATE INDEX alias_name ON alias(name_norm, entity_id);
CREATE TABLE edge (
    id VARCHAR(160) PRIMARY KEY,
    source_id VARCHAR(200) NOT NULL REFERENCES entity(id),
    relation VARCHAR(40) NOT NULL CHECK (relation IN
        ('CONTAINS', 'ASSOCIATED_WITH_PATTERN', 'CITED_IN', 'HAS_HERBAL_PIECE',
         'ASSOCIATED_WITH_TERM', 'MAPPED_TO_ICD11', 'HAS_MEDICINAL_PROPERTY')),
    target_id VARCHAR(200) NOT NULL REFERENCES entity(id),
    properties_json TEXT NOT NULL,
    quality_state VARCHAR(40) NOT NULL CHECK (quality_state IN ('consistent', 'conflicting')),
    CHECK (source_id <> target_id),
    UNIQUE (source_id, relation, target_id)
);
CREATE INDEX edge_outgoing ON edge(source_id, relation, target_id);
CREATE INDEX edge_incoming ON edge(target_id, relation, source_id);
CREATE TABLE evidence (
    id VARCHAR(160) PRIMARY KEY,
    entity_id VARCHAR(200) REFERENCES entity(id),
    edge_id VARCHAR(160) REFERENCES edge(id),
    source_record_id VARCHAR(160) NOT NULL REFERENCES source_record(id),
    field_path TEXT NOT NULL,
    kind VARCHAR(40) NOT NULL CHECK (kind IN
        ('curated', 'source_quote', 'bibliographic', 'auto_extracted', 'rule_inferred')),
    excerpt TEXT,
    CHECK ((entity_id IS NOT NULL AND edge_id IS NULL) OR
           (entity_id IS NULL AND edge_id IS NOT NULL)),
    CHECK (kind <> 'source_quote' OR (excerpt IS NOT NULL AND length(trim(excerpt)) > 0))
);
CREATE INDEX evidence_entity ON evidence(entity_id, id);
CREATE INDEX evidence_edge ON evidence(edge_id, id);
-- Cross-row endpoint types, JSON/pointers, content digests and evidence coverage
-- are publication gates in prepare_data.py and import_vastbase.py.
