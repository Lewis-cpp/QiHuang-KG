# QiHuang-KG

面向中医药学习者的知识图谱检索与学习系统。已完成两源清洗、PostgreSQL 入库、Neo4j 样例验证、Vue + FastAPI 最小链路及 M1a 详情与证据 API。主库包含 20,374 个实体、179,502 条关系、291,305 条证据，实体与关系合计 199,876 条。当前使用 PostgreSQL，最终交付前迁移到 Vastbase。模型按用户安排暂不配置，已准备自行接入与验证说明。

- [启动、检查与模型接入](docs/bootstrap.md)
- [M0 + M1a 验收记录](docs/dev/m0-m1a-acceptance.md)
- [首版范围冻结](docs/scope-freeze.md)
- [环境验证记录](docs/environment-report.json)
- [原型架构阅读版（历史）](architecture-design.html)
- [开发计划与课程验收要求](docs/development-plan.md)
- [架构设计正文](docs/architecture.md)
- [项目范围分析](project-scope-analysis.html)
- [数据集指南](datasets/dataset-guide.html)
- [SQLite 建表脚本](docs/schema.sql)
- [核心数据结构审计](docs/data-profile.json)
- [数据处理结果与运行说明](docs/data-processing.md)
- [两源数据质量复核](docs/data-quality-report.json)
- [PostgreSQL 开发库与 Vastbase 迁移说明](docs/vastbase-import.md)

SQLite 用于保留本草典原型及生成离线清洗批次，不作为正式主库验收。最终交付要求 Vastbase、NoSQL、AI 和十万条以上数据，范围与实现以[冻结说明](docs/scope-freeze.md)和[v2 架构](docs/architecture.md)为准。

## 克隆仓库

原始古籍方剂文件 `datasets/raw/ancient-formulas-sqlite/metadata.sqlite` 由 Git LFS 管理。先在本机安装 Git LFS，再执行：

```sh
git lfs install
git clone https://github.com/Lewis-cpp/QiHuang-KG.git
cd QiHuang-KG
git lfs pull
```

## 运行项目

恢复已有开发环境：

```sh
python3 scripts/setup_services.py
docker compose up -d --wait
.venv/bin/python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

另一终端在 `frontend/` 执行 `npm ci`、`npm run dev`，打开 `http://127.0.0.1:5174`。页面提供真实统计、名称与类型检索、连接状态、四君子汤关系样例；M1a 详情、证据和组成查询可通过 `/docs` 或 curl 使用；前端详情、交互图谱和 AI 功能留待后续阶段。全新环境的依赖安装与数据导入见[启动说明](docs/bootstrap.md)。

开发库位于 `127.0.0.1:15432`，库名 `qihuang`。私有连接配置为 `config/postgresql.json`；密码自动生成并复用，未纳入版本管理。PostgreSQL 与 Neo4j 均通过 Docker 命名卷持久化。

生成两源标准化批次并验证（Python 标准库即可）：

```sh
python3 scripts/prepare_data.py
python3 tests/test_data_pipeline.py
```

导入上述命令输出的批次（需要安装 `requirements-vastbase.txt` 中的共享驱动）：

```sh
.venv/bin/python scripts/import_vastbase.py --engine postgresql --release var/prepared/实际构建ID
```

两种数据库共享 DDL、导入与校验流程。最终迁移时显式使用 `--engine vastbase` 和实际实例配置，具体步骤见[运行说明](docs/vastbase-import.md)。运行报告区分 PostgreSQL 开发入库与 Vastbase 最终验收。

原本草典基线继续保留，使用 Python 3.10 或以上版本，无需安装第三方依赖：

```sh
python3 scripts/import_core.py
python3 scripts/audit_core_data.py --check
python3 tests/test_import_core.py
```

导入命令输出数据库绝对路径与构建 ID。数据库位于 `var/releases/<build_id>/kg.sqlite`，同目录包含发布清单 `manifest.json` 和问题报告 `report.json`；同一输入重复执行会验证并复用快照。报告另存于 `datasets/processed/<build_id>.json`。

开发顺序与最终验收标准见开发计划，原型接口约定见架构设计。`datasets/raw/` 中原始文件保持不变。本草典别名表为空，TCM-MKG 提供 2,972 条来源别名；1 处角色冲突与 35 条未关联书目已按具体记录登记，处理规则见运行说明。
