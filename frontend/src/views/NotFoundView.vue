<script setup lang="ts">
import { setTitle } from '../labels'

setTitle('页面不存在')
</script>

<template>
  <header class="entity-header">
    <p class="eyebrow">404</p>
    <h1 tabindex="-1">页面不存在</h1>
  </header>
  <section class="panel detail-section">
    <p>没有这个页面，链接可能有误。</p>
    <RouterLink class="text-link" to="/">返回检索</RouterLink>
  </section>
</template>
