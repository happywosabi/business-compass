import { api, ApiError } from './client'

export interface Run {
  id: string
  request_id: string
  status: 'running' | 'succeeded' | 'failed' | 'cancelled'
  output: { content?: string; quick_replies?: string[]; evaluation_id?: string; confirmation?: Confirmation }
  error?: string
}
export interface Confirmation {
  id: string
  action: 'evaluation' | 'defaults' | 'apply'
  revision: number
  payload: { keys?: string[]; changes?: Record<string, unknown> }
  expires_at: string
}
export interface ChatMessage {
  id: string
  run_id: string
  role: string
  content: string
  tool_calls: boolean
}
export interface ChatHistory {
  messages: ChatMessage[]
  runs: Run[]
}
export const interviewApi = {
  confirmations: (id: string) => api.get<Confirmation[]>(`/api/profiles/${id}/confirmations`),
  confirm: (id: string, action: Confirmation) => api.post<{evaluation_id?: string}>(`/api/profiles/${id}/confirmations/${action.id}/confirm`, {revision: action.revision}),
  history: (id: string) => api.get<ChatHistory>(`/api/profiles/${id}/interview`),
  run: (id: string, rid: string) => api.get<Run>(`/api/profiles/${id}/interview/runs/${rid}`),
  cancel: (id: string, rid: string) =>
    api.post<Run>(`/api/profiles/${id}/interview/runs/${rid}/cancel`),
}

export interface StreamEvent {
  event: string
  data: Record<string, unknown>
}

/** SSE 事件边界与 UTF-8 字符都可能跨网络分片；心跳不当成消息。 */
export async function readEvents(
  stream: ReadableStream<Uint8Array>,
  consume: (event: StreamEvent) => void,
) {
  const reader = stream.getReader(),
    decoder = new TextDecoder()
  let buffer = ''
  function drain(final = false) {
    // 标准支持 CRLF，保留跨分片的 CR。
    buffer = buffer.replace(/\r\n/g, '\n')
    let boundary: number
    while ((boundary = buffer.indexOf('\n\n')) !== -1) {
      const block = buffer.slice(0, boundary)
      buffer = buffer.slice(boundary + 2)
      const lines = block.split('\n')
      const event =
        lines
          .find((line) => line.startsWith('event:'))
          ?.slice(6)
          .trim() ?? 'message'
      const data = lines
        .filter((line) => line.startsWith('data:'))
        .map((line) => line.slice(5).trimStart())
        .join('\n')
      if (data) consume({ event, data: JSON.parse(data) })
    }
    if (final && buffer.trim() && !buffer.trim().startsWith(':'))
      throw new Error('回复连接中断，请恢复对话')
  }
  try {
    while (true) {
      const { done, value } = await reader.read()
      buffer += done ? decoder.decode() : decoder.decode(value, { stream: true })
      drain(done)
      if (done) break
    }
  } finally {
    reader.releaseLock()
  }
}

export async function sendInterview(
  id: string,
  body: { request_id: string; revision: number; content: string },
  signal: AbortSignal,
  consume: (event: StreamEvent) => void,
) {
  const response = await fetch(`/api/profiles/${id}/interview/messages`, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify(body),
    signal,
  })
  if (!response.ok) {
    const json = await response.json().catch(() => ({}))
    throw new ApiError(response.status, json.detail ?? '连接失败，请稍后重试')
  }
  if (!response.body) throw new Error('浏览器无法读取流式回复')
  await readEvents(response.body, consume)
}
