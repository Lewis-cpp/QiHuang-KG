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
| 前端 | 单页：统计、检索、依赖状态、样例关系表 | `frontend/src/App.vue` |
| 模型 | 客户端、配置模板和验证脚本已就绪，未发起真实调用 | `backend/model_client.py` |

开发计划第 1–2 周的阶段出口已在 PostgreSQL 上达成，只差模型的一次真实调用。下一阶段从第 3 周（业务 API）开始。

### 1.2 实测的数据特征（影响设计）

以下数字来自当前批次 `5a76218e…`：

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
  - 证据类型：`curated` 290,346、`bibliographic` 531、`source_quote` 428。
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

### 5.1 路由与页面

引入 `vue-router`，需要锁定版本，并把依赖变更写进 `package-lock.json`。

| 路由 | 页面 | 内容 |
| --- | --- | --- |
| `/` | 检索 | 搜索框、类型和来源筛选、结果列表（显示命中说明）、分页 |
| `/entity/:id` | 详情 | 基本信息、属性分区、关系分区（按 `relation_summary` 生成，每个分区独立分页）、证据入口 |
| `/evidence/:id` | 证据 | 证据类型、字段定位、原始值、来源记录、数据集、文件哈希 |
| `/datasets` | 来源 | 来源列表、许可与署名、各来源计数 |
| `/stats` | 统计 | 实体、关系、证据的计数，分类型和来源；区分原始行数与有效业务记录 |
| `/graph/:id` | 图谱 | M3 实现 |

### 5.2 展示规则

- **字段显示**：每种实体类型的字段中文名和显示顺序放在 `frontend/src/fieldLabels.ts`。不在配置里的字段放进"其他属性"折叠区，不丢弃。
- **方剂组成表**
  - 列：位置、药名（可跳转）、剂量原文、君臣佐使、证据。
  - 剂量照原文显示，不换算。
  - `role=null` 显示"来源未标注"；`conflicting` 时显示冲突标记和说明。
- **审核状态**：`unknown` 显示"来源提供 · 未审核"，与现有 `App.vue` 一致；`editor_reviewed` 显示"编辑已审核"。
- **ICD-11 编码**：只显示编码本身，不补造疾病名称。
- **页面状态**：每个页面都要有加载中、空结果、404、503 四种状态。错误信息使用后端 `message`，不显示堆栈。
- **布局**：桌面优先，窄屏可用即可（范围冻结不含移动端）。

### 5.3 M2 出口

- 方剂详情 → 药物详情 → 收录该药的其他方剂 → 证据，全程可以往返跳转。
- 在浏览器中刷新深链接（例如 `/entity/...`）能回到同一页面。开发服务和 `vite preview` 都要验证。
- `npm run build` 中的 `vue-tsc` 类型检查通过。

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
