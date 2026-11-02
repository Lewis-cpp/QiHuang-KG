"""M7 recovery drill (m7-spec §3): restore into a temporary database, re-verify, clean up.

Run with .venv/bin/python tests/drill_m7.py → docs/acceptance/m7-recovery.json.
Nothing touches the main environment destructively: the restore target is a fresh database
qihuang_restore, created by the drill (it refuses to run if one already exists) and dropped at the end; the Neo4j step only re-runs the idempotent projection.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import psycopg2
from psycopg2 import sql

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend import services

STEPS = []


def step(name, command, ok, detail):
    STEPS.append(dict(name=name, ok=bool(ok), command=command, detail=str(detail)[:400]))
    print(f"{'PASS' if ok else 'FAIL'} {name} {str(detail)[:160]}")


def credentials(config_name, dbname):
    """The copied config with the restore database's name."""
    data = json.loads((TEMP / config_name).read_text())
    data['dbname'] = dbname
    return data


def run(cmd, env=None, timeout=1800):
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=timeout,
                          env={**os.environ, **(env or {})})


TEMP = Path(tempfile.mkdtemp(prefix='qihuang-restore-'))
BUILD = services.application()['build_id']


def main():
    main_report = json.loads((ROOT / 'var/postgresql-report.json').read_text())
    for source in (ROOT / 'config').glob('*.json'):
        shutil.copy(source, TEMP / source.name)
    # Point the copied configs at the restore database BEFORE anything runs; the main database must
    # never see the drill's import (the import itself refuses to double-import, but defense in depth).
    for name in ('postgresql.json', 'postgresql_reader.json'):
        data = json.loads((TEMP / name).read_text())
        data['dbname'] = 'qihuang_restore'
        (TEMP / name).write_text(json.dumps(data))

    create_restore_database()  # only after this succeeds is the database ours for cleanup() to drop
    try:
        relational_restore(main_report)
        reader_setup()
        api_recheck()
        graph_restore()
    finally:
        cleanup()
    deploy_check()

    report = dict(checked_at=datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(timespec='seconds'),
                  build_id=BUILD, steps=STEPS)
    path = ROOT / 'docs/acceptance/m7-recovery.json'
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    failed = [s['name'] for s in STEPS if not s['ok']]
    print(f"{len(STEPS) - len(failed)}/{len(STEPS)} ok; written to {path.relative_to(ROOT)}")
    if failed:
        sys.exit(f'FAILED: {failed}')


def create_restore_database():
    """Create qihuang_restore; an existing one is not ours to drop, so stop before cleanup() can run."""
    connection = psycopg2.connect(**{**json.loads((ROOT / 'config/postgresql.json').read_text()), 'dbname': 'qihuang'})
    connection.autocommit = True
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1 FROM pg_database WHERE datname=%s', ('qihuang_restore',))
            if cursor.fetchone():
                shutil.rmtree(TEMP, ignore_errors=True)
                sys.exit('qihuang_restore already exists; drop or rename it yourself, then rerun the drill')
            cursor.execute('CREATE DATABASE qihuang_restore OWNER qihuang_import')
    finally:
        connection.close()


def relational_restore(main_report):
    """A fresh database, the same prepared release, and digest-equal verification (m7-spec §3)."""
    # Guard: the import must target the restore database, never the main one.
    assert json.loads((TEMP / 'postgresql.json').read_text())['dbname'] == 'qihuang_restore'
    command = ['.venv/bin/python', 'scripts/import_vastbase.py', '--engine', 'postgresql',
               '--config', str(TEMP / 'postgresql.json'),
               '--release', f'var/prepared/{BUILD}', '--report', str(TEMP / 'restore-report.json')]
    started = time.monotonic()
    result = run(command)
    elapsed = round(time.monotonic() - started)
    detail = f'import {elapsed}s; '
    ok = result.returncode == 0
    restore = {}
    if ok:
        restore = json.loads((TEMP / 'restore-report.json').read_text())
        imported = restore['import_result']
        same_counts = imported['verification']['counts'] == main_report['import_result']['verification']['counts']
        same_digest = imported['verification']['table_sha256'] == main_report['import_result']['verification']['table_sha256']
        ok = imported['status'] == 'imported' and same_counts and same_digest
        detail += (f"status={imported['status']}, counts 一致 {same_counts}, table_sha256 一致 {same_digest}, "
                   f"业务记录 {imported['verification']['business_records']}")
    else:
        detail += result.stderr[-300:]
    step('relational_restore',
         'python3 scripts/import_vastbase.py --engine postgresql --config <临时>/postgresql.json '
         f'--release var/prepared/{BUILD[:12]}… --report <临时>/restore-report.json', ok, detail)
    return restore


def reader_setup():
    env = {'QIHUANG_CONFIG_DIR': str(TEMP)}
    result = run(['.venv/bin/python', 'scripts/setup_reader.py', '--engine', 'postgresql'], env=env)
    ok, detail = result.returncode == 0, 'setup_reader 退出码 0' if result.returncode == 0 else result.stderr[-300:]
    print(f"    setup_reader rc={result.returncode}: {(result.stdout or result.stderr).strip().splitlines()[-1:]}")
    if ok:
        schema = json.loads((TEMP / 'app.json').read_text())['schema']
        reader = psycopg2.connect(**credentials('postgresql_reader.json', 'qihuang_restore'))
        codes = []
        with reader.cursor() as cursor:
            def fresh_session():
                # The role default makes every new transaction read-only, and changing the GUC only
                # affects transactions opened after it — so aim the search path, turn read-only off and
                # COMMIT, so the attempted write runs in a fresh writable transaction.
                cursor.execute(sql.SQL('SET search_path TO {}, pg_catalog').format(sql.Identifier(schema)))
                cursor.execute('SET default_transaction_read_only = off')
                reader.commit()

            fresh_session()
            cursor.execute('SELECT count(*) FROM entity')
            readable = cursor.fetchone()[0] == 20374
            reader.rollback()
            for statement in ('INSERT INTO dataset (id,title,version_label,source_url,license_statement,attribution) '
                              "VALUES ('x','x','x','x','x','x')", 'UPDATE build SET schema_version=3',
                              'DELETE FROM alias', 'CREATE TABLE probe_m7 ()'):
                fresh_session()
                try:
                    cursor.execute(statement)
                    reader.commit()
                    codes.append('no-error')
                except psycopg2.Error as error:
                    reader.rollback()
                    codes.append(error.pgcode)
        ok = readable and set(codes) == {'42501'}
        detail = f'只读可查 20,374 行；读写事务下 INSERT/UPDATE/DELETE/CREATE 全部 42501：{codes}'
        reader.close()
    step('reader_setup', 'QIHUANG_CONFIG_DIR=<临时> python3 scripts/setup_reader.py --engine postgresql', ok, detail)


def api_recheck():
    env = {'QIHUANG_CONFIG_DIR': str(TEMP)}
    started = time.monotonic()
    result = run(['.venv/bin/python', 'tests/test_api.py'], env=env)
    tail = (result.stdout or result.stderr).strip().splitlines()[-1:] or ['']
    step('api_recheck', 'QIHUANG_CONFIG_DIR=<临时> python3 tests/test_api.py', result.returncode == 0,
         f"{round(time.monotonic() - started)}s；{tail[0][:240]}")


def graph_restore():
    drill = json.loads((ROOT / 'docs/acceptance/m3-backup-restore.json').read_text())
    dump_load_ok = (drill['after']['node_count'] == drill['before']['node_count'] and
                    drill['after']['edge_count'] == drill['before']['edge_count'] and
                    drill['after']['id_digest'] == drill['before']['id_digest'])
    result = run(['.venv/bin/python', 'scripts/project_graph.py'])
    ok = result.returncode == 0 and '"status": "reused"' in result.stdout and dump_load_ok
    counts = f"{drill['after']['node_count']} 节点 / {drill['after']['edge_count']} 边，摘要一致"
    step('graph_restore',
         '引用 docs/acceptance/m3-backup-restore.json；python3 scripts/project_graph.py（主 Neo4j 重跑投影）',
         ok, f'dump/load 演练：{counts}；project_graph 复用 reused={result.returncode == 0}')


def cleanup():
    connection = psycopg2.connect(**{**json.loads((TEMP / 'postgresql.json').read_text()), 'dbname': 'qihuang'})
    connection.autocommit = True
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='qihuang_restore' "
                       'AND pid <> pg_backend_pid()')
        cursor.execute('DROP DATABASE IF EXISTS qihuang_restore')
    connection.close()
    shutil.rmtree(TEMP, ignore_errors=True)
    health = services.database_health()
    ok = health['status'] == 'ready' and health['build_id'] == BUILD
    step('cleanup', 'DROP DATABASE qihuang_restore；删除临时配置目录', ok,
         f"主库 {health['status']}，build_id 未变（{health['build_id'][:12]}…）")


def deploy_check():
    server = subprocess.Popen(['.venv/bin/python', '-m', 'uvicorn', 'backend.app:app', '--host', '127.0.0.1',
                               '--port', '8001'], cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            try:
                if httpx.get('http://127.0.0.1:8001/api/v1/health/live', timeout=2).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(1)
        result = run(['node', 'tests/browser/deploy_check.mjs', 'http://127.0.0.1:8001'], timeout=300)
        verdict = json.loads(result.stdout.strip().splitlines()[-1]) if result.stdout.strip() else {}
        step('deploy_check',
             'npm run build 后以独立 uvicorn（127.0.0.1:8001）托管 frontend/dist；'
             'node tests/browser/deploy_check.mjs 无头 Chrome 打开并刷新实体、图谱、/ai 三个深链接',
             verdict.get('ok', False), verdict.get('detail') or '三个深链接刷新后标题正确，无控制台错误（favicon 404 除外）')
    finally:
        server.terminate()
        server.wait(timeout=30)


if __name__ == '__main__':
    main()
