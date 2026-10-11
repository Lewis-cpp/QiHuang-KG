"""Record M1 maintenance evidence: read-only role write failures and a failed import that rolls back.

Needs the local development database with the import account and the reader role set up.
"""

import json
import shutil
import sys
import tempfile
import time
from contextlib import closing
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from test_api import ROOT, BUILD, API, client, reader_checks
from backend import services

sys.path.insert(0, str(ROOT / 'scripts'))
import import_vastbase

FAILED_BUILD = 'f' * 64


def live_state(c, schema):
    c.execute("SELECT nspname FROM pg_namespace WHERE nspname LIKE 'qihuang\\_%' ORDER BY nspname")
    schemas = [r[0] for r in c.fetchall()]
    counts = {}
    for table in ('build', 'dataset', 'source_record', 'entity', 'alias', 'edge', 'evidence'):
        c.execute(f'SELECT count(*) FROM "{schema}".{table}')
        counts[table] = c.fetchone()[0]
    c.connection.rollback()
    return dict(schemas=schemas, counts=counts)


def rollback_demo():
    """Import a release under a new build ID whose target verification fails after every row is copied."""
    settings = services.application()
    release = ROOT / 'var/prepared' / BUILD
    stats_before = client.get(API + '/stats').json()
    with closing(import_vastbase.connection(ROOT / 'config/postgresql.json', 'postgresql')) as db, \
            tempfile.TemporaryDirectory() as temp:
        before = live_state(db.cursor(), settings['schema'])
        failed = Path(temp)
        manifest = json.loads((release / 'manifest.json').read_text())
        manifest['build_id'] = FAILED_BUILD
        (failed / 'manifest.json').write_text(json.dumps(manifest))
        shutil.copy(release / 'report.json', failed / 'report.json')
        (failed / 'kg.sqlite').symlink_to(release / 'kg.sqlite')
        copied = {}
        real_verify = import_vastbase.verify_target

        def observe(c, target_manifest):
            # Inside the import transaction: the new schema holds the full copy at this point.
            for table in ('entity', 'edge', 'evidence'):
                c.execute(f'SELECT count(*) FROM {table}')
                copied[table] = c.fetchone()[0]
            return real_verify(c, target_manifest)

        started = time.perf_counter()
        # Staging validation would reject the altered manifest before any database write; skip it so the
        # failure happens where it matters, after DDL and COPY inside the import transaction.
        with patch.object(import_vastbase, 'validate', lambda stage, m: None), \
                patch.object(import_vastbase, 'verify_target', observe):
            try:
                import_vastbase.import_release(db, failed)
            except ValueError as error:
                failure = str(error)
            else:
                raise AssertionError('Failed import was committed')
        elapsed = time.perf_counter() - started
        after = live_state(db.cursor(), settings['schema'])
    stats_after = client.get(API + '/stats').json()
    failed_schema = 'qihuang_' + FAILED_BUILD[:24]
    assert failure == 'Target build mismatch'
    assert copied == dict(entity=20374, edge=179502, evidence=291305), copied
    assert failed_schema not in after['schemas'] and after == before
    assert stats_after == stats_before and stats_after['build_id'] == BUILD
    return dict(failed_schema=failed_schema, failure=failure, rows_copied_before_failure=copied,
                elapsed_seconds=round(elapsed, 1), before=before, after=after,
                api_stats_unchanged=True, api_build_id=stats_after['build_id'],
                note='staging validation skipped on purpose; the build row check in verify_target fails the import')


def main():
    with services.relational() as c:
        c.execute('SELECT version() AS version')
        version = c.fetchone()['version']
    checked_at = datetime.now(ZoneInfo('Asia/Singapore')).isoformat()
    codes = reader_checks()
    (ROOT / 'docs/acceptance/m1-readonly.json').write_text(json.dumps(dict(
        checked_at=checked_at, database=version, build_id=BUILD, role='qihuang_reader',
        default_transaction_read_only='on', sqlstate=codes,
        meaning={'25006': 'read_only_sql_transaction', '42501': 'insufficient_privilege'},
        note='Each write runs after SET TRANSACTION READ WRITE, so the failure comes from privileges, not the setting'),
        ensure_ascii=False, indent=2) + '\n')
    result = rollback_demo()
    (ROOT / 'docs/acceptance/m1-import-rollback.json').write_text(json.dumps(dict(
        checked_at=checked_at, database=version, live_build_id=BUILD, **result), ensure_ascii=False, indent=2) + '\n')
    print('PASS: reader writes fail with', sorted(set(codes.values())), '; failed import of',
          sum(result['rows_copied_before_failure'].values()), 'rows rolled back, live release unchanged')


if __name__ == '__main__':
    main()
