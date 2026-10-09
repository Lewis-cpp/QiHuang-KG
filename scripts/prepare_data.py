"""Clean both sources into an immutable, validated staging database (stdlib only)."""

import argparse
import csv
import hashlib
import io
import json
import re
import sqlite3
import sys
import tempfile
from collections import Counter, defaultdict
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from import_core import ROOT, TABLES, build as build_core, canonical, digest, normalize, pointer, require, write_json

RAW = ROOT / "datasets/raw/tcm-mkg"
DDL = ROOT / "docs/schema-vastbase.sql"
VERSION = "2.0.0"
FILES = {
    "D1_TCM_terminology.tsv": "TCMT_ID Chinese_group English_group Chinese_term Pinyin_term Chinese_synonyms English_term Synonyms English_definition_description",
    "D2_Chinese_patent_medicine.tsv": "CPM_ID Chinese_patent_medicine Pinyin_term Routes_of_administration",
    "D3_CPM_TCMT.tsv": "CPM_ID TCMT_ID Chinese_group English_group Chinese_term Pinyin_term English_term Synonyms",
    "D4_CPM_CHP.tsv": "CPM_ID CHP_ID Dosage_ratio",
    "D5_CPM_ICD11.tsv": "CPM_ID ICD11_code",
    "D6_Chinese_herbal_pieces.tsv": "CHP_ID Chinese_herbal_pieces Chinese_synonyms Pinyin_term English_term Sources",
    "D7_CHP_Medicinal_properties.tsv": "CHP_ID Medicinal_properties Class x_rank y_rank",
}
ENDPOINT_CHECK = """SELECT count(*) FROM edge e
LEFT JOIN entity s ON s.id=e.source_id LEFT JOIN entity t ON t.id=e.target_id
WHERE s.id IS NULL OR t.id IS NULL OR NOT (
 (e.relation='CONTAINS' AND s.type='formula' AND t.type='herb') OR
 (e.relation='ASSOCIATED_WITH_PATTERN' AND s.type='formula' AND t.type='pattern') OR
 (e.relation='CITED_IN' AND s.type IN ('herb','formula') AND t.type='text') OR
 (e.relation='HAS_HERBAL_PIECE' AND s.type='patent_medicine' AND t.type='herbal_piece') OR
 (e.relation='ASSOCIATED_WITH_TERM' AND s.type='patent_medicine' AND t.type='tcm_term') OR
 (e.relation='MAPPED_TO_ICD11' AND s.type='patent_medicine' AND t.type='icd11_code') OR
 (e.relation='HAS_MEDICINAL_PROPERTY' AND s.type='herbal_piece' AND t.type='medicinal_property'))"""
QUALITY_CHECKS = {
    "invalid_endpoint_types": ENDPOINT_CHECK,
    "missing_entity_evidence": "SELECT count(*) FROM entity e WHERE NOT EXISTS "
                               "(SELECT 1 FROM evidence v WHERE v.entity_id=e.id)",
    "missing_edge_evidence": "SELECT count(*) FROM edge e WHERE NOT EXISTS "
                             "(SELECT 1 FROM evidence v WHERE v.edge_id=e.id)",
    "entity_source_dataset_mismatch": "SELECT count(*) FROM entity e JOIN source_record s "
                                      "ON s.id=e.source_record_id WHERE e.dataset_id<>s.dataset_id",
}


def check_quality(cursor):
    counts = {}
    for name, query in QUALITY_CHECKS.items():
        cursor.execute(query)
        counts[name] = cursor.fetchone()[0]
        require(counts[name] == 0, f"Quality check failed: {name} ({counts[name]})")
    return counts


def read_tsv(path):
    """Parse quoted multiline TSV; repair only the exact, previously inspected row."""
    text = path.read_bytes().decode("utf-8-sig")
    require("\x00" not in text, f"NUL byte: {path.name}")
    lines = text.splitlines(keepends=True)
    reader = csv.reader(io.StringIO(text, newline=""), delimiter="\t", strict=True)
    header = next(reader)
    require(header == FILES[path.name].split(), f"Header changed: {path.name}")
    end = reader.line_num
    for number, cells in enumerate(reader, 1):
        start, end = end + 1, reader.line_num
        original = cells[:]
        raw_text = "".join(lines[start - 1:end])
        repair = None
        if len(cells) != len(header):
            if (path.name == "D6_Chinese_herbal_pieces.tsv" and start == 1718 and
                    hashlib.sha256(raw_text.encode()).hexdigest() ==
                    "759e6c78b51d8a34e407b2eac5cf1c273dff864438836a407c521d3859b16528"):
                cells = cells[:3] + cells[4:]
                repair = "remove_exact_extra_empty_column_4"
            else:
                raise ValueError(f"Unexpected column count: {path.name}:{start} record {number}")
        fields = dict(zip(header, cells))
        # These aliases are source-supplied, not medically reviewed equivalences.
        aliases = list(dict.fromkeys(x.strip() for x in fields.get("Chinese_synonyms", "").split("|")
                                    if x.strip()))
        yield number, dict(fields=fields, raw_cells=original, raw_tsv=raw_text,
                           line_start=start, line_end=end, aliases=aliases, repair=repair)


def entity_id(kind, key):
    return f"tcm-mkg:{kind}:{key}"


def table_hash(rows):
    # Sorting row digests makes verification independent of database collation.
    return hashlib.sha256("".join(sorted(digest(list(r)) for r in rows)).encode()).hexdigest()


def summaries(db):
    counts = {t: db.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in TABLES}
    counts["business_records"] = counts["entity"] + counts["edge"]
    counts["entity_types"] = dict(db.execute("SELECT type,count(*) FROM entity GROUP BY type"))
    counts["relations"] = dict(db.execute("SELECT relation,count(*) FROM edge GROUP BY relation"))
    counts["entities_by_dataset"] = dict(db.execute("SELECT dataset_id,count(*) FROM entity GROUP BY dataset_id"))
    counts["edges_by_dataset"] = dict(db.execute(
        "SELECT s.dataset_id,count(*) FROM edge e JOIN entity s ON s.id=e.source_id GROUP BY s.dataset_id"))
    return counts


def import_tcm(db, raw, hashes):
    meta = json.loads((raw / "_record.json").read_text())["metadata"]
    db.execute("INSERT INTO dataset VALUES (?,?,?,?,?,?)", ("tcm-mkg", meta["title"], meta["version"],
               "https://doi.org/" + meta["doi"], meta["license"]["id"],
               "; ".join(x["name"] for x in meta["creators"])))
    report, issues, sources = {}, [], {}
    entities, claims = {}, defaultdict(list)

    def evidence(target, sid, path):
        eid = "evidence:" + digest([target, sid, path, "curated"])
        db.execute("INSERT INTO evidence VALUES (?,?,?,?,?,?,?)", (eid,
                   None if target.startswith("edge:") else target,
                   target if target.startswith("edge:") else None, sid, path, "curated", None))

    def entity(kind, key, label, sid, doc, category=None, derived=False):
        require(bool(key.strip()) and bool(label.strip()), f"Empty entity key/name: {sid}")
        eid = entity_id(kind, key)
        if eid in entities:
            require(derived, f"Duplicate entity ID: {eid}")
            evidence(eid, sid, "/fields")
            return eid
        entities[eid] = kind
        fields = doc["fields"]
        attrs = ({"code": key} if kind == "icd11_code" else
                 {"class": category, "name": label} if kind == "medicinal_property" else
                 {k: v if v.strip() else None for k, v in fields.items()})
        search = normalize("\n".join([label, *doc["aliases"], fields.get("Pinyin_term", ""),
                                    fields.get("English_term", "")]))
        db.execute("INSERT INTO entity VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", (eid, "tcm-mkg", kind,
                   key, label.strip(), key, category, normalize(label), search, canonical(attrs),
                   sid, None, "unknown"))
        evidence(eid, sid, "/fields")
        if not derived:
            for i, name in enumerate(doc["aliases"]):
                db.execute("INSERT INTO alias VALUES (?,?,?,?,?)",
                           (eid, name, normalize(name), sid, f"/aliases/{i}"))
        return eid

    for filename in FILES:
        rows = []
        for number, doc in read_tsv(raw / filename):
            sid = "source:" + digest(["tcm-mkg", filename, number])
            locator = f"record:{number};lines:{doc['line_start']}-{doc['line_end']}"
            db.execute("INSERT INTO source_record VALUES (?,?,?,?,?,?,?)", (sid, "tcm-mkg", filename,
                       hashes[filename], str(number), locator, canonical(doc)))
            rows.append((sid, doc))
            if doc["repair"]:
                issues.append(dict(code="repaired_extra_column", filename=filename, source_record_id=sid,
                                   locator=locator, raw_value=doc["raw_cells"], action=doc["repair"]))
        sources[filename[:2]] = rows
        report[filename] = dict(raw=len(rows), accepted=len(rows), rejected=0, unique_business=0)

    for prefix, kind, keyfield, label, category in (
            ("D1", "tcm_term", "TCMT_ID", "Chinese_term", "Chinese_group"),
            ("D2", "patent_medicine", "CPM_ID", "Chinese_patent_medicine", None),
            ("D6", "herbal_piece", "CHP_ID", "Chinese_herbal_pieces", "Sources")):
        for sid, doc in sources[prefix]:
            row = doc["fields"]
            require(bool(re.fullmatch(keyfield.removesuffix("_ID") + r"[0-9]{5}", row[keyfield])),
                    f"Invalid ID: {sid} ({keyfield}={row[keyfield]})")
            entity(kind, row[keyfield], row[label], sid, doc, row.get(category))
        report[next(n for n in FILES if n.startswith(prefix))]["unique_business"] = len(sources[prefix])

    for prefix, relation, skind, sfield, tkind, tfield in (
            ("D3", "ASSOCIATED_WITH_TERM", "patent_medicine", "CPM_ID", "tcm_term", "TCMT_ID"),
            ("D4", "HAS_HERBAL_PIECE", "patent_medicine", "CPM_ID", "herbal_piece", "CHP_ID"),
            ("D5", "MAPPED_TO_ICD11", "patent_medicine", "CPM_ID", "icd11_code", "ICD11_code"),
            ("D7", "HAS_MEDICINAL_PROPERTY", "herbal_piece", "CHP_ID", "medicinal_property", "Medicinal_properties")):
        unique = set()
        for sid, doc in sources[prefix]:
            row = doc["fields"]
            source = entity_id(skind, row[sfield])
            key = row[tfield]
            if prefix == "D5":
                target = entity(tkind, key, key, sid, doc, derived=True)
            elif prefix == "D7":
                require(bool(row["Class"].strip()), f"Missing property class: {sid}")
                target = entity(tkind, digest([row["Class"], key]), key, sid, doc, row["Class"], True)
            else:
                target = entity_id(tkind, key)
            require(source in entities and target in entities, f"Missing endpoint: {sid}")
            triple = (source, relation, target)
            claims[triple].append((sid, {k: v for k, v in row.items() if k not in (sfield, tfield)}))
            unique.add(triple)
        report[next(n for n in FILES if n.startswith(prefix))]["unique_business"] = len(unique)

    for triple, entries in sorted(claims.items()):
        eid = "edge:" + digest(list(triple))
        properties, conflicts = {}, {}
        for key in sorted({k for _, fields in entries for k in fields}):
            values = list(dict.fromkeys(fields[key] for _, fields in entries if fields.get(key, "").strip()))
            properties[key] = values[0] if len(values) == 1 else None
            if len(values) > 1:
                conflicts[key] = values
        if conflicts:
            properties["conflicts"] = conflicts
        db.execute("INSERT INTO edge VALUES (?,?,?,?,?,?)", (eid, *triple, canonical(properties),
                   "conflicting" if conflicts else "consistent"))
        for sid, _ in entries:
            evidence(eid, sid, "/fields")
        if len(entries) > 1:
            issues.append(dict(code="duplicate_relation", edge_id=eid, sources=[s for s, _ in entries],
                               conflicts=conflicts, action="merge_nonempty_fields_keep_all_evidence"))
    return report, issues


def validate(db, manifest):
    require(db.execute("PRAGMA integrity_check").fetchone() == ("ok",), "Integrity failure")
    require(not db.execute("PRAGMA foreign_key_check").fetchall(), "Foreign key failure")
    check_quality(db.cursor())
    for column, table in (("attributes_json", "entity"), ("properties_json", "edge")):
        for (payload,) in db.execute(f"SELECT {column} FROM {table}"):
            require(isinstance(json.loads(payload), dict), f"Invalid JSON object: {table}")
    for table, value in (("evidence", "excerpt"), ("alias", "name")):
        for payload, path, expected, kind in db.execute(
                f"SELECT s.content_json,v.field_path,v.{value}," +
                ("v.kind" if table == "evidence" else "'alias'") +
                f" FROM {table} v JOIN source_record s ON s.id=v.source_record_id"):
            resolved = pointer(json.loads(payload), path)
            if kind in ("source_quote", "alias"):
                require(resolved == expected, f"Evidence value differs: {path}")
    require(summaries(db) == manifest["counts"], "Count mismatch")
    for table in TABLES:
        require(table_hash(db.execute(f"SELECT * FROM {table}")) == manifest["table_sha256"][table],
                f"Content mismatch: {table}")
    saved = db.execute("SELECT * FROM build").fetchall()
    require(len(saved) == 1 and saved[0][:4] == (manifest["build_id"], 2, VERSION, manifest["created_at"])
            and json.loads(saved[0][4]) == manifest, "Build manifest mismatch")


def build(raw=RAW, releases=ROOT / "var/prepared"):
    core_dir, core, _ = build_core()
    inputs = {name: hashlib.sha256((raw / name).read_bytes()).hexdigest() for name in (*FILES, "_record.json")}
    identity = dict(schema_version=2, transform_version=VERSION, core_build_id=core["build_id"],
                    input_sha256=inputs, schema_sha256=hashlib.sha256(DDL.read_bytes()).hexdigest(),
                    transform_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    build_id = digest(identity)
    releases.mkdir(parents=True, exist_ok=True)
    release = releases / build_id
    with tempfile.TemporaryDirectory(prefix=".building-", dir=releases) as temp:
        stage = Path(temp) / build_id
        stage.mkdir()
        with closing(sqlite3.connect(stage / "kg.sqlite")) as db:
            db.execute("PRAGMA foreign_keys=ON")
            db.executescript(DDL.read_text())
            with db, closing(sqlite3.connect(core_dir / "kg.sqlite")) as baseline:
                core_hashes = {}
                for table in TABLES:
                    rows = baseline.execute(f"SELECT * FROM {table}").fetchall()
                    core_hashes[table] = table_hash(rows)
                    if rows:
                        db.executemany(f"INSERT INTO {table} VALUES ({','.join('?' for _ in rows[0])})", rows)
                    require(table_hash(db.execute(f"SELECT * FROM {table}")) == core_hashes[table],
                            f"Core migration mismatch: {table}")
                files, issues = import_tcm(db, raw, inputs)
                require(inputs == {n: hashlib.sha256((raw / n).read_bytes()).hexdigest() for n in inputs},
                        "Inputs changed during import")
                counts = summaries(db)
                require(counts["business_records"] >= 100000, "Fewer than 100,000 business records")
                report = dict(status="prepared_not_imported", build_id=build_id, files=files, issues=issues,
                              issue_counts=dict(Counter(x["code"] for x in issues)), counts=counts,
                              core_issue_counts=core["issue_counts"], core_table_sha256=core_hashes,
                              quality=check_quality(db.cursor()),
                              checks={k: "passed" for k in ("core_row_equality", "foreign_keys", "endpoint_types",
                                      "entity_evidence_coverage", "dataset_provenance", "evidence_pointers",
                                      "raw_preservation", "business_count")})
                manifest = dict(identity, build_id=build_id, created_at=datetime.now(timezone.utc).isoformat(),
                                counts=counts, report_sha256=digest(report),
                                table_sha256={t: table_hash(db.execute(f"SELECT * FROM {t}")) for t in TABLES})
                db.execute("INSERT INTO build VALUES (?,?,?,?,?)", (build_id, 2, VERSION,
                           manifest["created_at"], canonical(manifest)))
            validate(db, manifest)
            write_json(stage / "manifest.json", manifest)
            write_json(stage / "report.json", report)
        reused = release.exists()
        if reused:
            existing = json.loads((release / "manifest.json").read_text())
            require(all(existing[k] == v for k, v in identity.items()), "Existing identity mismatch")
            require(existing["table_sha256"] == manifest["table_sha256"], "Nonreproducible content")
            require(existing["report_sha256"] == digest(json.loads((release / "report.json").read_text()))
                    == manifest["report_sha256"], "Report mismatch")
            with closing(sqlite3.connect(release.as_uri() + "/kg.sqlite?mode=ro", uri=True)) as db:
                validate(db, existing)
            manifest = existing
        else:
            stage.rename(release)
    return release, manifest, reused


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, default=RAW)
    parser.add_argument("--releases-dir", type=Path, default=ROOT / "var/prepared")
    args = parser.parse_args()
    try:
        release, manifest, reused = build(args.raw_dir.resolve(), args.releases_dir.resolve())
    except (ValueError, OSError, sqlite3.Error, csv.Error, KeyError) as error:
        args.releases_dir.mkdir(parents=True, exist_ok=True)
        write_json(args.releases_dir / "last-failure.json", dict(status="failed", error=str(error)))
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    print(json.dumps(dict(status="reused" if reused else "prepared", release=str(release),
                          build_id=manifest["build_id"], counts=manifest["counts"]), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
