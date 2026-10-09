"""Run with .venv/bin/python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000."""

from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse

from backend import model_client, services

app = FastAPI(title="QiHuang-KG", version="0.1.0", description="中医药知识检索与学习 · 最小开发链路")


@app.exception_handler(services.ServiceError)
def service_error(request, error):
    return JSONResponse(status_code=503, content={"error": {"code": error.code, "message": str(error)}})


@app.get("/api/v1/health/live")
def live():
    return {"status": "alive"}


def checked(fn):
    try:
        return fn()
    except services.ServiceError as error:
        return dict(status="unavailable", code=error.code, message=str(error))


@app.get("/api/v1/health")
def health():
    with ThreadPoolExecutor(max_workers=2) as pool:
        pg = pool.submit(checked, services.database_health)
        neo4j = pool.submit(checked, services.graph_health)
        components = dict(database=pg.result(), neo4j=neo4j.result(), model=model_client.status())
    ready = components["database"]["status"] == "ready"
    all_verified = ready and components["neo4j"]["status"] == "ready" and components["model"]["status"] == "verified"
    return JSONResponse(status_code=200 if ready else 503, content=dict(
        status="ready" if all_verified else "degraded" if ready else "unavailable", services=components))


@app.get("/api/v1/stats")
def stats():
    return services.stats()


@app.get("/api/v1/entities")
def entities(q: str = Query("", max_length=100), type: str | None = None,
             limit: int = Query(20, ge=1, le=50), offset: int = Query(0, ge=0, le=10000)):
    if type is not None and type not in services.TYPES:
        return JSONResponse(status_code=422, content={"error": {"code": "invalid_type", "message": "不支持的实体类型"}})
    return services.entities(q, type, limit, offset)


@app.get("/api/v1/graph/sample")
def sample_graph():
    return services.sample_graph()
