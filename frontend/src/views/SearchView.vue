<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter, type LocationQuery } from 'vue-router'
import { get, useLoader } from '../api/client'
import type { EntityPage } from '../api/types'
import { datasetNames, label, number, reviewNames, setTitle, typeNames } from '../labels'
import Pager from '../components/Pager.vue'
import StateView from '../components/StateView.vue'

const LIMIT = 20
const MAX_PAGE = Math.floor(10000 / LIMIT) + 1
const examples = ['四君子汤', '甘草', '猪苓汤']
const route = useRoute()
const router = useRouter()

// The URL is the search state, so back/forward and refresh restore the same results (spec §5.5).
const one = (value: LocationQuery[string]) => (Array.isArray(value) ? value[0] : value) ?? ''
const criteria = computed(() => {
  const page = Math.min(MAX_PAGE, Math.max(1, Number.parseInt(one(route.query.page), 10) || 1))
  return {
    q: one(route.query.q).slice(0, 100),
    type: typeNames[one(route.query.type)] ? one(route.query.type) : '',
    dataset: datasetNames[one(route.query.dataset)] ? one(route.query.dataset) : '',
    page,
  }
})
const idle = computed(() => !criteria.value.q.trim() && !criteria.value.type)
const form = ref({ q: '', type: '', dataset: '' })

const { data, error, loading, load, cancel } = useLoader(signal => get<EntityPage>('/entities', {
  q: criteria.value.q, type: criteria.value.type, dataset: criteria.value.dataset,
  limit: LIMIT, offset: (criteria.value.page - 1) * LIMIT,
}, { signal }))

watch(criteria, value => {
  form.value = { q: value.q, type: value.type, dataset: value.dataset }
  setTitle(value.q ? `检索“${value.q}”` : '知识检索')
  if (idle.value) cancel()
  else void load()
}, { immediate: true })

function navigate(state: { q: string; type: string; dataset: string }, page = 1, replace = false) {
  const query: Record<string, string> = {}
  if (state.q.trim()) query.q = state.q.trim()
  if (state.type) query.type = state.type
  if (state.dataset) query.dataset = state.dataset
  if (page > 1) query.page = String(page)
  void (replace ? router.replace : router.push)({ path: '/', query })
}
const apply = () => navigate(form.value)

// A page past the end (e.g. a stale link) moves to the last page that has results.
watch(data, result => {
  if (result && !result.items.length && result.total > 0 && criteria.value.page > 1) {
    navigate(criteria.value, Math.min(MAX_PAGE, Math.ceil(result.total / LIMIT)), true)
  }
})
</script>

<template>
  <section class="intro" :class="{ compact: !idle }">
    <div>
      <p class="eyebrow">有出处的知识，有脉络的理解</p>
      <h1 tabindex="-1">从一味药，<br v-if="idle">读懂知识的关联。</h1>
      <p v-if="idle" class="intro-copy">检索方剂、中药、中成药、饮片与术语，查看组成、关联与每一条来源证据。<br>本草典与 TCM-MKG 两源数据已接入。</p>
    </div>
    <aside v-if="idle" class="intro-note">
      <span class="note-number">资料检索</span>
      <h2>从真实数据开始</h2>
      <p>名称和来源别名都能检索。详情页列出属性、关系和证据，证据可以追溯到来源文件的具体字段。</p>
      <RouterLink to="/stats">查看数据统计 <span aria-hidden="true">→</span></RouterLink>
    </aside>
  </section>

  <section class="panel knowledge" aria-labelledby="search-heading">
    <div class="section-heading">
      <div><p class="eyebrow">KNOWLEDGE INDEX</p><h2 id="search-heading">知识检索</h2></div>
      <span class="muted">名称与来源别名</span>
    </div>
    <form class="search" role="search" @submit.prevent="apply()">
      <label class="sr-only" for="query">关键词</label>
      <input id="query" v-model="form.q" maxlength="100" placeholder="输入方剂、中药或术语名称" />
      <label class="sr-only" for="kind">实体类型</label>
      <select id="kind" v-model="form.type" @change="apply()">
        <option value="">全部类型</option>
        <option v-for="(name, value) in typeNames" :key="value" :value="value">{{ name }}</option>
      </select>
      <label class="sr-only" for="dataset">来源</label>
      <select id="dataset" v-model="form.dataset" @change="apply()">
        <option value="">全部来源</option>
        <option v-for="(name, value) in datasetNames" :key="value" :value="value">{{ name }}</option>
      </select>
      <button type="submit" :disabled="loading">{{ loading ? '检索中…' : '检索' }}</button>
    </form>

    <div v-if="idle" class="examples">
      <span class="muted">试试：</span>
      <RouterLink v-for="example in examples" :key="example" class="chip" :to="{ path: '/', query: { q: example } }">{{ example }}</RouterLink>
    </div>
    <StateView v-else :loading="loading" :error="error" :empty="data?.total === 0"
      empty-text="没有找到匹配记录，试试换个关键词，或去掉类型和来源筛选。" @retry="load">
      <template v-if="data">
        <p class="results-meta">找到 {{ number(data.total) }} 条记录</p>
        <ul class="results">
          <li v-for="item in data.items" :key="item.id">
            <div>
              <h3><RouterLink :to="`/entity/${encodeURIComponent(item.id)}`">{{ item.label }}</RouterLink><span class="tag">{{ label(typeNames, item.type) }}</span></h3>
              <p>
                {{ item.category || '来源未提供分类' }}
                <span v-if="item.match" class="match">· {{ item.match.field === 'name' ? '名称命中' : `别名命中：${item.match.text}` }}</span>
                · <RouterLink class="text-link" :to="`/graph/${encodeURIComponent(item.id)}`" :aria-label="`${item.label} 关系图谱`">图谱</RouterLink>
              </p>
            </div>
            <span class="source">{{ label(datasetNames, item.dataset_id) }}<small>{{ label(reviewNames, item.review_status) || '状态未提供' }}</small></span>
          </li>
        </ul>
        <Pager :total="data.total" :limit="LIMIT" :offset="(criteria.page - 1) * LIMIT" :disabled="loading" @change="navigate(criteria, $event / LIMIT + 1)" />
      </template>
    </StateView>
  </section>
</template>
