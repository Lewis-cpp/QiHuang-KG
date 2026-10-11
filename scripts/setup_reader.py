"""Create or refresh the application's read-only role and grant it the selected release schema."""

import argparse
import json
import re
import sys
from contextlib import closing
from pathlib import Path

from import_core import ROOT, require
from import_vastbase import connection

WRITE_PRIVILEGES = "INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER"


def reader_settings(path, admin):
    require(path.is_file(), f"Missing reader config: {path.name}")
    reader = json.loads(path.read_text())
    require(isinstance(reader, dict) and re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", str(reader.get("user", ""))),
            "Reader config requires a lowercase role name")
    require(isinstance(reader.get("password"), str) and reader["password"].strip() and
            reader["password"] != "REPLACE_IN_PRIVATE_CONFIG", "Reader config requires a password")
    require(reader["user"] != admin.get("user"), "Reader must be a different role from the import account")
    return reader


def grant(db, reader, schemas):
    """One transaction: the role can log in, read the given schemas and write nothing."""
    from psycopg2 import sql
    role = sql.Identifier(reader["user"])
    with db.cursor() as c:
        c.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (reader["user"],))
        verb = "ALTER" if c.fetchone() else "CREATE"
        c.execute(sql.SQL(verb + " ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD %s").format(role),
                  (reader["password"],))
        c.execute(sql.SQL("ALTER ROLE {} SET default_transaction_read_only = on").format(role))
        c.execute("SELECT current_database()")
        c.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(sql.Identifier(c.fetchone()[0]), role))
        tables = 0
        for schema in schemas:
            c.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema=%s AND table_name='build'",
                      (schema,))
            require(c.fetchone()[0] == 1, f"Not a release schema: {schema}")
            c.execute(sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(sql.Identifier(schema), role))
            c.execute(sql.SQL("GRANT SELECT ON ALL TABLES IN SCHEMA {} TO {}").format(sql.Identifier(schema), role))
            c.execute("SELECT c.relname, c.relkind FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                      "WHERE n.nspname=%s AND c.relkind IN ('r','v') ORDER BY c.relname", (schema,))
            for name, _ in c.fetchall():
                qualified = sql.Identifier(schema, name).as_string(c)
                c.execute("SELECT has_table_privilege(%s,%s,'SELECT'), has_table_privilege(%s,%s,%s)",
                          (reader["user"], qualified, reader["user"], qualified, WRITE_PRIVILEGES))
                readable, writable = c.fetchone()
                require(readable and not writable, f"Unexpected privileges on {schema}.{name}")
                tables += 1
            c.execute("SELECT has_schema_privilege(%s,%s,'CREATE')", (reader["user"], schema))
            require(not c.fetchone()[0], f"Reader can create objects in {schema}")
        c.execute("SELECT has_database_privilege(%s,current_database(),'CREATE'), rolsuper, rolcreaterole, "
                  "rolcreatedb FROM pg_roles WHERE rolname=%s", (reader["user"], reader["user"]))
        require(not any(c.fetchone()), "Reader has administrative privileges")
    db.commit()
    return dict(role=reader["user"], action=verb.lower(), schemas=schemas, relations=tables,
                default_transaction_read_only="on")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", choices=("vastbase", "postgresql"), default="postgresql")
    parser.add_argument("--schema", action="append", help="Release schema; default: config/app.json. Repeatable")
    args = parser.parse_args()
    admin_path = ROOT / f"config/{args.engine}.json"
    admin = json.loads(admin_path.read_text()) if admin_path.is_file() else {}
    reader = reader_settings(ROOT / f"config/{args.engine}_reader.json", admin)
    schemas = args.schema or [json.loads((ROOT / "config/app.json").read_text())["schema"]]
    for schema in schemas:
        require(re.fullmatch(r"qihuang_[a-f0-9]{24}", schema), "Invalid release schema name")
    with closing(connection(admin_path, args.engine)) as db:
        result = grant(db, reader, schemas)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except ValueError as error:
        sys.exit(f"Blocked: {error}")
