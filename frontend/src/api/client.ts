import axios, { type AxiosRequestConfig } from 'axios'
import type { ApiError, AppSettings, AuthMe, AvailableChannel, Channel, Dashboard, Message, Page, SettingsResponse, Task, TelegramStatus } from '../types/api'

const client = axios.create({ baseURL: import.meta.env.VITE_API_BASE || '/api/v1', withCredentials: true, timeout: 30000 })
let csrfToken = ''
export function setCsrfToken(value: string): void { csrfToken = value }
client.interceptors.request.use((config) => {
  if (csrfToken && config.method && !['get', 'head', 'options'].includes(config.method.toLowerCase())) {
    config.headers.set('X-CSRF-Token', csrfToken)
  }
  return config
})

export function errorMessage(error: unknown): string {
  if (axios.isAxiosError<ApiError>(error)) return error.response?.data?.error?.message || error.message
  return error instanceof Error ? error.message : '操作失败'
}

async function get<T>(url: string, config?: AxiosRequestConfig): Promise<T> { return (await client.get<T>(url, config)).data }
async function post<T>(url: string, body?: unknown): Promise<T> { return (await client.post<T>(url, body)).data }
async function put<T>(url: string, body: unknown): Promise<T> { return (await client.put<T>(url, body)).data }
async function del<T>(url: string): Promise<T> { return (await client.delete<T>(url)).data }
const channelPath = (id: string) => `/channels/${encodeURIComponent(id)}`

export const api = {
  authMe: () => get<AuthMe>('/auth/me'),
  authLogin: (password: string) => post<AuthMe>('/auth/login', { password }),
  authLogout: () => post<{ ok: boolean }>('/auth/logout'),
  dashboard: () => get<Dashboard>('/dashboard'),
  telegramStatus: () => get<TelegramStatus>('/telegram/status'),
  telegramLogin: (phone: string) => post<TelegramStatus>('/telegram/login', { phone }),
  telegramVerify: (code?: string, password?: string) => post<TelegramStatus>('/telegram/login/verify', { code, password }),
  telegramDisconnect: () => post<TelegramStatus>('/telegram/disconnect'),
  telegramReconnect: () => post<TelegramStatus>('/telegram/reconnect'),
  availableChannels: () => get<AvailableChannel[]>('/channels/available'),
  channels: (params?: Record<string, string | number>) => get<Page<Channel>>('/channels', { params }),
  addChannels: (telegram_chat_ids: string[]) => post<Channel[]>('/channels', { telegram_chat_ids }),
  channel: (id: string) => get<Channel>(channelPath(id)),
  removeChannel: (id: string) => del<{ ok: boolean }>(channelPath(id)),
  purgeChannel: (id: string) => post<{ ok: boolean }>(`${channelPath(id)}/purge`, { confirm_telegram_chat_id: id }),
  syncChannel: (id: string) => post<Task>(`${channelPath(id)}/sync`),
  reconcileChannel: (id: string) => post<Task>(`${channelPath(id)}/reconcile`),
  listenChannel: (id: string) => post<Channel>(`${channelPath(id)}/listen`),
  stopListenChannel: (id: string) => del<Channel>(`${channelPath(id)}/listen`),
  messages: (id: string, params: Record<string, string | number>, signal?: AbortSignal) => get<Page<Message>>(`${channelPath(id)}/messages`, { params, signal }),
  message: (id: string, messageId: string) => get<Message>(`${channelPath(id)}/messages/${encodeURIComponent(messageId)}`),
  mediaUrl: (id: string, messageId: string) => `${client.defaults.baseURL}${channelPath(id)}/messages/${encodeURIComponent(messageId)}/media`,
  downloadMedia: (id: string, messageId: string) => post<Task>(`${channelPath(id)}/messages/${encodeURIComponent(messageId)}/media/download`),
  tasks: (params?: Record<string, string | number>) => get<Page<Task>>('/tasks', { params }),
  task: (id: string) => get<Task>(`/tasks/${encodeURIComponent(id)}`),
  taskAction: (id: string, action: 'pause' | 'cancel' | 'resume' | 'retry') => post<Task>(`/tasks/${encodeURIComponent(id)}/${action}`),
  exports: (params?: Record<string, string | number>) => get<Page<Task>>('/exports', { params }),
  createExport: (body: { telegram_chat_id: string | null; format: 'json' | 'jsonl' | 'zip'; include_media: boolean; media_only: boolean; date_from: string | null; date_to: string | null }) => post<Task>('/exports', body),
  exportUrl: (id: string) => `${client.defaults.baseURL}/exports/${encodeURIComponent(id)}/download`,
  settings: () => get<SettingsResponse>('/settings'),
  saveSettings: (values: AppSettings) => put<SettingsResponse>('/settings', values),
}

export const getMessages = api.messages

