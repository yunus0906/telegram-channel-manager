<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api, errorMessage } from '../api/client'
import type { AvailableChannel, Channel } from '../types/api'

const router = useRouter()
const items = ref<Channel[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const query = ref('')
const accessType = ref('')
const loading = ref(false)
const error = ref('')
const available = ref<AvailableChannel[]>([])
const selected = ref<AvailableChannel[]>([])
const discoveryOpen = ref(false)
const discoveryLoading = ref(false)
const actionId = ref('')

async function load(): Promise<void> {
  loading.value = true; error.value = ''
  try {
    const result = await api.channels({ page: page.value, page_size: pageSize, q: query.value, access_type: accessType.value })
    items.value = result.items; total.value = result.total
  } catch (cause) { error.value = errorMessage(cause) }
  finally { loading.value = false }
}
async function discover(): Promise<void> {
  discoveryOpen.value = true; discoveryLoading.value = true
  try { available.value = await api.availableChannels() }
  catch (cause) { ElMessage.error(errorMessage(cause)) }
  finally { discoveryLoading.value = false }
}
async function addSelected(): Promise<void> {
  if (!selected.value.length) return
  try {
    await api.addChannels(selected.value.map((item) => item.telegram_chat_id))
    ElMessage.success('频道已添加'); discoveryOpen.value = false; selected.value = []; await load()
  } catch (cause) { ElMessage.error(errorMessage(cause)) }
}
async function action(channel: Channel, kind: 'sync' | 'reconcile' | 'listen' | 'stop' | 'remove' | 'purge'): Promise<void> {
  actionId.value = channel.telegram_chat_id
  try {
    if (kind === 'remove') {
      await ElMessageBox.confirm(`从管理列表移出“${channel.title}”？本地消息会保留。`, '移出频道', { type: 'warning' })
      await api.removeChannel(channel.telegram_chat_id)
    } else if (kind === 'purge') {
      await ElMessageBox.prompt(`这会删除“${channel.title}”的本地消息、媒体与导出文件。请输入完整 Chat ID：${channel.telegram_chat_id}`, '删除本地数据', {
        confirmButtonText: '确认删除', cancelButtonText: '取消', inputValidator: (value) => value === channel.telegram_chat_id || 'Chat ID 不匹配',
      })
      await api.purgeChannel(channel.telegram_chat_id)
    } else if (kind === 'sync') await api.syncChannel(channel.telegram_chat_id)
    else if (kind === 'reconcile') await api.reconcileChannel(channel.telegram_chat_id)
    else if (kind === 'listen') await api.listenChannel(channel.telegram_chat_id)
    else await api.stopListenChannel(channel.telegram_chat_id)
    ElMessage.success(kind === 'sync' || kind === 'reconcile' ? '任务已创建' : '操作成功')
    await load()
  } catch (cause) {
    if (cause !== 'cancel' && cause !== 'close') ElMessage.error(errorMessage(cause))
  } finally { actionId.value = '' }
}
function search(): void { page.value = 1; void load() }
onMounted(() => { void load() })
</script>

<template>
  <div class="page">
    <div class="page-heading">
<div><h1>频道管理</h1><p>仅显示当前账号可访问并已添加的频道</p></div><el-button type="primary" @click="discover">
发现频道
</el-button>
</div>
    <div class="panel">
      <div class="toolbar">
        <el-input v-model="query" placeholder="搜索频道名称" clearable @keyup.enter="search" @clear="search" />
        <el-select v-model="accessType" placeholder="访问类型" clearable style="width: 140px" @change="search">
<el-option label="公开" value="public" /><el-option label="私有" value="private" />
</el-select>
        <el-button @click="search">
搜索
</el-button>
      </div>
      <el-alert v-if="error" :title="error" type="error" show-icon class="toolbar" />
      <el-table v-loading="loading" :data="items" style="width: 100%" empty-text="暂无已管理频道">
        <el-table-column label="频道" min-width="180">
<template #default="{ row }">
<strong>{{ row.title }}</strong><div class="mono muted">
{{ row.telegram_chat_id }}
</div>
</template>
</el-table-column>
        <el-table-column label="类型 / 地址" min-width="160">
<template #default="{ row }">
<el-tag size="small" :type="row.access_type === 'private' ? 'info' : 'success'">
{{ row.access_type === 'private' ? '私有' : '公开' }}
</el-tag><div v-if="row.permalink">
<a :href="row.permalink" target="_blank" rel="noopener noreferrer">{{ row.username }}</a>
</div><div v-else class="muted">
授权访问
</div>
</template>
</el-table-column>
        <el-table-column prop="message_count" label="本地消息" width="100" />
        <el-table-column label="同步 / 监听" width="130">
<template #default="{ row }">
<div>{{ row.history_sync_enabled ? '已启动同步' : '未同步' }}</div><div :class="row.live_listener_enabled ? '' : 'muted'">
{{ row.live_listener_enabled ? '监听中' : '未监听' }}
</div>
</template>
</el-table-column>
        <el-table-column label="最近同步" min-width="155">
<template #default="{ row }">
{{ row.last_history_sync_at ? new Date(row.last_history_sync_at).toLocaleString() : '暂无' }}
</template>
</el-table-column>
        <el-table-column label="操作" min-width="270">
<template #default="{ row }">
<div class="cell-actions">
          <el-button link type="primary" @click="router.push(`/channels/${row.telegram_chat_id}/messages`)">
消息
</el-button>
          <el-button link type="primary" :loading="actionId === row.telegram_chat_id" @click="action(row, 'sync')">
同步
</el-button>
          <el-button link @click="action(row, 'reconcile')">
校准
</el-button>
          <el-button link @click="action(row, row.live_listener_enabled ? 'stop' : 'listen')">
{{ row.live_listener_enabled ? '停止监听' : '监听' }}
</el-button>
          <el-button link @click="router.push({ path: '/tasks', query: { channel: row.telegram_chat_id } })">
任务
</el-button>
          <el-button link type="warning" @click="action(row, 'remove')">
移出
</el-button>
          <el-button link type="danger" @click="action(row, 'purge')">
删数据
</el-button>
        </div>
</template>
</el-table-column>
      </el-table>
      <div class="pagination">
<el-pagination v-model:current-page="page" :page-size="pageSize" :total="total" layout="total, prev, pager, next" @current-change="load" />
</div>
    </div>
    <el-dialog v-model="discoveryOpen" title="发现可访问频道" width="min(760px, 94vw)">
      <el-alert title="添加频道与启动同步是两个独立操作" type="info" :closable="false" class="toolbar" />
      <el-table v-loading="discoveryLoading" :data="available" max-height="420" empty-text="未发现可访问频道" @selection-change="(rows: AvailableChannel[]) => selected = rows">
        <el-table-column type="selection" width="48" /><el-table-column prop="title" label="频道名称" min-width="190" /><el-table-column prop="telegram_chat_id" label="Chat ID" min-width="175" /><el-table-column label="访问类型" width="100">
<template #default="{ row }">
{{ row.access_type === 'private' ? '私有' : '公开' }}
</template>
</el-table-column>
      </el-table>
      <template #footer>
<el-button @click="discoveryOpen = false">
取消
</el-button><el-button type="primary" :disabled="!selected.length" @click="addSelected">
添加所选频道
</el-button>
</template>
    </el-dialog>
  </div>
</template>
