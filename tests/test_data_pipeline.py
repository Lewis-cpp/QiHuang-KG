"""Run with python3 tests/test_data_pipeline.py (optional QIHUANG_TEST_DSN for SQL tests)."""

import csv
import hashlib
import json
import os
import sqlite3
import sys
import tempfile
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import import_vastbase
from import_core import canonical, digest
from prepare_data import DDL, FILES, QUALITY_CHECKS, RAW, build, check_quality, entity_id, import_tcm, read_tsv, validate


def hashes():
    return {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT / "datasets/raw").rglob("*") if p.is_file()}


def expect_failure(fn, text):
    try:
        fn()
    except ValueError as error:
        assert text in str(error), str(error)
    else:
        raise AssertionError(f"Expected failure: {text}")


def check_small_inputs(base):
    base.mkdir()
    (base / "_record.json").write_bytes((RAW / "_record.json").read_bytes())
    rows = {
        "D1": [["TCMT00001", "组", "Group", "术语", "shu yu", "别名|另名", "Term", "", "multiline\nquoted\tfield"]],
        "D2": [["CPM00001", "中成药", "test", "Oral"]],
        "D3": [["CPM00001", "TCMT00001", "组", "Group", "术语", "shu yu", "Term", synonym] for synonym in ("a", "b")],
        "D4": [["CPM00001", "CHP00001", "0"]],
        "D5": [["CPM00001", "X1"]],
        "D6": [["CHP00001", "饮片", "", "yin pian", "Piece", "Plant"]],
        "D7": [["CHP00001", "Same label", kind, "1", "2"] for kind in ("Flavor", "Nature")],
    }
    for filename, header in FILES.items():
        with (base / filename).open("w", newline="") as f:
            writer = csv.writer(f, delimiter="\t")
            writer.writerow(header.split())
            writer.writerows(rows[filename[:2]])
    inputs = {name: hashlib.sha256((base / name).read_bytes()).hexdigest() for name in FILES}
    with closing(sqlite3.connect(":memory:")) as db:
        db.execute("PRAGMA foreign_keys=ON")
        db.executescript(DDL.read_text())
        files, issues = import_tcm(db, base, inputs)
        assert files["D3_CPM_TCMT.tsv"]["unique_business"] == 1
        props, quality = db.execute("SELECT properties_json,quality_state FROM edge WHERE relation='ASSOCIATED_WITH_TERM'").fetchone()
        assert quality == "conflicting"
        assert json.loads(props)["Synonyms"] is None
        assert json.loads(props)["conflicts"] == {"Synonyms": ["a", "b"]}
        assert db.execute("SELECT count(*) FROM entity WHERE type='medicinal_property'").fetchone()[0] == 2
        assert json.loads(db.execute("SELECT properties_json FROM edge WHERE relation='HAS_HERBAL_PIECE'").fetchone()[0])["Dosage_ratio"] == "0"
        assert not db.execute("PRAGMA foreign_key_check").fetchall()
        assert check_quality(db.cursor()) == dict.fromkeys(QUALITY_CHECKS, 0)
        db.execute("INSERT INTO dataset SELECT 'other',title,version_label,source_url,license_statement,attribution FROM dataset")
        for statement, expected in (
                ("UPDATE entity SET type='herb' WHERE type='tcm_term'", "invalid_endpoint_types"),
                ("DELETE FROM evidence WHERE entity_id IS NOT NULL", "missing_entity_evidence"),
                ("DELETE FROM evidence WHERE edge_id IS NOT NULL", "missing_edge_evidence"),
                ("UPDATE entity SET dataset_id='other'", "entity_source_dataset_mismatch")):
            db.execute("SAVEPOINT bad_quality")
            db.execute(statement)
            expect_failure(lambda: check_quality(db.cursor()), expected)
            db.execute("ROLLBACK TO SAVEPOINT bad_quality")
            db.execute("RELEASE SAVEPOINT bad_quality")
    docs = list(read_tsv(base / "D1_TCM_terminology.tsv"))
    assert docs[0][1]["fields"]["English_definition_description"] == "multiline\nquoted\tfield"
    assert docs[0][1]["line_end"] > docs[0][1]["line_start"]
    originals = {name: (base / name).read_bytes() for name in FILES}
    # Even internally consistent references must use the ID prefix for their table.
    for valid, wrong in ((b"TCMT00001", b"CPM00099"), (b"CPM00001", b"CHP00099"),
                         (b"CHP00001", b"TCMT00099")):
        for name, content in originals.items():
            (base / name).write_bytes(content.replace(valid, wrong))
        with closing(sqlite3.connect(":memory:")) as db:
            db.execute("PRAGMA foreign_keys=ON")
            db.executescript(DDL.read_text())
            expect_failure(lambda: import_tcm(db, base, inputs), "Invalid ID")
    for name, content in originals.items():
        (base / name).write_bytes(content)
    path = base / "D6_Chinese_herbal_pieces.tsv"
    original = path.read_bytes()
    path.write_bytes(original.replace(b"CHP00001\t", b"CHP00001\t\t"))
    expect_failure(lambda: list(read_tsv(path)), "Unexpected column count")
    path.write_bytes(original)
    path = base / "D4_CPM_CHP.tsv"
    path.write_bytes(path.read_bytes().replace(b"CHP00001", b"CHP99999"))
    with closing(sqlite3.connect(":memory:")) as db:
        db.execute("PRAGMA foreign_keys=ON")
        db.executescript(DDL.read_text())
        expect_failure(lambda: import_tcm(db, base, inputs), "Missing endpoint")


def check_sql(release, manifest):
    import psycopg2
    from psycopg2 import sql
    schema = "qihuang_" + manifest["build_id"][:24]
    with closing(psycopg2.connect(os.environ["QIHUANG_TEST_DSN"])) as db:
        with db.cursor() as c:
            c.execute("SELECT version()")
            version = c.fetchone()[0]
        db.rollback()
        if "vastbase" not in version.casefold():
            expect_failure(lambda: import_vastbase.identify(db), "not identified as Vastbase")
            db.rollback()
            assert import_vastbase.identify(db, "postgresql")["engine"] == "postgresql"
        else:
            expect_failure(lambda: import_vastbase.identify(db, "postgresql"), "not identified as PostgreSQL")
            db.rollback()
        probe = import_vastbase.probe(db)
        assert probe["status"] == "passed"
        # Fail after the entire load, just before commit: DDL/data must both disappear.
        with patch.object(import_vastbase, "verify_target", side_effect=ValueError("injected validation failure")):
            expect_failure(lambda: import_vastbase.import_release(db, release), "injected validation failure")
        with db.cursor() as c:
            c.execute("SELECT count(*) FROM pg_namespace WHERE nspname=%s", (schema,))
            assert c.fetchone()[0] == 0
        db.rollback()
        first = import_vastbase.import_release(db, release)
        second = import_vastbase.import_release(db, release)
        assert first["status"] == "imported" and second["status"] == "reused"
        assert first["verification"] == second["verification"]
        assert first["verification"]["quality"] == dict.fromkeys(QUALITY_CHECKS, 0)
        # COPY distinguishes NULL, empty string, literal backslash-N and embedded controls.
        with db.cursor() as c:
            c.execute("CREATE TEMP TABLE copy_values (value TEXT)")
            values = [(None,), ("",), ("\\N",), ("中文\n\t\r\\'",)]
            import_vastbase.copy_rows(c, "copy_values", values)
            c.execute("SELECT * FROM copy_values")
            assert c.fetchall() == values
            c.execute(sql.SQL("SET LOCAL search_path TO {}, pg_catalog").format(sql.Identifier(schema)))
            c.execute("UPDATE entity SET label='tampered' WHERE id=%s", ("bencaodian:herb:gan_cao",))
            expect_failure(lambda: import_vastbase.verify_target(c, manifest), "Target content mismatch")
        db.rollback()
        print("PASS: SQL compatibility on " + version.split(",")[0] + "; not Vastbase acceptance")


def main():
    before = hashes()
    release, manifest, _ = build()
    _, again, reused = build()
    assert reused and manifest == again
    assert manifest["counts"]["entity"] == 20374
    assert manifest["counts"]["edge"] == 179502
    assert manifest["counts"]["business_records"] == 199876
    report = json.loads((release / "report.json").read_text())
    assert report["issue_counts"] == {"repaired_extra_column": 1, "duplicate_relation": 1}
    assert report["core_issue_counts"] == {"unresolved_reference": 35, "conflicting_claim": 1}
    assert report["quality"] == dict.fromkeys(QUALITY_CHECKS, 0)
    with closing(sqlite3.connect(release / "kg.sqlite")) as db:
        validate(db, manifest)
        fields = json.loads(db.execute("SELECT attributes_json FROM entity WHERE id=?",
                            (entity_id("herbal_piece", "CHP01717"),)).fetchone()[0])
        assert fields["Pinyin_term"] == "huang qi" and fields["English_term"] == "root of Membranous Milkvetch"
        edge = "edge:" + digest([entity_id("patent_medicine", "CPM07546"), "ASSOCIATED_WITH_TERM", entity_id("tcm_term", "TCMT00784")])
        props, quality = db.execute("SELECT properties_json,quality_state FROM edge WHERE id=?", (edge,)).fetchone()
        assert quality == "consistent" and json.loads(props)["Synonyms"]
        assert db.execute("SELECT count(*) FROM evidence WHERE edge_id=?", (edge,)).fetchone()[0] == 2
        assert db.execute("SELECT count(*) FROM entity WHERE type='icd11_code' AND label<>source_key").fetchone()[0] == 0
        # Roll back a deliberate corruption of the prepared snapshot.
        db.execute("UPDATE entity SET label='tampered' WHERE id='tcm-mkg:herbal_piece:CHP01717'")
        expect_failure(lambda: validate(db, manifest), "Content mismatch")
        db.rollback()
    with tempfile.TemporaryDirectory() as temp:
        check_small_inputs(Path(temp) / "fixtures")
    if os.environ.get("QIHUANG_TEST_DSN"):
        check_sql(release, manifest)
    assert hashes() == before, "Raw inputs changed"
    print("PASS: 199876 business records, reproducibility, precise repair, multiline TSV, deduplication, "
          "conflicts, provenance, namespace separation, ID prefixes, quality gates, missing endpoints, "
          "tamper detection, raw preservation")


if __name__ == "__main__":
    main()
