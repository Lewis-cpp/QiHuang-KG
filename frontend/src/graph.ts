// spec §6.4: canvas state for /graph/:id. Pure functions so the merge rules can be tested without a browser.
import type { GraphNode, GraphPage, RelationEdge, RelationPage, RelationSummary } from './api/types'

export const CANVAS_LIMITS = { nodes: 100, edges: 200 }

export interface Expansion { shown: number; total: number; truncated: boolean }

export interface Canvas {
  nodes: Map<string, GraphNode>
  edges: Map<string, RelationEdge>
  expanded: Map<string, Expansion>
}

export function emptyCanvas(): Canvas {
  return { nodes: new Map(), edges: new Map(), expanded: new Map() }
}

export type Merge =
  | { ok: true; canvas: Canvas; addedNodes: number; addedEdges: number }
  | { ok: false; nodes: number; edges: number }

// Merge by ID; when the result would pass a canvas limit nothing is merged, so the canvas never shows half a hop.
export function mergeElements(canvas: Canvas, nodes: GraphNode[], edges: RelationEdge[]): Merge {
  const newNodes = nodes.filter((n, i) => !canvas.nodes.has(n.id) && nodes.findIndex(m => m.id === n.id) === i)
  const newEdges = edges.filter((e, i) => !canvas.edges.has(e.id) && edges.findIndex(f => f.id === e.id) === i)
  const total = { nodes: canvas.nodes.size + newNodes.length, edges: canvas.edges.size + newEdges.length }
  if (total.nodes > CANVAS_LIMITS.nodes || total.edges > CANVAS_LIMITS.edges) return { ok: false, ...total }
  const next: Canvas = { nodes: new Map(canvas.nodes), edges: new Map(canvas.edges), expanded: new Map(canvas.expanded) }
  newNodes.forEach(n => next.nodes.set(n.id, n))
  newEdges.forEach(e => next.edges.set(e.id, e))
  return { ok: true, canvas: next, addedNodes: newNodes.length, addedEdges: newEdges.length }
}

// The true number of edges the request could have returned: all relations, or only the filtered ones.
export function relationTotal(counts: RelationSummary[], relations: string[]): number {
  return counts.filter(c => !relations.length || relations.includes(c.relation)).reduce((sum, c) => sum + c.count, 0)
}

export function mergeHop(canvas: Canvas, page: GraphPage): Merge {
  const merged = mergeElements(canvas, page.nodes, page.edges)
  if (merged.ok) {
    merged.canvas.expanded.set(page.center, {
      shown: page.edges.length, total: relationTotal(page.relation_counts, page.relations), truncated: page.truncated,
    })
  }
  return merged
}

export function mergePaths(canvas: Canvas, page: RelationPage): Merge {
  return mergeElements(canvas, Object.values(page.nodes), Object.values(page.edges))
}

export function expansionText(e: Expansion): string {
  const n = (x: number) => x.toLocaleString('zh-CN')
  return e.truncated ? `共 ${n(e.total)} 条关系，仅显示 ${n(e.shown)} 条` : `共 ${n(e.total)} 条关系，已全部显示`
}

// Relation types differ by color and by line pattern; the legend repeats both with text.
export const relationStyles: Record<string, { color: string; dash: number[] }> = {
  CONTAINS: { color: '#2f6f5e', dash: [] },
  ASSOCIATED_WITH_PATTERN: { color: '#b0623b', dash: [10, 5] },
  CITED_IN: { color: '#7a5ca8', dash: [2, 4] },
  HAS_HERBAL_PIECE: { color: '#2f74a8', dash: [14, 4, 3, 4] },
  ASSOCIATED_WITH_TERM: { color: '#8f7417', dash: [5, 5] },
  MAPPED_TO_ICD11: { color: '#a8456b', dash: [16, 4, 3, 4, 3, 4] },
  HAS_MEDICINAL_PROPERTY: { color: '#5d7d2a', dash: [3, 3, 10, 3] },
}

export const typeStyles: Record<string, { color: string; shape: string }> = {
  herb: { color: '#3f7d5d', shape: 'ellipse' },
  formula: { color: '#8a5a2b', shape: 'round-rectangle' },
  pattern: { color: '#b0623b', shape: 'diamond' },
  text: { color: '#6b5ca5', shape: 'rectangle' },
  tcm_term: { color: '#8f7417', shape: 'hexagon' },
  patent_medicine: { color: '#2f74a8', shape: 'barrel' },
  herbal_piece: { color: '#5d8a3a', shape: 'round-triangle' },
  icd11_code: { color: '#a8456b', shape: 'tag' },
  medicinal_property: { color: '#6f6f6f', shape: 'octagon' },
}

// The text list follows the canvas: by relation, then start and end names, in code point order like the API.
const compare = (a: string, b: string) => (a < b ? -1 : a > b ? 1 : 0)
export function edgeRows(canvas: Canvas) {
  const name = (id: string) => canvas.nodes.get(id)?.label ?? id
  return [...canvas.edges.values()]
    .map(edge => ({ edge, source: canvas.nodes.get(edge.source_id), target: canvas.nodes.get(edge.target_id) }))
    .sort((a, b) => compare(a.edge.relation, b.edge.relation) || compare(name(a.edge.source_id), name(b.edge.source_id))
      || compare(name(a.edge.target_id), name(b.edge.target_id)) || compare(a.edge.id, b.edge.id))
}
