import type { Parameter } from '@/api/profiles'
import { formatMoney, formatPercent } from './format'

export const STAGES: Record<string, string> = {
  basic: '基本情况',
  product: '卖什么',
  shop: '铺面和装修',
  costs: '人和日常开销',
  traffic: '客流',
  none: '其他假设',
}
export const PROFILE_STAGES: Record<string, string> = {
  idea: '还在想',
  preparing: '正在筹备',
  operating: '已经开业',
}
export const LOCATIONS: Record<string, string> = {
  mall: '商场',
  street: '街边',
  school: '学校旁',
  residential: '小区',
  office: '写字楼',
  other: '其他',
}
export const SOURCES: Record<string, string> = {
  user: '你填的',
  ai_inferred: 'AI 估算',
  default: '默认值',
  experiment: '验证所得',
  actual: '真实数据',
}

export function displayValue(value: unknown, unit?: string | null, key?: string): string {
  if (value === null || value === undefined) return '待填写'
  if (Array.isArray(value)) {
    if (!value.length) return key === 'fixed_cost.staff' ? '不请员工' : '无'
    if (key === 'fixed_cost.staff')
      return value
        .map((item) => `${item.role} ${item.count} 人 × ${formatMoney(item.monthly_cost)}`)
        .join('；')
    if (key === 'revenue.channels')
      return value.map((item) => `${item.name} ${formatPercent(item.share)}`).join(' / ')
    return value
      .map((v) => (typeof v === 'number' ? `${Math.round(v * 100)}%` : String(v)))
      .join(' · ')
  }
  if (typeof value === 'number') {
    if (unit === '比例') return formatPercent(value)
    if (unit?.startsWith('元')) return formatMoney(value)
    return `${value.toLocaleString('zh-CN')}${unit === '单/天' ? ' 单/天' : unit ? ` ${unit}` : ''}`
  }
  return LOCATIONS[String(value)] ?? String(value)
}

export function displayParameter(
  param: Parameter | null,
  unit?: string | null,
  key?: string,
): string {
  return param ? displayValue(param.base, unit, key) : '待填写'
}

export type JsonSchema = {
  type?: string
  $ref?: string
  enum?: string[]
  properties?: Record<string, JsonSchema>
  items?: JsonSchema
  minimum?: number
  maximum?: number
  exclusiveMinimum?: number
}
export function resolveSchema(
  schema: JsonSchema,
  definitions: Record<string, unknown>,
): JsonSchema {
  return schema.$ref ? (definitions[schema.$ref.split('/').at(-1)!] as JsonSchema) : schema
}

export function emptyValue(schema: JsonSchema, definitions: Record<string, unknown>): unknown {
  const item = resolveSchema(schema, definitions)
  if (item.type === 'array') return []
  if (item.type === 'object')
    return Object.fromEntries(
      Object.entries(item.properties ?? {}).map(([k, v]) => [k, emptyValue(v, definitions)]),
    )
  if (item.enum) return item.enum[0]
  return item.type === 'number' || item.type === 'integer' ? null : ''
}
