# 论文用图（Mermaid 源码，m7-spec §4）

图源可直接在支持 Mermaid 的编辑器渲染导出。所有数字取自验收记录文件（括号内为字段路径），**引用时以文件当前内容为准**，不在此手抄后修改；下方"记录值"为 2026-11-02 撰写时的快照，仅供对照。

## 1. 系统架构图

```mermaid
flowchart LR
    subgraph client["浏览器（Vue 3 + vue-router）"]
        SPA["检索 / 详情 / 证据 / 图谱 / AI 页面"]
    end
    subgraph backend["FastAPI（uvicorn，单进程）"]
        API["/api/v1 只读接口"]
        AIQ["/ai/query：条件白名单→参数化 SQL"]
        AIE["/ai/explain：材料组装→校验→降级"]
        HOST["frontend/dist 静态托管 + SPA 回退"]
    end
    subgraph data["数据层"]
        PG[("PostgreSQL / Vastbase\n实体 20,374 · 关系 179,502 · 证据 291,308")]
        NEO[("Neo4j 5.26\n全量投影 :Entity/:LINK")]
        MODEL["deepseek-flash\nJSON 模式，信号量并发 2"]
    end
    SPA -->|"fetch + build_id 一致性"| HOST
    HOST --> API
    SPA --> AIQ
    SPA --> AIE
    API --> PG
    AIQ --> PG
    AIQ <--> MODEL
    AIE --> PG
    AIE <--> MODEL
    API --> NEO
    AIE -->|"证据 ID 回查"| PG
```

## 2. ER 图（关系库 7 张表）

```mermaid
erDiagram
    dataset ||--o{ source_record : "dataset_id"
    source_record ||--o{ entity : "source_record_id"
    source_record ||--o{ alias : "source_record_id"
    source_record ||--o{ edge : "—"
    source_record ||--o{ evidence : "source_record_id"
    entity ||--o{ alias : "entity_id"
    entity ||--o{ edge : "source_id / target_id"
    entity ||--o{ evidence : "entity_id（实体级）"
    edge ||--o{ evidence : "edge_id（关系级）"
    build {
        varchar_64 id PK
        int schema_version
        text transform_version
        text created_at
        text manifest_json
    }
    dataset {
        varchar_80 id PK
        text title
        text version_label
        text source_url
        text license_statement
        text attribution
    }
    source_record {
        varchar_160 id PK
        varchar_80 dataset_id FK
        varchar_160 filename
        varchar_64 file_sha256
        varchar_160 record_key
        text record_locator
        text content_json
    }
    entity {
        varchar_200 id PK
        varchar_80 dataset_id FK
        varchar_40 type
        text label
        text category
        text name_norm
        text attributes_json
        varchar_40 review_status
    }
    alias {
        varchar_200 entity_id FK
        text name
        varchar_500 name_norm
        varchar_200 field_path
    }
    edge {
        varchar_160 id PK
        varchar_200 source_id FK
        varchar_40 relation
        varchar_200 target_id FK
        text properties_json
        varchar_40 quality_state
    }
    evidence {
        varchar_160 id PK
        varchar_200 entity_id FK
        varchar_160 edge_id FK
        varchar_160 source_record_id FK
        text field_path
        varchar_40 kind
        text excerpt
    }
```

## 3. Neo4j 图模型

```mermaid
flowchart LR
    subgraph node["(:Entity) 节点，另带类型标签 :Herb/:Formula/…"]
        id1["id"]
        b1["build_id"]
        l1["label / type / scope"]
    end
    subgraph rel["[:LINK] 关系"]
        id2["id"]
        b2["build_id"]
        r2["relation / quality_state"]
        e2["evidence_ids"]
        p2["CONTAINS 另带 role/position/dosage_raw"]
    end
    subgraph marker["(:Projection) 投影标记"]
        m1["build_id / scope / complete\nnode_count / edge_count / id_digest"]
    end
    node --- rel
    marker -.校验依据.-> node
```

## 4. AI 链路一：自然语言条件查询（/ai/query）

```mermaid
sequenceDiagram
    participant U as 用户
    participant A as FastAPI /ai/query
    participant M as deepseek-flash
    participant DB as PostgreSQL（只读事务）
    U->>A: POST {question ≤200字, build_id?}
    A->>DB: 开只读事务：读取分类清单
    A->>M: query_v1（问题包裹在 <question> 标记内）
    M-->>A: {target_type, conditions[], unsupported[]}
    A->>A: 白名单校验 + 实体名/别名解析
    alt 0 个候选 / 多个候选
        A-->>U: unresolved（附建议）/ ambiguous（候选单选，重提不调模型）
    else 可执行
        A->>DB: 参数化 SQL（EXISTS/NOT EXISTS + 列条件）
        A-->>U: status=ok：执行的条件 + results(≤50) + 覆盖说明
    end
```

## 5. AI 链路二：带引用的方剂解释（/ai/explain）

```mermaid
sequenceDiagram
    participant U as 用户（点击后触发）
    participant A as FastAPI /ai/explain
    participant DB as PostgreSQL（一次只读事务取全部材料）
    participant M as deepseek-flash
    U->>A: POST {entity_id, build_id?}
    A->>DB: gather()：属性/组成/证候/出处 → M1…Mn（映射证据 ID）
    A->>M: explain_v1 + <materials>（第 1 次，含失败原因则为第 2 次）
    M-->>A: {sections[{heading,sentences[{text,citations[M*]}]}], insufficient[]}
    A->>A: validate()：结构/引用/药名/角色/冲突/剂量，全部失败一起收集
    alt 校验通过
        A-->>U: status=ok：句子 + refs + 真实证据 ID citations（引用可回查 503/503）
    else 两次均失败
        A-->>U: status=explanation_unavailable + failure 原因 + 完整 materials（页面照常展示）
    end
```

## 6. 评测结果表（数字引用报告文件）

| 指标 | 值的来源（文件 → 字段） | 记录值（2026-11-02 快照） | 门槛 | 达标 |
| --- | --- | --- | --- | --- |
| 查询通过率（test） | `docs/acceptance/m5-eval-test.json` → `metrics.query.passed/total/rate` | 25/25 = 1.0 | ≥ 0.90 | ✅ |
| 解释完成率（test） | 同上 → `metrics.explain.ok/total/rate` | 19/20 = 0.95 | ≥ 0.90 | ✅ |
| 引用可回查率 | 同上 → `metrics.explain.citations_resolved/citations_total` | 503/503 = 1.0 | 1.0 | ✅ |
| 对抗样本（全部/关键） | 同上 → `metrics.adversarial` | 15/15；关键 13/13 | 全部 | ✅ |
| 事实支持率 | 同上 → `metrics.fact_support`（`--score-review` 生成） | 待人工审核（审核表 301 句） | ≥ 0.95 | 待人工 |
| 解释唯一降级样本 | 同上 → `samples[T-E15]`，原因见 `docs/dev/issues.md` I-002 | 模型编造剂量被校验拦截 | — | 设计行为 |

## 7. 性能表（数字引用报告文件）

| 接口组 | 值的来源 | 记录值（2026-11-02 快照） | 目标 | 达标 |
| --- | --- | --- | --- | --- |
| 12 个非 AI 接口 × 并发 1/5 | `docs/acceptance/m6-bench.json` → `endpoints[]` 的 `p95_ms` | 全部 ≤ 185 ms | ≤ 2000 ms | ✅ |
| `/ai/query` | 同上 → `ai[name=ai_query].p95_ms` | 约 1.4–1.6 s | ≤ 15 s | ✅ |
| `/ai/explain` | 同上 → `ai[name=ai_explain].p95_ms` | 约 18–20 s | ≤ 15 s | ❌ 已接受（I-004：模型生成时延） |
| 并发挤占信号量 | 同上 → `ai_busy_probe` | 5 并发 → 2 成功 + 3 `model_busy` | 设计行为 | ✅ |
| Vastbase 验收 | `docs/acceptance/m6-vastbase.json` → `status` | blocked（无实例，I-003） | passed | 阻塞外部 |

## 8. 恢复与部署验证（数字引用报告文件）

| 演练 | 证据文件 | 结论 |
| --- | --- | --- |
| 关系库恢复 → 只读账号 → 接口复验 → 清理 | `docs/acceptance/m7-recovery.json` → `steps[relational_restore|reader_setup|api_recheck|cleanup]` | 6/6 通过；table_sha256 与主库一致；写入全被 42501 拒绝 |
| Neo4j dump/load + 投影复用 | 同上 → `steps[graph_restore]`；`m3-backup-restore.json` | 20,374/179,502 节点边，摘要一致，`reused` |
| 构建产物由 FastAPI 托管 | 同上 → `steps[deploy_check]`；`tests/test_deploy.py` | 三个深链接刷新正常，无仓库文件泄露 |
