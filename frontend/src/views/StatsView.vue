<script setup lang="ts">
import { onMounted, watch } from 'vue'
import { get, rememberBuild, snapshotChanged, storedBuild, useLoader } from '../api/client'
import type { DatasetPage, Health, Stats } from '../api/types'
import { label, number, projectionNames, relationNames, serviceStates, setTitle, typeNames } from '../labels'
import CopyText from '../components/CopyText.vue'
import StateView from '../components/StateView.vue'

const services = { database: '关系主库', neo4j: 'Neo4j 图库', model: '模型服务' }
// /stats and /health take no build_id, so the batch check happens here (spec §5.4).
const stats = useLoader(signal => get<Stats>('/stats', {}, { signal, pinBuild: false }))
const health = useLoader(signal => get<Health>('/health', {}, { signal, pinBuild: false, acceptStatus: [503] }))
const datasets = useLoader(signal => get<DatasetPage>('/datasets', {}, { signal }))
onMounted(() => { void stats.load(); void health.load(); void datasets.load() })
setTitle('数据统计')

watch(stats.data, value => {
  if (!value) return
  const stored = storedBuild()
  if (!stored) rememberBuild(value.build_id)
  else if (stored !== value.build_id) snapshotChanged.value = true
})
const sorted = (counts: Record<string, number>) => Object.entries(counts).sort((a, b) => b[1] - a[1])
const sum = (counts: Record<string, number>) => Object.values(counts).reduce((a, b) => a + b, 0)
</script>

<template>
  <header class="entity-header">
    <p class="eyebrow">STATISTICS</p>
    <h1 tabindex="-1">数据统计</h1>
  </header>

  <StateView :loading="stats.loading.value" :error="stats.error.value" @retry="stats.load">
    <template v-if="stats.data.value">
      <section class="stats total" aria-label="业务记录总量">
        <div>
          <span>业务记录总量</span>
          <strong>{{ number(stats.data.value.business_records) }}</strong>
          <small>实体 {{ number(stats.data.value.entities) }} + 业务关系 {{ number(stats.data.value.edges) }} = {{ number(stats.data.value.business_records) }}</small>
          <small>验收口径：去重实体 + 业务关系。证据、别名和来源记录不计入。</small>
        </div>
        <div><span>证据记录</span><strong>{{ number(stats.data.value.evidence) }}</strong><small>保留原始出处与字段定位，不计入业务记录</small></div>
      </section>

      <div class="stats-grid">
        <section class="panel" aria-labelledby="types-heading">
          <h2 id="types-heading">按实体类型</h2>
          <table>
            <thead><tr><th scope="col">类型</th><th scope="col" class="numeric">实体数</th></tr></thead>
            <tbody>
              <tr v-for="[type, count] in sorted(stats.data.value.entity_types)" :key="type"><td>{{ label(typeNames, type) }}</td><td class="numeric">{{ number(count) }}</td></tr>
            </tbody>
            <tfoot><tr><th scope="row">合计</th><td class="numeric">{{ number(sum(stats.data.value.entity_types)) }}</td></tr></tfoot>
          </table>
        </section>
        <section class="panel" aria-labelledby="relations-heading">
          <h2 id="relations-heading">按关系类型</h2>
          <table>
            <thead><tr><th scope="col">关系</th><th scope="col" class="numeric">关系数</th></tr></thead>
            <tbody>
              <tr v-for="[relation, count] in sorted(stats.data.value.relations)" :key="relation"><td>{{ label(relationNames, relation) }} <code class="muted">{{ relation }}</code></td><td class="numeric">{{ number(count) }}</td></tr>
            </tbody>
            <tfoot><tr><th scope="row">合计</th><td class="numeric">{{ number(sum(stats.data.value.relations)) }}</td></tr></tfoot>
          </table>
        </section>
      </div>
    </template>
  </StateView>

  <section class="panel detail-section" aria-labelledby="datasets-heading">
    <h2 id="datasets-heading">按来源</h2>
    <StateView :loading="datasets.loading.value" :error="datasets.error.value" @retry="datasets.load">
      <div v-if="datasets.data.value" class="table-wrap">
        <table>
          <thead><tr><th scope="col">来源</th><th scope="col" class="numeric">实体</th><th scope="col" class="numeric">业务关系</th><th scope="col" class="numeric">来源记录</th></tr></thead>
          <tbody>
            <tr v-for="d in datasets.data.value.items" :key="d.id">
              <td><RouterLink class="text-link" to="/datasets">{{ d.title }}</RouterLink></td>
              <td class="numeric">{{ number(d.counts.entities) }}</td>
              <td class="numeric">{{ number(d.counts.edges) }}</td>
              <td class="numeric">{{ number(d.counts.source_records) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p class="footnote">来源记录是导入时保留的原始记录，TCM-MKG 的来源记录数与源文件数据行数一一对应。来源记录、证据和别名都不计入业务记录总量。</p>
    </StateView>
  </section>

  <section class="panel detail-section" aria-labelledby="health-heading">
    <div class="section-heading">
      <h2 id="health-heading">运行状态</h2>
      <button type="button" class="text-button" :disabled="health.loading.value" @click="health.load">{{ health.loading.value ? '检查中…' : '刷新' }}</button>
    </div>
    <StateView :loading="health.loading.value && !health.data.value" :error="health.error.value" @retry="health.load">
      <ul v-if="health.data.value" class="services">
        <li v-for="(name, key) in services" :key="key">
          <span>{{ name }}<small v-if="key === 'neo4j'" class="muted"> · 图投影：{{ label(projectionNames, health.data.value.services.neo4j?.projection) || '未知' }}</small></span>
          <strong :class="['state', health.data.value.services[key]?.status]">{{ label(serviceStates, health.data.value.services[key]?.status) || '未知' }}</strong>
        </li>
      </ul>
      <p class="connection-note">模型连接按配置单独验证，刷新运行状态不会发起模型调用。</p>
    </StateView>
    <p v-if="stats.data.value" class="build">数据批次 <CopyText :text="stats.data.value.build_id" label="批次 ID" /></p>
  </section>
</template>
