import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, expect, it, vi } from 'vitest'

const { getMessages } = vi.hoisted(() => ({ getMessages: vi.fn() }))
vi.mock('../api/client', () => ({ getMessages, errorMessage: (error: Error) => error.message }))

import { useMessagesStore } from './messages'

beforeEach(() => {
  setActivePinia(createPinia())
  getMessages.mockReset()
})

it('keeps the selected channel when an older request resolves late', async () => {
  let resolveOld!: (value: unknown) => void
  getMessages.mockImplementationOnce(() => new Promise((resolve) => { resolveOld = resolve }))
  getMessages.mockResolvedValueOnce({ items: [{ telegram_message_id: '2' }], total: 1, page: 1, page_size: 30 })
  const store = useMessagesStore()
  const old = store.selectChannel('-1001')
  await store.selectChannel('-1002')
  resolveOld({ items: [{ telegram_message_id: '1' }], total: 1, page: 1, page_size: 30 })
  await old
  expect(store.channelId).toBe('-1002')
  expect(store.items[0]?.telegram_message_id).toBe('2')
})
