import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'dashboard',
      component: () => import('../views/DashboardView.vue'),
    },
    {
      path: '/knowledge-bases/:id',
      name: 'knowledge-base',
      component: () => import('../views/KnowledgeBaseView.vue'),
      props: true,
    },
  ],
})

export default router
