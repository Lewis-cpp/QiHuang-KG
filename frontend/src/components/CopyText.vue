<script setup lang="ts">
import { ref } from 'vue'

const props = defineProps<{ text: string; label?: string }>()
const copied = ref(false)
async function copy() {
  try {
    await navigator.clipboard.writeText(props.text)
    copied.value = true
    setTimeout(() => { copied.value = false }, 1500)
  } catch { /* clipboard unavailable; the text stays selectable */ }
}
</script>

<template>
  <span class="copy-text">
    <code>{{ text }}</code>
    <button type="button" class="text-button" :aria-label="`复制${label ?? ''}`" @click="copy">{{ copied ? '已复制' : '复制' }}</button>
  </span>
</template>
