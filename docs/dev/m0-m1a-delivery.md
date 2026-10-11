# M0 + M1a 开发交付说明

文档更新：2026-10-11。开发与真实环境验收日期：2026-10-10。本次文档整理引用已有验收记录，未重新执行数据库或性能测试。

M0 + M1a 已完成：应用与 Neo4j 样例统一到当前批次，新增实体详情、实体证据分页、证据详情和两种组成查询模板。可通过 API 完成“检索四君子汤 → 查看详情 → 查看组成 → 打开证据 → 核对原始字段”的完整链路。

| 项目 | 交付状态 |
| --- | --- |
| 开发依据 | [M0 + M1a 开发文档](m0-m1a-development.md)，来源分支 `docs/m0-m1a-plan` |
| 代码与文档分支 | `codex/m0-m1a-implementation` |
| 受测实现提交 | `cac13964e0ce9ba86b670df59d3c00125b2224de`；后续交付提交只补充文档和报告 |
| 应用批次 | `5a76218e52001d45e4bd75e099a38780408e873342a14e5db0c86d7bb7a3008a` |
| PostgreSQL schema | `qihuang_5a76218e52001d45e4bd75e0` |
| 数据规模 | 20,374 个实体、179,502 条业务关系、291,305 条证据；业务记录合计 199,876 |
| Neo4j | 同批次样例，6 个节点、5 条边；尚非全量图投影 |

## 已完成功能

路径统一以 `/api/v1` 开头。四个新接口均接受可选 `build_id`，成功响应包含实际读取的批次；请求批次不匹配时返回 409 `snapshot_changed`。

| 方法与路径 | 已实现内容 |
| --- | --- |
| `GET /entities/{id}` | 九种实体类型的原始属性、别名、关系汇总、实体证据总数及前 20 条预览 |
| `GET /entities/{id}/evidence` | 实体证据分页；`limit` 默认 20、范围 1～50，`offset` 范围 0～10000 |
| `GET /evidence/{id}` | 证据目标、JSON Pointer 原始值、来源记录、数据集版本、许可和署名 |
| `GET /relation-queries` | `formula_herbs` 查询方剂组成，`herb_formulas` 反查收录中药的方剂；返回本页路径、节点、边及证据 ID |

ID 与分页参数先校验，再建立数据库连接。每个新请求在同一个只读、可重复读事务内完成查询，使用参数绑定、3 秒语句超时和库内批次核对。

错误统一返回 `{"error":{"code":"…","message":"中文提示"}}`。已处理不存在的实体或证据、未知路径、方法不支持、批次变更、非法参数、模板类型不匹配、证据定位失效和依赖不可用。错误码与 HTTP 状态的完整映射见[架构说明](../architecture.md)。

## 启动与演示

以下命令适用于已导入当前批次的开发环境，在仓库根目录执行。全新环境的依赖安装和导入顺序见[启动说明](../bootstrap.md)及[数据导入说明](../vastbase-import.md)。私有配置不在 Git 中，不能仅靠拉取代码恢复数据库和凭据。

```sh
python3 scripts/setup_services.py
docker compose up -d --wait
.venv/bin/python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

打开 `http://127.0.0.1:8000/docs` 查看参数及响应模型。已有 `config/app.json` 不会被初始化脚本覆盖；应核对其批次与上表一致。

在另一终端演示四君子汤到人参组成原值的链路：

```sh
API=http://127.0.0.1:8000/api/v1
FORMULA=bencaodian:formula:si_jun_zi_tang
EVIDENCE=evidence:72340d34a2f1acaf0dee984198dcb9ea60beda6d11d8168122cecd6c1f19e33c

curl --fail --silent --show-error --get "$API/entities" \
  --data-urlencode 'q=四君子汤' --data-urlencode 'type=formula'
curl --fail --silent --show-error "$API/entities/$FORMULA"
curl --fail --silent --show-error --get "$API/relation-queries" \
  --data-urlencode 'template=formula_herbs' --data-urlencode "entity_id=$FORMULA"
curl --fail --silent --show-error "$API/evidence/$EVIDENCE"
```

示例中的证据 ID 是本批次人参组成边的第一条证据。实际调用应从模板响应的 `edges[edge_id].evidence_ids` 取 ID；`edges` 是以边 ID 为键的字典。最后一步的 `raw_value` 包含 `herb_key=ren_shen`、`role=jun`、`dosage=9g`。[四次实际请求和完整响应](../acceptance/m1a-chain.json)已保存。

## 代码与验收入口

| 文件 | 职责 |
| --- | --- |
| [backend/app.py](../../backend/app.py) | 路由、参数校验、统一错误响应 |
| [backend/services.py](../../backend/services.py) | 配置、只读事务、批次检查和错误状态映射 |
| [backend/queries.py](../../backend/queries.py) | 详情与关系查询、证据排序、JSON Pointer 解析和结果组装 |
| [backend/schemas.py](../../backend/schemas.py) | 响应模型及 OpenAPI 契约 |
| [tests/test_api.py](../../tests/test_api.py) | 固定样例、分页、错误、安全边界与可选停机演练 |
| [tests/measure_m1a.py](../../tests/measure_m1a.py) | 真实 HTTP 性能、curl 链路和 SQL 执行计划记录 |

复验功能与既有回归：

```sh
.venv/bin/python tests/test_app.py
.venv/bin/python tests/test_database_config.py
.venv/bin/python tests/test_data_pipeline.py
.venv/bin/python tests/test_import_core.py
.venv/bin/python tests/test_api.py
```

数据库和 Neo4j 样例须先就绪。性能与故障演练还需要后端在 `127.0.0.1:8000` 运行：

```sh
.venv/bin/python tests/measure_m1a.py
.venv/bin/python tests/test_api.py --with-outage
```

性能脚本会更新仓库中的执行计划、链路和性能报告。`--with-outage` 会短暂停止本机 PostgreSQL，并在 `finally` 中恢复容器；不要在其他工作依赖该数据库时运行。普通测试不主动停库。

## 已有验收结果

以下为 2026-10-10 的实测结果，完整逐项记录见[验收文档](m0-m1a-acceptance.md)。

| 检查 | 结果 | 证据 |
| --- | --- | --- |
| 原有回归 | 四个测试文件全部通过 | [回归输出](../acceptance/m1a-regression.json) |
| 新 API | 固定样例、错误与安全边界通过；3,439 条证据分页无重复、231 条证据抽样通过、甘草 61 条反查分页通过 | [测试输出](../acceptance/m1a-tests.txt) |
| 查询计划 | 30 份实际计划；实体、关系、证据、别名四张表无顺序扫描 | [执行计划](../query-plans/m1a.md) |
| HTTP 性能 | 8 个场景各预热 5 次、采样 50 次；400 次采样零失败，各场景 P95 为 7.174～14.617 ms | [性能及环境记录](../acceptance/m1a-performance.json) |
| 停机恢复 | 四个新接口返回统一 503，存活检查保持 200；恢复 PostgreSQL 后无需重启后端 | [停机记录](../acceptance/m1a-outage.json) |
| 批次回滚 | 旧 schema 保留，恢复旧配置并重启后端后验证通过，再切回当前批次 | [运行记录](../acceptance/m0-runtime.json) |

## 数据语义与回滚

- 剂量保留来源原文，不换算；冲突角色保持 `null`。猪苓汤中泽泻的 `quality_state=conflicting`，不猜测其角色。
- 证据排序先按类型，再按字段指针是否为空、指针字典序和 ID；具体字段证据排在整条记录证据之前。
- F-13 原验收预期误认了来源文件。人参边的第二条证据实际来自 `relationships.json`；已修正文档并复验，未修改原始数据。
- 来源 JSON 超过 64 KB 时，返回 `content=null` 和 `content_truncated=true`。`raw_value` 保留引用原值，因此这不是整个响应体的大小上限。
- M0 切换前的配置备份位于本机 `var/app.json.previous.bak`。恢复为 `config/app.json` 后重启后端即可回滚；再次切换前应保存当前配置。备份文件、数据库内容和凭据不会随 Git 推送。

## 未完成范围与后续工作

M1b 的检索排序、通用关系列表、其他五个关系模板、来源目录、业务视图和独立只读账号尚未实现。前端详情页面、Neo4j 全量图投影、真实 AI 功能和 Vastbase 最终迁移继续按 [spec.md](../../spec.md) 推进。

当前性能只代表本机单用户，未代替最终 5 并发验收。两个关系模板当前最多匹配 61 条，在内存中排序或分页；规模扩大后应改为 SQL 分页。应用每请求建立一个数据库连接，是否引入连接池应依据并发实测。

模型未配置时，健康状态可以为 `degraded`，环境验证报告为 `incomplete`；这不等于已通过的 PostgreSQL 和 Neo4j 验证失败。当前仅验收 PostgreSQL 开发环境，不能据此宣称 Vastbase、全量图谱或真实 AI 已完成。
