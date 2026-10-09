"""Reuse PostgreSQL setup and provision private Neo4j/application configuration."""

import json
import secrets

from setup_postgres import ROOT, main as setup_postgres, private_write


def main():
    setup_postgres()
    config = ROOT / "config/neo4j.json"
    auth = ROOT / "config/neo4j.env"
    if config.exists():
        settings = json.loads(config.read_text())
        if settings.get("uri") != "bolt://127.0.0.1:17687" or settings.get("user") != "neo4j":
            raise ValueError("Existing Neo4j config differs from Compose; configure it manually")
        password = settings["password"]
    elif auth.exists():
        username, password = auth.read_text().strip().split("/", 1)
        if username != "NEO4J_AUTH=neo4j":
            raise ValueError("Unexpected Neo4j user in existing secret")
    else:
        password = secrets.token_urlsafe(32)
    if not isinstance(password, str) or not password.strip():
        raise ValueError("Neo4j password is empty")
    value = "NEO4J_AUTH=neo4j/" + password
    if auth.exists() and auth.read_text().strip() != value:
        raise ValueError("Neo4j credentials differ; refusing to rotate them")
    if not config.exists():
        private_write(config, json.dumps(dict(uri="bolt://127.0.0.1:17687", user="neo4j",
                                             password=password, database="neo4j"), indent=2) + "\n")
    config.chmod(0o600)
    private_write(auth, value + "\n")
    app = ROOT / "config/app.json"
    if not app.exists():
        report_path = ROOT / "var/postgresql-report.json"
        if not report_path.exists():
            print("Database credentials ready. Start Compose, import PostgreSQL data, then rerun to select the application build.")
            return
        report = json.loads(report_path.read_text())
        result = report.get("import_result") or {}
        if report["status"] != "passed" or result.get("status") not in ("imported", "reused"):
            raise ValueError("Import PostgreSQL data successfully before creating application config")
        private_write(app, json.dumps(dict(database_engine="postgresql", schema=result["schema"],
                                          build_id=result["build_id"]), indent=2) + "\n")
    print("Ready: Neo4j private credentials and application build selection; model remains separately configured")


if __name__ == "__main__":
    main()
