# M6 规格：Vastbase 迁移、兼容性与性能（T02、T08 剩余，T20 性能）

版本：1.0。编写日期：2026-11-01。上位文档：[spec.md](../../spec.md) §9.1–9.2、[Vastbase 迁移说明](../vastbase-import.md)。

M6 分两段。**6A 不需要 Vastbase 实例**，可以立即做；**6B 需要实例**，没有连接配置时如实记为阻塞，不得用 PostgreSQL 的结果代替（spec §9.1 末段）。

---

## 1. 6A：SQL 可移植性（无需实例）

### 1.1 收敛 PostgreSQL 专用写法

`docs/schema-views.sql` 已经用 `CAST(x AS json) ->> 'k'` 读取 JSON 文本列。应用代码中的同类写法改成相同形式，避免依赖 `jsonb` 和 `::` 类型转换：

| 位置 | 现状 | 改为 |
| --- | --- | --- |
| `backend/ai.py` `fragment()` | `attributes_json::jsonb->>%s`、`t.attributes_json::jsonb->>'dynasty_zh'` | `CAST(e.attributes_json AS json)->>%s` 等 |
| `backend/explain.py` | 实现时直接用 `CAST(... AS json)` | — |
| 其余 `backend/*.py` | 用下方的 grep 逐条检查 | 能等价改写的改写；不能改写的记入 1.2 |

检查命令：

```sh
grep -nE "::|jsonb|ILIKE|pg_trgm|DISTINCT ON|FILTER \(|RETURNING|ON CONFLICT" backend/*.py
```

测试文件中的独立 SQL（如 `tests/test_ai.py`、`tests/test_explain.py` 中的 `::jsonb`）只在 PostgreSQL 开发库上运行，不必改。

改完后 `tests/run_all.sh` 必须仍然全绿，`tests/test_api.py` 的性能相关断言不能变慢到失败。

### 1.2 兼容性清单 `docs/dev/m6-compat.md`

逐项列出应用和导入脚本依赖的数据库特性，标明“已在 PostgreSQL 验证 / 需在 Vastbase 验证 / Vastbase 已验证”：

- `COLLATE "C"` 排序；`LIKE … ESCAPE`；`= ANY(%s)`（psycopg2 列表 → 数组）；`CAST(text AS json)->>`；`SET LOCAL statement_timeout`、`SET LOCAL search_path`；`REPEATABLE READ` 只读事务；`COPY` 批量写入；`CREATE OR REPLACE VIEW`；角色与 `GRANT`/`REVOKE`（`setup_reader.py`）；`version()` 的标识字符串。
- 每项写清楚：用在哪个文件哪个函数、Vastbase 上如果不支持的替代方案。

这份清单就是 6B 的检查表。

### 1.3 性能基线：`scripts/bench.py`

只用 httpx（已安装），对**正在运行的** uvicorn 发请求（不是 TestClient），这样测到的是实际服务。

```sh
.venv/bin/python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000   # 另一个终端
.venv/bin/python scripts/bench.py --base http://127.0.0.1:8000 [--ai] [--out docs/acceptance/m6-bench.json]
```

**非 AI 接口**（固定样本，ID 与 `tests/test_api.py` 中的常量一致）：

| name | 路径 |
| --- | --- |
| search_name | `/api/v1/entities?q=四君子汤` |
| search_common | `/api/v1/entities?q=甘草` |
| catalog | `/api/v1/entities?type=herb&offset=100` |
| detail | `/api/v1/entities/bencaodian:formula:si_jun_zi_tang` |
| detail_hub | `/api/v1/entities/tcm-mkg:herbal_piece:CHP01118` |
| neighbors_deep | `/api/v1/entities/tcm-mkg:herbal_piece:CHP01118/relations?relation=HAS_HERBAL_PIECE&direction=in&limit=50&offset=2000` |
| evidence | `/api/v1/evidence/evidence:f1e7866ee0971b80d3d27c8cb7fecf221003b29e87cf8c42d8a6947080d71cec` |
| template | `/api/v1/relation-queries?template=herb_formulas&entity_id=bencaodian:herb:gan_cao` |
| graph | `/api/v1/graph?center=bencaodian:formula:si_jun_zi_tang` |
| graph_hub | `/api/v1/graph?center=<BITTER，见 test_api.py>` |
| graph_paths | `/api/v1/graph/paths?template=<graph.PATH_TEMPLATES 的第一个>&entity_id=bencaodian:herb:ren_shen` |
| stats | `/api/v1/stats` |

- 每个接口：预热 20 次；然后并发 1 和并发 5 各采样**至少 200 次**（并发 5 用 `ThreadPoolExecutor(5)`，总请求数 ≥ 200）。
- 非 200 响应和超时（客户端超时 10 秒）都计入 `failures`，按错误码统计，**不剔除**；分位数在全部样本（含失败）的耗时上计算。
- 目标：P95 ≤ 2,000 ms。

**AI 接口**（`--ai` 时执行，计费）：

- `/ai/query`：dev 集中 5 个 `ok` 问题，各 4 次，并发 1，共 20 次。
- `/ai/explain`：dev 集 5 首方剂各 2 次，并发 1，共 10 次。
- 另做一次并发 5 的 `/ai/query`（5 个请求同时发出），记录 `model_busy` 的个数：这是设计行为（信号量 2），报告中单独说明，不算失败。
- 目标：P95 ≤ 15,000 ms，单次超时 30 秒。

### 1.4 报告 `docs/acceptance/m6-bench.json`

```json
{
  "recorded_at": "…", "engine": "postgresql|vastbase", "purpose": "baseline|acceptance",
  "db_version": "…", "neo4j_version": "…", "build_id": "…",
  "hardware": {"cpu": "…", "cores": 0, "memory_gb": 0, "os": "…"},
  "server": "uvicorn backend.app:app（单进程）",
  "warmup": 20,
  "endpoints": [
    {"name": "search_name", "path": "…", "concurrency": 1, "samples": 200, "ok": 200, "failures": {},
     "p50_ms": 0, "p95_ms": 0, "max_ms": 0, "bytes_p50": 0, "target_ms": 2000, "met": true}
  ],
  "ai": [ {"name": "ai_query", "concurrency": 1, "samples": 20, "ok": 20, "failures": {}, "p50_ms": 0, "p95_ms": 0,
           "max_ms": 0, "target_ms": 15000, "met": true} ],
  "ai_busy_probe": {"sent": 5, "ok": 2, "model_busy": 3},
  "gaps": []
}
```

- PostgreSQL 上跑出的是 `purpose=baseline`，保存为 `m6-bench.json`；Vastbase 上的验收结果保存为 `m6-bench-vastbase.json`（`purpose=acceptance`）。
- 任何 `met=false` 都要在 `gaps` 中写明原因与处理（加索引、改查询或接受）。优化前先用 `EXPLAIN (ANALYZE, BUFFERS)` 定位，执行计划追加到 `docs/query-plans/m6.md`。
- 硬件信息从 `/proc/cpuinfo`、`/proc/meminfo`、`platform` 读取。

---

## 2. 6B：Vastbase 迁移与验收（需要实例）

**前置检查**：`config/vastbase.json` 与 `config/vastbase_reader.json` 是否存在。不存在时：

1. 写 `docs/acceptance/m6-vastbase.json`：`{"status": "blocked", "reason": "未提供 Vastbase 实例连接配置（config/vastbase.json）", "checked_at": "…", "next_steps": ["…用户需要做的事…"]}`。
2. 在 `docs/dev/issues.md` 记一行，级别 `阻断`，状态 `阻塞外部`。
3. 继续做 M7，不要停下等待。

**有实例时**，按 spec §9.1 执行，每一步的命令、输出摘要写入报告：

| 步骤 | 操作 | 报告字段 |
| --- | --- | --- |
| 1 | 记录产品版本、兼容模式、字符集、驱动版本；`import_vastbase.py`（默认 `--engine vastbase`）环境探测 | `product_version, compat_mode, encoding, driver, probe` |
| 2 | `import_vastbase.py --release var/prepared/<build_id>` | `import_report`（引用 `var/vastbase-report.json` 中的状态与计数） |
| 3 | 两库对照：每张表行数、`table_sha256`（取两份导入报告）；`schema-views.sql` 每个视图的 `count(*)` 与按 `id` 排序前 100 行的 SHA-256 | `comparison.tables[]`、`comparison.views[]`，每项 `equal` |
| 4 | 在 Vastbase 上运行 `scripts/setup_reader.py`（必要时按兼容清单改写），然后用只读账号尝试 `INSERT/UPDATE/DELETE/CREATE`，全部失败 | `reader_write_denied: true`，附错误码 |
| 5 | 临时把 `config/app.json` 的 `database_engine` 改为 `vastbase`（schema 不变），运行 `tests/test_api.py`、`tests/test_ai.py`、`tests/test_explain.py`、`eval/run_eval.py --split dev --only D-Q01 D-Q03 D-E01` | `api_tests`、`ai_smoke` |
| 6 | 确认 Neo4j 投影 `build_id` 与 Vastbase 批次一致，`/graph` 200 | `graph_build_match: true` |
| 7 | `scripts/bench.py` 在 Vastbase 上运行 | `m6-bench-vastbase.json` |

报告整体 `status`：全部通过为 `passed`，任何一步失败为 `failed`（附 `failure`），并在问题清单登记。验收后应用配置保留在 Vastbase 还是切回 PostgreSQL，由用户决定；默认切回 PostgreSQL 并在报告 `final_engine` 中写明。

兼容问题的处理原则：先改成两库都支持的写法（共享 DDL 和查询），实在不行才按 `database_engine` 分支，并在 `m6-compat.md` 记录。

---

## 3. 出口

- 6A：`m6-compat.md` 完成；应用代码无 `::jsonb`；`run_all.sh` 全绿；`m6-bench.json`（PostgreSQL 基线）全部接口有结果，未达标项有分析。
- 6B：`m6-vastbase.json` 为 `passed`，或为 `blocked` 且问题清单中有对应的“阻塞外部”行。`failed` 不能作为出口状态。
