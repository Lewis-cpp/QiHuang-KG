# QiHuang-KG 后续开发规格（spec）

版本：0.1（草案）。编写日期：2026-10-10。适用范围：从当前状态到最终交付的剩余开发工作。

本文档把 [开发计划](docs/development-plan.md) 第 6 节尚未完成的任务（T09–T22，以及 T02/T03/T04/T08 的剩余部分）细化为可直接编码和验收的规格：接口契约、查询规则、图投影、AI 链路、测试与里程碑。范围边界仍以 [首版范围冻结](docs/scope-freeze.md) 为准，数据模型以 [v2 架构](docs/architecture.md) 和 [共享 DDL](docs/schema-vastbase.sql) 为准；本文与它们冲突时，先修订本文再动代码。

---

## 1. 当前基线

### 1.1 已完成

| 方面 | 状态 | 依据 |
| --- | --- | --- |
| 数据 | 两源清洗完成：20,374 实体、179,502 业务关系、291,305 证据，业务记录合计 199,876 | `prepare_data.py`；`test_data_pipeline.py` 于 2026-10-10 重跑通过 |
| 关系库 | PostgreSQL 18.6 开发库已入库，每个批次一个独立 schema | `docs/vastbase-import.md` |
| 图库 | Neo4j 5.26，四君子汤样例：6 节点、5 关系 | `verify_environment.py` |
| 后端 | 5 个接口：`health/live`、`health`、`stats`、`entities`、`graph/sample` | `backend/app.py` |
| 前端 | M2 已实现：检索、详情、证据、来源、统计五个页面 | `frontend/src/`，交付说明见 [docs/dev/m2-delivery.md](docs/dev/m2-delivery.md) |
| 模型 | 客户端、配置模板和验证脚本已就绪，未发起真实调用 | `backend/model_client.py` |

开发计划第 1–2 周的阶段出口已在 PostgreSQL 上达成，只差模型的一次真实调用。下一阶段从第 3 周（业务 API）开始。

### 1.2 实测的数据特征（影响设计）

以下数字来自当前批次 `c0406848…`（2026-10-16 起；与 `5a76218e…` 相比只更正了十枣汤的大戟，引文证据多 3 条）：

- **实体分布**
  - 本草典：中药 365、方剂 112、证候 84、古籍 38，均为 `editor_reviewed`。
  - TCM-MKG：中成药 8,977、饮片 6,207、ICD-11 编码 2,758、术语 1,810、药性 23，均为 `unknown`。
- **超高度数节点普遍存在**
  - 入度：`Bitter medicinal` 3,439，`甘草`（饮片）2,278。
  - 出度：单个中成药最多 160。
  - 因此任何"列出全部邻居"的接口都**必须分页或截断**，不能一次返回全部。
- **方剂组成**
  - `CONTAINS` 共 751 条，属性含 `dosage_raw`、`position`、`role`。
  - 角色分布：jun 144、chen 205、zuo 301、shi 100。
  - 唯一冲突边是猪苓汤→泽泻，`role=null` 且 `quality_state=conflicting`。
- **组合查询的可用字段**
  - 方剂：`category` 共 17 类，另有 `subcategory`、`source_text_key`。
  - 古籍：`dynasty_zh` 写法不统一，有"宋 / 北宋 / 南宋"等。
  - 中药：`nature` 共 8 种取值，另有 `flavors`、`category`。
  - 中成药：`Routes_of_administration` 分 Oral / Topical / Injection。
- **证据**
  - 证据类型：`curated` 290,346、`bibliographic` 531、`source_quote` 431。
  - `field_path` 为空字符串时表示整条记录。
- **ID 字符集**
  - 实体与证据 ID 只含 `[A-Za-z0-9_.:-]`，最长 91 字符。
  - 因此可以直接作为 URL 路径参数。

### 1.3 批次统一（M0 已完成，2026-10-10）

应用配置、示例配置、PostgreSQL 和 Neo4j 样例已统一到 `5a76218e…` 批次。统计仍为 199,876 条业务记录，旧 schema 和私有配置备份保留，真实 HTTP 回滚及恢复已验证。

`docs/data-quality-report.json` 和 `docs/data-pipeline-report.json` 保留历史内容。`tests/test_app.py` 当前仍断言 `graph.projection == "sample"`，M3 引入全量投影后再同步修改。

---

## 2. 全局约定（所有新接口适用）

### 2.1 响应与错误

- 前缀统一为 `/api/v1`，UTF-8 JSON，所有业务接口只读。
- **成功响应**
  - 沿用现有扁平风格：主体字段加 `build_id`。
  - 分页响应带 `items, total, limit, offset`。
  - 不改动已上线接口的结构。
- **错误体统一为** `{"error": {"code": "...", "message": "..."}}`。
  - FastAPI 默认的 422 校验错误要转换成这个格式，`code=invalid_query`。
  - 未知的 `/api/*` 路径返回 JSON 404，`code=not_found`。

| HTTP | code | 场景 |
| --- | --- | --- |
| 404 | `entity_not_found` / `evidence_not_found` | ID 格式合法但不存在 |
| 409 | `snapshot_changed` | 请求携带的 `build_id` 与当前配置不一致 |
| 422 | `invalid_query` / `invalid_type` / `unsupported_entity_type` | 参数越界、白名单外取值、模板与实体类型不匹配 |
| 503 | `database_unavailable` / `neo4j_unavailable` / `projection_not_ready` / `model_*` | 依赖不可用或超时 |
| 500 | `internal_error` | 未预期的异常；不回传堆栈、路径或凭据 |

### 2.2 分页与上限

- `limit` 默认 20，上限 50。`offset` 取 0–10000（与现有 `/entities` 一致）。
- 排序必须稳定，最后一个排序键总是 `id`。
- 图接口不返回 `total`，改用 `truncated` 标志加上限值说明结果是否完整。

### 2.3 批次一致性

- 业务 GET 接口都接受可选参数 `build_id`；与当前批次不一致时返回 409 `snapshot_changed`。
- 前端在首次响应中拿到 `build_id`，之后的请求都带上。收到 409 时清空缓存并提示刷新。
- 只要图投影的 `build_id` 与关系库不同，图接口就返回 503 `projection_not_ready`，不混用两个批次的数据。

### 2.4 安全边界

- SQL 一律参数绑定。schema 名只能来自经过校验的配置，并用 `sql.Identifier` 引用。
- Cypher 只用固定模板，客户端不能指定标签、关系类型或路径长度。
- 模型输出永远不作为 SQL、Cypher 或文件路径执行。
- 凭据不进入前端、日志、报告或 Git。

---

## 3. 里程碑总览

周次接续开发计划的相对周次。截止日期尚未确定，所以"参考日期"一列**假设 2026-10-12（周一）开工、每周 5 个工作日**，只用于排期，不代表承诺。

| 里程碑 | 计划周次 | 参考日期 | 覆盖任务 | 出口标准（摘要） |
| --- | --- | --- | --- | --- |
| M0 基线整理 | 第 3 周初 | 10-12 | §1.3 | 批次 ID 统一；全部测试在当前批次上通过 |
| M1 关系库业务 API | 第 3 周 | 10-12 → 10-16 | T09 T10 T11 | 不经过前端，用 curl 完成"检索 → 详情 → 组成 → 证据"；只读账号写入失败有实测记录 |
| M2 资料检索页面 | 第 4 周 | 10-19 → 10-23 | T14（检索/详情/来源/统计） | 方剂与药物详情可往返跳转；空结果、冲突、缺失、错误状态都可见 |
| M3 Neo4j 全量投影与图谱 | 第 5 周 | 10-26 → 10-30 | T03 剩余、T12 T13 T14（图谱） | 全量投影摘要与主库一致；图请求实际经过 Neo4j；两跳路径可演示 |
| M4a AI 自然语言查询 | 第 6 周 | 11-02 → 11-06 | T04 剩余、T15 T18 | 真实模型调用通过；支持范围内的问题转成可核对条件并执行 |
| M4b AI 方剂解释 | 第 7 周 | 11-09 → 11-13 | T16 T17 T18 | 引用 100% 可回查；冲突项不被写成确定结论；失败时有降级 |
| M5 联调与评测 | 第 8 周 | 11-16 → 11-20 | T19 T20（AI 与功能部分） | P0 用例全部通过；冻结评测集已跑出结果；**停止新增范围** |
| M6 Vastbase 迁移与性能 | 第 9 周 | 11-23 → 11-27 | T02 T08 剩余、T20（性能/恢复） | Vastbase 实例完成真实验收；两库摘要一致；性能报告 |
| M7 交付 | 第 10 周 | 11-30 → 12-04 | T21 T22 | 四项硬性指标逐项签收 |

**建议提前做一项**：Vastbase 环境的申请和驱动探测（`import_vastbase.py` 已经支持 `probe`）。M1 期间就应该跑一次连接和建表探测，问题越早暴露越好，见 §10。

---

## 4. M1：关系库业务 API（T09–T11）

M1 分两步实施：

- **M1a（2026-10-10 已实现）**：统一错误处理；实体详情、实体证据分页、证据详情；`formula_herbs` 和 `herb_formulas` 两个模板。
  - 开发文档：[docs/dev/m0-m1a-development.md](docs/dev/m0-m1a-development.md)
  - 验收文档：[docs/dev/m0-m1a-acceptance.md](docs/dev/m0-m1a-acceptance.md)
- **M1b（2026-10-11 已实现）**：本节其余内容；存储过程仍待 §11 确认。
  - 交付说明：[docs/dev/m1b-delivery.md](docs/dev/m1b-delivery.md)

注意：实体证据数量差别很大，最多一个实体有 3,439 条。所以 M1a 中，实体详情只预览前 20 条证据，另外提供 `GET /entities/{id}/evidence` 分页接口。这一点对 §4.3 做了补充。

### 4.1 接口清单

| 方法与路径 | 状态 | 说明 |
| --- | --- | --- |
| `GET /entities` | M1b 已完成 | 增加命中排序、命中说明和 `dataset` 过滤 |
| `GET /entities/{id}` | M1a 已完成 | 实体详情与证据预览 |
| `GET /entities/{id}/evidence` | M1a 已完成 | 实体证据分页 |
| `GET /entities/{id}/relations` | M1b 已完成 | 按关系类型和方向分页列出邻居（关系库） |
| `GET /relation-queries` | M1b 已完成 | M1a 实现 `formula_herbs`、`herb_formulas`；M1b 补齐其余 5 个模板 |
| `GET /evidence/{id}` | M1a 已完成 | 证据详情与原始值 |
| `GET /datasets` | M1b 已完成 | 来源、版本、许可与署名 |
| `GET /entities/{id}/formula-notes` | 已完成 | 仅限方剂：关联证候的主症、次症、舌象、脉象，以及各组成药物的禁忌、安全提示、孕期、哺乳期、儿童、用量范围字段；均为入库字段原样返回，其他类型返回 422 `unsupported_entity_type` |
| `GET /stats` / `GET /health` | M1b 已完成 | 健康检查补充 `projection` 的取值（`sample` / `full` / `not_ready`） |

### 4.2 `GET /entities`（改进）

- **参数**：`q`（≤100 字）、`type?`（9 种实体类型白名单）、`dataset?`（`bencaodian` / `tcm-mkg`）、`limit`、`offset`。
- **查询词规范化**：沿用 NFKC、去首尾空格、`casefold`，`LIKE` 中的通配符转义为字面字符。
- **排序**（依次比较）：
  1. 名称精确命中
  2. 别名精确命中
  3. 名称前缀命中
  4. 别名前缀命中
  5. 名称或别名子串命中

  同一级别内按 `name_norm, id` 排序。用 SQL `CASE` 计算 `match_rank`。
- **每项新增字段**：`match: {field: "name"|"alias", text: "命中的原文"}`。一个实体有多个别名命中时也只出现一次（先按实体去重，再分页）。
- **`q` 为空**：按类型目录返回，沿用当前行为。
- **性能**：先在 2 万实体上用 `LIKE` 实测 P95。超过 2 秒时再评估 `pg_trgm`，但 Vastbase 能否兼容要在 M6 前验证，所以不能在实测前引入。

### 4.3 `GET /entities/{id}`

```json
{
  "id": "bencaodian:formula:si_jun_zi_tang",
  "type": "formula",
  "label": "四君子汤",
  "dataset_id": "bencaodian",
  "category": "补益剂",
  "review_status": "editor_reviewed",
  "review_status_raw": "editor-reviewed",
  "attributes": { "description_zh": "...", "treatment_principle": {"zh": "益气健脾", "en": "..."} },
  "aliases": [{ "name": "...", "source_record_id": "...", "field_path": "..." }],
  "evidence_ids": ["evidence:..."],
  "relation_summary": [
    { "relation": "CONTAINS", "direction": "out", "count": 4 },
    { "relation": "CITED_IN", "direction": "out", "count": 1 }
  ],
  "build_id": "..."
}
```

- `attributes` 是 `attributes_json` 解析后的对象，原样返回，后端不翻译、不推断。前端负责字段中文名和显示顺序，配置见 §5。
- `relation_summary` 用一条 `GROUP BY` 查询得到，前端靠它决定显示哪些关系分区。
- 实体不存在时返回 404 `entity_not_found`。

### 4.4 `GET /entities/{id}/relations`

- **参数**：`relation`（必填，7 种关系类型白名单）、`direction`（`out` / `in`，必填）、`limit`、`offset`。
- **校验**：关系类型与实体类型不匹配时（比如中药使用 `HAS_HERBAL_PIECE`）返回 200 空列表，不报 422，因为这只是没有数据。
- **每项字段**：`edge {id, relation, properties, quality_state, evidence_ids}` 和 `neighbor {id, type, label, category}`。
- **排序**
  - `CONTAINS` 出边（方剂组成）按 `properties.position` 排序，为空的排在最后，再按邻居 `label`、`id`。
  - `HAS_MEDICINAL_PROPERTY` 出边按邻居 `category`（药性类别）、`label`、`id`，与 `piece_properties` 一致。
  - `CONTAINS` 入边（药物反查方剂）和其他关系按邻居 `label`、`id`。同一味药在不同方剂中的位置不可比较，所以入边不按位置排序。
  - 文本排序键按码位顺序比较（`COLLATE "C"`），不随数据库区域设置变化。
- 返回 `total`。甘草这类节点会有数千条，分页是必需的。

### 4.5 `GET /relation-queries`

**参数**：`template`（白名单）、`entity_id`、`limit`、`offset`。只在关系库上执行。

| template | 输入类型 | 路径 | 排序 |
| --- | --- | --- | --- |
| `formula_herbs` | formula | 方剂 →CONTAINS→ 中药 | position, label |
| `herb_formulas` | herb | 中药 ←CONTAINS← 方剂 | label |
| `formula_patterns` | formula | 方剂 →ASSOCIATED_WITH_PATTERN→ 证候 | label |
| `herb_patterns_via_formula` | herb | 中药 ←CONTAINS← 方剂 →ASSOCIATED_WITH_PATTERN→ 证候 | 证候 label, 方剂 label |
| `patent_medicine_pieces` | patent_medicine | 中成药 →HAS_HERBAL_PIECE→ 饮片 | label |
| `piece_patent_medicines` | herbal_piece | 饮片 ←HAS_HERBAL_PIECE← 中成药 | label |
| `piece_properties` | herbal_piece | 饮片 →HAS_MEDICINAL_PROPERTY→ 药性 | class, label |

- **响应**：`paths[]`，每条为 `{node_ids:[...], edge_ids:[...]}`；另附本页涉及的 `nodes{}` 和 `edges{}` 字典（边带 `properties`、`quality_state`、`evidence_ids`），以及 `total`。
- **两跳路径**按完整路径去重。同一个证候经过不同方剂到达时，保留为不同路径。
- **固定说明文字**：两跳结果的说明只能是"该药出现在某方剂中，该方剂在来源数据中关联某证候"，不能生成"该药治疗该证候"。
- **错误**：输入实体类型与模板不符时返回 422 `unsupported_entity_type`。

### 4.6 `GET /evidence/{id}`

```json
{
  "id": "evidence:...",
  "kind": "curated",
  "target": { "entity_id": "...", "edge_id": null },
  "field_path": "/composition/1",
  "raw_value": { "...": "按 field_path 从 content_json 中解析出的原始值" },
  "excerpt": null,
  "source_record": {
    "id": "...", "filename": "formulas.json", "record_key": "...",
    "record_locator": "...", "file_sha256": "..."
  },
  "dataset": { "id": "bencaodian", "title": "...", "version_label": "...", "attribution": "..." },
  "build_id": "..."
}
```

- `raw_value` 由后端按 JSON Pointer 从 `source_record.content_json` 解析得到。`field_path` 为空时返回整条记录；记录超过 64 KB 时截断，并带上 `raw_value_truncated: true`。
- `filename` 只返回数据集内的相对名称，不暴露服务器路径。不接受客户端传入文件路径。

### 4.7 `GET /datasets`

返回 `dataset` 表的全部字段，加上每个来源的实体数、关系数和 source_record 数，用于来源页和许可说明。

### 4.8 数据库工作（T09、T11）

- **执行计划**：对 §4.2–4.6 的每条查询记录 `EXPLAIN (ANALYZE, BUFFERS)`，结果存到 `docs/query-plans/`。只有执行计划显示需要时才加索引。预计用得上的索引：
  - `edge(source_id, relation, target_id)` 和 `edge(target_id, relation, source_id)`：已存在
  - `alias(entity_id)`：现有主键的前缀已覆盖
  - `evidence(edge_id, id)` 和 `evidence(entity_id, id)`：已存在
- **业务视图**（课程展示用，同时供 API 复用）
  - `v_formula_composition`：方剂、药、剂量原文、角色、位置、质量状态
  - `v_entity_relation_summary`
  - 视图写入 `docs/schema-vastbase.sql` 之后的追加 DDL 文件 `docs/schema-views.sql`，保持两库共享。导入时在同一事务中创建并校验；复用已有 schema 时只追加视图。
- **维护事务示例**：直接引用现有的单事务导入流程，并补一段"导入失败后回滚、旧批次不受影响"的演示记录。不额外建在线写接口。记录见 `docs/acceptance/m1-import-rollback.json`。
- **存储过程**：只有任务书明确要求时才补，见 §11 待确认事项。
- **只读账号（T11）**
  - `qihuang_reader` 角色：只授予目标 schema 的 `USAGE` 和 `SELECT` 权限，并设置 `default_transaction_read_only=on`。`setup_postgres.py` 生成它的私有凭据；`setup_reader.py` 在数据库中创建角色并授权，因为数据库要在导入之后才有目标 schema。
  - 应用改用这个账号连接，导入账号只供脚本使用。
  - 测试用这个账号真实执行 `INSERT`、`UPDATE`、`CREATE`，断言都因权限不足失败（错误码 `42501`），不能只检查配置文件。默认只读会先以 `25006` 拒绝写入，所以测试先显式开启读写事务，确认拦住写入的是权限本身。

### 4.9 实现结构

- `backend/services.py` 已有约 160 行。新增查询拆到 `backend/queries.py`，放 SQL 与结果组装；`services.py` 保留连接和配置。
- 路由仍放在 `app.py`。路由超过约 15 个时，再拆成 `backend/routes/`。
- 请求和响应用 Pydantic 模型声明，OpenAPI 自动生成，不另写一份接口文档。

### 4.10 M1 出口

- 每个接口都有成功、空结果、404、422 用例，加在 `tests/test_api.py`，用 TestClient 连接真实开发库。
- 用 curl 完成一条完整链路：搜索"四君子汤"→ 打开详情 → `formula_herbs` → 打开任意一条边的证据，并看到原始字段值。
- 猪苓汤→泽泻这条冲突边在接口中如实返回 `quality_state=conflicting` 和 `role=null`。
- 只读账号的写入失败测试通过。

---

## 5. M2：资料检索页面（T14，非图谱部分）

状态：**已确认并实现**（2026-10-11）。§5.0 六项均按默认做法执行；交付说明见 [docs/dev/m2-delivery.md](docs/dev/m2-delivery.md)。

### 5.0 待确认的决定

下面几项是编写本节时选的默认做法，确认或修改后再开工。

| # | 问题 | 默认做法 | 另一种做法 |
| --- | --- | --- | --- |
| 1 | 是否改后端 | **不改**。M2 只调用 §4 已上线的接口 | 为统计页新增"文件原始行 / 接受 / 拒收"接口（见 §5.9） |
| 2 | 现有单页的去留 | 首页简介和检索合并为 `/`；运行状态移到 `/stats`；"四君子汤关系样例"删除，由详情页的关系分区代替 | 保留样例区块到 M3 |
| 3 | 统计页的"原始行数" | 用 `/datasets` 中每个来源的 `source_records` 计数，标为"来源记录"，与"有效业务记录"分开显示 | 同第 1 项的另一种做法 |
| 4 | 详情页关系分区的翻页是否写进 URL | **不写**。刷新详情页后各分区回到第 1 页 | 写进查询参数，刷新后保留页码 |
| 5 | 来源中的禁忌、孕期、安全提示等字段 | 原文显示在"来源中的注意事项"分区，并固定标注"来源原文，仅供学习参考，不构成用药建议" | 首版不显示这些字段 |
| 6 | 前端测试 | 不引入前端测试框架（与 §8.1 一致）；用 `vue-tsc` 加浏览器逐项核对，结果和截图写入交付说明 | 引入 Playwright 冒烟测试 |

### 5.1 范围

- **包含**：检索、实体详情（属性、别名、关系分区、证据）、证据详情、来源、统计和运行状态五个页面，以及它们共用的请求封装、分页和状态组件。
- **不包含**：图谱画布（M3）、AI 查询与解释（M4）、两跳模板 `herb_patterns_via_formula` 的页面入口（留给 M3 的路径查询）、移动端专门适配、账户。
- **接口**：只调用 §4 已上线的接口。实现中如果发现必须改接口，先修订本文再写代码。
- **`/graph/sample`** 接口保留，供 M3 之前的测试使用；页面不再调用它。

### 5.2 技术与依赖

- 新增 `vue-router` 4.x，`package.json` 中写**精确版本**，并提交 `package-lock.json` 的变更。使用 `createWebHistory`。
- 不引入 UI 组件库、Pinia、axios 或 CSS 框架。状态放在各页面组件里，跨页面只共享 `build_id`。
- 接口类型在 `api/types.ts` 中手写，字段名与 `backend/schemas.py` 一致，不引入 OpenAPI 代码生成。
- 现有 `vite.config.ts` 的 `/api` 代理不变。Vite 开发服务和 `vite preview` 默认就有 history 回退；生产托管按 §9.3 由 FastAPI 回退。

```text
frontend/src/
  main.ts
  router.ts
  api/client.ts        请求封装：错误体解析、build_id、取消请求
  api/types.ts         与 backend/schemas.py 对应的类型
  labels.ts            类型、来源、审核状态、关系、证据类型、角色的中文名
  fieldLabels.ts       各实体类型的字段中文名与显示顺序
  components/          StateView、Pager、EvidenceLinks、ReviewBadge、AttributeValue 等
  views/               SearchView、EntityView、EvidenceView、DatasetsView、StatsView、NotFoundView
```

### 5.3 路由

| 路由 | 页面 | 调用的接口 | URL 中保存的状态 |
| --- | --- | --- | --- |
| `/` | 检索 | `GET /entities` | `q`、`type`、`dataset`、`page` |
| `/entity/:id` | 详情 | `GET /entities/{id}`；每个关系分区调用 `GET /entities/{id}/relations`；证据分区调用 `GET /entities/{id}/evidence` | 无（见 §5.0 第 4 项） |
| `/evidence/:id` | 证据 | `GET /evidence/{id}` | 无 |
| `/datasets` | 来源 | `GET /datasets` | 无 |
| `/stats` | 统计与运行状态 | `GET /stats`、`GET /health`、`GET /datasets` | 无 |
| `/graph/:id` | 图谱 | M3 实现；M2 不注册这个路由，页面上也不出现图谱入口 | — |
| 其他路径 | 页面不存在 | 无 | — |

- 路径中的 ID 用 `encodeURIComponent` 编码。ID 字符集见 §1.2，含 `:` 也能直接使用。
- 所有跳转都用 `RouterLink` 生成真实的 `<a href>`，可以中键或在新标签页打开。
- 切换路由后，`document.title` 设为"页面名称 · 岐黄知图"，焦点移到页面的 `<h1>`。
- 页头导航：检索、来源、统计。

### 5.4 公共行为

#### 请求封装（`api/client.ts`）

- 解析 §2.1 的错误体，把 `code` 和 `message` 交给页面。页面只显示 `message`，不显示堆栈或原始响应。
- `fetch` 本身抛出异常（服务没启动、网络断开）时，按 503 处理，提示"无法连接服务，请检查后端是否启动"。
- 每个页面在离开或重新请求时取消上一次请求（`AbortController`），只渲染最后一次请求的结果。

#### 批次一致性（§2.3）

- `build_id` 保存在 `sessionStorage`。第一次成功响应时写入，之后所有接受 `build_id` 的请求都带上它。
- `/stats` 和 `/health` 不接受 `build_id` 参数。统计页拿到 `stats.build_id` 后与保存的值比较，不一致时按 409 处理。
- 收到 409 `snapshot_changed` 时，页面顶部显示横幅"数据已更新到新批次，请刷新"。点击"刷新"会清除保存的 `build_id` 并重新加载当前路由，不自动刷新。
- `sessionStorage` 读写都包在 `try/catch` 里；不可用时只在内存中保存。

#### 页面状态（`StateView`）

每个页面和每个独立加载的分区都有以下状态：

| 状态 | 触发条件 | 显示 |
| --- | --- | --- |
| 加载中 | 请求进行中 | "加载中…"，加 `aria-busy` |
| 空结果 | 成功但 `items` 为空或 `total=0` | 说明当前条件下没有记录，并给出可做的操作（换关键词、去掉筛选） |
| 未找到 | 404 `entity_not_found` / `evidence_not_found`；路径中的 ID 格式不合法（422） | "未找到该记录"，加返回检索的链接 |
| 服务不可用 | 503 或网络失败 | 后端 `message` 加"重试"按钮 |
| 批次已更新 | 409 | 见上面的横幅 |
| 其他错误 | 500 或其他 422 | 后端 `message` |

- 详情页的各个关系分区和证据分区独立加载，某个分区失败不影响页面其他部分。
- 结果区域用 `aria-live="polite"`。

#### 分页（`Pager`）

- 每页 20 条，显示"第 x / y 页，共 n 条"和上一页、下一页按钮。
- 接口限制 `offset ≤ 10000`。可达的最后一页是 `floor(10000 / 20) + 1 = 501`。总数超出时，在最后可达页提示"结果过多，请细化条件"，不提供更后面的页码。

#### 中文名（`labels.ts`）

- 实体类型、来源、审核状态沿用现有 `App.vue` 中的映射。
- 证据类型：`curated` 整理数据、`bibliographic` 书目、`source_quote` 原文引用。
- 君臣佐使：`jun` 君、`chen` 臣、`zuo` 佐、`shi` 使；`null` 显示"来源未标注"。
- 映射里没有的取值，原样显示，不丢弃也不猜测。

### 5.5 检索页 `/`

- **表单**：关键词（`maxlength=100`）、实体类型（全部加 9 种）、来源（全部、本草典、TCM-MKG）、"检索"按钮。
  - 提交或改变筛选条件时，把条件写进 URL（`page` 回到 1）。页面根据 URL 发请求，所以浏览器后退和刷新都能恢复结果。
- **结果项**
  - 名称链接到 `/entity/:id`，后面是类型标签。
  - 分类（为空时显示"来源未提供分类"）、来源、审核状态。
  - 命中说明：`match.field=name` 显示"名称命中"；`alias` 显示"别名命中：{text}"；`match` 为 `null`（类型目录）时不显示。
- **初始状态**：关键词和类型都为空时不发请求，显示简介和三个示例检索链接："四君子汤"、"甘草"、"猪苓汤"。它们是 `/?q=...` 形式的检索链接，不写死实体 ID。
- **只选类型、不填关键词**：按 §4.2 返回该类型的目录，可以翻页浏览。
- 简介文案中"完整详情……将在后续阶段实现"改为与当前功能一致的说明。

### 5.6 详情页 `/entity/:id`

#### 页头

名称、类型标签、来源、审核状态、分类，以及等宽小字的实体 ID（带复制按钮）。

#### 别名

- 列出 `aliases[].name`，按接口顺序显示。数量超过 20 个时折叠，显示"展开全部"。
- 别名来自来源数据，审核状态与实体一致，不另加说明。

#### 属性

- 按 `fieldLabels.ts` 中该类型的字段顺序显示。
- 已配置但值为 `null` 或空字符串的字段，显示"来源未提供"。
- 未配置的字段放进"其他属性"折叠区，值为空的不显示。
- **值的显示规则**（`AttributeValue`）
  - 字符串：纯文本，保留换行（`white-space: pre-line`）。
  - 数字、布尔：转成文本。
  - 字符串数组：用"、"连接。
  - 含 `zh` 键的对象：先显示中文，`en` 用次要文字显示在下方，其余键用小字列出。
  - 对象数组：逐项列出。
  - 其他对象：按"键名：值"逐项列出，键名用 `fieldLabels.ts` 中的 `subKeyLabels` 显示中文，没有配置的显示原键名；成对的 `X_zh` / `X_en` 合并显示。嵌套超过 4 层时改为格式化 JSON（`<pre>`）。
  - 来源值 `no_data` 显示为"来源无数据"。
  - **禁止 `v-html`**。所有来源文本都按纯文本渲染。
- **ICD-11 编码**：只显示编码本身，不补造疾病名称。
- **注意事项分区**：`contraindications_*`、`safety_notes_*`、`pregnancy`、`lactation`、`pediatric`、`acute_use_note` 这些字段单独放在"来源中的注意事项"分区，分区开头固定写"以下为来源原文，仅供学习参考，不构成用药建议"（§5.0 第 5 项）。

- **方剂的症状与注意事项**：本草典方剂条目本身没有主治症状和禁忌字段，方剂详情页另加两个分区，数据来自 `GET /entities/{id}/formula-notes`，不由模型生成，也不补写。
  - "适用证候及症状"：经 `ASSOCIATED_WITH_PATTERN` 关联的证候条目中的主症、次症、舌象、脉象原文，附关联证据。当前批次 112 首方剂中 56 首有关联证候；没有关联的说明来源未给本方关联证候，并引导查看属性中的"说明"（多数方剂的主治写在其中），附跳转按钮。
  - "组成药物的注意事项"：经 `CONTAINS` 关联的各药物条目中的禁忌、安全提示、用量备注（`dosage_range.notes`，如"有毒""反甘草""孕妇禁用"）原文，以及孕期、哺乳期、儿童的类别（`contraindicated` 禁用、`avoid` 忌用、`caution` 慎用）和说明；类别为 `no_data` 的不列出。分区开头固定写"以下为各组成药物条目中的来源原文，不是本方的整体禁忌；仅供学习参考，不构成用药建议"，没有任何记载的药物在分区末尾列出并注明"不代表无禁忌"。

**字段配置**（已用开发库核对每种类型 `attributes_json` 的实际键）：

| 类型 | 按顺序显示的字段 |
| --- | --- |
| `formula` 经典方剂 | 拼音、英文名、子分类、出处（`source_text_key` 原文）、出处篇章、治法、制法、加减、方歌、说明 |
| `herb` 中药 | 拼音、拉丁名、英文名、性、味、功效、主治、用量范围、炮制、古籍记载、药理、说明 |
| `pattern` 证候 | 拼音、英文名、主症、次症、舌象、脉象、病因、病机、治法、相关脏腑、说明 |
| `text` 古籍 | 拼音、英文名、作者、朝代、成书年代、学派、学术地位、说明；`passages` 放折叠区 |
| `patent_medicine` 中成药 | 拼音、给药途径（Oral 口服、Topical 外用、Injection 注射，后面括注原值） |
| `herbal_piece` 中药饮片 | 中文异名、拼音、英文名、来源 |
| `tcm_term` 中医术语 | 中文分组、英文分组、拼音、中文同义词、英文名、英文同义词、英文定义 |
| `icd11_code` ICD-11 编码 | 编码 |
| `medicinal_property` 药性 | 类别、名称 |

- 带 `_zh` / `_en` 后缀的成对字段，配置中只放 `_zh`；`_en` 作为次要文字显示在中文下方。
- `category` 已在页头显示，不在属性中重复。
- 性、味、相关脏腑的英文代码按 `valueLabels` 显示为中文（如 `neutral` 显示"平"），没有配置的取值原样显示。
- TCM-MKG 中与名称重复的 ID 列和名称列不放进配置，进入"其他属性"。

#### 关系分区

- 由 `relation_summary` 生成：每个 `count > 0` 的（关系，方向）组合是一个分区，标题后显示数量。分区按下表顺序排列。
- 每个分区独立分页，每页 20 条，调用 `GET /entities/{id}/relations`。
- `quality_state=conflicting` 的边在所在行显示冲突标记和说明。

| 关系 | 出边分区 | 入边分区 |
| --- | --- | --- |
| `CONTAINS` | 组成 | 收录该药的方剂 |
| `ASSOCIATED_WITH_PATTERN` | 关联证候 | 关联该证候的方剂 |
| `CITED_IN` | 出处古籍 | 引用该书的条目 |
| `HAS_HERBAL_PIECE` | 饮片组成 | 含该饮片的中成药 |
| `ASSOCIATED_WITH_TERM` | 关联术语 | 关联该术语的中成药 |
| `MAPPED_TO_ICD11` | ICD-11 编码 | 映射到该编码的中成药 |
| `HAS_MEDICINAL_PROPERTY` | 药性 | 具有该药性的饮片 |

**各分区的列**：

| 分区 | 列 |
| --- | --- |
| 组成（方剂 `CONTAINS` 出边） | 位置、药名（可跳转）、剂量原文、君臣佐使、证据 |
| 收录该药的方剂（`CONTAINS` 入边） | 方剂（可跳转）、分类、剂量原文、该方中的角色、证据 |
| 饮片组成 / 含该饮片的中成药 | 名称（可跳转）、剂量比例原文（`Dosage_ratio`）、证据 |
| 药性（`HAS_MEDICINAL_PROPERTY` 出边） | 类别、药性（可跳转）、证据 |
| 其他分区 | 名称（可跳转）、类型、分类、证据 |

- **剂量**：照原文显示，不换算。
- **位置**：`position_source=target_id_order` 表示来源没有给出位置，位置列显示"—"，并在表格下方说明"部分药物的排列顺序由系统补充，非来源记载"。
- **冲突**
  - 本草典组成边（如猪苓汤→泽泻）：冲突字段为 `null`，角色列显示"⚠ 来源记载不一致"，说明"各来源对该项记载不同，未作取舍，可打开证据查看各来源原值"。
  - TCM-MKG 关系边：冲突值保存在 `properties.conflicts` 中，按"字段：值一 / 值二"列出。
- **其他边属性**：上表没有列出的 `properties` 键（如药性边的 `x_rank`、`y_rank`），放在该行的折叠"边属性"中原样显示。`missing_claim_fields`、`position_source` 只用于上面的说明，不单独显示。
- **证据列**：只有 1 条时直接链接到 `/evidence/:id`；有多条时显示"n 条证据"，点击后在行内展开链接列表。

#### 证据分区

- 显示 `evidence_total`，以及 `evidence_preview` 的前 20 条。超过 20 条时显示分页，第 2 页起调用 `GET /entities/{id}/evidence`。
- 每条显示证据类型、字段定位（`field_path` 为空时显示"整条记录"）、摘录（为空时不显示），链接到 `/evidence/:id`。

### 5.7 证据页 `/evidence/:id`

- **概要**：证据类型、字段定位、摘录。
- **证据对象**
  - 实体证据：实体名称，链接到详情页。
  - 关系证据：起点 → 关系中文名 → 终点，两端都可跳转。
- **原始值**：`raw_value` 为字符串时直接显示；否则显示格式化 JSON。
- **来源记录**：文件名、记录键、记录定位、文件 SHA-256（等宽字体，带复制按钮）。完整记录 `content` 放在折叠区；`content_truncated=true` 时注明"记录超过 64 KB，已截断"。
- **数据集**：名称、版本、许可说明、署名。`source_url` 作为外部链接，带 `rel="noopener noreferrer"`。

### 5.8 来源页 `/datasets`

- 每个来源一张卡片：名称、ID、版本、来源地址、许可说明、署名，以及实体数、关系数、来源记录数。
- 页面底部注明：公开交付前需逐项核对原始使用条件（开发计划 §2.2）。

### 5.9 统计页 `/stats`

- **业务记录总量**：大号数字，下方写出算式"实体 20,374 + 业务关系 179,502 = 199,876"（数字取接口实时值），并注明验收口径"去重实体 + 业务关系"。
- **分项**：按实体类型、按关系类型（用 §5.6 的中文名）、按来源各一张表。
- **与原始数据的区分**（§5.0 第 3 项）
  - 按来源显示 `source_records` 计数，标为"来源记录"，说明它是导入时保留的原始记录。
  - 证据、别名、来源记录都不计入业务记录总量，页面上写明。
  - 开发库核对结果：TCM-MKG 的 195,211 条来源记录与 D1～D7 源文件行数一一对应；本草典的来源记录按 JSON 条目和关系记录计，不等于文件行数。所以页面统一称"来源记录"，不称"原始行数"。
- **运行状态**：从现有首页移过来，显示 PostgreSQL 主库、Neo4j 图库、模型服务的状态，以及 Neo4j 的 `projection` 取值。保留"刷新"按钮和"刷新运行状态不会发起模型调用"的说明。
  - `/health` 返回 503 时页面仍然渲染：主库显示不可用，其他服务按响应显示。
- **批次**：完整 `build_id`，等宽字体，带复制按钮。

### 5.10 视觉与可用性

- 沿用现有 `style.css` 的配色、字体和页头页脚。新增样式按组件拆分，不引入 CSS 框架。
- 桌面优先。宽度小于 720px 时表格可以横向滚动，页面本身不出现横向滚动条。
- 表格使用语义化的 `<table>`、`<th scope>`；所有按钮和链接都能用键盘操作，焦点可见。

### 5.11 M2 出口

- `npm run build`（含 `vue-tsc` 类型检查）通过。
- **往返链路**：检索"四君子汤"→ 方剂详情 → 组成中的"甘草"→ 收录甘草的其他方剂 → 任一方剂 → 一条组成证据 → 证据对象链接回到方剂。全程可以往返跳转，浏览器后退能回到上一步。
- **猪苓汤**的组成表中，泽泻显示冲突标记和说明，证据中能看到各来源的原值。
- **甘草（饮片）**的"含该饮片的中成药"分区共 2,278 条，可以逐页翻到最后一页。
- **ICD-11 编码**详情只显示编码。
- **深链接**：在开发服务和 `vite preview` 中，分别刷新 `/`（带查询参数）、`/entity/...`、`/evidence/...`、`/datasets`、`/stats`，都回到同一页面。
- **异常状态**
  - 停掉后端：每个页面显示"服务不可用"和"重试"，后端恢复后点"重试"可以正常显示。
  - 不存在的实体 ID 和证据 ID 显示"未找到"；不存在的路径显示"页面不存在"。
  - 把 `sessionStorage` 中的 `build_id` 改成另一个合法值后操作页面，出现"数据已更新"横幅；点"刷新"后恢复正常。
- **交付记录**：逐项结果和截图写入 `docs/dev/m2-delivery.md`，截图放在 `docs/screenshots/m2-*.png`；固定用例同步追加到 `tests/cases.md`（§8.1）。

---

## 6. M3：Neo4j 全量投影与图谱（T12–T13）

### 6.1 投影构建：`scripts/project_graph.py`

- **输入**：关系库中当前配置的批次，用导入账号只读访问。
- **图模型沿用样例**
  - 节点：`(:Entity {id, build_id, label, type, scope:'full'})`
  - 关系：`[:LINK {id, build_id, relation, evidence_ids, quality_state, scope:'full'}]`
  - 边上只存展示和筛选所需的属性：`CONTAINS` 的 `role`、`position`、`dosage_raw`。证据正文不进图库。
  - 额外为每个节点加类型标签（`:Formula`、`:Herb` 等），提高按类型过滤的效率。标签取自后端的固定映射，不来自用户输入。
- **写入**
  - `UNWIND` 批量写入，每批 5,000 条，用 `MERGE` 保证幂等。
  - 先写节点再写边，最后写 `(:Projection {build_id, scope:'full', complete, node_count, edge_count, id_digest})`。
- **校验**
  - 节点数、边数与主库一致（20,374 / 179,502）。
  - 节点 ID 集合和边 ID 集合的排序 SHA-256 摘要与主库一致。
  - 全部校验通过后，才把 `complete` 设为 `true`。
- **旧版本**
  - 不同 `build_id` 的数据并存，查询一律按 `build_id` 过滤。
  - 清理旧批次只能通过显式的 `--prune <build_id>`，并且禁止删除当前配置的批次。
- **资源**：现有 compose 的 Neo4j 堆上限 512 MB，按 20 万节点和关系估算够用。M3 中实测内存和导入耗时，写入报告。
- **样例投影**：保留 `scope='bootstrap'` 的样例，用于健康检查回退。

### 6.2 `GET /api/v1/graph`

- **参数**：`center`（实体 ID）、`relation?`（白名单，可多选）。
- **查询**
  - 只取一跳邻居，出入边都包含。
  - 按 `relation, neighbor.label, id` 排序。
  - 最多 50 个节点（含中心节点）和 100 条边。
  - 多取一条候选来判断是否被截断。
- **响应**
  - `nodes[]`、`edges[]`、`truncated`、`limits{nodes:50, edges:100}`。
  - 另附 `relation_counts[]`：中心节点按关系和方向的真实总数，从关系库读取，标明来源。截断时，前端据此提示"共 2,278 条，仅显示 99 条"。
- **其他约束**：返回边的两个端点必须都在返回的节点中；投影未完成或批次不符时返回 503。

### 6.3 `GET /api/v1/graph/paths`

- **参数**：`template=herb_patterns_via_formula`、`entity_id`、`limit≤50`。
- 用固定 Cypher 在 Neo4j 上执行两跳查询，用于演示"图查询确实经过 NoSQL"。返回结构与 §4.5 相同。
- M3 测试中，对同一输入比较关系库和图库两种实现的结果集，必须一致。这项测试同时作为双库一致性的证据。

### 6.4 图谱页面 `/graph/:id`

- 用 Cytoscape.js 绘图，版本需要锁定。
- **交互**
  - 点击节点发起该节点的一跳请求，前端按 ID 合并结果。
  - 画布累计上限 100 个节点、200 条边，达到上限时提示清空或切换中心。
- **辅助功能**
  - 画布旁边提供同样内容的文字关系列表，可以用键盘操作。
  - 关系类型同时用颜色和线型或图例文字区分，不只靠颜色。
- 点击一条边显示它的证据列表，链接到 `/evidence/:id`。

### 6.5 M3 出口

- 投影报告中的数量和 ID 摘要都与主库一致，并记录投影耗时。
- 图请求实际经过 Neo4j：停掉 Neo4j 后，图页面显示"图数据库暂时不可用"，检索和详情仍然正常。
- Neo4j 重启后，投影数据仍在。
- 完整的备份恢复演练：用 `neo4j-admin database dump` 导出，然后 `load`，校验 `Projection` 摘要与导出前一致。演练过程写入报告（T03 剩余部分）。

---

## 7. M4：AI 功能（T15–T18）

### 7.0 前置：首次真实调用（T04 剩余）

- 由用户提供 `config/model.json` 和 API key，然后执行 `verify_environment.py --check-model`。这个命令最多发出两次请求。
- 这是 M4a 的**阻塞项**。在模型配置到位之前，M4 只能用 MockTransport 开发协议和校验逻辑，不能宣称 AI 功能完成。
- 提示词放在 `backend/prompts/`，每个文件带版本号（例如 `query_v1.md`）。每次调用都记录使用的提示词版本。

### 7.1 `POST /api/v1/ai/query`：自然语言条件查询

请求为 `{"question": "...", "build_id?": "..."}`，问题不超过 200 字。

**处理链路**：问题 → 模型输出条件 JSON → 后端校验白名单 → 实体名解析 → 参数化 SQL 查询 → 返回结果。

**模型只能输出以下结构**。字段之外的任何内容都会导致 `model_invalid_response`。

```json
{
  "target_type": "formula | herb | patent_medicine | herbal_piece",
  "conditions": [
    { "field": "name_contains", "value": "..." },
    { "field": "category", "value": "补益剂" },
    { "field": "includes_herb", "value": "甘草" },
    { "field": "excludes_herb", "value": "人参" },
    { "field": "associated_pattern", "value": "脾胃气虚证" },
    { "field": "source_dynasty", "value": "宋" },
    { "field": "herb_nature", "value": "warm" },
    { "field": "route", "value": "Oral" }
  ],
  "unsupported": ["模型认为无法表达的部分（原文）"]
}
```

**首版支持的字段与目标类型**（后端维护白名单表，类型与字段的组合不在表里时返回 `unsupported`）：

| 字段 | formula | herb | patent_medicine | herbal_piece | 实现 |
| --- | --- | --- | --- | --- | --- |
| `name_contains` | ✓ | ✓ | ✓ | ✓ | 复用 §4.2 |
| `category` | ✓ | ✓ | — | — | `entity.category` 精确匹配，取值须在库中已有值内 |
| `includes_herb` / `excludes_herb` | ✓ | — | ✓ | — | 方剂用 `CONTAINS`→herb；中成药用 `HAS_HERBAL_PIECE`→herbal_piece |
| `associated_pattern` | ✓ | — | — | — | `ASSOCIATED_WITH_PATTERN` |
| `source_dynasty` | ✓ | — | — | — | `CITED_IN`→text 的 `dynasty_zh`，经朝代归一表 |
| `herb_nature` | — | ✓ | — | — | `attributes.nature`，8 个枚举值 |
| `route` | — | — | ✓ | — | `Routes_of_administration`，3 个枚举值 |

- **实体名解析**：`includes_herb`、`associated_pattern` 等字段的值，按"名称精确 → 别名精确"解析为实体 ID。
  - 0 个候选：`status=unresolved`，返回原词，不执行查询。
  - 多个候选：`status=ambiguous`，返回候选列表，由用户选择后带上 `resolved` 参数重新提交。**不能猜一个执行。**
- **朝代归一表**（`backend/vocab.py`，有版本号）
  - "宋" → {宋, 北宋, 南宋}
  - "汉" → {汉, 东汉, 战国至汉}
  - 其他朝代同理，表中只收当前 38 部古籍中实际出现的取值。
  - 表外的朝代返回 `unsupported`。
- **覆盖说明**：`source_dynasty` 和 `associated_pattern` 只覆盖本草典的 112 首方剂，响应中要附上这条覆盖说明。这两个条件不涉及中成药。
- **返回**
  - `status`：`ok` / `ambiguous` / `unresolved` / `unsupported` / `failed`。
  - `conditions`：经过校验和解析、实际执行的条件。前端照原样显示"查询实际执行了什么"。
  - `results`：最多 50 条，复用 §4.2 的结果项。
  - 另附 `model`、`prompt_version`、`build_id`。
- **安全**
  - 问题文本不能改变允许的操作。
  - 包含"忽略指令"或要求输出 SQL 的问题，仍然只能得到白名单条件，或者返回 `unsupported`。

### 7.2 `POST /api/v1/ai/explain`：带引用的方剂解释

请求为 `{"entity_id": "bencaodian:formula:...", "build_id?": "..."}`。首版只支持 `formula` 类型（112 首），其他类型返回 422 `unsupported_entity_type`。

**材料组装**（不经模型，直接从关系库取）：

- 方剂属性：`description_zh`、`treatment_principle`、`preparation_zh`、`category`、`subcategory`、`source_chapter`。每项附实体级证据 ID。
- 组成：`CONTAINS` 边的药名、剂量原文、角色、位置、`quality_state` 和边的证据 ID。
- 关联证候：`ASSOCIATED_WITH_PATTERN`，附证据 ID。
- 出处：`CITED_IN`→古籍，附书名、朝代和证据 ID。
- 每条材料编号 `M1…Mn`，并映射到真实证据 ID。模型只能看到材料编号，后端负责换回证据 ID。

**模型输出结构**：

```json
{
  "sections": [
    { "heading": "组成与配伍", "sentences": [ { "text": "...", "citations": ["M3", "M4"] } ] },
    { "heading": "出处", "sentences": [ ... ] }
  ],
  "insufficient": ["材料不足以回答的方面"]
}
```

**后端校验**（T17），顺序执行，任意一步失败即判为本次生成失败：

1. 结构合法，每句至少有一个引用，所有引用编号都在本次材料范围内。
2. 正文中出现的药名必须是组成材料中的药名，或者该药实体的已知别名。
3. 句子中出现"君 / 臣 / 佐 / 使 + 药名"时，必须与组成材料中的 `role` 一致。
4. 冲突边或 `role=null` 的药，不能出现在确定的角色陈述中。
5. 剂量数字只能原样引用 `dosage_raw`，不能出现材料中没有的剂量。

- **失败处理**
  - 校验失败时重试一次，并在提示中附上失败原因。
  - 仍然失败时返回 `status=explanation_unavailable`，同时返回完整的结构化材料，页面照常展示组成和出处。
- **传输错误**：超时、HTTP 错误、拒答**不重试**，与范围冻结中的"无自动重试"一致。
- **返回**：`status`、`sections`（引用已换成证据 ID）、`materials`、`model`、`prompt_version`、`usage`、`build_id`。
- **重要说明**：引用 ID 存在只说明来源可以定位，不说明文字一定得到支持。这一点通过 §8 的人工评测衡量。

### 7.3 共性约束（T18）

- **单次调用**：超时 30 秒，最大输出 1,024 token，沿用 `model_client.settings` 的范围校验。
- **并发**：进程内用信号量把同时进行的模型调用限制为 2 个，超出时返回 503 `model_busy`，用来控制成本。
- **调用日志**：每次调用追加一行到 `var/ai-calls.jsonl`，记录时间、端点、`request_id`、模型、提示词版本、token 用量、耗时、状态和校验失败原因。日志不写入 key，问题原文需要截断。
- **降级**：模型未配置或不可用时，AI 入口显示明确状态，检索、详情和图谱不受影响。
- **页面**
  - 查询页：输入框、"实际执行的条件"卡片、候选消歧、结果列表。
  - 解释页：嵌在方剂详情中，每句话后面的引用标记可以点开对应的证据页。

### 7.4 M4 出口

- M4a：真实模型完成至少 10 条开发样本的查询，条件可人工核对。歧义和不支持的样本没有执行任何猜测查询。
- M4b：在 10 首方剂上生成解释，引用 100% 可回查。猪苓汤的解释中没有把泽泻写成确定的角色。人为制造校验失败时，能走到降级路径。

---

## 8. M5：测试、评测与联调（T19–T20）

### 8.1 测试组织

- 沿用现有风格：`tests/*.py` 可以用 `python` 直接运行，带断言，不引入新的测试框架。

| 文件 | 内容 | 依赖 |
| --- | --- | --- |
| `test_data_pipeline.py` / `test_import_core.py` | 已有：数据管线 | 只需标准库 |
| `test_app.py` / `test_database_config.py` | 已有：健康检查、配置 | 开发库 |
| `test_api.py` | 新增：§4 和 §6 的全部接口用例 | 开发库 + Neo4j |
| `test_ai_contract.py` | 新增：用 MockTransport 测协议、白名单、解析、校验和降级 | 无需真实模型 |
| `eval/run_eval.py` | 新增：用真实模型跑评测集并输出报告 | 真实模型（计费） |

- 固定功能用例不少于 30 个，覆盖检索、详情、关系、证据、图、AI 和异常场景，清单写在 `tests/cases.md`。

### 8.2 AI 评测集

- 文件：`eval/dev.jsonl`（20 条）和 `eval/test.jsonl`（60 条）。测试集**一经冻结就不再按结果修改**，冻结时记录文件的 SHA-256。
- 每条样本包含：问题、支持状态、预期条件或预期事实、预期证据。
- 门槛沿用开发计划 §7.3：

| 类别 | 数量 | 目标 |
| --- | --- | --- |
| 支持范围内的查询 | 25 | 执行结果与人工条件查询完全一致 ≥ 90% |
| 方剂解释 | 20 | 引用可定位率 100%；人工逐项核对的事实支持率 ≥ 95% |
| 无依据、歧义、越界、注入 | 15 | 不执行未授权查询；关键样本全部通过 |

- 报告记录：模型、提示词版本、生成设置、每条样本的结果、耗时、费用、失败样本。不预设一定能达标。

### 8.3 M5 出口

- 所有 P0 用例通过。阻断问题逐条登记，有处理结论。
- 冻结测试集已跑出完整结果。没有达标的项目列明差距和原因。
- **从这个节点起冻结范围**：P1 功能（配伍提示、共现统计、方剂比较）只有在 M5 提前完成时才考虑。

---

## 9. M6–M7：Vastbase 迁移、性能与交付（T02 T08 T20 T21 T22）

### 9.1 Vastbase 迁移

1. 记录产品版本、兼容模式和驱动版本，然后执行 `import_vastbase.py --engine vastbase` 的 probe 步骤。
2. 用同一个 `var/prepared/<build_id>` 批次导入，执行导入后校验。
3. 比较两库摘要：各表行数、`table_sha256`、M1 视图的查询结果。
4. 在 Vastbase 上建 `qihuang_reader` 只读账号，重新运行写入失败测试。
5. 切换 `config/app.json` 的 `database_engine` 并配置连接，完整运行 `test_api.py` 和评测脚本的冒烟子集。
6. 确认 Neo4j 投影的 `build_id` 与 Vastbase 中的批次一致，图接口恢复可用。

PostgreSQL 上的结果**不能代替** Vastbase 的验收。每一项都要在实际实例上重新执行并留下记录。

### 9.2 性能测试

- 新增脚本 `scripts/bench.py`，使用 httpx，不引入新工具。
- 非 AI 接口：预热 20 次，然后每个接口至少采样 200 次，分单用户和 5 并发两种情况。
- 目标：普通检索和局部图的 P95 ≤ 2 秒；AI 的 P95 ≤ 15 秒，超时上限 30 秒。
- 报告记录硬件、版本、批次、并发数、样本和返回规模。失败和超时单独列出，不能剔除后宣称达标。

### 9.3 部署与恢复（T21）

- 生产形态：`vite build` 生成静态资源，由 FastAPI 托管 `/assets` 并处理 SPA 回退。`/api/*` 的路由优先于 SPA 回退。
- 恢复演练：关系库从批次重新导入，图库通过 dump/load 或重新投影恢复。演练后两库回到同一批次，接口复验通过。

### 9.4 交付物（T22）

- 代码与依赖锁文件、DDL 与迁移脚本、投影脚本。
- 测试、评测、性能和恢复报告。
- 部署说明。
- 论文用图表：ER 图、架构图、查询执行计划、评测结果。
- 五分钟演示脚本和录屏，流程见开发计划 §9。

---

## 10. 风险与提前动作

| 风险 | 影响 | 提前动作 |
| --- | --- | --- |
| Vastbase 实例或驱动拿不到、不兼容 | 硬性指标无法签收 | **M1 期间**就申请环境并跑一次 probe 与建表；不兼容的写法（如 `pg_trgm`、部分 JSON 函数）在 M1–M3 中禁用 |
| 模型迟迟没有配置 | M4 无法验收 | 协议和校验先用 Mock 开发；M4a 开始前必须拿到配置，否则重新排期 |
| 超高度数节点拖慢图和关系接口 | 页面卡顿、P95 超标 | 所有邻居查询都分页或截断，M1 就测量甘草、Bitter 等节点 |
| AI 编造组成、角色或剂量 | 内容错误 | §7.2 的结构化校验加人工评测，失败时降级为只显示材料 |
| 朝代、证候覆盖面窄 | 组合查询的演示样本少 | 只用已核对的样本演示；响应中如实给出覆盖说明 |
| 单人工期吃紧 | 延期 | 按开发计划 §5 的删减顺序处理：先删 P1、页面装饰、非关键统计，保留四项硬性指标 |

---

## 11. 待确认事项

以下几项会改变工作量或范围，需要在 M1 结束前确认：

1. **交付截止日期**：确定后把 §3 的参考日期替换为实际日期，并确认缓冲是否够用。
2. **课程是否硬性要求存储过程、触发器或 Web 端 CRUD**：要求的话，M1 需要增加存储过程，并单独评估管理入口和认证的工期。
3. **Vastbase 实例的来源和版本**：学校提供、自建还是云服务，以及何时可用。
4. **模型服务商和预算**：会影响评测轮次和并发上限。
5. **数据量口径**：任务书中的"十万条"是否就是"实体 + 业务关系"（当前为 199,876）。如果要求十万个独立实体，现有数据不满足，需要重新规划。
