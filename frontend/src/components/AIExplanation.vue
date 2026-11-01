<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { get, post, useLoader } from '../api/client'
import type { AIExplanation, ExplainSentence, Health } from '../api/types'
import EvidenceLinks from './EvidenceLinks.vue'

// Requested only by an explicit click: every generation is a billed model call.
const props = defineProps<{ entityId: string }>()
const { data, error, loading, load } = useLoader(signal =>
  post<AIExplanation>('/ai/explain', { entity_id: props.entityId }, { signal }))
const health = useLoader(signal => get<Health>('/health', {}, { signal, pinBuild: false, acceptStatus: [503] }))
onMounted(() => void health.load())
const modelReady = computed(() => !health.data.value || health.data.value.services.model?.status === 'verified')

const requested = ref(false)
function generate() {
  requested.value = true
  void load()
}
const evidenceFor = (sentence: ExplainSentence, index: number) =>
  data.value?.materials.find(m => m.ref === sentence.refs[index])?.evidence_ids ?? []
// One open evidence list at a time; refs with a single evidence link navigate directly instead.
const opened = ref<string | null>(null)
const toggle = (key: string) => { opened.value = opened.value === key ? null : key }
</script>

<template>
  <section class="panel detail-section" aria-labelledby="ai-explain-heading">
    <h2 id="ai-explain-heading">AI 解释</h2>
    <p v-if="!modelReady" class="notice-text" role="status">模型未就绪：{{ health.data.value?.services.model?.message || '尚未完成真实调用验证' }}。仍可尝试生成。</p>
    <p v-if="!requested" class="muted">依据本页材料生成带引用的解释，由你点击后才发起。</p>
    <button type="button" class="ghost-button" :disabled="loading" @click="generate">
      {{ loading ? '生成中…' : requested ? '重新生成' : '生成 AI 解释' }}</button>

    <div v-if="error && error.status !== 409" class="error" role="alert">
      <p>{{ error.message }}</p>
      <button type="button" class="ghost-button" @click="generate">重试</button>
    </div>

    <template v-if="data">
      <p v-if="data.status === 'explanation_unavailable'" class="error" role="alert">
        未能生成通过校验的解释{{ data.failure?.length ? '：' : '。' }}
        <template v-if="data.failure?.length">{{ data.failure.join('；') }}</template>
      </p>
      <template v-else>
        <section v-for="section in data.sections" :key="section.heading" class="explain-section">
          <h3>{{ section.heading }}</h3>
          <p v-for="(sentence, s) in section.sentences" :key="s" class="explain-sentence">
            {{ sentence.text }}
            <template v-for="(ref, r) in sentence.refs" :key="ref">
              <RouterLink v-if="evidenceFor(sentence, r).length === 1" class="ref-badge"
                :to="`/evidence/${encodeURIComponent(evidenceFor(sentence, r)[0])}`">[{{ r + 1 }}]</RouterLink>
              <template v-else>
                <button type="button" class="ref-badge" :aria-expanded="opened === `${s}-${r}`"
                  @click="toggle(`${s}-${r}`)">[{{ r + 1 }}]</button>
                <span v-if="opened === `${s}-${r}`" class="ref-evidence">
                  <EvidenceLinks :ids="evidenceFor(sentence, r)" />
                </span>
              </template>
            </template>
          </p>
        </section>
        <section v-if="data.insufficient.length" class="explain-insufficient">
          <h3>资料未覆盖的方面</h3>
          <ul><li v-for="note in data.insufficient" :key="note">{{ note }}</li></ul>
        </section>
      </template>
      <p class="footnote">内容依据所列资料生成，仅供学习参考，不构成用药建议。</p>
    </template>
  </section>
</template>
