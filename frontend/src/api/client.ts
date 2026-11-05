/**
 * 调用后端接口的统一入口。
 *
 * - 登录状态靠后端设置的 HttpOnly Cookie，浏览器自动带上，前端不保存任何令牌
 * - 所有错误都转换成 ApiError，它的 message 是可以直接展示给用户的中文
 */

export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

type Method = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'

interface RequestOptions {
  /** 401 是正常结果时（如登录时密码错误、检查是否已登录），不触发「登录已过期」处理 */
  silent401?: boolean
}

let unauthorizedHandler: (() => void) | null = null

/** 已登录状态下接口返回 401（登录过期、在别的设备改了密码）时调用，由 main.ts 设置 */
export function setUnauthorizedHandler(handler: () => void): void {
  unauthorizedHandler = handler
}

function messageFor(status: number, detail: unknown): string {
  if (typeof detail === 'string' && detail) return detail
  if (status === 422) return '填写的内容格式不正确，请检查后再试'
  if (status === 429) return '操作太频繁，请稍后再试'
  if (status >= 500) return '服务器出了点问题，请稍后再试'
  return `请求失败（${status}）`
}

export async function request<T>(
  method: Method,
  path: string,
  body?: unknown,
  options: RequestOptions = {},
): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' }
  if (body !== undefined) headers['Content-Type'] = 'application/json'

  let response: Response
  try {
    response = await fetch(path, {
      method,
      headers,
      credentials: 'same-origin',
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  } catch {
    throw new ApiError(0, '网络不好，请检查网络后重试')
  }

  // Nginx 限流（429）或后端没启动（502）时返回的是网页而不是 JSON，解析失败也没关系
  let data: unknown = null
  const text = await response.text()
  if (text) {
    try {
      data = JSON.parse(text)
    } catch {
      data = null
    }
  }

  if (!response.ok) {
    const detail = data && typeof data === 'object' ? (data as { detail?: unknown }).detail : undefined
    if (response.status === 401 && !options.silent401) unauthorizedHandler?.()
    throw new ApiError(response.status, messageFor(response.status, detail))
  }
  return data as T
}

export const api = {
  get: <T>(path: string, options?: RequestOptions) => request<T>('GET', path, undefined, options),
  post: <T>(path: string, body: unknown = {}, options?: RequestOptions) =>
    request<T>('POST', path, body, options),
}

/** 把任意错误变成给用户看的一句话 */
export function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : '出了点问题，请稍后再试'
}
