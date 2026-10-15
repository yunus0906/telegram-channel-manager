<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api, errorMessage } from '../api/client'
import type { Channel, Task } from '../types/api'

const channels = ref<Channel[]>([])
const items = ref<Task[]>([])
const total = ref(0)
const page = ref(1)
const loading = ref(false)
const submitting = ref(false)
const error = ref('')
const form = ref<{ telegram_chat_id: string; format: 'json' | 'jsonl' | 'zip'; include_media: boolean; media_only: boolean }>({ telegram_chat_id: '', format: 'json', include_media: false, media_only: false })
const dateRange = ref<[string, string] | null>(null)

async function load(): Promise<void> {
  loading.value = true; error.value = ''
  try { const result = await api.exports({ page: page.value, page_size: 20 }); items.value = result.items; total.value = result.total }
  catch (cause) { error.value = errorMessage(cause) }
  finally { loading.value = false }
}
async function loadChannels(): Promise<void> {
  try {
    const [found, settings] = await Promise.all([api.channels({ page: 1, page_size: 100 }), api.settings()])
    channels.value = found.items
    form.value.format = settings.values.default_export_format
  }
  catch (cause) { ElMessage.error(errorMessage(cause)) }
}
async function submit(): Promise<void> {
  submitting.value = true
  try {
    await api.createExport({
      telegram_chat_id: form.value.telegram_chat_id || null, format: form.value.format,
      include_media: form.value.format === 'zip' && form.value.include_media,
      media_only: form.value.format === 'zip' && form.value.include_media && Boolean(form.value.telegram_chat_id) && form.value.media_only,
      date_from: dateRange.value?.[0] ? `${dateRange.value[0]}T00:00:00Z` : null,
      date_to: dateRange.value?.[1] ? `${dateRange.value[1]}T23:59:59Z` : null,
    })
    ElMessage.success('导出任务已创建'); await load()
  } catch (cause) { ElMessage.error(errorMessage(cause)) }
  finally { submitting.value = false }
}
const refresh = () => { void load() }
onMounted(() => { void load(); void loadChannels(); window.addEventListener('tcm:refresh', refresh); window.addEventListener('tcm:event', refresh) })
onUnmounted(() => { window.removeEventListener('tcm:refresh', refresh); window.removeEventListener('tcm:event', refresh) })
</script>
<template>
  <div class="page">
    <div class="page-heading">
<div><h1>导出与下载</h1><p>后台生成 JSON、JSONL 和安全 ZIP 文件</p></div>
</div>
    <div class="panel">
<h2 class="section-title">
创建导出任务
</h2><el-form label-position="top" @submit.prevent="submit">
      <div class="toolbar">
<el-form-item label="导出范围">
<el-select v-model="form.telegram_chat_id" style="width: 240px">
<el-option label="所有已管理频道" value="" /><el-option v-for="channel in channels" :key="channel.telegram_chat_id" :label="channel.title" :value="channel.telegram_chat_id" />
</el-select>
</el-form-item>
        <el-form-item label="格式">
<el-select v-model="form.format" style="width: 150px">
<el-option label="JSON 快照" value="json" /><el-option label="JSONL 事件" value="jsonl" /><el-option label="ZIP 打包" value="zip" />
</el-select>
</el-form-item>
        <el-form-item label="日期范围">
<el-date-picker v-model="dateRange" type="daterange" value-format="YYYY-MM-DD" range-separator="至" start-placeholder="开始日期" end-placeholder="结束日期" />
</el-form-item>
      </div>
      <el-form-item v-if="form.format === 'zip'">
<el-checkbox v-model="form.include_media">
包含已下载的媒体文件
</el-checkbox>
</el-form-item>
      <el-form-item v-if="form.format === 'zip' && form.include_media && form.telegram_chat_id">
<el-checkbox v-model="form.media_only">
仅打包媒体，不包含 JSON 快照
</el-checkbox>
</el-form-item>
      <el-button type="primary" native-type="submit" :loading="submitting">
创建导出
</el-button>
    </el-form>
</div>
    <div class="panel">
<div class="page-heading">
<h2 class="section-title">
导出历史
</h2><el-button @click="load">
刷新
</el-button>
</div>
      <el-alert v-if="error" :title="error" type="error" show-icon class="toolbar" />
      <el-table v-loading="loading" :data="items" empty-text="暂无导出任务">
        <el-table-column prop="id" label="任务 ID" min-width="235">
<template #default="{ row }">
<span class="mono">{{ row.id }}</span>
</template>
</el-table-column>
        <el-table-column label="频道" min-width="140">
<template #default="{ row }">
{{ row.telegram_chat_id || '全部频道' }}
</template>
</el-table-column>
        <el-table-column prop="task_type" label="格式" width="125" /><el-table-column prop="status" label="状态" width="100" />
        <el-table-column label="创建时间" min-width="165">
<template #default="{ row }">
{{ new Date(row.created_at).toLocaleString() }}
</template>
</el-table-column>
        <el-table-column label="操作" width="100">
<template #default="{ row }">
<a v-if="row.result_available" :href="api.exportUrl(row.id)">下载</a><el-tooltip v-else-if="row.error_message" :content="row.error_message">
<span class="muted">失败原因</span>
</el-tooltip><span v-else class="muted">等待生成</span>
</template>
</el-table-column>
      </el-table>
      <div class="pagination">
<el-pagination v-model:current-page="page" :total="total" :page-size="20" layout="total, prev, pager, next" @current-change="load" />
</div>
    </div>
  </div>
</template>
