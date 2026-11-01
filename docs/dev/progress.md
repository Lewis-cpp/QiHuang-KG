# 剩余开发进度（M4b → M7）

本文件是自动化开发代理的工作记忆。每完成一步、每次卡住、每次上下文重新开始，都先读这里，再更新这里。规则见 [agent-prompt.md](agent-prompt.md)。

## 当前状态

- 起点：分支 `feat/m4-model-client`（M4a 完成，尚未合并到 `main`），提交 `c743090`。
- 基线：`tests/run_all.sh` 于 2026-11-01 全部通过（`test_explain.py` 因模块未写而跳过）。
- 模型：`deepseek-flash`，`config/model.json` 已验证（`verified`）。运行真实调用前去掉 SOCKS 代理变量。
- Vastbase：没有实例配置（`config/vastbase.json` 不存在）。

## 里程碑清单

- [ ] M4b 带引用的方剂解释（[m4b-spec.md](m4b-spec.md) §12 步骤 1–7）
- [ ] M5 评测、演练与回归（[m5-spec.md](m5-spec.md) §8 步骤 1–6）
- [ ] M6A 可移植性与性能基线（[m6-spec.md](m6-spec.md) §1）
- [ ] M6B Vastbase 验收或记录阻塞（[m6-spec.md](m6-spec.md) §2）
- [ ] M7 部署、恢复与交付（[m7-spec.md](m7-spec.md)）

## 真实模型调用计数

以 `var/ai-calls.jsonl`（每次真实调用一行，含失败重试）为准；本任务自 2026-11-01 起共 **161 次**（截至 M5 步骤 5），预算 1000 次。

| 日期 | 用途 | 调用次数 |
| --- | --- | --- |
| 2026-11-02 | M4b：probe 3 + 调试/页面验收 + 10 首记录（explain 端点合计） | 70 |
| 2026-11-02 | M5：dev 集 + 页面回归 AI 用例 + test 集（query 端点合计） | 88 |
| — | 其中 explain-probe 子命令 3 次、`record_m4.py explain` 11 行、test 集 66 行、dev 集 24 行，其余为页面回归与调试 | — |

（说明：早期手记的 22 次与后续会话的多次页面验收存在重复/遗漏，最终以日志行数为准；日志中 `usage=null` 的 validation_failed 行不是调用，不计入。）

## 日志

（每步一条，最新的在最下面：日期、步骤、结果、提交、下一步。）

- 2026-11-02 基线确认：`tests/run_all.sh` 全绿（`test_explain.py` 因模块未写而跳过）。提交提供的脚手架（6e13b2f）并切出 `feat/m4b-explain`。
- 2026-11-02 M4b 步骤 1–4：`backend/explain.py`、`prompts/explain_v1.md`、schemas、`POST /api/v1/ai/explain`。`tests/test_explain.py` 一次通过；`run_all.sh` 全绿。提交 5011b9b。
- 2026-11-02 M4b 步骤 2（probe）：3 首最大方剂全部 `finish_reason=stop`；completion token 含推理（2630/3211/1846），正文约 560，未触发 1024 上限 → 保持 20 句/120 字，不建 v2。见 `m4-explain-probe.json`。期间定位并修复一个 500：句子有角色标记但某分句没有标记且含组成药名时 `nearest()` 返回 `None`；已修复并在 `tests/test_explain.py` 增加回归用例（新增用例，未改动任何原有断言）。
- 2026-11-02 M4b 步骤 5：`AIExplanation.vue` + EntityView 挂载 + types + 样式；`npm run build` 通过。页面验收 `m4b-browser.json` 23/23 全过（1280/390 两宽度：按钮不自动请求、角标进证据页可后退、降级原因、模型未就绪、390 无横向滚动；生成用真实模型，降级/未就绪用 `tests/browser/stub_backend.py`）。验收脚本与替身后端在 `tests/browser/`（`node_modules` 已被 Git 忽略）。
- 2026-11-02 M4b 步骤 6：`record_m4.py explain` 10 首全部 `ok`，引用 241/241 可回查（100%），`zhu_ling_ze_xie_role_stated=false`，降级演练通过。`m4-explain.json` 已生成。
- 2026-11-02 M4b 步骤 7：spec.md §7.2 指向 m4b-spec（已由脚手架完成）；m4-development.md §11 追加实施记录；README 进度更新；cases.md 增加 M4、M4B、M5 三节。下一步：推送并开 M4b PR，然后进入 M5。
- 2026-11-02 M4b 收尾（中断恢复）：会话在最终回归失败后中断，由监控会话接手。失败原因：app.py 未处理异常日志在收尾时被改为 `exc_info=True`（带 traceback），违反 test_api.py 对日志恰为 `Unhandled API exception: ValueError` 的合同断言；按"验收测试是合同"恢复原格式（只记类型名，客户端仍不见细节）。重跑 `tests/run_all.sh` 全绿（exit=0）。提交 3b3d38a（19+1 个文件），随后推送分支并开 M4b PR。下一步：进入 M5。
- 2026-11-02 M5 步骤 1–2（恢复续作）：接手时发现 `feat/m5-eval-regression` 分支上有一笔把 M5 半成品混进 M4b 提交信息的历史（88c43db，未推送）。软回退后按规格改名为 `feat/m5-eval`，把 run_eval.py 与 dev 报告以正确的 `feat(m5)` 信息重新提交（5655740）。dev 集一次达标（查询 11/11、解释 5/5 引用 120/120、对抗 4/4），提示词保持 v1 无需迭代；修复 run_eval.py 两处：人工审核表须写顶层数组（交付合同）、`--score-review` 在 0 句已填时崩溃。
- 2026-11-02 M5 步骤 3：`tests/drill_m5.py` 八项检查全过（M5-01…M5-06，含 Neo4j/PostgreSQL 停机与恢复），`m5-drills.json` 已生成（7348fc6）。期间修复演练脚本自身两处：M5-01 未排除 model.json、M5-03 的查询替身用错输出形态。
- 2026-11-02 M5 步骤 4：`tests/browser/m5_check.mjs` 驱动 cases.md 全部 49 条页面用例（M2/M3/M4/M4B），无头 Chrome 1280/390 两宽度，AI 用例用真实模型、降级与停机用替身后端和 Docker 停服，最终 49/49 全过，`m5-browser.json` 已生成（57699bd）。期间修复 `scripts/project_graph.py` 复用路径的崩溃（driver 5 把时间属性返回为 neo4j.time.DateTime，json.dumps 抛 TypeError；归一为 ISO 字符串）。页面回归迭代中发现并修正脚本自身的选择器竞态与断言错误（如 M3-07 的真实总数是 2,284=2,278 饮片+6 药性，而非 2,278）。经验：Vite dev server 长时间跨编辑运行会进入坏状态，重启后 /graph 懒加载恢复正常。
- 2026-11-02 M5 步骤 5：冻结 test 集（60 样本）完整运行一次：查询 25/25=1.0、解释 19/20=0.95（引用 503/503=1.0）、对抗 15/15（关键 13/13），全部达标。唯一未过样本 T-E15（银翘散）：查库证实模型两次都编造剂量（写 6g/5g/6g，材料为 9g/4g/9g），校验正确拦截并降级，非误判，已记 I-002。`m5-eval-test.json/.md` 与 `m5-explain-review.json`（301 句，reviewer 留空）已生成。模型调用总计以 var/ai-calls.jsonl 为准（见下表）。下一步：run_all.sh 全绿、推送并开 M5 PR。

## 测试争议

（认为某条已提供的验收测试与 spec 矛盾时写在这里：哪条断言、为什么、怎么改的。没有就留空。）
