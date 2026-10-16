<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { api, errorMessage } from '../api/client'
import type { Dashboard } from '../types/api'

const data = ref<Dashboard | null>(null)
const loading = ref(false)
const error = ref('')
async function load(): Promise<void> {
  loading.value = true; error.value = ''
  try { data.value = await api.dashboard() }
  catch (cause) { error.value = errorMessage(cause) }
  finally { loading.value = false }
}
const refresh = () => { void load() }
onMounted(() => { void load(); window.addEventListener('tcm:refresh', refresh); window.addEventListener('tcm:event', refresh) })
onUnmounted(() => { window.removeEventListener('tcm:refresh', refresh); window.removeEventListener('tcm:event', refresh) })
</script>
<template>
  <div class="page">
    <div class="page-heading">
<div><h1>仪表盘</h1><p>频道同步和连接状态总览</p></div><el-button @click="load">
刷新数据
</el-button>
</div>
    <el-alert v-if="error" :title="error" type="error" show-icon class="panel" />
    <div v-loading="loading" class="metric-grid">
      <div class="metric">
<div class="metric-label">
已管理频道
</div><div class="metric-value">
{{ data?.channel_count ?? '—' }}
</div>
</div>
      <div class="metric">
<div class="metric-label">
正在监听
</div><div class="metric-value">
{{ data?.listening_count ?? '—' }}
</div>
</div>
      <div class="metric">
<div class="metric-label">
已同步消息
</div><div class="metric-value">
{{ data?.message_count ?? '—' }}
</div>
</div>
      <div class="metric">
<div class="metric-label">
运行中任务
</div><div class="metric-value">
{{ data?.running_task_count ?? '—' }}
</div>
</div>
    </div>
    <div class="panel" style="margin-top: 18px">
<h2 class="section-title">
连接与同步
</h2>
      <el-descriptions :column="2" border>
        <el-descriptions-item label="Telegram">
{{ data?.telegram.authorized ? '已授权' : data?.telegram.configured ? '未授权' : '未配置' }}
</el-descriptions-item>
        <el-descriptions-item label="最近成功同步">
{{ data?.last_successful_sync_at ? new Date(data.last_successful_sync_at).toLocaleString() : '暂无' }}
</el-descriptions-item>
        <el-descriptions-item label="当前账号">
{{ data?.telegram.account_name || data?.telegram.account || '未登录' }}
</el-descriptions-item>
        <el-descriptions-item label="最近连接错误">
{{ data?.telegram.last_error || '无' }}
</el-descriptions-item>
      </el-descriptions>
    </div>
    <div class="panel">
<h2 class="section-title">
最近错误
</h2><el-empty v-if="!data?.recent_errors.length" description="暂无任务错误" :image-size="70" />
      <el-table v-else :data="data.recent_errors">
<el-table-column prop="id" label="任务 ID" min-width="220" /><el-table-column prop="task_type" label="类型" width="130" /><el-table-column prop="error_message" label="错误" min-width="170" />
</el-table>
    </div>
    <div class="panel">
<h2 class="section-title">
最近同步活动
</h2><el-empty v-if="!data?.recent_activity.length" description="暂无消息活动" :image-size="70" />
      <el-table v-else :data="data.recent_activity">
<el-table-column prop="type" label="事件" width="140" /><el-table-column prop="channel_id" label="频道 ID" min-width="170" /><el-table-column prop="message_id" label="消息 ID" width="140" /><el-table-column prop="timestamp" label="时间" min-width="180" />
</el-table>
    </div>
  </div>
</template>
