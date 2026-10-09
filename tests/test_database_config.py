"""Check private credential reuse and isolation between development/final targets."""

import json
import os
import sys
import tempfile
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import import_vastbase
import setup_postgres
import setup_services


def main():
    with tempfile.TemporaryDirectory() as temp:
        base = Path(temp)
        with patch.object(setup_postgres, "ROOT", base), redirect_stdout(StringIO()):
            setup_postgres.main()
            config = base / "config/postgresql.json"
            secret = base / "var/postgres-password"
            before = (config.read_bytes(), secret.read_bytes())
            setup_postgres.main()
            assert (config.read_bytes(), secret.read_bytes()) == before
            assert config.stat().st_mode & 0o777 == secret.stat().st_mode & 0o777 == 0o600
            settings = json.loads(config.read_text())
            assert settings["password"] == secret.read_text().strip()
            secret.write_text("different-password\n")
            try:
                setup_postgres.main()
            except ValueError as error:
                assert "differ" in str(error)
            else:
                raise AssertionError("Changed existing mismatched credentials")
            assert config.read_bytes() == before[0]
            assert secret.read_text() == "different-password\n"
        with patch.dict(os.environ, {"POSTGRES_DSN": "development", "VASTBASE_DSN": "final"}, clear=True):
            with patch("psycopg2.connect") as connect:
                import_vastbase.connection(config, "postgresql")
                connect.assert_called_once_with("development", connect_timeout=10)
            with patch("psycopg2.connect") as connect:
                import_vastbase.connection(config)
                connect.assert_called_once_with("final", connect_timeout=10)
        with patch.dict(os.environ, {"VASTBASE_DSN": "final"}, clear=True):
            with patch("psycopg2.connect") as connect:
                import_vastbase.connection(config, "postgresql")
                connect.assert_called_once_with(**settings)
        # The final-target gate must remain strict even after adding development mode.
        with patch("psycopg2.connect") as connect:
            db = connect.return_value
            cursor = db.cursor.return_value.__enter__.return_value
            cursor.fetchone.return_value = ("PostgreSQL 18.6",)
            try:
                import_vastbase.identify(db)
            except ValueError as error:
                assert "not identified as Vastbase" in str(error)
            else:
                raise AssertionError("PostgreSQL passed the Vastbase identity gate")
    with tempfile.TemporaryDirectory() as temp:
        base = Path(temp)
        with patch.object(setup_postgres, "ROOT", base), patch.object(setup_services, "ROOT", base), redirect_stdout(StringIO()):
            setup_services.main()  # First boot must prepare Compose before the SQL import exists.
            config = base / "config/neo4j.json"
            auth = base / "config/neo4j.env"
            app = base / "config/app.json"
            before = (config.read_bytes(), auth.read_bytes())
            assert not app.exists()
            setup_services.main()
            assert (config.read_bytes(), auth.read_bytes()) == before
            assert config.stat().st_mode & 0o777 == auth.stat().st_mode & 0o777 == 0o600
            report = {"status": "passed", "import_result": {
                "status": "imported", "schema": "qihuang_" + "a" * 24, "build_id": "a" * 64}}
            (base / "var/postgresql-report.json").write_text(json.dumps(report))
            setup_services.main()
            assert json.loads(app.read_text())["build_id"] == "a" * 64
            assert app.stat().st_mode & 0o777 == 0o600
            auth.write_text("NEO4J_AUTH=neo4j/different-password\n")
            try:
                setup_services.main()
            except ValueError as error:
                assert "differ" in str(error)
            else:
                raise AssertionError("Changed mismatched Neo4j credentials")
            assert config.read_bytes() == before[0]
    print("PASS: private credential permissions/reuse, first boot, mismatch protection, engine-specific connections, Vastbase gate")


if __name__ == "__main__":
    main()
