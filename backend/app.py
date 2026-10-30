"""Run with .venv/bin/python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000."""

from concurrent.futures import ThreadPoolExecutor
import logging
from typing import Annotated, Literal

from fastapi import FastAPI, Path, Query
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from backend import ai, graph, model_client, queries, schemas, services

app = FastAPI(title="QiHuang-KG", version="0.3.0", description="中医药知识检索与学习 · 详情、来源证据与图谱",
              responses={status: {"model": schemas.ErrorResponse} for status in (404, 409, 422, 500, 502, 503)})


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
    components["neo4j"].setdefault("projection", "not_ready")
    ready = components["database"]["status"] == "ready"
    all_verified = ready and components["neo4j"]["status"] == "ready" and components["model"]["status"] == "verified"
    return JSONResponse(status_code=200 if ready else 503, content=dict(
        status="ready" if all_verified else "degraded" if ready else "unavailable", services=components))


@app.get("/api/v1/stats")
def stats():
    return services.stats()


@app.get("/api/v1/entities", response_model=schemas.EntityPage, summary="实体检索与类型目录")
def entities(q: Annotated[str, Query(max_length=100, description="名称或别名；为空时按类型目录返回")] = "",
             type: Annotated[str | None, Query(description="实体类型")] = None,
             dataset: Annotated[Literal['bencaodian', 'tcm-mkg'] | None, Query(description="来源数据集")] = None,
             limit: Limit = 20, offset: Offset = 0, build_id: BuildID = None):
    if type is not None and type not in services.TYPES:
        raise services.ServiceError("invalid_type", "不支持的实体类型")
    return queries.search_entities(q, type, dataset, limit, offset, build_id)


@app.get("/api/v1/graph/sample")
def sample_graph():
    return services.sample_graph()


@app.get("/api/v1/graph", response_model=schemas.GraphPage, summary="图数据库中的一跳邻域")
def graph_neighborhood(center: Annotated[str, Query(pattern=ENTITY_PATTERN, description="中心实体 ID")],
                       relation: Annotated[list[Literal[queries.RELATIONS]] | None,
                                           Query(description="关系类型，可重复；为空时不过滤")] = None,
                       build_id: BuildID = None):
    return graph.neighborhood(center, sorted(set(relation)) if relation else None, build_id)


@app.get("/api/v1/graph/paths", response_model=schemas.RelationPage, summary="图数据库中的两跳路径")
def graph_paths(template: Annotated[Literal[tuple(graph.PATH_TEMPLATES)], Query(description="路径模板")],
                entity_id: Annotated[str, Query(pattern=ENTITY_PATTERN, description="起点实体 ID")],
                limit: Limit = 20, offset: Offset = 0, build_id: BuildID = None):
    return graph.paths(template, entity_id, limit, offset, build_id)


@app.get("/api/v1/entities/{id}", response_model=schemas.EntityDetail, summary="实体详情")
def entity_detail(id: EntityID, build_id: BuildID = None):
    return queries.entity_detail(id, build_id)


@app.get("/api/v1/entities/{id}/evidence", response_model=schemas.EvidencePage, summary="实体证据分页")
def entity_evidence(id: EntityID, limit: Limit = 20, offset: Offset = 0, build_id: BuildID = None):
    return queries.entity_evidence(id, limit, offset, build_id)


@app.get("/api/v1/evidence/{id}", response_model=schemas.EvidenceDetail, summary="证据详情与原始字段值")
def evidence_detail(id: EvidenceID, build_id: BuildID = None):
    return queries.evidence_detail(id, build_id)


@app.get("/api/v1/entities/{id}/relations", response_model=schemas.NeighborPage, summary="按关系类型和方向分页列出邻居")
def entity_relations(id: EntityID, relation: Annotated[Literal[queries.RELATIONS], Query(description="关系类型")],
                     direction: Annotated[Literal['out', 'in'], Query(description="out 为出边，in 为入边")],
                     limit: Limit = 20, offset: Offset = 0, build_id: BuildID = None):
    return queries.entity_relations(id, relation, direction, limit, offset, build_id)


@app.get("/api/v1/entities/{id}/formula-notes", response_model=schemas.FormulaNotes,
         summary="方剂关联证候的症状与组成药物的注意事项（来源原文）")
def formula_notes(id: EntityID, build_id: BuildID = None):
    return queries.formula_notes(id, build_id)


@app.get("/api/v1/datasets", response_model=schemas.DatasetPage, summary="来源、版本、许可与署名")
def datasets(build_id: BuildID = None):
    return queries.datasets(build_id)


@app.get("/api/v1/relation-queries", response_model=schemas.RelationPage, summary="固定模板的关系查询")
def relation_query(template: Annotated[Literal[tuple(queries.TEMPLATES)], Query(description="查询模板")],
                   entity_id: Annotated[str, Query(pattern=ENTITY_PATTERN, description="起点实体 ID")],
                   limit: Limit = 20, offset: Offset = 0, build_id: BuildID = None):
    return queries.relation_query(template, entity_id, limit, offset, build_id)


@app.post("/api/v1/ai/query", response_model=schemas.AIQueryResult,
          summary="自然语言条件查询：模型只提出白名单条件，后端校验、解析后执行参数化查询")
def ai_query(body: schemas.AIQueryRequest):
    with_conditions = body.conditions is not None
    if (body.question is None) != with_conditions or with_conditions != (body.target_type is not None):
        raise services.ServiceError("invalid_query", "请只提供 question，或同时提供 conditions 与 target_type")
    if body.question is not None:
        return ai.ask(body.question, body.build_id)
    # Disambiguated conditions skip the model: a second call could propose different conditions (M4 doc §8).
    conditions = [item.model_dump() for item in body.conditions]
    return dict(ai.answer(body.target_type, conditions, build_id=body.build_id), model=None, prompt_version=None)
