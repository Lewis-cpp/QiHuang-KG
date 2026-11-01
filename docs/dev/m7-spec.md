# M7 规格：部署、恢复与交付（T21、T22）

版本：1.0。编写日期：2026-11-01。上位文档：[spec.md](../../spec.md) §9.3–9.4、[开发计划](../development-plan.md) §8–9。验收测试：`tests/test_deploy.py`、`tests/test_delivery.py`（已写好）。

---

## 1. 生产形态：FastAPI 托管前端

`npm run build` 生成 `frontend/dist/`，由同一个 uvicorn 进程提供页面和接口。改动只在 `backend/app.py`，不新增依赖（`starlette.staticfiles` 已随 FastAPI 安装）。

规则：

1. `frontend/dist/index.html` **不存在**时，行为与现在完全一致（开发模式用 Vite 代理）。启动时判断一次。
2. 存在时：
   - `/assets/*` 由 `StaticFiles(directory=dist/'assets')` 提供；不存在的文件返回 404（不是 `index.html`），路径穿越（`/assets/../…`）不能读到 `dist/assets` 之外的文件。
   - `/api/*` 的路由与错误处理保持不变：未知 `/api/...` 仍是 JSON 404 `not_found`。
   - 其他任何 `GET` 路径（`/`、`/entity/…`、`/graph/…`、`/ai`、`/config/model.json`、`/var/postgres-password` 等）都返回 `index.html`，`Content-Type: text/html`。**只**从 `dist` 读文件，绝不把请求路径映射到仓库目录。
   - `dist` 根目录下除 `index.html` 外的文件（如 `favicon.ico`，若有）可以按文件名提供，但必须先确认解析后的路径仍在 `dist` 内。
3. `index.html` 响应带 `Cache-Control: no-cache`；`/assets/*` 带长缓存是可选项。
4. 现有 `/docs`、`/openapi.json` 保持可用（FastAPI 自带路由优先于回退）。

实现方式（参考）：在所有路由注册之后 `app.mount('/assets', ...)`，再注册 `@app.get('/{path:path}', include_in_schema=False)` 作为回退，回退函数里对 `api/` 开头的路径抛出 404 交给已有处理器。

验收：`npm run build` 后运行 `tests/test_deploy.py` 通过；再用 `uvicorn` 实际启动，浏览器打开 `http://127.0.0.1:8000/graph/bencaodian:formula:si_jun_zi_tang` 并刷新，页面正常（写入 `m7-recovery.json` 的 `deploy_check`）。

---

## 2. 部署说明 `docs/deploy.md`

面向“拿到仓库的另一台机器”，按顺序写可直接复制的命令，并说明每一步的成功标志。至少包含：

1. 前置：Python 3.12、Node 22+、Docker（Compose v2）、Git LFS；端口 8000、15432、17474、17687。
2. 拉取与 LFS；`python3 -m venv .venv`、`pip install -r requirements.lock -r requirements-vastbase.txt`。
3. 私有配置：`config/*.example.json` → 实际文件，权限 600；`QIHUANG_MODEL_API_KEY` 环境变量；哪些文件绝不提交（对照 `.gitignore`）。
4. 数据：`prepare_data.py` → `import_vastbase.py --engine postgresql --release …` → `setup_reader.py` → `project_graph.py`；Vastbase 用 `--engine vastbase`。
5. 模型：`verify_environment.py --check-model`（会产生 2 次计费调用），SOCKS 代理需 `env -u all_proxy -u ALL_PROXY`。
6. 构建与运行：`cd frontend && npm ci && npm run build`；`uvicorn backend.app:app --host 127.0.0.1 --port 8000`；只监听本机，如需对外由反向代理负责 TLS。
7. 检查：`/api/v1/health` 的三项状态含义；`tests/run_all.sh`。
8. 备份与恢复：引用 §3 的演练步骤。
9. 常见故障：Neo4j 未就绪、模型未验证、`snapshot_changed`、`build_mismatch`。

`README.md` 的“运行项目”一节改为链接到部署说明，并把进度描述更新为实际完成情况（M4b、M5、M6 状态如实写）。

---

## 3. 恢复演练 → `docs/acceptance/m7-recovery.json`

**不得**对主环境执行 `docker compose down -v`、删除主库 schema 或清空 Neo4j 主库。演练全部在临时对象上完成，结束后删除临时对象。

| 步骤 | 操作 | 判定 |
| --- | --- | --- |
| relational_restore | 在同一 PostgreSQL 实例中 `CREATE DATABASE qihuang_restore`；用临时配置目录（`QIHUANG_CONFIG_DIR`）和 `import_vastbase.py --engine postgresql --config <临时> --release var/prepared/<build_id> --report <临时>` 导入 | 导入状态 `imported`；各表行数与 `table_sha256` 与主库导入报告相同 |
| reader_setup | 在 `qihuang_restore` 上运行 `setup_reader.py`（临时配置） | 只读账号可读、写入失败 |
| api_recheck | 临时 `app.json` 指向 `qihuang_restore`，运行 `tests/test_api.py` | 通过 |
| graph_restore | 引用 `docs/acceptance/m3-backup-restore.json` 的 dump/load 结果；再对主 Neo4j 运行一次 `project_graph.py`，结果为 `reused` | `reused`，节点与边数量一致 |
| cleanup | `DROP DATABASE qihuang_restore`；删除临时配置 | 主库 `/api/v1/health` 仍为 `ready`/`degraded` 且 `build_id` 未变 |
| deploy_check | 构建前端，uvicorn 启动，无头 Chrome 打开并刷新三个深链接（实体、图谱、`/ai`） | 页面标题正确，无控制台错误（`favicon.ico` 404 除外，若已提供 favicon 则不应出现） |

格式：`{"checked_at": "…", "build_id": "…", "steps": [{"name": "relational_restore", "ok": true, "command": "…", "detail": "…"}]}`。命令中不得出现密码。

若 `import_vastbase.py` 不支持目标数据库名参数，就用临时配置文件中的 `dbname` 指定；需要的小改动可以做，但不能改变其默认行为。

---

## 4. 交付材料

| 文件 | 内容 |
| --- | --- |
| `docs/acceptance/final-checklist.md` | 四项硬性要求逐项一张表：**Vastbase**、**NoSQL（Neo4j）**、**AI**、**十万条以上数据**。每项列出验收证据的文件链接、实测数字、状态（`已通过` / `阻塞外部` / `未通过`）。另列 P0 用例、评测指标、性能、恢复、部署五项。状态必须与证据文件一致，不能写“已通过”而证据是 `blocked` |
| `docs/demo-script.md` | 五分钟演示脚本，按开发计划 §9 的 5 步：每步的页面、输入、预期画面、讲解要点（1–2 句）、备用方案（模型不可用时展示哪个已记录的结果） |
| `docs/thesis/figures.md` | 论文用图的 Mermaid 源码：系统架构图、ER 图（7 张表）、图模型、AI 两条链路的时序图；评测与性能结果表（数字引用报告文件，不手抄后改） |
| `README.md` | 更新进度与链接 |
| `tests/cases.md` | M2–M5 全部用例 |

录屏和论文正文由用户完成，不在自动化范围内。

---

## 5. 出口（最终验收）

1. `tests/run_all.sh` 全绿（含 `test_deploy.py`，运行前已 `npm run build`）。
2. `.venv/bin/python tests/test_delivery.py` 通过。它只允许一种“通过但有阻塞”的情况：Vastbase 为 `blocked`，此时输出 `PASS with BLOCKED: vastbase` 并在最终检查表中标为“阻塞外部”。
3. `docs/dev/progress.md` 写有最终总结：完成了什么、哪些阻塞在外部、用户接下来需要做什么（例如提供 Vastbase 实例后执行 m6-spec §2）。
