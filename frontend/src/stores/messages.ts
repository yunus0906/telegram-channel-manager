import { defineStore } from 'pinia'
import { reactive, ref, shallowRef } from 'vue'
import { errorMessage, getMessages } from '../api/client'
import type { Message } from '../types/api'

export const useMessagesStore = defineStore('messages', () => {
  const channelId = ref<string | null>(null)
  const items = shallowRef<Message[]>([])
  const total = ref(0)
  const page = ref(1)
  const pageSize = ref(30)
  const loading = ref(false)
  const error = ref('')
  const filters = reactive({ q: '', media_type: '', date_from: '', date_to: '' })
  let sequence = 0
  let controller: AbortController | null = null

  async function load(): Promise<void> {
    if (!channelId.value) return
    controller?.abort()
    controller = new AbortController()
    const current = ++sequence
    const selected = channelId.value
    loading.value = true
    error.value = ''
    try {
      const params: Record<string, string | number> = { page: page.value, page_size: pageSize.value }
      for (const [key, value] of Object.entries(filters)) if (value) params[key] = value
      const result = await getMessages(selected, params, controller.signal)
      if (current !== sequence || selected !== channelId.value) return
      items.value = result.items
      total.value = result.total
    } catch (cause) {
      if (current === sequence && selected === channelId.value && !(cause instanceof Error && cause.name === 'CanceledError')) {
        error.value = errorMessage(cause)
        items.value = []
      }
    } finally {
      if (current === sequence) loading.value = false
    }
  }

  async function selectChannel(id: string | null): Promise<void> {
    controller?.abort()
    sequence++
    channelId.value = id
    items.value = []
    total.value = 0
    page.value = 1
    filters.q = ''
    filters.media_type = ''
    filters.date_from = ''
    filters.date_to = ''
    if (id) await load()
  }

  async function search(): Promise<void> { page.value = 1; await load() }
  async function changePage(value: number): Promise<void> { page.value = value; await load() }
  return { channelId, items, total, page, pageSize, loading, error, filters, load, selectChannel, search, changePage }
})

