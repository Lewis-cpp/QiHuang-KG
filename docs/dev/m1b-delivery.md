# M1b 交付说明：业务查询、业务视图与只读账号

日期：2026-10-11。上位文档：[spec.md](../../spec.md) §4。批次：`5a76218e52001d45e4bd75e099a38780408e873342a14e5db0c86d7bb7a3008a`。

M1b 分两次合入：第一次是第 1–3 节的业务查询接口（PR #3）；第二次是第 4 节的业务视图、只读账号（T11）、健康检查投影取值和导入回滚演示。存储过程仍待 spec §11 确认，没有实现。

## 1. 接口

| 方法与路径 | 内容 |
| --- | --- |
| `GET /entities` | 新增 `dataset` 过滤和 `build_id`；有查询词时按五级命中排序，每项带 `match {field, text}`，每个实体只出现一次；查询词为空时仍按类型目录返回，`match` 为 `null` |
| `GET /entities/{id}/relations` | `relation`（7 种关系）与 `direction`（`out`/`in`）必填；返回 `items[{edge, neighbor}]` 和 `total` |
| `GET /relation-queries` | 补齐 `formula_patterns`、`herb_patterns_via_formula`、`patent_medicine_pieces`、`piece_patent_medicines`、`piece_properties` |
| `GET /datasets` | `dataset` 表全部字段，加每个来源的实体数、关系数和来源记录数 |

检索命中级别依次为：名称精确、别名精确、名称前缀、别名前缀、名称或别名子串。同一实体有多处命中时取级别最高的一处；同级时名称优先于别名，别名之间按规范文本排序。

## 2. 实现约定

- 七个模板和通用关系列表共用 `queries.TEMPLATES` 与 `fetch_paths`。SQL 中的列名和关系方向只来自固定表，关系类型、实体 ID、分页值全部参数绑定。
- 排序与 M1a 修复保持一致：文本排序键一律 `COLLATE "C"`，即码位顺序，不随数据库区域设置变化；最后一个排序键总是 `id`。
- 方剂组成（`CONTAINS` 出边）按 `properties.position` 排序，空值在后，再按中药名称和 ID。位置保存在 JSON 文本中，所以这一种查询取全部组成后在 Python 中排序（单个方剂最多几十味药）。其余查询在 SQL 中计数和分页，甘草饮片的 2,278 个中成药、Bitter medicinal 的 3,439 个饮片都按页读取。
- `CONTAINS` 入边（药物反查方剂）按方剂名称排序，与 `herb_formulas` 一致；药物在不同方剂中的位置没有可比性。spec §4.4 已按此修订（2026-10-11 确认）。
- `herb_patterns_via_formula` 按完整路径返回，同一证候经由不同方剂到达时保留为不同路径；响应带固定的 `note`："该药出现在某方剂中，该方剂在来源数据中关联某证候"。一跳模板的 `note` 为 `null`。
- 关系类型与实体类型不匹配时，`/entities/{id}/relations` 返回 200 空列表；`/relation-queries` 仍返回 422 `unsupported_entity_type`。
- `/datasets` 中的关系数按起点实体所属来源统计；当前数据中每条关系的两端都属于同一来源。
- `/entities` 的检索查询从 `services.py` 移到 `queries.py`，并改为从同一快照读取 `build_id`。

## 3. 验证

在云端容器中重建了本地 PostgreSQL 16.15，用 `prepare_data.py` 从仓库原始数据重新生成同一批次（`build_id` 一致）并用 `import_vastbase.py --engine postgresql` 导入。没有 Docker，也没有 Neo4j。

| 检查 | 结果 |
| --- | --- |
| `tests/test_api.py` | 通过。M1a 原有用例全部保留；新增检索、邻居分页、五个模板、来源目录用例，含成功、空结果、404、409、422 |
| 区域设置无关排序 | 在 `en-US-x-icu` 排序规则下构造样本，确认模板排序仍为码位顺序 |
| `tests/test_data_pipeline.py`、`test_import_core.py`、`test_database_config.py` | 通过 |
| `tests/test_app.py` | 未运行完成：需要 Neo4j |
| `tests/measure_m1b.py` | 执行计划见 [m1b.md](../query-plans/m1b.md)，HTTP 耗时见 [m1b-performance.json](../acceptance/m1b-performance.json)；12 个场景 P95 均在 100 ms 以内 |

子串检索使用 `LIKE '%词%'`，执行计划中 entity 和 alias 为顺序扫描，单字"草"的 P95 约 27 ms，远低于 spec §4.2 评估 `pg_trgm` 的 2 秒门槛，因此不引入新索引。关系与证据查询的计划中没有 edge/evidence 顺序扫描。

以上记录来自 PostgreSQL 16.15，不是 Compose 中的 PostgreSQL 18.6；在开发机上重跑 `tests/test_api.py` 和 `tests/measure_m1b.py` 可得到目标环境的结果。

## 4. 数据库工作（spec §4.8）

### 4.1 业务视图

`docs/schema-views.sql` 定义两个视图，追加在共享 DDL 之后：

| 视图 | 列 |
| --- | --- |
| `v_formula_composition` | `edge_id`、`formula_id`、`formula_label`、`herb_id`、`herb_label`、`dosage_raw`、`role`、`position`、`quality_state` |
| `v_entity_relation_summary` | `entity_id`、`relation`、`direction`（`out`/`in`）、`count` |

- `import_vastbase.py` 在导入事务中执行该文件，并校验四君子汤的组成和关系汇总覆盖全部 179,502 条边。复用已有 schema 时只追加视图，所以已有环境重跑一次导入命令即可升级。
- 环境探测（`probe`）也在随机 schema 中创建视图，Vastbase 若不支持其中的 JSON 写法会在探测阶段暴露。
- 实体详情的 `relation_summary` 改为读取 `v_entity_relation_summary`。执行计划显示过滤条件下推到两个分组子查询，分别使用 `edge_outgoing` 和 `edge_incoming` 索引。

### 4.2 只读账号（T11）

- `setup_postgres.py` 生成 `config/postgresql_reader.json`（`0600`，重复执行复用，密码必须与导入账号不同）。
- `scripts/setup_reader.py` 用导入账号创建或更新 `qihuang_reader`：`LOGIN`，无超级用户、建库和建角色权限，`default_transaction_read_only=on`，只授予 `config/app.json` 所选批次（或 `--schema` 指定批次）的 `USAGE` 与 `SELECT`。授权后逐表核对：可读、不可写、不可在 schema 或数据库中建对象，不满足即回滚。
- `services.relational()` 改用 `<engine>_reader` 配置连接，导入账号只供脚本使用。Vastbase 使用 `config/vastbase_reader.json`，模板为 `config/vastbase_reader.example.json`。
- 实测（`tests/test_api.py` 的 `reader_checks`，记录在 [m1-readonly.json](../acceptance/m1-readonly.json)）：默认会话中 `UPDATE` 以 `25006` 失败；显式 `SET TRANSACTION READ WRITE` 后，`INSERT`、`UPDATE`、`DELETE`、`CREATE TABLE`、`CREATE VIEW`、在 `public` 建表、`CREATE SCHEMA` 均以 `42501` 失败。

### 4.3 健康检查投影取值

`/health` 中 `neo4j.projection` 取 `full`（当前批次存在完整的 `scope:'full'` 投影标记，M3 写入）、`sample`（只有完整样例）或 `not_ready`。Neo4j 不可用时也返回 `not_ready`。

### 4.4 导入失败回滚演示

`tests/record_m1.py` 在开发库中把同一份数据以新批次号 `ffff…` 导入：建表、视图和 47 万余行 COPY 都在事务中完成，随后批次校验失败（`Target build mismatch`），整个事务回滚。记录在 [m1-import-rollback.json](../acceptance/m1-import-rollback.json)：失败后不存在新 schema，当前批次七张表的行数与失败前一致，`/stats` 响应不变。该演示为了让失败发生在数据库写入之后，跳过了暂存库校验（篡改过的清单在那一步就会被拒绝）。

### 4.5 验证

| 检查 | 结果 |
| --- | --- |
| `tests/test_api.py` | 通过；新增视图、投影取值、只读账号用例 |
| `tests/test_database_config.py` | 通过；新增只读账号凭据的生成、复用、权限与密码隔离 |
| `tests/test_import_core.py` | 通过 |
| `tests/record_m1.py` | 通过，生成上述两份记录 |
| `scripts/setup_reader.py` | 首次创建、再次执行更新均通过 |

环境与第 3 节相同：PostgreSQL 16.15，无 Docker、无 Neo4j。本地库的 TCP 连接使用 `scram-sha-256` 密码认证，只读账号用配置中的密码登录成功，错误密码被拒绝。

## 5. 尚未完成

- 存储过程：等待 spec §11 第 2 项确认。
- 在 Compose 的 PostgreSQL 18.6 和 Vastbase 上重跑本文全部测试（Vastbase 部分属于 M6）。
- 前端尚未使用新接口（M2）。
