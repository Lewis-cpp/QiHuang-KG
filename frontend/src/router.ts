import { nextTick } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import SearchView from './views/SearchView.vue'
import EntityView from './views/EntityView.vue'
import EvidenceView from './views/EvidenceView.vue'
import DatasetsView from './views/DatasetsView.vue'
import StatsView from './views/StatsView.vue'
import AIQueryView from './views/AIQueryView.vue'
import NotFoundView from './views/NotFoundView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: SearchView },
    { path: '/entity/:id', component: EntityView, props: true },
    { path: '/evidence/:id', component: EvidenceView, props: true },
    // Cytoscape is only loaded with the graph page.
    { path: '/graph/:id', component: () => import('./views/GraphView.vue'), props: true },
    { path: '/datasets', component: DatasetsView },
    { path: '/stats', component: StatsView },
    { path: '/ai', component: AIQueryView },
    { path: '/:pathMatch(.*)*', component: NotFoundView },
  ],
  scrollBehavior: (to, from, saved) => saved ?? (to.path === from.path ? undefined : { top: 0 }),
})

// Move focus to the new page's heading so screen readers announce it; query-only changes keep focus.
router.afterEach((to, from) => {
  if (to.path === from.path) return
  void nextTick(() => document.querySelector<HTMLElement>('main h1')?.focus({ preventScroll: true }))
})

export default router
