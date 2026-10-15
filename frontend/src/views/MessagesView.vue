<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { api, errorMessage } from '../api/client'
import { useLiveStore } from '../stores/live'
import { useMessagesStore } from '../stores/messages'
import type { Channel, LiveEvent, Message } from '../types/api'

const route = useRoute()
const router = useRouter()
const store = useMessagesStore()
const live = useLiveStore()
const { channelId, items, total, page, pageSize, loading, error, filters } = storeToRefs(store)
const channels = ref<Channel[]>([])
const channelLoading = ref(false)
const dateRange = ref<[string, string] | null>(null)
const detail = ref<Message | null>(null)
const detailOpen = ref(false)
const downloading = ref('')
const mediaStatusNames: Record<string, string> = { downloaded: '已下载', not_downloaded: '未下载', pending: '等待下载', running: '下载中', failed: '下载失败' }

async function loadChannels(): Promise<void> {
  channelLoading.value = true
  try {
    const result = await api.channels({ page: 1, page_size: 100 })
    channels.value = result.items
    if (!route.params.id && result.items.length) await router.replace(`/channels/${result.items[0]!.telegram_chat_id}/messages`)
  } catch (cause) { ElMessage.error(errorMessage(cause)) }
  finally { channelLoading.value = false }
}
async function applyFilters(): Promise<void> {
  filters.value.date_from = dateRange.value?.[0] ? `${dateRange.value[0]}T00:00:00Z` : ''
  filters.value.date_to = dateRange.value?.[1] ? `${dateRange.value[1]}T23:59:59Z` : ''
  await store.search()
}
async function copy(value: string): Promise<void> {
  try { await navigator.clipboard.writeText(value); ElMessage.success('已复制') }
  catch { ElMessage.error('复制失败，请检查浏览器权限') }
}
async function download(message: Message): Promise<void> {
  if (!channelId.value) return
  downloading.value = message.telegram_message_id
  try { await api.downloadMedia(channelId.value, message.telegram_message_id); ElMessage.success('附件下载任务已创建') }
  catch (cause) { ElMessage.error(errorMessage(cause)) }
  finally { downloading.value = '' }
}
function openDetail(message: Message): void { detail.value = message; detailOpen.value = true }
const onEvent = (event: Event) => {
  const data = (event as CustomEvent<LiveEvent>).detail
  if (data.channel_id === channelId.value && (data.type === 'sync.completed' || data.type === 'media.progress')) void store.load()
}
watch(() => route.params.id, async (id) => {
  const next = typeof id === 'string' ? id : null
  await store.selectChannel(next)
  live.subscribe(next ? [next] : [])
}, { immediate: true })
onMounted(() => { void loadChannels(); window.addEventListener('tcm:event', onEvent) })
onUnmounted(() => { live.subscribe([]); window.removeEventListener('tcm:event', onEvent) })
</script>

<template>
  <div class="page">
    <div class="page-heading">
<div><h1>消息内容</h1><p>本地消息按发布时间倒序展示；未下载的附件可按需获取</p></div><el-button :disabled="!channelId" @click="store.load">
刷新
</el-button>
</div>
    <div class="messages-layout">
      <aside v-loading="channelLoading" class="panel channel-list" aria-label="频道选择器">
        <h2 class="section-title">
频道
</h2>
        <el-empty v-if="!channels.length" description="请先添加频道" :image-size="64" />
        <button v-for="channel in channels" :key="channel.telegram_chat_id" type="button" class="channel-choice" :class="{ active: channelId === channel.telegram_chat_id }" @click="router.push(`/channels/${channel.telegram_chat_id}/messages`)">
          <span>{{ channel.title }}</span><br /><span class="mono muted">{{ channel.telegram_chat_id }}</span>
        </button>
      </aside>
      <section class="panel">
        <div class="toolbar">
          <el-input v-model="filters.q" placeholder="搜索消息正文" clearable @keyup.enter="applyFilters" @clear="applyFilters" />
          <el-select v-model="filters.media_type" placeholder="消息类型" clearable style="width: 140px" @change="applyFilters">
            <el-option label="文本" value="text" /><el-option label="图片" value="photo" /><el-option label="视频" value="video" /><el-option label="文档" value="document" />
          </el-select>
          <el-date-picker v-model="dateRange" type="daterange" value-format="YYYY-MM-DD" range-separator="至" start-placeholder="开始日期" end-placeholder="结束日期" @change="applyFilters" />
          <el-button @click="applyFilters">
筛选
</el-button>
        </div>
        <el-alert v-if="error" :title="error" type="error" show-icon class="toolbar" />
        <div v-loading="loading">
          <el-empty v-if="!items.length && !loading" :description="channelId ? '该频道暂无符合条件的本地消息' : '请选择频道'" />
          <article v-for="message in items" :key="message.telegram_message_id" class="message-card">
            <div class="message-meta">
<span class="mono">#{{ message.telegram_message_id }} · {{ new Date(message.message_date).toLocaleString() }}</span><el-tag v-if="message.edit_date" size="small" type="warning">
已编辑
</el-tag>
</div>
            <div class="message-text">
{{ message.text || '（无文字内容）' }}
</div>
            <div v-if="message.media_type" class="toolbar">
<el-tag size="small">
{{ message.media_type }}
</el-tag><span class="muted">{{ mediaStatusNames[message.media_status] || message.media_status }}</span>
              <template v-if="message.media_status === 'downloaded' && channelId">
                <el-image v-if="message.media_type === 'photo'" :src="api.mediaUrl(channelId, message.telegram_message_id)" fit="contain" style="max-width: 180px; max-height: 110px" :preview-src-list="[api.mediaUrl(channelId, message.telegram_message_id)]" />
                <video v-else-if="message.media_type === 'video'" controls preload="none" style="max-width: 220px; max-height: 125px" :src="api.mediaUrl(channelId, message.telegram_message_id)"></video>
                <a v-else :href="api.mediaUrl(channelId, message.telegram_message_id)">下载文档</a>
              </template>
              <el-button v-else link type="primary" :disabled="['pending', 'running'].includes(message.media_status)" :loading="downloading === message.telegram_message_id" @click="download(message)">
{{ message.media_status === 'failed' ? '重新下载' : '下载附件' }}
</el-button>
            </div>
            <div class="cell-actions">
<el-button link @click="openDetail(message)">
详情
</el-button><el-button link @click="copy(message.text)">
复制正文
</el-button><el-button v-if="message.permalink" link @click="copy(message.permalink)">
复制链接
</el-button><a v-if="message.permalink" :href="message.permalink" target="_blank" rel="noopener noreferrer">打开原始消息</a>
</div>
          </article>
        </div>
        <div class="pagination">
<el-pagination :current-page="page" :page-size="pageSize" :total="total" layout="total, prev, pager, next" @current-change="store.changePage" />
</div>
      </section>
    </div>
    <el-drawer v-model="detailOpen" title="消息详情" size="min(520px, 90vw)">
      <el-descriptions v-if="detail" :column="1" border>
        <el-descriptions-item label="消息 ID">
{{ detail.telegram_message_id }}
</el-descriptions-item>
        <el-descriptions-item label="频道 ID">
{{ detail.telegram_chat_id }}
</el-descriptions-item>
        <el-descriptions-item label="发布时间">
{{ new Date(detail.message_date).toLocaleString() }}
</el-descriptions-item>
        <el-descriptions-item label="编辑时间">
{{ detail.edit_date ? new Date(detail.edit_date).toLocaleString() : '未编辑' }}
</el-descriptions-item>
        <el-descriptions-item label="浏览 / 转发">
{{ detail.views ?? '—' }} / {{ detail.forwards ?? '—' }}
</el-descriptions-item>
        <el-descriptions-item label="回复消息 ID">
{{ detail.reply_to_message_id ?? '—' }}
</el-descriptions-item>
        <el-descriptions-item label="媒体">
{{ detail.media_type || '无' }} · {{ detail.media_status }}
</el-descriptions-item>
        <el-descriptions-item label="正文">
<span class="message-text">{{ detail.text || '（无文字内容）' }}</span>
</el-descriptions-item>
      </el-descriptions>
    </el-drawer>
  </div>
</template>
