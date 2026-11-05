import { api } from './client'
import type { components } from './schema'

type Schemas = components['schemas']
export type StoreEvaluation = Omit<
  Schemas['EvaluationOut'],
  'template_key' | 'parameters' | 'results'
> & {
  template_key: 'physical_store'
  parameters: Schemas['PhysicalStoreParams']
  results: Schemas['EvaluationResult']
}
export type OrchardEvaluation = Omit<
  Schemas['EvaluationOut'],
  'template_key' | 'parameters' | 'results'
> & {
  template_key: 'orchard'
  parameters: Schemas['OrchardParams']
  results: Schemas['OrchardResult']
}
export type Evaluation = StoreEvaluation | OrchardEvaluation
export type ScenarioResult = Schemas['ScenarioResult']
export type WhatIf = Schemas['WhatIfResult']
export const evaluationsApi = {
  create: (id: string, revision: number) =>
    api.post<Evaluation>(`/api/profiles/${id}/evaluations`, { revision }),
  list: (id: string, offset = 0) =>
    api.get<Evaluation[]>(`/api/profiles/${id}/evaluations?offset=${offset}`),
  get: (id: string, eid: string) => api.get<Evaluation>(`/api/profiles/${id}/evaluations/${eid}`),
  label: (id: string, eid: string, label: string) =>
    api.patch<Evaluation>(`/api/profiles/${id}/evaluations/${eid}`, { label: label || null }),
  preview: (id: string, body: Schemas['WhatIfRequest']) =>
    api.post<WhatIf>(`/api/profiles/${id}/what-if`, body),
  apply: (id: string, body: Schemas['ApplyWhatIf']) =>
    api.post<Evaluation>(`/api/profiles/${id}/what-if/apply`, body),
}
