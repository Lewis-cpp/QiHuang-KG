"""Small, read-only database access functions shared by the API and environment checks."""

import json
import os
import re
from contextlib import contextmanager
from pathlib import Path

import psycopg2
from neo4j import GraphDatabase
from psycopg2 import sql
from psycopg2.extras import RealDictCursor

ROOT = Path(__file__).resolve().parents[1]
TYPES = ("herb", "formula", "pattern", "text", "tcm_term", "patent_medicine",
         "herbal_piece", "icd11_code", "medicinal_property")
SAMPLE_FORMULA = "bencaodian:formula:si_jun_zi_tang"
ERROR_STATUS = {
    "entity_not_found": 404, "evidence_not_found": 404, "not_found": 404,
    "method_not_allowed": 405,
    "snapshot_changed": 409, "invalid_query": 422, "invalid_type": 422,
    "unsupported_entity_type": 422, "evidence_pointer_invalid": 500, "internal_error": 500,
    "model_http_error": 502, "model_invalid_response": 502, "model_incomplete": 502,
}


class ServiceError(RuntimeError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def config(name):
    folder = Path(os.environ.get("QIHUANG_CONFIG_DIR", ROOT / "config"))
    try:
        data = json.loads((folder / f"{name}.json").read_text())
        if not isinstance(data, dict):
            raise ValueError()
        return data
    except (OSError, ValueError):
        raise ServiceError(f"{name}_not_configured", f"{name} 配置缺失或格式不正确") from None


def application():
    settings = config("app")
    if (settings.get("database_engine") not in ("postgresql", "vastbase") or
            not re.fullmatch(r"qihuang_[a-f0-9]{24}", settings.get("schema", "")) or
            not re.fullmatch(r"[a-f0-9]{64}", settings.get("build_id", ""))):
        raise ServiceError("invalid_app_config", "数据库类型或发布批次配置无效")
    return settings


def selected(build_id):
    """The release settings, refusing a request pinned to another batch."""
    settings = application()
    if build_id is not None and build_id != settings["build_id"]:
        raise ServiceError("snapshot_changed", "数据批次已更新，请刷新后重试")
    return settings


@contextmanager
def relational(build_id=None):
    settings = selected(build_id)
    # The application uses the read-only role; the import account is reserved for scripts.
    params = config(settings["database_engine"] + "_reader")
    params["connect_timeout"] = 3
    # shortcut: one connection per request; add a pool when measured concurrency requires it.
    try:
        db = psycopg2.connect(**params)
        try:
            db.set_session(readonly=True, isolation_level="REPEATABLE READ")
            with db.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(sql.SQL("SET LOCAL search_path TO {}, pg_catalog").format(sql.Identifier(settings["schema"])))
                cursor.execute("SET LOCAL statement_timeout='3000ms'")
                cursor.execute("SELECT id FROM build")
                rows = cursor.fetchall()
                if len(rows) != 1 or rows[0]["id"] != settings["build_id"]:
                    raise ServiceError("build_mismatch", "关系数据库版本与应用配置不一致")
                yield cursor
        finally:
            db.close()
    except psycopg2.Error:
        raise ServiceError("database_unavailable", "关系数据库暂时不可用") from None


@contextmanager
def graph():
    settings = config("neo4j")
    try:
        with GraphDatabase.driver(settings["uri"], auth=(settings["user"], settings["password"]),
                                  connection_timeout=3, connection_acquisition_timeout=5,
                                  max_transaction_retry_time=0) as driver:
            driver.verify_connectivity()
            with driver.session(database=settings.get("database", "neo4j")) as session:
                yield session
    except ServiceError:
        raise
    except Exception:
        raise ServiceError("neo4j_unavailable", "图数据库暂时不可用") from None


def database_health():
    with relational() as c:
        c.execute("SELECT version() AS version")
        version = c.fetchone()["version"]
    return dict(status="ready", engine=application()["database_engine"], version=version,
                build_id=application()["build_id"])


def graph_health():
    with graph() as session:
        version = session.run("CALL dbms.components() YIELD versions RETURN versions[0] AS version").single()["version"]
        scopes = {row["scope"] for row in session.run(
            "MATCH (p:Projection {build_id:$build, complete:true}) WHERE p.scope IN ['full','bootstrap'] "
            "RETURN p.scope AS scope", build=application()["build_id"])}
    # A complete full projection (M3) takes precedence; the bootstrap sample remains the fallback.
    projection = "full" if "full" in scopes else "sample" if "bootstrap" in scopes else "not_ready"
    return dict(status="ready", version=version, projection=projection,
                build_id=application()["build_id"] if scopes else None)


def stats():
    with relational() as c:
        c.execute("SELECT type,count(*) AS count FROM entity GROUP BY type ORDER BY type")
        types = dict((r["type"], r["count"]) for r in c.fetchall())
        c.execute("SELECT relation,count(*) AS count FROM edge GROUP BY relation ORDER BY relation")
        relations = dict((r["relation"], r["count"]) for r in c.fetchall())
        c.execute("SELECT count(*) AS count FROM evidence")
        evidence = c.fetchone()["count"]
        c.execute("SELECT id,title,version_label FROM dataset ORDER BY id")
        datasets = c.fetchall()
        c.execute("SELECT id FROM build")
        build = c.fetchone()["id"]
    return dict(build_id=build, entities=sum(types.values()), edges=sum(relations.values()),
                business_records=sum(types.values()) + sum(relations.values()), evidence=evidence,
                entity_types=types, relations=relations, datasets=datasets)


def sample_source():
    with relational() as c:
        c.execute("SELECT id,source_id,relation,target_id FROM edge WHERE source_id=%s "
                  "AND relation IN ('CONTAINS','ASSOCIATED_WITH_PATTERN') ORDER BY id", (SAMPLE_FORMULA,))
        edges = c.fetchall()
        ids = [SAMPLE_FORMULA] + [e["target_id"] for e in edges]
        c.execute("SELECT id,label,type FROM entity WHERE id=ANY(%s) ORDER BY id", (ids,))
        nodes = c.fetchall()
        for edge in edges:
            c.execute("SELECT id FROM evidence WHERE edge_id=%s ORDER BY id", (edge["id"],))
            edge["evidence_ids"] = [r["id"] for r in c.fetchall()]
    return dict(nodes=nodes, edges=edges, build_id=application()["build_id"], scope="bootstrap")


def sample_graph():
    build = application()["build_id"]
    with graph() as session:
        marker = session.run("MATCH (p:Projection {scope:'bootstrap',build_id:$build,complete:true}) RETURN p", build=build).single()
        if not marker:
            raise ServiceError("projection_not_ready", "当前批次的样例图尚未构建")
        nodes = session.run("MATCH (n:Entity {build_id:$build,scope:'bootstrap'}) "
                            "RETURN n.id AS id,n.label AS label,n.type AS type ORDER BY id", build=build).data()
        edges = session.run("MATCH (s:Entity {build_id:$build})-[r:LINK {build_id:$build,scope:'bootstrap'}]->(t:Entity) "
                            "RETURN r.id AS id,s.id AS source_id,t.id AS target_id,r.relation AS relation," 
                            "r.evidence_ids AS evidence_ids ORDER BY id", build=build).data()
    return dict(nodes=nodes, edges=edges, build_id=build, scope="bootstrap")
