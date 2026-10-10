"""M1a fixed acceptance samples; run with .venv/bin/python tests/test_api.py."""

import json
import sys
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend import services
from backend.app import app

BUILD = '5a76218e52001d45e4bd75e099a38780408e873342a14e5db0c86d7bb7a3008a'
FORMULA = 'bencaodian:formula:si_jun_zi_tang'
CONFLICT = 'bencaodian:formula:zhu_ling_tang'
GINSENG = 'bencaodian:herb:ren_shen'
LICORICE = 'bencaodian:herb:gan_cao'
BITTER = 'tcm-mkg:medicinal_property:8fa8553dc501fce26501a2aef0fa5cd798a41a126c217079d78274d05a5d5842'
ASTRAGALUS = 'tcm-mkg:herbal_piece:CHP01717'
QUOTE = 'evidence:f1e7866ee0971b80d3d27c8cb7fecf221003b29e87cf8c42d8a6947080d71cec'
REPAIR = 'evidence:cddf877aa77babf4552bf15a1790708296568cf7404c4645995f2e5eded22227'
API = '/api/v1'
client = TestClient(app, raise_server_exceptions=False)


def ok(path, **params):
    r = client.get(API + path, params=params)
    assert r.status_code == 200, (path, r.status_code, r.text)
    data = r.json()
    assert data['build_id'] == BUILD
    return data


def error(path, status, code, **params):
    r = client.get(API + path, params=params)
    assert r.status_code == status, (path, r.status_code, r.text)
    assert set(r.json()) == {'error'} and set(r.json()['error']) == {'code', 'message'}
    assert r.json()['error']['code'] == code, r.text
    assert any('\u4e00' <= c <= '\u9fff' for c in r.json()['error']['message'])
    for forbidden in ('psycopg2', 'Traceback', 'SELECT', '/home/', 'qihuang_import', 'secret-test-value'):
        assert forbidden not in r.text
    return r.json()


def common_errors():
    error('/entities', 422, 'invalid_query', limit=51)
    error('/entities', 422, 'invalid_type', type='unsupported')
    for path in ('/nope', '/entities/x/y/z', '/evidence/..%2F..%2Fconfig%2Fpostgresql.json'):
        error(path, 404, 'not_found')
    with patch.object(services, 'stats', side_effect=ValueError('secret-test-value SELECT /home/')):
        error('/stats', 500, 'internal_error')
    with services.relational() as c:
        c.execute('SHOW transaction_isolation')
        assert c.fetchone()['transaction_isolation'] == 'repeatable read'
        c.execute('SHOW transaction_read_only')
        assert c.fetchone()['transaction_read_only'] == 'on'
        c.execute('SHOW statement_timeout')
        assert c.fetchone()['statement_timeout'] == '3s'
    with patch.object(services.psycopg2, 'connect', side_effect=AssertionError('Must not connect')):
        try:
            with services.relational('0' * 64):
                raise AssertionError('Wrong snapshot accepted')
        except services.ServiceError as e:
            assert e.code == 'snapshot_changed'


def main():
    common_errors()
    print('PASS: unified errors, redaction, repeatable read, snapshot guard')


if __name__ == '__main__':
    main()
