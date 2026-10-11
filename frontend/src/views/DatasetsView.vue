<script setup lang="ts">
import { onMounted } from 'vue'
import { get, useLoader } from '../api/client'
import type { DatasetPage } from '../api/types'
import { number, setTitle } from '../labels'
import StateView from '../components/StateView.vue'

const { data, error, loading, load } = useLoader(signal => get<DatasetPage>('/datasets', {}, { signal }))
onMounted(load)
setTitle('数据来源')
</script>

<template>
  <header class="entity-header">
    <p class="eyebrow">DATASETS</p>
    <h1 tabindex="-1">数据来源</h1>
  </header>
  <StateView :loading="loading" :error="error" :empty="data?.total === 0" empty-text="当前批次没有登记来源。" @retry="load">
    <div v-if="data" class="dataset-grid">
      <article v-for="dataset in data.items" :key="dataset.id" class="panel dataset-card" :aria-labelledby="`ds-${dataset.id}`">
        <h2 :id="`ds-${dataset.id}`">{{ dataset.title }}</h2>
        <p class="muted"><code>{{ dataset.id }}</code> · {{ dataset.version_label }}</p>
        <dl class="counts">
          <div><dt>实体</dt><dd>{{ number(dataset.counts.entities) }}</dd></div>
          <div><dt>关系</dt><dd>{{ number(dataset.counts.edges) }}</dd></div>
          <div><dt>来源记录</dt><dd>{{ number(dataset.counts.source_records) }}</dd></div>
        </dl>
        <dl class="attributes">
          <dt>来源地址</dt><dd><a class="text-link" :href="dataset.source_url" target="_blank" rel="noopener noreferrer">{{ dataset.source_url }}</a></dd>
          <dt>许可</dt><dd>{{ dataset.license_statement }}</dd>
          <dt>署名</dt><dd>{{ dataset.attribution }}</dd>
        </dl>
      </article>
    </div>
    <p class="footnote">公开交付前需逐项核对各来源的原始使用条件。</p>
  </StateView>
</template>
