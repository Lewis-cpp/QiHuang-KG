<script setup lang="ts">
import { computed } from 'vue'
import { number } from '../labels'

// The API caps offset at 10000 (spec §2.2), so pages past that are unreachable.
const MAX_OFFSET = 10000
const props = defineProps<{ total: number; limit: number; offset: number; disabled?: boolean }>()
const emit = defineEmits<{ change: [offset: number] }>()

const page = computed(() => Math.floor(props.offset / props.limit) + 1)
const pages = computed(() => Math.max(1, Math.ceil(props.total / props.limit)))
const reachable = computed(() => Math.min(pages.value, Math.floor(MAX_OFFSET / props.limit) + 1))
const capped = computed(() => pages.value > reachable.value && page.value >= reachable.value)
const go = (target: number) => emit('change', (target - 1) * props.limit)
</script>

<template>
  <nav v-if="total > limit" class="pager" aria-label="分页">
    <button type="button" class="ghost-button" :disabled="disabled || page <= 1" @click="go(page - 1)">上一页</button>
    <span>第 {{ number(page) }} / {{ number(pages) }} 页，共 {{ number(total) }} 条</span>
    <button type="button" class="ghost-button" :disabled="disabled || page >= reachable" @click="go(page + 1)">下一页</button>
    <span v-if="capped" class="pager-note">结果过多，请细化条件</span>
  </nav>
</template>
