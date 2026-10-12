<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { type ApiError, get, toApiError, useLoader } from '../api/client'
import type { GraphPage, RelationPage } from '../api/types'
import {
  CANVAS_LIMITS, type Canvas, edgeRows, emptyCanvas, expansionText, type Merge, mergeHop, mergePaths, relationStyles,
  typeStyles,
} from '../graph'
import { label, number, refocusHeading, relationNames, relationSections, roleNames, setTitle, typeNames } from '../labels'
import EvidenceLinks from '../components/EvidenceLinks.vue'
import GraphCanvas, { type Selection } from '../components/GraphCanvas.vue'
import StateView from '../components/StateView.vue'
import TwoHopPaths from '../components/TwoHopPaths.vue'

const props = defineProps<{ id: string }>()
const route = useRoute()
const router = useRouter()

// Filter lives in the URL (?relation=A&relation=B); unknown values are dropped, an empty filter means all relations.
const RELATIONS = relationSections.map(s => s.relation)
const relations = computed(() => {
  const raw = route.query.relation
  const list = (Array.isArray(raw) ? raw : raw ? [raw] : []).filter((r): r is string => typeof r === 'string')
  return RELATIONS.filter(r => list.includes(r))
})

const { data, error, loading, load } = useLoader(signal =>
  get<GraphPage>('/graph', { center: props.id, relation: relations.value }, { signal }))
onMounted(load)
watch(relations, load)
setTitle('关系图谱')

const canvas = shallowRef<Canvas>(emptyCanvas())
const selected = ref<Selection>(null)
const limitHit = ref<{ id: string; label: string; nodes: number; edges: number } | null>(null)
const expandError = shallowRef<ApiError | null>(null)
const expanding = ref<string | null>(null)
const lastExpansion = ref<string | null>(null)
const canvasRef = ref<InstanceType<typeof GraphCanvas> | null>(null)

let controller: AbortController | undefined
onBeforeUnmount(() => controller?.abort())

const center = computed(() => data.value?.nodes[0] ?? null)
function reset() {
  const page = data.value
  if (!page) return
  controller?.abort()  // a pending expansion belongs to the canvas being replaced
  expanding.value = null
  const merged = mergeHop(emptyCanvas(), page)
  canvas.value = merged.ok ? merged.canvas : emptyCanvas()
  selected.value = { kind: 'node', id: page.center }
  lastExpansion.value = page.center
  limitHit.value = null
  expandError.value = null
}
watch(data, page => {
  if (!page) return
  reset()
  setTitle(`${page.nodes[0].label} · 关系图谱`)
  refocusHeading()
})

function apply(merge: Merge, id: string, name: string) {
  if (merge.ok) {
    canvas.value = merge.canvas
    limitHit.value = null
  } else {
    limitHit.value = { id, label: name, nodes: merge.nodes, edges: merge.edges }
  }
  return merge.ok
}

// spec §6.4: clicking a node requests its one-hop neighborhood and merges the result by ID.
async function expand(id: string) {
  selected.value = { kind: 'node', id }
  if (canvas.value.expanded.has(id) || expanding.value === id) return
  controller?.abort()
  const current = new AbortController()
  controller = current
  expanding.value = id
  expandError.value = null
  try {
    const page = await get<GraphPage>('/graph', { center: id, relation: relations.value }, { signal: current.signal })
    if (apply(mergeHop(canvas.value, page), id, page.nodes[0].label)) lastExpansion.value = id
  } catch (e) {
    if (!current.signal.aborted) expandError.value = toApiError(e)
  } finally {
    if (controller === current) expanding.value = null
  }
}

function showPaths(page: RelationPage) {
  apply(mergePaths(canvas.value, page), page.entity_id, page.nodes[page.entity_id]?.label ?? '')
}

function setRelation(relation: string, on: boolean) {
  const next = RELATIONS.filter(r => r === relation ? on : relations.value.includes(r))
  void router.replace({ query: { ...route.query, relation: next.length ? next : undefined } })
}

const rows = computed(() => edgeRows(canvas.value))
const selectedNode = computed(() => selected.value?.kind === 'node' ? canvas.value.nodes.get(selected.value.id) ?? null : null)
const selectedEdge = computed(() => selected.value?.kind === 'edge' ? canvas.value.edges.get(selected.value.id) ?? null : null)
const nodeName = (id: string) => canvas.value.nodes.get(id)?.label ?? id
const entityLink = (id: string) => `/entity/${encodeURIComponent(id)}`
const graphLink = (id: string) => ({ path: `/graph/${encodeURIComponent(id)}`, query: route.query })
const counts = computed(() => (data.value?.relation_counts ?? []).reduce<Record<string, number>>(
  (acc, c) => ({ ...acc, [c.relation]: (acc[c.relation] ?? 0) + c.count }), {}))
const filterOptions = computed(() => RELATIONS.filter(r => counts.value[r] || relations.value.includes(r)))
const lastText = computed(() => {
  const id = lastExpansion.value
  const expansion = id ? canvas.value.expanded.get(id) : undefined
  return id && expansion ? `「${nodeName(id)}」${expansionText(expansion)}` : ''
})
const dashArray = (relation: string) => (relationStyles[relation]?.dash ?? []).join(' ')
const edgeProperty = (value: unknown, key: string) => key === 'role' ? label(roleNames, String(value))
  : key === 'position' && typeof value === 'number' ? String(value + 1) : String(value)
const propertyNames: Record<string, string> = { role: '君臣佐使', position: '组成位置', dosage_raw: '剂量原文' }
</script>

<template>
  <h1 v-if="!data" class="page-title" tabindex="-1">关系图谱</h1>
  <StateView :loading="loading && !data" :error="error" invalid-is-not-found not-found-text="未找到该实体，链接可能已失效。" @retry="load">
    <template v-if="data && center">
      <header class="entity-header graph-header">
        <p class="eyebrow">关系图谱 · {{ label(typeNames, center.type) }}</p>
        <h1 tabindex="-1">{{ center.label }}</h1>
        <p class="entity-meta">
          <RouterLink class="text-link" :to="entityLink(center.id)">查看详情</RouterLink>
          <span>图数据来自 Neo4j；关系总数来自{{ data.relation_counts_source === 'vastbase' ? ' Vastbase' : ' PostgreSQL' }}主库</span>
        </p>
      </header>

      <fieldset class="graph-filter">
        <legend>关系类型（不选即全部）</legend>
        <label v-for="r in filterOptions" :key="r">
          <input type="checkbox" :checked="relations.includes(r)" :disabled="loading" @change="setRelation(r, ($event.target as HTMLInputElement).checked)" />
          {{ label(relationNames, r) }} <span class="count">{{ number(counts[r] ?? 0) }}</span>
        </label>
      </fieldset>

      <div class="graph-status" aria-live="polite">
        <span>画布 {{ canvas.nodes.size }} / {{ CANVAS_LIMITS.nodes }} 个节点，{{ canvas.edges.size }} / {{ CANVAS_LIMITS.edges }} 条边</span>
        <span v-if="lastText" :class="{ 'pager-note': canvas.expanded.get(lastExpansion!)?.truncated }">{{ lastText }}</span>
        <span v-if="expanding">正在展开「{{ nodeName(expanding) }}」…</span>
      </div>
      <div v-if="limitHit" class="banner" role="alert">
        <span>展开「{{ limitHit.label }}」后画布将有 {{ limitHit.nodes }} 个节点、{{ limitHit.edges }} 条边，超过上限。可以清空画布，或以该节点为中心重新开始。</span>
        <span class="banner-actions">
          <button type="button" class="ghost-button" @click="reset">清空画布</button>
          <RouterLink class="ghost-button" :to="graphLink(limitHit.id)">以「{{ limitHit.label }}」为中心</RouterLink>
        </span>
      </div>
      <p v-if="expandError" class="error" role="alert">展开失败：{{ expandError.message }}</p>

      <div class="graph-layout">
        <div class="graph-stage">
          <GraphCanvas ref="canvasRef" :canvas="canvas" :center-id="center.id" :selected="selected"
            @node="expand" @edge="id => (selected = { kind: 'edge', id })" />
          <div class="graph-tools">
            <button type="button" class="ghost-button" @click="canvasRef?.relayout()">重新布局</button>
            <button type="button" class="ghost-button" @click="reset">清空画布</button>
          </div>
        </div>

        <aside class="panel graph-side" aria-live="polite" aria-labelledby="selection-heading">
          <h2 id="selection-heading">{{ selectedEdge ? '关系' : '节点' }}</h2>
          <template v-if="selectedNode">
            <p class="graph-node-title">{{ selectedNode.label }}<span class="tag">{{ label(typeNames, selectedNode.type) }}</span></p>
            <p v-if="selectedNode.category" class="muted">{{ selectedNode.category }}</p>
            <p v-if="canvas.expanded.get(selectedNode.id)" class="graph-note">{{ expansionText(canvas.expanded.get(selectedNode.id)!) }}</p>
            <p v-else class="graph-note">尚未展开。点击图中节点或下方按钮展开一跳关系。</p>
            <div class="graph-actions">
              <button v-if="!canvas.expanded.has(selectedNode.id)" type="button" class="ghost-button"
                :disabled="expanding === selectedNode.id" @click="expand(selectedNode.id)">展开一跳</button>
              <RouterLink class="text-link" :to="entityLink(selectedNode.id)">查看详情</RouterLink>
              <RouterLink v-if="selectedNode.id !== center.id" class="text-link" :to="graphLink(selectedNode.id)">以此为中心</RouterLink>
            </div>
          </template>
          <template v-else-if="selectedEdge">
            <p class="edge-target">
              <RouterLink class="text-link" :to="entityLink(selectedEdge.source_id)">{{ nodeName(selectedEdge.source_id) }}</RouterLink>
              <span>→ {{ label(relationNames, selectedEdge.relation) }} →</span>
              <RouterLink class="text-link" :to="entityLink(selectedEdge.target_id)">{{ nodeName(selectedEdge.target_id) }}</RouterLink>
            </p>
            <dl v-if="Object.keys(selectedEdge.properties).length" class="attr-dl">
              <template v-for="(value, key) in selectedEdge.properties" :key="key">
                <dt>{{ propertyNames[key] ?? key }}</dt><dd>{{ edgeProperty(value, String(key)) }}</dd>
              </template>
            </dl>
            <p v-if="selectedEdge.quality_state === 'conflicting'" class="conflict block">⚠ 来源记载不一致：缺失的字段在不同来源中取值不同，请查看证据。</p>
            <h3 class="graph-subhead">证据 <span class="count">{{ selectedEdge.evidence_ids.length }}</span></h3>
            <ol v-if="selectedEdge.evidence_ids.length" class="graph-evidence">
              <li v-for="(id, i) in selectedEdge.evidence_ids" :key="id">
                <RouterLink class="text-link" :to="`/evidence/${encodeURIComponent(id)}`">证据 {{ i + 1 }}</RouterLink>
              </li>
            </ol>
            <p v-else class="muted">无</p>
          </template>
          <p v-else class="muted">点击图中的节点或边查看详情。</p>
        </aside>
      </div>

      <TwoHopPaths v-if="center.type === 'herb'" :herb-id="center.id" @show="showPaths" />

      <section class="panel detail-section graph-legend" aria-labelledby="legend-heading">
        <h2 id="legend-heading">图例</h2>
        <ul class="legend-list">
          <li v-for="r in RELATIONS" :key="r">
            <svg width="44" height="10" aria-hidden="true"><line x1="0" y1="5" x2="44" y2="5" :stroke="relationStyles[r].color" stroke-width="2.5" :stroke-dasharray="dashArray(r)" /></svg>
            {{ label(relationNames, r) }}
          </li>
        </ul>
        <ul class="legend-list">
          <li v-for="(style, type) in typeStyles" :key="type"><span class="swatch" :style="{ background: style.color }" aria-hidden="true"></span>{{ label(typeNames, String(type)) }}</li>
          <li><span class="swatch center-swatch" aria-hidden="true"></span>中心节点（粗边框）</li>
        </ul>
      </section>

      <section class="panel detail-section" aria-labelledby="list-heading">
        <h2 id="list-heading">关系列表 <span class="count">{{ rows.length }}</span></h2>
        <p class="footnote graph-list-note">与画布内容相同。点名称展开该节点，点关系查看证据。</p>
        <div class="table-wrap">
          <table>
            <thead><tr><th scope="col">起点</th><th scope="col">关系</th><th scope="col">终点</th><th scope="col">证据</th></tr></thead>
            <tbody>
              <tr v-for="row in rows" :key="row.edge.id" :class="{ conflicting: row.edge.quality_state === 'conflicting', selected: selected?.id === row.edge.id }">
                <td><button type="button" class="text-button node-button" :aria-pressed="selected?.id === row.edge.source_id" @click="expand(row.edge.source_id)">{{ row.source?.label }}</button></td>
                <td><button type="button" class="text-button node-button" @click="selected = { kind: 'edge', id: row.edge.id }">
                  <span class="legend-dot" :style="{ background: relationStyles[row.edge.relation]?.color }" aria-hidden="true"></span>{{ label(relationNames, row.edge.relation) }}<span v-if="row.edge.quality_state === 'conflicting'" class="conflict"> ⚠</span>
                </button></td>
                <td><button type="button" class="text-button node-button" :aria-pressed="selected?.id === row.edge.target_id" @click="expand(row.edge.target_id)">{{ row.target?.label }}</button></td>
                <td><EvidenceLinks :ids="row.edge.evidence_ids" /></td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

    </template>
  </StateView>
</template>
