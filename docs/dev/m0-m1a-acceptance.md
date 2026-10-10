# M0 + M1a 验收文档

版本：1.0。编写日期：2026-10-10。对应开发文档：[m0-m1a-development.md](m0-m1a-development.md)。

本文档规定 M0 和 M1a 验收的**检查项、操作步骤、预期结果和判定方式**。各项都必须在真实的 PostgreSQL 开发库上执行。用 mock 或在测试中现场查询数据库得到的结果，不能作为验收依据。

---

## 1. 验收规则

- **通过条件**：§4–§9 中标为"必须"的项目全部通过。"记录"类项目只要求留下实测数据，不设通过阈值。
- **证据要求**：每一项都要在 §10 的记录表中填写执行日期、实际结果，以及命令输出或截图的保存位置。没有证据的项目视为未执行。
- **失败处理**：任何一项失败，修复后需要**重新执行该项及受影响的项目**。
  - 涉及错误处理或数据访问的修复，需要重跑 §4–§8 全部项目。
  - 如果某项的预期本身有误，先修改本文档并注明原因，再重新执行。不能只修改结论。
- **固定样例**：§3 中的数值来自批次 `5a76218e…`。如果验收时的批次不是它，说明 M0 没有完成，验收不能开始。

---

## 2. 前置条件

| # | 条件 | 检查方法 |
| --- | --- | --- |
| P1 | `docker compose ps` 显示 postgres 和 neo4j 都是 `healthy` | 命令输出 |
| P2 | `.venv` 按 `requirements.lock` 安装完成 | `uv pip sync` 没有报错 |
| P3 | 被验收的代码已推送到远程分支，并记录 commit SHA | `git log -1` |
| P4 | 后端已在 `127.0.0.1:8000` 启动 | `GET /api/v1/health/live` 返回 200 |

下文用 `$API` 代表 `http://127.0.0.1:8000/api/v1`，`$B` 代表完整批次 ID `5a76218e52001d45e4bd75e099a38780408e873342a14e5db0c86d7bb7a3008a`。

---

## 3. 固定样例与预期值

以下数值在 2026-10-10 从批次 `5a76218e…` 中实际查出。

### S1 四君子汤 `bencaodian:formula:si_jun_zi_tang`

- 名称：四君子汤
- 类型：`formula`；分类：补益剂
- 审核状态：`review_status=editor_reviewed`，`review_status_raw=editor-reviewed`
- 别名：无，返回空数组
- 关系汇总：`ASSOCIATED_WITH_PATTERN` 出边 1，`CITED_IN` 出边 1，`CONTAINS` 出边 4，没有入边
- 实体证据：1 条，`evidence:dba0589b…`，类型 `curated`，`field_path` 为空字符串

组成（`formula_herbs`）：

| position | 中药 | role | dosage_raw | 边 ID 前缀 | 第一条证据 |
| --- | --- | --- | --- | --- | --- |
| 0 | 人参 | jun | 9g | `edge:17d8c5fd` | `evidence:72340d34…`（`/composition/0`） |
| 1 | 白术 | chen | 9g | `edge:e5c70d96` | `/composition/1` |
| 2 | 茯苓 | zuo | 9g | `edge:76dd6516` | `/composition/2` |
| 3 | 甘草 | shi | 6g | `edge:996ed534` | `/composition/3` |

- 每条组成边都有 2 条证据：第一条的 `field_path` 是 `/composition/N`，第二条为空字符串。
- 人参这条边的第二条证据是 `evidence:cf090792…`。

### S2 猪苓汤 `bencaodian:formula:zhu_ling_tang`（冲突样例）

| position | 中药 | role | quality_state |
| --- | --- | --- | --- |
| 0 | 猪苓 | jun | consistent |
| 1 | 泽泻 | **null** | **conflicting** |
| 2 | 茯苓 | chen | consistent |
| 3 | 滑石 | zuo | consistent |
| 4 | 阿胶 | zuo | consistent |

### S3 人参 `bencaodian:herb:ren_shen`

- 关系汇总：`CITED_IN` 出边 1，`CONTAINS` 入边 21
- `herb_formulas` 的总数：21
- 实体证据：2 条。按排序规则，`source_quote` 类型、路径为 `/classical_references/0/passage` 的一条排在前面，`curated` 类型、路径为空的一条排在后面。

### S4 甘草 `bencaodian:herb:gan_cao`（分页样例）

- 注意：同名的饮片 `tcm-mkg:herbal_piece:CHP01118` 是另一个实体，两者不合并。
- `herb_formulas` 的总数为 61。
  - `limit=20, offset=60` 时返回 1 条。
  - `offset=61` 时返回 0 条，状态码仍为 200。

### S5 Bitter medicinal `tcm-mkg:medicinal_property:8fa8553dc501fce26501a2aef0fa5cd798a41a126c217079d78274d05a5d5842`（高度数样例）

- 关系汇总：`HAS_MEDICINAL_PROPERTY` 入边 3,439
- `evidence_total` 为 3,439，`evidence_preview` 恰好 20 条
- 证据分页：
  - `offset=3420, limit=20` 时返回 19 条
  - `offset=3439` 时返回 0 条

### S6 引文证据 `evidence:f1e7866ee0971b80d3d27c8cb7fecf221003b29e87cf8c42d8a6947080d71cec`

- 类型：`kind=source_quote`
- 目标：实体 `bencaodian:herb:gan_cao`
- 路径：`field_path=/classical_references/0/passage`
- `excerpt` 和 `raw_value` 都等于"味甘，平。主五脏六腑寒热邪气，坚筋骨，长肌肉，倍力，金疮肿，解毒。久服轻身延年。"

### S7 黄芪饮片 `tcm-mkg:herbal_piece:CHP01717`（定点修复样例）

- 名称：黄芪
- 别名：9 个，包括"黄耆""炙黄芪"
- 实体证据：`evidence:cddf877aa77babf4552bf15a1790708296568cf7404c4645995f2e5eded22227`，路径 `field_path=/fields`
- 该证据的来源记录：
  - `filename=D6_Chinese_herbal_pieces.tsv`
  - `record_locator=record:1717;lines:1718-1718`
  - `content.repair=remove_exact_extra_empty_column_4`

### S8 不存在但格式合法的 ID

- 实体：`bencaodian:formula:does_not_exist`
- 证据：`evidence:` 后跟 64 个 `0`

---

## 4. M0：批次统一

| ID | 级别 | 步骤 | 预期结果 |
| --- | --- | --- | --- |
| M0-01 | 必须 | `GET $API/health` | `services.database.build_id` 和 `services.neo4j.build_id` 都等于 `$B`；`neo4j.projection=sample` |
| M0-02 | 必须 | `GET $API/stats` | `entities=20374`，`edges=179502`，`evidence=291305`，`business_records=199876`，`build_id=$B` |
| M0-03 | 必须 | `GET $API/graph/sample` | 6 个节点、5 条边，`build_id=$B`，每条边的 `evidence_ids` 都不为空 |
| M0-04 | 必须 | 在开发库中查询旧 schema （schema 名读取配置备份） | 仍然存在，`build` 表中有一行。确认旧批次已保留，可以回滚 |
| M0-05 | 必须 | 在仓库中搜索 旧批次 ID（读取配置备份），排除 `.git` 和 `var/` | 只在 `docs/data-pipeline-report.json` 和 `docs/data-quality-report.json` 两份历史报告中出现 |
| M0-06 | 必须 | 查看 `config/app.example.json` 和 `docs/vastbase-import.md` | 批次、schema、导入命令和 `search_path` 示例都已改为新批次 |
| M0-07 | 必须 | 依次运行 `tests/test_app.py`、`test_database_config.py`、`test_data_pipeline.py`、`test_import_core.py` | 4 个文件全部输出 `PASS` |
| M0-08 | 必须 | 演练回滚：恢复备份的 `app.json`，重启后端，查看 `GET $API/health`；然后再切回新批次 | 回滚后 `database.build_id` 为旧批次。切回后，M0-01 重新通过 |
| M0-09 | 必须 | 查看 `git diff` 中的 `docs/environment-report.json` | 没有密码、token 等凭据 |

---

## 5. M1a 功能

### 5.1 实体详情 `GET /entities/{id}`

| ID | 级别 | 输入 | 预期结果 |
| --- | --- | --- | --- |
| F-01 | 必须 | S1 | 状态 200。`label`、`type`、`category`、`review_status`、`review_status_raw` 都与 S1 一致。`attributes` 是 JSON 对象，不是字符串，且 `treatment_principle.zh` 为"益气健脾"。`aliases` 是空数组。`build_id` 为 `$B` |
| F-02 | 必须 | S1 | `relation_summary` 恰好有 3 项，与 S1 一致，并按 `relation` 排序 |
| F-03 | 必须 | S1 | `evidence_total=1`，`evidence_preview` 中只有 `evidence:dba0589b…` 一条 |
| F-04 | 必须 | S3 | `relation_summary` 恰好有 2 项：`CITED_IN/out/1` 和 `CONTAINS/in/21`。`evidence_preview` 中第一条的类型为 `source_quote` |
| F-05 | 必须 | S5 | `evidence_total=3439`，`evidence_preview` 的长度恰好为 20。响应体小于 50 KB |
| F-06 | 必须 | S7 | `aliases` 有 9 项，包括"黄耆"，按 `name_norm` 排序。`dataset.id=tcm-mkg`，`review_status=unknown` |
| F-07 | 必须 | 依次查询 9 种实体类型各一个实体 | 全部返回 200，`attributes` 都是对象。ICD-11 编码只有 `code` 一个键 |

### 5.2 实体证据分页 `GET /entities/{id}/evidence`

| ID | 级别 | 输入 | 预期结果 |
| --- | --- | --- | --- |
| F-08 | 必须 | S5，`limit=50` 依次翻页到末尾 | 每页最多 50 条，`total` 始终为 3439。所有页合起来正好 3,439 个 ID，没有重复 |
| F-09 | 必须 | S5，`offset=3420`；再用 `offset=3439` | 第一个请求返回 19 条；第二个返回 200 和空 `items` |
| F-10 | 必须 | S5，同一页连续请求两次 | 两次返回的 `items` 顺序完全相同 |
| F-11 | 必须 | S1 | `items` 与 F-03 的预览一致 |

### 5.3 证据详情 `GET /evidence/{id}`

| ID | 级别 | 输入 | 预期结果 |
| --- | --- | --- | --- |
| F-12 | 必须 | `evidence:72340d34…`（S1 人参的组成证据） | 状态 200。`target.kind=edge`，`target.edge.source.label=四君子汤`，`target.edge.target.label=人参`，`relation=CONTAINS`。`raw_value.role=jun`，`raw_value.dosage=9g`。`source_record` 中 `filename=formulas.json`，`record_key=si_jun_zi_tang`。`dataset.id=bencaodian`，`license_statement` 不为空 |
| F-13 | 必须 | `evidence:cf090792…`（S1 人参边的整条记录证据） | `field_path` 为空字符串。`raw_value` 与 `source_record.content` 完全相同，都是四君子汤的整条记录，含 `composition` 数组 |
| F-14 | 必须 | S6 | `kind=source_quote`。`target.kind=entity`，`target.entity.id=bencaodian:herb:gan_cao`。`excerpt` 与 `raw_value` 都等于 S6 中的原文 |
| F-15 | 必须 | S7 的证据 | `raw_value` 是 `fields` 对象，其中 `CHP_ID=CHP01717`。`source_record.record_locator=record:1717;lines:1718-1718`。`source_record.content.repair=remove_exact_extra_empty_column_4`。`content_truncated=false` |
| F-16 | 必须 | 从 S2 猪苓汤→泽泻边的证据中任选一条 | 状态 200，`target.edge.target.label=泽泻` |
| F-17 | 必须 | 抽样约 230 条证据：先按 `evidence.id` 排序，每隔 1,456 条取一条，共 201 条，几乎全是 `curated`；再补充 `source_quote`、`bibliographic` 各 15 条，`bibliographic` 中至少 5 条挂在实体上 | 全部返回 200，没有 `evidence_pointer_invalid`。`source_record.filename` 中都不包含 `/` 或绝对路径 |

### 5.4 模板查询 `GET /relation-queries`

| ID | 级别 | 输入 | 预期结果 |
| --- | --- | --- | --- |
| F-18 | 必须 | `template=formula_herbs`，S1 | `total=4`。4 条路径的顺序为人参、白术、茯苓、甘草。每条边的 `properties` 与 S1 表格一致，其中 `position` 从 0 开始 |
| F-19 | 必须 | 同 F-18 | 每条边的 `evidence_ids` 有 2 项，第一项的 `field_path` 为 `/composition/N`。人参边为 `["evidence:72340d34…", "evidence:cf090792…"]` |
| F-20 | 必须 | 同 F-18 | `nodes` 正好包含 5 个 ID（四君子汤和 4 味药）；`edges` 正好包含 4 个 ID。每条路径中的 `node_ids` 和 `edge_ids` 都能在这两个字典中找到 |
| F-21 | 必须 | `template=formula_herbs`，S2 | 泽泻这条边的 `properties.role` 为 `null`，`quality_state` 为 `conflicting`。其余 4 条与 S2 表格一致 |
| F-22 | 必须 | `template=herb_formulas`，S3 | `total=21`。每条路径的 `node_ids[0]` 是人参；对应边的 `source_id` 是方剂，`target_id` 是人参，即边方向与路径方向相反 |
| F-23 | 必须 | `template=herb_formulas`，S4，按 `limit=20` 翻完 4 页 | 前 3 页各 20 条，第 4 页 1 条，合计 61 条，没有重复。按方剂 `label` 和 `id` 稳定排序 |
| F-24 | 必须 | 链路演示，见下方 | 用 curl 完成：`GET /entities?q=四君子汤&type=formula` → `GET /entities/{id}` → `GET /relation-queries?template=formula_herbs` → 第一条边的第一条证据 `GET /evidence/{id}`。最后一步返回人参的原始组成字段。保存 4 次请求和响应的全文 |

---

## 6. 错误处理

| ID | 级别 | 请求 | 预期结果 |
| --- | --- | --- | --- |
| E-01 | 必须 | `GET /entities/` 加 S8 实体 ID | 404。响应体恰好为 `{"error": {"code": "entity_not_found", "message": <中文>}}` |
| E-02 | 必须 | `GET /evidence/` 加 S8 证据 ID | 404 `evidence_not_found` |
| E-03 | 必须 | `GET /entities/{S8}/evidence`；`GET /relation-queries?template=formula_herbs&entity_id={S8}` | 都返回 404 `entity_not_found` |
| E-04 | 必须 | 格式不合法的实体 ID：`abc`、`bencaodian:unknown_type:x`、`bencaodian:formula:`、长度 201 的 key、`bencaodian:formula:a%20b` | 全部 422 `invalid_query`，不访问数据库（见 S-03） |
| E-05 | 必须 | 格式不合法的证据 ID：`evidence:123`、`evidence:` 后跟 64 个大写十六进制字符、`edge:` 加 64 位十六进制 | 全部 422 `invalid_query` |
| E-06 | 必须 | `template=formula_herbs&entity_id=<S3 人参>`；`template=herb_formulas&entity_id=<S1>` | 都返回 422 `unsupported_entity_type` |
| E-07 | 必须 | `template=formula_patterns`（M1b 模板）、`template=`（空值）、不带 template | 全部 422 `invalid_query` |
| E-08 | 必须 | 新接口上的 `limit=0`、`limit=51`、`offset=-1`、`offset=10001` | 全部 422 `invalid_query`，响应是统一错误格式，不是 FastAPI 默认的 `{"detail": ...}` |
| E-09 | 必须 | 已有接口上的 `GET /entities?limit=51` | 422，且响应改为统一格式。现有的 `test_app.py` 仍然通过 |
| E-10 | 必须 | `GET $API/nope`；`GET $API/entities/x/y/z` | 404 `not_found`，返回 JSON，不是 HTML |
| E-11 | 必须 | 在 4 个新接口上带 `build_id=` 加 64 个 `0` | 全部 409 `snapshot_changed` |
| E-12 | 必须 | 在新接口上带 `build_id=$B` | 正常返回 200 |
| E-13 | 必须 | `build_id=abc` | 422 `invalid_query` |
| E-14 | 必须 | 停止 postgres 容器，请求 4 个新接口各一次；然后重启容器 | 全部 503 `database_unavailable`；`/health/live` 仍为 200；重启后自动恢复，不需要重启后端 |
| E-15 | 必须 | 检查 E-01 到 E-14 所有错误响应的正文 | 不包含 `psycopg2`、`Traceback`、`SELECT`、`/home/`、`qihuang_import` 和任何密码 |

---

## 7. 安全与只读

| ID | 级别 | 步骤 | 预期结果 |
| --- | --- | --- | --- |
| S-01 | 必须 | 用 SQL 注入载荷作为 ID：`bencaodian:formula:x' OR '1'='1`，以及 URL 编码后的版本 | 422（格式校验拦截），不是 500 |
| S-02 | 必须 | 证据 ID 路径穿越：`/evidence/..%2F..%2Fconfig%2Fpostgresql.json` | 404 或 422，返回 JSON；响应中不包含配置文件内容 |
| S-03 | 必须 | 代码审查：新增的 SQL 只使用参数绑定；schema 名只来自 `services.relational()` | 新增文件中没有用 f-string 或 `%` 把输入拼进 SQL。ID 格式校验发生在查询数据库之前 |
| S-04 | 必须 | 代码审查：新查询都通过 `services.relational()` 执行 | 没有另建 `psycopg2.connect`。只读事务、3 秒超时和 build 核对都对新接口生效 |
| S-05 | 必须 | `tests/test_app.py` 中的写入拒绝用例 | 仍然通过 |

---

## 8. 性能与执行计划

| ID | 级别 | 步骤 | 预期结果 |
| --- | --- | --- | --- |
| P-01 | 必须 | 查看 `docs/query-plans/m1a.md` | 包含 §4 每条查询在 S1 和 S5 两个参数下的 `EXPLAIN (ANALYZE, BUFFERS)` 输出；`entity`、`edge`、`evidence`、`alias` 上都没有 Seq Scan |
| P-02 | 必须 | 本机单用户：每个接口先预热 5 次，再采样 50 次。参数取 S1、S5，以及 `herb_formulas` 加 S4 | 每个接口的 P95 ≤ 2 秒（spec §9.2 的最终目标）。失败和超时单独计数，并且必须为 0 |
| P-03 | 记录 | 同 P-02 | 记录每个接口的 P50、P95、最大值和响应体大小，以及硬件和容器资源配置。任何 P95 超过 500 毫秒的接口，都写一句原因分析，供 M6 参考 |

---

## 9. 文档与交付

| ID | 级别 | 检查内容 | 预期结果 |
| --- | --- | --- | --- |
| D-01 | 必须 | `docs/architecture.md` | "已实现接口"表中列出 4 个新接口，错误规则与开发文档 §3.1 一致 |
| D-02 | 必须 | 打开 `http://127.0.0.1:8000/docs` | 4 个新接口都有参数说明和响应模型 |
| D-03 | 必须 | `spec.md` | §1.3 标记为已完成；§4 标注了 M1a 已完成的接口 |
| D-04 | 必须 | `tests/test_api.py` | 覆盖 F、E、S 三类中所有可以自动化的项目，运行结果为 `PASS`；固定样例的值写死在测试中 |
| D-05 | 必须 | `git log` | 每个任务单独提交，提交信息写明任务编号；没有提交 `config/*.json` 或 `var/` 下的私有文件 |
| D-06 | 必须 | markdownlint（使用仓库中的 `.markdownlint.json`） | 新增和修改的 Markdown 文件都通过 |

---

## 10. 验收记录（执行时填写）

被验收的 commit：`________`。执行日期：`________`。执行人：`________`。环境：`________`。

| ID | 结果（通过 / 失败 / 不适用） | 实际值或备注 | 证据位置 |
| --- | --- | --- | --- |
| M0-01 | | | |
| M0-02 | | | |
| … | | | |
| D-06 | | | |

**结论**：

- [ ] 所有"必须"项都已通过，M0 + M1a 验收通过，可以开始 M1b 或 M2。
- [ ] 存在未通过的项目，问题清单如下：

| 问题 | 影响的验收项 | 处理结论 | 复验日期 |
| --- | --- | --- | --- |
| | | | |
