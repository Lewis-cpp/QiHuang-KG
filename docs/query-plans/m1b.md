# M1b 查询执行计划

批次：`5a76218e52001d45e4bd75e099a38780408e873342a14e5db0c86d7bb7a3008a`。服务器：`PostgreSQL 16.15 (Ubuntu 16.15-0ubuntu0.24.04.1) on x86_64-pc-linux-gnu, compiled by gcc (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0, 64-bit`。

保持默认规划器设置。关系与证据查询不允许 edge/evidence 顺序扫描；子串检索按 spec §4.2 先用 LIKE 实测，entity/alias 顺序扫描是预期结果，耗时见 m1b-performance.json。

## search exact 甘草

```sql
WITH hits AS (
    SELECT id AS entity_id, 'name' AS field, label AS text, name_norm AS text_norm,
           CASE WHEN name_norm='甘草' THEN 1 WHEN name_norm LIKE '甘草%' THEN 3 ELSE 5 END AS match_rank
    FROM entity WHERE name_norm LIKE '%甘草%'
    UNION ALL
    SELECT entity_id, 'alias', name, name_norm,
           CASE WHEN name_norm='甘草' THEN 2 WHEN name_norm LIKE '甘草%' THEN 4 ELSE 5 END
    FROM alias WHERE name_norm LIKE '%甘草%'
), best AS (
    SELECT h.*, row_number() OVER (PARTITION BY entity_id ORDER BY match_rank,
           CASE field WHEN 'name' THEN 0 ELSE 1 END, text_norm COLLATE "C", text COLLATE "C") AS pick
    FROM hits h
)
SELECT count(*) AS total FROM best b JOIN entity e ON e.id=b.entity_id WHERE b.pick=1
    AND (NULL::text IS NULL OR e.type=NULL) AND (NULL::text IS NULL OR e.dataset_id=NULL)
```

```text
Aggregate  (cost=1578.49..1578.50 rows=1 width=8) (actual time=4.805..4.808 rows=1 loops=1)
  Buffers: shared hit=1339
  ->  Nested Loop  (cost=1570.34..1578.48 rows=1 width=0) (actual time=4.672..4.802 rows=18 loops=1)
        Buffers: shared hit=1339
        ->  Subquery Scan on b  (cost=1569.93..1570.05 rows=1 width=418) (actual time=4.633..4.657 rows=18 loops=1)
              Filter: (b.pick = 1)
              Buffers: shared hit=1284
              ->  WindowAgg  (cost=1569.93..1570.02 rows=3 width=594) (actual time=4.633..4.654 rows=18 loops=1)
                    Run Condition: (row_number() OVER (?) <= 1)
                    Buffers: shared hit=1284
                    ->  Sort  (cost=1569.93..1569.93 rows=3 width=490) (actual time=4.628..4.636 rows=24 loops=1)
                          Sort Key: h.entity_id, h.match_rank, (CASE h.field WHEN 'name'::text THEN 0 ELSE 1 END), ((h.text_norm)::text) COLLATE "C", ((h.text)::text) COLLATE "C"
                          Sort Method: quicksort  Memory: 27kB
                          Buffers: shared hit=1284
                          ->  Subquery Scan on h  (cost=0.00..1569.90 rows=3 width=490) (actual time=0.007..4.588 rows=24 loops=1)
                                Buffers: shared hit=1278
                                ->  Append  (cost=0.00..1569.87 rows=3 width=518) (actual time=0.006..4.579 rows=24 loops=1)
                                      Buffers: shared hit=1278
                                      ->  Seq Scan on entity  (cost=0.00..1470.68 rows=2 width=90) (actual time=0.006..4.204 rows=16 loops=1)
                                            Filter: (name_norm ~~ '%甘草%'::text)
                                            Rows Removed by Filter: 20358
                                            Buffers: shared hit=1216
                                      ->  Subquery Scan on "*SELECT* 2"  (cost=0.00..99.17 rows=1 width=108) (actual time=0.212..0.371 rows=8 loops=1)
                                            Buffers: shared hit=62
                                            ->  Seq Scan on alias  (cost=0.00..99.16 rows=1 width=87) (actual time=0.211..0.368 rows=8 loops=1)
                                                  Filter: ((name_norm)::text ~~ '%甘草%'::text)
                                                  Rows Removed by Filter: 2964
                                                  Buffers: shared hit=62
        ->  Index Only Scan using entity_pkey on entity e  (cost=0.41..8.43 rows=1 width=30) (actual time=0.007..0.007 rows=1 loops=18)
              Index Cond: (id = (b.entity_id)::text)
              Heap Fetches: 0
              Buffers: shared hit=55
Planning:
  Buffers: shared hit=218
Planning Time: 0.726 ms
Execution Time: 4.902 ms
```

```sql
WITH hits AS (
    SELECT id AS entity_id, 'name' AS field, label AS text, name_norm AS text_norm,
           CASE WHEN name_norm='甘草' THEN 1 WHEN name_norm LIKE '甘草%' THEN 3 ELSE 5 END AS match_rank
    FROM entity WHERE name_norm LIKE '%甘草%'
    UNION ALL
    SELECT entity_id, 'alias', name, name_norm,
           CASE WHEN name_norm='甘草' THEN 2 WHEN name_norm LIKE '甘草%' THEN 4 ELSE 5 END
    FROM alias WHERE name_norm LIKE '%甘草%'
), best AS (
    SELECT h.*, row_number() OVER (PARTITION BY entity_id ORDER BY match_rank,
           CASE field WHEN 'name' THEN 0 ELSE 1 END, text_norm COLLATE "C", text COLLATE "C") AS pick
    FROM hits h
)
SELECT e.id,e.label,e.type,e.dataset_id,e.category,e.review_status,b.field,b.text FROM best b JOIN entity e ON e.id=b.entity_id WHERE b.pick=1
    AND (NULL::text IS NULL OR e.type=NULL) AND (NULL::text IS NULL OR e.dataset_id=NULL) ORDER BY b.match_rank, e.name_norm COLLATE "C", e.id LIMIT 20 OFFSET 0
```

```text
Limit  (cost=1578.49..1578.50 rows=1 width=184) (actual time=4.646..4.652 rows=18 loops=1)
  Buffers: shared hit=1356
  ->  Sort  (cost=1578.49..1578.50 rows=1 width=184) (actual time=4.645..4.649 rows=18 loops=1)
        Sort Key: b.match_rank, ((e.name_norm)::text) COLLATE "C", e.id
        Sort Method: quicksort  Memory: 29kB
        Buffers: shared hit=1356
        ->  Nested Loop  (cost=1570.34..1578.48 rows=1 width=184) (actual time=4.492..4.606 rows=18 loops=1)
              Buffers: shared hit=1350
              ->  Subquery Scan on b  (cost=1569.93..1570.05 rows=1 width=486) (actual time=4.464..4.483 rows=18 loops=1)
                    Filter: (b.pick = 1)
                    Buffers: shared hit=1278
                    ->  WindowAgg  (cost=1569.93..1570.02 rows=3 width=594) (actual time=4.463..4.479 rows=18 loops=1)
                          Run Condition: (row_number() OVER (?) <= 1)
                          Buffers: shared hit=1278
                          ->  Sort  (cost=1569.93..1569.93 rows=3 width=554) (actual time=4.454..4.458 rows=24 loops=1)
                                Sort Key: h.entity_id, h.match_rank, (CASE h.field WHEN 'name'::text THEN 0 ELSE 1 END), ((h.text_norm)::text) COLLATE "C", ((h.text)::text) COLLATE "C"
                                Sort Method: quicksort  Memory: 27kB
                                Buffers: shared hit=1278
                                ->  Subquery Scan on h  (cost=0.00..1569.90 rows=3 width=554) (actual time=0.007..4.403 rows=24 loops=1)
                                      Buffers: shared hit=1278
                                      ->  Append  (cost=0.00..1569.87 rows=3 width=518) (actual time=0.005..4.393 rows=24 loops=1)
                                            Buffers: shared hit=1278
                                            ->  Seq Scan on entity  (cost=0.00..1470.68 rows=2 width=90) (actual time=0.005..4.063 rows=16 loops=1)
                                                  Filter: (name_norm ~~ '%甘草%'::text)
                                                  Rows Removed by Filter: 20358
                                                  Buffers: shared hit=1216
                                            ->  Subquery Scan on "*SELECT* 2"  (cost=0.00..99.17 rows=1 width=108) (actual time=0.156..0.325 rows=8 loops=1)
                                                  Buffers: shared hit=62
                                                  ->  Seq Scan on alias  (cost=0.00..99.16 rows=1 width=87) (actual time=0.155..0.323 rows=8 loops=1)
                                                        Filter: ((name_norm)::text ~~ '%甘草%'::text)
                                                        Rows Removed by Filter: 2964
                                                        Buffers: shared hit=62
              ->  Index Scan using entity_pkey on entity e  (cost=0.41..8.43 rows=1 width=96) (actual time=0.006..0.006 rows=1 loops=18)
                    Index Cond: ((id)::text = (b.entity_id)::text)
                    Buffers: shared hit=72
Planning:
  Buffers: shared hit=224
Planning Time: 0.734 ms
Execution Time: 4.750 ms
```

## search single char 草

```sql
WITH hits AS (
    SELECT id AS entity_id, 'name' AS field, label AS text, name_norm AS text_norm,
           CASE WHEN name_norm='草' THEN 1 WHEN name_norm LIKE '草%' THEN 3 ELSE 5 END AS match_rank
    FROM entity WHERE name_norm LIKE '%草%'
    UNION ALL
    SELECT entity_id, 'alias', name, name_norm,
           CASE WHEN name_norm='草' THEN 2 WHEN name_norm LIKE '草%' THEN 4 ELSE 5 END
    FROM alias WHERE name_norm LIKE '%草%'
), best AS (
    SELECT h.*, row_number() OVER (PARTITION BY entity_id ORDER BY match_rank,
           CASE field WHEN 'name' THEN 0 ELSE 1 END, text_norm COLLATE "C", text COLLATE "C") AS pick
    FROM hits h
)
SELECT count(*) AS total FROM best b JOIN entity e ON e.id=b.entity_id WHERE b.pick=1
    AND (NULL::text IS NULL OR e.type=NULL) AND (NULL::text IS NULL OR e.dataset_id=NULL)
```

```text
Aggregate  (cost=1716.57..1716.58 rows=1 width=8) (actual time=7.593..7.596 rows=1 loops=1)
  Buffers: shared hit=3898
  ->  Nested Loop  (cost=1647.05..1716.56 rows=5 width=0) (actual time=5.134..7.535 rows=871 loops=1)
        Buffers: shared hit=3898
        ->  Subquery Scan on b  (cost=1646.63..1690.41 rows=5 width=418) (actual time=5.095..5.655 rows=871 loops=1)
              Filter: (b.pick = 1)
              Buffers: shared hit=1284
              ->  WindowAgg  (cost=1646.63..1677.53 rows=1030 width=594) (actual time=5.094..5.564 rows=871 loops=1)
                    Run Condition: (row_number() OVER (?) <= 1)
                    Buffers: shared hit=1284
                    ->  Sort  (cost=1646.63..1649.21 rows=1030 width=490) (actual time=5.086..5.146 rows=985 loops=1)
                          Sort Key: h.entity_id, h.match_rank, (CASE h.field WHEN 'name'::text THEN 0 ELSE 1 END), ((h.text_norm)::text) COLLATE "C", ((h.text)::text) COLLATE "C"
                          Sort Method: quicksort  Memory: 114kB
                          Buffers: shared hit=1284
                          ->  Subquery Scan on h  (cost=0.00..1595.09 rows=1030 width=490) (actual time=0.007..4.369 rows=985 loops=1)
                                Buffers: shared hit=1278
                                ->  Append  (cost=0.00..1582.22 rows=1030 width=518) (actual time=0.006..4.218 rows=985 loops=1)
                                      Buffers: shared hit=1278
                                      ->  Seq Scan on entity  (cost=0.00..1474.78 rows=821 width=90) (actual time=0.005..3.740 rows=789 loops=1)
                                            Filter: (name_norm ~~ '%草%'::text)
                                            Rows Removed by Filter: 19585
                                            Buffers: shared hit=1216
                                      ->  Subquery Scan on "*SELECT* 2"  (cost=0.00..102.29 rows=209 width=108) (actual time=0.142..0.388 rows=196 loops=1)
                                            Buffers: shared hit=62
                                            ->  Seq Scan on alias  (cost=0.00..100.20 rows=209 width=87) (actual time=0.141..0.367 rows=196 loops=1)
                                                  Filter: ((name_norm)::text ~~ '%草%'::text)
                                                  Rows Removed by Filter: 2776
                                                  Buffers: shared hit=62
        ->  Index Only Scan using entity_pkey on entity e  (cost=0.41..5.23 rows=1 width=30) (actual time=0.002..0.002 rows=1 loops=871)
              Index Cond: (id = (b.entity_id)::text)
              Heap Fetches: 0
              Buffers: shared hit=2614
Planning:
  Buffers: shared hit=218
Planning Time: 0.733 ms
Execution Time: 7.690 ms
```

```sql
WITH hits AS (
    SELECT id AS entity_id, 'name' AS field, label AS text, name_norm AS text_norm,
           CASE WHEN name_norm='草' THEN 1 WHEN name_norm LIKE '草%' THEN 3 ELSE 5 END AS match_rank
    FROM entity WHERE name_norm LIKE '%草%'
    UNION ALL
    SELECT entity_id, 'alias', name, name_norm,
           CASE WHEN name_norm='草' THEN 2 WHEN name_norm LIKE '草%' THEN 4 ELSE 5 END
    FROM alias WHERE name_norm LIKE '%草%'
), best AS (
    SELECT h.*, row_number() OVER (PARTITION BY entity_id ORDER BY match_rank,
           CASE field WHEN 'name' THEN 0 ELSE 1 END, text_norm COLLATE "C", text COLLATE "C") AS pick
    FROM hits h
)
SELECT e.id,e.label,e.type,e.dataset_id,e.category,e.review_status,b.field,b.text FROM best b JOIN entity e ON e.id=b.entity_id WHERE b.pick=1
    AND (NULL::text IS NULL OR e.type=NULL) AND (NULL::text IS NULL OR e.dataset_id=NULL) ORDER BY b.match_rank, e.name_norm COLLATE "C", e.id LIMIT 20 OFFSET 0
```

```text
Limit  (cost=1732.62..1732.63 rows=5 width=184) (actual time=8.158..8.164 rows=20 loops=1)
  Buffers: shared hit=4768
  ->  Sort  (cost=1732.62..1732.63 rows=5 width=184) (actual time=8.157..8.160 rows=20 loops=1)
        Sort Key: b.match_rank, ((e.name_norm)::text) COLLATE "C", e.id
        Sort Method: top-N heapsort  Memory: 33kB
        Buffers: shared hit=4768
        ->  Nested Loop  (cost=1647.05..1732.56 rows=5 width=184) (actual time=5.006..7.642 rows=871 loops=1)
              Buffers: shared hit=4762
              ->  Subquery Scan on b  (cost=1646.63..1690.41 rows=5 width=486) (actual time=4.983..5.551 rows=871 loops=1)
                    Filter: (b.pick = 1)
                    Buffers: shared hit=1278
                    ->  WindowAgg  (cost=1646.63..1677.53 rows=1030 width=594) (actual time=4.983..5.461 rows=871 loops=1)
                          Run Condition: (row_number() OVER (?) <= 1)
                          Buffers: shared hit=1278
                          ->  Sort  (cost=1646.63..1649.21 rows=1030 width=554) (actual time=4.975..5.035 rows=985 loops=1)
                                Sort Key: h.entity_id, h.match_rank, (CASE h.field WHEN 'name'::text THEN 0 ELSE 1 END), ((h.text_norm)::text) COLLATE "C", ((h.text)::text) COLLATE "C"
                                Sort Method: quicksort  Memory: 132kB
                                Buffers: shared hit=1278
                                ->  Subquery Scan on h  (cost=0.00..1595.09 rows=1030 width=554) (actual time=0.007..4.305 rows=985 loops=1)
                                      Buffers: shared hit=1278
                                      ->  Append  (cost=0.00..1582.22 rows=1030 width=518) (actual time=0.005..4.169 rows=985 loops=1)
                                            Buffers: shared hit=1278
                                            ->  Seq Scan on entity  (cost=0.00..1474.78 rows=821 width=90) (actual time=0.005..3.696 rows=789 loops=1)
                                                  Filter: (name_norm ~~ '%草%'::text)
                                                  Rows Removed by Filter: 19585
                                                  Buffers: shared hit=1216
                                            ->  Subquery Scan on "*SELECT* 2"  (cost=0.00..102.29 rows=209 width=108) (actual time=0.139..0.385 rows=196 loops=1)
                                                  Buffers: shared hit=62
                                                  ->  Seq Scan on alias  (cost=0.00..100.20 rows=209 width=87) (actual time=0.138..0.364 rows=196 loops=1)
                                                        Filter: ((name_norm)::text ~~ '%草%'::text)
                                                        Rows Removed by Filter: 2776
                                                        Buffers: shared hit=62
              ->  Index Scan using entity_pkey on entity e  (cost=0.41..8.43 rows=1 width=96) (actual time=0.002..0.002 rows=1 loops=871)
                    Index Cond: ((id)::text = (b.entity_id)::text)
                    Buffers: shared hit=3484
Planning:
  Buffers: shared hit=224
Planning Time: 0.719 ms
Execution Time: 8.258 ms
```

## search alias 黄耆

```sql
WITH hits AS (
    SELECT id AS entity_id, 'name' AS field, label AS text, name_norm AS text_norm,
           CASE WHEN name_norm='黄耆' THEN 1 WHEN name_norm LIKE '黄耆%' THEN 3 ELSE 5 END AS match_rank
    FROM entity WHERE name_norm LIKE '%黄耆%'
    UNION ALL
    SELECT entity_id, 'alias', name, name_norm,
           CASE WHEN name_norm='黄耆' THEN 2 WHEN name_norm LIKE '黄耆%' THEN 4 ELSE 5 END
    FROM alias WHERE name_norm LIKE '%黄耆%'
), best AS (
    SELECT h.*, row_number() OVER (PARTITION BY entity_id ORDER BY match_rank,
           CASE field WHEN 'name' THEN 0 ELSE 1 END, text_norm COLLATE "C", text COLLATE "C") AS pick
    FROM hits h
)
SELECT count(*) AS total FROM best b JOIN entity e ON e.id=b.entity_id WHERE b.pick=1
    AND (NULL::text IS NULL OR e.type=NULL) AND (NULL::text IS NULL OR e.dataset_id=NULL)
```

```text
Aggregate  (cost=1578.49..1578.50 rows=1 width=8) (actual time=3.852..3.854 rows=1 loops=1)
  Buffers: shared hit=1294
  ->  Nested Loop  (cost=1570.34..1578.48 rows=1 width=0) (actual time=3.835..3.850 rows=3 loops=1)
        Buffers: shared hit=1294
        ->  Subquery Scan on b  (cost=1569.93..1570.05 rows=1 width=418) (actual time=3.800..3.806 rows=3 loops=1)
              Filter: (b.pick = 1)
              Buffers: shared hit=1284
              ->  WindowAgg  (cost=1569.93..1570.02 rows=3 width=594) (actual time=3.799..3.804 rows=3 loops=1)
                    Run Condition: (row_number() OVER (?) <= 1)
                    Buffers: shared hit=1284
                    ->  Sort  (cost=1569.93..1569.93 rows=3 width=490) (actual time=3.794..3.795 rows=3 loops=1)
                          Sort Key: h.entity_id, h.match_rank, (CASE h.field WHEN 'name'::text THEN 0 ELSE 1 END), ((h.text_norm)::text) COLLATE "C", ((h.text)::text) COLLATE "C"
                          Sort Method: quicksort  Memory: 25kB
                          Buffers: shared hit=1284
                          ->  Subquery Scan on h  (cost=0.00..1569.90 rows=3 width=490) (actual time=2.733..3.770 rows=3 loops=1)
                                Buffers: shared hit=1278
                                ->  Append  (cost=0.00..1569.87 rows=3 width=518) (actual time=2.731..3.766 rows=3 loops=1)
                                      Buffers: shared hit=1278
                                      ->  Seq Scan on entity  (cost=0.00..1470.68 rows=2 width=90) (actual time=2.730..3.475 rows=1 loops=1)
                                            Filter: (name_norm ~~ '%黄耆%'::text)
                                            Rows Removed by Filter: 20373
                                            Buffers: shared hit=1216
                                      ->  Subquery Scan on "*SELECT* 2"  (cost=0.00..99.17 rows=1 width=108) (actual time=0.151..0.289 rows=2 loops=1)
                                            Buffers: shared hit=62
                                            ->  Seq Scan on alias  (cost=0.00..99.16 rows=1 width=87) (actual time=0.150..0.287 rows=2 loops=1)
                                                  Filter: ((name_norm)::text ~~ '%黄耆%'::text)
                                                  Rows Removed by Filter: 2970
                                                  Buffers: shared hit=62
        ->  Index Only Scan using entity_pkey on entity e  (cost=0.41..8.43 rows=1 width=30) (actual time=0.013..0.013 rows=1 loops=3)
              Index Cond: (id = (b.entity_id)::text)
              Heap Fetches: 0
              Buffers: shared hit=10
Planning:
  Buffers: shared hit=218
Planning Time: 0.663 ms
Execution Time: 3.952 ms
```

```sql
WITH hits AS (
    SELECT id AS entity_id, 'name' AS field, label AS text, name_norm AS text_norm,
           CASE WHEN name_norm='黄耆' THEN 1 WHEN name_norm LIKE '黄耆%' THEN 3 ELSE 5 END AS match_rank
    FROM entity WHERE name_norm LIKE '%黄耆%'
    UNION ALL
    SELECT entity_id, 'alias', name, name_norm,
           CASE WHEN name_norm='黄耆' THEN 2 WHEN name_norm LIKE '黄耆%' THEN 4 ELSE 5 END
    FROM alias WHERE name_norm LIKE '%黄耆%'
), best AS (
    SELECT h.*, row_number() OVER (PARTITION BY entity_id ORDER BY match_rank,
           CASE field WHEN 'name' THEN 0 ELSE 1 END, text_norm COLLATE "C", text COLLATE "C") AS pick
    FROM hits h
)
SELECT e.id,e.label,e.type,e.dataset_id,e.category,e.review_status,b.field,b.text FROM best b JOIN entity e ON e.id=b.entity_id WHERE b.pick=1
    AND (NULL::text IS NULL OR e.type=NULL) AND (NULL::text IS NULL OR e.dataset_id=NULL) ORDER BY b.match_rank, e.name_norm COLLATE "C", e.id LIMIT 20 OFFSET 0
```

```text
Limit  (cost=1578.49..1578.50 rows=1 width=184) (actual time=3.927..3.930 rows=3 loops=1)
  Buffers: shared hit=1296
  ->  Sort  (cost=1578.49..1578.50 rows=1 width=184) (actual time=3.926..3.929 rows=3 loops=1)
        Sort Key: b.match_rank, ((e.name_norm)::text) COLLATE "C", e.id
        Sort Method: quicksort  Memory: 25kB
        Buffers: shared hit=1296
        ->  Nested Loop  (cost=1570.34..1578.48 rows=1 width=184) (actual time=3.885..3.901 rows=3 loops=1)
              Buffers: shared hit=1290
              ->  Subquery Scan on b  (cost=1569.93..1570.05 rows=1 width=486) (actual time=3.862..3.868 rows=3 loops=1)
                    Filter: (b.pick = 1)
                    Buffers: shared hit=1278
                    ->  WindowAgg  (cost=1569.93..1570.02 rows=3 width=594) (actual time=3.861..3.866 rows=3 loops=1)
                          Run Condition: (row_number() OVER (?) <= 1)
                          Buffers: shared hit=1278
                          ->  Sort  (cost=1569.93..1569.93 rows=3 width=554) (actual time=3.852..3.854 rows=3 loops=1)
                                Sort Key: h.entity_id, h.match_rank, (CASE h.field WHEN 'name'::text THEN 0 ELSE 1 END), ((h.text_norm)::text) COLLATE "C", ((h.text)::text) COLLATE "C"
                                Sort Method: quicksort  Memory: 25kB
                                Buffers: shared hit=1278
                                ->  Subquery Scan on h  (cost=0.00..1569.90 rows=3 width=554) (actual time=2.829..3.838 rows=3 loops=1)
                                      Buffers: shared hit=1278
                                      ->  Append  (cost=0.00..1569.87 rows=3 width=518) (actual time=2.827..3.834 rows=3 loops=1)
                                            Buffers: shared hit=1278
                                            ->  Seq Scan on entity  (cost=0.00..1470.68 rows=2 width=90) (actual time=2.826..3.517 rows=1 loops=1)
                                                  Filter: (name_norm ~~ '%黄耆%'::text)
                                                  Rows Removed by Filter: 20373
                                                  Buffers: shared hit=1216
                                            ->  Subquery Scan on "*SELECT* 2"  (cost=0.00..99.17 rows=1 width=108) (actual time=0.186..0.314 rows=2 loops=1)
                                                  Buffers: shared hit=62
                                                  ->  Seq Scan on alias  (cost=0.00..99.16 rows=1 width=87) (actual time=0.185..0.312 rows=2 loops=1)
                                                        Filter: ((name_norm)::text ~~ '%黄耆%'::text)
                                                        Rows Removed by Filter: 2970
                                                        Buffers: shared hit=62
              ->  Index Scan using entity_pkey on entity e  (cost=0.41..8.43 rows=1 width=96) (actual time=0.009..0.009 rows=1 loops=3)
                    Index Cond: ((id)::text = (b.entity_id)::text)
                    Buffers: shared hit=12
Planning:
  Buffers: shared hit=224
Planning Time: 0.696 ms
Execution Time: 4.020 ms
```

## catalog medicinal_property

```sql
SELECT count(*) AS total FROM entity e
    WHERE ('medicinal_property'::text IS NULL OR e.type='medicinal_property') AND (NULL::text IS NULL OR e.dataset_id=NULL)
```

```text
Aggregate  (cost=12.27..12.28 rows=1 width=8) (actual time=0.064..0.065 rows=1 loops=1)
  Buffers: shared hit=4
  ->  Index Only Scan using entity_type_name on entity e  (cost=0.41..12.21 rows=23 width=0) (actual time=0.058..0.060 rows=23 loops=1)
        Index Cond: (type = 'medicinal_property'::text)
        Heap Fetches: 0
        Buffers: shared hit=4
Planning:
  Buffers: shared hit=92
Planning Time: 0.231 ms
Execution Time: 0.084 ms
```

```sql
SELECT e.id,e.label,e.type,e.dataset_id,e.category,e.review_status FROM entity e
    WHERE ('medicinal_property'::text IS NULL OR e.type='medicinal_property') AND (NULL::text IS NULL OR e.dataset_id=NULL) ORDER BY e.name_norm COLLATE "C", e.id LIMIT 20 OFFSET 0
```

```text
Limit  (cost=84.18..84.23 rows=20 width=116) (actual time=0.066..0.069 rows=20 loops=1)
  Buffers: shared hit=16
  ->  Sort  (cost=84.18..84.24 rows=23 width=116) (actual time=0.065..0.066 rows=20 loops=1)
        Sort Key: ((name_norm)::text) COLLATE "C", id
        Sort Method: quicksort  Memory: 30kB
        Buffers: shared hit=16
        ->  Index Scan using entity_type_name on entity e  (cost=0.41..83.66 rows=23 width=116) (actual time=0.022..0.030 rows=23 loops=1)
              Index Cond: ((type)::text = 'medicinal_property'::text)
              Buffers: shared hit=13
Planning:
  Buffers: shared hit=134
Planning Time: 0.419 ms
Execution Time: 0.088 ms
```

## relations CONTAINS out S3

```sql
SELECT e0.id AS e0_id, e0.source_id AS e0_source_id, e0.target_id AS e0_target_id, e0.relation AS e0_relation, e0.properties_json AS e0_properties_json, e0.quality_state AS e0_quality_state, n0.id AS n0_id, n0.label AS n0_label, n0.type AS n0_type, n0.category AS n0_category FROM edge e0 JOIN entity n0 ON n0.id=e0.target_id WHERE e0.source_id='bencaodian:formula:zhu_ling_tang' AND e0.relation='CONTAINS'
```

```text
Nested Loop  (cost=0.83..16.87 rows=1 width=266) (actual time=0.071..0.088 rows=5 loops=1)
  Buffers: shared hit=24
  ->  Index Scan using edge_outgoing on edge e0  (cost=0.42..8.44 rows=1 width=198) (actual time=0.054..0.055 rows=5 loops=1)
        Index Cond: (((source_id)::text = 'bencaodian:formula:zhu_ling_tang'::text) AND ((relation)::text = 'CONTAINS'::text))
        Buffers: shared hit=4
  ->  Index Scan using entity_pkey on entity n0  (cost=0.41..8.43 rows=1 width=68) (actual time=0.005..0.005 rows=1 loops=5)
        Index Cond: ((id)::text = (e0.target_id)::text)
        Buffers: shared hit=20
Planning:
  Buffers: shared hit=345
Planning Time: 0.863 ms
Execution Time: 0.110 ms
```

```sql
SELECT id,edge_id FROM evidence WHERE edge_id=ANY(ARRAY['edge:862d7ee7ca4ed1310a01e828b87f4f7106991065e1b730cffc92377e17c0d2e2','edge:269ca3f893b0fa90624471b05c454c15e07156f85f93574d7f97f257bef82d25','edge:af053ef907127d7c2cddc94a5bc967d80fa974028f9b91801a30fe9e65c58d51','edge:2b82918fca5e3b701fb8acc6a8f75865371737cc7a029a2cf1aa3652ddec6e5a','edge:635813be84a5b4767453ede97982693b8949a75a5f1b340873138f7ae3723cc2']) ORDER BY CASE kind WHEN 'source_quote' THEN 0 WHEN 'curated' THEN 1
    WHEN 'bibliographic' THEN 2 WHEN 'auto_extracted' THEN 3 WHEN 'rule_inferred' THEN 4 END,
    CASE WHEN field_path='' THEN 1 ELSE 0 END, field_path COLLATE "C", id
```

```text
Sort  (cost=42.96..42.97 rows=5 width=184) (actual time=0.099..0.100 rows=10 loops=1)
  Sort Key: (CASE kind WHEN 'source_quote'::text THEN 0 WHEN 'curated'::text THEN 1 WHEN 'bibliographic'::text THEN 2 WHEN 'auto_extracted'::text THEN 3 WHEN 'rule_inferred'::text THEN 4 ELSE NULL::integer END), (CASE WHEN (field_path = ''::text) THEN 1 ELSE 0 END), ((field_path)::text) COLLATE "C", id
  Sort Method: quicksort  Memory: 26kB
  Buffers: shared hit=30
  ->  Index Scan using evidence_edge on evidence  (cost=0.55..42.90 rows=5 width=184) (actual time=0.043..0.074 rows=10 loops=1)
        Index Cond: ((edge_id)::text = ANY ('{edge:862d7ee7ca4ed1310a01e828b87f4f7106991065e1b730cffc92377e17c0d2e2,edge:269ca3f893b0fa90624471b05c454c15e07156f85f93574d7f97f257bef82d25,edge:af053ef907127d7c2cddc94a5bc967d80fa974028f9b91801a30fe9e65c58d51,edge:2b82918fca5e3b701fb8acc6a8f75865371737cc7a029a2cf1aa3652ddec6e5a,edge:635813be84a5b4767453ede97982693b8949a75a5f1b340873138f7ae3723cc2}'::text[]))
        Buffers: shared hit=24
Planning:
  Buffers: shared hit=115
Planning Time: 0.326 ms
Execution Time: 0.117 ms
```

## relations HAS_MEDICINAL_PROPERTY in S5 deep page

```sql
SELECT count(*) AS total FROM edge e0 JOIN entity n0 ON n0.id=e0.source_id WHERE e0.target_id='tcm-mkg:medicinal_property:8fa8553dc501fce26501a2aef0fa5cd798a41a126c217079d78274d05a5d5842' AND e0.relation='HAS_MEDICINAL_PROPERTY'
```

```text
Aggregate  (cost=1245.14..1245.15 rows=1 width=8) (actual time=6.135..6.136 rows=1 loops=1)
  Buffers: shared hit=10459
  ->  Nested Loop  (cost=0.83..1243.97 rows=471 width=0) (actual time=0.043..5.924 rows=3439 loops=1)
        Buffers: shared hit=10459
        ->  Index Only Scan using edge_incoming on edge e0  (cost=0.42..69.44 rows=471 width=32) (actual time=0.026..0.716 rows=3439 loops=1)
              Index Cond: ((target_id = 'tcm-mkg:medicinal_property:8fa8553dc501fce26501a2aef0fa5cd798a41a126c217079d78274d05a5d5842'::text) AND (relation = 'HAS_MEDICINAL_PROPERTY'::text))
              Heap Fetches: 0
              Buffers: shared hit=141
        ->  Index Only Scan using entity_pkey on entity n0  (cost=0.41..2.49 rows=1 width=30) (actual time=0.001..0.001 rows=1 loops=3439)
              Index Cond: (id = (e0.source_id)::text)
              Heap Fetches: 0
              Buffers: shared hit=10318
Planning:
  Buffers: shared hit=324
Planning Time: 0.771 ms
Execution Time: 6.171 ms
```

```sql
SELECT e0.id AS e0_id, e0.source_id AS e0_source_id, e0.target_id AS e0_target_id, e0.relation AS e0_relation, e0.properties_json AS e0_properties_json, e0.quality_state AS e0_quality_state, n0.id AS n0_id, n0.label AS n0_label, n0.type AS n0_type, n0.category AS n0_category FROM edge e0 JOIN entity n0 ON n0.id=e0.source_id WHERE e0.target_id='tcm-mkg:medicinal_property:8fa8553dc501fce26501a2aef0fa5cd798a41a126c217079d78274d05a5d5842' AND e0.relation='HAS_MEDICINAL_PROPERTY' ORDER BY n0.label COLLATE "C", n0.id LIMIT 50 OFFSET 3400
```

```text
Limit  (cost=2963.06..2963.06 rows=1 width=298) (actual time=16.743..16.752 rows=39 loops=1)
  Buffers: shared hit=2269
  ->  Sort  (cost=2961.88..2963.06 rows=471 width=298) (actual time=16.332..16.614 rows=3439 loops=1)
        Sort Key: n0.label COLLATE "C", e0.source_id
        Sort Method: quicksort  Memory: 1843kB
        Buffers: shared hit=2269
        ->  Hash Join  (cost=1467.74..2940.97 rows=471 width=298) (actual time=9.739..13.180 rows=3439 loops=1)
              Hash Cond: ((n0.id)::text = (e0.source_id)::text)
              Buffers: shared hit=2266
              ->  Seq Scan on entity n0  (cost=0.00..1419.74 rows=20374 width=68) (actual time=0.003..2.808 rows=20374 loops=1)
                    Buffers: shared hit=1216
              ->  Hash  (cost=1461.85..1461.85 rows=471 width=198) (actual time=5.589..5.590 rows=3439 loops=1)
                    Buckets: 4096 (originally 1024)  Batches: 1 (originally 1)  Memory Usage: 1090kB
                    Buffers: shared hit=1050
                    ->  Bitmap Heap Scan on edge e0  (cost=49.25..1461.85 rows=471 width=198) (actual time=0.653..3.786 rows=3439 loops=1)
                          Recheck Cond: (((target_id)::text = 'tcm-mkg:medicinal_property:8fa8553dc501fce26501a2aef0fa5cd798a41a126c217079d78274d05a5d5842'::text) AND ((relation)::text = 'HAS_MEDICINAL_PROPERTY'::text))
                          Heap Blocks: exact=910
                          Buffers: shared hit=1050
                          ->  Bitmap Index Scan on edge_incoming  (cost=0.00..49.13 rows=471 width=0) (actual time=0.546..0.547 rows=3439 loops=1)
                                Index Cond: (((target_id)::text = 'tcm-mkg:medicinal_property:8fa8553dc501fce26501a2aef0fa5cd798a41a126c217079d78274d05a5d5842'::text) AND ((relation)::text = 'HAS_MEDICINAL_PROPERTY'::text))
                                Buffers: shared hit=140
Planning:
  Buffers: shared hit=257
Planning Time: 0.821 ms
Execution Time: 16.896 ms
```

```sql
SELECT id,edge_id FROM evidence WHERE edge_id=ANY(ARRAY['edge:5758ab52a44d8c173e080493b6a8dfeb2f25f8babd650acfafd939e0b7628580','edge:f4ba40e29b4ced6fb706fc6f761c6e25fbbc967b9dff9791f5c045dde95b17d4','edge:edd30fbfe7b7a204faf71b22d539b43c03acbc01fe93f957de3d21fc80e40bb4','edge:d4fa575a888816bb0f0e6695892e8f3e84b5fe002881a2c91ba5fa2204ab9b46','edge:fa04fee446ea223d9336bfef46d40fa2ac484a4334b43ad805a77c09e4412181','edge:749fbe0cb5747731a6c5210591df1bc164fbd9f7ad343407a6cc4a9e3bc99a2d','edge:b0e467ce0b5453119e9f12177b6c3408c98cf6c4103e72aebdaac217b06a1457','edge:0abf22d49f02676f98eff4bc163d8a940e209cf441bbe92bca426b0fe8839cac','edge:9e024eab569535496fdda8bb0117d8426a0963b2a6319bdf1b5014c80785d2c1','edge:1733e665e8d963c5465284ff2782e894c922f8ea68088bbf738adf233b1761ea','edge:7339a4602fb852986becc06fb09872b6597e0fb39f4afd30e76f77148006537e','edge:97bb172cb31b897db8a5599f19c0f88c71b3401d728e0fe7333c3a0e241fb1eb','edge:1a686583e26a6b99d0beeb923b90c33fbc3e397475d323c65cc77a55362a9a8e','edge:b84a26deecd0f5d722952a8ca2ab8d5935c9c4c2d511d4f8d758f32b5bf1d8d4','edge:c16b46bd266fc61918af21b9b9806262ac7e594030016bb9f2b0b0babad1c102','edge:0edb70244680fb47b1ce0a6049fcf9d85b6ea59a56ceb4074f91d938edce4b3f','edge:3dafad71afdc99b96b007783dea84acfc4b903284b714e00131bb6e47144d8b0','edge:3592183b64130699526367e3eb8e64af47b6736e1570ff371513ec1daeac791e','edge:7a1a0986f735e02a25f49d6b0406fc8fbf1dbef4fa3f74c4b55865cd5a8a222a','edge:9c7174bd7bb006267150528feef95cf894e8bd6e02da52299dfa5c451a6cebdc','edge:0c6359f894e80bbff4cfc820fe9c3998e2552b91d44d29bc081756c5cb568b8c','edge:d201b58fd474b77e1fb7902af558d6cd1105f6373ffd4ff818db25a797aff3ae','edge:505d09d4a6285fece14f21efd41b3e4269c179db6f8adb9bc3f9d416b8468449','edge:d3274c966c6a852f99cd34c59eca05ca74b47c4cd9122254d3b602ff7a1141c7','edge:f1cc4222a918cba9b4596f6970448acc440f32ea1ccf429f703c91b3c12a512d','edge:734015bb87d44d71946d0a99196fc2919e18dbd00165f265f677545b3f48e7b0','edge:e17e8503e8f7d3f6f59dd73c63bd17b6f40e7046d3d6a1aa45e6c99a6abb22be','edge:bf0a872757ca4a0fd56b893763291482c80880915fb55cfb9100d7804b037b46','edge:5f739f06b42e59749e24a7e1f3ac76b94c98bf63c4925b075baf6690866da89e','edge:d8e940c05f009f9e20e44ac7c8e0eac064103b453e82713f3e5026815bf4af2d','edge:ee1ec9998c9f4b754b690ba547f5fd4f7ff00b148d8a38f7636dc2476800b6d8','edge:082c2157679d26afc44160d37c39e740a69b33e1bf9b99217db01a6bde4b509c','edge:e75c33ef6a1f53b97af06f3328751909c28a7dd413d1ebb767db4ee98bbd278c','edge:e7a20cef7e2d6c8fdd949c3f7a97c434127cb069b3987659843f1258516c950c','edge:dccc003667abeebf10a95a59d5a9902b6821db45b2c39ae26c7515966cd58129','edge:0fe45945dc88c70dd87ca0a4703927df777130ed2bd6aa0322c08571b2a37ca9','edge:6f6cd6810819e5938c29c17b0e0f3d60190275a14b0fca86b62b9328e9a09afe','edge:805a3919d88b152a306a6bad92402bf0faeac4f6a4b2a41a595010d3cd614b29','edge:08dcd5e038e366fb4048db2e12da3d7bd577255a4831f36c3150cf9718fa3319']) ORDER BY CASE kind WHEN 'source_quote' THEN 0 WHEN 'curated' THEN 1
    WHEN 'bibliographic' THEN 2 WHEN 'auto_extracted' THEN 3 WHEN 'rule_inferred' THEN 4 END,
    CASE WHEN field_path='' THEN 1 ELSE 0 END, field_path COLLATE "C", id
```

```text
Sort  (cost=332.06..332.16 rows=40 width=184) (actual time=0.501..0.503 rows=39 loops=1)
  Sort Key: (CASE kind WHEN 'source_quote'::text THEN 0 WHEN 'curated'::text THEN 1 WHEN 'bibliographic'::text THEN 2 WHEN 'auto_extracted'::text THEN 3 WHEN 'rule_inferred'::text THEN 4 ELSE NULL::integer END), (CASE WHEN (field_path = ''::text) THEN 1 ELSE 0 END), ((field_path)::text) COLLATE "C", id
  Sort Method: quicksort  Memory: 32kB
  Buffers: shared hit=173
  ->  Bitmap Heap Scan on evidence  (cost=177.75..331.00 rows=40 width=184) (actual time=0.387..0.436 rows=39 loops=1)
        Recheck Cond: ((edge_id)::text = ANY ('{edge:5758ab52a44d8c173e080493b6a8dfeb2f25f8babd650acfafd939e0b7628580,edge:f4ba40e29b4ced6fb706fc6f761c6e25fbbc967b9dff9791f5c045dde95b17d4,edge:edd30fbfe7b7a204faf71b22d539b43c03acbc01fe93f957de3d21fc80e40bb4,edge:d4fa575a888816bb0f0e6695892e8f3e84b5fe002881a2c91ba5fa2204ab9b46,edge:fa04fee446ea223d9336bfef46d40fa2ac484a4334b43ad805a77c09e4412181,edge:749fbe0cb5747731a6c5210591df1bc164fbd9f7ad343407a6cc4a9e3bc99a2d,edge:b0e467ce0b5453119e9f12177b6c3408c98cf6c4103e72aebdaac217b06a1457,edge:0abf22d49f02676f98eff4bc163d8a940e209cf441bbe92bca426b0fe8839cac,edge:9e024eab569535496fdda8bb0117d8426a0963b2a6319bdf1b5014c80785d2c1,edge:1733e665e8d963c5465284ff2782e894c922f8ea68088bbf738adf233b1761ea,edge:7339a4602fb852986becc06fb09872b6597e0fb39f4afd30e76f77148006537e,edge:97bb172cb31b897db8a5599f19c0f88c71b3401d728e0fe7333c3a0e241fb1eb,edge:1a686583e26a6b99d0beeb923b90c33fbc3e397475d323c65cc77a55362a9a8e,edge:b84a26deecd0f5d722952a8ca2ab8d5935c9c4c2d511d4f8d758f32b5bf1d8d4,edge:c16b46bd266fc61918af21b9b9806262ac7e594030016bb9f2b0b0babad1c102,edge:0edb70244680fb47b1ce0a6049fcf9d85b6ea59a56ceb4074f91d938edce4b3f,edge:3dafad71afdc99b96b007783dea84acfc4b903284b714e00131bb6e47144d8b0,edge:3592183b64130699526367e3eb8e64af47b6736e1570ff371513ec1daeac791e,edge:7a1a0986f735e02a25f49d6b0406fc8fbf1dbef4fa3f74c4b55865cd5a8a222a,edge:9c7174bd7bb006267150528feef95cf894e8bd6e02da52299dfa5c451a6cebdc,edge:0c6359f894e80bbff4cfc820fe9c3998e2552b91d44d29bc081756c5cb568b8c,edge:d201b58fd474b77e1fb7902af558d6cd1105f6373ffd4ff818db25a797aff3ae,edge:505d09d4a6285fece14f21efd41b3e4269c179db6f8adb9bc3f9d416b8468449,edge:d3274c966c6a852f99cd34c59eca05ca74b47c4cd9122254d3b602ff7a1141c7,edge:f1cc4222a918cba9b4596f6970448acc440f32ea1ccf429f703c91b3c12a512d,edge:734015bb87d44d71946d0a99196fc2919e18dbd00165f265f677545b3f48e7b0,edge:e17e8503e8f7d3f6f59dd73c63bd17b6f40e7046d3d6a1aa45e6c99a6abb22be,edge:bf0a872757ca4a0fd56b893763291482c80880915fb55cfb9100d7804b037b46,edge:5f739f06b42e59749e24a7e1f3ac76b94c98bf63c4925b075baf6690866da89e,edge:d8e940c05f009f9e20e44ac7c8e0eac064103b453e82713f3e5026815bf4af2d,edge:ee1ec9998c9f4b754b690ba547f5fd4f7ff00b148d8a38f7636dc2476800b6d8,edge:082c2157679d26afc44160d37c39e740a69b33e1bf9b99217db01a6bde4b509c,edge:e75c33ef6a1f53b97af06f3328751909c28a7dd413d1ebb767db4ee98bbd278c,edge:e7a20cef7e2d6c8fdd949c3f7a97c434127cb069b3987659843f1258516c950c,edge:dccc003667abeebf10a95a59d5a9902b6821db45b2c39ae26c7515966cd58129,edge:0fe45945dc88c70dd87ca0a4703927df777130ed2bd6aa0322c08571b2a37ca9,edge:6f6cd6810819e5938c29c17b0e0f3d60190275a14b0fca86b62b9328e9a09afe,edge:805a3919d88b152a306a6bad92402bf0faeac4f6a4b2a41a595010d3cd614b29,edge:08dcd5e038e366fb4048db2e12da3d7bd577255a4831f36c3150cf9718fa3319}'::text[]))
        Heap Blocks: exact=11
        Buffers: shared hit=167
        ->  Bitmap Index Scan on evidence_edge  (cost=0.00..177.64 rows=40 width=0) (actual time=0.373..0.373 rows=39 loops=1)
              Index Cond: ((edge_id)::text = ANY ('{edge:5758ab52a44d8c173e080493b6a8dfeb2f25f8babd650acfafd939e0b7628580,edge:f4ba40e29b4ced6fb706fc6f761c6e25fbbc967b9dff9791f5c045dde95b17d4,edge:edd30fbfe7b7a204faf71b22d539b43c03acbc01fe93f957de3d21fc80e40bb4,edge:d4fa575a888816bb0f0e6695892e8f3e84b5fe002881a2c91ba5fa2204ab9b46,edge:fa04fee446ea223d9336bfef46d40fa2ac484a4334b43ad805a77c09e4412181,edge:749fbe0cb5747731a6c5210591df1bc164fbd9f7ad343407a6cc4a9e3bc99a2d,edge:b0e467ce0b5453119e9f12177b6c3408c98cf6c4103e72aebdaac217b06a1457,edge:0abf22d49f02676f98eff4bc163d8a940e209cf441bbe92bca426b0fe8839cac,edge:9e024eab569535496fdda8bb0117d8426a0963b2a6319bdf1b5014c80785d2c1,edge:1733e665e8d963c5465284ff2782e894c922f8ea68088bbf738adf233b1761ea,edge:7339a4602fb852986becc06fb09872b6597e0fb39f4afd30e76f77148006537e,edge:97bb172cb31b897db8a5599f19c0f88c71b3401d728e0fe7333c3a0e241fb1eb,edge:1a686583e26a6b99d0beeb923b90c33fbc3e397475d323c65cc77a55362a9a8e,edge:b84a26deecd0f5d722952a8ca2ab8d5935c9c4c2d511d4f8d758f32b5bf1d8d4,edge:c16b46bd266fc61918af21b9b9806262ac7e594030016bb9f2b0b0babad1c102,edge:0edb70244680fb47b1ce0a6049fcf9d85b6ea59a56ceb4074f91d938edce4b3f,edge:3dafad71afdc99b96b007783dea84acfc4b903284b714e00131bb6e47144d8b0,edge:3592183b64130699526367e3eb8e64af47b6736e1570ff371513ec1daeac791e,edge:7a1a0986f735e02a25f49d6b0406fc8fbf1dbef4fa3f74c4b55865cd5a8a222a,edge:9c7174bd7bb006267150528feef95cf894e8bd6e02da52299dfa5c451a6cebdc,edge:0c6359f894e80bbff4cfc820fe9c3998e2552b91d44d29bc081756c5cb568b8c,edge:d201b58fd474b77e1fb7902af558d6cd1105f6373ffd4ff818db25a797aff3ae,edge:505d09d4a6285fece14f21efd41b3e4269c179db6f8adb9bc3f9d416b8468449,edge:d3274c966c6a852f99cd34c59eca05ca74b47c4cd9122254d3b602ff7a1141c7,edge:f1cc4222a918cba9b4596f6970448acc440f32ea1ccf429f703c91b3c12a512d,edge:734015bb87d44d71946d0a99196fc2919e18dbd00165f265f677545b3f48e7b0,edge:e17e8503e8f7d3f6f59dd73c63bd17b6f40e7046d3d6a1aa45e6c99a6abb22be,edge:bf0a872757ca4a0fd56b893763291482c80880915fb55cfb9100d7804b037b46,edge:5f739f06b42e59749e24a7e1f3ac76b94c98bf63c4925b075baf6690866da89e,edge:d8e940c05f009f9e20e44ac7c8e0eac064103b453e82713f3e5026815bf4af2d,edge:ee1ec9998c9f4b754b690ba547f5fd4f7ff00b148d8a38f7636dc2476800b6d8,edge:082c2157679d26afc44160d37c39e740a69b33e1bf9b99217db01a6bde4b509c,edge:e75c33ef6a1f53b97af06f3328751909c28a7dd413d1ebb767db4ee98bbd278c,edge:e7a20cef7e2d6c8fdd949c3f7a97c434127cb069b3987659843f1258516c950c,edge:dccc003667abeebf10a95a59d5a9902b6821db45b2c39ae26c7515966cd58129,edge:0fe45945dc88c70dd87ca0a4703927df777130ed2bd6aa0322c08571b2a37ca9,edge:6f6cd6810819e5938c29c17b0e0f3d60190275a14b0fca86b62b9328e9a09afe,edge:805a3919d88b152a306a6bad92402bf0faeac4f6a4b2a41a595010d3cd614b29,edge:08dcd5e038e366fb4048db2e12da3d7bd577255a4831f36c3150cf9718fa3319}'::text[]))
              Buffers: shared hit=156
Planning:
  Buffers: shared hit=118
Planning Time: 0.580 ms
Execution Time: 0.554 ms
```

## formula_patterns S3

```sql
SELECT count(*) AS total FROM edge e0 JOIN entity n0 ON n0.id=e0.target_id WHERE e0.source_id='bencaodian:formula:zhu_ling_tang' AND e0.relation='ASSOCIATED_WITH_PATTERN'
```

```text
Aggregate  (cost=16.87..16.88 rows=1 width=8) (actual time=0.039..0.040 rows=1 loops=1)
  Buffers: shared hit=14
  ->  Nested Loop  (cost=0.83..16.87 rows=1 width=0) (actual time=0.031..0.038 rows=3 loops=1)
        Buffers: shared hit=14
        ->  Index Only Scan using edge_outgoing on edge e0  (cost=0.42..8.44 rows=1 width=36) (actual time=0.018..0.019 rows=3 loops=1)
              Index Cond: ((source_id = 'bencaodian:formula:zhu_ling_tang'::text) AND (relation = 'ASSOCIATED_WITH_PATTERN'::text))
              Heap Fetches: 0
              Buffers: shared hit=4
        ->  Index Only Scan using entity_pkey on entity n0  (cost=0.41..8.43 rows=1 width=30) (actual time=0.005..0.005 rows=1 loops=3)
              Index Cond: (id = (e0.target_id)::text)
              Heap Fetches: 0
              Buffers: shared hit=10
Planning:
  Buffers: shared hit=325
Planning Time: 0.781 ms
Execution Time: 0.103 ms
```

```sql
SELECT e0.id AS e0_id, e0.source_id AS e0_source_id, e0.target_id AS e0_target_id, e0.relation AS e0_relation, e0.properties_json AS e0_properties_json, e0.quality_state AS e0_quality_state, n0.id AS n0_id, n0.label AS n0_label, n0.type AS n0_type, n0.category AS n0_category FROM edge e0 JOIN entity n0 ON n0.id=e0.target_id WHERE e0.source_id='bencaodian:formula:zhu_ling_tang' AND e0.relation='ASSOCIATED_WITH_PATTERN' ORDER BY n0.label COLLATE "C", n0.id LIMIT 20 OFFSET 0
```

```text
Limit  (cost=16.88..16.89 rows=1 width=298) (actual time=0.104..0.105 rows=3 loops=1)
  Buffers: shared hit=19
  ->  Sort  (cost=16.88..16.89 rows=1 width=298) (actual time=0.103..0.104 rows=3 loops=1)
        Sort Key: n0.label COLLATE "C", e0.target_id
        Sort Method: quicksort  Memory: 26kB
        Buffers: shared hit=19
        ->  Nested Loop  (cost=0.83..16.87 rows=1 width=298) (actual time=0.036..0.045 rows=3 loops=1)
              Buffers: shared hit=16
              ->  Index Scan using edge_outgoing on edge e0  (cost=0.42..8.44 rows=1 width=198) (actual time=0.017..0.018 rows=3 loops=1)
                    Index Cond: (((source_id)::text = 'bencaodian:formula:zhu_ling_tang'::text) AND ((relation)::text = 'ASSOCIATED_WITH_PATTERN'::text))
                    Buffers: shared hit=4
              ->  Index Scan using entity_pkey on entity n0  (cost=0.41..8.43 rows=1 width=68) (actual time=0.007..0.007 rows=1 loops=3)
                    Index Cond: ((id)::text = (e0.target_id)::text)
                    Buffers: shared hit=12
Planning:
  Buffers: shared hit=261
Planning Time: 0.723 ms
Execution Time: 0.147 ms
```

```sql
SELECT id,edge_id FROM evidence WHERE edge_id=ANY(ARRAY['edge:1b48fbb34295647d6e91fa8cdf589f380a57c51953eb2b1ef1801febfe94d7cc','edge:cd305fbd9b53680cd9c110289e0cddf645ae8c131ff3cc1602bd512437766cc1','edge:c554175120ae9ccff177edd4bf706a0eebb5663fcee3ed2197eb5a5d55ddca02']) ORDER BY CASE kind WHEN 'source_quote' THEN 0 WHEN 'curated' THEN 1
    WHEN 'bibliographic' THEN 2 WHEN 'auto_extracted' THEN 3 WHEN 'rule_inferred' THEN 4 END,
    CASE WHEN field_path='' THEN 1 ELSE 0 END, field_path COLLATE "C", id
```

```text
Sort  (cost=25.76..25.77 rows=3 width=184) (actual time=0.091..0.091 rows=3 loops=1)
  Sort Key: (CASE kind WHEN 'source_quote'::text THEN 0 WHEN 'curated'::text THEN 1 WHEN 'bibliographic'::text THEN 2 WHEN 'auto_extracted'::text THEN 3 WHEN 'rule_inferred'::text THEN 4 ELSE NULL::integer END), (CASE WHEN (field_path = ''::text) THEN 1 ELSE 0 END), ((field_path)::text) COLLATE "C", id
  Sort Method: quicksort  Memory: 25kB
  Buffers: shared hit=22
  ->  Index Scan using evidence_edge on evidence  (cost=0.55..25.74 rows=3 width=184) (actual time=0.044..0.070 rows=3 loops=1)
        Index Cond: ((edge_id)::text = ANY ('{edge:1b48fbb34295647d6e91fa8cdf589f380a57c51953eb2b1ef1801febfe94d7cc,edge:cd305fbd9b53680cd9c110289e0cddf645ae8c131ff3cc1602bd512437766cc1,edge:c554175120ae9ccff177edd4bf706a0eebb5663fcee3ed2197eb5a5d55ddca02}'::text[]))
        Buffers: shared hit=16
Planning:
  Buffers: shared hit=115
Planning Time: 0.311 ms
Execution Time: 0.108 ms
```

## herb_patterns_via_formula 甘草

```sql
SELECT count(*) AS total FROM edge e0 JOIN entity n0 ON n0.id=e0.source_id JOIN edge e1 ON e1.source_id=n0.id AND e1.relation='ASSOCIATED_WITH_PATTERN' JOIN entity n1 ON n1.id=e1.target_id WHERE e0.target_id='bencaodian:herb:gan_cao' AND e0.relation='CONTAINS'
```

```text
Aggregate  (cost=21.71..21.72 rows=1 width=8) (actual time=0.380..0.381 rows=1 loops=1)
  Buffers: shared hit=530
  ->  Nested Loop  (cost=1.67..21.71 rows=1 width=0) (actual time=0.050..0.375 rows=52 loops=1)
        Buffers: shared hit=530
        ->  Nested Loop  (cost=1.25..17.83 rows=1 width=36) (actual time=0.038..0.286 rows=52 loops=1)
              Buffers: shared hit=373
              ->  Nested Loop  (cost=0.83..16.87 rows=1 width=62) (actual time=0.027..0.128 rows=61 loops=1)
                    Buffers: shared hit=189
                    ->  Index Only Scan using edge_incoming on edge e0  (cost=0.42..8.44 rows=1 width=32) (actual time=0.018..0.027 rows=61 loops=1)
                          Index Cond: ((target_id = 'bencaodian:herb:gan_cao'::text) AND (relation = 'CONTAINS'::text))
                          Heap Fetches: 0
                          Buffers: shared hit=5
                    ->  Index Only Scan using entity_pkey on entity n0  (cost=0.41..8.43 rows=1 width=30) (actual time=0.001..0.001 rows=1 loops=61)
                          Index Cond: (id = (e0.source_id)::text)
                          Heap Fetches: 0
                          Buffers: shared hit=184
              ->  Index Only Scan using edge_outgoing on edge e1  (cost=0.42..0.95 rows=1 width=68) (actual time=0.002..0.002 rows=1 loops=61)
                    Index Cond: ((source_id = (n0.id)::text) AND (relation = 'ASSOCIATED_WITH_PATTERN'::text))
                    Heap Fetches: 0
                    Buffers: shared hit=184
        ->  Index Only Scan using entity_pkey on entity n1  (cost=0.41..3.87 rows=1 width=30) (actual time=0.001..0.001 rows=1 loops=52)
              Index Cond: (id = (e1.target_id)::text)
              Heap Fetches: 0
              Buffers: shared hit=157
Planning:
  Buffers: shared hit=365
Planning Time: 1.423 ms
Execution Time: 0.439 ms
```

```sql
SELECT e0.id AS e0_id, e0.source_id AS e0_source_id, e0.target_id AS e0_target_id, e0.relation AS e0_relation, e0.properties_json AS e0_properties_json, e0.quality_state AS e0_quality_state, n0.id AS n0_id, n0.label AS n0_label, n0.type AS n0_type, n0.category AS n0_category, e1.id AS e1_id, e1.source_id AS e1_source_id, e1.target_id AS e1_target_id, e1.relation AS e1_relation, e1.properties_json AS e1_properties_json, e1.quality_state AS e1_quality_state, n1.id AS n1_id, n1.label AS n1_label, n1.type AS n1_type, n1.category AS n1_category FROM edge e0 JOIN entity n0 ON n0.id=e0.source_id JOIN edge e1 ON e1.source_id=n0.id AND e1.relation='ASSOCIATED_WITH_PATTERN' JOIN entity n1 ON n1.id=e1.target_id WHERE e0.target_id='bencaodian:herb:gan_cao' AND e0.relation='CONTAINS' ORDER BY n1.label COLLATE "C", n0.label COLLATE "C", n1.id, n0.id LIMIT 20 OFFSET 0
```

```text
Limit  (cost=26.36..26.36 rows=1 width=596) (actual time=0.645..0.649 rows=20 loops=1)
  Buffers: shared hit=706
  ->  Sort  (cost=26.36..26.36 rows=1 width=596) (actual time=0.644..0.646 rows=20 loops=1)
        Sort Key: n1.label COLLATE "C", n0.label COLLATE "C", e1.target_id, e0.source_id
        Sort Method: top-N heapsort  Memory: 59kB
        Buffers: shared hit=706
        ->  Nested Loop  (cost=1.67..26.35 rows=1 width=596) (actual time=0.055..0.540 rows=52 loops=1)
              Buffers: shared hit=703
              ->  Nested Loop  (cost=1.25..18.85 rows=1 width=464) (actual time=0.039..0.422 rows=52 loops=1)
                    Buffers: shared hit=495
                    ->  Nested Loop  (cost=0.83..16.87 rows=1 width=266) (actual time=0.031..0.224 rows=61 loops=1)
                          Buffers: shared hit=279
                          ->  Index Scan using edge_incoming on edge e0  (cost=0.42..8.44 rows=1 width=198) (actual time=0.016..0.059 rows=61 loops=1)
                                Index Cond: (((target_id)::text = 'bencaodian:herb:gan_cao'::text) AND ((relation)::text = 'CONTAINS'::text))
                                Buffers: shared hit=35
                          ->  Index Scan using entity_pkey on entity n0  (cost=0.41..8.43 rows=1 width=68) (actual time=0.002..0.002 rows=1 loops=61)
                                Index Cond: ((id)::text = (e0.source_id)::text)
                                Buffers: shared hit=244
                    ->  Index Scan using edge_outgoing on edge e1  (cost=0.42..1.96 rows=1 width=198) (actual time=0.003..0.003 rows=1 loops=61)
                          Index Cond: (((source_id)::text = (n0.id)::text) AND ((relation)::text = 'ASSOCIATED_WITH_PATTERN'::text))
                          Buffers: shared hit=216
              ->  Index Scan using entity_pkey on entity n1  (cost=0.41..7.50 rows=1 width=68) (actual time=0.002..0.002 rows=1 loops=52)
                    Index Cond: ((id)::text = (e1.target_id)::text)
                    Buffers: shared hit=208
Planning:
  Buffers: shared hit=301
Planning Time: 1.330 ms
Execution Time: 0.722 ms
```

```sql
SELECT id,edge_id FROM evidence WHERE edge_id=ANY(ARRAY['edge:daa9497be242ef274bfed1113ab957821e61fbb30127cacea2ebaeb7313ffd83','edge:c860ad8e4cbef7041dac32e7691ccff0e81256d5c2122bd166ce2f81f520750b','edge:f8ad527a77743dd2454e21cd98ad10ed02ed07449b2a49909d6ba2551c0804d0','edge:e15c2ae7401de68f88d2da24f5188586c9f94dc42eaf036eb0e5ed7188d6d20d','edge:0747b408016964dc3fc67ce27ecdbf215da4e934033942aa6af2cf36dc492002','edge:d554c783e5abeccc50697779eb1ebf405edb59a65185842d29df1b5aa180d0ab','edge:ff0a2671a8840cdf86af8b6422f7d8330ec208edb91079ffa0f454191c3e91af','edge:7c6c870f0ca00d0cd8ad3526695e355540f9678d1ae539d853fe616bb29e5953','edge:d5ed5cf23a6fbf04d34ae6a845778c9b97700d0edf885b25c542f4aa0b1ac2de','edge:ca94fd9705fea60dd384f89641a3b826cfe12767010d07b2552423efd5f3f227','edge:71f43e014f3e3adbe2e7ae8c4984fe9b89e37d5f70f96e48904974d32de05ea1','edge:670532d4af682127ab9f96fe55d1357b677281c3d27b94d25575db767db20974','edge:7829e36ae995fcf07e1c82f3c02a541b40c65c573f49e2e4ce7839f5ceb66deb','edge:6c1a4f4ad1ad2ff69024b67081f0d2e501575c706d9e8ce524b76720a5ad1218','edge:f917f460fda1f5dbffed621dc4155e6f2b22a946e9fbd6aa87455dd0f7c55b8c','edge:18d8dbc22beaf2ea441a452eef8671ff86fe8c8e862a3071dc72e4c586b7c9be','edge:6686742c39d777b1200ebbf54e964ec7ec019b79e548a4daee62ca1ac603943c','edge:eb8b79ec77b08a6fb9c0908ed8b52db28b7e2e76e3f754dd7fd14fa81490c8a1','edge:ea12bd2aaa66fccea1743b53e930acbcdd85de7a9cea7a02acdb015d50a4320b','edge:7fe4b743e808549805e4183ad654bd25ce1224e333056618fa5508105d3326f6','edge:a05dec9b6b22023148ac3cc89c65831d6d9d71e46240f141b85c730ba56b4a92','edge:3b303f17e854305ca02f753f7a5f4608c1ee00052256af9f0c3ef11613e7a907','edge:ea0571d2c6ea9844eb98c1bfeddd300cc7a593401dc3cdf3a768c04938042181','edge:343d1d6b98da35c1216f3de611e5f656e2c5bade81c1be68b44630c56d84636b','edge:cc1c194311bae2d1a8040df0d6ffd561ab16c4aee2e3c75186825379b0976191','edge:d0e1e840b6f3877208c57512339370bfeae66fb80d10e967aca726c6ef3f1300','edge:00d8cae763189209ee30ec5252639ec3b2cee63ee39e2ffccbd02065d2749bcf','edge:ef3987d532b35c11af647a2c9086497983bb35e295891e5e88a9778d0d4903c4','edge:0de3f3f21bf81f61f833c18f0de1e3e4c571b25a6ddc2fe1002ec2b67fb31bfb','edge:2adfe1257aa9eb35b58f0830cecac8c1dfd8346cfd17c5d6ba4d72414e5e917c','edge:e11e34e173e47b90e256a70af6343acf124e97f5d8164f74168982068cccec65','edge:8899714a0ff16dcea53ff7a985b356d0cda35a0fe822cf4d90abbe84f7222b0b','edge:40f0a92aedf96d3df23a15c943b40a17d43e5f383fcdf7ebcffc6fcfd435bc69','edge:2f1a89aa2d0a92e1a5f36ba87f8435d229000795e71d32eb791f2adad06e4d15','edge:303a4279f9ead76ee275685c6406b8934de653493bd17f44fa21259a0174db75','edge:21d12263441be415a80a4de18f9ad5e0643e92bf959919d505cd5f359fa8a8e5','edge:edbf5e65f79cf4630e844579a54d8bdfb433579cd02810a978ee68873efe37dd']) ORDER BY CASE kind WHEN 'source_quote' THEN 0 WHEN 'curated' THEN 1
    WHEN 'bibliographic' THEN 2 WHEN 'auto_extracted' THEN 3 WHEN 'rule_inferred' THEN 4 END,
    CASE WHEN field_path='' THEN 1 ELSE 0 END, field_path COLLATE "C", id
```

```text
Sort  (cost=315.41..315.50 rows=38 width=184) (actual time=0.499..0.502 rows=54 loops=1)
  Sort Key: (CASE kind WHEN 'source_quote'::text THEN 0 WHEN 'curated'::text THEN 1 WHEN 'bibliographic'::text THEN 2 WHEN 'auto_extracted'::text THEN 3 WHEN 'rule_inferred'::text THEN 4 ELSE NULL::integer END), (CASE WHEN (field_path = ''::text) THEN 1 ELSE 0 END), ((field_path)::text) COLLATE "C", id
  Sort Method: quicksort  Memory: 34kB
  Buffers: shared hit=174
  ->  Bitmap Heap Scan on evidence  (cost=168.64..314.41 rows=38 width=184) (actual time=0.361..0.422 rows=54 loops=1)
        Recheck Cond: ((edge_id)::text = ANY ('{edge:daa9497be242ef274bfed1113ab957821e61fbb30127cacea2ebaeb7313ffd83,edge:c860ad8e4cbef7041dac32e7691ccff0e81256d5c2122bd166ce2f81f520750b,edge:f8ad527a77743dd2454e21cd98ad10ed02ed07449b2a49909d6ba2551c0804d0,edge:e15c2ae7401de68f88d2da24f5188586c9f94dc42eaf036eb0e5ed7188d6d20d,edge:0747b408016964dc3fc67ce27ecdbf215da4e934033942aa6af2cf36dc492002,edge:d554c783e5abeccc50697779eb1ebf405edb59a65185842d29df1b5aa180d0ab,edge:ff0a2671a8840cdf86af8b6422f7d8330ec208edb91079ffa0f454191c3e91af,edge:7c6c870f0ca00d0cd8ad3526695e355540f9678d1ae539d853fe616bb29e5953,edge:d5ed5cf23a6fbf04d34ae6a845778c9b97700d0edf885b25c542f4aa0b1ac2de,edge:ca94fd9705fea60dd384f89641a3b826cfe12767010d07b2552423efd5f3f227,edge:71f43e014f3e3adbe2e7ae8c4984fe9b89e37d5f70f96e48904974d32de05ea1,edge:670532d4af682127ab9f96fe55d1357b677281c3d27b94d25575db767db20974,edge:7829e36ae995fcf07e1c82f3c02a541b40c65c573f49e2e4ce7839f5ceb66deb,edge:6c1a4f4ad1ad2ff69024b67081f0d2e501575c706d9e8ce524b76720a5ad1218,edge:f917f460fda1f5dbffed621dc4155e6f2b22a946e9fbd6aa87455dd0f7c55b8c,edge:18d8dbc22beaf2ea441a452eef8671ff86fe8c8e862a3071dc72e4c586b7c9be,edge:6686742c39d777b1200ebbf54e964ec7ec019b79e548a4daee62ca1ac603943c,edge:eb8b79ec77b08a6fb9c0908ed8b52db28b7e2e76e3f754dd7fd14fa81490c8a1,edge:ea12bd2aaa66fccea1743b53e930acbcdd85de7a9cea7a02acdb015d50a4320b,edge:7fe4b743e808549805e4183ad654bd25ce1224e333056618fa5508105d3326f6,edge:a05dec9b6b22023148ac3cc89c65831d6d9d71e46240f141b85c730ba56b4a92,edge:3b303f17e854305ca02f753f7a5f4608c1ee00052256af9f0c3ef11613e7a907,edge:ea0571d2c6ea9844eb98c1bfeddd300cc7a593401dc3cdf3a768c04938042181,edge:343d1d6b98da35c1216f3de611e5f656e2c5bade81c1be68b44630c56d84636b,edge:cc1c194311bae2d1a8040df0d6ffd561ab16c4aee2e3c75186825379b0976191,edge:d0e1e840b6f3877208c57512339370bfeae66fb80d10e967aca726c6ef3f1300,edge:00d8cae763189209ee30ec5252639ec3b2cee63ee39e2ffccbd02065d2749bcf,edge:ef3987d532b35c11af647a2c9086497983bb35e295891e5e88a9778d0d4903c4,edge:0de3f3f21bf81f61f833c18f0de1e3e4c571b25a6ddc2fe1002ec2b67fb31bfb,edge:2adfe1257aa9eb35b58f0830cecac8c1dfd8346cfd17c5d6ba4d72414e5e917c,edge:e11e34e173e47b90e256a70af6343acf124e97f5d8164f74168982068cccec65,edge:8899714a0ff16dcea53ff7a985b356d0cda35a0fe822cf4d90abbe84f7222b0b,edge:40f0a92aedf96d3df23a15c943b40a17d43e5f383fcdf7ebcffc6fcfd435bc69,edge:2f1a89aa2d0a92e1a5f36ba87f8435d229000795e71d32eb791f2adad06e4d15,edge:303a4279f9ead76ee275685c6406b8934de653493bd17f44fa21259a0174db75,edge:21d12263441be415a80a4de18f9ad5e0643e92bf959919d505cd5f359fa8a8e5,edge:edbf5e65f79cf4630e844579a54d8bdfb433579cd02810a978ee68873efe37dd}'::text[]))
        Heap Blocks: exact=20
        Buffers: shared hit=168
        ->  Bitmap Index Scan on evidence_edge  (cost=0.00..168.53 rows=38 width=0) (actual time=0.349..0.349 rows=54 loops=1)
              Index Cond: ((edge_id)::text = ANY ('{edge:daa9497be242ef274bfed1113ab957821e61fbb30127cacea2ebaeb7313ffd83,edge:c860ad8e4cbef7041dac32e7691ccff0e81256d5c2122bd166ce2f81f520750b,edge:f8ad527a77743dd2454e21cd98ad10ed02ed07449b2a49909d6ba2551c0804d0,edge:e15c2ae7401de68f88d2da24f5188586c9f94dc42eaf036eb0e5ed7188d6d20d,edge:0747b408016964dc3fc67ce27ecdbf215da4e934033942aa6af2cf36dc492002,edge:d554c783e5abeccc50697779eb1ebf405edb59a65185842d29df1b5aa180d0ab,edge:ff0a2671a8840cdf86af8b6422f7d8330ec208edb91079ffa0f454191c3e91af,edge:7c6c870f0ca00d0cd8ad3526695e355540f9678d1ae539d853fe616bb29e5953,edge:d5ed5cf23a6fbf04d34ae6a845778c9b97700d0edf885b25c542f4aa0b1ac2de,edge:ca94fd9705fea60dd384f89641a3b826cfe12767010d07b2552423efd5f3f227,edge:71f43e014f3e3adbe2e7ae8c4984fe9b89e37d5f70f96e48904974d32de05ea1,edge:670532d4af682127ab9f96fe55d1357b677281c3d27b94d25575db767db20974,edge:7829e36ae995fcf07e1c82f3c02a541b40c65c573f49e2e4ce7839f5ceb66deb,edge:6c1a4f4ad1ad2ff69024b67081f0d2e501575c706d9e8ce524b76720a5ad1218,edge:f917f460fda1f5dbffed621dc4155e6f2b22a946e9fbd6aa87455dd0f7c55b8c,edge:18d8dbc22beaf2ea441a452eef8671ff86fe8c8e862a3071dc72e4c586b7c9be,edge:6686742c39d777b1200ebbf54e964ec7ec019b79e548a4daee62ca1ac603943c,edge:eb8b79ec77b08a6fb9c0908ed8b52db28b7e2e76e3f754dd7fd14fa81490c8a1,edge:ea12bd2aaa66fccea1743b53e930acbcdd85de7a9cea7a02acdb015d50a4320b,edge:7fe4b743e808549805e4183ad654bd25ce1224e333056618fa5508105d3326f6,edge:a05dec9b6b22023148ac3cc89c65831d6d9d71e46240f141b85c730ba56b4a92,edge:3b303f17e854305ca02f753f7a5f4608c1ee00052256af9f0c3ef11613e7a907,edge:ea0571d2c6ea9844eb98c1bfeddd300cc7a593401dc3cdf3a768c04938042181,edge:343d1d6b98da35c1216f3de611e5f656e2c5bade81c1be68b44630c56d84636b,edge:cc1c194311bae2d1a8040df0d6ffd561ab16c4aee2e3c75186825379b0976191,edge:d0e1e840b6f3877208c57512339370bfeae66fb80d10e967aca726c6ef3f1300,edge:00d8cae763189209ee30ec5252639ec3b2cee63ee39e2ffccbd02065d2749bcf,edge:ef3987d532b35c11af647a2c9086497983bb35e295891e5e88a9778d0d4903c4,edge:0de3f3f21bf81f61f833c18f0de1e3e4c571b25a6ddc2fe1002ec2b67fb31bfb,edge:2adfe1257aa9eb35b58f0830cecac8c1dfd8346cfd17c5d6ba4d72414e5e917c,edge:e11e34e173e47b90e256a70af6343acf124e97f5d8164f74168982068cccec65,edge:8899714a0ff16dcea53ff7a985b356d0cda35a0fe822cf4d90abbe84f7222b0b,edge:40f0a92aedf96d3df23a15c943b40a17d43e5f383fcdf7ebcffc6fcfd435bc69,edge:2f1a89aa2d0a92e1a5f36ba87f8435d229000795e71d32eb791f2adad06e4d15,edge:303a4279f9ead76ee275685c6406b8934de653493bd17f44fa21259a0174db75,edge:21d12263441be415a80a4de18f9ad5e0643e92bf959919d505cd5f359fa8a8e5,edge:edbf5e65f79cf4630e844579a54d8bdfb433579cd02810a978ee68873efe37dd}'::text[]))
              Buffers: shared hit=148
Planning:
  Buffers: shared hit=118
Planning Time: 0.318 ms
Execution Time: 0.543 ms
```

## patent_medicine_pieces

```sql
SELECT count(*) AS total FROM edge e0 JOIN entity n0 ON n0.id=e0.target_id WHERE e0.source_id='tcm-mkg:patent_medicine:CPM00001' AND e0.relation='HAS_HERBAL_PIECE'
```

```text
Aggregate  (cost=39.14..39.15 rows=1 width=8) (actual time=0.081..0.082 rows=1 loops=1)
  Buffers: shared hit=32
  ->  Nested Loop  (cost=0.83..39.12 rows=6 width=0) (actual time=0.032..0.079 rows=9 loops=1)
        Buffers: shared hit=32
        ->  Index Only Scan using edge_outgoing on edge e0  (cost=0.42..8.54 rows=6 width=36) (actual time=0.016..0.017 rows=9 loops=1)
              Index Cond: ((source_id = 'tcm-mkg:patent_medicine:CPM00001'::text) AND (relation = 'HAS_HERBAL_PIECE'::text))
              Heap Fetches: 0
              Buffers: shared hit=4
        ->  Index Only Scan using entity_pkey on entity n0  (cost=0.41..5.10 rows=1 width=30) (actual time=0.006..0.006 rows=1 loops=9)
              Index Cond: (id = (e0.target_id)::text)
              Heap Fetches: 0
              Buffers: shared hit=28
Planning:
  Buffers: shared hit=325
Planning Time: 0.763 ms
Execution Time: 0.109 ms
```

```sql
SELECT e0.id AS e0_id, e0.source_id AS e0_source_id, e0.target_id AS e0_target_id, e0.relation AS e0_relation, e0.properties_json AS e0_properties_json, e0.quality_state AS e0_quality_state, n0.id AS n0_id, n0.label AS n0_label, n0.type AS n0_type, n0.category AS n0_category FROM edge e0 JOIN entity n0 ON n0.id=e0.target_id WHERE e0.source_id='tcm-mkg:patent_medicine:CPM00001' AND e0.relation='HAS_HERBAL_PIECE' ORDER BY n0.label COLLATE "C", n0.id LIMIT 20 OFFSET 0
```

```text
Limit  (cost=67.95..67.96 rows=6 width=298) (actual time=0.174..0.176 rows=9 loops=1)
  Buffers: shared hit=43
  ->  Sort  (cost=67.95..67.96 rows=6 width=298) (actual time=0.174..0.175 rows=9 loops=1)
        Sort Key: n0.label COLLATE "C", e0.target_id
        Sort Method: quicksort  Memory: 29kB
        Buffers: shared hit=43
        ->  Nested Loop  (cost=0.83..67.87 rows=6 width=298) (actual time=0.067..0.140 rows=9 loops=1)
              Buffers: shared hit=40
              ->  Index Scan using edge_outgoing on edge e0  (cost=0.42..17.29 rows=6 width=198) (actual time=0.020..0.022 rows=9 loops=1)
                    Index Cond: (((source_id)::text = 'tcm-mkg:patent_medicine:CPM00001'::text) AND ((relation)::text = 'HAS_HERBAL_PIECE'::text))
                    Buffers: shared hit=4
              ->  Index Scan using entity_pkey on entity n0  (cost=0.41..8.43 rows=1 width=68) (actual time=0.012..0.012 rows=1 loops=9)
                    Index Cond: ((id)::text = (e0.target_id)::text)
                    Buffers: shared hit=36
Planning:
  Buffers: shared hit=261
Planning Time: 0.662 ms
Execution Time: 0.207 ms
```

```sql
SELECT id,edge_id FROM evidence WHERE edge_id=ANY(ARRAY['edge:a6c62bdc86918a30f23c50513cdb506df90be784178a240a2b7851214680dd3c','edge:e162df19860a1ad0a752c62601d3cbd49565cc27c2cee74ac3848c3398d03769','edge:c3971f263ea9402c04b778af9a34a04881ace4523dddfcce11aaa02531be9c20','edge:8b277d391222223061ffd4ecf1ae95d146bd68a076fdc50699a0394dea98407f','edge:9381627b7e189fd9e6addab77aa06c1916b276223ac708532ce8de2b7785a3e0','edge:f4eb57b153c8b21f9ba370a2e564be533425833b5ce8c078c3f7deefa88f6cd4','edge:8b994b35df7e35489fb5633bcb2a58f85f2d3ea1e02049cbacda76afc4faef87','edge:c8e8c5b9190aacbebea27e98b47ca477b4dd61ccda42fe36a977f2a13b800d00','edge:8ae330d60d993d605f08c507412c3c1c6041e0af87096bc3c10e25f3b289a39d']) ORDER BY CASE kind WHEN 'source_quote' THEN 0 WHEN 'curated' THEN 1
    WHEN 'bibliographic' THEN 2 WHEN 'auto_extracted' THEN 3 WHEN 'rule_inferred' THEN 4 END,
    CASE WHEN field_path='' THEN 1 ELSE 0 END, field_path COLLATE "C", id
```

```text
Sort  (cost=76.58..76.61 rows=9 width=184) (actual time=0.139..0.140 rows=9 loops=1)
  Sort Key: (CASE kind WHEN 'source_quote'::text THEN 0 WHEN 'curated'::text THEN 1 WHEN 'bibliographic'::text THEN 2 WHEN 'auto_extracted'::text THEN 3 WHEN 'rule_inferred'::text THEN 4 ELSE NULL::integer END), (CASE WHEN (field_path = ''::text) THEN 1 ELSE 0 END), ((field_path)::text) COLLATE "C", id
  Sort Method: quicksort  Memory: 26kB
  Buffers: shared hit=43
  ->  Bitmap Heap Scan on evidence  (cost=41.02..76.44 rows=9 width=184) (actual time=0.096..0.099 rows=9 loops=1)
        Recheck Cond: ((edge_id)::text = ANY ('{edge:a6c62bdc86918a30f23c50513cdb506df90be784178a240a2b7851214680dd3c,edge:e162df19860a1ad0a752c62601d3cbd49565cc27c2cee74ac3848c3398d03769,edge:c3971f263ea9402c04b778af9a34a04881ace4523dddfcce11aaa02531be9c20,edge:8b277d391222223061ffd4ecf1ae95d146bd68a076fdc50699a0394dea98407f,edge:9381627b7e189fd9e6addab77aa06c1916b276223ac708532ce8de2b7785a3e0,edge:f4eb57b153c8b21f9ba370a2e564be533425833b5ce8c078c3f7deefa88f6cd4,edge:8b994b35df7e35489fb5633bcb2a58f85f2d3ea1e02049cbacda76afc4faef87,edge:c8e8c5b9190aacbebea27e98b47ca477b4dd61ccda42fe36a977f2a13b800d00,edge:8ae330d60d993d605f08c507412c3c1c6041e0af87096bc3c10e25f3b289a39d}'::text[]))
        Heap Blocks: exact=1
        Buffers: shared hit=37
        ->  Bitmap Index Scan on evidence_edge  (cost=0.00..41.00 rows=9 width=0) (actual time=0.087..0.087 rows=9 loops=1)
              Index Cond: ((edge_id)::text = ANY ('{edge:a6c62bdc86918a30f23c50513cdb506df90be784178a240a2b7851214680dd3c,edge:e162df19860a1ad0a752c62601d3cbd49565cc27c2cee74ac3848c3398d03769,edge:c3971f263ea9402c04b778af9a34a04881ace4523dddfcce11aaa02531be9c20,edge:8b277d391222223061ffd4ecf1ae95d146bd68a076fdc50699a0394dea98407f,edge:9381627b7e189fd9e6addab77aa06c1916b276223ac708532ce8de2b7785a3e0,edge:f4eb57b153c8b21f9ba370a2e564be533425833b5ce8c078c3f7deefa88f6cd4,edge:8b994b35df7e35489fb5633bcb2a58f85f2d3ea1e02049cbacda76afc4faef87,edge:c8e8c5b9190aacbebea27e98b47ca477b4dd61ccda42fe36a977f2a13b800d00,edge:8ae330d60d993d605f08c507412c3c1c6041e0af87096bc3c10e25f3b289a39d}'::text[]))
              Buffers: shared hit=36
Planning:
  Buffers: shared hit=118
Planning Time: 0.320 ms
Execution Time: 0.171 ms
```

## piece_patent_medicines 甘草饮片 deep page

```sql
SELECT count(*) AS total FROM edge e0 JOIN entity n0 ON n0.id=e0.source_id WHERE e0.target_id='tcm-mkg:herbal_piece:CHP01118' AND e0.relation='HAS_HERBAL_PIECE'
```

```text
Aggregate  (cost=1472.44..1472.45 rows=1 width=8) (actual time=6.701..6.702 rows=1 loops=1)
  Buffers: shared hit=265
  ->  Merge Join  (cost=0.83..1470.07 rows=948 width=0) (actual time=2.440..6.459 rows=2278 loops=1)
        Merge Cond: ((e0.source_id)::text = (n0.id)::text)
        Buffers: shared hit=265
        ->  Index Only Scan using edge_incoming on edge e0  (cost=0.42..138.44 rows=948 width=32) (actual time=0.021..0.619 rows=2278 loops=1)
              Index Cond: ((target_id = 'tcm-mkg:herbal_piece:CHP01118'::text) AND (relation = 'HAS_HERBAL_PIECE'::text))
              Heap Fetches: 0
              Buffers: shared hit=54
        ->  Index Only Scan using entity_pkey on entity n0  (cost=0.41..1399.36 rows=20374 width=30) (actual time=0.008..3.105 rows=18553 loops=1)
              Heap Fetches: 0
              Buffers: shared hit=211
Planning:
  Buffers: shared hit=324
Planning Time: 0.735 ms
Execution Time: 6.749 ms
```

```sql
SELECT e0.id AS e0_id, e0.source_id AS e0_source_id, e0.target_id AS e0_target_id, e0.relation AS e0_relation, e0.properties_json AS e0_properties_json, e0.quality_state AS e0_quality_state, n0.id AS n0_id, n0.label AS n0_label, n0.type AS n0_type, n0.category AS n0_category FROM edge e0 JOIN entity n0 ON n0.id=e0.source_id WHERE e0.target_id='tcm-mkg:herbal_piece:CHP01118' AND e0.relation='HAS_HERBAL_PIECE' ORDER BY n0.label COLLATE "C", n0.id LIMIT 50 OFFSET 2250
```

```text
Limit  (cost=4056.95..4056.95 rows=1 width=298) (actual time=15.143..15.150 rows=28 loops=1)
  Buffers: shared hit=2911
  ->  Sort  (cost=4054.58..4056.95 rows=948 width=298) (actual time=14.880..15.057 rows=2278 loops=1)
        Sort Key: n0.label COLLATE "C", e0.source_id
        Sort Method: quicksort  Memory: 1253kB
        Buffers: shared hit=2911
        ->  Hash Join  (cost=2534.47..4007.70 rows=948 width=298) (actual time=6.240..12.864 rows=2278 loops=1)
              Hash Cond: ((n0.id)::text = (e0.source_id)::text)
              Buffers: shared hit=2908
              ->  Seq Scan on entity n0  (cost=0.00..1419.74 rows=20374 width=68) (actual time=0.003..3.059 rows=20374 loops=1)
                    Buffers: shared hit=1216
              ->  Hash  (cost=2522.62..2522.62 rows=948 width=198) (actual time=5.080..5.082 rows=2278 loops=1)
                    Buckets: 4096 (originally 1024)  Batches: 1 (originally 1)  Memory Usage: 515kB
                    Buffers: shared hit=1692
                    ->  Bitmap Heap Scan on edge e0  (cost=98.14..2522.62 rows=948 width=198) (actual time=0.586..3.934 rows=2278 loops=1)
                          Recheck Cond: (((target_id)::text = 'tcm-mkg:herbal_piece:CHP01118'::text) AND ((relation)::text = 'HAS_HERBAL_PIECE'::text))
                          Heap Blocks: exact=1639
                          Buffers: shared hit=1692
                          ->  Bitmap Index Scan on edge_incoming  (cost=0.00..97.90 rows=948 width=0) (actual time=0.386..0.386 rows=2278 loops=1)
                                Index Cond: (((target_id)::text = 'tcm-mkg:herbal_piece:CHP01118'::text) AND ((relation)::text = 'HAS_HERBAL_PIECE'::text))
                                Buffers: shared hit=53
Planning:
  Buffers: shared hit=257
Planning Time: 0.680 ms
Execution Time: 15.272 ms
```

```sql
SELECT id,edge_id FROM evidence WHERE edge_id=ANY(ARRAY['edge:f65449a49683357b88948b909b5832b4a1cd9449397999e62ecaa18a026603b4','edge:f227bcfe906d2628b7a3be2a84ec13ac1d42ca64c65ce208ffedcbfb5a5c979b','edge:3278bbd7a294e23f0da21a02ee835d0239e36653059fd6dad713976c4c757e0f','edge:f4c1d579e74bf2721f51b9bd6f2d4e97aaddddb4b9beeeb1365d495f8dbe8f5b','edge:579d1f0106ba112da6b9fe4f56bcfb964e73a611caf2a2570da153db5931c1b5','edge:e4d22666afe91ba062436eae011a392b176d090661e247d21a42671e8eaf52b5','edge:e3e3677be87ee6d086733b71a2eaf06dadee8391646676dffe3b64b119f7f5b4','edge:5c0885521cc48e0798873884e6d95882f74d9806c317b2a4ba2593212eea7aaf','edge:cd654c3c8472582441f5626f3003eb5d528d123fc8eca06d7288419e72da81ad','edge:c88bb9ca091fec0dbce0152821e0a145ad2f65ebf096d79535c1a2e22d37cf10','edge:f31e891b118887e0456648d975c74ee4d05e56c0f86ebc1be7d3802c5c29e004','edge:cda0b9e68c9c4e6a1c91ff760713be62cbf89a6cc2bd9c0f97d8052146fbcd2c','edge:820e83dab2cede38d731bc57faeb9df59e2968c0c4d63c962d2436b5f22e8f04','edge:234dbe851b24468b482170263513958fef7b784726827e197bd7bf377e4cfc2d','edge:2c1e1bead7fc0cdca7087420896275c41ee6b170dc4d38514d588eb6e8e78acb','edge:c35db999fc84f83bb6d4ba83a8e682acf2200a088ca507fb6546fa2d0047f1cb','edge:f2cbdbc21c85c72fe54442f09dc4c5ed030b12d158c273fd89be4a52e03a3c1b','edge:5ff130b66a4c46e5a8763dc07f7514369aa6a327439b1b7812423f2a4a5a6c3f','edge:530759eb6864c0f12dd5ca748caf8690152c391127256912a3caa444e12b1bf8','edge:792ada43a787f8032ca0b33fc5ed2e96fdd47e5a83778a9113ac386a8359b863','edge:eedf6189fc5b68225176e9a0e62ff538248861bd1e8765e59636f2fe8516bb52','edge:7da41e368dc4a14001d83d8b80dd6fee8e69c52ae0ee833641489fefabc84e92','edge:c90a76784cc4fc45cd74e820a828211f4eab3fa9256cec871193293134d4e74a','edge:a5379f1c11774b28bc5e5523c6a94f5bf27b1c4c0512fe39d81fd1f9f2bb69c5','edge:029f540b54642ff99f240bb572c800f1cb194b80fd30a25907d562fc479ca589','edge:7feaa6e9d63e76bae47f31ead4bc4c36490293b5a3cdcfe06514a9abcb5ba600','edge:7f53e5d70ee028b593e2271ae5dbd7f9015254235d111a512311873809018dd5','edge:8dc0739adf3450cd776d9f3f4c37b9b660c4cea73b1ff6540a1cf58fc57a106d']) ORDER BY CASE kind WHEN 'source_quote' THEN 0 WHEN 'curated' THEN 1
    WHEN 'bibliographic' THEN 2 WHEN 'auto_extracted' THEN 3 WHEN 'rule_inferred' THEN 4 END,
    CASE WHEN field_path='' THEN 1 ELSE 0 END, field_path COLLATE "C", id
```

```text
Sort  (cost=236.47..236.54 rows=28 width=184) (actual time=0.578..0.581 rows=28 loops=1)
  Sort Key: (CASE kind WHEN 'source_quote'::text THEN 0 WHEN 'curated'::text THEN 1 WHEN 'bibliographic'::text THEN 2 WHEN 'auto_extracted'::text THEN 3 WHEN 'rule_inferred'::text THEN 4 ELSE NULL::integer END), (CASE WHEN (field_path = ''::text) THEN 1 ELSE 0 END), ((field_path)::text) COLLATE "C", id
  Sort Method: quicksort  Memory: 30kB
  Buffers: shared hit=139
  ->  Bitmap Heap Scan on evidence  (cost=127.62..235.80 rows=28 width=184) (actual time=0.417..0.497 rows=28 loops=1)
        Recheck Cond: ((edge_id)::text = ANY ('{edge:f65449a49683357b88948b909b5832b4a1cd9449397999e62ecaa18a026603b4,edge:f227bcfe906d2628b7a3be2a84ec13ac1d42ca64c65ce208ffedcbfb5a5c979b,edge:3278bbd7a294e23f0da21a02ee835d0239e36653059fd6dad713976c4c757e0f,edge:f4c1d579e74bf2721f51b9bd6f2d4e97aaddddb4b9beeeb1365d495f8dbe8f5b,edge:579d1f0106ba112da6b9fe4f56bcfb964e73a611caf2a2570da153db5931c1b5,edge:e4d22666afe91ba062436eae011a392b176d090661e247d21a42671e8eaf52b5,edge:e3e3677be87ee6d086733b71a2eaf06dadee8391646676dffe3b64b119f7f5b4,edge:5c0885521cc48e0798873884e6d95882f74d9806c317b2a4ba2593212eea7aaf,edge:cd654c3c8472582441f5626f3003eb5d528d123fc8eca06d7288419e72da81ad,edge:c88bb9ca091fec0dbce0152821e0a145ad2f65ebf096d79535c1a2e22d37cf10,edge:f31e891b118887e0456648d975c74ee4d05e56c0f86ebc1be7d3802c5c29e004,edge:cda0b9e68c9c4e6a1c91ff760713be62cbf89a6cc2bd9c0f97d8052146fbcd2c,edge:820e83dab2cede38d731bc57faeb9df59e2968c0c4d63c962d2436b5f22e8f04,edge:234dbe851b24468b482170263513958fef7b784726827e197bd7bf377e4cfc2d,edge:2c1e1bead7fc0cdca7087420896275c41ee6b170dc4d38514d588eb6e8e78acb,edge:c35db999fc84f83bb6d4ba83a8e682acf2200a088ca507fb6546fa2d0047f1cb,edge:f2cbdbc21c85c72fe54442f09dc4c5ed030b12d158c273fd89be4a52e03a3c1b,edge:5ff130b66a4c46e5a8763dc07f7514369aa6a327439b1b7812423f2a4a5a6c3f,edge:530759eb6864c0f12dd5ca748caf8690152c391127256912a3caa444e12b1bf8,edge:792ada43a787f8032ca0b33fc5ed2e96fdd47e5a83778a9113ac386a8359b863,edge:eedf6189fc5b68225176e9a0e62ff538248861bd1e8765e59636f2fe8516bb52,edge:7da41e368dc4a14001d83d8b80dd6fee8e69c52ae0ee833641489fefabc84e92,edge:c90a76784cc4fc45cd74e820a828211f4eab3fa9256cec871193293134d4e74a,edge:a5379f1c11774b28bc5e5523c6a94f5bf27b1c4c0512fe39d81fd1f9f2bb69c5,edge:029f540b54642ff99f240bb572c800f1cb194b80fd30a25907d562fc479ca589,edge:7feaa6e9d63e76bae47f31ead4bc4c36490293b5a3cdcfe06514a9abcb5ba600,edge:7f53e5d70ee028b593e2271ae5dbd7f9015254235d111a512311873809018dd5,edge:8dc0739adf3450cd776d9f3f4c37b9b660c4cea73b1ff6540a1cf58fc57a106d}'::text[]))
        Heap Blocks: exact=21
        Buffers: shared hit=133
        ->  Bitmap Index Scan on evidence_edge  (cost=0.00..127.54 rows=28 width=0) (actual time=0.401..0.401 rows=28 loops=1)
              Index Cond: ((edge_id)::text = ANY ('{edge:f65449a49683357b88948b909b5832b4a1cd9449397999e62ecaa18a026603b4,edge:f227bcfe906d2628b7a3be2a84ec13ac1d42ca64c65ce208ffedcbfb5a5c979b,edge:3278bbd7a294e23f0da21a02ee835d0239e36653059fd6dad713976c4c757e0f,edge:f4c1d579e74bf2721f51b9bd6f2d4e97aaddddb4b9beeeb1365d495f8dbe8f5b,edge:579d1f0106ba112da6b9fe4f56bcfb964e73a611caf2a2570da153db5931c1b5,edge:e4d22666afe91ba062436eae011a392b176d090661e247d21a42671e8eaf52b5,edge:e3e3677be87ee6d086733b71a2eaf06dadee8391646676dffe3b64b119f7f5b4,edge:5c0885521cc48e0798873884e6d95882f74d9806c317b2a4ba2593212eea7aaf,edge:cd654c3c8472582441f5626f3003eb5d528d123fc8eca06d7288419e72da81ad,edge:c88bb9ca091fec0dbce0152821e0a145ad2f65ebf096d79535c1a2e22d37cf10,edge:f31e891b118887e0456648d975c74ee4d05e56c0f86ebc1be7d3802c5c29e004,edge:cda0b9e68c9c4e6a1c91ff760713be62cbf89a6cc2bd9c0f97d8052146fbcd2c,edge:820e83dab2cede38d731bc57faeb9df59e2968c0c4d63c962d2436b5f22e8f04,edge:234dbe851b24468b482170263513958fef7b784726827e197bd7bf377e4cfc2d,edge:2c1e1bead7fc0cdca7087420896275c41ee6b170dc4d38514d588eb6e8e78acb,edge:c35db999fc84f83bb6d4ba83a8e682acf2200a088ca507fb6546fa2d0047f1cb,edge:f2cbdbc21c85c72fe54442f09dc4c5ed030b12d158c273fd89be4a52e03a3c1b,edge:5ff130b66a4c46e5a8763dc07f7514369aa6a327439b1b7812423f2a4a5a6c3f,edge:530759eb6864c0f12dd5ca748caf8690152c391127256912a3caa444e12b1bf8,edge:792ada43a787f8032ca0b33fc5ed2e96fdd47e5a83778a9113ac386a8359b863,edge:eedf6189fc5b68225176e9a0e62ff538248861bd1e8765e59636f2fe8516bb52,edge:7da41e368dc4a14001d83d8b80dd6fee8e69c52ae0ee833641489fefabc84e92,edge:c90a76784cc4fc45cd74e820a828211f4eab3fa9256cec871193293134d4e74a,edge:a5379f1c11774b28bc5e5523c6a94f5bf27b1c4c0512fe39d81fd1f9f2bb69c5,edge:029f540b54642ff99f240bb572c800f1cb194b80fd30a25907d562fc479ca589,edge:7feaa6e9d63e76bae47f31ead4bc4c36490293b5a3cdcfe06514a9abcb5ba600,edge:7f53e5d70ee028b593e2271ae5dbd7f9015254235d111a512311873809018dd5,edge:8dc0739adf3450cd776d9f3f4c37b9b660c4cea73b1ff6540a1cf58fc57a106d}'::text[]))
              Buffers: shared hit=112
Planning:
  Buffers: shared hit=118
Planning Time: 0.511 ms
Execution Time: 0.636 ms
```

## piece_properties 黄芪

```sql
SELECT count(*) AS total FROM edge e0 JOIN entity n0 ON n0.id=e0.target_id WHERE e0.source_id='tcm-mkg:herbal_piece:CHP01717' AND e0.relation='HAS_MEDICINAL_PROPERTY'
```

```text
Aggregate  (cost=21.33..21.34 rows=1 width=8) (actual time=0.058..0.059 rows=1 loops=1)
  Buffers: shared hit=17
  ->  Nested Loop  (cost=0.83..21.32 rows=2 width=0) (actual time=0.045..0.055 rows=4 loops=1)
        Buffers: shared hit=17
        ->  Index Only Scan using edge_outgoing on edge e0  (cost=0.42..8.46 rows=2 width=36) (actual time=0.026..0.027 rows=4 loops=1)
              Index Cond: ((source_id = 'tcm-mkg:herbal_piece:CHP01717'::text) AND (relation = 'HAS_MEDICINAL_PROPERTY'::text))
              Heap Fetches: 0
              Buffers: shared hit=4
        ->  Index Only Scan using entity_pkey on entity n0  (cost=0.41..6.43 rows=1 width=30) (actual time=0.005..0.005 rows=1 loops=4)
              Index Cond: (id = (e0.target_id)::text)
              Heap Fetches: 0
              Buffers: shared hit=13
Planning:
  Buffers: shared hit=325
Planning Time: 1.171 ms
Execution Time: 0.095 ms
```

```sql
SELECT e0.id AS e0_id, e0.source_id AS e0_source_id, e0.target_id AS e0_target_id, e0.relation AS e0_relation, e0.properties_json AS e0_properties_json, e0.quality_state AS e0_quality_state, n0.id AS n0_id, n0.label AS n0_label, n0.type AS n0_type, n0.category AS n0_category FROM edge e0 JOIN entity n0 ON n0.id=e0.target_id WHERE e0.source_id='tcm-mkg:herbal_piece:CHP01717' AND e0.relation='HAS_MEDICINAL_PROPERTY' ORDER BY n0.category COLLATE "C", n0.label COLLATE "C", n0.id LIMIT 20 OFFSET 0
```

```text
Limit  (cost=27.08..27.09 rows=2 width=330) (actual time=0.066..0.068 rows=4 loops=1)
  Buffers: shared hit=23
  ->  Sort  (cost=27.08..27.09 rows=2 width=330) (actual time=0.066..0.067 rows=4 loops=1)
        Sort Key: n0.category COLLATE "C", n0.label COLLATE "C", e0.target_id
        Sort Method: quicksort  Memory: 27kB
        Buffers: shared hit=23
        ->  Nested Loop  (cost=0.83..27.07 rows=2 width=330) (actual time=0.029..0.040 rows=4 loops=1)
              Buffers: shared hit=20
              ->  Index Scan using edge_outgoing on edge e0  (cost=0.42..10.21 rows=2 width=198) (actual time=0.015..0.017 rows=4 loops=1)
                    Index Cond: (((source_id)::text = 'tcm-mkg:herbal_piece:CHP01717'::text) AND ((relation)::text = 'HAS_MEDICINAL_PROPERTY'::text))
                    Buffers: shared hit=4
              ->  Index Scan using entity_pkey on entity n0  (cost=0.41..8.43 rows=1 width=68) (actual time=0.004..0.004 rows=1 loops=4)
                    Index Cond: ((id)::text = (e0.target_id)::text)
                    Buffers: shared hit=16
Planning:
  Buffers: shared hit=261
Planning Time: 0.685 ms
Execution Time: 0.097 ms
```

```sql
SELECT id,edge_id FROM evidence WHERE edge_id=ANY(ARRAY['edge:47c6936f8981e0f6d72e1474f81bc15d25e2df3518c0cb074f22f7853d70c02e','edge:86d5ce1ffd8e2ea501a938d4e01b10ce1b945749ed879e5a0b89a8f1f41f44d1','edge:075c32f5cfa7e68f8bd72df488e9ae6f0b81bf795c551334ba675f8ae6f7f7f9','edge:aa2b359d90cd44a6862d9654f5c3fb085bcfa4f88b47584eccd8a44f8dd72a33']) ORDER BY CASE kind WHEN 'source_quote' THEN 0 WHEN 'curated' THEN 1
    WHEN 'bibliographic' THEN 2 WHEN 'auto_extracted' THEN 3 WHEN 'rule_inferred' THEN 4 END,
    CASE WHEN field_path='' THEN 1 ELSE 0 END, field_path COLLATE "C", id
```

```text
Sort  (cost=34.36..34.37 rows=4 width=184) (actual time=0.125..0.126 rows=4 loops=1)
  Sort Key: (CASE kind WHEN 'source_quote'::text THEN 0 WHEN 'curated'::text THEN 1 WHEN 'bibliographic'::text THEN 2 WHEN 'auto_extracted'::text THEN 3 WHEN 'rule_inferred'::text THEN 4 ELSE NULL::integer END), (CASE WHEN (field_path = ''::text) THEN 1 ELSE 0 END), ((field_path)::text) COLLATE "C", id
  Sort Method: quicksort  Memory: 25kB
  Buffers: shared hit=26
  ->  Index Scan using evidence_edge on evidence  (cost=0.55..34.32 rows=4 width=184) (actual time=0.063..0.099 rows=4 loops=1)
        Index Cond: ((edge_id)::text = ANY ('{edge:47c6936f8981e0f6d72e1474f81bc15d25e2df3518c0cb074f22f7853d70c02e,edge:86d5ce1ffd8e2ea501a938d4e01b10ce1b945749ed879e5a0b89a8f1f41f44d1,edge:075c32f5cfa7e68f8bd72df488e9ae6f0b81bf795c551334ba675f8ae6f7f7f9,edge:aa2b359d90cd44a6862d9654f5c3fb085bcfa4f88b47584eccd8a44f8dd72a33}'::text[]))
        Buffers: shared hit=20
Planning:
  Buffers: shared hit=115
Planning Time: 0.429 ms
Execution Time: 0.150 ms
```

## datasets

```sql
SELECT * FROM dataset ORDER BY id
```

```text
Sort  (cost=20.76..21.31 rows=220 width=338) (actual time=0.019..0.020 rows=2 loops=1)
  Sort Key: id
  Sort Method: quicksort  Memory: 25kB
  Buffers: shared hit=4
  ->  Seq Scan on dataset  (cost=0.00..12.20 rows=220 width=338) (actual time=0.002..0.003 rows=2 loops=1)
        Buffers: shared hit=1
Planning:
  Buffers: shared hit=42
Planning Time: 0.098 ms
Execution Time: 0.029 ms
```

```sql
SELECT dataset_id, count(*) AS n FROM entity GROUP BY dataset_id
```

```text
GroupAggregate  (cost=0.41..1446.66 rows=2 width=16) (actual time=0.149..3.987 rows=2 loops=1)
  Group Key: dataset_id
  Buffers: shared hit=223
  ->  Index Only Scan using entity_dataset_id_type_source_key_key on entity  (cost=0.41..1344.77 rows=20374 width=8) (actual time=0.035..2.355 rows=20374 loops=1)
        Heap Fetches: 0
        Buffers: shared hit=223
Planning:
  Buffers: shared hit=90
Planning Time: 0.231 ms
Execution Time: 4.022 ms
```

```sql
SELECT s.dataset_id, count(*) AS n FROM edge e JOIN entity s ON s.id=e.source_id GROUP BY s.dataset_id
```

```text
Finalize GroupAggregate  (cost=9003.97..9004.48 rows=2 width=16) (actual time=36.743..40.526 rows=2 loops=1)
  Group Key: s.dataset_id
  Buffers: shared hit=6438
  ->  Gather Merge  (cost=9003.97..9004.44 rows=4 width=16) (actual time=36.735..40.517 rows=6 loops=1)
        Workers Planned: 2
        Workers Launched: 2
        Buffers: shared hit=6438
        ->  Sort  (cost=8003.95..8003.95 rows=2 width=16) (actual time=34.378..34.381 rows=2 loops=3)
              Sort Key: s.dataset_id
              Sort Method: quicksort  Memory: 25kB
              Buffers: shared hit=6438
              Worker 0:  Sort Method: quicksort  Memory: 25kB
              Worker 1:  Sort Method: quicksort  Memory: 25kB
              ->  Partial HashAggregate  (cost=8003.92..8003.94 rows=2 width=16) (actual time=34.343..34.350 rows=2 loops=3)
                    Group Key: s.dataset_id
                    Batches: 1  Memory Usage: 24kB
                    Buffers: shared hit=6422
                    Worker 0:  Batches: 1  Memory Usage: 24kB
                    Worker 1:  Batches: 1  Memory Usage: 24kB
                    ->  Parallel Hash Join  (cost=1485.66..7629.96 rows=74792 width=8) (actual time=4.726..26.469 rows=59834 loops=3)
                          Hash Cond: ((e.source_id)::text = (s.id)::text)
                          Buffers: shared hit=6422
                          ->  Parallel Seq Scan on edge e  (cost=0.00..5947.93 rows=74792 width=32) (actual time=0.006..7.837 rows=59834 loops=3)
                                Buffers: shared hit=5200
                          ->  Parallel Hash  (cost=1335.85..1335.85 rows=11985 width=38) (actual time=4.561..4.562 rows=6791 loops=3)
                                Buckets: 32768  Batches: 1  Memory Usage: 1824kB
                                Buffers: shared hit=1216
                                ->  Parallel Seq Scan on entity s  (cost=0.00..1335.85 rows=11985 width=38) (actual time=0.008..2.039 rows=6791 loops=3)
                                      Buffers: shared hit=1216
Planning:
  Buffers: shared hit=306
Planning Time: 0.766 ms
Execution Time: 40.695 ms
```

```sql
SELECT dataset_id, count(*) AS n FROM source_record GROUP BY dataset_id
```

```text
Finalize GroupAggregate  (cost=1000.44..12283.88 rows=2 width=16) (actual time=24.321..27.099 rows=2 loops=1)
  Group Key: dataset_id
  Buffers: shared hit=2221
  ->  Gather Merge  (cost=1000.44..12283.84 rows=4 width=16) (actual time=24.297..27.089 rows=4 loops=1)
        Workers Planned: 2
        Workers Launched: 2
        Buffers: shared hit=2221
        ->  Partial GroupAggregate  (cost=0.42..11283.36 rows=2 width=16) (actual time=14.068..14.074 rows=1 loops=3)
              Group Key: dataset_id
              Buffers: shared hit=2221
              ->  Parallel Index Only Scan using source_record_dataset_id_filename_record_key_key on source_record  (cost=0.42..10872.32 rows=82203 width=8) (actual time=0.030..8.668 rows=65762 loops=3)
                    Heap Fetches: 0
                    Buffers: shared hit=2221
Planning:
  Buffers: shared hit=57
Planning Time: 0.155 ms
Execution Time: 27.170 ms
```
