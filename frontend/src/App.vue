<script setup lang="ts">
import { useRoute } from 'vue-router'
import { forgetBuild, snapshotChanged } from './api/client'

const route = useRoute()
// spec §2.3: never refresh on our own; the reader decides when to leave the old batch.
function reloadBatch() {
  forgetBuild()
  snapshotChanged.value = false
  location.reload()
}
</script>

<template>
  <div class="shell">
    <header class="site-header">
      <RouterLink class="brand" to="/"><span class="seal" aria-hidden="true">岐</span><span>岐黄知图<small>QIHUANG KNOWLEDGE GRAPH</small></span></RouterLink>
      <nav aria-label="页面导航">
        <RouterLink to="/" :class="{ active: route.path === '/' }">检索</RouterLink>
        <RouterLink to="/ai" active-class="active">AI 查询</RouterLink>
        <RouterLink to="/datasets" active-class="active">来源</RouterLink>
        <RouterLink to="/stats" active-class="active">统计</RouterLink>
      </nav>
      <span class="preview">开发预览 · 0.2</span>
    </header>
    <div v-if="snapshotChanged" class="banner" role="alert">
      <span>数据已更新到新批次，请刷新。</span>
      <button type="button" class="ghost-button" @click="reloadBatch">刷新</button>
    </div>
    <main>
      <RouterView :key="route.path" />
    </main>
    <footer><span>岐黄知图 · 资料检索与学习</span><span>保留来源差异，支持回查证据。</span></footer>
  </div>
</template>
