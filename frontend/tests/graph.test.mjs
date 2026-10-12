import assert from 'node:assert/strict'
import { after, test } from 'node:test'
import { createServer } from 'vite'

const server = await createServer({
  configFile: false,
  server: { middlewareMode: true, hmr: false, watch: null },
})
after(() => server.close())
const graph = await server.ssrLoadModule('/src/graph.ts')

const node = id => ({ id, type: 'herb', label: id, category: null })
const edge = (id, source_id, target_id, relation = 'CONTAINS') =>
  ({ id, relation, source_id, target_id, properties: {}, quality_state: 'consistent', evidence_ids: [] })
const hop = (center, ids, extra = {}) => ({
  center, nodes: [node(center), ...ids.map(node)], edges: ids.map(id => edge(`${center}-${id}`, center, id)),
  truncated: false, limits: { nodes: 50, edges: 100 }, relations: [],
  relation_counts: [{ relation: 'CONTAINS', direction: 'out', count: ids.length }], ...extra,
})

test('merges hops by ID and records each expansion', () => {
  const first = graph.mergeHop(graph.emptyCanvas(), hop('a', ['b', 'c']))
  assert.equal(first.ok, true)
  const second = graph.mergeHop(first.canvas, { ...hop('b', ['c', 'd']), edges: [edge('a-b', 'a', 'b'), edge('b-c', 'b', 'c'), edge('b-d', 'b', 'd')] })
  assert.equal(second.ok, true)
  assert.deepEqual([...second.canvas.nodes.keys()], ['a', 'b', 'c', 'd'])
  assert.deepEqual([...second.canvas.edges.keys()], ['a-b', 'a-c', 'b-c', 'b-d'])
  assert.equal(second.addedNodes, 1)
  assert.deepEqual([...second.canvas.expanded.keys()], ['a', 'b'])
  assert.equal(first.canvas.nodes.size, 3, 'the earlier canvas is not mutated')
})

test('refuses a hop that would pass the canvas limits and keeps the canvas', () => {
  const many = n => Array.from({ length: n }, (_, i) => `n${i}`)
  const start = graph.mergeHop(graph.emptyCanvas(), hop('a', many(49)))
  assert.equal(start.canvas.nodes.size, 50)
  const atLimit = graph.mergeHop(start.canvas, hop('n0', many(99).map(id => `m${id}`).slice(0, 50)))
  assert.equal(atLimit.ok, true)
  assert.equal(atLimit.canvas.nodes.size, 100)
  const over = graph.mergeHop(atLimit.canvas, hop('n1', ['x']))
  assert.deepEqual(over, { ok: false, nodes: 101, edges: 100 })
})

test('reports the true total for the active relation filter', () => {
  const counts = [{ relation: 'CONTAINS', direction: 'in', count: 2278 }, { relation: 'CITED_IN', direction: 'out', count: 1 }]
  assert.equal(graph.relationTotal(counts, []), 2279)
  assert.equal(graph.relationTotal(counts, ['CONTAINS']), 2278)
  const page = hop('a', ['b'], { truncated: true, relations: ['CONTAINS'], relation_counts: counts })
  const merged = graph.mergeHop(graph.emptyCanvas(), page)
  assert.equal(graph.expansionText(merged.canvas.expanded.get('a')), '共 2,278 条关系，仅显示 1 条')
})

test('lists edges by relation, then start and end names', () => {
  const merged = graph.mergeElements(graph.emptyCanvas(), [node('甲'), node('乙'), node('丙')],
    [edge('2', '乙', '甲', 'CONTAINS'), edge('1', '甲', '丙', 'CITED_IN'), edge('3', '丙', '甲', 'CONTAINS')])
  assert.deepEqual(graph.edgeRows(merged.canvas).map(r => r.edge.id), ['1', '3', '2'])
})

test('every relation and entity type has a distinct style', () => {
  const relations = Object.values(graph.relationStyles)
  assert.equal(new Set(relations.map(s => s.color)).size, 7)
  assert.equal(new Set(relations.map(s => s.dash.join())).size, 7)
  assert.equal(new Set(Object.values(graph.typeStyles).map(s => s.shape)).size, 9)
})
