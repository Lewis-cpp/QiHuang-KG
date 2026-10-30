<script setup lang="ts">
import { computed, onMounted, ref, shallowRef } from 'vue'
import { get, post, useLoader } from '../api/client'
import type { AICondition, AIQueryResult, Health } from '../api/types'
import { label, number, setTitle, typeNames } from '../labels'
import EntityHitItem from '../components/EntityHitItem.vue'
import StateView from '../components/StateView.vue'

const MAX_LENGTH = 200
const examples = ['含甘草的补益剂', '出自宋代的方剂', '含冰片的外用中成药']
setTitle('AI 条件查询')

// Not kept in the URL: a refresh or a shared link would otherwise repeat a billed model call.
const question = ref('')
const request = shallowRef<Record<string, unknown>>({})
const choices = ref<Record<string, string>>({})
// A resubmission sends only resolved conditions; keep showing what the original question could not run.
const carried = ref<string[]>([])
const unsupported = computed(() => [...new Set([...carried.value, ...(data.value?.unsupported ?? [])])])
const { data, error, loading, load } = useLoader(signal => post<AIQueryResult>('/ai/query', request.value, { signal }))
const health = useLoader(signal => get<Health>('/health', {}, { signal, pinBuild: false, acceptStatus: [503] }))
onMounted(() => void health.load())
const modelReady = computed(() => !health.data.value || health.data.value.services.model?.status === 'verified')

const key = (item: { field: string; value: string }) => `${item.field}\u0000${item.value}`
const ready = computed(() => (data.value?.candidates ?? []).every(group => choices.value[key(group)]))

function submit(body: Record<string, unknown>, keep: string[] = []) {
  request.value = body
  choices.value = {}
  carried.value = keep
  void load()
}
function ask(text = question.value) {
  question.value = text
  if (text.trim()) submit({ question: text.trim() })
}
// The chosen candidates go back as conditions; the backend checks them again and does not call the model.
function resubmit(result: AIQueryResult) {
  const conditions = result.conditions.map((item: AICondition) => ({
    field: item.field, value: item.value, entity_id: item.entity_id ?? choices.value[key(item)] ?? null,
  }))
  submit({ target_type: result.target_type, conditions }, unsupported.value)
}
</script>

<template>
  <header class="entity-header">
    <p class="eyebrow">AI QUERY</p>
    <h1 tabindex="-1">AI 条件查询</h1>
    <p class="note-lead">用一句话描述要找的方剂、中药或中成药。模型只把问题转换为下方列出的条件，查询由系统按条件执行。</p>
  </header>

  <section class="panel" aria-labelledby="ai-heading">
    <div class="section-heading"><h2 id="ai-heading">提问</h2></div>
    <p v-if="!modelReady" class="notice-text" role="status">模型未就绪：{{ health.data.value?.services.model?.message || '尚未完成真实调用验证' }}。仍可尝试提交。</p>
    <form class="search" @submit.prevent="ask()">
      <label class="sr-only" for="question">问题</label>
      <input id="question" v-model="question" :maxlength="MAX_LENGTH" placeholder="例如：含甘草的补益剂" />
      <button type="submit" :disabled="loading || !question.trim()">{{ loading ? '查询中…' : '查询' }}</button>
    </form>
    <div class="examples">
      <span class="muted">试试：</span>
      <button v-for="example in examples" :key="example" type="button" class="chip" :disabled="loading" @click="ask(example)">{{ example }}</button>
    </div>
    <p class="muted">{{ question.length }} / {{ MAX_LENGTH }} 字 · 内容依据所列资料生成，仅供学习参考，不构成用药建议。</p>

    <StateView v-if="loading || error || data" :loading="loading" :error="error" @retry="load">
      <template v-if="data">
        <section class="detail-section" aria-labelledby="executed-heading">
          <h3 id="executed-heading">实际执行的条件{{ typeNames[data.target_type] ? ` · ${typeNames[data.target_type]}` : "" }}</h3>
          <ul v-if="data.conditions.length" class="examples" aria-label="条件">
            <li v-for="item in data.conditions" :key="key(item)" class="chip">{{ item.label }}</li>
          </ul>
          <p v-else class="muted">没有可执行的条件。</p>
          <p v-if="unsupported.length" class="notice-text">未支持、未执行：{{ unsupported.join('；') }}</p>
        </section>

        <form v-if="data.status === 'ambiguous'" @submit.prevent="resubmit(data)">
          <fieldset v-for="group in data.candidates" :key="key(group)" class="choices">
            <legend>“{{ group.value }}”对应多个条目，请选择一个：</legend>
            <label v-for="item in group.items" :key="item.id" class="choice">
              <input v-model="choices[key(group)]" type="radio" :name="key(group)" :value="item.id" />
              {{ item.label }} <span class="tag">{{ label(typeNames, item.type) }}</span>
              <span class="muted">{{ item.category || '来源未提供分类' }} · {{ item.id }}</span>
            </label>
          </fieldset>
          <button type="submit" class="ghost-button" :disabled="!ready || loading">按所选条目查询</button>
        </form>

        <section v-if="data.suggestions" class="detail-section">
          <div v-for="group in data.suggestions" :key="key(group)">
            <p>库中没有名为“{{ group.value }}”的条目，未执行查询。</p>
            <p v-if="group.items.length">你是否要找：
              <RouterLink v-for="item in group.items" :key="item.id" class="chip" :to="`/entity/${encodeURIComponent(item.id)}`">{{ item.label }}</RouterLink>
            </p>
          </div>
        </section>

        <p v-if="data.status === 'unsupported'" class="empty">问题不在支持范围内，或条件相互矛盾，未执行查询。</p>

        <template v-if="data.results">
          <p v-if="data.coverage_note" class="notice-text">{{ data.coverage_note }}</p>
          <p class="results-meta">找到 {{ number(data.results.total) }} 条记录<span v-if="data.results.total > data.results.items.length">，显示前 {{ data.results.items.length }} 条</span></p>
          <ul v-if="data.results.items.length" class="results">
            <EntityHitItem v-for="item in data.results.items" :key="item.id" :item="item" />
          </ul>
          <p v-else class="empty">没有符合全部条件的记录。</p>
        </template>
      </template>
    </StateView>
  </section>
</template>
