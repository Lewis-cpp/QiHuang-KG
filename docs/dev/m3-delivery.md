# M3 交付说明：Neo4j 全量投影与图谱

日期：2026-10-12；2026-10-14 调整单跳截断顺序。上位文档：[spec.md](../../spec.md) §6。批次：`5a76218e52001d45e4bd75e099a38780408e873342a14e5db0c86d7bb7a3008a`。

实现时确定的 12 项做法写在 spec §6.5，需要改动时修订那一节。

## 1. 交付内容

| 部分 | 文件 | 内容 |
| --- | --- | --- |
| 投影构建 | `scripts/project_graph.py` | 从当前批次读取全部实体和关系，每批 5,000 条 `MERGE` 写入；节点加类型标签（`:Formula`、`:Herb` 等）；核对数量和 ID 摘要后写 `Projection.complete=true`；支持复用、`--rebuild`、`--prune` |
| 图接口 | `backend/graph.py`、`backend/app.py` | `GET /api/v1/graph`（一跳，出入边，50 节点 / 100 边；超过上限时关系少的类型在前，同类按君臣佐使和被用到的次数排；节点带 `usage`；关系总数来自关系库）；`GET /api/v1/graph/paths`（`herb_patterns_via_formula`，只查 Neo4j，返回结构与 `/relation-queries` 相同） |
| 页面 | `frontend/src/views/GraphView.vue` 等 | `/graph/:id`：Cytoscape.js 画布、点击展开并按 ID 合并、画布上限 100 / 200、关系筛选、侧栏证据和被用到的次数、图例和截断顺序说明、可键盘操作的关系列表、中药的两跳路径分区 |
| 入口 | `EntityView.vue` | 详情页页头"在关系图谱中查看" |
| 修正 | `scripts/verify_environment.py` | 样例写入和一跳、两跳核对改为按 `scope='bootstrap'`，否则全量投影后再跑环境验证会把同 ID 的全量边改成样例边，并因计数翻倍而失败（本次实测发现） |

依赖只新增 `cytoscape` 3.34.3（精确版本，自带类型声明，无下游依赖）。锁文件用 npm 11 生成。图谱页面单独打包（约 145 KB gzip），其余页面不加载。

## 2. 验证环境

云端容器中重建本地 PostgreSQL 16.15，用 `prepare_data.py` 和 `import_vastbase.py --engine postgresql` 导入同一批次，再用 `setup_reader.py` 创建只读账号。

Neo4j 无法从 Docker Hub 拉取（匿名拉取限额），所以用 Maven Central 上的同版本构件 `org.neo4j:neo4j:5.26.31`（与 Compose 镜像摘要对应的 5.26.31 相同）以嵌入方式启动，开启 Bolt `127.0.0.1:17687`，堆上限 512 MB、页缓存 256 MB，与 Compose 一致。备份恢复用同版本构件中的 `neo4j-admin`（`org.neo4j.cli.AdminTool`）。没有配置模型。

以上结果来自这套环境，不是 Compose 中的 PostgreSQL 18.6 和 Neo4j 容器。在开发机上按[运行说明](../bootstrap.md#m3-neo4j-全量投影与图谱)执行 `project_graph.py` 和测试即可复核。

## 3. 结果

| 检查 | 结果 |
| --- | --- |
| 投影（空库） | 节点 20,374、边 179,502，与主库一致；ID 摘要 `01acc9d5…`；读取 1.7 秒、写入 23.5 秒、合计 29.8 秒；完成后堆使用 174 MB / 上限 512 MB。见 [m3-projection.json](../acceptance/m3-projection.json) |
| 重跑 | 已完成的投影复用并重新核对；`--rebuild` 重写后结果不变 |
| `tests/test_api.py` | 通过。新增：一跳上限、关系筛选、404 / 422 / 409、投影未就绪 503、Neo4j 不可用 503 且详情和关系查询不受影响；一跳的边顺序、`truncated` 和每个节点的 `usage` 与关系库按 §6.2 重算的结果逐条一致，覆盖 157 个中心（每种类型关系最多的 3 个，加按 ID 哈希抽取的 15 个） |
| 两库一致性（§6.3） | 有两跳路径的 94 味中药、568 条路径逐页比较：路径顺序、节点、边端点、质量状态、证据 ID 全部一致 |
| `tests/test_app.py` 及其余 Python 测试 | 通过；`projection` 断言改为 `full` |
| `npm run build`（含 `vue-tsc`） | 通过 |
| `npm test` | 13/13；新增画布合并、上限、截断文字、列表顺序、次数说明、样式互不相同和数组参数 |
| 浏览器核对（Vite 开发服务） | 35/35 |
| 浏览器核对（`vite preview`） | 35/35 |
| 停止 Neo4j | 图谱显示"图数据库暂时不可用"和"重试"，详情和检索正常；重启后点"重试"恢复，投影仍在（5/5） |
| 备份恢复演练 | `dump` 后在空数据目录 `load`，`Projection` 的数量、摘要、投影时间与导出前一致，并与主库重新核对通过。见 [m3-backup-restore.json](../acceptance/m3-backup-restore.json) |

逐项结果见 [m3-browser.json](../acceptance/m3-browser.json)，固定用例见 [tests/cases.md](../../tests/cases.md) 的 M3 部分。浏览器核对用无头 Chromium 驱动，脚本没有提交（spec §8.1 不引入前端测试框架）。

几个值得注意的实测结果：

- **截断**：药性"苦"有 3,439 条入边，画布显示 49 个邻居，依次是用到最多的饮片：芍药（1,368 种中成药）、陈皮（902）、黄芩（882）……。按名称排时显示的是一口红、一品红、一年蓬，"苦"的 3,439 种饮片中有 2,722 种没有中成药用到。
- **小类型不被挤掉**：饮片甘草有 6 条药性和 2,278 种中成药，不筛选时先显示 6 条药性，再显示用到它的 43 种中成药。
- **君臣佐使**：四君子汤依次为人参（君）、白术（臣）、茯苓（佐）、甘草（使）；中药甘草收录于 61 首方剂，先显示以它为君的炙甘草汤、为臣的四逆汤，其余 59 首中它都是使药，按名称排。
- **冲突边**：猪苓汤 → 泽泻在图上加粗标 ⚠，侧栏不写角色，列出 2 条证据。
- **两跳**：人参 23 条路径，首条"人参 ← 乌梅丸 → 厥阴病证"，与 M1 关系库模板的结果一致。

### 3.1 在 Compose 开发环境中的复核（2026-10-19）

在开发机的真实 Compose 服务（Neo4j 5.26.31 镜像、PostgreSQL 18）上复核，结果见 [m3-compose-drills.json](../acceptance/m3-compose-drills.json)：

| 检查 | 结果 |
| --- | --- |
| `project_graph.py --rebuild` | 11.8 s；堆已用约 74 MiB（上限 512 MiB）；容器内存约 1.36 GiB |
| 停止 Neo4j | `/graph`、`/graph/paths` 返回 503；详情、检索、统计 200 |
| 重新启动 | 投影仍为 `complete`，数量与摘要和主库一致 |
| `docs/bootstrap.md` 中的 `dump` / `load` 命令 | 备份 130 MB；停机导出约 14 s，恢复约 4 s；`load` 在独立的 Compose 项目中执行，没有覆盖开发数据卷；恢复实例与原实例的 5 条 `Projection` 标记一致，三项核对为 `true` |
| `tests/test_project_graph.py` | 通过：重复写入不增加数据，写入本身不产生完成标记，`verify` 能识别缺边、多余节点和被改的 ID，`--prune` 拒绝当前批次 |

备份目录必须允许容器内的 `neo4j` 用户（UID 7474）写入。若 `var/neo4j-dumps` 已存在且属于该用户，宿主用户无法读写，导出会失败，随后的 `load` 会静默恢复目录中更早的备份。恢复前请核对备份文件的大小和文件数。

## 4. 截图

| 页面 | 文件 |
| --- | --- |
| 四君子汤一跳 | [m3-graph.png](../screenshots/m3-graph.png) |
| 展开甘草后 | [m3-expanded.png](../screenshots/m3-expanded.png) |
| 画布上限提示 | [m3-limit.png](../screenshots/m3-limit.png) |
| 人参与两跳路径 | [m3-paths.png](../screenshots/m3-paths.png) |
| Neo4j 停止 | [m3-neo4j-down.png](../screenshots/m3-neo4j-down.png) |
| 窄屏 | [m3-narrow.png](../screenshots/m3-narrow.png) |

## 5. 未包含

AI 功能属于 M4。图上只存展示所需的边属性，其他属性和证据正文仍从关系库读取。
