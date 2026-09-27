import { createRouter, createWebHistory } from 'vue-router'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'home', component: () => import('./pages/Home.vue') },
    {
      path: '/project/:pid',
      name: 'project',
      component: () => import('./pages/ProjectPage.vue')
    },
    {
      path: '/project/:pid/template/:tid',
      name: 'template',
      component: () => import('./pages/TemplateEditor.vue')
    },
    {
      path: '/project/:pid/cards/:cid?',
      name: 'card',
      component: () => import('./pages/CardEditor.vue')
    },
    { path: '/assets', name: 'assets', component: () => import('./pages/AssetsPage.vue') }
  ]
})
