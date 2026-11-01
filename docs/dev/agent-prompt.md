# 给开发代理的提示词（M4b → M7）

把下面“---”之间的全文作为代理的任务提示。开头三项启动参数由用户在启动前填写。

---

## 启动参数

- `ALLOW_PUSH`：`yes`（只在本地提交；`yes` 时每个里程碑完成后推送分支并开 PR，不合并）
- `MODEL_CALL_BUDGET`：`1000`（真实模型调用总次数上限，含重试；超出前停下并在进度文件中说明）
- `VASTBASE`：`none`（有实例时改为“已配置 config/vastbase.json 与 config/vastbase_reader.json”）

## 你的任务

你在仓库 `QiHuang-KG`（中医药知识图谱：FastAPI + Vue + PostgreSQL/Vastbase + Neo4j + 大模型）中独立完成剩余开发：**M4b 带引用的方剂解释 → M5 评测与回归 → M6 Vastbase 与性能 → M7 部署与交付**。设计已经写好，你负责按设计写代码、跑测试、修错，循环直到验收测试通过。这是一项长时间任务：不要做完一步就停，也不要在中途向用户提问；遇到只有用户能解决的问题（例如缺少 Vastbase 实例），按规则记录为阻塞，然后继续做其余工作。

**完成的定义**（全部满足才算结束）：

1. `tests/run_all.sh --with-deploy` 输出 `ALL PASSED`。
2. `.venv/bin/python tests/test_delivery.py` 输出 `PASS: …`，或在没有 Vastbase 实例时输出 `PASS with BLOCKED: vastbase`。
3. `docs/dev/progress.md` 有“## 最终总结”一节。

## 每次开始（包括上下文被压缩或会话重启后）

1. 读 `docs/dev/progress.md`，再看 `git status` 和 `git log --oneline -15`，确认自己做到哪一步。
2. 读当前里程碑的 spec 全文。不要凭记忆写接口。
3. 确认服务在运行：`docker compose ps`（PostgreSQL、Neo4j 健康）；没有就 `docker compose up -d --wait`。

## 必读文档（第一次按顺序全部读完）

1. `spec.md`：全局约定（§2）、里程碑（§3）、AI（§7）
2. `docs/dev/m4-development.md`：M4 的公共约束与 M4a 的实施记录
3. `docs/dev/m4b-spec.md`、`m5-spec.md`、`m6-spec.md`、`m7-spec.md`：你要实现的内容
4. 已有代码：`backend/ai.py`、`backend/model_client.py`、`backend/queries.py`、`backend/services.py`、`backend/app.py`、`backend/schemas.py`；前端 `frontend/src/views/AIQueryView.vue`、`EntityView.vue`、`api/client.ts`
5. 已提供的验收测试：`tests/test_explain.py`、`tests/test_eval_sets.py`、`tests/test_deploy.py`、`tests/test_delivery.py`、`tests/run_all.sh`
6. 评测集：`eval/dev.jsonl`、`eval/test.jsonl`

## 不可违反的规则

### 测试与评测

- `eval/test.jsonl` 和 `eval/test.jsonl.sha256` 已冻结，**绝不修改**。提示词只能按 dev 集调整（m5-spec §3）。
- 已提供的验收测试是合同。不要删除断言、放宽条件、加 `try/except` 吞掉失败，或者改成“跳过”。如果你确信某条断言与 spec 矛盾或依据的数据事实有误：先在数据库里查证，把证据写进 `progress.md` 的“测试争议”，然后只做最小修改并保持原意。同一文件的争议修改不超过 3 处；超过说明是你的实现方向错了。
- 验收记录（`docs/acceptance/*.json`）必须由脚本实际运行产生。不能手写、手改或从旧结果复制数字。失败的结果如实保留，在 `gaps` 和问题清单中解释。
- PostgreSQL 上的结果不能写成 Vastbase 验收通过。
- 人工审核表（`m5-explain-review.json`）的 `reviewer` 字段留给人填写，你不能签名。

### 代码

- 不新增 Python 或 npm 依赖。需要的东西都已安装（httpx、pydantic、FastAPI、psycopg2、neo4j、vite、vue）。唯一例外是页面验收用的 playwright-core：本机没有，按下文“页面验收”的方式装在被 Git 忽略的 `tests/browser/node_modules`。
- 沿用仓库风格：Python 测试用 `python tests/xxx.py` 直接运行、带断言、不引入 pytest；错误消息用中文；函数小而直接；注释只写“为什么”。
- SQL 一律参数绑定；模型输出永远不进入 SQL、Cypher 或文件路径（spec §2.4）。
- 模型调用不能放在 `services.relational()` 上下文里（M4 开发文档 §3）。
- 修改提示词必须新建版本文件（`*_v2.md`），旧版本保留。
- 不提交密钥、`config/*.json`（示例文件除外）、`var/` 下的文件。提交前 `git status` 检查。
- 不对主环境执行破坏性操作：不 `docker compose down -v`、不删除主库 schema、不清空 Neo4j 主库、不 `git push --force`、不改写已有提交。恢复演练只在临时对象上做（m7-spec §3）。

### 真实模型调用

- 运行前去掉 SOCKS 代理：`env -u all_proxy -u ALL_PROXY …`。
- 只在以下场景发起真实调用：`record_m4.py explain --probe`（3 次）、`record_m4.py explain`（10 首，含重试最多 20 次）、`verify_environment.py --check-model`（仅在改了模型配置后，2 次）、`run_eval.py --split dev`（每轮约 25–35 次）、`run_eval.py --split test`（约 60–80 次，原则上只跑一次）、页面验收、`bench.py --ai`（约 35 次）。
- 每次运行后在 `progress.md` 的“真实模型调用计数”表中记账。接近 `MODEL_CALL_BUDGET` 时停止调用，先完成不需要模型的工作，最后在总结中说明。
- 单元测试和回归一律用替身（`patch.object(model_client, 'complete_json')`），绝不计费。

### Git

- M4b 从 `feat/m4-model-client` 切出 `feat/m4b-explain`；之后每个里程碑在上一个分支上切新分支：`feat/m5-eval`、`feat/m6-portability`、`feat/m7-delivery`。不在 `main` 上提交，不合并到 `main`。
- 每完成 spec 中的一个步骤提交一次，提交信息沿用仓库格式：`feat(m4b): …`、`fix(m5): …`、`test(m5): …`、`docs(m7): …`，正文一两句说明为什么。
- `ALLOW_PUSH=yes` 时，里程碑完成后推送分支并用 `gh pr create` 开 PR（目标为上一个里程碑的分支，M4b 的目标为 `feat/m4-model-client`），PR 描述列出出口条件和验收记录链接。

## 工作循环（每个步骤都这样做）

1. **对齐**：重读该步骤在 spec 中的条文和对应测试，列出要改的文件（含调用方、schemas、前端类型、文档）。
2. **实现**：写能通过该步骤测试的最小完整实现。优先复用已有函数（`queries.require_entity`、`queries.position_key`、`queries.edge_evidence`、`queries.normalize_query`、`services.relational`、`model_client.complete_json/record`、前端 `post()`、`StateView`、`EvidenceLinks` 等）。
3. **验证**：先跑该步骤的测试；失败就读完整输出，定位根因再改，不要盲改。然后跑 `tests/run_all.sh`，确认没有回归。
4. **自审**：`git diff` 逐行读一遍：是否有多余代码、是否漏改调用方、错误码与 spec 是否一致、有没有把模型文字回显到页面、有没有泄露密钥或路径。
5. **提交并记录**：提交；在 `progress.md` 日志追加一条（日期、步骤、测试结果、提交哈希、下一步）。
6. 进入下一步。里程碑全部步骤完成后，对照该 spec 的“出口”逐条核对，在 `progress.md` 勾选。

## 里程碑顺序与检查命令

| 里程碑 | spec | 该段完成时必须通过 |
| --- | --- | --- |
| M4b | `docs/dev/m4b-spec.md` §12 | `tests/test_explain.py`；`run_all.sh`；`m4-explain-probe.json`、`m4-explain.json`、`m4b-browser.json` 已生成且满足 m4b-spec §12 |
| M5 | `docs/dev/m5-spec.md` §8 | `tests/test_eval_sets.py`；`m5-eval-dev.json`、`m5-eval-test.json`、`m5-explain-review.json`、`m5-drills.json`、`m5-browser.json`；关键对抗样本 13/13 |
| M6A | `docs/dev/m6-spec.md` §1 | `run_all.sh`；`backend/` 无 `::jsonb`；`m6-compat.md`；`m6-bench.json` |
| M6B | `docs/dev/m6-spec.md` §2 | `m6-vastbase.json` 为 `passed`，或 `blocked` 且问题清单有“阻塞外部”行 |
| M7 | `docs/dev/m7-spec.md` §5 | `run_all.sh --with-deploy`；`test_delivery.py` |

建议在 M4b 第 1 步之前先跑一次 `tests/run_all.sh`，确认基线全绿再动代码。

页面验收沿用 M4a 的做法：系统 `google-chrome` 加 playwright-core 无头运行，前端用 `npm run dev`（Vite 代理到 8000）或构建后由 FastAPI 托管。验收脚本放在 `tests/browser/`（新建），输出格式同 `docs/acceptance/m4a-browser.json`。在 `tests/browser/` 下执行 `npm init -y && npm install playwright-core@1.56.1`（`node_modules/` 已被 Git 忽略；`tests/browser/package.json` 与锁文件可以提交），用 `executablePath: "/usr/bin/google-chrome"` 启动，不下载浏览器，不写入 `frontend/package.json`。

## 卡住时

- 同一个失败连续修 3 次仍不通过：停下来，把失败输出、你的假设和已尝试的做法写进 `progress.md`，换一个思路（重读 spec、查数据库实际数据、缩小复现）。
- 连续 5 次仍不通过：在 `docs/dev/issues.md` 记一行（级别按实际影响），状态 `未处理`，先做后面不依赖它的步骤，最后回头处理。结束前所有 `阻断` 行都必须处理掉或证明是外部阻塞。
- spec 本身有矛盾或遗漏：选最保守、最小的做法实现，在 spec 对应位置补一句说明，并写进 `progress.md`。不要扩大范围。
- 数据与 spec 描述不一致：以数据库实测为准，更新 spec 中的数字并注明测量日期和批次。

## 结束时

在 `progress.md` 写“## 最终总结”：

- 每个里程碑的结果（一句话 + 验收记录链接）。
- 四项硬性要求（Vastbase、Neo4j、AI、十万条数据）的状态，与 `docs/acceptance/final-checklist.md` 一致。
- 未达标的指标与原因。
- 需要用户做的事：例如提供 Vastbase 实例后执行 m6-spec §2；人工填写解释审核表并运行 `run_eval.py --score-review`；录制演示视频。
- 真实模型调用总次数与费用（如有单价）。

然后输出同样内容的简短版本作为你的最后一条消息。

---
