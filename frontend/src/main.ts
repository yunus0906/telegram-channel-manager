import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import 'element-plus/theme-chalk/dark/css-vars.css'
import './styles/tokens.css'
import './styles/element-theme.css'
import './styles/base.css'
import './styles/components.css'
import App from './App.vue'
import router from './router'

// 在首屏绘制前应用主题，避免闪烁
const THEME_KEY = 'tcm-theme'
try {
  const saved = localStorage.getItem(THEME_KEY)
  const prefersDark = window.matchMedia?.('(prefers-color-scheme: dark)').matches
  if (saved === 'dark' || (saved === null && prefersDark)) document.documentElement.classList.add('dark')
} catch { /* localStorage 不可用时忽略 */ }

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.use(ElementPlus)
app.mount('#app')
