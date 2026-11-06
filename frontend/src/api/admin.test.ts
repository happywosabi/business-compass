import { afterEach, describe, expect, it, vi } from 'vitest'
import { adminRequest, queryString, userState, type AdminUser } from './admin'

afterEach(() => vi.unstubAllGlobals())
describe('管理接口边界', () => {
  it('按需构造筛选参数', () => {
    expect(queryString({ q: 'a+b@example.com', cursor: undefined, status: '', limit: 20 })).toBe('?q=a%2Bb%40example.com&limit=20')
  })
  it('管理数据使用同源会话且禁止缓存', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ ok: true }), { status: 200 }))
    vi.stubGlobal('fetch', fetch)
    await adminRequest('/users/123/actions', { action: 'disable', reason: '确认账号异常' })
    expect(fetch).toHaveBeenCalledWith('/api/admin/users/123/actions', expect.objectContaining({ method: 'POST', cache: 'no-store', credentials: 'same-origin', headers: expect.objectContaining({ 'Content-Type': 'application/json' }) }))
  })
  it('保留锁定状态供页面清空资料并重新验证', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: '请重新验证密码' }), { status: 423 })))
    await expect(adminRequest('/profiles')).rejects.toMatchObject({ status: 423, message: '请重新验证密码' })
  })
  it('并发确认仅提交需要比较的状态', () => {
    const user = { id: '123', email: 'test@example.com', status: 'active', daily_ai_quota: null, is_admin: false, failed_login_count: 0, locked_until: null } as AdminUser
    expect(userState(user)).toEqual({ status: 'active', daily_ai_quota: null, is_admin: false, failed_login_count: 0, locked_until: null })
  })
})
