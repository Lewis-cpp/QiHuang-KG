# M6A 兼容性清单（m6-spec §1.2）

应用与导入脚本依赖的数据库特性，逐项标注验证状态。**这是 6B（Vastbase 实例验收）的检查表**：
6B 时每项在 Vastbase 上复验，并把本表的状态改为「Vastbase 已验证」，写明实测值。

状态图例：✅ 已在 PostgreSQL 验证（当前批次 `cbadd11e…`，2026-11-02）｜⏳ 需在 Vastbase 验证。

| # | 特性 | 用在哪 | 说明与 Vastbase 替代方案 | 状态 |
| --- | --- | --- | --- | --- |
| 1 | `COLLATE "C"` 排序 | `backend/queries.py`（检索、关系、模板排序）、`backend/ai.py`（分类清单）、`backend/explain.py`（证候/出处材料排序）、`docs/schema-views.sql` | 按码位排序，保证两库结果顺序一致。Vastbase（PostgreSQL 兼容模式）支持 C collation；若不支持，用 `ORDER BY convert_to(x,'UTF8')` 字节序替代，逐处改写 | ✅ / ⏳ |
| 2 | `LIKE … ESCAPE`（反斜杠转义） | `backend/queries.py` `search_page`（`like_escape` 后的 `name_norm LIKE %s`） | 依赖 LIKE 默认转义符为反斜杠（standard_conforming_strings=on）。若 Vastbase 默认不同，显式写 `LIKE %s ESCAPE '\'` | ✅ / ⏳ |
| 3 | `= ANY(%s)`（psycopg2 列表→数组） | `backend/ai.py`（朝代取值列表）、`backend/explain.py`（按 edge 批量查证据）、`backend/queries.py` `edge_evidence` | 数组字面量参数绑定。Vastbase 兼容；若驱动不传数组，改为 `IN` 元组展开（仍参数绑定） | ✅ / ⏳ |
| 4 | `CAST(text AS json) ->> 'key'` | `backend/ai.py` `fragment()`（药性/给药途径/出处朝代）、`docs/schema-views.sql` | m6-spec §1.1 已把 `::jsonb` 全部收敛为 `CAST(x AS json)`；M6B 需复验 attributes_json 为合法 JSON 文本。若 json 类型缺 `->>`，用 `json_extract_path_text(CAST(x AS json), 'k')` | ✅ / ⏳ |
| 5 | `%(type)s::text IS NULL` 参数类型固定 | `backend/queries.py` `SEARCH_HITS`/`CATALOG_FROM` | psycopg2 传 None 时需要已知类型才能比较。PostgreSQL 标准语法，Vastbase 应兼容；备选 `CAST(%(type)s AS text)` | ✅ / ⏳ |
| 6 | `SET LOCAL statement_timeout='3000ms'` | `backend/services.py` `relational()` | 只读会话的语句级超时。Vastbase 支持 statement_timeout；若 SET LOCAL 作用域不同，改用连接参数 `options='-c statement_timeout=3000'` | ✅ / ⏳ |
| 7 | `SET LOCAL search_path TO {schema}, pg_catalog`（`sql.Identifier` 组合） | `backend/services.py` `relational()`、导入脚本 | schema 名只来自校验过的配置并用 `sql.Identifier` 引用。Vastbase 兼容 | ✅ / ⏳ |
| 8 | `REPEATABLE READ` 只读事务 | `backend/services.py` `relational()`（`set_session(readonly=True)`） | 快照一致性：一次请求内所有语句读同一版本。Vastbase 兼容；若隔离级别名不同，按其文档映射 | ✅ / ⏳ |
| 9 | `COPY … FROM STDIN`（`copy_expert`） | `scripts/import_vastbase.py` 批量导入 | 导入账号执行。Vastbase 支持 COPY；若不支持流式，回退 `execute_values` 分批 | ✅ / ⏳ |
| 10 | `CREATE OR REPLACE VIEW` | `docs/schema-views.sql`（`v_formula_composition`、`v_entity_relation_summary`） | 共享 DDL，两库同源。Vastbase 兼容 | ✅ / ⏳ |
| 11 | 角色与 `GRANT`/`REVOKE`、`ALTER ROLE … SET default_transaction_read_only` | `scripts/setup_reader.py`（`qihuang_reader` 只读账号）、写入失败测试（42501/25006） | M6B 在 Vastbase 上重建角色并重跑写入失败测试 | ✅ / ⏳ |
| 12 | `version()` 标识字符串 | `backend/services.py` `database_health`、`import_vastbase.py` `identify`（产品版本/兼容模式探测） | 原样展示，不做解析依赖；Vastbase 的 version() 串直接记录进 m6-vastbase.json | ✅ / ⏳ |
| 13 | psycopg2 `sql.SQL`/`sql.Identifier` 组合 | 所有动态表名/schema 名处 | 客户端驱动能力，与服务器版本无关 | ✅ / ⏳ |

已确认**不使用**的 PostgreSQL 专有特性（grep 于 2026-11-02，`backend/*.py`）：`::jsonb`（已收敛为 CAST，见 #4）、`ILIKE`、`pg_trgm`、`DISTINCT ON`、`FILTER (…)`、`RETURNING`、`ON CONFLICT`、存储过程、触发器。

`tests/*.py` 中的独立 SQL（`tests/test_ai.py`、`tests/test_explain.py` 的 `::jsonb`）只在 PostgreSQL 开发库上运行，按 m6-spec §1.1 不改。
