import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', name: 'login', component: () => import('../views/LoginView.vue') },
    {
      path: '/', component: () => import('../layouts/MainLayout.vue'), children: [
        { path: '', redirect: '/dashboard' },
        { path: 'dashboard', component: () => import('../views/DashboardView.vue') },
        { path: 'channels', component: () => import('../views/ChannelsView.vue') },
        { path: 'messages', component: () => import('../views/MessagesView.vue') },
        { path: 'channels/:id/messages', component: () => import('../views/MessagesView.vue') },
        { path: 'tasks', component: () => import('../views/TasksView.vue') },
        { path: 'exports', component: () => import('../views/ExportsView.vue') },
        { path: 'settings', component: () => import('../views/SettingsView.vue') },
        { path: 'design-system', component: () => import('../views/DesignSystemView.vue') },
      ],
    },
  ],
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  if (!auth.ready) await auth.load()
  if (to.name === 'login') return auth.authenticated ? '/dashboard' : true
  if (!auth.authenticated) return '/login'
  return true
})

export default router
