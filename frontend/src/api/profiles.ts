import { api } from './client'
import type { components } from './schema'

type Schemas = components['schemas']
export type Profile = Schemas['ProfileOut']
export type ProfileSummary = Schemas['ProfileSummary']
export type Template = Schemas['TemplateOut']
export type Field = Template['fields'][number]
export type Change = Schemas['ChangeOut']
export type View = 'active' | 'archived' | 'deleted'
export interface Parameter {
  base: unknown
  pessimistic?: unknown
  optimistic?: unknown
  source: string
  note?: string | null
}

export const profilesApi = {
  templates: (industry?: string) =>
    api.get<Template[]>(
      industry === 'fruit_retail' ? '/api/templates?industry=fruit_retail' : '/api/templates',
    ),
  list: (view: View = 'active', cursor?: string) => api.get<Schemas['ProfilePage']>(`/api/profiles?view=${view}${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ''}`),
  summaries: async () => {
    const items: ProfileSummary[] = []
    let cursor: string | undefined
    do {
      const page = await profilesApi.list('active', cursor)
      items.push(...page.items)
      cursor = page.next_cursor ?? undefined
    } while (cursor)
    return items
  },
  get: (id: string) => api.get<Profile>(`/api/profiles/${id}`),
  create: (body: Schemas['ProfileCreate']) => api.post<Profile>('/api/profiles', body),
  update: (id: string, body: Schemas['ProfileUpdate']) =>
    api.patch<Profile>(`/api/profiles/${id}`, body),
  parameters: (id: string, revision: number, changes: Record<string, unknown>) =>
    api.patch<Profile>(`/api/profiles/${id}/parameters`, { revision, changes }),
  defaults: (id: string, revision: number, keys: string[]) =>
    api.post<Profile>(`/api/profiles/${id}/defaults`, { revision, keys }),
  copy: (id: string, revision: number) =>
    api.post<Profile>(`/api/profiles/${id}/copy`, { revision }),
  remove: (id: string, revision: number) => api.delete(`/api/profiles/${id}?revision=${revision}`),
  restore: (id: string, revision: number) =>
    api.post<Profile>(`/api/profiles/${id}/restore`, { revision }),
  changes: (id: string) => api.get<Change[]>(`/api/profiles/${id}/changes`),
}

export function parameterAt(profile: Profile, key: string): Parameter | null {
  const [section, name] = key.split('.')
  const params = profile.parameters as unknown as Record<string, Record<string, Parameter | null>>
  return params[section!]?.[name!] ?? null
}
