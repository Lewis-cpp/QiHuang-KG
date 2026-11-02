# 部署说明（m7-spec §2）

面向"拿到仓库的另一台机器"，按顺序执行。每一步都给出成功标志；命令可直接复制。
本仓库的交付形态：FastAPI 同进程提供 `/api/v1` 接口与 `frontend/dist` 静态页面（`npm run build` 后自动生效）。

## 1. 前置条件

| 依赖 | 版本 | 用途 |
| --- | --- | --- |
| Python | 3.12 | 后端、脚本、评测 |
| Node.js | 22+（含 npm） | 前端构建（vue-tsc + vite） |
| Docker + Compose v2 | 任意近期版本 | PostgreSQL 18 与 Neo4j 5.26 |
| Git LFS | 与仓库要求一致 | 拉取原始数据集 |
| 端口 | 8000 / 15432 / 17474 / 17687 | 后端、PostgreSQL、Neo4j HTTP/Bolt，全部只监听本机回环 |

成功标志：`python3 --version`、`node --version`、`docker compose version`、`git lfs version` 都能执行。

## 2. 拉取代码与依赖

```sh
git clone <仓库地址> QiHuang-KG && cd QiHuang-KG
git lfs pull
python3 -m venv .venv
.venv/bin/pip install -r requirements.lock -r requirements-vastbase.txt
```

成功标志：`requirements.lock` 安装无报错；`.venv/bin/python -c "import fastapi, httpx, psycopg2, neo4j"` 不抛异常。

## 3. 私有配置

数据库凭据由脚本生成，其余从示例复制并填写（权限 600，**绝不提交**，`.gitignore` 已排除）：

| 文件 | 内容 |
| --- | --- |
| `config/postgresql.json` / `config/postgresql_reader.json`、`var/postgres-password` | `setup_services.py` 生成：导入账号与只读账号连接、Compose 的 PostgreSQL secret |
| `config/neo4j.json`、`config/neo4j.env` | `setup_services.py` 生成：Neo4j 连接与 Compose 的 `NEO4J_AUTH` |
| `config/app.json` | 第 4 步导入完成后再次运行 `setup_services.py` 按导入报告生成，**不要从示例复制** |
| `config/model.json` | `base_url`、`model`、`api_key` 或 `api_key_env`、`timeout_seconds`、`max_completion_tokens` |

```sh
python3 scripts/setup_services.py              # 生成数据库与 Neo4j 凭据（重跑复用，不轮换）
cp config/model.example.json config/model.json && chmod 600 config/model.json
export QIHUANG_MODEL_API_KEY='sk-…'   # 模型 key 优先走环境变量，不落盘
```

成功标志：`config/neo4j.env`、`var/postgres-password` 与上表 JSON 存在且 `git status` 不显示它们；此时尚无 `config/app.json`。用 Vastbase 时另从 `vastbase*.example.json` 复制。模型 key、数据库密码不进入 Git、日志与报告。

## 4. 数据准备与导入（PostgreSQL + Neo4j）

```sh
docker compose up -d --wait                     # PostgreSQL 18 + Neo4j 5.26，等待健康
python3 scripts/prepare_data.py                 # 清洗两源，产出 var/prepared/<build_id>/
.venv/bin/python scripts/import_vastbase.py --engine postgresql --release var/prepared/<build_id>
python3 scripts/setup_services.py              # 按导入报告生成 config/app.json（选择应用批次）
.venv/bin/python scripts/setup_reader.py --engine postgresql
.venv/bin/python scripts/project_graph.py       # 全量投影 Neo4j（幂等，重跑 reused）
```

成功标志：
- `import_vastbase.py` 输出 `"status": "imported"`；再次运行的 `setup_services.py` 据此写出 `config/app.json`（`schema`、`build_id`）；
- `setup_reader.py` 结尾 JSON 显示 `hardened` 与只读账号写入全部失败；
- `project_graph.py` 输出 `status: projected`（首跑）且节点 20,374、边 179,502。

Vastbase：`import_vastbase.py --engine vastbase`（默认即 vastbase），同一批次目录；连接信息填 `config/vastbase.json` 与 `config/vastbase_reader.json`。验收流程见 [m6-spec §2](dev/m6-spec.md)。

## 5. 模型验证（产生 2 次计费调用）

```sh
env -u all_proxy -u ALL_PROXY .venv/bin/python scripts/verify_environment.py --check-model
```

成功标志：三项 `passed`，`var/model-verification.json` 记录配置指纹。开发机带 SOCKS 代理时必须 `env -u all_proxy -u ALL_PROXY`，否则报"代理配置无效"。

## 6. 构建与运行

```sh
cd frontend && npm ci && npm run build && cd ..
.venv/bin/python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

成功标志：
- `http://127.0.0.1:8000/` 打开检索页（FastAPI 托管 `frontend/dist`；`dist/index.html` 不存在时回退为"仅接口"模式，前端改用 `npm run dev` 的 5174 端口）；
- `http://127.0.0.1:8000/api/v1/health` 的三项服务状态正常；
- 只监听 127.0.0.1，对外 exposure 由反向代理负责 TLS。

`/api/v1/health` 状态含义：`database`（关系库连接与批次一致）、`neo4j`（图库连接与投影状态 `full/sample/not_ready`）、`model`（`verified`=最近一次真实调用通过；健康检查不调用模型）。整体 `ready` 需三者全部正常。

## 7. 验收检查

```sh
bash tests/run_all.sh                # 全量回归（不含计费调用），预期末行 ALL PASSED
bash tests/run_all.sh --with-deploy  # 追加 test_deploy.py（需先 npm run build）
```

成功标志：`ALL PASSED`。评测与性能基线见 `eval/run_eval.py --split test`（计费）与 `scripts/bench.py`。

## 8. 备份与恢复

- 关系库：从批次目录重新导入（`import_vastbase.py`，幂等）；完整演练见 `tests/drill_m7.py`（在临时数据库上执行并清理）。
- 图库：`docker compose exec neo4j neo4j-admin database dump neo4j --to-path=dumps`，恢复用 `database load --overwrite-destination=true` 后重跑 `project_graph.py` 应为 `reused`；演练记录见 [m3-backup-restore.json](acceptance/m3-backup-restore.json)。
- 恢复后判定：两库 `build_id` 一致，`/api/v1/health` 回到 `ready`，接口复验通过（`tests/drill_m7.py` 的 api_recheck 步骤）。

## 9. 常见故障

| 现象 | 原因与处理 |
| --- | --- |
| 图页面"图数据库暂时不可用" | Neo4j 未启动或投影未完成：`docker compose up -d --wait neo4j` 后重跑 `project_graph.py`；`projection=not_ready` 时接口返回 503 |
| `/ai` 显示"模型未就绪" | `config/model.json` 缺失、key 未配置，或未通过 `--check-model` 验证（指纹不符）；重新执行第 5 步 |
| 接口返回 409 `snapshot_changed` | 请求携带的 `build_id` 与当前配置不一致：前端点"刷新"清除保存的批次 |
| 接口返回 503 `build_mismatch` | `config/app.json` 的 `build_id` 与库中 `build` 表不一致：核对导入输出后修正配置 |
| 模型 502 `model_http_error` | 模型服务返回 4xx/5xx（401=key 无效，429=限流）；看消息中的状态码 |
| SOCKS 代理报"代理配置无效" | `all_proxy` 指向 SOCKS 时 httpx 初始化失败；用 `env -u all_proxy -u ALL_PROXY` 运行 |

---

运行项目（开发模式、数据来源与License说明）见 [README](../README.md)；进度与验收记录索引见 [docs/dev/progress.md](dev/progress.md) 与 [docs/acceptance/](acceptance/)。
