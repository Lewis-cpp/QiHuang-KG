<script setup lang="ts">
import { computed } from 'vue'
import { errorKind, type ApiError } from '../api/client'

const props = withDefaults(defineProps<{
  loading: boolean
  error: ApiError | null
  empty?: boolean
  emptyText?: string
  notFoundText?: string
  invalidIsNotFound?: boolean
}>(), { empty: false, emptyText: '当前条件下没有记录。', notFoundText: '未找到该记录。', invalidIsNotFound: false })
defineEmits<{ retry: [] }>()

const kind = computed(() => props.error ? errorKind(props.error, props.invalidIsNotFound) : null)
</script>

<template>
  <div class="state-view" aria-live="polite" :aria-busy="loading">
    <p v-if="loading" class="state-message">加载中…</p>
    <div v-else-if="kind === 'not_found'" class="state-message">
      <p>{{ notFoundText }}</p>
      <RouterLink to="/" class="text-link">返回检索</RouterLink>
    </div>
    <div v-else-if="kind === 'unavailable'" class="error" role="alert">
      <p>{{ error?.message }}</p>
      <button type="button" class="ghost-button" @click="$emit('retry')">重试</button>
    </div>
    <p v-else-if="kind === 'snapshot'" class="error" role="alert">数据已更新到新批次，请点击页面顶部的“刷新”。</p>
    <p v-else-if="kind === 'error'" class="error" role="alert">{{ error?.message }}</p>
    <p v-else-if="empty" class="empty">{{ emptyText }}</p>
    <slot v-else />
  </div>
</template>
