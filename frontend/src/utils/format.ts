/**
 * 数字展示规则，见 docs/前端设计.md 第五节。
 * 所有页面都用这里的函数，保证同一个数在各处显示得一样。
 */

const MINUS = '−' // 全角减号「−」，比连字符「-」更醒目
const thousands = new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 })

/** 金额：≥ 1 万显示为「34.1 万」，< 1 万显示为「6,000 元」，负数带「−」 */
export function formatMoney(value: number): string {
  const amount = Math.round(Math.abs(value))
  const sign = value < 0 && amount > 0 ? MINUS : ''
  if (amount >= 10000) return `${sign}${(amount / 10000).toFixed(1)} 万`
  return `${sign}${thousands.format(amount)} 元`
}

/** 金额区间：「34.1 万–37.8 万」 */
export function formatMoneyRange(low: number, high: number): string {
  return `${formatMoney(low)}–${formatMoney(high)}`
}

/** 表格里的金额：统一用元、千分位；signed 为 true 时正数带「+」 */
export function formatYuan(value: number, signed = false): string {
  const amount = Math.round(Math.abs(value))
  const text = thousands.format(amount)
  if (amount === 0) return '0'
  if (value < 0) return MINUS + text
  return signed ? `+${text}` : text
}

/** 回本月份：null 表示计算引擎推演 120 个月仍未回本 */
export function formatMonth(month: number | null): string {
  return month === null ? '10 年内回不了本' : `第 ${month} 个月`
}

/** 比例：0.36 →「36%」 */
export function formatPercent(ratio: number): string {
  const percent = Math.round(ratio * 100)
  return `${percent < 0 ? MINUS : ''}${Math.abs(percent)}%`
}

/** 「至少要卖」这类数量向上取整：146.83 → 147（先去掉浮点误差，避免 147.0000001 变成 148） */
export function atLeast(value: number): number {
  return Math.ceil(Math.round(value * 1e6) / 1e6)
}

/** 按业态显示单量的单位：饮品用「杯」，零售用「笔」，其他用「单」 */
export function unitFor(industry: string | null | undefined): string {
  if (industry === 'drinks') return '杯'
  if (industry === 'retail') return '笔'
  return '单'
}

const dateFormat = new Intl.DateTimeFormat('zh-CN', {
  timeZone: 'Asia/Shanghai',
  year: 'numeric',
  month: 'long',
  day: 'numeric',
})

/** 日期：后端存的是 UTC，按北京时间显示为「2026年11月5日」 */
export function formatDate(iso: string): string {
  const date = new Date(iso)
  return Number.isNaN(date.getTime()) ? '' : dateFormat.format(date)
}
