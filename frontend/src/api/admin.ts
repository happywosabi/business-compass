import { ApiError } from './client'

export interface AdminSession { expires_at: string | null; unlocked: boolean }
export interface Page<T> { items: T[]; next_cursor: string | null }
export interface UserState { status: string; daily_ai_quota: number | null; is_admin: boolean; failed_login_count: number; locked_until: string | null }
export interface AdminUser extends UserState { id: string; email: string; nickname: string | null; verified: boolean; created_at: string; last_login_at: string | null; storage_bytes: number; storage_limit: number; profile_count: number; today_ai_runs: number; daily_ai_limit: number }
export interface AdminRun { id: string; user_id: string; profile_id: string; kind: string; model: string; status: string; input_tokens: number; output_tokens: number; duration_seconds: number; created_at: string; error: string | null }
export interface AdminProfile { id: string; user_id: string; name: string; industry: string; stage: string; status: string; revision: number; created_at: string; deleted_at: string | null }
export interface AdminHotspot { id: string; title: string; channel: string; safe: boolean; manually_hidden: boolean; expired: boolean; fetched_at: string }
export interface CollectionDiagnostics { stage?: string; candidates?: number; approved?: number; added?: number; embedding_fallback?: boolean; sources?: { source: string; status: string; http_status?: number; items?: number }[] }
export interface AdminCollection { id: string; status: string; model: string; embedding_model: string; input_tokens: number; output_tokens: number; embedding_tokens: number; llm_calls: number; embedding_calls: number; created_at: string; finished_at: string | null; error: string | null; diagnostics: CollectionDiagnostics }
export interface AdminAudit { id: string; actor_id: string | null; action: string; target: string; reason: string; result: string; created_at: string; ip: string | null; changes: unknown }
export interface Overview { totals: { users: number; profiles: number; calculations: number; succeeded: number; failed: number; running: number; cancelled: number; success_rate: number | null; input_tokens: number; output_tokens: number }; days: number; trend: { date: string; runs: number; tokens: number; failed: number }[]; public_hotspots: { runs: number; llm_tokens: number; embedding_tokens: number } }
export interface SystemState { database: string; version: string; models: Record<string, string>; configured: Record<string, boolean>; worker: { last_seen: string | null; stale: boolean }; last_collection: { status: string; created_at: string; finished_at: string | null; llm_calls: number; embedding_calls: number } | null; default_daily_ai_quota: number; public_hot_daily_limit: number }

export function userState(user: AdminUser): UserState {
  return { status: user.status, daily_ai_quota: user.daily_ai_quota, is_admin: user.is_admin, failed_login_count: user.failed_login_count, locked_until: user.locked_until }
}

export function queryString(values: Record<string, string | number | undefined>): string {
  const query = new URLSearchParams()
  for (const [key, value] of Object.entries(values)) if (value !== '' && value !== undefined) query.set(key, String(value))
  return query.size ? `?${query}` : ''
}

export async function adminRequest<T>(path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  let response: Response
  try {
    response = await fetch(`/api/admin${path}`, {
      method: body === undefined ? 'GET' : 'POST', cache: 'no-store', credentials: 'same-origin',
      headers: body === undefined ? { Accept: 'application/json' } : { Accept: 'application/json', 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body), signal,
    })
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') throw error
    throw new ApiError(0, '网络连接失败，请重试')
  }
  const data = await response.json().catch(() => null)
  if (!response.ok) throw new ApiError(response.status, typeof data?.detail === 'string' ? data.detail : '请求失败，请检查输入后重试')
  return data as T
}
