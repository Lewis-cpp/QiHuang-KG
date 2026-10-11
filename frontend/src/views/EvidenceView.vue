<script setup lang="ts">
import { onMounted, watch } from 'vue'
import { get, useLoader } from '../api/client'
import type { EvidenceDetail } from '../api/types'
import { evidenceKinds, label, refocusHeading, relationNames, setTitle, typeNames } from '../labels'
import CopyText from '../components/CopyText.vue'
import StateView from '../components/StateView.vue'

const props = defineProps<{ id: string }>()
const { data, error, loading, load } = useLoader(signal => get<EvidenceDetail>(`/evidence/${encodeURIComponent(props.id)}`, {}, { signal }))
onMounted(load)
setTitle('证据')
watch(data, evidence => { if (evidence) refocusHeading() })
const entityLink = (id: string) => `/entity/${encodeURIComponent(id)}`
const json = (value: unknown) => JSON.stringify(value, null, 2)
</script>

<template>
  <h1 v-if="!data" class="page-title" tabindex="-1">证据</h1>
  <StateView :loading="loading" :error="error" invalid-is-not-found not-found-text="未找到该证据，链接可能已失效。" @retry="load">
    <template v-if="data">
      <header class="entity-header">
        <p class="eyebrow">EVIDENCE</p>
        <h1 tabindex="-1">证据<span class="tag">{{ label(evidenceKinds, data.kind) }}</span></h1>
        <p class="entity-id"><CopyText :text="data.id" label="证据 ID" /></p>
      </header>

      <section class="panel detail-section" aria-labelledby="summary-heading">
        <h2 id="summary-heading">概要</h2>
        <dl class="attributes">
          <dt>证据对象</dt>
          <dd v-if="data.target.kind === 'entity'">
            <RouterLink class="text-link" :to="entityLink(data.target.entity.id)">{{ data.target.entity.label }}</RouterLink>
            <span class="tag">{{ label(typeNames, data.target.entity.type) }}</span>
          </dd>
          <dd v-else class="edge-target">
            <RouterLink class="text-link" :to="entityLink(data.target.edge.source.id)">{{ data.target.edge.source.label }}</RouterLink>
            <span class="relation-label">{{ label(relationNames, data.target.edge.relation) }} <span aria-hidden="true">→</span></span>
            <RouterLink class="text-link" :to="entityLink(data.target.edge.target.id)">{{ data.target.edge.target.label }}</RouterLink>
          </dd>
          <dt>证据类型</dt><dd>{{ label(evidenceKinds, data.kind) }}</dd>
          <dt>字段定位</dt><dd><code>{{ data.field_path || '整条记录' }}</code></dd>
          <template v-if="data.excerpt"><dt>摘录</dt><dd class="excerpt">{{ data.excerpt }}</dd></template>
        </dl>
      </section>

      <section class="panel detail-section" aria-labelledby="raw-heading">
        <h2 id="raw-heading">原始值</h2>
        <p v-if="typeof data.raw_value === 'string'" class="raw-text">{{ data.raw_value }}</p>
        <pre v-else class="attr-json">{{ json(data.raw_value) }}</pre>
      </section>

      <section class="panel detail-section" aria-labelledby="record-heading">
        <h2 id="record-heading">来源记录</h2>
        <dl class="attributes">
          <dt>文件</dt><dd><code>{{ data.source_record.filename }}</code></dd>
          <dt>记录键</dt><dd><code>{{ data.source_record.record_key }}</code></dd>
          <dt>记录定位</dt><dd><code>{{ data.source_record.record_locator }}</code></dd>
          <dt>文件 SHA-256</dt><dd><CopyText :text="data.source_record.file_sha256" label="文件哈希" /></dd>
        </dl>
        <details class="fold">
          <summary>完整记录</summary>
          <p v-if="data.source_record.content_truncated" class="notice-text">记录超过 64 KB，已截断。</p>
          <pre class="attr-json">{{ json(data.source_record.content) }}</pre>
        </details>
      </section>

      <section class="panel detail-section" aria-labelledby="dataset-heading">
        <h2 id="dataset-heading">数据集</h2>
        <dl class="attributes">
          <dt>名称</dt><dd>{{ data.dataset.title }}</dd>
          <dt>版本</dt><dd>{{ data.dataset.version_label }}</dd>
          <dt>许可</dt><dd>{{ data.dataset.license_statement }}</dd>
          <dt>署名</dt><dd>{{ data.dataset.attribution }}</dd>
          <dt>来源地址</dt><dd><a class="text-link" :href="data.dataset.source_url" target="_blank" rel="noopener noreferrer">{{ data.dataset.source_url }}</a></dd>
        </dl>
      </section>
    </template>
  </StateView>
</template>
