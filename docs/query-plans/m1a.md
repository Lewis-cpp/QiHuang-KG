# M1a 查询执行计划

日期：2026-10-10。批次：`5a76218e52001d45e4bd75e099a38780408e873342a14e5db0c86d7bb7a3008a`。

PostgreSQL 18.6，保持默认规划器设置，未禁用顺序扫描。四张大表不允许 Seq Scan；小表 build/dataset 的顺序扫描正常。

S1 为四君子汤，S5 为 Bitter medicinal。证据详情分别取组成证据与 S5 实体证据。

S5 不适用组成模板，因此模板 SQL 对 S5 的空结果仅用于计划诊断，API 仍返回 422。另附甘草反查的实际计划。

## S1 查询 1

```sql
SELECT id FROM build
```

```text
Seq Scan on build  (cost=0.00..12.90 rows=290 width=146) (actual time=0.003..0.003 rows=1.00 loops=1)
  Buffers: shared hit=1
Planning Time: 0.010 ms
Execution Time: 0.009 ms
```

## S1 查询 2

```sql
SELECT * FROM entity WHERE id='bencaodian:formula:si_jun_zi_tang'
```

```text
Index Scan using entity_pkey on entity  (cost=0.41..8.43 rows=1 width=424) (actual time=0.017..0.017 rows=1.00 loops=1)
  Index Cond: ((id)::text = 'bencaodian:formula:si_jun_zi_tang'::text)
  Index Searches: 1
  Buffers: shared hit=4
Planning:
  Buffers: shared hit=161
Planning Time: 0.305 ms
Execution Time: 0.037 ms
```

## S1 查询 3

```sql
SELECT id,title FROM dataset WHERE id='bencaodian'
```

```text
Index Scan using dataset_pkey on dataset  (cost=0.14..8.16 rows=1 width=210) (actual time=0.013..0.014 rows=1.00 loops=1)
  Index Cond: ((id)::text = 'bencaodian'::text)
  Index Searches: 1
  Buffers: shared hit=2
Planning:
  Buffers: shared hit=37
Planning Time: 0.099 ms
Execution Time: 0.030 ms
```

## S1 查询 4

```sql
SELECT name,source_record_id,field_path FROM alias WHERE entity_id='bencaodian:formula:si_jun_zi_tang' ORDER BY name_norm,name
```

```text
Incremental Sort  (cost=8.31..8.35 rows=2 width=105) (actual time=0.029..0.030 rows=0.00 loops=1)
  Sort Key: name_norm, name
  Presorted Key: name_norm
  Full-sort Groups: 1  Sort Method: quicksort  Average Memory: 25kB  Peak Memory: 25kB
  Buffers: shared hit=5
  ->  Index Scan using alias_pkey on alias  (cost=0.28..8.30 rows=1 width=105) (actual time=0.015..0.015 rows=0.00 loops=1)
        Index Cond: ((entity_id)::text = 'bencaodian:formula:si_jun_zi_tang'::text)
        Index Searches: 1
        Buffers: shared hit=2
Planning:
  Buffers: shared hit=106
Planning Time: 0.292 ms
Execution Time: 0.054 ms
```

## S1 查询 5

```sql
SELECT relation,'out' AS direction,count(*) AS count FROM edge WHERE source_id='bencaodian:formula:si_jun_zi_tang' GROUP BY relation UNION ALL SELECT relation,'in' AS direction,count(*) AS count FROM edge WHERE target_id='bencaodian:formula:si_jun_zi_tang' GROUP BY relation ORDER BY relation,direction
```

```text
Sort  (cost=18.40..18.43 rows=13 width=57) (actual time=0.086..0.088 rows=3.00 loops=1)
  Sort Key: edge.relation, ('out'::text)
  Sort Method: quicksort  Memory: 25kB
  Buffers: shared hit=10
  ->  Append  (cost=0.42..18.16 rows=13 width=57) (actual time=0.045..0.066 rows=3.00 loops=1)
        Buffers: shared hit=7
        ->  GroupAggregate  (cost=0.42..8.80 rows=6 width=57) (actual time=0.044..0.047 rows=3.00 loops=1)
              Group Key: edge.relation
              Buffers: shared hit=4
              ->  Index Only Scan using edge_outgoing on edge  (cost=0.42..8.67 rows=14 width=17) (actual time=0.035..0.037 rows=6.00 loops=1)
                    Index Cond: (source_id = 'bencaodian:formula:si_jun_zi_tang'::text)
                    Heap Fetches: 0
                    Index Searches: 1
                    Buffers: shared hit=4
        ->  GroupAggregate  (cost=0.42..9.30 rows=7 width=57) (actual time=0.016..0.017 rows=0.00 loops=1)
              Group Key: edge_1.relation
              Buffers: shared hit=3
              ->  Index Only Scan using edge_incoming on edge edge_1  (cost=0.42..9.05 rows=36 width=17) (actual time=0.016..0.016 rows=0.00 loops=1)
                    Index Cond: (target_id = 'bencaodian:formula:si_jun_zi_tang'::text)
                    Heap Fetches: 0
                    Index Searches: 1
                    Buffers: shared hit=3
Planning:
  Buffers: shared hit=135
Planning Time: 0.467 ms
Execution Time: 0.136 ms
```

## S1 查询 6

```sql
SELECT count(*) AS total FROM evidence WHERE entity_id='bencaodian:formula:si_jun_zi_tang'
```

```text
Aggregate  (cost=8.87..8.88 rows=1 width=8) (actual time=0.034..0.034 rows=1.00 loops=1)
  Buffers: shared hit=5
  ->  Index Only Scan using evidence_entity on evidence  (cost=0.55..8.83 rows=16 width=0) (actual time=0.028..0.029 rows=1.00 loops=1)
        Index Cond: (entity_id = 'bencaodian:formula:si_jun_zi_tang'::text)
        Heap Fetches: 0
        Index Searches: 1
        Buffers: shared hit=5
Planning:
  Buffers: shared hit=98
Planning Time: 0.255 ms
Execution Time: 0.061 ms
```

## S1 查询 7

```sql
SELECT id,kind,field_path,excerpt,source_record_id FROM evidence WHERE entity_id='bencaodian:formula:si_jun_zi_tang' ORDER BY CASE kind WHEN 'source_quote' THEN 0 WHEN 'curated' THEN 1
    WHEN 'bibliographic' THEN 2 WHEN 'auto_extracted' THEN 3 WHEN 'rule_inferred' THEN 4 END,
    CASE WHEN field_path='' THEN 1 ELSE 0 END, field_path, id LIMIT 20 OFFSET 0
```

```text
Limit  (cost=67.74..67.78 rows=16 width=299) (actual time=0.047..0.048 rows=1.00 loops=1)
  Buffers: shared hit=11
  ->  Sort  (cost=67.74..67.78 rows=16 width=299) (actual time=0.046..0.046 rows=1.00 loops=1)
        Sort Key: (CASE kind WHEN 'source_quote'::text THEN 0 WHEN 'curated'::text THEN 1 WHEN 'bibliographic'::text THEN 2 WHEN 'auto_extracted'::text THEN 3 WHEN 'rule_inferred'::text THEN 4 ELSE NULL::integer END), (CASE WHEN (field_path = ''::text) THEN 1 ELSE 0 END), field_path, id
        Sort Method: quicksort  Memory: 25kB
        Buffers: shared hit=11
        ->  Index Scan using evidence_entity on evidence  (cost=0.55..67.42 rows=16 width=299) (actual time=0.024..0.024 rows=1.00 loops=1)
              Index Cond: ((entity_id)::text = 'bencaodian:formula:si_jun_zi_tang'::text)
              Index Searches: 1
              Buffers: shared hit=5
Planning:
  Buffers: shared hit=129
Planning Time: 0.354 ms
Execution Time: 0.074 ms
```

## S1 查询 8

```sql
SELECT * FROM evidence WHERE id='evidence:72340d34a2f1acaf0dee984198dcb9ea60beda6d11d8168122cecd6c1f19e33c'
```

```text
Index Scan using evidence_pkey on evidence  (cost=0.42..8.44 rows=1 width=401) (actual time=0.030..0.031 rows=1.00 loops=1)
  Index Cond: ((id)::text = 'evidence:72340d34a2f1acaf0dee984198dcb9ea60beda6d11d8168122cecd6c1f19e33c'::text)
  Index Searches: 1
  Buffers: shared hit=4
Planning:
  Buffers: shared hit=119
Planning Time: 0.273 ms
Execution Time: 0.045 ms
```

## S1 查询 9

```sql
SELECT * FROM source_record WHERE id='source:7b97ace64c20ac073aa2d3c9b66d21366722aea1dd65c1a4fdf61e13567f4fa4'
```

```text
Index Scan using source_record_pkey on source_record  (cost=0.42..8.44 rows=1 width=466) (actual time=0.031..0.032 rows=1.00 loops=1)
  Index Cond: ((id)::text = 'source:7b97ace64c20ac073aa2d3c9b66d21366722aea1dd65c1a4fdf61e13567f4fa4'::text)
  Index Searches: 1
  Buffers: shared hit=4
Planning:
  Buffers: shared hit=100
Planning Time: 0.230 ms
Execution Time: 0.045 ms
```

## S1 查询 10

```sql
SELECT * FROM dataset WHERE id='bencaodian'
```

```text
Index Scan using dataset_pkey on dataset  (cost=0.14..8.16 rows=1 width=338) (actual time=0.008..0.009 rows=1.00 loops=1)
  Index Cond: ((id)::text = 'bencaodian'::text)
  Index Searches: 1
  Buffers: shared hit=2
Planning:
  Buffers: shared hit=37
Planning Time: 0.108 ms
Execution Time: 0.023 ms
```

## S1 查询 11

```sql
SELECT id,relation,source_id,target_id FROM edge WHERE id='edge:17d8c5fd2a3e045b422c5d9c56edbefccf1d4e78a76320867e4d7d88e2740a3e'
```

```text
Index Scan using edge_pkey on edge  (cost=0.42..8.44 rows=1 width=155) (actual time=0.031..0.032 rows=1.00 loops=1)
  Index Cond: ((id)::text = 'edge:17d8c5fd2a3e045b422c5d9c56edbefccf1d4e78a76320867e4d7d88e2740a3e'::text)
  Index Searches: 1
  Buffers: shared hit=4
Planning:
  Buffers: shared hit=128
Planning Time: 0.300 ms
Execution Time: 0.047 ms
```

## S1 查询 12

```sql
SELECT id,label,type FROM entity WHERE id=ANY(ARRAY['bencaodian:formula:si_jun_zi_tang','bencaodian:herb:ren_shen'])
```

```text
Index Scan using entity_pkey on entity  (cost=0.41..15.91 rows=2 width=55) (actual time=0.026..0.038 rows=2.00 loops=1)
  Index Cond: ((id)::text = ANY ('{bencaodian:formula:si_jun_zi_tang,bencaodian:herb:ren_shen}'::text[]))
  Index Searches: 2
  Buffers: shared hit=8
Planning:
  Buffers: shared hit=173
Planning Time: 0.401 ms
Execution Time: 0.051 ms
```

## S1 查询 13

```sql
SELECT e.*,n.id AS node_id,n.label,n.type FROM edge e JOIN entity n ON n.id=e.target_id WHERE e.source_id='bencaodian:formula:si_jun_zi_tang' AND e.relation='CONTAINS'
```

```text
Nested Loop  (cost=0.83..16.87 rows=1 width=253) (actual time=0.021..0.037 rows=4.00 loops=1)
  Buffers: shared hit=20
  ->  Index Scan using edge_outgoing on edge e  (cost=0.42..8.44 rows=1 width=198) (actual time=0.011..0.012 rows=4.00 loops=1)
        Index Cond: (((source_id)::text = 'bencaodian:formula:si_jun_zi_tang'::text) AND ((relation)::text = 'CONTAINS'::text))
        Index Searches: 1
        Buffers: shared hit=4
  ->  Index Scan using entity_pkey on entity n  (cost=0.41..8.43 rows=1 width=55) (actual time=0.005..0.005 rows=1.00 loops=4)
        Index Cond: ((id)::text = (e.target_id)::text)
        Index Searches: 4
        Buffers: shared hit=16
Planning:
  Buffers: shared hit=345
Planning Time: 0.623 ms
Execution Time: 0.057 ms
```

## S1 查询 14

```sql
SELECT id,edge_id FROM evidence WHERE edge_id=ANY(ARRAY['edge:17d8c5fd2a3e045b422c5d9c56edbefccf1d4e78a76320867e4d7d88e2740a3e','edge:e5c70d965a54fe4888889faf5f97a7b7028d20882dfa5675ce16a5bdaba6c7f2','edge:76dd65166e484077fb9dbc981bfc079e36c01de7808fba39065f6fa9c1709f04','edge:996ed53400325645c2fc6291d11612917e9ece156af4b3ac2a4f7cf77164c479']) ORDER BY CASE kind WHEN 'source_quote' THEN 0 WHEN 'curated' THEN 1
    WHEN 'bibliographic' THEN 2 WHEN 'auto_extracted' THEN 3 WHEN 'rule_inferred' THEN 4 END,
    CASE WHEN field_path='' THEN 1 ELSE 0 END, field_path, id
```

```text
Sort  (cost=34.36..34.37 rows=4 width=160) (actual time=0.100..0.101 rows=8.00 loops=1)
  Sort Key: (CASE kind WHEN 'source_quote'::text THEN 0 WHEN 'curated'::text THEN 1 WHEN 'bibliographic'::text THEN 2 WHEN 'auto_extracted'::text THEN 3 WHEN 'rule_inferred'::text THEN 4 ELSE NULL::integer END), (CASE WHEN (field_path = ''::text) THEN 1 ELSE 0 END), field_path, id
  Sort Method: quicksort  Memory: 26kB
  Buffers: shared hit=23
  ->  Index Scan using evidence_edge on evidence  (cost=0.55..34.32 rows=4 width=160) (actual time=0.035..0.069 rows=8.00 loops=1)
        Index Cond: ((edge_id)::text = ANY ('{edge:17d8c5fd2a3e045b422c5d9c56edbefccf1d4e78a76320867e4d7d88e2740a3e,edge:e5c70d965a54fe4888889faf5f97a7b7028d20882dfa5675ce16a5bdaba6c7f2,edge:76dd65166e484077fb9dbc981bfc079e36c01de7808fba39065f6fa9c1709f04,edge:996ed53400325645c2fc6291d11612917e9ece156af4b3ac2a4f7cf77164c479}'::text[]))
        Index Searches: 4
        Buffers: shared hit=17
Planning:
  Buffers: shared hit=119
Planning Time: 0.311 ms
Execution Time: 0.124 ms
```

## S1 查询 15

```sql
SELECT * FROM entity WHERE id='bencaodian:herb:gan_cao'
```

```text
Index Scan using entity_pkey on entity  (cost=0.41..8.43 rows=1 width=424) (actual time=0.024..0.024 rows=1.00 loops=1)
  Index Cond: ((id)::text = 'bencaodian:herb:gan_cao'::text)
  Index Searches: 1
  Buffers: shared hit=4
Planning:
  Buffers: shared hit=161
Planning Time: 0.352 ms
Execution Time: 0.041 ms
```

## S1 查询 16

```sql
SELECT e.*,n.id AS node_id,n.label,n.type FROM edge e JOIN entity n ON n.id=e.source_id WHERE e.target_id='bencaodian:herb:gan_cao' AND e.relation='CONTAINS' ORDER BY n.label,n.id
```

```text
Sort  (cost=16.88..16.89 rows=1 width=253) (actual time=0.636..0.640 rows=61.00 loops=1)
  Sort Key: n.label, e.source_id
  Sort Method: quicksort  Memory: 44kB
  Buffers: shared hit=286
  ->  Nested Loop  (cost=0.83..16.87 rows=1 width=253) (actual time=0.038..0.420 rows=61.00 loops=1)
        Buffers: shared hit=283
        ->  Index Scan using edge_incoming on edge e  (cost=0.42..8.44 rows=1 width=198) (actual time=0.015..0.083 rows=61.00 loops=1)
              Index Cond: (((target_id)::text = 'bencaodian:herb:gan_cao'::text) AND ((relation)::text = 'CONTAINS'::text))
              Index Searches: 1
              Buffers: shared hit=39
        ->  Index Scan using entity_pkey on entity n  (cost=0.41..8.43 rows=1 width=55) (actual time=0.005..0.005 rows=1.00 loops=61)
              Index Cond: ((id)::text = (e.source_id)::text)
              Index Searches: 61
              Buffers: shared hit=244
Planning:
  Buffers: shared hit=257
Planning Time: 0.781 ms
Execution Time: 0.674 ms
```

## S1 查询 17

```sql
SELECT id,edge_id FROM evidence WHERE edge_id=ANY(ARRAY['edge:662f17fa572888f52ffa2c22dbba482a4f1d3a1a626f311dbd898b079eb83e72','edge:a5306fbdd85975c0d0ddf41a020402c6187c0c3b4a569a49b718933b37c1f35d','edge:731ddb4132af49cebcc86a49f8b5028f2fe8cfa436794146d11415c895ae99fc','edge:289576245f45b599b0b847f6b5927ed2f0dbfdeaab02b9dde91eac21385209ed','edge:2246dd2b9e1edbd53b2cad774485f08e885fc6b5ebd8868e9312f6e1a4b7b590','edge:5d26434c032ea389f0cf6b533bafeecd8b21b457c503fd37053643e30a9def8e','edge:2d2d87a9665afec546a9fb2ae736871d9f521f969f24916bd83dcf8e7d2e5ead','edge:7ae6819c498df48374f607bc86e1c54a30468102b0277d3ebc149ab62d620fe4','edge:73cfc581cedbd7913a7e9a63248bda6886c704464419acd1e8714b2f61f190a5','edge:d40ff301194ba7e0fc94b1df671826d1aa230715c6994e7d8bad885f0cf03e90','edge:e53dab146b6da68e5c5fe0588fa4c5f6aadf18a037868dc424eda207ec2efed2','edge:996ed53400325645c2fc6291d11612917e9ece156af4b3ac2a4f7cf77164c479','edge:a9c5d7d445671549a5b8f7add63a0ece83a5df9c531910e0d417c646c7fe338f','edge:c987d2d1952b2fe2d74b1dd0c610724ef339672dc5d6d3881ed28ed4b1562294','edge:f917f460fda1f5dbffed621dc4155e6f2b22a946e9fbd6aa87455dd0f7c55b8c','edge:745778975f4b9d0066c2ea62fe97c87e178a62f11c294de615042bd4685143c5','edge:6ccc7de86b4a8e431a2de175b8a6489e6ea745bd0fa1bf8e377b9bd58b15a4ad','edge:9092086cd46af043f3144510f9236dc3a2aa833dde1ce62fec2f3a5f602061cf','edge:f73f51bd4f939a6a84252bd3abd90ea0449d8d924427ca759e29e699850b29fc','edge:eb72bf8c43a11d1a3291ef1ecfb9d19e524ee81a0b5e4ec614b407900a079f88']) ORDER BY CASE kind WHEN 'source_quote' THEN 0 WHEN 'curated' THEN 1
    WHEN 'bibliographic' THEN 2 WHEN 'auto_extracted' THEN 3 WHEN 'rule_inferred' THEN 4 END,
    CASE WHEN field_path='' THEN 1 ELSE 0 END, field_path, id
```

```text
Sort  (cost=169.37..169.42 rows=20 width=160) (actual time=0.406..0.409 rows=40.00 loops=1)
  Sort Key: (CASE kind WHEN 'source_quote'::text THEN 0 WHEN 'curated'::text THEN 1 WHEN 'bibliographic'::text THEN 2 WHEN 'auto_extracted'::text THEN 3 WHEN 'rule_inferred'::text THEN 4 ELSE NULL::integer END), (CASE WHEN (field_path = ''::text) THEN 1 ELSE 0 END), field_path, id
  Sort Method: quicksort  Memory: 32kB
  Buffers: shared hit=104
  ->  Bitmap Heap Scan on evidence  (cost=91.16..168.94 rows=20 width=160) (actual time=0.288..0.323 rows=40.00 loops=1)
        Recheck Cond: ((edge_id)::text = ANY ('{edge:662f17fa572888f52ffa2c22dbba482a4f1d3a1a626f311dbd898b079eb83e72,edge:a5306fbdd85975c0d0ddf41a020402c6187c0c3b4a569a49b718933b37c1f35d,edge:731ddb4132af49cebcc86a49f8b5028f2fe8cfa436794146d11415c895ae99fc,edge:289576245f45b599b0b847f6b5927ed2f0dbfdeaab02b9dde91eac21385209ed,edge:2246dd2b9e1edbd53b2cad774485f08e885fc6b5ebd8868e9312f6e1a4b7b590,edge:5d26434c032ea389f0cf6b533bafeecd8b21b457c503fd37053643e30a9def8e,edge:2d2d87a9665afec546a9fb2ae736871d9f521f969f24916bd83dcf8e7d2e5ead,edge:7ae6819c498df48374f607bc86e1c54a30468102b0277d3ebc149ab62d620fe4,edge:73cfc581cedbd7913a7e9a63248bda6886c704464419acd1e8714b2f61f190a5,edge:d40ff301194ba7e0fc94b1df671826d1aa230715c6994e7d8bad885f0cf03e90,edge:e53dab146b6da68e5c5fe0588fa4c5f6aadf18a037868dc424eda207ec2efed2,edge:996ed53400325645c2fc6291d11612917e9ece156af4b3ac2a4f7cf77164c479,edge:a9c5d7d445671549a5b8f7add63a0ece83a5df9c531910e0d417c646c7fe338f,edge:c987d2d1952b2fe2d74b1dd0c610724ef339672dc5d6d3881ed28ed4b1562294,edge:f917f460fda1f5dbffed621dc4155e6f2b22a946e9fbd6aa87455dd0f7c55b8c,edge:745778975f4b9d0066c2ea62fe97c87e178a62f11c294de615042bd4685143c5,edge:6ccc7de86b4a8e431a2de175b8a6489e6ea745bd0fa1bf8e377b9bd58b15a4ad,edge:9092086cd46af043f3144510f9236dc3a2aa833dde1ce62fec2f3a5f602061cf,edge:f73f51bd4f939a6a84252bd3abd90ea0449d8d924427ca759e29e699850b29fc,edge:eb72bf8c43a11d1a3291ef1ecfb9d19e524ee81a0b5e4ec614b407900a079f88}'::text[]))
        Heap Blocks: exact=18
        Buffers: shared hit=98
        ->  Bitmap Index Scan on evidence_edge  (cost=0.00..91.10 rows=20 width=0) (actual time=0.276..0.276 rows=40.00 loops=1)
              Index Cond: ((edge_id)::text = ANY ('{edge:662f17fa572888f52ffa2c22dbba482a4f1d3a1a626f311dbd898b079eb83e72,edge:a5306fbdd85975c0d0ddf41a020402c6187c0c3b4a569a49b718933b37c1f35d,edge:731ddb4132af49cebcc86a49f8b5028f2fe8cfa436794146d11415c895ae99fc,edge:289576245f45b599b0b847f6b5927ed2f0dbfdeaab02b9dde91eac21385209ed,edge:2246dd2b9e1edbd53b2cad774485f08e885fc6b5ebd8868e9312f6e1a4b7b590,edge:5d26434c032ea389f0cf6b533bafeecd8b21b457c503fd37053643e30a9def8e,edge:2d2d87a9665afec546a9fb2ae736871d9f521f969f24916bd83dcf8e7d2e5ead,edge:7ae6819c498df48374f607bc86e1c54a30468102b0277d3ebc149ab62d620fe4,edge:73cfc581cedbd7913a7e9a63248bda6886c704464419acd1e8714b2f61f190a5,edge:d40ff301194ba7e0fc94b1df671826d1aa230715c6994e7d8bad885f0cf03e90,edge:e53dab146b6da68e5c5fe0588fa4c5f6aadf18a037868dc424eda207ec2efed2,edge:996ed53400325645c2fc6291d11612917e9ece156af4b3ac2a4f7cf77164c479,edge:a9c5d7d445671549a5b8f7add63a0ece83a5df9c531910e0d417c646c7fe338f,edge:c987d2d1952b2fe2d74b1dd0c610724ef339672dc5d6d3881ed28ed4b1562294,edge:f917f460fda1f5dbffed621dc4155e6f2b22a946e9fbd6aa87455dd0f7c55b8c,edge:745778975f4b9d0066c2ea62fe97c87e178a62f11c294de615042bd4685143c5,edge:6ccc7de86b4a8e431a2de175b8a6489e6ea745bd0fa1bf8e377b9bd58b15a4ad,edge:9092086cd46af043f3144510f9236dc3a2aa833dde1ce62fec2f3a5f602061cf,edge:f73f51bd4f939a6a84252bd3abd90ea0449d8d924427ca759e29e699850b29fc,edge:eb72bf8c43a11d1a3291ef1ecfb9d19e524ee81a0b5e4ec614b407900a079f88}'::text[]))
              Index Searches: 20
              Buffers: shared hit=80
Planning:
  Buffers: shared hit=122
Planning Time: 0.307 ms
Execution Time: 0.436 ms
```

## S1 查询 18

```sql
SELECT e.*,n.id AS node_id,n.label,n.type FROM edge e JOIN entity n ON n.id=e.source_id WHERE e.target_id='bencaodian:formula:si_jun_zi_tang' AND e.relation='CONTAINS' ORDER BY n.label,n.id
```

```text
Sort  (cost=16.88..16.89 rows=1 width=253) (actual time=0.086..0.087 rows=0.00 loops=1)
  Sort Key: n.label, e.source_id
  Sort Method: quicksort  Memory: 25kB
  Buffers: shared hit=6
  ->  Nested Loop  (cost=0.83..16.87 rows=1 width=253) (actual time=0.037..0.038 rows=0.00 loops=1)
        Buffers: shared hit=3
        ->  Index Scan using edge_incoming on edge e  (cost=0.42..8.44 rows=1 width=198) (actual time=0.036..0.036 rows=0.00 loops=1)
              Index Cond: (((target_id)::text = 'bencaodian:formula:si_jun_zi_tang'::text) AND ((relation)::text = 'CONTAINS'::text))
              Index Searches: 1
              Buffers: shared hit=3
        ->  Index Scan using entity_pkey on entity n  (cost=0.41..8.43 rows=1 width=55) (never executed)
              Index Cond: ((id)::text = (e.source_id)::text)
              Index Searches: 0
Planning:
  Buffers: shared hit=257
Planning Time: 0.607 ms
Execution Time: 0.114 ms
```

## S5 查询 1

```sql
SELECT id FROM build
```

```text
Seq Scan on build  (cost=0.00..12.90 rows=290 width=146) (actual time=0.002..0.003 rows=1.00 loops=1)
  Buffers: shared hit=1
Planning Time: 0.010 ms
Execution Time: 0.009 ms
```

## S5 查询 2

```sql
SELECT * FROM entity WHERE id='tcm-mkg:medicinal_property:8fa8553dc501fce26501a2aef0fa5cd798a41a126c217079d78274d05a5d5842'
```

```text
Index Scan using entity_pkey on entity  (cost=0.41..8.43 rows=1 width=424) (actual time=0.036..0.037 rows=1.00 loops=1)
  Index Cond: ((id)::text = 'tcm-mkg:medicinal_property:8fa8553dc501fce26501a2aef0fa5cd798a41a126c217079d78274d05a5d5842'::text)
  Index Searches: 1
  Buffers: shared hit=4
Planning:
  Buffers: shared hit=161
Planning Time: 0.333 ms
Execution Time: 0.053 ms
```

## S5 查询 3

```sql
SELECT id,title FROM dataset WHERE id='tcm-mkg'
```

```text
Index Scan using dataset_pkey on dataset  (cost=0.14..8.16 rows=1 width=210) (actual time=0.012..0.012 rows=1.00 loops=1)
  Index Cond: ((id)::text = 'tcm-mkg'::text)
  Index Searches: 1
  Buffers: shared hit=2
Planning:
  Buffers: shared hit=37
Planning Time: 0.102 ms
Execution Time: 0.028 ms
```

## S5 查询 4

```sql
SELECT name,source_record_id,field_path FROM alias WHERE entity_id='tcm-mkg:medicinal_property:8fa8553dc501fce26501a2aef0fa5cd798a41a126c217079d78274d05a5d5842' ORDER BY name_norm,name
```

```text
Incremental Sort  (cost=8.31..8.35 rows=2 width=105) (actual time=0.039..0.040 rows=0.00 loops=1)
  Sort Key: name_norm, name
  Presorted Key: name_norm
  Full-sort Groups: 1  Sort Method: quicksort  Average Memory: 25kB  Peak Memory: 25kB
  Buffers: shared hit=5
  ->  Index Scan using alias_pkey on alias  (cost=0.28..8.30 rows=1 width=105) (actual time=0.026..0.026 rows=0.00 loops=1)
        Index Cond: ((entity_id)::text = 'tcm-mkg:medicinal_property:8fa8553dc501fce26501a2aef0fa5cd798a41a126c217079d78274d05a5d5842'::text)
        Index Searches: 1
        Buffers: shared hit=2
Planning:
  Buffers: shared hit=106
Planning Time: 0.287 ms
Execution Time: 0.064 ms
```

## S5 查询 5

```sql
SELECT relation,'out' AS direction,count(*) AS count FROM edge WHERE source_id='tcm-mkg:medicinal_property:8fa8553dc501fce26501a2aef0fa5cd798a41a126c217079d78274d05a5d5842' GROUP BY relation UNION ALL SELECT relation,'in' AS direction,count(*) AS count FROM edge WHERE target_id='tcm-mkg:medicinal_property:8fa8553dc501fce26501a2aef0fa5cd798a41a126c217079d78274d05a5d5842' GROUP BY relation ORDER BY relation,direction
```

```text
Incremental Sort  (cost=38.10..485.50 rows=13 width=57) (actual time=1.041..1.043 rows=1.00 loops=1)
  Sort Key: edge.relation, ('out'::text)
  Presorted Key: edge.relation
  Full-sort Groups: 1  Sort Method: quicksort  Average Memory: 25kB  Peak Memory: 25kB
  Buffers: shared hit=144
  ->  Merge Append  (cost=0.85..484.91 rows=13 width=57) (actual time=1.032..1.033 rows=1.00 loops=1)
        Sort Key: edge.relation
        Buffers: shared hit=144
        ->  GroupAggregate  (cost=0.42..8.80 rows=6 width=57) (actual time=0.026..0.027 rows=0.00 loops=1)
              Group Key: edge.relation
              Buffers: shared hit=3
              ->  Index Only Scan using edge_outgoing on edge  (cost=0.42..8.67 rows=14 width=17) (actual time=0.025..0.025 rows=0.00 loops=1)
                    Index Cond: (source_id = 'tcm-mkg:medicinal_property:8fa8553dc501fce26501a2aef0fa5cd798a41a126c217079d78274d05a5d5842'::text)
                    Heap Fetches: 0
                    Index Searches: 1
                    Buffers: shared hit=3
        ->  GroupAggregate  (cost=0.42..475.98 rows=7 width=57) (actual time=1.005..1.005 rows=1.00 loops=1)
              Group Key: edge_1.relation
              Buffers: shared hit=141
              ->  Index Only Scan using edge_incoming on edge edge_1  (cost=0.42..458.53 rows=3476 width=17) (actual time=0.030..0.731 rows=3439.00 loops=1)
                    Index Cond: (target_id = 'tcm-mkg:medicinal_property:8fa8553dc501fce26501a2aef0fa5cd798a41a126c217079d78274d05a5d5842'::text)
                    Heap Fetches: 0
                    Index Searches: 1
                    Buffers: shared hit=141
Planning:
  Buffers: shared hit=135
Planning Time: 0.425 ms
Execution Time: 1.106 ms
```

## S5 查询 6

```sql
SELECT count(*) AS total FROM evidence WHERE entity_id='tcm-mkg:medicinal_property:8fa8553dc501fce26501a2aef0fa5cd798a41a126c217079d78274d05a5d5842'
```

```text
Aggregate  (cost=417.30..417.31 rows=1 width=8) (actual time=0.905..0.906 rows=1.00 loops=1)
  Buffers: shared hit=115
  ->  Index Only Scan using evidence_entity on evidence  (cost=0.55..408.97 rows=3331 width=0) (actual time=0.044..0.709 rows=3439.00 loops=1)
        Index Cond: (entity_id = 'tcm-mkg:medicinal_property:8fa8553dc501fce26501a2aef0fa5cd798a41a126c217079d78274d05a5d5842'::text)
        Heap Fetches: 0
        Index Searches: 1
        Buffers: shared hit=115
Planning:
  Buffers: shared hit=98
Planning Time: 0.308 ms
Execution Time: 0.940 ms
```

## S5 查询 7

```sql
SELECT id,kind,field_path,excerpt,source_record_id FROM evidence WHERE entity_id='tcm-mkg:medicinal_property:8fa8553dc501fce26501a2aef0fa5cd798a41a126c217079d78274d05a5d5842' ORDER BY CASE kind WHEN 'source_quote' THEN 0 WHEN 'curated' THEN 1
    WHEN 'bibliographic' THEN 2 WHEN 'auto_extracted' THEN 3 WHEN 'rule_inferred' THEN 4 END,
    CASE WHEN field_path='' THEN 1 ELSE 0 END, field_path, id LIMIT 20 OFFSET 0
```

```text
Limit  (cost=7052.16..7052.21 rows=20 width=299) (actual time=4.286..4.290 rows=20.00 loops=1)
  Buffers: shared hit=939
  ->  Sort  (cost=7052.16..7060.48 rows=3331 width=299) (actual time=4.285..4.286 rows=20.00 loops=1)
        Sort Key: (CASE kind WHEN 'source_quote'::text THEN 0 WHEN 'curated'::text THEN 1 WHEN 'bibliographic'::text THEN 2 WHEN 'auto_extracted'::text THEN 3 WHEN 'rule_inferred'::text THEN 4 ELSE NULL::integer END), (CASE WHEN (field_path = ''::text) THEN 1 ELSE 0 END), field_path, id
        Sort Method: top-N heapsort  Memory: 33kB
        Buffers: shared hit=939
        ->  Bitmap Heap Scan on evidence  (cost=306.36..6963.52 rows=3331 width=299) (actual time=0.580..2.387 rows=3439.00 loops=1)
              Recheck Cond: ((entity_id)::text = 'tcm-mkg:medicinal_property:8fa8553dc501fce26501a2aef0fa5cd798a41a126c217079d78274d05a5d5842'::text)
              Heap Blocks: exact=819
              Buffers: shared hit=933
              ->  Bitmap Index Scan on evidence_entity  (cost=0.00..305.53 rows=3331 width=0) (actual time=0.472..0.472 rows=3439.00 loops=1)
                    Index Cond: ((entity_id)::text = 'tcm-mkg:medicinal_property:8fa8553dc501fce26501a2aef0fa5cd798a41a126c217079d78274d05a5d5842'::text)
                    Index Searches: 1
                    Buffers: shared hit=114
Planning:
  Buffers: shared hit=129
Planning Time: 0.343 ms
Execution Time: 4.320 ms
```

## S5 查询 8

```sql
SELECT * FROM evidence WHERE id='evidence:001565e0950196b5c0981002ff8467bea6f7bf4791ac34524358cde9ef321a99'
```

```text
Index Scan using evidence_pkey on evidence  (cost=0.42..8.44 rows=1 width=401) (actual time=0.032..0.032 rows=1.00 loops=1)
  Index Cond: ((id)::text = 'evidence:001565e0950196b5c0981002ff8467bea6f7bf4791ac34524358cde9ef321a99'::text)
  Index Searches: 1
  Buffers: shared hit=4
Planning:
  Buffers: shared hit=119
Planning Time: 0.347 ms
Execution Time: 0.050 ms
```

## S5 查询 9

```sql
SELECT * FROM source_record WHERE id='source:e19c2ba452f9ec48a987efc00ba1120fec7f54faf397d2dc1fd0cb8f6ec35902'
```

```text
Index Scan using source_record_pkey on source_record  (cost=0.42..8.44 rows=1 width=466) (actual time=0.029..0.030 rows=1.00 loops=1)
  Index Cond: ((id)::text = 'source:e19c2ba452f9ec48a987efc00ba1120fec7f54faf397d2dc1fd0cb8f6ec35902'::text)
  Index Searches: 1
  Buffers: shared hit=4
Planning:
  Buffers: shared hit=100
Planning Time: 0.233 ms
Execution Time: 0.044 ms
```

## S5 查询 10

```sql
SELECT * FROM dataset WHERE id='tcm-mkg'
```

```text
Index Scan using dataset_pkey on dataset  (cost=0.14..8.16 rows=1 width=338) (actual time=0.008..0.008 rows=1.00 loops=1)
  Index Cond: ((id)::text = 'tcm-mkg'::text)
  Index Searches: 1
  Buffers: shared hit=2
Planning:
  Buffers: shared hit=37
Planning Time: 0.097 ms
Execution Time: 0.023 ms
```

## S5 查询 11

```sql
SELECT e.*,n.id AS node_id,n.label,n.type FROM edge e JOIN entity n ON n.id=e.target_id WHERE e.source_id='tcm-mkg:medicinal_property:8fa8553dc501fce26501a2aef0fa5cd798a41a126c217079d78274d05a5d5842' AND e.relation='CONTAINS'
```

```text
Nested Loop  (cost=0.83..16.87 rows=1 width=253) (actual time=0.020..0.021 rows=0.00 loops=1)
  Buffers: shared hit=3
  ->  Index Scan using edge_outgoing on edge e  (cost=0.42..8.44 rows=1 width=198) (actual time=0.019..0.020 rows=0.00 loops=1)
        Index Cond: (((source_id)::text = 'tcm-mkg:medicinal_property:8fa8553dc501fce26501a2aef0fa5cd798a41a126c217079d78274d05a5d5842'::text) AND ((relation)::text = 'CONTAINS'::text))
        Index Searches: 1
        Buffers: shared hit=3
  ->  Index Scan using entity_pkey on entity n  (cost=0.41..8.43 rows=1 width=55) (never executed)
        Index Cond: ((id)::text = (e.target_id)::text)
        Index Searches: 0
Planning:
  Buffers: shared hit=345
Planning Time: 0.899 ms
Execution Time: 0.044 ms
```

## S5 查询 12

```sql
SELECT e.*,n.id AS node_id,n.label,n.type FROM edge e JOIN entity n ON n.id=e.source_id WHERE e.target_id='tcm-mkg:medicinal_property:8fa8553dc501fce26501a2aef0fa5cd798a41a126c217079d78274d05a5d5842' AND e.relation='CONTAINS' ORDER BY n.label,n.id
```

```text
Sort  (cost=189.65..189.69 rows=15 width=253) (actual time=0.041..0.042 rows=0.00 loops=1)
  Sort Key: n.label, e.source_id
  Sort Method: quicksort  Memory: 25kB
  Buffers: shared hit=6
  ->  Nested Loop  (cost=0.83..189.35 rows=15 width=253) (actual time=0.024..0.025 rows=0.00 loops=1)
        Buffers: shared hit=3
        ->  Index Scan using edge_incoming on edge e  (cost=0.42..62.90 rows=15 width=198) (actual time=0.023..0.024 rows=0.00 loops=1)
              Index Cond: (((target_id)::text = 'tcm-mkg:medicinal_property:8fa8553dc501fce26501a2aef0fa5cd798a41a126c217079d78274d05a5d5842'::text) AND ((relation)::text = 'CONTAINS'::text))
              Index Searches: 1
              Buffers: shared hit=3
        ->  Index Scan using entity_pkey on entity n  (cost=0.41..8.43 rows=1 width=55) (never executed)
              Index Cond: ((id)::text = (e.source_id)::text)
              Index Searches: 0
Planning:
  Buffers: shared hit=257
Planning Time: 0.812 ms
Execution Time: 0.070 ms
```
