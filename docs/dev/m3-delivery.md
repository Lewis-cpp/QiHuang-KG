# M3 交付说明：Neo4j 全量投影与图谱

日期：2026-10-19。上位文档：[spec.md](../../spec.md) §6。批次：`cbadd11ea5c86dc3d7654c4652b06e23a77245af728fee2f1c46c9382ced867e`。验收数据见 [m3-graph.json](../acceptance/m3-graph.json)。

## 1. 内容

| 部分 | 内容 |
| --- | --- |
| `scripts/project_graph.py` | 把当前批次写入 Neo4j：先节点后边，每批 5,000 条，`MERGE` 保证重跑不重复；节点带类型标签；`Projection.complete` 在数量与 ID 摘要校验通过后才置为 `true`；`--prune <build_id>` 清理其他批次，拒绝清理当前配置的批次 |
| `GET /api/v1/graph` | 以实体为中心的一跳邻居，出入边都含；最多 50 个节点、100 条边，超出时 `truncated=true`；`relation_counts` 来自关系库 |
| `GET /api/v1/graph/paths` | 固定模板 `herb_patterns_via_formula` 的两跳路径，结构与 `/relation-queries` 相同 |
| `/graph/:id` | Cytoscape.js 3.34.4 画布、一跳展开、边的证据、100 节点 / 200 边上限、图例、与画布内容相同的关系表 |
| 实体详情页 | 有关系的实体增加"查看关系图谱"链接 |

## 2. 实现约定

- **图库只存展示属性**：`CONTAINS` 的边带 `role`、`position`、`dosage_raw`，这三个键即使为空也保留，空值表示来源冲突。`corrections`、`position_source` 等完整属性仍从关系库读取。
- **全量投影会覆盖节点的 `scope`**：同一批次的样例节点被标为 `full`。`sample_graph()` 因此改为按固定的四君子汤读取，不再依赖 `scope`。
- **图接口先问关系库**：批次不符返回 409、实体不存在返回 404，之后才访问 Neo4j。实体在关系库中存在但图库中没有，或投影未完成时，返回 503 `projection_not_ready`。
- **证据顺序**：投影时使用关系库的 `EVIDENCE_ORDER`，两个库返回的证据列表顺序一致。
- **截断规则**：取 101 条候选边，遇到第一条需要第 51 个节点的边就停止，结果始终是有序前缀。
- **前端**：图谱路由按需加载，主包 142 kB，图谱包 447 kB。关系用颜色加线型区分，图例写明线型名称。

## 3. 验证

| 检查 | 结果 |
| --- | --- |
| 投影：节点 / 边 / ID 摘要与主库一致 | 20,374 / 179,502 / 一致 |
| 投影耗时 | 首次 15.6 s，重跑 8.7 s |
| Neo4j 容器内存 | 约 1.36 GiB（堆上限 512 MiB，页缓存 256 MiB） |
| `/graph/paths` 与 `/relation-queries`，本草典全部药物逐个对比 | 一致 |
| 停止 Neo4j | `/graph`、`/graph/paths` 返回 503；实体详情、检索、统计 200 |
| 重启 Neo4j | 投影仍在，`complete=true`，摘要与主库一致 |
| `dump` / `load` | 备份 130 MB，导出约 15 s（含停机），恢复 4 s；恢复实例的 5 条投影标记与原实例完全一致，摘要与主库一致 |
| 浏览器核对 | 点击、展开、边证据、截断提示、100 节点上限、Neo4j 不可用，均符合预期 |
| `tests/test_project_graph.py` | 通过：重跑幂等、校验能识别缺边、多余节点和被改的 ID，`--prune` 拒绝当前批次 |

截图：[m3-graph.png](../screenshots/m3-graph.png)、[m3-graph-unavailable.png](../screenshots/m3-graph-unavailable.png)。

## 4. 备份与恢复步骤

导出需要停止 Neo4j，Community 版没有在线备份：

```sh
docker compose stop neo4j
docker run --rm -v qihuang-kg_neo4j_data:/data -v "$PWD/backup":/backups <compose 中的 neo4j 镜像> \
  neo4j-admin database dump neo4j --to-path=/backups
docker compose start neo4j
```

恢复到新数据卷并核对，不覆盖原数据：

```sh
docker volume create restore-test
docker run --rm -v restore-test:/data -v "$PWD/backup":/backups <镜像> \
  neo4j-admin database load neo4j --from-path=/backups --overwrite-destination=true
docker run -d --name restore-test -p 127.0.0.1:27687:7687 -v restore-test:/data \
  --env-file config/neo4j.env <镜像>
```

用 `project_graph.verify` 对恢复实例做数量和摘要核对。正式恢复到 `qihuang-kg_neo4j_data` 时才对原数据卷执行 `load`，并先停止 `neo4j` 服务。

## 5. 已知限制

- Neo4j 里还有旧批次（`5a76218e…`、`1fe2300d…`）的投影，没有清理。需要时执行 `project_graph.py --prune <build_id>`。
- 内存只采到 4 个样本，`docker stats` 每次约 2 s，数字是量级参考。
- 图谱页面的浏览器核对脚本没有提交（spec §8.1 不引入前端测试框架）。
- 两跳模板目前只有 `herb_patterns_via_formula` 一个，页面上没有入口。
