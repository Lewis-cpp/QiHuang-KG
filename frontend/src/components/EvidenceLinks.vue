<script setup lang="ts">
import { ref } from 'vue'

defineProps<{ ids: string[] }>()
const open = ref(false)
</script>

<template>
  <span v-if="!ids.length" class="muted">无</span>
  <RouterLink v-else-if="ids.length === 1" class="text-link" :to="`/evidence/${encodeURIComponent(ids[0])}`">证据</RouterLink>
  <span v-else class="evidence-links">
    <button type="button" class="text-button" :aria-expanded="open" @click="open = !open">{{ ids.length }} 条证据</button>
    <span v-if="open" class="evidence-list">
      <RouterLink v-for="(id, i) in ids" :key="id" class="text-link" :to="`/evidence/${encodeURIComponent(id)}`">证据 {{ i + 1 }}</RouterLink>
    </span>
  </span>
</template>
