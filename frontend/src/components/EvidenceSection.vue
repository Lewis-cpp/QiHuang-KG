<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { get, useLoader } from '../api/client'
import type { EvidencePage, EvidencePreview } from '../api/types'
import { evidenceKinds, label, number } from '../labels'
import Pager from './Pager.vue'
import StateView from './StateView.vue'

// Page 1 comes with the entity detail (evidence_preview); later pages use the paginated endpoint.
const LIMIT = 20
const props = defineProps<{ entityId: string; total: number; preview: EvidencePreview[] }>()
const offset = ref(0)
const { data, error, loading, load, cancel } = useLoader(signal => get<EvidencePage>(
  `/entities/${encodeURIComponent(props.entityId)}/evidence`, { limit: LIMIT, offset: offset.value }, { signal }))
watch(offset, value => value === 0 ? cancel() : load())
const items = computed(() => offset.value === 0 ? props.preview : data.value?.items ?? [])
</script>

<template>
  <section class="panel detail-section" aria-labelledby="evidence-heading">
    <h2 id="evidence-heading">证据 <span class="count">{{ number(total) }}</span></h2>
    <StateView :loading="offset > 0 && loading" :error="offset > 0 ? error : null" :empty="total === 0" empty-text="该实体没有单独的证据记录。" @retry="load">
      <ul class="evidence-items">
        <li v-for="item in items" :key="item.id">
          <RouterLink class="text-link" :to="`/evidence/${encodeURIComponent(item.id)}`">{{ label(evidenceKinds, item.kind) }}</RouterLink>
          <span class="muted">字段定位：<code>{{ item.field_path || '整条记录' }}</code></span>
          <p v-if="item.excerpt" class="excerpt">{{ item.excerpt }}</p>
        </li>
      </ul>
      <Pager :total="total" :limit="LIMIT" :offset="offset" :disabled="loading" @change="offset = $event" />
    </StateView>
  </section>
</template>
