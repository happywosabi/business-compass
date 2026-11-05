import type { components } from './schema'
export type OrchardParams = components['schemas']['OrchardParams']
export type OrchardSection = components['schemas']['OrchardSection']
export type OrchardResult = components['schemas']['OrchardResult']
export type OrchardWhatIf = components['schemas']['OrchardWhatIf']
export type Variety = components['schemas']['Variety']
export type Grade = components['schemas']['Grade']
export type OrchardChannel = components['schemas']['OrchardChannel']
export type Amount = components['schemas']['Amount']
export const channel = (kind: 'wholesale' | 'retail', share = 1): OrchardChannel => ({
  id: crypto.randomUUID(),
  kind,
  share,
  price: null,
  packaging_per_kg: null,
  logistics_per_kg: null,
  fee_rate: null,
})
export const grade = (): Grade => ({
  id: crypto.randomUUID(),
  name: '统货',
  share: 1,
  sell_through: null,
  channels: [channel('wholesale')],
})
export const variety = (): Variety => ({
  id: crypto.randomUUID(),
  name: '',
  area_mu: null,
  harvest_kg: null,
  loss_rate: null,
  grades: [grade()],
  costs: { inputs: null, irrigation: null, paid_labor: null, other: null },
})
export function orchardChanges(section: OrchardSection) {
  return Object.fromEntries(Object.entries(section).map(([k, v]) => [`orchard.${k}`, v]))
}
