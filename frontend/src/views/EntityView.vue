<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { get, useLoader } from '../api/client'
import type { EntityDetail } from '../api/types'
import { attributeSections } from '../attributes'
import { label, refocusHeading, relationSections, reviewNames, setTitle, typeNames } from '../labels'
import AttributeValue from '../components/AttributeValue.vue'
import CopyText from '../components/CopyText.vue'
import EvidenceSection from '../components/EvidenceSection.vue'
import FormulaNotes from '../components/FormulaNotes.vue'
import RelationSection from '../components/RelationSection.vue'
import StateView from '../components/StateView.vue'

const ALIAS_PREVIEW = 20
const props = defineProps<{ id: string }>()
const { data, error, loading, load } = useLoader(signal => get<EntityDetail>(`/entities/${encodeURIComponent(props.id)}`, {}, { signal }))
onMounted(load)
setTitle('实体详情')
watch(data, entity => {
  if (!entity) return
  setTitle(entity.label)
  refocusHeading()
})

const allAliases = ref(false)
const aliases = computed(() => {
  const list = data.value?.aliases ?? []
  return allAliases.value ? list : list.slice(0, ALIAS_PREVIEW)
})
const sections = computed(() => data.value ? attributeSections(data.value.type, data.value.attributes) : null)
const order = (relation: string) => {
  const index = relationSections.findIndex(s => s.relation === relation)
  return index < 0 ? relationSections.length : index
}
const relations = computed(() => (data.value?.relation_summary ?? [])
  .filter(r => r.count > 0)
  .sort((a, b) => order(a.relation) - order(b.relation) || (a.direction === 'out' ? -1 : 1) - (b.direction === 'out' ? -1 : 1)))
</script>

<template>
  <h1 v-if="!data" class="page-title" tabindex="-1">实体详情</h1>
  <StateView :loading="loading" :error="error" invalid-is-not-found not-found-text="未找到该实体，链接可能已失效。" @retry="load">
    <template v-if="data && sections">
      <header class="entity-header">
        <p class="eyebrow">{{ label(typeNames, data.type) }}</p>
        <h1 tabindex="-1">{{ data.label }}<span class="tag">{{ label(typeNames, data.type) }}</span></h1>
        <p class="entity-meta">
          <span>{{ data.dataset.title }}</span>
          <span>{{ label(reviewNames, data.review_status) || '状态未提供' }}</span>
          <span>{{ data.category || '来源未提供分类' }}</span>
        </p>
        <p class="entity-id"><CopyText :text="data.id" label="实体 ID" /></p>
      </header>

      <section v-if="data.type === 'herbal_piece' || data.same_name_entities.length" class="panel detail-section" aria-labelledby="same-name-heading">
        <h2 id="same-name-heading">同名条目</h2>
        <p v-if="data.same_name_entities.length">
          {{ data.type === 'herb' ? '另一来源中有同名饮片：' : '本草典中有同名药材，含功效、主治与安全信息：' }}
          <RouterLink v-for="item in data.same_name_entities" :key="item.id" class="text-link" :to="`/entity/${encodeURIComponent(item.id)}`">{{ item.label }}（{{ label(typeNames, item.type) }}）</RouterLink>
        </p>
        <p v-else class="muted">该来源只提供名称、同义词与分类，不含功效和主治；本草典中没有可唯一对应的同名药材。</p>
      </section>

      <section v-if="data.aliases.length" class="panel detail-section" aria-labelledby="alias-heading">
        <h2 id="alias-heading">别名 <span class="count">{{ data.aliases.length }}</span></h2>
        <ul class="alias-list"><li v-for="alias in aliases" :key="`${alias.name}|${alias.source_record_id}|${alias.field_path}`">{{ alias.name }}</li></ul>
        <button v-if="data.aliases.length > ALIAS_PREVIEW" type="button" class="text-button" @click="allAliases = !allAliases">{{ allAliases ? '收起' : '展开全部' }}</button>
      </section>

      <section class="panel detail-section" aria-labelledby="attr-heading">
        <h2 id="attr-heading">属性</h2>
        <dl class="attributes">
          <template v-for="row in sections.main" :key="row.key">
            <dt :id="`attr-${row.key}`">{{ row.label }}</dt>
            <dd v-if="row.missing" class="muted">来源未提供</dd>
            <dd v-else>
              <AttributeValue :value="row.value" :field="row.key" />
              <small v-if="typeof row.secondary === 'string'" class="secondary">{{ row.secondary }}</small>
            </dd>
          </template>
        </dl>
        <details v-for="row in sections.collapsed" :key="row.key" class="fold">
          <summary>{{ row.label }}</summary>
          <AttributeValue :value="row.value" :field="row.key" />
        </details>
        <details v-if="sections.other.length" class="fold">
          <summary>其他属性（{{ sections.other.length }}）</summary>
          <dl class="attributes">
            <template v-for="row in sections.other" :key="row.key">
              <dt><code>{{ row.label }}</code></dt>
              <dd>
                <AttributeValue :value="row.value" :field="row.key" />
                <small v-if="typeof row.secondary === 'string'" class="secondary">{{ row.secondary }}</small>
              </dd>
            </template>
          </dl>
        </details>
      </section>

      <FormulaNotes v-if="data.type === 'formula'" :entity-id="data.id" />

      <section v-if="sections.safety.length" class="panel detail-section notice" aria-labelledby="safety-heading">
        <h2 id="safety-heading">来源中的注意事项</h2>
        <p class="notice-text">以下为来源原文，仅供学习参考，不构成用药建议。</p>
        <dl class="attributes">
          <template v-for="row in sections.safety" :key="row.key">
            <dt>{{ row.label }}</dt>
            <dd>
              <AttributeValue v-if="!row.missing" :value="row.value" :field="row.key" />
              <small v-if="typeof row.secondary === 'string'" class="secondary">{{ row.secondary }}</small>
            </dd>
          </template>
        </dl>
      </section>

      <section v-if="relations.length" class="panel detail-section" aria-labelledby="relations-heading">
        <h2 id="relations-heading">关系</h2>
        <RelationSection v-for="r in relations" :key="`${r.relation}-${r.direction}`" :entity-id="data.id"
          :relation="r.relation" :direction="r.direction" :count="r.count" />
      </section>

      <EvidenceSection :entity-id="data.id" :total="data.evidence_total" :preview="data.evidence_preview" />
    </template>
  </StateView>
</template>
