<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { get, useLoader } from '../api/client'
import type { Direction, NeighborEdge, NeighborPage } from '../api/types'
import { label, number, roleNames, sectionTitle, typeNames } from '../labels'
import AttributeValue from './AttributeValue.vue'
import EvidenceLinks from './EvidenceLinks.vue'
import Pager from './Pager.vue'
import StateView from './StateView.vue'

const LIMIT = 20
const props = defineProps<{ entityId: string; relation: string; direction: Direction; count: number }>()
const offset = ref(0)
const { data, error, loading, load } = useLoader(signal => get<NeighborPage>(
  `/entities/${encodeURIComponent(props.entityId)}/relations`,
  { relation: props.relation, direction: props.direction, limit: LIMIT, offset: offset.value }, { signal }))
onMounted(load)
watch(offset, load)

const title = computed(() => sectionTitle(props.relation, props.direction))
const variant = computed(() => {
  if (props.relation === 'CONTAINS') return props.direction === 'out' ? 'composition' : 'formulas'
  if (props.relation === 'HAS_HERBAL_PIECE') return 'pieces'
  if (props.relation === 'HAS_MEDICINAL_PROPERTY' && props.direction === 'out') return 'properties'
  return 'generic'
})

// Keys rendered as columns or footnotes; anything else goes to the row's collapsed "边属性".
const SHOWN = new Set(['dosage_raw', 'position', 'role', 'position_source', 'missing_claim_fields', 'conflicts', 'Dosage_ratio'])
const extras = (edge: NeighborEdge) =>
  Object.fromEntries(Object.entries(edge.properties).filter(([k, v]) => !SHOWN.has(k) && v != null && v !== ''))
const hasExtras = (edge: NeighborEdge) => Object.keys(extras(edge)).length > 0
const conflicting = (edge: NeighborEdge) => edge.quality_state === 'conflicting'
const conflictValues = (edge: NeighborEdge) =>
  Object.entries((edge.properties.conflicts ?? {}) as Record<string, unknown[]>).map(([k, values]) => `${k}：${values.join(' / ')}`)

// A null claim on a conflicting edge means the sources disagree (spec §5.6), not that the value is missing.
function claim(edge: NeighborEdge, key: string, missing: string) {
  const value = edge.properties[key]
  if (value != null && value !== '') return { text: key === 'role' ? label(roleNames, String(value)) : String(value), conflict: false }
  return conflicting(edge) ? { text: '⚠ 来源记载不一致', conflict: true } : { text: missing, conflict: false }
}
const fallbackPosition = (edge: NeighborEdge) => edge.properties.position_source === 'target_id_order'
const position = (edge: NeighborEdge) =>
  fallbackPosition(edge) || typeof edge.properties.position !== 'number' ? '—' : String(edge.properties.position + 1)
const anyConflict = computed(() => data.value?.items.some(i => conflicting(i.edge)) ?? false)
const anyFallback = computed(() => data.value?.items.some(i => fallbackPosition(i.edge)) ?? false)
const entityLink = (id: string) => `/entity/${encodeURIComponent(id)}`
</script>

<template>
  <section class="relation-section" :aria-labelledby="`rel-${relation}-${direction}`">
    <h3 :id="`rel-${relation}-${direction}`">{{ title }} <span class="count">{{ number(count) }}</span></h3>
    <StateView :loading="loading" :error="error" :empty="data?.items.length === 0" empty-text="该分区暂无记录。" @retry="load">
      <div v-if="data" class="table-wrap">
        <table>
          <thead>
            <tr v-if="variant === 'composition'"><th scope="col" class="numeric">位置</th><th scope="col">药名</th><th scope="col">剂量原文</th><th scope="col">君臣佐使</th><th scope="col">证据</th></tr>
            <tr v-else-if="variant === 'formulas'"><th scope="col">方剂</th><th scope="col">分类</th><th scope="col">剂量原文</th><th scope="col">该方中的角色</th><th scope="col">证据</th></tr>
            <tr v-else-if="variant === 'pieces'"><th scope="col">名称</th><th scope="col">剂量比例原文</th><th scope="col">证据</th></tr>
            <tr v-else-if="variant === 'properties'"><th scope="col">类别</th><th scope="col">药性</th><th scope="col">证据</th></tr>
            <tr v-else><th scope="col">名称</th><th scope="col">类型</th><th scope="col">分类</th><th scope="col">证据</th></tr>
          </thead>
          <tbody>
            <tr v-for="{ edge, neighbor } in data.items" :key="edge.id" :class="{ conflicting: conflicting(edge) }">
              <td v-if="variant === 'composition'" class="numeric">{{ position(edge) }}</td>
              <td v-if="variant === 'properties'">{{ neighbor.category || '—' }}</td>
              <td>
                <RouterLink class="text-link" :to="entityLink(neighbor.id)">{{ neighbor.label }}</RouterLink>
                <span v-if="variant === 'generic' && conflicting(edge)" class="conflict"> ⚠ 来源记载不一致</span>
                <small v-for="line in conflictValues(edge)" :key="line" class="conflict block">⚠ {{ line }}</small>
                <details v-if="hasExtras(edge)" class="edge-extras"><summary>边属性</summary><AttributeValue :value="extras(edge)" /></details>
              </td>
              <template v-if="variant === 'composition' || variant === 'formulas'">
                <td v-if="variant === 'formulas'">{{ neighbor.category || '—' }}</td>
                <td :class="{ conflict: claim(edge, 'dosage_raw', '').conflict }">{{ claim(edge, 'dosage_raw', '来源未提供').text }}</td>
                <td :class="{ conflict: claim(edge, 'role', '').conflict }">{{ claim(edge, 'role', '来源未标注').text }}</td>
              </template>
              <td v-else-if="variant === 'pieces'">{{ claim(edge, 'Dosage_ratio', '来源未提供').text }}</td>
              <template v-else-if="variant === 'generic'">
                <td>{{ label(typeNames, neighbor.type) }}</td>
                <td>{{ neighbor.category || '—' }}</td>
              </template>
              <td><EvidenceLinks :ids="edge.evidence_ids" /></td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-if="anyConflict" class="footnote">⚠ 各来源对该项记载不同，未作取舍，可打开证据查看各来源原值。</p>
      <p v-if="anyFallback" class="footnote">位置为“—”的药物，排列顺序由系统补充，非来源记载。</p>
      <Pager v-if="data" :total="data.total" :limit="LIMIT" :offset="offset" :disabled="loading" @change="offset = $event" />
    </StateView>
  </section>
</template>
