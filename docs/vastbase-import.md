# 两源清洗、PostgreSQL 开发库与 Vastbase 迁移

实施日期：2026-10-04。按当前安排，先用 PostgreSQL 18.6 完成开发，最终交付前迁移到 Vastbase。两源数据已实际导入持久化的 PostgreSQL 开发库。Vastbase 环境验证和迁移留到最后阶段。本文件补充并替代原型架构中的存储与数据范围约定。

本次实际批次、逐表摘要、测试状态和环境结果保存到[验证报告](data-pipeline-report.json)。PostgreSQL 开发入库与 Vastbase 最终验收分别记录，不再让缺少 Vastbase 阻塞后续应用开发。

2026-10-08 补齐 ID 前缀校验、实体证据覆盖和来源所属数据集检查。最新全量复核、质量计数与 PostgreSQL 导入结果见[质量复核报告](data-quality-report.json)；应用当前选择的批次仍见下表。

## PostgreSQL 开发环境

项目根目录的 `compose.yaml` 固定已验证镜像的摘要，使用命名卷 `qihuang-kg_postgres_data` 保存数据，并配置容器健康检查。启动步骤：

```sh
python3 scripts/setup_services.py
docker compose up -d --wait
```

`setup_services.py` 复用 `setup_postgres.py` 生成随机密码、权限为 `0600` 的 `config/postgresql.json` 和 `var/postgres-password`，同时准备 Compose 所需的 Neo4j 私有配置。重复执行复用现有凭据；两份凭据不一致时拒绝覆盖。Compose 从 secret 文件读取 PostgreSQL 密码。首次入库完成后再次执行 `setup_services.py` 选择应用批次，完整顺序见[阶段启动说明](bootstrap.md)。开发库仅监听回环地址，连接参数如下：

| 配置 | 当前值 |
| --- | --- |
| 主机与端口 | `127.0.0.1:15432` |
| 数据库 | `qihuang` |
| 维护账号 | `qihuang_import` |
| 私有连接文件 | `config/postgresql.json` |
| 当前数据 schema | `qihuang_cbadd11ea5c86dc3d7654c46` |
| 当前构建 ID | `cbadd11ea5c86dc3d7654c4652b06e23a77245af728fee2f1c46c9382ced867e` |

安装共享驱动并完成环境验证和入库：

```sh
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements-vastbase.txt
.venv/bin/python scripts/import_vastbase.py --engine postgresql
.venv/bin/python scripts/import_vastbase.py --engine postgresql --release var/prepared/cbadd11ea5c86dc3d7654c4652b06e23a77245af728fee2f1c46c9382ced867e
```

新生成的批次使用 `prepare_data.py` 输出的目录。PostgreSQL 模式默认读取 `config/postgresql.json`，也可使用 `POSTGRES_DSN`；默认报告为 `var/postgresql-report.json`，标记 `engine=postgresql`、`purpose=development`，`vastbase=null`。Vastbase 模式继续使用独立的配置、DSN 和报告路径。

日常管理：

```sh
docker compose ps
docker compose stop
docker compose up -d --wait
docker compose exec postgres psql -U qihuang_import -d qihuang
```

在数据库会话中选择当前发布批次后即可查询：

```sql
SET search_path TO qihuang_cbadd11ea5c86dc3d7654c46, pg_catalog;
SELECT type, count(*) FROM entity GROUP BY type ORDER BY type;
SELECT relation, count(*) FROM edge GROUP BY relation ORDER BY relation;
```

容器重建仍使用同一个命名卷；`docker compose down` 保留数据卷，`docker compose down -v` 会删除数据。维护账号用于本地数据导入；应用使用只读账号 `qihuang_reader`，由 `scripts/setup_reader.py` 创建和授权，见[阶段启动说明](bootstrap.md#m1-只读账号与业务视图)。导入时在同一事务中执行 `docs/schema-views.sql` 创建业务视图并校验；复用已有 schema 时只追加视图。环境探测同样在随机 schema 中创建视图，提前暴露 Vastbase 的 JSON 兼容问题。

## 当前结果

| 指标 | 本草典 | TCM-MKG | 合计 |
| --- | --- | --- | --- |
| 实体 | 599 | 19,775 | 20,374 |
| 去重业务关系 | 1,286 | 178,216 | 179,502 |
| 有效业务记录 | 1,885 | 197,991 | 199,876 |

标准化暂存库另有 197,287 条来源记录、2,972 条来源提供的别名、291,308 条证据和 2 个数据集。证据、别名、原始备份及历史批次不计入十万条业务记录。本草典六张数据表在复制后逐表比较完整内容摘要，原有 1 处角色冲突和 35 条未关联书目保留。

| TCM-MKG 文件 | 原始逻辑记录 | 接受 | 拒收 | 唯一业务记录 |
| --- | --- | --- | --- | --- |
| D1 术语 | 1,810 | 1,810 | 0 | 1,810 |
| D2 中成药 | 8,977 | 8,977 | 0 | 8,977 |
| D3 中成药—术语 | 11,185 | 11,185 | 0 | 11,184 |
| D4 中成药—饮片 | 74,084 | 74,084 | 0 | 74,084 |
| D5 中成药—编码 | 69,431 | 69,431 | 0 | 69,431 |
| D6 饮片 | 6,207 | 6,207 | 0 | 6,207 |
| D7 饮片—药性 | 23,517 | 23,517 | 0 | 23,517 |

D5 另外产生 2,758 个去重编码实体，D7 另外产生 23 个药性实体。TSV 按带引号和多行字段的格式读取，上表为逻辑记录数，不是物理行数。

## 清洗与模型

- 保留已有本草典 ID；TCM-MKG 使用独立的 `tcm-mkg:<type>:<key>` 命名空间。同名中药、饮片、经典方剂、中成药不合并。
- D1、D2、D6 的 ID 分别只接受 `TCMT`、`CPM`、`CHP` 前缀及五位数字。引用一致但前缀用错的输入也会终止构建。
- D6 物理第 1,718 行 `CHP01717` 多出一个空列。规则同时核对文件名、物理行号和整行 SHA-256，只删除该行的第 4 个空字段。原行、原列数组、修复规则及位置均保留，未知列数异常直接失败。
- D3 的 `CPM07546 → TCMT00784` 合并为一条关系，保留两条证据。原始 `Synonyms` 一方为空、一方非空，采用非空值；两个不同的非空属性值则设为 `null`，在 `conflicts` 保留全部值并标记 `conflicting`。真实样本无新增冲突，测试覆盖了冲突分支。
- 原始文本完整保留；搜索名称使用 NFKC、首尾空格清理与大小写折叠。空白属性标准化为 `null`，剂量比例保留原字符串，`0` 不视为缺失值，不换算剂量。
- D1、D6 的中文同义词只按来源的竖线分隔，保存来源和派生数组定位。它们是来源声明，审核状态为 `unknown`，不用于自动合并实体或生成等价医学结论。
- D5 编码节点只显示原始编码，不补造疾病名称。D7 节点以分类和药性名称共同确定身份。
- 每条来源保存文件 SHA-256、逻辑记录序号、起止物理行、原始 TSV 和解析字段。证据通过 JSON Pointer 定位；中药引文保持原值。
- `dataset` 读取本地来源登记，保留版本、DOI 和署名；TCM-MKG 登记为 `cc-by-nc-4.0`。

| 来源类型 | 实体类型 | 关系 |
| --- | --- | --- |
| 本草典中药、方剂、证候、古籍 | `herb / formula / pattern / text` | 保留 `CONTAINS / ASSOCIATED_WITH_PATTERN / CITED_IN` |
| D1 / D2 / D6 | `tcm_term / patent_medicine / herbal_piece` | D3：`ASSOCIATED_WITH_TERM`；D4：`HAS_HERBAL_PIECE` |
| D5 | `icd11_code` | `MAPPED_TO_ICD11` |
| D7 | `medicinal_property` | `HAS_MEDICINAL_PROPERTY` |

[v2 DDL](schema-vastbase.sql)继续使用七张表。JSON 保存为经过校验的 UTF-8 `TEXT`，避免依赖不同兼容模式下的 JSON 函数。一个来源记录可能产生编码节点与关系，因此 v2 不再要求实体的 `source_record_id` 唯一。外键、唯一性、枚举与证据目标互斥由数据库约束；端点类型、证据覆盖、来源定位与内容摘要是导入提交前的验证条件。当前没有在线写接口，后续增改必须重新构建并验证批次。

## 质量检查与计数

暂存库和 PostgreSQL/Vastbase 目标库共用以下 SQL 检查。任一异常计数非零时终止构建或回滚导入；报告的 `quality` 保存实际计数。

| 报告字段 | 异常内容 | 通过条件 |
| --- | --- | --- |
| `invalid_endpoint_types` | 悬空关系或关系两端类型不匹配 | 0 |
| `missing_entity_evidence` | 实体没有可追溯证据 | 0 |
| `missing_edge_evidence` | 关系没有可追溯证据 | 0 |
| `entity_source_dataset_mismatch` | 实体与原始记录所属数据集不同 | 0 |

各表总数、实体类型、关系类型和来源分类计数保存在 `counts`。十万条验收只累计当前批次的实体与去重业务关系。目标库逐表比较行数和完整内容摘要；本草典迁移先逐表核对原型基线，再与 TCM-MKG 合并。

本草典的 35 条未关联书目和 1 处角色冲突继续保留原值与标记。它们不生成悬空边，也不通过猜测补齐。D6 定点修复和 D3 去重保留全部来源证据。

## 本地复现

在仓库根目录执行：

```sh
python3 scripts/prepare_data.py
python3 tests/test_data_pipeline.py
python3 scripts/audit_core_data.py --check
python3 tests/test_import_core.py
```

两源清洗仅需 Python 3.10 以上及标准库。成功输出 `release` 路径，目录中包含 `kg.sqlite`、`manifest.json` 和 `report.json`。原始文件不修改；失败不会发布半成品。重复构建校验完整内容后复用快照，篡改已有快照会失败。

批次 ID 包含本草典构建 ID、全部 TCM-MKG 输入与元数据哈希、v2 DDL、转换脚本和规则版本。SQLite 是离线标准化暂存格式；导入 Vastbase 后仍需逐表内容核对。

## 连接真实 Vastbase

当前要求 UTF-8 和 PG 兼容模式。G100 的认证协议与发行版本可能要求厂商匹配的客户端库，尚不能承诺 PyPI 驱动适用于任意 G100。仓库固定 `psycopg2-binary==2.9.13` 作为候选，需以实际探测结果确认；认证失败时记录错误类型并取得匹配驱动，不自动降低认证要求。

安装候选驱动并创建私有连接配置：

```sh
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements-vastbase.txt
cp config/vastbase.example.json config/vastbase.json
chmod 600 config/vastbase.json
```

编辑 `config/vastbase.json` 的主机、端口、数据库、账号、密码及 TLS 选项。该路径已被 Git 忽略。也支持预先配置的 `VASTBASE_DSN`；不要把带密码的连接串放进命令参数、报告或版本库。远程连接按实际证书设置 `sslmode=verify-full` 和 `sslrootcert`。

环境验证与入库命令：

```sh
.venv/bin/python scripts/import_vastbase.py
.venv/bin/python scripts/import_vastbase.py --release var/prepared/实际构建ID
```

导入账号需要目标数据库的 `CREATE` 权限，能够创建本项目的 schema、表和索引并读写它们。工具不创建数据库或修改其他 schema，不调整账号与服务认证。可通过 `--config` 和 `--report` 指定其他路径。

环境探测首先读取真实服务器版本，核对显式选择的引擎。默认 `--engine vastbase` 只接受标识中含 `Vastbase` 的服务器；`--engine postgresql` 则核对 PostgreSQL 身份。随后读取兼容模式与字符编码，在随机 schema 中执行目标建表、中文读写、参数绑定、文本 JSON、COPY 批量写入、外键与唯一约束、保存点回滚、DDL 回滚、分页和索引执行计划，最后回滚全部探测对象。

正式导入使用 `qihuang_<build_id前24位>` schema，在一个事务中建表、装载、核对全部数据表行数与内容摘要、端点类型、证据覆盖、来源计数及四君子汤组成样例，通过后才提交。失败整批回滚；重复运行验证并复用同一批次；旧批次不覆盖、不删除。工具输出 schema 名，供后续应用配置使用，不自动切换在线服务。

报告默认位于 `var/vastbase-report.json`。没有连接配置时退出码为 1，状态为 `blocked`，`vastbase` 与 `import_result` 均为 `null`。只有真实环境验证成功且报告的 `import_result.status` 为 `imported` 或 `reused`，才表示本批数据已经完成 Vastbase 入库。

## 最终迁移步骤

1. 应用开发使用 PostgreSQL 和当前标准化批次，保留相同实体 ID、表结构、关系类型和来源证据。数据修订通过清洗流程重新生成批次。
2. 在最终部署前取得实际 Vastbase 实例和匹配驱动，配置 `config/vastbase.json`，运行默认的 Vastbase 环境探测，处理实际兼容性差异。
3. 对同一个准备好的批次执行 `scripts/import_vastbase.py --engine vastbase --release 批次目录`，完成独立事务导入，不直接恢复 PostgreSQL 专用物理备份。
4. 对比两库的构建 ID、各表行数和内容 SHA-256，核对组成、冲突与出处样例。通过后将应用连接配置及 schema 切换到 Vastbase；图投影保持同批次。
5. 在实际 Vastbase 上重新运行接口、查询性能、事务和故障恢复验收。PostgreSQL 保留到切换验证通过，作为开发和回退环境。

## 验证边界

本地回归覆盖真实两源数据、重复构建、精确坏行修复、多行字段、属性冲突、缺失端点、证据定位、内容篡改拒绝及原始文件哈希不变。SQL 集成测试通过 `QIHUANG_TEST_DSN` 显式连接一次性测试库，覆盖整批导入、幂等复用和验证失败回滚。PostgreSQL 可作为当前开发库验收，最终仍须实际 Vastbase 验收。测试确认 PostgreSQL 模式能够使用该服务器、Vastbase 模式仍会拒绝该服务器。

完成真实入库需要以下二选一：已有 Vastbase 的连接配置；或本机可加载的厂商镜像/安装包及其适用的许可条件。[官方镜像安装文档](https://docs.vastdata.com.cn/zh_CN/VastbaseG100/V3.0.9/1/80b950d86e23435b93cf8bc3fe77e923)说明镜像需联系工程师获取；[官方交互安装文档](https://docs.vastdata.com.cn/zh_CN/VastbaseG100/V3.0.8/1/092436a0aebd419b82ed163f9d3148d4)说明适用版本可在安装时生成 90 天试用许可，具体以所获版本为准。本次未使用非官方镜像。

Neo4j 样例与 Vue + FastAPI 最小链路现已完成，见[阶段运行说明](bootstrap.md)。模型按用户安排留空；全量图谱、完整业务接口、AI 功能及最终 Vastbase 验收仍属后续任务，清洗或 SQL 检查不能代替它们。

2026-10-10 应用切换至 `5a76218e` 批次，Neo4j 样例同步重建。旧 schema 保留，配置备份位于 `var/app.json.previous.bak`；恢复备份并重启后端即可回滚。

2026-10-16 当前批次改为 `cbadd11e`，唯一的数据差异是十枣汤组成中大蓟改为大戟（见[数据处理说明](data-processing.md#组成键值更正)）。实体、边和来源记录数量不变，引文证据增加 3 条。
