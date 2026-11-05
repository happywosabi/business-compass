/** 当前登录用户。整个网站共用这一份。 */

import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { authApi, type User } from '@/api/auth'
import { ApiError } from '@/api/client'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<User | null>(null)
  /** 是否已经向后端确认过登录状态 */
  const loaded = ref(false)
  let pending: Promise<void> | null = null

  const isVerified = computed(() => user.value?.email_verified === true)

  /** 向后端确认当前是否已登录。网络出错时不报错，按未登录处理，下次跳转页面时再试 */
  async function refresh(): Promise<void> {
    try {
      user.value = await authApi.me()
      loaded.value = true
    } catch (error) {
      user.value = null
      if (error instanceof ApiError && error.status === 401) loaded.value = true
    }
  }

  /** 第一次需要时才检查登录状态；同时有多处调用时只发一次请求 */
  function ensureLoaded(): Promise<void> {
    if (loaded.value) return Promise.resolve()
    pending ??= refresh().finally(() => {
      pending = null
    })
    return pending
  }

  async function login(email: string, password: string): Promise<void> {
    user.value = await authApi.login({ email, password })
    loaded.value = true
  }

  async function logout(): Promise<void> {
    try {
      await authApi.logout()
    } finally {
      // 网络出错也在本地退出，Cookie 过期后服务器上的会话自然失效
      user.value = null
    }
  }

  /** 会话已在服务器上失效（登录过期、重置了密码）时清掉本地状态 */
  function clear(): void {
    user.value = null
  }

  return { user, loaded, isVerified, refresh, ensureLoaded, login, logout, clear }
})
