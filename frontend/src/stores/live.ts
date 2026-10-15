import { defineStore } from 'pinia'
import { ref } from 'vue'
import { useMessagesStore } from './messages'
import type { LiveEvent } from '../types/api'

export const useLiveStore = defineStore('live', () => {
  const connected = ref(false)
  let socket: WebSocket | null = null
  let retryTimer: number | undefined
  let attempts = 0
  let stopped = false
  let subscribed: string[] = []

  function subscribe(channelIds: string[]): void {
    subscribed = channelIds
    if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ action: 'subscribe', channel_ids: channelIds }))
  }

  function connect(): void {
    stopped = false
    if (socket && (socket.readyState === WebSocket.CONNECTING || socket.readyState === WebSocket.OPEN)) return
    const scheme = location.protocol === 'https:' ? 'wss:' : 'ws:'
    socket = new WebSocket(`${scheme}//${location.host}/api/v1/ws`)
    socket.onopen = () => {
      connected.value = true
      attempts = 0
      subscribe(subscribed)
      window.dispatchEvent(new Event('tcm:refresh'))
    }
    socket.onmessage = (message: MessageEvent<string>) => {
      try {
        const event = JSON.parse(message.data) as LiveEvent
        window.dispatchEvent(new CustomEvent('tcm:event', { detail: event }))
        const messages = useMessagesStore()
        if (event.channel_id === messages.channelId && event.type.startsWith('message.')) void messages.load()
      } catch { /* Invalid events are ignored; REST refetch restores state. */ }
    }
    socket.onclose = () => {
      connected.value = false
      socket = null
      if (!stopped) retryTimer = window.setTimeout(connect, Math.min(30000, 1000 * 2 ** attempts++))
    }
    socket.onerror = () => socket?.close()
  }

  function disconnect(): void {
    stopped = true
    connected.value = false
    if (retryTimer) window.clearTimeout(retryTimer)
    socket?.close()
    socket = null
  }
  return { connected, connect, disconnect, subscribe }
})
