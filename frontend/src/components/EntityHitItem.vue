<script setup lang="ts">
import type { EntityHit } from '../api/types'
import { datasetNames, label, reviewNames, typeNames } from '../labels'

defineProps<{ item: EntityHit }>()
</script>

<template>
  <li>
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
</template>
