"""Adversarial checks for the read-only role setup and for re-importing a live release.

Needs the local development database, the import account and config/postgresql_reader.json.
Every scenario ends with scripts/setup_reader.py restoring a verified read-only role.
"""

import sys
import threading
import time
from contextlib import closing

from test_api import ROOT, BUILD, FORMULA
from backend import queries, services

sys.path.insert(0, str(ROOT / 'scripts'))
import import_vastbase
import setup_reader


def admin():
    return import_vastbase.connection(ROOT / 'config/postgresql.json', 'postgresql')


def context():
    import json
    settings = services.application()
    admin_settings = json.loads((ROOT / 'config/postgresql.json').read_text())
    reader = setup_reader.reader_settings(ROOT / 'config/postgresql_reader.json', admin_settings)
    return reader, admin_settings['user'], [settings['schema']]


def run_sql(statements):
    with closing(admin()) as db, db.cursor() as c:
        for statement in statements:
            c.execute(statement)
        db.commit()


def reader_setup_checks():
    reader, admin_user, schemas = context()
    role, schema = reader['user'], schemas[0]
    with closing(admin()) as db, db.cursor() as c:
        c.execute('SHOW server_version_num')
        version = int(c.fetchone()[0])
    # PostgreSQL 16 records inheritance per membership; older servers use the role attribute.
    membership = ([f'GRANT {admin_user} TO {role} WITH INHERIT FALSE'] if version >= 160000 else
                  [f'ALTER ROLE {role} NOINHERIT', f'GRANT {admin_user} TO {role}'])
    scenarios = {
        # Each one is a way an existing role or database could let the reader write.
        'set_role_to_import_account': (membership, f'REVOKE {admin_user} FROM {role}'),
        'database_setting_overrides_read_only': (
            [f'ALTER ROLE {role} IN DATABASE qihuang SET default_transaction_read_only = off'], None),
        'public_schema_create': (['GRANT CREATE ON SCHEMA public TO PUBLIC'],
                                 'REVOKE CREATE ON SCHEMA public FROM PUBLIC'),
        'temporary_tables': (['GRANT TEMPORARY ON DATABASE qihuang TO PUBLIC'],
                             'REVOKE TEMPORARY ON DATABASE FROM PUBLIC'),
        'leftover_table_grant': ([f'GRANT INSERT ON {schema}.dataset TO {role}'], None),
        'leftover_schema_grant': ([f'GRANT CREATE ON SCHEMA {schema} TO {role}'], None),
    }
    results = {}
    for name, (attack, expected) in scenarios.items():
        with closing(admin()) as db:
            setup_reader.grant(db, reader, schemas)
        run_sql(attack)
        # The login check alone must notice the hole; otherwise it proves nothing.
        try:
            setup_reader.verify_as_reader(reader, admin_user, schemas)
        except ValueError:
            pass
        else:
            raise AssertionError(f'{name}: verification missed the opening')
        with closing(admin()) as db:
            result = setup_reader.grant(db, reader, schemas)
        if expected:
            assert expected in result['hardened'], (name, result['hardened'])
        results[name] = setup_reader.verify_as_reader(reader, admin_user, schemas)
    # Attributes that never allow a table write are still cleared.
    run_sql([f'ALTER ROLE {role} REPLICATION BYPASSRLS'])
    with closing(admin()) as db:
        hardened = setup_reader.grant(db, reader, schemas)['hardened']
    assert {f'ALTER ROLE {role} NOREPLICATION', f'ALTER ROLE {role} NOBYPASSRLS'} <= set(hardened), hardened
    # Owning an object grants every privilege on it, so setup refuses instead of trying to repair it.
    run_sql(['CREATE TABLE public.reader_owned (id INTEGER)', f'ALTER TABLE public.reader_owned OWNER TO {role}'])
    try:
        with closing(admin()) as db:
            setup_reader.grant(db, reader, schemas)
    except ValueError as error:
        assert 'owns database objects' in str(error)
    else:
        raise AssertionError('Reader owning a table was accepted')
    finally:
        run_sql(['DROP TABLE public.reader_owned'])
    with closing(admin()) as db:
        setup_reader.grant(db, reader, schemas)
    setup_reader.verify_as_reader(reader, admin_user, schemas)
    return results


def reimport_checks():
    """A reused release is live: re-running its import must not stall detail requests."""
    release = ROOT / 'var/prepared' / BUILD
    outcome = {}

    def run_import():
        with closing(admin()) as db:
            outcome['result'] = import_vastbase.import_release(db, release)

    worker = threading.Thread(target=run_import)
    worker.start()
    timings, failures = [], []
    while worker.is_alive():
        started = time.perf_counter()
        try:
            queries.entity_detail(FORMULA)
        except services.ServiceError as error:
            failures.append(error.code)
        timings.append((time.perf_counter() - started) * 1000)
        time.sleep(0.05)
    worker.join()
    assert outcome['result']['status'] == 'reused'
    assert not failures and max(timings) < 1000, (failures, max(timings))
    return len(timings), round(max(timings))


def main():
    results = reader_setup_checks()
    requests, slowest = reimport_checks()
    print('PASS: setup_reader closes', len(results), 'write paths of an existing role or database;',
          requests, 'detail requests during a live re-import, none failed, slowest', slowest, 'ms')


if __name__ == '__main__':
    main()
