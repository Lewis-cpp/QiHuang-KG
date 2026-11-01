"""M7 production hosting: FastAPI serves frontend/dist with an SPA fallback that never exposes repository files.

Run after `cd frontend && npm run build`: .venv/bin/python tests/test_deploy.py. Contract: docs/dev/m7-spec.md §1.
"""

import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / 'frontend/dist'
sys.path.insert(0, str(ROOT))


def main():
    index = DIST / 'index.html'
    assert index.is_file(), 'frontend/dist/index.html is missing: run `cd frontend && npm run build` first'
    from backend.app import app
    client = TestClient(app, raise_server_exceptions=False)
    html = index.read_text(encoding='utf-8')

    for path in ('/', '/entity/bencaodian:formula:si_jun_zi_tang', '/graph/bencaodian:formula:si_jun_zi_tang',
                 '/ai', '/stats', '/datasets', '/evidence/evidence:' + 'a' * 64, '/no/such/page'):
        r = client.get(path)
        assert r.status_code == 200 and r.headers['content-type'].startswith('text/html'), (path, r.status_code)
        assert r.text == html, f'{path} must return dist/index.html'
        assert 'no-cache' in r.headers.get('cache-control', ''), path

    # Repository files are never served, whatever the path looks like.
    secret_markers = ('base_url', 'api_key', 'password', 'import fastapi', 'BEGIN', 'build_id')
    for path in ('/config/model.json', '/config/app.json', '/var/postgres-password', '/backend/app.py', '/.env',
                 '/assets/../../config/model.json', '/assets/%2e%2e/%2e%2e/config/model.json',
                 '/..%2Fconfig%2Fmodel.json', '/frontend/dist/index.html/../../../config/model.json'):
        r = client.get(path)
        assert r.status_code in (200, 404), (path, r.status_code)
        if r.status_code == 200:
            assert r.text == html, f'{path} served something other than index.html'
        else:
            assert not any(m in r.text for m in secret_markers[:5]), path

    assets = sorted((DIST / 'assets').glob('*.js'))
    assert assets, 'no built JavaScript assets'
    r = client.get('/assets/' + assets[0].name)
    assert r.status_code == 200 and 'javascript' in r.headers['content-type']
    assert r.content == assets[0].read_bytes()
    r = client.get('/assets/does-not-exist.js')
    assert r.status_code == 404 and r.text != html, 'a missing asset must be 404, not the SPA page'

    # The API keeps its own routing and JSON errors.
    r = client.get('/api/v1/health/live')
    assert r.status_code == 200 and r.json() == {'status': 'alive'}
    for path in ('/api/v1/nope', '/api/nope', '/api'):
        r = client.get(path)
        assert r.status_code == 404 and r.json()['error']['code'] == 'not_found', (path, r.text)
    r = client.post('/api/v1/entities')
    assert r.status_code == 405 and r.json()['error']['code'] == 'method_not_allowed'
    assert client.get('/openapi.json').status_code == 200 and client.get('/docs').status_code == 200
    r = client.get('/api/v1/entities', params={'q': '四君子汤'})
    assert r.status_code == 200 and r.json()['items'][0]['id'] == 'bencaodian:formula:si_jun_zi_tang'
    print('PASS: SPA fallback with no-cache index, deep links, built assets, missing asset 404, no repository file '
          'exposure, API routing and JSON errors unchanged')


if __name__ == '__main__':
    main()
