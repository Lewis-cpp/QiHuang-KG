<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { get, useLoader } from '../api/client'
import type { RelationPage } from '../api/types'
import Pager from './Pager.vue'
import StateView from './StateView.vue'

// spec §6.3: the two-hop template is answered by Neo4j; the wording stays the fixed note from the API.
const LIMIT = 20
const props = defineProps<{ herbId: string }>()
const emit = defineEmits<{ show: [page: RelationPage] }>()
const offset = ref(0)
const { data, error, loading, load } = useLoader(signal => get<RelationPage>('/graph/paths',
  { template: 'herb_patterns_via_formula', entity_id: props.herbId, limit: LIMIT, offset: offset.value }, { signal }))
onMounted(load)
watch(offset, load)
const entityLink = (id: string) => `/entity/${encodeURIComponent(id)}`
</script>

<template>
  <section class="panel detail-section" aria-labelledby="paths-heading">
    <h2 id="paths-heading">经方剂关联的证候 <span v-if="data" class="count">{{ data.total }}</span></h2>
    <StateView :loading="loading" :error="error" :empty="data?.total === 0" empty-text="来源数据中没有经方剂关联到证候的路径。" @retry="load">
      <template v-if="data">
        <p class="notice-text">{{ data.note }}。这里列出的是数据中的连接，不表示该药治疗该证候。路径由图数据库查询。</p>
        <ol class="path-list" :start="data.offset + 1">
          <li v-for="path in data.paths" :key="path.edge_ids.join()">
            <template v-for="(id, i) in path.node_ids" :key="id">
              <span v-if="i" class="path-arrow" aria-hidden="true">{{ i === 1 ? '←包含—' : '—关联证候→' }}</span>
              <span v-if="i" class="sr-only">{{ i === 1 ? '被以下方剂包含：' : '该方剂关联证候：' }}</span>
              <RouterLink class="text-link" :to="entityLink(id)">{{ data.nodes[id].label }}</RouterLink>
            </template>
          </li>
        </ol>
        <div class="path-actions">
          <button type="button" class="ghost-button" @click="emit('show', data)">在图中显示本页 {{ data.paths.length }} 条路径</button>
          <Pager :total="data.total" :limit="data.limit" :offset="data.offset" :disabled="loading" @change="offset = $event" />
        </div>
      </template>
    </StateView>
  </section>
</template>
