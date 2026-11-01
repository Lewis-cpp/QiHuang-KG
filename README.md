# QiHuang-KG

面向中医药学习者的知识图谱检索与学习系统。已完成两源清洗、PostgreSQL 入库、详情与证据 API（M1）、资料检索页面（M2）和 Neo4j 全量投影与关系图谱（M3）。主库包含 20,374 个实体、179,502 条关系、291,308 条证据，实体与关系合计 199,876 条。当前使用 PostgreSQL，最终交付前迁移到 Vastbase。模型按用户安排暂不配置，已准备自行接入与验证说明。

- [启动、检查与模型接入](docs/bootstrap.md)
- [M0 + M1a 开发交付说明](docs/dev/m0-m1a-delivery.md)
- [M0 + M1a 验收记录](docs/dev/m0-m1a-acceptance.md)
- [M1b 交付说明](docs/dev/m1b-delivery.md)
- [M2 交付说明](docs/dev/m2-delivery.md)
- [M3 交付说明](docs/dev/m3-delivery.md)
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

另一终端在 `frontend/` 执行 `npm ci`、`npm run dev`，打开 `http://127.0.0.1:5174`。页面提供名称与别名检索、实体详情、证据、来源与统计；每条检索结果和详情页都可进入关系图谱 `/graph/<实体ID>`（一跳展开、关系筛选、中药两跳路径）。接口文档见 `http://127.0.0.1:8000/docs`。`/ai` 页面提供 AI 条件查询：模型只把问题转换为白名单条件，查询由后端参数化执行（M4a）；方剂详情页提供带引用的 AI 解释：模型只依据后端组装的材料生成，逐句校验引用、角色与剂量，失败时降级为只展示材料（M4b）。执行 `npm run build` 后，FastAPI 直接托管 `frontend/dist`（同一 8000 端口提供页面与接口）。**全新环境的部署步骤（依赖、私有配置、导入、模型验证、构建运行、备份恢复与常见故障）见[部署说明](docs/deploy.md)**，另有[启动说明](docs/bootstrap.md)。

## 项目进度

- **M0–M3 已完成**：数据管线、关系库业务 API、检索/详情/证据/来源/统计页面、Neo4j 全量投影与图谱页（验收记录见 `docs/acceptance/`）。
- **M4a/M4b 已完成**：AI 条件查询与带引用的方剂解释（`docs/acceptance/m4-query.json`、`m4-explain.json`、`m4b-browser.json`）。
- **M5 已完成**：冻结评测集一次运行达标（查询 25/25、解释 19/20、对抗关键 13/13，引用可回查 100%），故障演练与 49 条页面回归全过（`m5-eval-test.json`、`m5-drills.json`、`m5-browser.json`）。
- **M6A 已完成**：SQL 可移植性、兼容检查表、PostgreSQL 性能基线（`docs/dev/m6-compat.md`、`m6-bench.json`）；**M6B 阻塞外部**：等待 Vastbase 实例（`m6-vastbase.json`，问题清单 I-003）。
- **M7 已完成**：FastAPI 托管构建产物、部署说明、恢复演练 6/6、交付材料（`m7-recovery.json`、`docs/deploy.md`、`docs/acceptance/final-checklist.md`）。
- 工作日志与真实模型调用计数：`docs/dev/progress.md`；遗留事项：`docs/dev/issues.md`。

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
