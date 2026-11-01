"""Stub API server for page drills that must not bill a model: serves frontend/dist, proxies /api/v1.

Usage: python tests/browser/stub_backend.py <port> <degraded|notready>
- degraded: POST /api/v1/ai/explain returns a validation-failed explanation; everything else is proxied.
- notready: /health reports model.status=not_configured; the page must show 模型未就绪.
"""

import sys
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from starlette.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parents[2]
DIST = ROOT / 'frontend/dist'
REAL = 'http://127.0.0.1:8000'
port, mode = int(sys.argv[1]), sys.argv[2]

app = FastAPI()
upstream = httpx.Client(timeout=10)


@app.api_route('/api/v1/health', methods=['GET'])
def health():
    model = dict(status='verified', model='deepseek-flash') if mode == 'degraded' else \
        dict(status='not_configured', message='模型名称或服务凭据尚未配置')
    return dict(status='degraded', services=dict(database=dict(status='ready'), neo4j=dict(status='ready'),
                                                 model=model))


@app.post('/api/v1/ai/explain')
async def explain_stub(request: Request):
    body = await request.json()
    if mode != 'degraded':
        return JSONResponse(status_code=503, content={'error': {
            'code': 'model_not_configured', 'message': '模型名称或服务凭据尚未配置'}})
    return dict(status='explanation_unavailable', entity_id=body.get('entity_id'), sections=[], insufficient=[],
                materials=[], failure=['第 1 句把“泽泻”写成了臣药，但材料中它的角色未给出或存在冲突',
                                       '第 2 句的剂量“12g”与材料中白术的剂量不符'],
                attempts=2, model='stub-model', prompt_version='explain_v1', usage=[], build_id=body.get('build_id'))


@app.api_route('/api/v1/{path:path}', methods=['GET', 'POST'])
async def proxy(path: str, request: Request):
    response = upstream.request(request.method, f'{REAL}/api/v1/{path}',
                                params=request.url.query, content=await request.body(),
                                headers={'Content-Type': request.headers.get('content-type', '')})
    return Response(content=response.content, status_code=response.status_code,
                    media_type=response.headers.get('content-type'))


if (DIST / 'index.html').is_file():
    app.mount('/assets', StaticFiles(directory=DIST / 'assets'), name='assets')

    @app.get('/{path:path}', include_in_schema=False)
    def spa(path: str):
        if path.startswith('api/'):
            return JSONResponse(status_code=404, content={'error': {'code': 'not_found', 'message': '不存在'}})
        candidate = (DIST / path).resolve()
        if candidate.is_file() and candidate.is_relative_to(DIST):
            return Response(content=candidate.read_bytes())
        return Response(content=(DIST / 'index.html').read_bytes(), media_type='text/html',
                        headers={'Cache-Control': 'no-cache'})


if __name__ == '__main__':
    import uvicorn

    uvicorn.run(app, host='127.0.0.1', port=port, log_level='warning')
