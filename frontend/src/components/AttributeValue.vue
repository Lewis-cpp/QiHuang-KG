<script setup lang="ts">
import { computed } from 'vue'
import { isEmpty, objectRows } from '../attributes'
import { routeNames, subKeyLabels, valueLabels } from '../fieldLabels'

// Renders source values as plain text only (never v-html); deep nesting falls back to JSON.
const props = withDefaults(defineProps<{ value: unknown; field?: string; depth?: number }>(), { depth: 0 })

const isScalar = (v: unknown): v is string | number | boolean => ['string', 'number', 'boolean'].includes(typeof v)

function text(v: string | number | boolean): string {
  if (typeof v === 'boolean') return v ? '是' : '否'
  if (v === 'no_data') return '来源无数据'
  if (typeof v === 'string' && props.field) {
    if (props.field === 'Routes_of_administration' && routeNames[v]) return `${routeNames[v]}（${v}）`
    const mapped = valueLabels[props.field]?.[v]
    if (mapped) return mapped
  }
  return String(v)
}

const view = computed(() => {
  const v = props.value
  if (isScalar(v)) return { kind: 'scalar' as const, text: text(v) }
  if (props.depth > 4 || v == null) return { kind: 'json' as const }
  if (Array.isArray(v)) {
    const items = v.filter(item => !isEmpty(item))
    if (items.every(isScalar)) return { kind: 'scalar' as const, text: items.map(text).join('、') }
    return { kind: 'list' as const, items }
  }
  if (typeof v === 'object') {
    const object = v as Record<string, unknown>
    if (typeof object.zh === 'string') {
      const rest = Object.fromEntries(Object.entries(object).filter(([k]) => k !== 'zh' && k !== 'en'))
      return { kind: 'bilingual' as const, zh: object.zh, en: typeof object.en === 'string' ? object.en : '', rows: objectRows(rest) }
    }
    return { kind: 'object' as const, rows: objectRows(object) }
  }
  return { kind: 'json' as const }
})
</script>

<template>
  <span v-if="view.kind === 'scalar'" class="attr-text">{{ view.text }}</span>
  <ul v-else-if="view.kind === 'list'" class="attr-list">
    <li v-for="(item, i) in view.items" :key="i"><AttributeValue :value="item" :field="field" :depth="depth + 1" /></li>
  </ul>
  <span v-else-if="view.kind === 'bilingual'" class="attr-bilingual">
    <span class="attr-text">{{ view.zh }}</span>
    <small v-if="view.en" class="secondary">{{ view.en }}</small>
    <small v-for="row in view.rows" :key="row.key" class="attr-extra">{{ subKeyLabels[row.key] ?? row.label }}：<AttributeValue :value="row.value" :depth="depth + 1" /></small>
  </span>
  <dl v-else-if="view.kind === 'object'" class="attr-dl">
    <template v-for="row in view.rows" :key="row.key">
      <dt>{{ row.label }}</dt>
      <dd>
        <AttributeValue :value="row.value" :depth="depth + 1" />
        <small v-if="typeof row.secondary === 'string'" class="secondary">{{ row.secondary }}</small>
      </dd>
    </template>
  </dl>
  <pre v-else class="attr-json">{{ JSON.stringify(value, null, 2) }}</pre>
</template>
