<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import { ElMessage } from 'element-plus'
import { DataAnalysis, Collection, ChatLineSquare, List, Download, Setting, Moon, Sunny } from '@element-plus/icons-vue'
import { api, errorMessage } from '../api/client'
import { useAuthStore } from '../stores/auth'
import { useLiveStore } from '../stores/live'
import type { TelegramStatus } from '../types/api'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const live = useLiveStore()
const { connected } = storeToRefs(live)
const telegram = ref<TelegramStatus | null>(null)
const isDark = ref(false)
const THEME_KEY = 'tcm-theme'

const menu = [
  { path: '/dashboard', title: '仪表盘', icon: DataAnalysis },
  { path: '/channels', title: '频道管理', icon: Collection },
  { path: '/messages', title: '消息内容', icon: ChatLineSquare },
  { path: '/tasks', title: '同步任务', icon: List },
  { path: '/exports', title: '导出与下载', icon: Download },
  { path: '/settings', title: '系统设置', icon: Setting },
]
const activeMenu = () => route.path.includes('/messages') ? '/messages' : `/${route.path.split('/')[1]}`

function syncThemeState(): void {
  isDark.value = document.documentElement.classList.contains('dark')
}
function toggleTheme(): void {
  isDark.value = !isDark.value
  document.documentElement.classList.toggle('dark', isDark.value)
  try { localStorage.setItem(THEME_KEY, isDark.value ? 'dark' : 'light') } catch { /* 忽略 */ }
}

async function refreshStatus(): Promise<void> {
  try { telegram.value = await api.telegramStatus() } catch { telegram.value = null }
}
async function logout(): Promise<void> {
  try { await auth.logout(); live.disconnect(); await router.push('/login') }
  catch (error) { ElMessage.error(errorMessage(error)) }
}
const onRefresh = () => { void refreshStatus() }
const onEvent = (event: Event) => { if ((event as CustomEvent).detail?.type === 'telegram.connection') void refreshStatus() }
onMounted(() => {
  syncThemeState()
  void refreshStatus()
  live.connect()
  window.addEventListener('tcm:refresh', onRefresh)
  window.addEventListener('tcm:event', onEvent)
})
onUnmounted(() => {
  live.disconnect()
  window.removeEventListener('tcm:refresh', onRefresh)
  window.removeEventListener('tcm:event', onEvent)
})
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar" aria-label="主导航">
      <div class="brand">
<span class="brand-mark">T</span><span class="brand-title">Channel Manager</span>
</div>
      <el-menu :default-active="activeMenu()" router>
        <el-menu-item v-for="item in menu" :key="item.path" :index="item.path" :aria-label="item.title" :title="item.title">
          <el-icon><component :is="item.icon" /></el-icon><span class="nav-text">{{ item.title }}</span>
        </el-menu-item>
      </el-menu>
      <div class="sidebar-foot">
本地频道管理平台
</div>
    </aside>
    <div class="main-column">
      <header class="topbar">
        <div class="topbar-title">
安全管理已授权账号的频道内容
</div>
        <div class="topbar-status">
          <el-tag :type="telegram?.authorized ? 'success' : 'warning'" size="small">
Telegram {{ telegram?.authorized ? '已授权' : '未连接' }}
</el-tag>
          <el-tag :type="connected ? 'success' : 'info'" size="small">
实时 {{ connected ? '在线' : '离线' }}
</el-tag>
          <el-tooltip :content="isDark ? '切换到浅色' : '切换到深色'" placement="bottom">
            <el-button circle :icon="isDark ? Sunny : Moon" @click="toggleTheme" aria-label="切换主题" />
          </el-tooltip>
          <el-button link @click="logout">
退出管理
</el-button>
        </div>
      </header>
      <main><RouterView /></main>
    </div>
  </div>
</template>
