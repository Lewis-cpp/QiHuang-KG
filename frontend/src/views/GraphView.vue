<script setup lang="ts">
import { computed, onMounted, ref, shallowRef } from 'vue'
import { get, toApiError, useLoader, type ApiError } from '../api/client'
import type { GraphEdge, GraphResponse, Node } from '../api/types'
import { label, number, refocusHeading, relationNames, relationStyles, roleNames, setTitle, typeColors, typeNames } from '../labels'
import GraphCanvas from '../components/GraphCanvas.vue'
import EvidenceLinks from '../components/EvidenceLinks.vue'
import StateView from '../components/StateView.vue'

// spec §6.4: the canvas keeps at most 100 nodes and 200 edges; the reader clears or changes centre to go on.
const MAX_NODES = 100
const MAX_EDGES = 200
const props = defineProps<{ id: string }>()

const nodes = shallowRef(new Map<string, Node>())
const edges = shallowRef(new Map<string, GraphEdge>())
// Per node: the true relation total from the relational store and how many edges the graph request returned.
const loaded = shallowRef(new Map<string, { total: number; shown: number; truncated: boolean }>())
const filter = ref<string[]>([])
const capped = ref(false)
const selectedNode = ref<string | null>(null)
const selectedEdge = ref<string | null>(null)
const expanding = ref(false)
const expandError = ref<ApiError | null>(null)
let expandToken = 0

const params = (center: string) => ({ center, relation: filter.value.length ? filter.value : undefined })

function merge(res: GraphResponse) {
  const nextNodes = new Map(nodes.value)
  const nextEdges = new Map(edges.value)
  for (const n of res.nodes) {
    if (nextNodes.has(n.id)) continue
    if (nextNodes.size >= MAX_NODES) capped.value = true
    else nextNodes.set(n.id, n)
  }
  for (const e of res.edges) {
    if (nextEdges.has(e.id)) continue
    if (!nextNodes.has(e.source_id) || !nextNodes.has(e.target_id)) continue
    if (nextEdges.size >= MAX_EDGES) capped.value = true
    else nextEdges.set(e.id, e)
  }
  const nextLoaded = new Map(loaded.value)
  nextLoaded.set(res.center, {
    total: res.relation_counts.reduce((sum, r) => sum + r.count, 0), shown: res.edges.length, truncated: res.truncated,
  })
  nodes.value = nextNodes
  edges.value = nextEdges
  loaded.value = nextLoaded
}

function clear() {
  nodes.value = new Map()
  edges.value = new Map()
  loaded.value = new Map()
  capped.value = false
  selectedNode.value = selectedEdge.value = null
  expandError.value = null
}

const first = useLoader(async signal => {
  const res = await get<GraphResponse>('/graph', params(props.id), { signal })
  clear()
  merge(res)
  return res
})
onMounted(first.load)
setTitle('关系图谱')

const centerNode = computed(() => nodes.value.get(props.id))
const nodeList = computed(() => [...nodes.value.values()])
const edgeList = computed(() => [...edges.value.values()])
const name = (id: string) => nodes.value.get(id)?.label ?? id

async function expand(id: string) {
  if (loaded.value.has(id) || expanding.value) return
  const token = ++expandToken
  expanding.value = true
  expandError.value = null
  try {
    const res = await get<GraphResponse>('/graph', params(id))
    if (token === expandToken) merge(res)
  } catch (e) {
    if (token === expandToken) expandError.value = toApiError(e)
  } finally {
    if (token === expandToken) expanding.value = false
  }
}

function pickNode(id: string) {
  selectedNode.value = id
  selectedEdge.value = null
  void expand(id)
}

function pickEdge(id: string) {
  selectedEdge.value = id
  selectedNode.value = null
}

const selectedNodeInfo = computed(() => selectedNode.value ? { node: nodes.value.get(selectedNode.value)!, info: loaded.value.get(selectedNode.value) } : null)
const selectedEdgeInfo = computed(() => selectedEdge.value ? edges.value.get(selectedEdge.value) ?? null : null)

async function reload() {
  expandToken++
  expanding.value = false
  await first.load()
  refocusHeading()
}

const relationKeys = Object.keys(relationNames)
const dosage = (e: GraphEdge) => e.relation === 'CONTAINS'
  ? [e.properties.role === null ? '君臣佐使：⚠ 来源记载不一致' : e.properties.role ? `君臣佐使：${label(roleNames, String(e.properties.role))}` : '',
    e.properties.dosage_raw === null ? '剂量：⚠ 来源记载不一致' : e.properties.dosage_raw ? `剂量：${e.properties.dosage_raw}` : ''].filter(Boolean)
  : []
const usedRelations = computed(() => [...new Set(edgeList.value.map(e => e.relation))])
const usedTypes = computed(() => [...new Set(nodeList.value.map(n => n.type))])
</script>

<template>
  <h1 v-if="!centerNode" class="page-title" tabindex="-1">关系图谱</h1>
  <p class="graph-back"><RouterLink class="text-link" :to="`/entity/${encodeURIComponent(id)}`">返回实体详情</RouterLink></p>
  <StateView :loading="first.loading.value" :error="first.error.value" invalid-is-not-found not-found-text="未找到该实体，链接可能已失效。" @retry="reload">
    <template v-if="centerNode">
      <header class="entity-header graph-header">
        <p class="eyebrow">关系图谱 · {{ label(typeNames, centerNode.type) }}</p>
        <h1 tabindex="-1">{{ centerNode.label }}</h1>
        <p class="muted">点击节点展开它的一跳关系；点击关系查看证据。图中为来源数据中的记载关系。</p>
      </header>

      <section class="panel detail-section graph-toolbar" aria-label="图谱设置">
        <fieldset>
          <legend>只看这些关系（不选为全部）</legend>
          <label v-for="key in relationKeys" :key="key" class="check">
            <input v-model="filter" type="checkbox" :value="key" @change="reload"> {{ relationNames[key] }}
          </label>
        </fieldset>
        <p class="graph-counts" aria-live="polite">
          节点 {{ nodes.size }} / {{ MAX_NODES }}，关系 {{ edges.size }} / {{ MAX_EDGES }}
          <button type="button" class="ghost-button" @click="reload">清空并重置</button>
        </p>
        <p v-if="loaded.get(id)?.truncated" class="pager-note" role="status">
          该中心节点共 {{ number(loaded.get(id)!.total) }} 条关系，图中仅显示 {{ number(loaded.get(id)!.shown) }} 条。完整列表见<RouterLink class="text-link" :to="`/entity/${encodeURIComponent(id)}`">实体详情</RouterLink>。
        </p>
        <p v-if="capped" class="banner" role="status">画布已达到上限（{{ MAX_NODES }} 个节点或 {{ MAX_EDGES }} 条关系），部分关系未显示。请清空画布，或以其他节点为中心重新查看。</p>
        <p v-if="expanding" class="muted" role="status">正在展开…</p>
        <p v-if="expandError" class="error" role="alert">{{ expandError.message }}</p>
      </section>

      <div class="graph-layout">
        <section class="panel graph-stage" aria-label="关系图">
          <GraphCanvas :nodes="nodeList" :edges="edgeList" :center="id" :selected-node="selectedNode" :selected-edge="selectedEdge"
            @select-node="pickNode" @select-edge="pickEdge" />
        </section>

        <aside class="panel graph-side" aria-live="polite" aria-label="所选内容">
          <template v-if="selectedNodeInfo">
            <h2>{{ selectedNodeInfo.node.label }}</h2>
            <p class="muted">{{ label(typeNames, selectedNodeInfo.node.type) }}</p>
            <p v-if="selectedNodeInfo.info?.truncated" class="pager-note">
              该节点共 {{ number(selectedNodeInfo.info.total) }} 条关系，仅显示 {{ number(selectedNodeInfo.info.shown) }} 条。
              完整列表见实体详情页。
            </p>
            <p v-else-if="selectedNodeInfo.info" class="muted">已展开，共 {{ number(selectedNodeInfo.info.total) }} 条关系。</p>
            <p>
              <RouterLink class="text-link" :to="`/entity/${encodeURIComponent(selectedNodeInfo.node.id)}`">实体详情</RouterLink>
              <template v-if="selectedNodeInfo.node.id !== id">
                · <RouterLink class="text-link" :to="`/graph/${encodeURIComponent(selectedNodeInfo.node.id)}`">以此为中心</RouterLink>
              </template>
            </p>
          </template>
          <template v-else-if="selectedEdgeInfo">
            <h2>{{ name(selectedEdgeInfo.source_id) }} → {{ label(relationNames, selectedEdgeInfo.relation) }} → {{ name(selectedEdgeInfo.target_id) }}</h2>
            <p v-if="selectedEdgeInfo.quality_state === 'conflicting'" class="pager-note">⚠ 来源对这条关系的记载不一致。</p>
            <p v-for="line in dosage(selectedEdgeInfo)" :key="line" class="muted">{{ line }}</p>
            <h3>证据</h3>
            <ul v-if="selectedEdgeInfo.evidence_ids.length" class="graph-evidence">
              <li v-for="(evidenceId, i) in selectedEdgeInfo.evidence_ids" :key="evidenceId">
                <RouterLink class="text-link" :to="`/evidence/${encodeURIComponent(evidenceId)}`">证据 {{ i + 1 }}</RouterLink>
              </li>
            </ul>
            <p v-else class="muted">没有证据记录。</p>
          </template>
          <p v-else class="muted">选择图中的节点或关系，在这里查看详情。</p>
        </aside>
      </div>

      <section class="panel detail-section" aria-labelledby="legend-heading">
        <h2 id="legend-heading">图例</h2>
        <ul class="legend">
          <li v-for="relation in usedRelations" :key="relation">
            <span class="swatch" :style="{ borderTopColor: relationStyles[relation]?.color, borderTopStyle: relationStyles[relation]?.line }" aria-hidden="true"></span>
            {{ label(relationNames, relation) }}（{{ relationStyles[relation]?.lineName }}）
          </li>
        </ul>
        <ul class="legend">
          <li v-for="type in usedTypes" :key="type"><span class="dot" :style="{ background: typeColors[type] }" aria-hidden="true"></span>{{ label(typeNames, type) }}</li>
        </ul>
      </section>

      <section class="panel detail-section" aria-labelledby="list-heading">
        <h2 id="list-heading">关系列表 <span class="count">{{ edgeList.length }}</span></h2>
        <p v-if="!edgeList.length" class="empty">当前条件下没有关系。</p>
        <div v-else class="table-wrap">
          <table class="data-table">
            <caption class="sr-only">与图相同的关系列表</caption>
            <thead><tr><th scope="col">起点</th><th scope="col">关系</th><th scope="col">终点</th><th scope="col">说明</th><th scope="col">证据</th></tr></thead>
            <tbody>
              <tr v-for="e in edgeList" :key="e.id" :class="{ selected: e.id === selectedEdge }">
                <td><button type="button" class="text-button" @click="pickNode(e.source_id)">{{ name(e.source_id) }}</button></td>
                <td><button type="button" class="text-button" :aria-pressed="e.id === selectedEdge" @click="pickEdge(e.id)">{{ label(relationNames, e.relation) }}</button></td>
                <td><button type="button" class="text-button" @click="pickNode(e.target_id)">{{ name(e.target_id) }}</button></td>
                <td>
                  <span v-if="e.quality_state === 'conflicting'" class="pager-note">⚠ 来源记载不一致 </span>
                  <span v-for="line in dosage(e)" :key="line" class="muted dosage-line">{{ line }}</span>
                </td>
                <td><EvidenceLinks :ids="e.evidence_ids" /></td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </template>
  </StateView>
</template>
