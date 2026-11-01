"""M5 fault drills (m5-spec §7): six failure paths through the real app; no billed model call.

Run with .venv/bin/python tests/drill_m5.py → docs/acceptance/m5-drills.json.
Needs Docker services up; the drill stops and restarts PostgreSQL and Neo4j and always restores them.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

import httpx
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend import explain, model_client, services
from backend.app import app

SI_JUN = 'bencaodian:formula:si_jun_zi_tang'
ZHU_LING = 'bencaodian:formula:zhu_ling_tang'
RESULTS = []


def check(name, ok, detail=''):
    RESULTS.append(dict(name=name, ok=bool(ok), detail=str(detail)))
    print(f"{'PASS' if ok else 'FAIL'} {name} {detail}")


def stub_query():
    """A patcher returning a valid query-shape output (whitelisted condition only)."""
    output = {'target_type': 'formula', 'conditions': [{'field': 'includes_herb', 'value': '甘草'}], 'unsupported': []}

    def fake(system, content, log=None):
        return output, dict(model='drill-model', usage={'completion_tokens': 3}, request_id='drill')

    return patch.object(model_client, 'complete_json', side_effect=fake)


def stub_explain(entity_id=ZHU_LING):
    """A patcher returning an explain-shape output that passes validation."""
    bundle = explain.gather(entity_id)
    ref = next(m['ref'] for m in bundle['materials'] if m['kind'] == 'source')
    output = {'sections': [{'heading': '出处', 'sentences': [{'text': '本方的出处与关联证候见材料所列。', 'citations': [ref]}]}],
              'insufficient': []}

    def fake(system, content, log=None):
        return output, dict(model='drill-model', usage={'completion_tokens': 3}, request_id='drill')

    return patch.object(model_client, 'complete_json', side_effect=fake)


@contextmanager
def config_dir(mutate=None):
    """A private config copy; services.config() re-reads QIHUANG_CONFIG_DIR on every call."""
    temp = Path(tempfile.mkdtemp(prefix='qihuang-drill-'))
    for source in (ROOT / 'config').glob('*.json'):
        shutil.copy(source, temp / source.name)
    if mutate:
        mutate(temp)
    saved = os.environ.get('QIHUANG_CONFIG_DIR')
    os.environ['QIHUANG_CONFIG_DIR'] = str(temp)
    try:
        yield temp
    finally:
        if saved is None:
            os.environ.pop('QIHUANG_CONFIG_DIR', None)
        else:
            os.environ['QIHUANG_CONFIG_DIR'] = saved
        shutil.rmtree(temp, ignore_errors=True)


def compose(*args):
    return subprocess.run(['docker', 'compose', *args], cwd=ROOT, capture_output=True, text=True, timeout=180)


def wait_for(predicate, timeout, what):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if predicate():
                return True
        except Exception:
            pass
        time.sleep(2)
    print(f'    {what} did not recover within {timeout}s')
    return False


def drill_not_configured():
    """M5-01: without model.json the AI endpoints degrade, everything else is unaffected."""
    client = TestClient(app)

    def drop_model(temp):
        (temp / 'model.json').unlink()

    with config_dir(drop_model):
        health = client.get('/api/v1/health').json()['services']['model']
        query = client.post('/api/v1/ai/query', json={'question': '含甘草的补益剂'})
        explain = client.post('/api/v1/ai/explain', json={'entity_id': SI_JUN})
        search = client.get('/api/v1/entities', params={'q': '四君子汤'})
    check('M5-01 模型未配置时降级', health['status'] == 'not_configured' and
          query.status_code == 503 and query.json()['error']['code'] == 'model_not_configured' and
          explain.status_code == 503 and explain.json()['error']['code'] == 'model_not_configured' and
          search.status_code == 200,
          f"model={health['status']}, query={query.status_code}, explain={explain.status_code}, search={search.status_code}")


def drill_model_unreachable():
    """M5-02: an unreachable base_url fails fast as model_unavailable, exactly one attempt."""
    client = TestClient(app)

    def mutate(temp):
        path = temp / 'model.json'
        data = json.loads(path.read_text())
        data['base_url'] = 'http://127.0.0.1:9'
        path.write_text(json.dumps(data))

    calls = []
    real = model_client.complete_json

    def counting(*args, **kwargs):
        calls.append(1)
        return real(*args, **kwargs)

    with config_dir(mutate), patch.object(model_client, 'complete_json', side_effect=counting):
        started = time.monotonic()
        response = client.post('/api/v1/ai/explain', json={'entity_id': SI_JUN})
        elapsed = time.monotonic() - started
    code = response.json().get('error', {}).get('code')
    check('M5-02 模型不可达快速失败', response.status_code == 503 and code == 'model_unavailable' and
          len(calls) == 1 and elapsed < 30, f"{response.status_code}/{code}, attempts={len(calls)}, {elapsed:.1f}s")


def drill_neo4j_down(client):
    """M5-03: AI paths survive a Neo4j outage; /graph fails and recovers."""
    down = compose('stop', 'neo4j')
    ok_down = down.returncode == 0
    try:
        graph = client.get('/api/v1/graph', params={'center': SI_JUN})
        with stub_query():
            query = client.post('/api/v1/ai/query', json={'question': '含甘草的补益剂'})
        with stub_explain():
            explain_response = client.post('/api/v1/ai/explain', json={'entity_id': ZHU_LING})
        check('M5-03 Neo4j 停机时 AI 正常、图接口 503',
              ok_down and graph.status_code == 503 and graph.json()['error']['code'] == 'neo4j_unavailable' and
              query.status_code == 200 and query.json()['status'] == 'ok' and explain_response.status_code == 200,
              f"graph={graph.status_code}, query={query.status_code}, explain={explain_response.status_code}")
    finally:
        compose('start', 'neo4j')
    recovered = wait_for(lambda: client.get('/api/v1/graph', params={'center': SI_JUN}).status_code == 200, 120,
                         'Neo4j')
    check('M5-03 Neo4j 恢复后图接口 200', recovered)


def drill_postgres_down(client):
    """M5-04: with PostgreSQL down both AI endpoints fail before reaching the model."""
    down = compose('stop', 'postgres')
    try:
        called = []

        def must_not_call(*args, **kwargs):
            called.append(1)
            raise AssertionError('M5-04 must not reach the model')

        with patch.object(model_client, 'complete_json', side_effect=must_not_call):
            query = client.post('/api/v1/ai/query', json={'question': '含甘草的补益剂'})
            explain_response = client.post('/api/v1/ai/explain', json={'entity_id': SI_JUN})
        codes = (query.json().get('error', {}).get('code'), explain_response.json().get('error', {}).get('code'))
        check('M5-04 数据库停机时 AI 拒绝且不调模型',
              down.returncode == 0 and query.status_code == 503 and explain_response.status_code == 503 and
              codes == ('database_unavailable', 'database_unavailable') and not called,
              f"query={query.status_code}, explain={explain_response.status_code}, model_calls={len(called)}")
    finally:
        compose('start', 'postgres')
    recovered = wait_for(lambda: client.get('/api/v1/entities', params={'q': '四君子汤', 'limit': 1}).status_code == 200,
                         120, 'PostgreSQL')
    check('M5-04 数据库恢复后接口 200', recovered)


def drill_build_mismatch(client):
    """M5-05: a legal but different build_id is a 409 before any model call."""
    called = []

    def must_not_call(*args, **kwargs):
        called.append(1)

    with patch.object(model_client, 'complete_json', side_effect=must_not_call):
        query = client.post('/api/v1/ai/query', json={'question': '含甘草的补益剂', 'build_id': '0' * 64})
        explain_response = client.post('/api/v1/ai/explain', json={'entity_id': SI_JUN, 'build_id': '0' * 64})
    check('M5-05 批次不一致返回 409 且不调模型',
          query.status_code == 409 and explain_response.status_code == 409 and not called,
          f"query={query.status_code}, explain={explain_response.status_code}, model_calls={len(called)}")


def slow_completion(seconds):
    """A MockTransport-backed httpx.Client so the REAL complete_json (and its SLOTS) runs."""
    bundle = explain.gather(ZHU_LING)
    ref = next(m['ref'] for m in bundle['materials'] if m['kind'] == 'source')
    content = json.dumps({'sections': [{'heading': '出处',
                                        'sentences': [{'text': '本方的出处与关联证候见材料所列。', 'citations': [ref]}]}],
                          'insufficient': []}, ensure_ascii=False)
    payload = {'id': 'drill', 'model': 'drill-model',
               'choices': [{'finish_reason': 'stop', 'message': {'content': content}}],
               'usage': {'prompt_tokens': 1, 'completion_tokens': 1}}

    def handler(request):
        time.sleep(seconds)
        return httpx.Response(200, json=payload)

    real_client = httpx.Client

    def factory(**kwargs):
        return real_client(**kwargs, transport=httpx.MockTransport(handler))

    return patch.object(model_client.httpx, 'Client', side_effect=factory)


def drill_busy():
    """M5-06: three concurrent explains through the real semaphore — exactly one model_busy."""
    def run(_):
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post('/api/v1/ai/explain', json={'entity_id': ZHU_LING})
        return response.status_code, response.json().get('error', {}).get('code')

    with slow_completion(1.0):
        with ThreadPoolExecutor(max_workers=3) as pool:
            outcomes = list(pool.map(run, range(3)))
    codes = [code or f'http {status}' for status, code in outcomes]
    busy = codes.count('model_busy')
    ok = sum(1 for status, _ in outcomes if status == 200)
    check('M5-06 三路并发恰好一个 model_busy', busy == 1 and ok == 2, f'outcomes={codes}')


def main():
    client = TestClient(app, raise_server_exceptions=False)
    drill_not_configured()
    drill_model_unreachable()
    drill_neo4j_down(client)
    drill_postgres_down(client)
    drill_build_mismatch(client)
    drill_busy()
    report = dict(checked_at=datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(timespec='seconds'), results=RESULTS)
    path = ROOT / 'docs/acceptance/m5-drills.json'
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    failed = [r['name'] for r in RESULTS if not r['ok']]
    print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} ok; written to {path.relative_to(ROOT)}")
    if failed:
        sys.exit(f'FAILED: {failed}')


if __name__ == '__main__':
    main()
