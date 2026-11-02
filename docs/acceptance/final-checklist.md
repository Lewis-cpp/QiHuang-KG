# 最终检查表（m7-spec §4）

四项硬性要求逐项签收；每项给出证据文件与实测数字。状态与证据文件一致：`已通过` / `阻塞外部` / `未通过`。
撰写日期：2026-11-02。批次：`cbadd11ea5c8…`（其余 47 位见 `config/app.json` 或各报告 `build_id` 字段）。

## 四项硬性要求

| # | 要求 | 状态 | 证据与实测数字 |
| --- | --- | --- | --- |
| 1 | **Vastbase 作为正式业务主库** | **阻塞外部** | 无实例连接配置（`config/vastbase.json` 不存在）。6A 已完成全部无需实例的工作：SQL 收敛（`backend/` 无 `::jsonb`）、兼容检查表 [m6-compat.md](../dev/m6-compat.md)（13 项）、PostgreSQL 基线 [m6-bench.json](m6-bench.json)。实机验收记录 [m6-vastbase.json](m6-vastbase.json) 状态 `blocked`，附实例就绪后的 7 步验收流程；问题清单 I-003。**PostgreSQL 上的结果不代替 Vastbase 验收** |
| 2 | **NoSQL（Neo4j）真实使用** | **已通过** | 全量投影 20,374 节点 / 179,502 边，ID 摘要与主库一致（[m3-backup-restore.json](m3-backup-restore.json)，dump/load 演练前后一致）；图接口实际查询 Neo4j（`/graph`、`/graph/paths`，`graph_source=neo4j`）；图请求在投影完成度与批次上强校验（503 `projection_not_ready` / `build_mismatch`） |
| 3 | **AI 真实参与理解与生成** | **已通过** | 条件查询：模型只提白名单条件，后端参数化执行（冻结 test 集 25/25，注入 4/4 无越权）；解释：材料编号 → 模型生成 → 逐句校验（引用可回查 503/503=100%，角色/冲突/剂量校验拦截 T-E15 的编造剂量并降级）。证据：[m5-eval-test.json](m5-eval-test.json)、[m4-explain.json](m4-explain.json)、[m4-query.json](m4-query.json)；模型 `deepseek-flash`，提示词 `query_v1` / `explain_v1` |
| 4 | **十万条以上数据（100,000+）** | **已通过** | 业务记录 199,876 = 实体 20,374 + 业务关系 179,502（口径"去重实体 + 业务关系"），另有证据 291,308、来源记录 197,287、别名 2,972。证据：[m6-bench.json](m6-bench.json)（`build_id`）与导入报告 `var/postgresql-report.json`（`import_result.verification.counts`） |

## 其他验收项

| 项 | 状态 | 证据 |
| --- | --- | --- |
| P0 固定用例 | 已通过 | `tests/test_api.py`（F-01–F-24 及 M1b/M3 扩展）、`tests/run_all.sh` 全绿；页面用例 49/49（[m5-browser.json](m5-browser.json)） |
| 评测指标 | 已通过（解释完成率 0.95、查询 1.0、对抗关键 13/13） | [m5-eval-test.json](m5-eval-test.json)（冻结集一次运行）；未达标项与降级样本见 gaps 与问题清单 I-002；事实支持率待人工审核（[m5-explain-review.json](m5-explain-review.json)，301 句，`reviewer` 留空） |
| 性能 | 已通过 / 1 项接受 | [m6-bench.json](m6-bench.json)：非 AI 全部 P95 ≤ 2000ms；ai_query 达标；ai_explain 超目标已接受（I-004） |
| 恢复 | 已通过 | [m7-recovery.json](m7-recovery.json)：临时库导入（table_sha256 与主库一致）→ 只读账号写入 42501 → test_api 复验 → 清理 → 部署检查，6/6 |
| 部署 | 已通过 | FastAPI 托管 `frontend/dist` + SPA 回退（[m7-recovery.json](m7-recovery.json) `deploy_check`；`tests/test_deploy.py`）；部署手册 [docs/deploy.md](../deploy.md) |
| 演示与论文材料 | 已完成 | [docs/demo-script.md](../demo-script.md)（备用方案内嵌）；[docs/thesis/figures.md](../thesis/figures.md)（Mermaid 图源 + 引用报告的数字表）；录屏与论文正文由使用者完成 |
| 遗留事项 | 1 项阻塞外部，3 项已接受 | [docs/dev/issues.md](../dev/issues.md)：I-003 Vastbase 实例（阻塞外部）、I-002 T-E15 降级（已接受）、I-004 解释时延（已接受）、I-001 证候建议（已接受） |

## 使用者接下来需要做的事

1. 提供 Vastbase 实例后执行 [m6-spec §2](../dev/m6-spec.md) 的 7 步（详见 [m6-vastbase.json](m6-vastbase.json) 的 `next_steps`），把 I-003 与本表第 1 行更新为实测结论。
2. 人工填写 [m5-explain-review.json](m5-explain-review.json) 的 `facts` / `supported` / `reviewer`，然后运行 `.venv/bin/python eval/run_eval.py --score-review` 得到事实支持率（≥ 0.95 为达标）。
3. 按 [docs/demo-script.md](../demo-script.md) 录制演示视频；论文正文按 [docs/thesis/figures.md](../thesis/figures.md) 引用报告数字。
