"""Run with .venv/bin/python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000."""

from concurrent.futures import ThreadPoolExecutor
import logging
from typing import Annotated, Literal

from fastapi import FastAPI, Path, Query
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from backend import model_client, queries, schemas, services

app = FastAPI(title="QiHuang-KG", version="0.2.0", description="中医药知识检索与学习 · 详情与来源证据",
              responses={status: {"model": schemas.ErrorResponse} for status in (404, 409, 422, 500, 503)})


@app.exception_handler(services.ServiceError)
def service_error(request, error):
    return JSONResponse(status_code=services.ERROR_STATUS.get(error.code, 503),
                        content={"error": {"code": error.code, "message": str(error)}})


@app.exception_handler(RequestValidationError)
def invalid_query(request, error):
    return service_error(request, services.ServiceError("invalid_query", "请求参数格式、范围或长度不正确"))


@app.exception_handler(HTTPException)
def http_error(request, error):
    if error.status_code == 404:
        return service_error(request, services.ServiceError("not_found", "请求的接口不存在"))
    code = "method_not_allowed" if error.status_code == 405 else "invalid_query"
    response = service_error(request, services.ServiceError(code, "请求方法或参数不正确"))
    response.headers.update(error.headers or {})
    return response


@app.middleware("http")
async def unexpected_errors(request, call_next):
    try:
        return await call_next(request)
    except Exception as error:
        logging.getLogger(__name__).error("Unhandled API exception: %s", type(error).__name__)
        return service_error(request, services.ServiceError("internal_error", "服务暂时无法处理请求"))


ENTITY_PATTERN = r"^(bencaodian|tcm-mkg):(" + "|".join(services.TYPES) + r"):[A-Za-z0-9_.-]{1,160}$"
EntityID = Annotated[str, Path(pattern=ENTITY_PATTERN, description="来源:实体类型:键")]
EvidenceID = Annotated[str, Path(pattern=r"^evidence:[a-f0-9]{64}$", description="证据的稳定 ID")]
BuildID = Annotated[str | None, Query(pattern=r"^[a-f0-9]{64}$", description="可选发布批次，不一致时返回 409")]
Limit = Annotated[int, Query(ge=1, le=50, description="每页条数")]
Offset = Annotated[int, Query(ge=0, le=10000, description="跳过的条数")]


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
        raise services.ServiceError("invalid_type", "不支持的实体类型")
    return services.entities(q, type, limit, offset)


@app.get("/api/v1/graph/sample")
def sample_graph():
    return services.sample_graph()


@app.get("/api/v1/entities/{id}", response_model=schemas.EntityDetail, summary="实体详情")
def entity_detail(id: EntityID, build_id: BuildID = None):
    return queries.entity_detail(id, build_id)


@app.get("/api/v1/entities/{id}/evidence", response_model=schemas.EvidencePage, summary="实体证据分页")
def entity_evidence(id: EntityID, limit: Limit = 20, offset: Offset = 0, build_id: BuildID = None):
    return queries.entity_evidence(id, limit, offset, build_id)


@app.get("/api/v1/evidence/{id}", response_model=schemas.EvidenceDetail, summary="证据详情与原始字段值")
def evidence_detail(id: EvidenceID, build_id: BuildID = None):
    return queries.evidence_detail(id, build_id)


@app.get("/api/v1/relation-queries", response_model=schemas.RelationPage, summary="方剂组成与药物反查")
def relation_query(template: Annotated[Literal['formula_herbs', 'herb_formulas'], Query(description="查询模板")],
                   entity_id: Annotated[str, Query(pattern=ENTITY_PATTERN, description="起点实体 ID")],
                   limit: Limit = 20, offset: Offset = 0, build_id: BuildID = None):
    return queries.relation_query(template, entity_id, limit, offset, build_id)
