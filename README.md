# QiHuang-KG

面向中医药学习者的知识图谱检索与学习系统，提供名称与别名检索、实体详情、来源证据、关系图谱、AI 条件查询和带引用的方剂解释。AI 解释会校验引用、药物角色与剂量；校验失败时降级展示原始材料。

当前使用 PostgreSQL 保存业务数据，Neo4j 提供图谱查询，Vue 前端由 FastAPI 托管。
数据包含 20,374 个实体、179,502 条关系和 291,308 条证据。
Vastbase 的导入与连接入口已准备，尚待真实实例验证。

`main` 只保留运行所需代码、数据、配置示例和本说明。完整开发文档、测试、评测及验收记录保留在 `feat/m7-delivery` 分支。

## 环境要求

- Python 3.12
- Node.js 24（含 npm）
- Docker 与 Docker Compose v2

以下命令在仓库根目录执行。服务默认只监听本机，数据库数据保存在 Docker 命名卷中。

## 首次安装

```sh
git clone https://github.com/Lewis-cpp/QiHuang-KG.git
cd QiHuang-KG
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
python3.12 scripts/setup_services.py
docker compose up -d --wait
.venv/bin/python scripts/prepare_data.py
```

最后一步输出 `release` 路径和 `build_id`。将下面的 `BUILD_ID` 替换为该值，再继续：

```sh
.venv/bin/python scripts/import_vastbase.py --engine postgresql --release var/prepared/BUILD_ID
python3.12 scripts/setup_services.py
.venv/bin/python scripts/setup_reader.py --engine postgresql
.venv/bin/python scripts/project_graph.py
```

导入成功时状态为 `imported`（重复导入为 `reused`）。
第二次运行 `setup_services.py` 根据导入报告生成应用配置；`setup_reader.py` 创建应用只读账号。
图谱首次投影状态为 `projected`，重复执行为 `reused`。

## 构建与启动

```sh
npm --prefix frontend ci
npm --prefix frontend run build
.venv/bin/python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

打开 [项目首页](http://127.0.0.1:8000/)，
[接口文档](http://127.0.0.1:8000/docs)提供全部接口说明。
[健康检查](http://127.0.0.1:8000/api/v1/health)分别返回关系库、图谱和模型状态；
模型未配置时整体为 `degraded`，普通检索与图谱仍可使用。

已有环境再次启动，只需执行 `docker compose up -d --wait`，然后启动后端。前端源码变更后重新构建。

开发时可在另一终端运行以下命令，使用 [前端开发页面](http://127.0.0.1:5174/)；后端仍在 8000 端口运行：

```sh
npm --prefix frontend run dev
```

## 配置 AI 模型

AI 功能需要支持聊天补全、`response_format=json_object` 和 `max_completion_tokens` 的兼容模型服务。普通检索与图谱不依赖模型。

```sh
cp config/model.example.json config/model.json
chmod 600 config/model.json
```

在 `config/model.json` 中填写服务的 `base_url` 和准确的 `model` 名称。`base_url` 不包含 `/chat/completions`。示例使用环境变量提供密钥：

```sh
export QIHUANG_MODEL_API_KEY='替换为你的模型密钥'
env -u all_proxy -u ALL_PROXY .venv/bin/python scripts/verify_environment.py --check-model
```

验证最多产生两次计费调用，通过后模型状态为 `verified`。
验证和后端启动需要使用同一密钥环境变量；修改环境变量后重启后端。
也可在私有 `model.json` 中填写 `api_key`，同名环境变量优先。

模型调用默认超时 30 秒。解释生成可能需要约 20 秒；服务不可用或内容未通过校验时，页面显示原因及原始材料。

## 配置与数据维护

| 文件或目录 | 用途 |
| --- | --- |
| `backend/`、`backend/prompts/` | 业务接口、模型调用、内容校验与运行时提示词 |
| `frontend/` | 页面源码与构建配置，`dist/` 由构建生成 |
| `scripts/` | 数据准备、导入、只读账号、图谱投影、环境验证及建表 SQL |
| `datasets/raw/`、`datasets/curated/` | 两个实际使用的数据源、来源记录和更正依据 |
| `config/*.example.json` | 应用、模型与 Vastbase 配置示例 |
| `config/app.json` | 当前数据库类型、schema 与 `build_id`，由初始化脚本生成 |
| `config/postgresql*.json` | PostgreSQL 导入账号与应用只读账号 |
| `config/neo4j.json`、`config/neo4j.env` | Neo4j 连接与容器认证 |
| `var/` | 私有凭据、数据批次、模型验证及运行报告 |

私有配置、密钥、构建产物与运行数据均被 Git 忽略。初始化脚本复用已有数据库凭据；数据库初始化后，不要仅修改配置文件中的密码。

默认连接地址：PostgreSQL 为 `127.0.0.1:15432`（数据库 `qihuang`），
Neo4j Bolt 为 `127.0.0.1:17687`，
[Neo4j Browser](http://127.0.0.1:17474/)可检查图数据库。

数据准备脚本对原始输入、转换代码与 SQL 计算指纹，生成可重复校验的批次。
更新转换代码后，重新准备数据可能得到新的 `build_id`。
切换已有环境的批次前备份 `config/app.json`；新批次导入成功后，再更新其中的 `schema` 和 `build_id`，
运行 `setup_reader.py`、`project_graph.py` 并重启后端。保留旧 schema 与图谱批次，便于回滚。

### 备份与恢复

保留 `datasets/`、已准备的 `var/prepared/` 批次目录以及私有配置。
关系库可用同一批次重新导入，随后恢复应用配置并重建只读账号授权。
Neo4j 可通过 `project_graph.py` 从当前关系库重新构建；已有完整投影需要重写时使用 `--rebuild`。

`docker compose down` 保留数据库卷；`docker compose down -v` 会删除数据库数据。恢复后检查两库批次一致及健康状态。

### 使用 Vastbase

复制 `config/vastbase.example.json` 与 `config/vastbase_reader.example.json`
为去掉 `.example` 的私有文件，填写真实连接信息。
先运行连接与兼容性检查，再导入同一准备批次：

```sh
.venv/bin/python scripts/import_vastbase.py --engine vastbase
.venv/bin/python scripts/import_vastbase.py --engine vastbase --release var/prepared/BUILD_ID
```

导入成功后，将 `config/app.json` 的 `database_engine` 改为 `vastbase`，
并使用导入报告中的 `schema` 和 `build_id`，
再运行 `setup_reader.py --engine vastbase`、`project_graph.py` 并重启后端。
真实 Vastbase 兼容性与性能仍需在目标实例上验证，PostgreSQL 结果不能代替。

## 常见问题

| 现象 | 处理 |
| --- | --- |
| 图数据库不可用或投影未完成 | 启动 Neo4j 后重新运行 `scripts/project_graph.py` |
| AI 显示模型未就绪 | 检查私有配置、密钥与模型名称，重新执行 `--check-model` 验证 |
| 409 `snapshot_changed` | 页面点击“刷新”，清除保存的旧批次 |
| 503 `build_mismatch` | 核对应用配置与关系库、图谱的 `build_id`，完成授权和投影 |
| 模型返回 401 或 429 | 检查密钥、配额与服务限流 |
| 提示代理配置无效 | 在验证和后端启动命令前加 `env -u all_proxy -u ALL_PROXY` |

## 数据来源与许可

- 本草典开放数据：Bencaodian Editorial / 本草典编辑部，CC BY-SA 4.0。
  来源声明保留在 `datasets/raw/bencaodian/_source-page.md`，
  署名信息在 `datasets/curated/bencaodian.json`。
- TCM-MKG V1.0：Zeng, Jingqi；Jia, Xiaobin，CC BY-NC 4.0。
  原始元数据保留在 `datasets/raw/tcm-mkg/_record.json`，
  数据标识为 DOI `10.5281/zenodo.13763953`。

保留两源数据各自的署名与许可约束。系统用于资料检索与学习，数据及 AI 解释不构成诊疗建议。
