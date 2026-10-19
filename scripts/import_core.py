"""Build a validated, immutable SQLite snapshot using only the standard library."""

import argparse
import hashlib
import json
import re
import sqlite3
import sys
import tempfile
import unicodedata
from collections import Counter, defaultdict
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "datasets/raw/bencaodian"
CURATED = ROOT / "datasets/curated"
SCHEMA = ROOT / "docs/schema.sql"
TRANSFORM_VERSION = "1.1.0"
ENTITY_FILES = {"herbs.json": "herb", "formulas.json": "formula",
                "patterns.json": "pattern", "classical_texts.json": "text"}
CORE_RELATIONS = {"herb_in_formula", "formula_treats_pattern", "formula_cited_in_text"}
DEFERRED_RELATIONS = {"herb_enters_meridian", "herb_synergizes_with", "herb_incompatible_with",
                      "formula_derived_from", "pattern_differential_with", "acupoint_combines_with",
                      "acupoint_treats_pattern", "meridian_paired_with", "acupoint_on_meridian"}
TABLES = ("dataset", "source_record", "entity", "alias", "edge", "evidence")
SEARCH_FIELDS = ("name_zh", "title_zh", "name_pinyin", "title_pinyin", "name_en", "title_en",
                 "name_latin", "category", "description_zh", "description_en")
REVIEW_STATUS = {"editor-reviewed": "editor_reviewed", "verified": "editor_reviewed",
                 "draft": "draft", "needs-review": "needs_review"}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def normalize(value):
    return unicodedata.normalize("NFKC", value).strip().casefold()


def pointer(value, path):
    """Resolve an RFC 6901 pointer relative to an object or a complete file."""
    if path and not path.startswith("/"):
        raise ValueError(f"Invalid JSON Pointer: {path}")
    for token in path.split("/")[1:]:
        if re.search(r"~(?![01])", token):
            raise ValueError(f"Invalid JSON Pointer escape: {path}")
        token = token.replace("~1", "/").replace("~0", "~")
        if isinstance(value, list):
            if not re.fullmatch(r"0|[1-9][0-9]*", token):
                raise ValueError(f"Invalid array index: {path}")
            value = value[int(token)]
        else:
            value = value[token]
    return value


class ImportFailure(ValueError):
    def __init__(self, issue):
        super().__init__(f"{issue['code']}: {issue['filename']} {issue['record_key']} {issue['field_path']}")
        self.issue = issue


def issue(code, filename, record_key, field_path, raw_value, action, severity="warning"):
    return dict(severity=severity, code=code, filename=filename, record_key=record_key,
                field_path=field_path, raw_value=raw_value, action=action)


def fail(code, filename, key, path, value):
    raise ImportFailure(issue(code, filename, key, path, value, "终止构建，保留已有快照", "error"))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_inputs(raw, curated):
    paths = {f"raw/{name}": raw / name for name in (*ENTITY_FILES, "relationships.json",
                                                    "schema.json", "_source-page.md")}
    paths.update({f"curated/{name}": curated / name
                  for name in ("bencaodian.json", "known-issues.json", "corrections.json")})
    paths.update({"schema.sql": SCHEMA, "import_core.py": Path(__file__)})
    blobs = {}
    for name, path in paths.items():
        try:
            blobs[name] = path.read_bytes()
        except OSError as error:
            fail("input_unreadable", name, "", "", str(error))
    data = {}
    for name, blob in blobs.items():
        if name.endswith(".json"):
            try:
                data[name] = json.loads(blob)
            except (ValueError, UnicodeError) as error:
                fail("invalid_json", name, "", "", str(error))
    hashes = {name: hashlib.sha256(blob).hexdigest() for name, blob in blobs.items()}
    identity = dict(schema_version=1, transform_version=TRANSFORM_VERSION, input_sha256=hashes)
    return data, identity, blobs["schema.sql"].decode("utf-8")


def import_rows(db, data, hashes):
    metadata = data["curated/bencaodian.json"]
    require(metadata["id"] == "bencaodian", "This importer supports the bencaodian namespace")
    db.execute("INSERT INTO dataset VALUES (?,?,?,?,?,?)", tuple(metadata[k] for k in
               ("id", "title", "version_label", "source_url", "license_statement", "attribution")))
    issues, records, entities, claims = [], {}, {}, defaultdict(list)
    raw_counts, deferred = {}, {}

    def source(filename, key, locator, row):
        sid = "source:" + digest(["bencaodian", filename, key])
        if sid in records:
            if records[sid][2] != row:
                fail("duplicate_source_key", filename, key, locator, row)
            return sid
        records[sid] = (filename, key, row)
        db.execute("INSERT INTO source_record VALUES (?,?,?,?,?,?,?)",
                   (sid, "bencaodian", filename, hashes[f"raw/{filename}"], key, locator, canonical(row)))
        return sid

    def evidence(target, sid, path, kind="curated", excerpt=None):
        eid = "evidence:" + digest([target, sid, path, kind])
        db.execute("INSERT OR IGNORE INTO evidence VALUES (?,?,?,?,?,?,?)",
                   (eid, target if target.startswith("bencaodian:") else None,
                    target if target.startswith("edge:") else None, sid, path, kind, excerpt))

    def warn(code, sid, path, raw_value, action):
        filename, key, _ = records[sid]
        issues.append(issue(code, filename, key, path, raw_value, action))

    # Curated key corrections, each backed by quotations from the source itself (datasets/curated/corrections.json).
    corrections = {}
    for i, c in enumerate(data["curated/corrections.json"]["corrections"]):
        key = (f"bencaodian:formula:{c['formula']}", c["raw_herb"])
        if key in corrections:
            fail("duplicate_correction", "corrections.json", c["formula"], f"/corrections/{i}", c)
        corrections[key] = c
    applied = defaultdict(list)

    def add_claim(source_id, relation, kind, key, sid, path, properties=None, position=None, key_path=""):
        filename, record_key, row = records[sid]
        # A malformed key (e.g. a list) skips the lookup and fails below as missing_endpoint with its location.
        correction = corrections.get((source_id, key)) if relation == "CONTAINS" and isinstance(key, str) else None
        if correction:
            key = correction["herb"]
            warn("corrected_reference", sid, path + key_path, correction["raw_herb"],
                 f"按 corrections.json 改为 {correction['herb']}，原始记录保持不变")
        target = f"bencaodian:{kind}:{key}"
        if source_id not in entities or target not in entities:
            fail("missing_endpoint", filename, record_key, path, pointer(row, path))
        if correction:
            applied[(source_id, relation, target)].append(dict(
                source_record_id=sid, field_path=path + key_path, raw_value=correction["raw_herb"],
                corrected_value=key, reason_zh=correction["reason_zh"]))
        claims[(source_id, relation, target)].append((sid, path, properties or {}, position))

    for filename, kind in ENTITY_FILES.items():
        rows = data[f"raw/{filename}"]
        if not isinstance(rows, list) or not rows:
            fail("invalid_entity_array", filename, "", "", rows)
        raw_counts[filename] = len(rows)
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                fail("invalid_record", filename, "", f"/{index}", row)
            key = row.get("key")
            if not isinstance(key, str) or not re.fullmatch(r"[a-z0-9_]+", key):
                fail("invalid_source_key", filename, str(key), f"/{index}/key", key)
            entity_id = f"bencaodian:{kind}:{key}"
            if entity_id in entities:
                fail("duplicate_source_key", filename, key, f"/{index}/key", key)
            label_field = "title_zh" if kind == "text" else "name_zh"
            label = row.get(label_field)
            if not isinstance(label, str) or not normalize(label):
                fail("missing_label", filename, key, f"/{label_field}", label)
            if not isinstance(row.get("slug"), str) or not row["slug"].strip():
                fail("missing_slug", filename, key, "/slug", row.get("slug"))
            sid = source(filename, key, f"/{index}", row)
            entities[entity_id] = (row, sid, kind)
            verification = row.get("verification") or {}
            if not isinstance(verification, dict):
                fail("invalid_verification", filename, key, "/verification", verification)
            status_raw = verification.get("status")
            if status_raw is not None and not isinstance(status_raw, str):
                fail("invalid_review_status", filename, key, "/verification/status", status_raw)
            status = REVIEW_STATUS.get(status_raw, "unknown")
            if status == "unknown":
                warn("unknown_review_status", sid, "/verification/status", status_raw,
                     "保留原始状态，规范化为 unknown")
            # Composition is exposed through merged edges, never through unreviewed attributes.
            attrs = {k: v for k, v in row.items() if k not in
                     {"key", "slug", label_field, "verification", "composition"}}
            search = "\n".join(normalize(row[k]) for k in SEARCH_FIELDS if isinstance(row.get(k), str))
            db.execute("INSERT INTO entity VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                       (entity_id, "bencaodian", kind, key, label, row["slug"], row.get("category"),
                        normalize(label), search, canonical(attrs), sid, status_raw, status))
            evidence(entity_id, sid, "")

    for entity_id, (row, sid, kind) in entities.items():
        if kind == "formula":
            composition = row.get("composition", [])
            if not isinstance(composition, list):
                fail("invalid_composition", "formulas.json", row["key"], "/composition", composition)
            for i, item in enumerate(composition):
                if not isinstance(item, dict):
                    fail("invalid_composition", "formulas.json", row["key"], f"/composition/{i}", item)
                add_claim(entity_id, "CONTAINS", "herb", item.get("herb_key"), sid,
                          f"/composition/{i}", item, i, "/herb_key")
            if row.get("source_text_key"):
                add_claim(entity_id, "CITED_IN", "text", row["source_text_key"], sid, "/source_text_key")
        elif kind == "herb":
            references = row.get("classical_references", [])
            if not isinstance(references, list):
                fail("invalid_references", "herbs.json", row["key"], "/classical_references", references)
            for i, ref in enumerate(references):
                path = f"/classical_references/{i}"
                if not isinstance(ref, dict):
                    fail("invalid_reference", "herbs.json", row["key"], path, ref)
                linked = f"bencaodian:text:{ref.get('text_key')}" in entities
                if linked:
                    add_claim(entity_id, "CITED_IN", "text", ref["text_key"], sid, path)
                else:
                    evidence(entity_id, sid, path, "bibliographic")
                    warn("unresolved_reference", sid, path, ref.get("text_key"),
                         "保留中药实体引文及书目文字，不生成古籍边")
                if isinstance(ref.get("passage"), str) and ref["passage"].strip():
                    evidence(entity_id, sid, path + "/passage", "source_quote", ref["passage"])
        elif kind == "text":
            passages = row.get("passages", [])
            if not isinstance(passages, list):
                fail("invalid_passages", "classical_texts.json", row["key"], "/passages", passages)
            for i, passage in enumerate(passages):
                if not isinstance(passage, dict):
                    fail("invalid_passage", "classical_texts.json", row["key"], f"/passages/{i}", passage)
                if isinstance(passage.get("text"), str) and passage["text"].strip():
                    evidence(entity_id, sid, f"/passages/{i}/text", "source_quote", passage["text"])

    relations = data["raw/relationships.json"]
    if not isinstance(relations, dict):
        fail("invalid_relationships", "relationships.json", "", "", relations)
    unknown = relations.keys() - CORE_RELATIONS - DEFERRED_RELATIONS
    if unknown or CORE_RELATIONS - relations.keys():
        fail("unknown_relation_mapping", "relationships.json", "", "", sorted(relations))
    for relation, rows in relations.items():
        if not isinstance(rows, list):
            fail("invalid_relation_array", "relationships.json", relation, f"/{relation}", rows)
        raw_counts[relation] = len(rows)
        if relation in DEFERRED_RELATIONS:
            deferred[relation] = len(rows)
        for i, row in enumerate(rows):
            if not isinstance(row, dict):
                fail("invalid_record", "relationships.json", relation, f"/{relation}/{i}", row)
            sid = source("relationships.json", digest(row), f"/{relation}/{i}", row)
            if relation not in CORE_RELATIONS:
                continue
            formula = f"bencaodian:formula:{row.get('formula')}"
            if relation == "herb_in_formula":
                add_claim(formula, "CONTAINS", "herb", row.get("herb"), sid, "", row, key_path="/herb")
            elif relation == "formula_treats_pattern":
                add_claim(formula, "ASSOCIATED_WITH_PATTERN", "pattern", row.get("pattern"), sid, "")
            else:
                add_claim(formula, "CITED_IN", "text", row.get("text"), sid, "")

    correction_quotes = defaultdict(list)
    for (formula, raw_key), correction in corrections.items():
        if not any(triple[0] == formula and entry["raw_value"] == raw_key
                   for triple, entries in applied.items() for entry in entries):
            fail("stale_correction", "corrections.json", correction["formula"], "/corrections", correction)
        target = f"bencaodian:herb:{correction['herb']}"
        for quote in correction["basis"]:
            sid = "source:" + digest(["bencaodian", quote["filename"], quote["record_key"]])
            try:
                value = pointer(records[sid][2], quote["field_path"])
            except (KeyError, IndexError, ValueError):
                value = None
            if not isinstance(value, str) or quote["text"] not in value:
                fail("correction_basis_mismatch", "corrections.json", correction["formula"], quote["field_path"], quote)
            correction_quotes[(formula, "CONTAINS", target)].append((sid, quote["field_path"], value))

    fallback_positions = defaultdict(list)
    for triple, entries in sorted(claims.items()):
        if triple[1] == "CONTAINS" and all(e[3] is None for e in entries):
            fallback_positions[triple[0]].append(triple[2])
    for triple, entries in sorted(claims.items()):
        edge_id = "edge:" + digest(list(triple))
        properties, quality = {}, "consistent"
        if triple[1] == "CONTAINS":
            positions = sorted({e[3] for e in entries if e[3] is not None})
            properties["position"] = positions[0] if positions else fallback_positions[triple[0]].index(triple[2])
            properties["position_source"] = "composition" if positions else "target_id_order"
            properties["missing_claim_fields"] = []
            for field, normalized in (("role", "role"), ("dosage", "dosage_raw")):
                values = []
                for sid, path, attrs, _ in entries:
                    value = attrs.get(field)
                    if value is not None and not isinstance(value, str):
                        filename, key, _ = records[sid]
                        fail("invalid_composition_value", filename, key, path + "/" + field, value)
                    if value is None or not value.strip():
                        properties["missing_claim_fields"].append(
                            dict(source_record_id=sid, field_path=path + "/" + field))
                    elif value not in values:
                        values.append(value)
                properties[normalized] = values[0] if len(values) == 1 else None
                if len(values) > 1:
                    quality = "conflicting"
                    first_sid, first_path, _, _ = entries[0]
                    warn("conflicting_claim", first_sid, first_path + "/" + field, values,
                         "保留双方证据，冲突字段设为 null，关系标记 conflicting")
        if triple in applied:
            properties["corrections"] = applied[triple]
        db.execute("INSERT INTO edge VALUES (?,?,?,?,?,?)", (edge_id, *triple, canonical(properties), quality))
        for sid, path, _, _ in entries:
            evidence(edge_id, sid, path, "bibliographic" if triple[1] == "CITED_IN" else "curated")
        for sid, path, quote in correction_quotes.get(triple, []):
            evidence(edge_id, sid, path, "source_quote", quote)
    return sorted(issues, key=canonical), raw_counts, deferred


def summarize(db):
    counts = {table: db.execute(f"SELECT count(*) FROM {table}").fetchone()[0] for table in TABLES}
    counts["entity_types"] = dict(db.execute("SELECT type,count(*) FROM entity GROUP BY type"))
    counts["relations"] = dict(db.execute("SELECT relation,count(*) FROM edge GROUP BY relation"))
    counts["conflicting_edges"] = db.execute("SELECT count(*) FROM edge WHERE quality_state='conflicting'").fetchone()[0]
    return counts


def content_hash(db):
    checksum = hashlib.sha256()
    for row in db.execute("SELECT type,name,sql FROM sqlite_master ORDER BY type,name"):
        checksum.update(canonical(list(row)).encode())
        checksum.update(b"\n")
    for table in TABLES:
        checksum.update(table.encode())
        for row in db.execute(f"SELECT * FROM {table} ORDER BY 1,2,3"):
            checksum.update(canonical(list(row)).encode())
            checksum.update(b"\n")
    return checksum.hexdigest()


def validate(db, data, manifest):
    require(db.execute("PRAGMA integrity_check").fetchall() == [("ok",)], "SQLite integrity failure")
    require(not db.execute("PRAGMA foreign_key_check").fetchall(), "Foreign key failure")
    require(db.execute("SELECT count(*) FROM build").fetchone()[0] == 1, "Exactly one build is required")
    require(not db.execute("SELECT id FROM edge WHERE NOT EXISTS (SELECT 1 FROM evidence WHERE edge_id=edge.id)").fetchall(),
            "An edge has no evidence")
    require(not db.execute("SELECT e.id FROM entity e JOIN source_record s ON s.id=e.source_record_id "
                           "WHERE e.dataset_id<>s.dataset_id").fetchall(), "Dataset mismatch")
    require(not db.execute("SELECT e.id FROM edge e JOIN entity s ON s.id=e.source_id JOIN entity t ON t.id=e.target_id "
                           "WHERE NOT ((e.relation='CONTAINS' AND s.type='formula' AND t.type='herb') OR "
                           "(e.relation='ASSOCIATED_WITH_PATTERN' AND s.type='formula' AND t.type='pattern') OR "
                           "(e.relation='CITED_IN' AND s.type IN ('herb','formula') AND t.type='text'))").fetchall(),
            "Invalid endpoint types")
    records = {}
    for sid, filename, sha, locator, content in db.execute(
            "SELECT id,filename,file_sha256,record_locator,content_json FROM source_record"):
        row = json.loads(content)
        require(sha == manifest["input_sha256"][f"raw/{filename}"], f"Source hash mismatch: {sid}")
        require(pointer(data[f"raw/{filename}"], locator) == row, f"Source locator mismatch: {sid}")
        records[sid] = row
    for eid, sid, path, kind, excerpt in db.execute("SELECT id,source_record_id,field_path,kind,excerpt FROM evidence"):
        value = pointer(records[sid], path)
        if kind == "source_quote":
            require(isinstance(value, str) and value == excerpt and value.strip(), f"Invalid quotation: {eid}")
    for sid, path, name in db.execute("SELECT source_record_id,field_path,name FROM alias"):
        require(pointer(records[sid], path) == name, "Invalid alias provenance")
    require(summarize(db) == manifest["counts"], "Manifest counts mismatch")
    require(content_hash(db) == manifest["content_sha256"], "Snapshot content mismatch")
    saved = db.execute("SELECT id,schema_version,transform_version,created_at,manifest_json FROM build").fetchone()
    require(saved[:4] == (manifest["build_id"], manifest["schema_version"], manifest["transform_version"], manifest["created_at"])
            and json.loads(saved[4]) == manifest, "Build manifest mismatch")


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def build(raw=RAW, curated=CURATED, releases=ROOT / "var/releases", processed=ROOT / "datasets/processed"):
    data, identity, schema = read_inputs(raw, curated)
    build_id = digest(identity)
    release = releases / build_id
    releases.mkdir(parents=True, exist_ok=True)
    # A private directory and one final rename keep failed imports out of releases.
    with tempfile.TemporaryDirectory(prefix=".building-", dir=releases) as temp:
        staging = Path(temp) / build_id
        staging.mkdir()
        with closing(sqlite3.connect(staging / "kg.sqlite")) as db:
            db.executescript(schema)
            with db:
                issues, raw_counts, deferred = import_rows(db, data, identity["input_sha256"])
                known = data["curated/known-issues.json"]["issues"]
                signatures = lambda rows: {canonical({k: r[k] for k in
                    ("code", "filename", "record_key", "field_path", "raw_value")}) for r in rows}
                actual, accepted = signatures(issues), signatures(known)
                if actual != accepted:
                    fail("warning_baseline_changed", "known-issues.json", "", "/issues",
                         {"unexpected": [json.loads(x) for x in sorted(actual - accepted)],
                          "no_longer_present": [json.loads(x) for x in sorted(accepted - actual)]})
                report = dict(build_id=build_id, status="passed", issues=issues,
                              issue_counts=dict(Counter(x["code"] for x in issues)),
                              raw_counts=raw_counts, deferred_relations=deferred,
                              counts=summarize(db), checks={name: "passed" for name in
                                  ("foreign_keys", "integrity", "endpoint_types", "evidence_coverage",
                                   "source_pointers", "evidence_pointers", "warning_baseline", "manifest")})
                manifest = dict(identity, build_id=build_id, created_at=datetime.now(timezone.utc).isoformat(),
                                counts=report["counts"], raw_counts=raw_counts, issue_counts=report["issue_counts"],
                                content_sha256=content_hash(db), report_sha256=digest(report))
                db.execute("INSERT INTO build VALUES (?,?,?,?,?)", (build_id, 1, TRANSFORM_VERSION,
                           manifest["created_at"], canonical(manifest)))
            validate(db, data, manifest)
            write_json(staging / "manifest.json", manifest)
            write_json(staging / "report.json", report)
        reused = release.exists()
        if reused:
            existing = json.loads((release / "manifest.json").read_text(encoding="utf-8"))
            require({k: existing[k] for k in identity} == identity, "Existing release has different inputs")
            require(existing["build_id"] == build_id and existing["content_sha256"] == manifest["content_sha256"],
                    "Existing release differs from the reproducible build")
            with closing(sqlite3.connect((release / "kg.sqlite").resolve().as_uri() + "?mode=ro", uri=True)) as db:
                db.execute("PRAGMA foreign_keys=ON")
                validate(db, data, existing)
            require(digest(json.loads((release / "report.json").read_text(encoding="utf-8"))) == manifest["report_sha256"]
                    == existing["report_sha256"], "Existing report mismatch")
            manifest = existing
        else:
            staging.rename(release)
        # The normalized SQLite snapshot is authoritative; this is its readable quality report.
        processed.mkdir(parents=True, exist_ok=True)
        write_json(processed / f"{build_id}.json", report)
    return release, manifest, reused


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, default=RAW)
    parser.add_argument("--curated-dir", type=Path, default=CURATED)
    parser.add_argument("--releases-dir", type=Path, default=ROOT / "var/releases")
    parser.add_argument("--processed-dir", type=Path, default=ROOT / "datasets/processed")
    args = parser.parse_args()
    try:
        release, manifest, reused = build(args.raw_dir, args.curated_dir, args.releases_dir, args.processed_dir)
    except (ValueError, OSError, sqlite3.Error, KeyError, TypeError, IndexError, AttributeError) as error:
        problem = error.issue if isinstance(error, ImportFailure) else issue(
            "build_failed", "", "", "", str(error), "终止构建，保留已有快照", "error")
        args.processed_dir.mkdir(parents=True, exist_ok=True)
        write_json(args.processed_dir / "last-failure.json", {"status": "failed", "issues": [problem]})
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    print(json.dumps(dict(status="reused" if reused else "built", database=str((release / "kg.sqlite").resolve()),
                          build_id=manifest["build_id"], counts=manifest["counts"],
                          issue_counts=manifest["issue_counts"]), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
