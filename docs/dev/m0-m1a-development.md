# M0 + M1a 开发文档：批次统一与详情、证据接口

版本：1.0。编写日期：2026-10-10。上位文档：[spec.md](../../spec.md) §1.3、§2、§4。验收标准见 [m0-m1a-acceptance.md](m0-m1a-acceptance.md)。

本文档只规定"做什么、做到什么程度、按什么顺序做"，不包含实现代码。文中的 JSON 是接口契约示例，字段名和语义以本文为准；示例值取自批次 `5a76218e…`。

---

## 1. 范围

spec 中的 M1 拆成两部分，本次只做前一半：

| 部分 | 内容 | 本次 |
| --- | --- | --- |
| **M0** | 应用、Neo4j 样例和文档统一到当前批次 | ✓ |
| **M1a** | 统一错误处理；实体详情、实体证据列表、证据详情；`formula_herbs` 和 `herb_formulas` 两个关系模板 | ✓ |
| M1b | `/entities` 排序改进、`/entities/{id}/relations`、其余 5 个模板、`/datasets`、业务视图、只读账号（T11） | 下一步 |

M1a 完成后，不需要前端，就能用 curl 走通"检索四君子汤 → 打开详情 → 查看组成 → 打开一条组成证据 → 看到原始字段值"，以及反方向的"药物 → 收录该药的方剂"。

**本次不涉及**：前端页面（M2）、Neo4j 全量投影（M3）、AI（M4）、数据管线和 DDL 的修改。

---

## 2. M0：批次统一

### 2.1 现状诊断

开发库中目前**同时存在两个批次**，应用和图库还停在旧批次上：

| 位置 | 当前指向 | 依据 |
| --- | --- | --- |
| 当前代码 `prepare_data.py` 生成的批次 | `5a76218e…` | 2026-10-10 本地重跑 |
| PostgreSQL 中最近一次导入并校验的 schema | `qihuang_5a76218e52001d45e4bd75e0` | `docs/data-quality-report.json` → `environment.import_result` |
| 应用配置 `config/app.json` | 旧批次（旧） | 同一报告的 `application_selection` |
| Neo4j 样例投影 | 旧批次（旧） | `docs/environment-report.json` |
| `config/app.example.json` | 旧批次（旧） | 仓库文件 |
| `docs/vastbase-import.md` 中的"当前批次"、导入命令和 SQL 示例 | 旧批次（旧） | 仓库文件 |

`data-quality-report.json` 的 `remaining` 字段已经写明："应用与 Neo4j 样例仍使用原批次；新校验批次单独入库，两批业务内容摘要相同。"所以 M0 **不需要重新清洗数据**，只需要切换应用配置并重建样例。

**旧批次为什么会留下来**：`setup_services.py` 只在 `config/app.json` 不存在时才创建它。之后导入新批次时，已有的 `app.json` 不会被覆盖，应用也就不会自动切过去。这是有意的设计，可以防止误切批次，但需要人工完成切换。

**build_id 的计算方式**：由输入文件哈希、DDL 哈希、`transform_version`、核心批次 ID 和 **`prepare_data.py` 文件本身的哈希**共同决定，不包含创建时间。因此：

- 同样的输入和代码，重复运行得到同一个 build_id，并复用已有快照。
- **只要改动 `prepare_data.py` 的任何一个字节，包括注释，就会产生新批次**，需要重新导入并再次切换。在 M1 到 M3 期间，没有数据层面的需求就不要改这个文件。

### 2.2 步骤

1. **确认数据库状态**
   - 在开发库中列出所有 `qihuang_%` schema，以及每个 schema 中 `build` 表的 `id`。
   - 确认 `qihuang_5a76218e52001d45e4bd75e0` 存在，且其中 build id 为完整的 `5a76218e…a3008a`。
2. **确认导入报告**
   - 读取 `var/postgresql-report.json`，确认 `status=passed`，且 `import_result.build_id` 为 `5a76218e…`。
   - 如果不是，先用 `import_vastbase.py --engine postgresql --release var/prepared/5a76218e…` 重新导入。导入会复用或校验已有 schema，不会删除数据。
3. **切换应用配置**
   - 把现有的 `config/app.json` 备份为 `var/app.json.previous.bak`。
   - 删除原文件，重新运行 `python3 scripts/setup_services.py`，由它从导入报告中选出批次。
   - 不建议手工编辑 JSON，以免 schema 名与 build id 不对应。
4. **重建 Neo4j 样例**
   - 运行 `.venv/bin/python scripts/verify_environment.py`。`check_neo4j()` 会为新批次写入 `scope=bootstrap` 的样例，逐条与主库比对，然后把投影标记为完成。
   - 旧批次的样例节点保留。所有查询都按 `build_id` 过滤，旧数据不会被读到。
5. **回归测试**
   - 依次运行 `tests/test_app.py`、`tests/test_database_config.py`、`tests/test_data_pipeline.py`、`tests/test_import_core.py`，全部通过。
6. **更新文档**，见 §2.3。

### 2.3 文档更新清单

| 文件 | 修改 |
| --- | --- |
| `config/app.example.json` | `schema` 和 `build_id` 改为新批次 |
| `docs/vastbase-import.md` | "当前数据 schema""当前构建 ID"两行、导入命令和 `SET search_path` 示例改为新批次。原有的 10-04 实施记录保留，补一句"2026-10-xx 应用切换至 5a76218e 批次" |
| `docs/environment-report.json` | 用第 4 步新生成的 `var/environment-report.json` 覆盖。提交前确认其中没有密码等凭据 |
| `docs/data-quality-report.json` | **不修改**，它是 10-08 的历史记录 |
| `docs/data-pipeline-report.json` | **不修改**，它是 10-04 的历史记录 |
| `spec.md` §1.3 | 标记为"已完成"，注明完成日期 |

### 2.4 规则

- **旧 schema （schema 名读取配置备份） 保留**，作为 M1a 验收前的回滚点。DDL 约定是"不做破坏性 DDL"，清理旧批次另行决定，不放在本次范围内。
- 回滚方法：把备份的 `app.json` 放回原位，然后重启后端。应用会核对库中 `build` 表的 id，所以不会出现"配置是新批次、读到的却是旧数据"的情况。

### 2.5 完成定义

- `GET /api/v1/health` 中 `database.build_id` 和 `neo4j.build_id` 都是 `5a76218e…`，`neo4j.projection` 为 `sample`。
- `GET /api/v1/stats` 的数值不变：实体 20,374，关系 179,502，证据 291,305，业务记录 199,876。
- 仓库中除两份历史报告外，不再出现 旧批次 ID（读取配置备份）。

---

## 3. M1a：统一约定（所有新接口适用）

### 3.1 错误处理改造

目前所有 `ServiceError` 一律映射为 503，FastAPI 的参数校验错误返回框架默认的 `{"detail": [...]}`。M1a 需要先改造错误处理，否则 404 无法实现。

**改造后的规则**：

- 每个错误码对应固定的 HTTP 状态，映射表放在后端的一个地方，不分散写在各个路由中。
- 响应体统一为 `{"error": {"code": "...", "message": "..."}}`。`message` 用中文，面向用户，不包含 SQL、路径、堆栈或凭据。

| HTTP | code | 触发条件 | 状态 |
| --- | --- | --- | --- |
| 404 | `entity_not_found` | 实体 ID 格式合法，但当前批次中不存在 | 新增 |
| 404 | `evidence_not_found` | 证据 ID 格式合法，但不存在 | 新增 |
| 404 | `not_found` | 未定义的 `/api/*` 路径 | 新增 |
| 405 | `method_not_allowed` | 请求方法不适用于接口，保留 Allow 响应头 | 新增 |
| 409 | `snapshot_changed` | 请求携带的 `build_id` 与当前配置不一致 | 新增 |
| 422 | `invalid_query` | 参数格式、范围或长度不合法，包括 FastAPI 默认的校验错误 | 新增（统一格式） |
| 422 | `invalid_type` | 实体类型不在白名单内 | 已有 |
| 422 | `unsupported_entity_type` | 模板与实体类型不匹配 | 新增 |
| 500 | `evidence_pointer_invalid` | 证据的 `field_path` 在原始记录中无法解析，属于数据完整性错误 | 新增 |
| 500 | `internal_error` | 其他未预期异常；只在服务端日志中记录异常类型 | 新增 |
| 503 | `database_unavailable` / `build_mismatch` / `*_not_configured` / `invalid_app_config` | 已有的依赖错误 | 已有，不变 |

**兼容性**：现有的 `test_app.py` 只断言状态码 422，`App.vue` 只检查 `response.ok`，所以改为统一格式不影响现有功能。

### 3.2 ID 格式校验

ID 先在路由层校验格式，不合法时直接返回 422，不查询数据库。实测当前数据中的所有 ID 都只含 `[A-Za-z0-9_.:-]`，最长 91 字符。

| ID | 格式规则 |
| --- | --- |
| 实体 ID | `<dataset>:<type>:<key>`，其中 dataset 为 `bencaodian` 或 `tcm-mkg`，type 为 9 种实体类型之一，key 为 1–160 个 `[A-Za-z0-9_.-]` 字符 |
| 证据 ID | `evidence:` 后跟 64 位小写十六进制 |
| `build_id` 参数 | 64 位小写十六进制 |

格式合法但查不到的 ID 返回 404。两种情况要分开：格式错误是 422，不存在是 404。

### 3.3 批次参数

- 所有新接口都接受可选的查询参数 `build_id`。
  - 不传时，正常返回。
  - 传了且与当前配置一致时，正常返回。
  - 传了但不一致时，返回 409 `snapshot_changed`。
- 所有成功响应都包含 `build_id` 字段。
- 现有的 5 个接口在 M1a 中**不加**这个参数，留到 M1b 统一处理，以免本次改动面过大。

### 3.4 数据访问

- 所有查询都通过现有的 `services.relational()` 执行。它已经提供只读事务、3 秒语句超时、按配置设置 `search_path`，并核对 `build` 表的 id。不另开连接，不绕过这些检查。
- 一个请求中的多条查询，在同一个 `relational()` 上下文中完成，以保证读到同一个快照。
- SQL 全部参数绑定，不拼接用户输入。
- `attributes_json`、`properties_json`、`content_json` 在后端解析为 JSON 对象后再返回。前端不需要二次解析字符串。

### 3.5 证据排序（各接口一致）

同一个实体或同一条边可能有多条证据，统一按以下顺序排列，让最具体的证据排在前面：

1. 按证据类型：`source_quote` → `curated` → `bibliographic` → `auto_extracted` → `rule_inferred`
2. `field_path` 不为空的，排在为空（整条记录）的前面
3. 按 `field_path` 字典序
4. 按 `id`

例如四君子汤→人参这条组成边有两条证据：`/composition/0` 排在第一，整条记录（`field_path` 为空）排在第二。

---

## 4. M1a：接口契约

### 4.1 `GET /api/v1/entities/{id}`：实体详情

**参数**：路径参数 `id`；可选查询参数 `build_id`。

**响应示例**：

```json
{
  "id": "bencaodian:formula:si_jun_zi_tang",
  "type": "formula",
  "label": "四君子汤",
  "dataset": { "id": "bencaodian", "title": "本草典开放数据" },
  "category": "补益剂",
  "review_status": "editor_reviewed",
  "review_status_raw": "editor-reviewed",
  "source_record_id": "source:7b97ace6…",
  "attributes": {
    "description_zh": "脾胃气虚证之代表方……",
    "treatment_principle": { "zh": "益气健脾", "en": "Augment qi and fortify the Spleen" }
  },
  "aliases": [],
  "relation_summary": [
    { "relation": "ASSOCIATED_WITH_PATTERN", "direction": "out", "count": 1 },
    { "relation": "CITED_IN", "direction": "out", "count": 1 },
    { "relation": "CONTAINS", "direction": "out", "count": 4 }
  ],
  "evidence_total": 1,
  "evidence_preview": [
    { "id": "evidence:dba0589b…", "kind": "curated", "field_path": "", "excerpt": null }
  ],
  "build_id": "5a76218e…"
}
```

**字段规则**：

- `attributes`：`attributes_json` 解析后原样返回。后端不翻译、不补字段、不删除字段。
  - 不同类型的字段差别很大，例如本草典方剂有 13 个键，ICD-11 编码只有 `code` 一个键。
- `aliases`：该实体的全部别名，按 `name_norm` 和 `name` 排序，每项包含 `name`、`source_record_id`、`field_path`。
  - 实测每个实体最多 11 个别名，所以不分页。
  - 本草典实体没有别名，返回空数组。
- `relation_summary`：该实体作为起点（`out`）和终点（`in`）的边，按关系类型分组计数，按 `relation`、`direction` 排序。
  - 没有任何边时返回空数组。
- `evidence_total` / `evidence_preview`：实体级证据的总数，以及按 §3.5 排序的前 **20** 条。
  - 预览项不包含原始值，原始值通过 §4.3 获取。
  - 必须预览加分页，不能一次返回全部。实测有 674 个实体的证据超过 20 条，其中 "Bitter medicinal" 有 3,439 条。

**错误**：格式错误 422 `invalid_query`；不存在 404 `entity_not_found`；批次不符 409；数据库问题 503。

### 4.2 `GET /api/v1/entities/{id}/evidence`：实体证据分页

**参数**：`id`、`limit`（默认 20，取 1–50）、`offset`（取 0–10000）、可选 `build_id`。

**响应**：

- `items[]`：每项包含 `id`、`kind`、`field_path`、`excerpt`、`source_record_id`。
- 另有 `total`、`limit`、`offset`、`build_id`。
- 排序按 §3.5。

**错误**：

- 实体不存在时返回 404 `entity_not_found`。
- `offset` 超出 `total` 时返回 200 和空 `items`，不是 404。

### 4.3 `GET /api/v1/evidence/{id}`：证据详情

**参数**：`id`、可选 `build_id`。

**响应示例**（一条组成边的证据）：

```json
{
  "id": "evidence:72340d34…",
  "kind": "curated",
  "field_path": "/composition/0",
  "excerpt": null,
  "target": {
    "kind": "edge",
    "edge": {
      "id": "edge:17d8c5fd…",
      "relation": "CONTAINS",
      "source": { "id": "bencaodian:formula:si_jun_zi_tang", "label": "四君子汤", "type": "formula" },
      "target": { "id": "bencaodian:herb:ren_shen", "label": "人参", "type": "herb" }
    }
  },
  "raw_value": { "dosage": "9g", "herb_key": "ren_shen", "role": "jun", "…": "…" },
  "source_record": {
    "id": "source:7b97ace6…",
    "dataset_id": "bencaodian",
    "filename": "formulas.json",
    "record_key": "si_jun_zi_tang",
    "record_locator": "/0",
    "file_sha256": "…",
    "content": { "…": "完整的原始记录" },
    "content_truncated": false
  },
  "dataset": {
    "id": "bencaodian",
    "title": "本草典开放数据",
    "version_label": "v1 · generated 2026-04-17T05:37:00.984Z",
    "source_url": "https://bencaodian.org/en/about/data/",
    "license_statement": "CC BY-SA 4.0；……",
    "attribution": "Bencaodian Editorial / 本草典编辑部"
  },
  "build_id": "5a76218e…"
}
```

**字段规则**：

- **`target`**：二选一，取决于证据挂在实体上还是边上。
  - 挂在实体上：`{"kind": "entity", "entity": {id, label, type}}`
  - 挂在边上：`{"kind": "edge", "edge": {id, relation, source{...}, target{...}}}`
  - 返回端点的名称，页面不必再查一次。
- **`raw_value`**：把 `field_path` 当作 JSON Pointer（RFC 6901，需要处理 `~0` 和 `~1` 转义），在 `source_record.content_json` 上解析得到。
  - `field_path` 为空字符串时，`raw_value` 就是整条记录。
  - 不同来源的路径基准不同：
    - 本草典：`content_json` 就是原始 JSON 对象，路径形如 `/composition/0`、`/classical_references/0/passage`。
    - TCM-MKG：`content_json` 是包装对象，包含 `fields`、`raw_cells`、`raw_tsv`、`line_start`、`line_end`、`aliases`、`repair`，证据路径一般是 `/fields`。
  - 数据管线的发布检查 `evidence_pointers` 已保证所有路径可以解析。解析失败就说明数据损坏，返回 500 `evidence_pointer_invalid`。
- **`source_record.content`**：解析后的完整 `content_json`。
  - 超过 64 KB（按存储 JSON 的 UTF-8 字节计）时省略完整记录，返回 `content=null`，并把 `content_truncated` 设为 `true`。`raw_value` 保持原值；这不是整个响应体的大小上限。实测最大记录约 13.7 KB（`classical_texts.json`），目前不会触发截断，但这条保护要保留。
  - TCM-MKG 记录中的 `repair` 字段会跟随 `content` 一起返回。例如黄芪（CHP01717）的值为 `remove_exact_extra_empty_column_4`，对应 D6 文件第 1,718 行的定点修复，验收时会检查。
- **`filename`**：只返回数据集内的文件名，不暴露服务器路径。
- **`excerpt`**：只有 `source_quote` 类证据有值，其他类型为 `null`。

**错误**：格式错误 422；不存在 404 `evidence_not_found`；批次不符 409。

### 4.4 `GET /api/v1/relation-queries`：模板查询（M1a 只实现两个模板）

**参数**：

- `template`：取值 `formula_herbs` 或 `herb_formulas`。其他值，包括 M1b 才会实现的模板名，都返回 422 `invalid_query`。
- `entity_id`
- `limit`（默认 20，取 1–50）、`offset`
- 可选 `build_id`

| template | 输入实体类型 | 路径 | 排序 |
| --- | --- | --- | --- |
| `formula_herbs` | `formula` | 方剂 →CONTAINS→ 中药 | `properties.position` 升序（从 0 开始），再按中药 `label`、`id` |
| `herb_formulas` | `herb` | 中药 ←CONTAINS← 方剂 | 方剂 `label`、`id` |

**响应示例**（`formula_herbs`，四君子汤）：

```json
{
  "template": "formula_herbs",
  "entity_id": "bencaodian:formula:si_jun_zi_tang",
  "paths": [
    { "node_ids": ["bencaodian:formula:si_jun_zi_tang", "bencaodian:herb:ren_shen"], "edge_ids": ["edge:17d8c5fd…"] }
  ],
  "nodes": {
    "bencaodian:herb:ren_shen": { "id": "bencaodian:herb:ren_shen", "type": "herb", "label": "人参" }
  },
  "edges": {
    "edge:17d8c5fd…": {
      "id": "edge:17d8c5fd…",
      "relation": "CONTAINS",
      "source_id": "bencaodian:formula:si_jun_zi_tang",
      "target_id": "bencaodian:herb:ren_shen",
      "properties": { "position": 0, "role": "jun", "dosage_raw": "9g", "position_source": "composition", "missing_claim_fields": [] },
      "quality_state": "consistent",
      "evidence_ids": ["evidence:72340d34…", "evidence:cf090792…"]
    }
  },
  "total": 4,
  "limit": 20,
  "offset": 0,
  "build_id": "5a76218e…"
}
```

**规则**：

- **路径方向**：`paths[].node_ids` 总是从输入实体开始。所以在 `herb_formulas` 中，路径是"中药 → 方剂"，与边的实际方向相反；边的真实方向以 `edges` 中的 `source_id` 和 `target_id` 为准。
- **字典范围**：`nodes` 和 `edges` 只包含本页路径中出现的节点和边，其中 `nodes` 也包含输入实体本身。
- **边的属性**：`properties` 原样返回，后端不做以下处理：
  - 不换算剂量，`dosage_raw` 保持原文。
  - 不补 `role` 的空值。猪苓汤→泽泻的 `role` 是 `null`，`quality_state` 是 `conflicting`，接口如实返回。
- **证据**：`evidence_ids` 按 §3.5 排序，实测每条边有 1–2 条。
- **类型校验**：输入实体存在但类型与模板不符时，返回 422 `unsupported_entity_type`，例如对中药使用 `formula_herbs`。实体不存在时返回 404。
- **数据量**：
  - `formula_herbs`：一个方剂最多 15 味药，用默认 `limit` 一页就能取完。
  - `herb_formulas`：一味药最多出现在 61 首方剂中（甘草），需要翻页。

**关于冲突的说明**：数据库只记录了"冲突"这个状态，没有保存冲突的具体取值。猪苓汤中泽泻的角色在来源中同时出现了"臣"和"君"，这一信息只登记在 `datasets/curated/known-issues.json` 和批次报告中。M1a 不扩展数据库结构，页面通过证据链接查看原始记录即可。是否在接口中展示冲突取值，列入 §7 待决事项。

---

## 5. 代码组织与测试

### 5.1 代码组织

这里只约定文件边界，具体实现由开发时决定。

| 文件 | 职责 |
| --- | --- |
| `backend/services.py` | 保留连接、配置、健康检查等现有职责。§3.1 的错误码与状态码映射表放在 `ServiceError` 旁边 |
| `backend/queries.py`（新增） | §4 各接口的 SQL 与结果组装，JSON Pointer 解析和证据排序也放在这里 |
| `backend/schemas.py`（新增） | Pydantic 响应模型，由它生成 OpenAPI，不另写接口文档 |
| `backend/app.py` | 新增路由、ID 格式校验、三个异常处理器（业务错误、参数校验错误、未知 `/api/*` 路径） |

### 5.2 执行计划记录

- 对 §4 的每一条查询，以"四君子汤"和 "Bitter medicinal" 为参数各执行一次 `EXPLAIN (ANALYZE, BUFFERS)`，结果保存到 `docs/query-plans/m1a.md`。
- **检查要求**：`entity`、`edge`、`evidence`、`alias` 四张表上都不能出现顺序扫描（Seq Scan）。
- 现有的索引预计已经够用：
  - `entity` 主键
  - `edge_outgoing(source_id, relation, target_id)` 和 `edge_incoming(target_id, relation, source_id)`
  - `evidence_entity(entity_id, id)` 和 `evidence_edge(edge_id, id)`
  - `alias` 主键，其前缀为 `entity_id`
- 如果执行计划显示需要新索引：
  - 新增 DDL 写进一个独立的追加文件，供 PostgreSQL 和 Vastbase 共用。
  - **不修改** `docs/schema-vastbase.sql`，因为修改它会改变 build_id（见 §2.1）。

### 5.3 测试

新增 `tests/test_api.py`，沿用仓库现有的测试风格：直接用 `.venv/bin/python` 运行，用 TestClient 连接真实的开发库，测试失败时抛出断言错误。

- 测试内容逐条对应验收文档中的功能、错误、安全用例，样例数据也使用验收文档 §3 中的固定值。
- 测试数据要以 ID 和数值写死在测试中，不能在测试里现查数据库再拿来和接口结果比较，否则相当于用实现去验证实现。
- 现有的 4 个测试文件必须继续通过。

### 5.4 文档同步

- `docs/architecture.md` 的"已实现接口"表：加入 4 个新接口，并更新错误规则段落。
- `spec.md` §4：标注 M1a 已完成的接口。
- OpenAPI（`/docs`）中能看到新接口的请求参数和响应模型。

---

## 6. 任务拆分与顺序

估算基于单人开发，每天约 5–6 小时有效工作时间。

| # | 任务 | 依赖 | 估算 |
| --- | --- | --- | --- |
| 1 | M0：确认数据库、切换配置、重建样例、回归测试 | — | 0.5 天 |
| 2 | M0：文档更新与提交 | 1 | 0.25 天 |
| 3 | 错误处理改造、ID 校验、`build_id` 参数，并补测试 | 1 | 0.5 天 |
| 4 | `GET /entities/{id}` 和 `GET /entities/{id}/evidence` | 3 | 0.75 天 |
| 5 | `GET /evidence/{id}`，含 JSON Pointer 解析和截断保护 | 3 | 0.5 天 |
| 6 | `GET /relation-queries` 的两个模板 | 3 | 0.5 天 |
| 7 | 执行计划记录、性能抽样、文档同步 | 4 5 6 | 0.5 天 |
| 8 | 按验收文档自测并填写验收记录 | 7 | 0.5 天 |
| | **合计** | | **约 4 天** |

建议按 4 → 5 → 6 的顺序实现：详情先完成，证据才有入口，模板查询再复用证据排序。

每完成一个任务就提交一次，提交信息中写明任务编号。

---

## 7. 待决事项

以下事项不阻塞 M1a。默认按"暂不处理"执行，需要时再调整。

1. **冲突取值是否在接口中展示**：如果要展示，有两种做法。
   - 让数据管线把 `known-issues` 写入数据库：要改 DDL，会产生新批次。
   - 让后端只读加载批次报告：不需要改数据。
   - 默认：M1a 不展示，页面通过证据查看原始记录。
2. **英文和拼音名称是否参与检索**：属于 M1b 的检索改进，与本次无关，在这里先记下。
3. **旧批次 （schema 名读取配置备份） 何时清理**：建议 M1a 验收通过后再决定，清理需要单独的脚本和确认步骤。
