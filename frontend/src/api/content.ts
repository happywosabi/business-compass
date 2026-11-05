import { api } from './client'
export interface Topic {
  id: string
  title: string
  angle: string
  date: string | null
  kind: string
  sources: { title: string; url: string | null; excerpt: string; retrieved_at: string }[]
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
  drafts: (id: string) => api.get<Draft[]>(`/api/profiles/${id}/content/drafts`),
  create: (
    id: string,
    body: {
      request_id: string
      topic_id: string
      platform: string
      confirmed_facts: string
      voice: string
    },
  ) => api.post<Draft>(`/api/profiles/${id}/content/drafts`, body),
}
