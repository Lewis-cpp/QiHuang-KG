"""Run with python3 tests/test_import_core.py; no third-party dependencies."""

import hashlib
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from audit_core_data import check_schema
from import_core import CURATED, RAW, ImportFailure, build, canonical, digest, normalize, pointer


def raw_hashes():
    return {str(p.relative_to(RAW)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in RAW.iterdir() if p.is_file()}


def main():
    before = raw_hashes()
    check_schema()
    assert normalize("  ＧＡＮ CAO  ") == "gan cao"
    assert pointer({"a/b": {"~": ["yes"]}}, "/a~1b/~0/0") == "yes"
    for bad in ("/a~2", "/01", "/-1"):
        try:
            pointer([1, 2], bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"Accepted malformed pointer: {bad}")

    with tempfile.TemporaryDirectory() as temp:
        base = Path(temp)
        release, manifest, reused = build(releases=base / "releases", processed=base / "processed")
        assert not reused
        assert manifest["counts"]["entity"] == 599
        assert manifest["counts"]["edge"] == 1286
        assert manifest["counts"]["source_record"] == 2076
        assert manifest["counts"]["evidence"] == 3149
        assert manifest["issue_counts"] == {"unresolved_reference": 35, "conflicting_claim": 1, "corrected_reference": 2}
        original_bytes = (release / "kg.sqlite").read_bytes()
        original_mtime = (release / "kg.sqlite").stat().st_mtime_ns
        again, repeated, reused = build(releases=base / "releases", processed=base / "processed")
        assert reused and again == release and repeated == manifest
        assert (release / "kg.sqlite").stat().st_mtime_ns == original_mtime
        assert (release / "kg.sqlite").read_bytes() == original_bytes
        _, independent, _ = build(releases=base / "second", processed=base / "processed")
        assert independent["build_id"] == manifest["build_id"]
        assert independent["content_sha256"] == manifest["content_sha256"]

        with closing(sqlite3.connect(release / "kg.sqlite")) as db:
            assert len(db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()) == 7
            herbs = db.execute("SELECT h.label,json_extract(e.properties_json,'$.dosage_raw') FROM edge e "
                               "JOIN entity h ON h.id=e.target_id WHERE source_id=? AND relation='CONTAINS' "
                               "ORDER BY json_extract(e.properties_json,'$.position')",
                               ("bencaodian:formula:si_jun_zi_tang",)).fetchall()
            assert herbs == [("人参", "9g"), ("白术", "9g"), ("茯苓", "9g"), ("甘草", "6g")]
            edge_id, props, quality = db.execute("SELECT id,properties_json,quality_state FROM edge "
                                                "WHERE source_id=? AND target_id=?",
                                                ("bencaodian:formula:zhu_ling_tang", "bencaodian:herb:ze_xie")).fetchone()
            assert edge_id == "edge:" + digest(["bencaodian:formula:zhu_ling_tang", "CONTAINS", "bencaodian:herb:ze_xie"])
            assert quality == "conflicting" and json.loads(props)["role"] is None
            assert json.loads(props)["dosage_raw"] == "9g"
            assert db.execute("SELECT count(*) FROM evidence WHERE edge_id=?", (edge_id,)).fetchone()[0] == 2
            assert {x[0] for x in db.execute("SELECT target_id FROM edge WHERE source_id=? AND relation='CITED_IN'",
                                           ("bencaodian:formula:xiao_jian_zhong_tang",))} == {
                                               "bencaodian:text:shang_han_lun", "bencaodian:text:jin_gui_yao_lue"}
            for key in ("qiang_huo", "mei_gui_hua"):
                eid = "bencaodian:herb:" + key
                assert db.execute("SELECT 1 FROM evidence WHERE entity_id=? AND kind='source_quote'", (eid,)).fetchone()
                assert db.execute("SELECT 1 FROM evidence WHERE entity_id=? AND kind='bibliographic'", (eid,)).fetchone()
            assert db.execute("SELECT count(*) FROM entity WHERE json_type(attributes_json,'$.composition') IS NOT NULL").fetchone()[0] == 0
            # 十枣汤: the source key da_ji (大蓟) is corrected to da_ji_2 (大戟); the raw values stay traceable.
            herbs = db.execute("SELECT h.id,h.label,e.properties_json,e.id FROM edge e JOIN entity h ON h.id=e.target_id "
                               "WHERE e.source_id='bencaodian:formula:shi_zao_tang' AND e.relation='CONTAINS'").fetchall()
            assert sorted(h[1] for h in herbs) == sorted(["芫花", "甘遂", "大戟", "大枣"])
            corrected = next(h for h in herbs if h[0] == "bencaodian:herb:da_ji_2")
            fixes = json.loads(corrected[2])["corrections"]
            assert {(f["field_path"], f["raw_value"], f["corrected_value"]) for f in fixes} == {
                ("/composition/2/herb_key", "da_ji", "da_ji_2"), ("/herb", "da_ji", "da_ji_2")}
            assert all("corrections" not in json.loads(h[2]) for h in herbs if h is not corrected)
            assert not db.execute("SELECT 1 FROM edge WHERE target_id='bencaodian:herb:da_ji'").fetchone()
            assert db.execute("SELECT count(*) FROM evidence WHERE edge_id=? AND kind='source_quote'",
                              (corrected[3],)).fetchone()[0] == 3
            # A two-hop herb -> formula -> pattern query uses actual, evidenced edges.
            assert db.execute("SELECT 1 FROM edge a JOIN edge b ON a.source_id=b.source_id "
                              "WHERE a.target_id=? AND a.relation='CONTAINS' "
                              "AND b.relation='ASSOCIATED_WITH_PATTERN' AND b.target_id=?",
                              ("bencaodian:herb:ren_shen", "bencaodian:pattern:pi_qi_xu")).fetchone()

        raw = base / "raw"
        shutil.copytree(RAW, raw)
        formulas = json.loads((raw / "formulas.json").read_text())
        relationships = json.loads((raw / "relationships.json").read_text())
        # Actual input failures must be located and must not publish any new directory.
        for name, mutate, expected in (
            ("formulas.json", lambda rows: rows.append(rows[0]), "duplicate_source_key"),
            ("formulas.json", lambda rows: rows[0].update(name_zh="　 "), "missing_label"),
            ("formulas.json", lambda rows: rows[0]["composition"][0].update(herb_key="missing"), "missing_endpoint"),
            ("relationships.json", lambda rows: rows.update(unmapped=[]), "unknown_relation_mapping"),
            ("formulas.json", lambda rows: rows[0]["verification"].update(status="new-status"), "warning_baseline_changed"),
        ):
            source = formulas if name == "formulas.json" else relationships
            rows = json.loads(canonical(source))
            mutate(rows)
            (raw / name).write_text(canonical(rows))
            try:
                build(raw=raw, releases=base / "releases", processed=base / "processed")
            except ImportFailure as error:
                assert error.issue["code"] == expected, error.issue
                assert error.issue["filename"] and isinstance(error.issue["field_path"], str)
            else:
                raise AssertionError(f"Accepted bad input: {expected}")
            (raw / name).write_bytes((RAW / name).read_bytes())
            assert list((base / "releases").iterdir()) == [release]
            assert (release / "kg.sqlite").read_bytes() == original_bytes

        # A correction must still match the source and quote it exactly; otherwise the build stops.
        curated = base / "curated"
        shutil.copytree(CURATED, curated)
        corrections = json.loads((CURATED / "corrections.json").read_text())
        for mutate, expected in (
            (lambda c: c[0].update(formula="si_jun_zi_tang"), "stale_correction"),
            (lambda c: c[0]["basis"][0].update(text="大蓟"), "correction_basis_mismatch"),
        ):
            rows = json.loads(canonical(corrections))
            mutate(rows["corrections"])
            (curated / "corrections.json").write_text(canonical(rows))
            try:
                build(curated=curated, releases=base / "releases", processed=base / "processed")
            except ImportFailure as error:
                assert error.issue["code"] == expected, error.issue
            else:
                raise AssertionError(f"Accepted bad correction: {expected}")
            assert list((base / "releases").iterdir()) == [release]

        # A duplicate relationship adds neither an edge nor redundant evidence.
        relationships["herb_in_formula"].append(relationships["herb_in_formula"][0])
        (raw / "relationships.json").write_text(canonical(relationships))
        _, dedup, _ = build(raw=raw, releases=base / "duplicates", processed=base / "processed")
        assert dedup["counts"] == manifest["counts"]
        (raw / "relationships.json").write_bytes((RAW / "relationships.json").read_bytes())

        # Missing corroboration preserves the supplied value and marks the missing source.
        formulas[0]["composition"][0].pop("dosage")
        (raw / "formulas.json").write_text(canonical(formulas))
        missing_release, _, _ = build(raw=raw, releases=base / "missing", processed=base / "processed")
        with closing(sqlite3.connect(missing_release / "kg.sqlite")) as db:
            props, quality = db.execute("SELECT properties_json,quality_state FROM edge WHERE source_id=? AND target_id=?",
                                       ("bencaodian:formula:si_jun_zi_tang", "bencaodian:herb:ren_shen")).fetchone()
            assert quality == "consistent" and json.loads(props)["dosage_raw"] == "9g"
            assert len(json.loads(props)["missing_claim_fields"]) == 1

        # The command-line failure path emits a machine-readable report and a nonzero exit.
        (raw / "formulas.json").write_text("{")
        result = subprocess.run([sys.executable, str(ROOT / "scripts/import_core.py"), "--raw-dir", str(raw),
                                 "--releases-dir", str(base / "releases"), "--processed-dir", str(base / "processed")],
                                capture_output=True, text=True)
        assert result.returncode == 1
        failure = json.loads((base / "processed/last-failure.json").read_text())
        assert failure["issues"][0]["code"] == "invalid_json"
        assert list((base / "releases").iterdir()) == [release]

        # An existing but altered snapshot must fail validation, never be silently reused.
        with closing(sqlite3.connect(release / "kg.sqlite")) as db:
            db.execute("UPDATE entity SET label='tampered' WHERE id='bencaodian:herb:gan_cao'")
            db.commit()
        try:
            build(releases=base / "releases", processed=base / "processed")
        except ValueError as error:
            assert "Snapshot content mismatch" in str(error)
        else:
            raise AssertionError("Reused a tampered snapshot")
    assert raw_hashes() == before, "Raw source files changed"
    print("PASS: real-data import, repeatability, provenance, sample queries, conflict/missing values, "
          "deduplication, failure isolation, CLI errors, tamper detection, and raw-file preservation")


if __name__ == "__main__":
    main()
