-- Business views appended after schema-vastbase.sql in every release schema; shared by PostgreSQL and Vastbase.
-- Views only read existing tables, so rerunning this file replaces them without touching data.
CREATE OR REPLACE VIEW v_formula_composition AS
SELECT e.id AS edge_id,
       f.id AS formula_id,
       f.label AS formula_label,
       h.id AS herb_id,
       h.label AS herb_label,
       CAST(e.properties_json AS json) ->> 'dosage_raw' AS dosage_raw,
       CAST(e.properties_json AS json) ->> 'role' AS role,
       CAST(CAST(e.properties_json AS json) ->> 'position' AS INTEGER) AS position,
       e.quality_state
FROM edge e
JOIN entity f ON f.id = e.source_id
JOIN entity h ON h.id = e.target_id
WHERE e.relation = 'CONTAINS';

CREATE OR REPLACE VIEW v_entity_relation_summary AS
SELECT source_id AS entity_id, relation, CAST('out' AS VARCHAR(3)) AS direction, count(*) AS count
FROM edge GROUP BY source_id, relation
UNION ALL
SELECT target_id AS entity_id, relation, CAST('in' AS VARCHAR(3)) AS direction, count(*) AS count
FROM edge GROUP BY target_id, relation;
