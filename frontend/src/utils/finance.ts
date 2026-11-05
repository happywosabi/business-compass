import { formatYuan, formatMonth } from './format'
export const money = (value: number, digits = 0) =>
  digits === 0
    ? formatYuan(value)
    : value.toLocaleString('zh-CN', { maximumFractionDigits: digits }).replace('-', '−')
export const wan = (value: number) => money(value / 10000, 1)
export const payback = (value: number | null) => formatMonth(value)
export const monthLabel = (value: number) => (value === 0 ? '开业前' : `第 ${value} 个月`)
export function fundingRange(values: number[] | null | undefined) {
  return values?.length === 2 ? `${wan(values[0]!)}–${wan(values[1]!)} 万` : '先调整方案'
}
