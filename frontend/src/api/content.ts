import { api } from './client'
export interface Topic {
  id: string
  title: string
  angle: string
  date: string | null
  kind: string
  sources: {
    title: string
    url: string | null
    excerpt: string
    retrieved_at: string
    published_at?: string
    publisher?: string
    kind?: string
    status?: string
  }[]
}
export interface Draft {
  id: string
  platform: string
  topic: string
  angle: string
  sources: Topic['sources']
  content: string | null
  status: string
  created_at: string
}
export const contentApi = {
  topics: (id: string) => api.get<Topic[]>(`/api/profiles/${id}/content/topics`),
  hotTopics: (id: string) => api.get<Topic[]>(`/api/profiles/${id}/content/hot-topics`),
  refreshHotTopics: (id: string) =>
    api.post<{ topics: Topic[]; error: string | null; message?: string }>(`/api/profiles/${id}/content/hot-topics/refresh`, {}),
  drafts: (id: string) => api.get<Draft[]>(`/api/profiles/${id}/content/drafts`),
  create: (
    id: string,
    body: {
      request_id: string
      topic_id: string
      hot_topic_id?: string
      platform: string
      confirmed_facts: string
      voice: string
      audience?: 'buyers' | 'consumers'
    },
  ) => api.post<Draft>(`/api/profiles/${id}/content/drafts`, body),
}
