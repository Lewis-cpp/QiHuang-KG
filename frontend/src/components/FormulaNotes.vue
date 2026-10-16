<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { get, useLoader } from '../api/client'
import type { FormulaNotes, NoteSource } from '../api/types'
import EvidenceLinks from './EvidenceLinks.vue'
import StateView from './StateView.vue'

// Source text copied from the formula's linked patterns and herbs; the formula record has neither field itself.
const props = defineProps<{ entityId: string }>()
const { data, error, loading, load } = useLoader(signal =>
  get<FormulaNotes>(`/entities/${encodeURIComponent(props.entityId)}/formula-notes`, {}, { signal }))
onMounted(load)

type Bilingual = { zh?: string; en?: string }
const zh = (value: unknown) => (value as Bilingual | undefined)?.zh ?? ''
const symptoms = (value: unknown) => ((value ?? []) as Bilingual[]).map(s => s.zh).filter(Boolean).join('；')

const STATUS: Record<string, string> = { contraindicated: '禁用', avoid: '忌用', caution: '慎用' }
const TEXT_FIELDS: [string, string][] = [['contraindications', '禁忌'], ['safety_notes', '安全提示']]
const GROUP_FIELDS: [string, string][] = [['pregnancy', '孕期'], ['lactation', '哺乳期'], ['pediatric', '儿童']]

// Dosage notes mostly say how to decoct; only those with safety wording count as a precaution.
// Phrases, not single characters: "解毒" and "无毒" must not match, while "仅供外用" and "宜减量" must.
const SAFETY_WORDING = /有毒|小毒|大毒|毒性|中毒|毒大|十八反|十九畏|禁用|禁服|严禁|忌用|忌服|尤忌|孕妇|妊娠|慎用|慎服|过量|超量|不宜过大|用量过大|剂量不可过大|严格控制|严格炮制|不宜久服|不可长期|不宜生食|仅供外用|减量/

interface Row { label: string; text: string; secondary?: string }
function herbRows(herb: NoteSource): Row[] {
  const f = herb.fields
  const rows: Row[] = []
  for (const [key, label] of TEXT_FIELDS) {
    if (typeof f[`${key}_zh`] === 'string') rows.push({ label, text: f[`${key}_zh`] as string, secondary: f[`${key}_en`] as string | undefined })
  }
  const dosage = f.dosage_range as { notes?: unknown } | undefined
  if (typeof dosage?.notes === 'string' && SAFETY_WORDING.test(dosage.notes)) rows.push({ label: '用量备注', text: dosage.notes })
  for (const [key, label] of GROUP_FIELDS) {
    const group = f[key] as { category?: string; note_zh?: string; note_en?: string } | undefined
    // `no_data` means the source has nothing to say, which is not the same as safe; such rows are left out.
    if (!group || !group.category || group.category === 'no_data') continue
    const status = STATUS[group.category] ?? group.category
    rows.push({ label, text: group.note_zh ? `${status}：${group.note_zh}` : status, secondary: group.note_en })
  }
  return rows
}
const herbs = computed(() => (data.value?.herbs ?? []).map(herb => ({ herb, rows: herbRows(herb) })))
const withNotes = computed(() => herbs.value.filter(h => h.rows.length))
const withoutNotes = computed(() => herbs.value.filter(h => !h.rows.length).map(h => h.herb.label))
const entityLink = (id: string) => `/entity/${encodeURIComponent(id)}`
// The 说明 row lives in EntityView's attribute list (id attr-description_zh).
function showDescription() {
  const target = document.getElementById('attr-description_zh')
  if (!target) return
  target.scrollIntoView({ behavior: 'smooth', block: 'center' })
  // Focusable only for this jump, so clicking other labels never focuses them.
  target.setAttribute('tabindex', '-1')
  target.addEventListener('blur', () => target.removeAttribute('tabindex'), { once: true })
  target.focus({ preventScroll: true })
}
</script>

<template>
  <section class="panel detail-section" aria-labelledby="symptom-heading">
    <h2 id="symptom-heading">适用证候及症状</h2>
    <p class="note-lead">本方剂条目没有结构化的主治症状字段<template v-if="data?.patterns.length">。以下为来源中与本方关联的证候条目原文</template>。</p>
    <StateView :loading="loading" :error="error" @retry="load">
      <div v-if="data?.patterns.length === 0" class="empty-guide">
        <p>来源未给本方关联证候，因此没有可列出的症状条目。</p>
        <p>本方的主治和适用证候可参阅属性中的“说明”。
          <button type="button" class="text-button" @click="showDescription">查看“说明”</button></p>
      </div>
      <article v-for="p in data?.patterns" :key="p.id" class="note-item">
        <h3><RouterLink class="text-link" :to="entityLink(p.id)">{{ p.label }}</RouterLink>
          <small class="note-evidence"><EvidenceLinks :ids="p.evidence_ids" /></small></h3>
        <dl class="attributes">
          <dt>主症</dt><dd>{{ symptoms(p.fields.cardinal_symptoms) || '来源未提供' }}</dd>
          <template v-if="symptoms(p.fields.secondary_symptoms)"><dt>次症</dt><dd>{{ symptoms(p.fields.secondary_symptoms) }}</dd></template>
          <template v-if="zh(p.fields.tongue)"><dt>舌象</dt><dd>{{ zh(p.fields.tongue) }}</dd></template>
          <template v-if="zh(p.fields.pulse)"><dt>脉象</dt><dd>{{ zh(p.fields.pulse) }}</dd></template>
        </dl>
      </article>
    </StateView>
  </section>

  <section class="panel detail-section notice" aria-labelledby="herb-safety-heading">
    <h2 id="herb-safety-heading">组成药物的注意事项</h2>
    <p class="notice-text">以下为各组成药物条目中的来源原文，不是本方的整体禁忌；仅供学习参考，不构成用药建议。</p>
    <StateView :loading="loading" :error="error" :empty="data != null && withNotes.length === 0"
      empty-text="来源中组成药物均无注意事项记载。" @retry="load">
      <article v-for="{ herb, rows } in withNotes" :key="herb.id" class="note-item">
        <h3><RouterLink class="text-link" :to="entityLink(herb.id)">{{ herb.label }}</RouterLink></h3>
        <dl class="attributes">
          <template v-for="row in rows" :key="row.label">
            <dt>{{ row.label }}</dt>
            <dd>{{ row.text }}<small v-if="row.secondary" class="secondary">{{ row.secondary }}</small></dd>
          </template>
        </dl>
      </article>
      <p v-if="withoutNotes.length" class="footnote">{{ withoutNotes.join('、') }}：来源中没有注意事项记载（不代表无禁忌）。</p>
    </StateView>
  </section>
</template>
