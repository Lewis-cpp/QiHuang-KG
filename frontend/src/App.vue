<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

type Entity = { id: string; label: string; type: string; dataset_id: string; category: string | null; review_status: string }
type Stats = { entities: number; edges: number; evidence: number; business_records: number; build_id: string }
type Service = { status: string; message?: string; projection?: string; version?: string }
type Health = { status: string; services: Record<string, Service> }
type Graph = { build_id: string; scope: string; nodes: { id: string; label: string; type: string }[]; edges: { id: string; source_id: string; target_id: string; relation: string; evidence_ids: string[] }[] }

const typeNames: Record<string, string> = { herb: '中药', formula: '经典方剂', pattern: '证候', text: '古籍', tcm_term: '中医术语', patent_medicine: '中成药', herbal_piece: '中药饮片', icd11_code: 'ICD-11 编码', medicinal_property: '药性' }
const stateNames: Record<string, string> = { ready: '连接正常', verified: '调用已验证', not_configured: '尚未配置', not_verified: '等待验证', unavailable: '暂不可用' }
const reviewNames: Record<string, string> = { editor_reviewed: '编辑已审核', draft: '草稿', needs_review: '待审核', unknown: '来源提供 · 未审核' }
const stats = ref<Stats | null>(null)
const health = ref<Health | null>(null)
const graph = ref<Graph | null>(null)
const q = ref('四君子汤')
const kind = ref('')
const items = ref<Entity[]>([])
const total = ref(0)
const loading = ref(false)
const refreshing = ref(false)
const searchError = ref('')
const statusError = ref('')
const graphError = ref('')
let searchController: AbortController | undefined
const number = (n: number | undefined) => n === undefined ? '—' : n.toLocaleString('zh-CN')
const graphLabels = computed(() => new Map(graph.value?.nodes.map(n => [n.id, n.label])))
const graphRows = computed(() => graph.value?.edges.map(e => ({ ...e, source: graphLabels.value.get(e.source_id), target: graphLabels.value.get(e.target_id) })) ?? [])

async function get<T>(url: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(url, { signal })
  if (!response.ok) throw new Error(`请求未完成（HTTP ${response.status}），请检查服务后重试。`)
  return response.json()
}
async function refresh() {
  refreshing.value = true
  statusError.value = ''
  try {
    const [s, h] = await Promise.all([get<Stats>('/api/v1/stats'), get<Health>('/api/v1/health')])
    stats.value = s
    health.value = h
  } catch (e) {
    stats.value = null
    health.value = null
    statusError.value = (e as Error).message
  } finally { refreshing.value = false }
}
async function search() {
  searchController?.abort()
  const controller = new AbortController()
  searchController = controller
  loading.value = true
  searchError.value = ''
  try {
    const params = new URLSearchParams({ q: q.value, limit: '20' })
    if (kind.value) params.set('type', kind.value)
    const result = await get<{ items: Entity[]; total: number }>(`/api/v1/entities?${params}`, controller.signal)
    items.value = result.items
    total.value = result.total
  } catch (e) {
    if ((e as Error).name !== 'AbortError') {
      searchError.value = (e as Error).message
      items.value = []
    }
  } finally { if (searchController === controller) loading.value = false }
}
async function loadGraph() {
  graphError.value = ''
  try { graph.value = await get<Graph>('/api/v1/graph/sample') }
  catch (e) { graph.value = null; graphError.value = (e as Error).message }
}
onMounted(() => { void refresh(); void search(); void loadGraph() })
</script>

<template>
  <div class="shell">
    <header>
      <a class="brand" href="#top"><span class="seal" aria-hidden="true">岐</span><span>岐黄知图<small>QIHUANG KNOWLEDGE GRAPH</small></span></a>
      <nav aria-label="页面导航"><a href="#knowledge">知识检索</a><a href="#sample">关系样例</a><a href="#connections">运行状态</a></nav>
      <span class="preview">开发预览 · 0.1</span>
    </header>
    <main id="top">
      <section class="intro">
        <div><p class="eyebrow">有出处的知识，有脉络的理解</p><h1>从一味药，<br>读懂知识的关联。</h1><p class="intro-copy">检索中医药资料，追溯方剂组成与知识来源。<br>本草典与 TCM-MKG 两源数据已接入。</p></div>
        <aside class="intro-note"><span class="note-number">01 / 基础链路</span><h2>从真实数据开始</h2><p>名称检索、数据统计与样例关系已连接数据库。完整详情、图谱探索与 AI 解释将在后续阶段实现。</p><a href="#knowledge">开始检索 <span aria-hidden="true">↓</span></a></aside>
      </section>
      <section class="stats" aria-label="当前知识库统计">
        <div><span>知识实体</span><strong>{{ number(stats?.entities) }}</strong><small>九类实体，各自保留来源</small></div>
        <div><span>业务关系</span><strong>{{ number(stats?.edges) }}</strong><small>去重后的有效关系</small></div>
        <div><span>证据记录</span><strong>{{ number(stats?.evidence) }}</strong><small>保留原始出处与字段定位</small></div>
        <div><span>业务记录总量</span><strong>{{ number(stats?.business_records) }}</strong><small>实体与关系合计</small></div>
      </section>
      <div class="workspace">
        <section id="knowledge" class="panel knowledge">
          <div class="section-heading"><div><p class="eyebrow">KNOWLEDGE INDEX</p><h2>知识检索</h2></div><span class="muted">名称与来源别名</span></div>
          <form class="search" @submit.prevent="search">
            <label class="sr-only" for="query">搜索名称</label><input id="query" v-model="q" maxlength="100" placeholder="输入方剂、中药或术语名称" />
            <label class="sr-only" for="kind">实体类型</label><select id="kind" v-model="kind"><option value="">全部类型</option><option v-for="(label, value) in typeNames" :key="value" :value="value">{{ label }}</option></select>
            <button type="submit" :disabled="loading">{{ loading ? '检索中…' : '检索' }}</button>
          </form>
          <p v-if="searchError" role="alert" class="error">{{ searchError }}</p>
          <div v-else aria-live="polite" :aria-busy="loading">
            <p class="results-meta">找到 {{ number(total) }} 条记录<span v-if="total > 20"> · 当前显示前 20 条，请细化关键词</span></p>
            <ul class="results"><li v-for="item in items" :key="item.id"><div><h3>{{ item.label }}<span class="tag">{{ typeNames[item.type] }}</span></h3><p>{{ item.category || '来源未提供分类' }}</p></div><span class="source">{{ item.dataset_id === 'bencaodian' ? '本草典' : 'TCM-MKG' }}<small>{{ reviewNames[item.review_status] ?? '状态未提供' }}</small></span></li></ul>
            <p v-if="!items.length && !loading" class="empty">没有找到匹配记录，试试其他名称或类型。</p>
          </div>
        </section>
        <aside id="connections" class="panel connections">
          <div class="section-heading"><h2>运行状态</h2><button class="text-button" :disabled="refreshing" @click="refresh">{{ refreshing ? '检查中…' : '刷新' }}</button></div>
          <p v-if="statusError" role="alert" class="error">{{ statusError }}</p>
          <ul v-else class="services"><li v-for="(label, key) in { database: 'PostgreSQL 主库', neo4j: 'Neo4j 图库', model: '模型服务' }" :key="key"><span>{{ label }}</span><strong :class="['state', health?.services[key]?.status]">{{ stateNames[health?.services[key]?.status ?? ''] ?? '连接检查中' }}</strong></li></ul>
          <p class="connection-note">模型连接按配置单独验证。刷新运行状态不会发起模型调用。</p>
          <p v-if="stats" class="build">数据批次 <code>{{ stats.build_id.slice(0, 12) }}</code></p>
        </aside>
      </div>
      <section id="sample" class="panel sample">
        <div class="section-heading"><div><p class="eyebrow">RELATION SAMPLE</p><h2>四君子汤 · 关系样例</h2></div><button class="text-button" @click="loadGraph">刷新关系</button></div>
        <p class="muted">从同批次主库生成的小范围图投影，用于验证组成与证候关联；完整图谱尚未开放。</p>
        <p v-if="graphError" role="alert" class="error">{{ graphError }}</p>
        <ul v-else class="relations"><li v-for="edge in graphRows" :key="edge.id"><span>{{ edge.source }}</span><span class="relation-label">{{ edge.relation === 'CONTAINS' ? '包含' : '关联证候' }} <span aria-hidden="true">→</span></span><strong>{{ edge.target }}</strong><small>{{ edge.evidence_ids.length }} 条来源证据</small></li></ul>
      </section>
    </main>
    <footer><span>岐黄知图 · 资料检索与学习</span><span>保留来源差异，支持回查证据。</span></footer>
  </div>
</template>
