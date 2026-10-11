# M1b 交付说明：业务查询接口

日期：2026-10-11。上位文档：[spec.md](../../spec.md) §4.1–§4.7。批次：`5a76218e52001d45e4bd75e099a38780408e873342a14e5db0c86d7bb7a3008a`。

本次只交付 M1b 中的业务查询接口。业务视图、独立只读账号（T11）和健康检查的 `full` 投影取值不在本次范围内，见第 4 节。

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

## 4. 尚未完成

- §4.8 业务视图 `v_formula_composition`、`v_entity_relation_summary` 及其追加 DDL。
- §4.8 只读账号 `qihuang_reader` 及 `42501` 写入失败实测。
- §4.1 健康检查的 `projection=full` 取值，依赖 M3 的全量投影标记。
- 前端尚未使用新接口（M2）。
