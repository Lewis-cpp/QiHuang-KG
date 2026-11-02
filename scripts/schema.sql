-- QiHuang-KG MVP schema v1. A new database is built for every release.
-- Enable foreign_keys on EVERY connection, including read-only connections.
PRAGMA foreign_keys = ON;

CREATE TABLE build (
    id TEXT PRIMARY KEY NOT NULL,
    schema_version INTEGER NOT NULL CHECK (schema_version = 1),
    transform_version TEXT NOT NULL,
    created_at TEXT NOT NULL,
    manifest_json TEXT NOT NULL CHECK (json_valid(manifest_json))
);

CREATE TABLE dataset (
    id TEXT PRIMARY KEY NOT NULL,
    title TEXT NOT NULL,
    version_label TEXT NOT NULL,
    source_url TEXT NOT NULL,
    license_statement TEXT NOT NULL,
    attribution TEXT NOT NULL
);

CREATE TABLE source_record (
    id TEXT PRIMARY KEY NOT NULL,
    dataset_id TEXT NOT NULL REFERENCES dataset(id),
    filename TEXT NOT NULL,
    file_sha256 TEXT NOT NULL CHECK (length(file_sha256) = 64),
    record_key TEXT NOT NULL,
    record_locator TEXT NOT NULL,
    content_json TEXT NOT NULL CHECK (json_valid(content_json)),
    UNIQUE (dataset_id, filename, record_key)
);

CREATE TABLE entity (
    id TEXT PRIMARY KEY NOT NULL,
    dataset_id TEXT NOT NULL REFERENCES dataset(id),
    type TEXT NOT NULL CHECK (type IN ('herb', 'formula', 'pattern', 'text')),
    source_key TEXT NOT NULL,
    label TEXT NOT NULL CHECK (length(trim(label)) > 0),
    slug TEXT NOT NULL,
    category TEXT,
    name_norm TEXT NOT NULL,
    search_text_norm TEXT NOT NULL,
    attributes_json TEXT NOT NULL CHECK (json_valid(attributes_json)),
    source_record_id TEXT NOT NULL UNIQUE REFERENCES source_record(id),
    review_status_raw TEXT,
    review_status TEXT NOT NULL CHECK (review_status IN
        ('editor_reviewed', 'draft', 'needs_review', 'unknown')),
    UNIQUE (dataset_id, type, source_key)
);
CREATE INDEX entity_type_name ON entity(type, name_norm, id);
CREATE INDEX entity_name ON entity(name_norm, id);

CREATE TABLE alias (
    entity_id TEXT NOT NULL REFERENCES entity(id),
    name TEXT NOT NULL CHECK (length(trim(name)) > 0),
    name_norm TEXT NOT NULL,
    source_record_id TEXT NOT NULL REFERENCES source_record(id),
    field_path TEXT NOT NULL,
    PRIMARY KEY (entity_id, name_norm, source_record_id, field_path)
);
CREATE INDEX alias_name ON alias(name_norm, entity_id);

CREATE TABLE edge (
    id TEXT PRIMARY KEY NOT NULL,
    source_id TEXT NOT NULL REFERENCES entity(id),
    relation TEXT NOT NULL CHECK (relation IN
        ('CONTAINS', 'ASSOCIATED_WITH_PATTERN', 'CITED_IN')),
    target_id TEXT NOT NULL REFERENCES entity(id),
    properties_json TEXT NOT NULL CHECK (json_valid(properties_json)),
    quality_state TEXT NOT NULL CHECK (quality_state IN ('consistent', 'conflicting')),
    CHECK (source_id <> target_id),
    UNIQUE (source_id, relation, target_id)
);
CREATE INDEX edge_outgoing ON edge(source_id, relation, target_id);
CREATE INDEX edge_incoming ON edge(target_id, relation, source_id);

CREATE TRIGGER edge_type_insert BEFORE INSERT ON edge
WHEN NOT EXISTS (
    SELECT 1 FROM entity s, entity t
    WHERE s.id = NEW.source_id AND t.id = NEW.target_id AND (
        (NEW.relation = 'CONTAINS' AND s.type = 'formula' AND t.type = 'herb') OR
        (NEW.relation = 'ASSOCIATED_WITH_PATTERN' AND s.type = 'formula' AND t.type = 'pattern') OR
        (NEW.relation = 'CITED_IN' AND s.type IN ('herb', 'formula') AND t.type = 'text')
    )
)
BEGIN
    SELECT RAISE(ABORT, 'invalid edge endpoint types');
END;

-- Release construction only uses INSERT. Mutating endpoints/types requires a rebuild.
CREATE TRIGGER edge_identity_immutable BEFORE UPDATE OF source_id, relation, target_id ON edge
BEGIN
    SELECT RAISE(ABORT, 'rebuild to change edge identity');
END;
CREATE TRIGGER entity_type_immutable BEFORE UPDATE OF type ON entity
BEGIN
    SELECT RAISE(ABORT, 'rebuild to change entity type');
END;

CREATE TABLE evidence (
    id TEXT PRIMARY KEY NOT NULL,
    entity_id TEXT REFERENCES entity(id),
    edge_id TEXT REFERENCES edge(id),
    source_record_id TEXT NOT NULL REFERENCES source_record(id),
    field_path TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN
        ('curated', 'source_quote', 'bibliographic', 'auto_extracted', 'rule_inferred')),
    excerpt TEXT,
    CHECK ((entity_id IS NOT NULL) + (edge_id IS NOT NULL) = 1),
    CHECK (kind <> 'source_quote' OR (excerpt IS NOT NULL AND length(trim(excerpt)) > 0))
);
CREATE INDEX evidence_entity ON evidence(entity_id, id);
CREATE INDEX evidence_edge ON evidence(edge_id, id);

-- Publication gates also validate JSON pointers and require >=1 evidence per edge.
-- Those cross-row checks run after the complete import, before publication.
