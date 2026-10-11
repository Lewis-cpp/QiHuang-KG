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
CONNECT_KEYS = ("host", "port", "dbname", "user", "password", "connect_timeout", "sslmode", "sslrootcert",
                "sslcert", "sslkey")


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
    """One transaction: the role can log in and read the given schemas, and every other way to write is removed."""
    from psycopg2 import sql
    name = reader["user"]
    role = sql.Identifier(name)
    hardened = []
    with db.cursor() as c:
        c.execute("SELECT current_database()")
        database = sql.Identifier(c.fetchone()[0])
        c.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (name,))
        verb = "ALTER" if c.fetchone() else "CREATE"
        c.execute(sql.SQL(verb + " ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD %s").format(role),
                  (reader["password"],))
        # An existing role may carry attributes this script never set; clear those the server reports.
        c.execute("SELECT * FROM pg_roles WHERE rolname=%s", (name,))
        attributes = dict(zip((d[0] for d in c.description), c.fetchone()))
        for column, option in (("rolreplication", "NOREPLICATION"), ("rolbypassrls", "NOBYPASSRLS")):
            if attributes.get(column):
                c.execute(sql.SQL("ALTER ROLE {} " + option).format(role))
                hardened.append(f"ALTER ROLE {name} {option}")
        # Membership allows SET ROLE to another account even when its privileges are not inherited. PostgreSQL 16
        # keeps one grant per grantor and a plain REVOKE removes only the current user's, so name each grantor.
        c.execute("SHOW server_version_num")
        per_grantor = int(c.fetchone()[0]) >= 160000
        memberships = ("SELECT g.rolname, r.rolname FROM pg_auth_members m JOIN pg_roles g ON g.oid=m.roleid "
                       "JOIN pg_roles u ON u.oid=m.member LEFT JOIN pg_roles r ON r.oid=m.grantor "
                       "WHERE u.rolname=%s ORDER BY g.rolname, r.rolname")
        c.execute(memberships, (name,))
        for granted, grantor in c.fetchall():
            if per_grantor:
                c.execute(sql.SQL("REVOKE {} FROM {} GRANTED BY {}").format(
                    sql.Identifier(granted), role, sql.Identifier(grantor)))
                hardened.append(f"REVOKE {granted} FROM {name} GRANTED BY {grantor}")
            else:
                c.execute(sql.SQL("REVOKE {} FROM {}").format(sql.Identifier(granted), role))
                hardened.append(f"REVOKE {granted} FROM {name}")
        # REVOKE only warns when it removes nothing, so check the result.
        c.execute(memberships, (name,))
        remaining = sorted({granted for granted, _ in c.fetchall()})
        require(not remaining, f"Reader is still a member of {remaining}; revoke it as a superuser")
        # A per-database setting would override the role-wide read-only default.
        c.execute(sql.SQL("ALTER ROLE {} IN DATABASE {} RESET ALL").format(role, database))
        c.execute(sql.SQL("ALTER ROLE {} SET default_transaction_read_only = on").format(role))
        c.execute("SELECT EXISTS (SELECT 1 FROM pg_class WHERE relowner=r.oid) OR "
                  "EXISTS (SELECT 1 FROM pg_namespace WHERE nspowner=r.oid) FROM pg_roles r WHERE r.rolname=%s",
                  (name,))
        require(not c.fetchone()[0], "Reader owns database objects; it would hold every privilege on them")
        c.execute(sql.SQL("REVOKE CREATE, TEMPORARY ON DATABASE {} FROM {}").format(database, role))
        c.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(database, role))
        # PUBLIC may allow creating tables in public; revoking its default TEMPORARY privilege is extra hardening.
        c.execute("SELECT n.nspname FROM pg_namespace n WHERE has_schema_privilege(%s, n.oid, 'CREATE') "
                  "ORDER BY n.nspname", (name,))
        for (schema,) in c.fetchall():
            c.execute(sql.SQL("REVOKE CREATE ON SCHEMA {} FROM {}").format(sql.Identifier(schema), role))
            if schema == "public":
                c.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
                hardened.append("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
        c.execute("SELECT has_database_privilege(%s, current_database(), 'TEMPORARY')", (name,))
        if c.fetchone()[0]:
            c.execute(sql.SQL("REVOKE TEMPORARY ON DATABASE {} FROM PUBLIC").format(database))
            hardened.append("REVOKE TEMPORARY ON DATABASE FROM PUBLIC")
        tables = 0
        for schema in schemas:
            c.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema=%s AND table_name='build'",
                      (schema,))
            require(c.fetchone()[0] == 1, f"Not a release schema: {schema}")
            target = sql.Identifier(schema)
            # Start from nothing so grants left by earlier runs or by hand cannot survive.
            c.execute(sql.SQL("REVOKE ALL ON ALL TABLES IN SCHEMA {} FROM {}").format(target, role))
            c.execute(sql.SQL("REVOKE ALL ON SCHEMA {} FROM {}").format(target, role))
            c.execute(sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(target, role))
            c.execute(sql.SQL("GRANT SELECT ON ALL TABLES IN SCHEMA {} TO {}").format(target, role))
            c.execute("SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                      "WHERE n.nspname=%s AND c.relkind IN ('r','v') ORDER BY c.relname", (schema,))
            for (relation,) in c.fetchall():
                qualified = sql.Identifier(schema, relation).as_string(c)
                c.execute("SELECT has_table_privilege(%s,%s,'SELECT'), has_table_privilege(%s,%s,%s)",
                          (name, qualified, name, qualified, WRITE_PRIVILEGES))
                readable, writable = c.fetchone()
                require(readable and not writable, f"Unexpected privileges on {schema}.{relation}")
                tables += 1
        c.execute("SELECT n.nspname FROM pg_namespace n WHERE has_schema_privilege(%s, n.oid, 'CREATE')", (name,))
        require(not c.fetchall(), "Reader can still create objects in a schema")
        c.execute("SELECT has_database_privilege(%s,current_database(),'CREATE') OR "
                  "has_database_privilege(%s,current_database(),'TEMPORARY'), rolsuper, rolcreaterole, rolcreatedb "
                  "FROM pg_roles WHERE rolname=%s", (name, name, name))
        require(not any(c.fetchone()), "Reader has administrative privileges")
    db.commit()
    return dict(role=name, action=verb.lower(), schemas=schemas, relations=tables, hardened=hardened,
                default_transaction_read_only="on")


def verify_as_reader(reader, admin_user, schemas):
    """Log in as the role and try each way to write; every attempt must fail for lack of privilege."""
    import psycopg2
    from psycopg2 import sql
    statements = [sql.SQL("SET ROLE {}").format(sql.Identifier(admin_user)),
                  sql.SQL("CREATE TABLE public.reader_probe (id INTEGER)"),
                  sql.SQL("CREATE TEMPORARY TABLE reader_probe (id INTEGER)"),
                  sql.SQL("CREATE SCHEMA reader_probe")]
    for schema in schemas:
        target = sql.Identifier(schema)
        statements += [sql.SQL("CREATE TABLE {}.reader_probe (id INTEGER)").format(target),
                       sql.SQL("INSERT INTO {0}.dataset SELECT * FROM {0}.dataset WHERE false").format(target),
                       sql.SQL("UPDATE {}.entity SET label=label WHERE false").format(target),
                       sql.SQL("DELETE FROM {}.evidence WHERE false").format(target)]
    db = psycopg2.connect(**{k: v for k, v in reader.items() if k in CONNECT_KEYS})
    try:
        with db.cursor() as c:
            c.execute("SHOW default_transaction_read_only")
            require(c.fetchone()[0] == "on", "Reader sessions do not default to read-only")
            for schema in schemas:
                c.execute(sql.SQL("SELECT count(*) FROM {}.build").format(sql.Identifier(schema)))
                require(c.fetchone()[0] == 1, f"Reader cannot read {schema}")
            c.execute("SELECT n.nspname, c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                      "WHERE c.relkind IN ('r','p','v','m','f') AND n.nspname NOT IN ('pg_catalog','information_schema') "
                      "AND n.nspname NOT LIKE 'pg\\_toast%%' AND has_table_privilege(c.oid,%s)", (WRITE_PRIVILEGES,))
            writable = c.fetchall()
            require(not writable, f"Reader can write to {writable[:3]}")
            # Any role the reader belongs to is one it may SET ROLE to, whatever that role can do.
            c.execute("SELECT rolname FROM pg_roles WHERE rolname <> current_user "
                      "AND pg_has_role(current_user, oid, 'MEMBER') ORDER BY rolname")
            roles = [row[0] for row in c.fetchall()]
            require(not roles, f"Reader is a member of {roles[:3]}")
            db.rollback()
            for statement in statements:
                # Lift the session default first, so only privileges can stop the write.
                c.execute("SET TRANSACTION READ WRITE")
                try:
                    c.execute(statement)
                except psycopg2.Error as error:
                    require(error.pgcode == "42501", f"Unexpected SQLSTATE {error.pgcode}: {statement.as_string(c)}")
                else:
                    raise ValueError(f"Reader was allowed: {statement.as_string(c)}")
                finally:
                    db.rollback()
    finally:
        db.close()
    return len(statements)


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
        with db.cursor() as c:
            c.execute("SELECT current_user")
            admin_user = c.fetchone()[0]
        result = grant(db, reader, schemas)
        try:
            result["write_attempts_denied"] = verify_as_reader(reader, admin_user, schemas)
        except ValueError:
            # The login found a way to write, and the grants are already committed: lock the role out rather than
            # leave a writable account in use. A rerun that passes logs it back in.
            from psycopg2 import sql
            with db.cursor() as c:
                c.execute(sql.SQL("ALTER ROLE {} NOLOGIN").format(sql.Identifier(reader["user"])))
            db.commit()
            print(f"{reader['user']} can no longer log in; rerun this script after removing the cause",
                  file=sys.stderr)
            raise
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except ValueError as error:
        sys.exit(f"Blocked: {error}")
