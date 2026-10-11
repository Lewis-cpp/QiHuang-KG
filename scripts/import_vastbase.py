"""Probe PostgreSQL or Vastbase and atomically import the same prepared release."""

import argparse
import hashlib
import io
import json
import os
import platform
import shutil
import sqlite3
import sys
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from import_core import ROOT, TABLES, canonical, digest, require, write_json
from prepare_data import DDL, check_quality, table_hash, validate

VIEWS = ROOT / "docs/schema-views.sql"


def copy_rows(cursor, table, rows):
    from psycopg2 import sql
    def escape(value):
        if value is None:
            return "\\N"
        return str(value).replace("\\", "\\\\").replace("\t", "\\t").replace("\n", "\\n").replace("\r", "\\r")
    stream = io.StringIO()
    for row in rows:
        stream.write("\t".join(escape(v) for v in row) + "\n")
    stream.seek(0)
    cursor.copy_expert(sql.SQL("COPY {} FROM STDIN").format(sql.Identifier(table)), stream)


def connection(config, engine="vastbase"):
    import psycopg2
    dsn_key = "POSTGRES_DSN" if engine == "postgresql" else "VASTBASE_DSN"
    if os.environ.get(dsn_key):
        return psycopg2.connect(os.environ[dsn_key], connect_timeout=10)
    require(config.is_file(), f"No connection: supply --config or {dsn_key}")
    settings = json.loads(config.read_text())
    require(isinstance(settings, dict) and {"host", "port", "dbname", "user"} <= settings.keys(),
            "Connection config requires host, port, dbname, user")
    require(settings.get("password") != "REPLACE_IN_PRIVATE_CONFIG", "Replace the example password in the private config")
    allowed = {"host", "port", "dbname", "user", "password", "connect_timeout", "sslmode", "sslrootcert", "sslcert", "sslkey"}
    require(not settings.keys() - allowed, "Unknown connection config keys")
    return psycopg2.connect(**({"connect_timeout": 10} | settings))


def identify(db, engine="vastbase"):
    """The explicit engine must match; development imports never imply Vastbase acceptance."""
    require(engine in ("vastbase", "postgresql"), "Unsupported database engine")
    with db.cursor() as c:
        c.execute("SELECT version()")
        version = c.fetchone()[0]
        if engine == "vastbase":
            require("vastbase" in version.casefold(), "Server is not identified as Vastbase; import refused")
        else:
            require(version.startswith("PostgreSQL ") and "vastbase" not in version.casefold(),
                    "Server is not identified as PostgreSQL; import refused")
        c.execute("SELECT setting FROM pg_settings WHERE name='sql_compatibility'")
        mode = c.fetchone()
        compatibility = mode[0] if mode else "native"
        require(compatibility.upper() in ("PG", "NATIVE"), "Use a PG-compatible database for this schema")
        c.execute("SHOW server_encoding")
        encoding = c.fetchone()[0]
        require(encoding.upper().replace("-", "") == "UTF8", "Database must use UTF8")
    db.rollback()
    return dict(engine=engine, version=version, compatibility=compatibility, encoding=encoding)


def probe(db):
    """All probe objects and writes are rolled back, including DDL."""
    from psycopg2 import IntegrityError, sql
    name = "qihuang_probe_" + uuid.uuid4().hex[:16]
    try:
        with db.cursor() as c:
            c.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(name)))
            c.execute(sql.SQL("SET LOCAL search_path TO {}, pg_catalog").format(sql.Identifier(name)))
            c.execute(DDL.read_text())
            c.execute(VIEWS.read_text())
            c.execute("CREATE TABLE probe_parent (id INTEGER PRIMARY KEY, label TEXT NOT NULL UNIQUE, payload TEXT NOT NULL)")
            c.execute("CREATE TABLE probe_child (id INTEGER PRIMARY KEY, parent_id INTEGER REFERENCES probe_parent(id))")
            payload = canonical({"中文": "黄芪", "quote": "'\\\n\t", "empty": "", "null": None})
            label = "黄芪'参数; --"
            c.execute("INSERT INTO probe_parent VALUES (%s,%s,%s)", (0, label, payload))
            c.execute("SELECT label,payload FROM probe_parent WHERE id=%s", (0,))
            require(c.fetchone() == (label, payload), "Unicode/parameter/text roundtrip failed")
            copy_rows(c, "probe_parent", ((i, f"药物{i}", payload) for i in range(1, 101)))
            c.execute("INSERT INTO probe_child VALUES (1,0)")
            for statement, params in (
                    ("INSERT INTO probe_parent VALUES (%s,%s,%s)", (0, "duplicate", payload)),
                    ("INSERT INTO probe_parent VALUES (%s,%s,%s)", (102, label, payload)),
                    ("INSERT INTO probe_child VALUES (%s,%s)", (2, 999))):
                c.execute("SAVEPOINT invalid_row")
                try:
                    c.execute(statement, params)
                except IntegrityError:
                    c.execute("ROLLBACK TO SAVEPOINT invalid_row")
                else:
                    raise ValueError("Expected unique/FK constraint was not enforced")
            c.execute("SAVEPOINT rollback_row")
            c.execute("INSERT INTO probe_child VALUES (3,0)")
            c.execute("ROLLBACK TO SAVEPOINT rollback_row")
            c.execute("SELECT count(*) FROM probe_child")
            require(c.fetchone()[0] == 1, "Savepoint rollback failed")
            c.execute("SELECT id FROM probe_parent ORDER BY id LIMIT %s OFFSET %s", (2, 1))
            require(c.fetchall() == [(1,), (2,)], "Pagination failed")
            c.execute("SET LOCAL enable_seqscan=off")
            c.execute("EXPLAIN SELECT * FROM probe_parent WHERE id=50")
            plan = [r[0] for r in c.fetchall()]
            require(any("index" in line.casefold() for line in plan), "Index not used in probe plan")
        db.rollback()
        with db.cursor() as c:
            c.execute("SELECT count(*) FROM pg_namespace WHERE nspname=%s", (name,))
            require(c.fetchone()[0] == 0, "DDL rollback failed")
        db.rollback()
        return dict(status="passed", checks=["target_ddl", "business_views", "unicode", "parameters", "text_json", "copy_batch",
                    "unique", "foreign_key", "savepoint_rollback", "ddl_rollback", "pagination", "index_plan"], plan=plan)
    finally:
        db.rollback()


def verify_target(c, manifest):
    counts, hashes = {}, {}
    for table in TABLES:
        c.execute(f"SELECT * FROM {table}")
        rows = c.fetchall()
        counts[table] = len(rows)
        hashes[table] = table_hash(rows)
        require(counts[table] == manifest["counts"][table], f"Target count mismatch: {table}")
        require(hashes[table] == manifest["table_sha256"][table], f"Target content mismatch: {table}")
    quality = check_quality(c)
    c.execute("SELECT * FROM build")
    saved = c.fetchall()
    require(len(saved) == 1 and saved[0][:4] == (manifest["build_id"], 2, manifest["transform_version"],
            manifest["created_at"]) and json.loads(saved[0][4]) == manifest, "Target build mismatch")
    c.execute("SELECT s.dataset_id,count(*) FROM edge e JOIN entity s ON s.id=e.source_id GROUP BY s.dataset_id")
    edges = dict(c.fetchall())
    c.execute("SELECT dataset_id,count(*) FROM entity GROUP BY dataset_id")
    entities = dict(c.fetchall())
    require(edges == manifest["counts"]["edges_by_dataset"] and
            entities == manifest["counts"]["entities_by_dataset"], "Dataset count mismatch")
    c.execute("SELECT h.label,e.properties_json FROM edge e JOIN entity h ON h.id=e.target_id "
              "WHERE e.source_id=%s AND e.relation='CONTAINS'", ("bencaodian:formula:si_jun_zi_tang",))
    composition = sorted(((r[0], json.loads(r[1])) for r in c.fetchall()), key=lambda r: r[1]["position"])
    require([(n, p["dosage_raw"]) for n, p in composition] ==
            [("人参", "9g"), ("白术", "9g"), ("茯苓", "9g"), ("甘草", "6g")], "Composition sample mismatch")
    return dict(counts=counts, table_sha256=hashes, quality=quality,
                business_records=counts["entity"] + counts["edge"],
                entities_by_dataset=entities, edges_by_dataset=edges, sample_composition=composition)


def verify_views(c, manifest):
    c.execute("SELECT herb_label,dosage_raw,role,position,quality_state FROM v_formula_composition "
              "WHERE formula_id=%s ORDER BY position", ("bencaodian:formula:si_jun_zi_tang",))
    composition = [tuple(r) for r in c.fetchall()]
    require(composition == [("人参", "9g", "jun", 0, "consistent"), ("白术", "9g", "chen", 1, "consistent"),
                            ("茯苓", "9g", "zuo", 2, "consistent"), ("甘草", "6g", "shi", 3, "consistent")],
            "Composition view sample mismatch")
    c.execute("SELECT count(*) FROM v_formula_composition")
    rows = c.fetchone()[0]
    c.execute("SELECT direction,sum(count) FROM v_entity_relation_summary GROUP BY direction ORDER BY direction")
    totals = dict((direction, int(total)) for direction, total in c.fetchall())
    edges = manifest["counts"]["edge"]
    require(totals == {"in": edges, "out": edges}, "Relation summary view does not cover every edge")
    return dict(v_formula_composition=rows, v_entity_relation_summary=totals)


def import_release(db, release):
    from psycopg2 import sql
    manifest = json.loads((release / "manifest.json").read_text())
    require(manifest["schema_sha256"] == hashlib.sha256(DDL.read_bytes()).hexdigest(), "DDL differs from release")
    require(manifest["report_sha256"] == digest(json.loads((release / "report.json").read_text())), "Report hash mismatch")
    schema = "qihuang_" + manifest["build_id"][:24]
    with closing(sqlite3.connect((release / "kg.sqlite").as_uri() + "?mode=ro", uri=True)) as stage:
        validate(stage, manifest)
        try:
            with db.cursor() as c:
                c.execute("SELECT count(*) FROM pg_namespace WHERE nspname=%s", (schema,))
                reused = bool(c.fetchone()[0])
                if not reused:
                    c.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
                c.execute(sql.SQL("SET LOCAL search_path TO {}, pg_catalog").format(sql.Identifier(schema)))
                if not reused:
                    c.execute(DDL.read_text())
                    for table in (*TABLES, "build"):
                        copy_rows(c, table, stage.execute(f"SELECT * FROM {table}"))
                # Block concurrent writes until the verified transaction is committed.
                c.execute("LOCK TABLE build,dataset,source_record,entity,alias,edge,evidence IN SHARE MODE")
                result = verify_target(c, manifest)
                # Views are replaceable, so a reused release also gets the current ones. Replacing a view locks out
                # its readers until commit and a reused release may be live: do it last so the lock covers only the
                # view check, and give up before readers queued behind it reach their 3 s statement timeout.
                c.execute("SET LOCAL lock_timeout = '2s'")
                c.execute(VIEWS.read_text())
                result["views"] = verify_views(c, manifest)
            db.commit()
        except Exception:
            db.rollback()
            raise
    return dict(status="reused" if reused else "imported", schema=schema,
                build_id=manifest["build_id"], verification=result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", choices=("vastbase", "postgresql"), default="vastbase")
    parser.add_argument("--config", type=Path, help="Default: config/<engine>.json")
    parser.add_argument("--release", type=Path, help="Prepared directory; omit to run environment verification only")
    parser.add_argument("--report", type=Path, help="Default: var/<engine>-report.json")
    args = parser.parse_args()
    args.config = args.config or ROOT / f"config/{args.engine}.json"
    args.report = args.report or ROOT / f"var/{args.engine}-report.json"
    report = dict(status="not_verified", checked_at=datetime.now(timezone.utc).isoformat(),
                  engine=args.engine, purpose="development" if args.engine == "postgresql" else "final_target",
                  local=dict(python=platform.python_version(), platform=platform.platform(),
                             disk_free_bytes=shutil.disk_usage(ROOT).free), database=None, vastbase=None, import_result=None)
    try:
        import psycopg2
        report["driver"] = dict(name="psycopg2", version=psycopg2.__version__)
        with closing(connection(args.config, args.engine)) as db:
            db.set_client_encoding("UTF8")
            report["database"] = identify(db, args.engine)
            if args.engine == "vastbase":
                report["vastbase"] = report["database"]
            report["probe"] = probe(db)
            if args.release:
                report["import_result"] = import_release(db, args.release.resolve())
            report["status"] = "passed"
    except Exception as error:
        report["status"] = "blocked" if isinstance(error, (ValueError, ImportError)) else "failed"
        # Connection exceptions may embed DSNs or passwords: do not echo them.
        report["error"] = (str(error) if isinstance(error, (ValueError, ImportError)) else
                           f"{type(error).__name__}; SQLSTATE={getattr(error, 'pgcode', None)}")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    write_json(args.report, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
