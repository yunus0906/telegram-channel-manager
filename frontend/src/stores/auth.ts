import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api, setCsrfToken } from '../api/client'

export const useAuthStore = defineStore('auth', () => {
  const authenticated = ref(false)
  const ready = ref(false)

  async function load(): Promise<void> {
    try {
      const result = await api.authMe()
      authenticated.value = result.authenticated
      setCsrfToken(result.csrf_token)
    } catch {
      authenticated.value = false
      setCsrfToken('')
    } finally {
      ready.value = true
    }
  }
  async function login(password: string): Promise<void> {
    const result = await api.authLogin(password)
    authenticated.value = result.authenticated
    setCsrfToken(result.csrf_token)
  }
  async function logout(): Promise<void> {
    await api.authLogout()
    authenticated.value = false
    setCsrfToken('')
  }
  return { authenticated, ready, load, login, logout }
})

