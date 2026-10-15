<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { api, errorMessage } from '../api/client'
import type { Task } from '../types/api'

const route = useRoute()
const items = ref<Task[]>([])
const total = ref(0)
const page = ref(1)
const status = ref('')
const loading = ref(false)
const error = ref('')
const detail = ref<Task | null>(null)
const detailOpen = ref(false)
const actionId = ref('')
const statusNames: Record<string, string> = { pending: '等待中', running: '运行中', paused: '已暂停', completed: '已完成', failed: '失败', cancelled: '已取消' }
const typeNames: Record<string, string> = { history: '历史同步', reconcile: '历史校准', media: '媒体下载', json_export: 'JSON 导出', jsonl_export: 'JSONL 导出', zip_export: 'ZIP 打包' }

async function load(): Promise<void> {
  loading.value = true; error.value = ''
  try {
    const params: Record<string, string | number> = { page: page.value, page_size: 20 }
    if (status.value) params.status = status.value
    if (typeof route.query.channel === 'string') params.telegram_chat_id = route.query.channel
    const result = await api.tasks(params)
    items.value = result.items; total.value = result.total
    if (detail.value) detail.value = result.items.find((item) => item.id === detail.value?.id) || await api.task(detail.value.id)
  } catch (cause) { error.value = errorMessage(cause) }
  finally { loading.value = false }
}
async function action(task: Task, kind: 'pause' | 'cancel' | 'resume' | 'retry'): Promise<void> {
  actionId.value = task.id
  try { await api.taskAction(task.id, kind); ElMessage.success('任务状态已更新'); await load() }
  catch (cause) { ElMessage.error(errorMessage(cause)) }
  finally { actionId.value = '' }
}
function inspect(task: Task): void { detail.value = task; detailOpen.value = true }
const refresh = () => { void load() }
onMounted(() => { void load(); window.addEventListener('tcm:refresh', refresh); window.addEventListener('tcm:event', refresh) })
onUnmounted(() => { window.removeEventListener('tcm:refresh', refresh); window.removeEventListener('tcm:event', refresh) })
</script>
<template>
  <div class="page">
    <div class="page-heading">
<div><h1>同步任务</h1><p>任务进度和错误状态由后端持久保存</p></div><el-button @click="load">
刷新任务
</el-button>
</div>
    <div class="panel">
      <div class="toolbar">
<el-select v-model="status" placeholder="全部状态" clearable style="width: 155px" @change="page = 1; load()">
<el-option v-for="(label, key) in statusNames" :key="key" :label="label" :value="key" />
</el-select><el-tag v-if="route.query.channel" type="info">
频道 {{ route.query.channel }}
</el-tag>
</div>
      <el-alert v-if="error" :title="error" type="error" show-icon class="toolbar" />
      <el-table v-loading="loading" :data="items" empty-text="暂无任务">
        <el-table-column prop="id" label="任务 ID" min-width="240">
<template #default="{ row }">
<span class="mono">{{ row.id }}</span>
</template>
</el-table-column>
        <el-table-column label="频道" min-width="145">
<template #default="{ row }">
<span class="mono">{{ row.telegram_chat_id || '全部' }}</span>
</template>
</el-table-column>
        <el-table-column label="类型" width="110">
<template #default="{ row }">
{{ typeNames[row.task_type] || row.task_type }}
</template>
</el-table-column>
        <el-table-column label="状态" width="100">
<template #default="{ row }">
<el-tag :type="row.status === 'completed' ? 'success' : row.status === 'failed' ? 'danger' : row.status === 'running' ? 'primary' : 'info'">
{{ statusNames[row.status] || row.status }}
</el-tag>
</template>
</el-table-column>
        <el-table-column label="进度" width="120">
<template #default="{ row }">
{{ row.processed_count }}{{ row.total_count !== null ? ` / ${row.total_count}` : '' }}
</template>
</el-table-column>
        <el-table-column label="更新时间" min-width="165">
<template #default="{ row }">
{{ new Date(row.updated_at).toLocaleString() }}
</template>
</el-table-column>
        <el-table-column label="操作" min-width="180">
<template #default="{ row }">
<div class="cell-actions">
<el-button link @click="inspect(row)">
详情
</el-button><el-button v-if="['history', 'reconcile'].includes(row.task_type) && (row.status === 'running' || row.status === 'pending')" link @click="action(row, 'pause')">
暂停
</el-button><el-button v-if="row.status === 'paused'" link @click="action(row, 'resume')">
恢复
</el-button><el-button v-if="row.status === 'pending' || row.status === 'paused' || (row.status === 'running' && ['history', 'reconcile'].includes(row.task_type))" link type="danger" @click="action(row, 'cancel')">
取消
</el-button><el-button v-if="row.status === 'failed'" link type="primary" @click="action(row, 'retry')">
重试
</el-button>
</div>
</template>
</el-table-column>
      </el-table>
      <div class="pagination">
<el-pagination v-model:current-page="page" :total="total" :page-size="20" layout="total, prev, pager, next" @current-change="load" />
</div>
    </div>
    <el-drawer v-model="detailOpen" title="任务详情" size="min(560px, 90vw)">
<el-descriptions v-if="detail" :column="1" border>
      <el-descriptions-item label="任务 ID">
{{ detail.id }}
</el-descriptions-item><el-descriptions-item label="类型">
{{ typeNames[detail.task_type] || detail.task_type }}
</el-descriptions-item>
      <el-descriptions-item label="频道">
{{ detail.telegram_chat_id || '全部频道' }}
</el-descriptions-item><el-descriptions-item label="状态">
{{ statusNames[detail.status] || detail.status }}
</el-descriptions-item>
      <el-descriptions-item label="已处理">
{{ detail.processed_count }}
</el-descriptions-item><el-descriptions-item label="总量">
{{ detail.total_count ?? '未知' }}
</el-descriptions-item>
      <el-descriptions-item label="游标">
{{ detail.cursor_message_id ?? '无' }}
</el-descriptions-item><el-descriptions-item label="重试次数">
{{ detail.retry_count }}
</el-descriptions-item>
      <el-descriptions-item label="开始时间">
{{ detail.started_at ? new Date(detail.started_at).toLocaleString() : '未开始' }}
</el-descriptions-item><el-descriptions-item label="结束时间">
{{ detail.finished_at ? new Date(detail.finished_at).toLocaleString() : '未结束' }}
</el-descriptions-item>
      <el-descriptions-item label="错误">
{{ detail.error_message || '无' }}
</el-descriptions-item>
    </el-descriptions>
</el-drawer>
  </div>
</template>
