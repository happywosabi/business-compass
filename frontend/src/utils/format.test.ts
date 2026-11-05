import { describe, expect, it } from 'vitest'

import {
  atLeast,
  formatDate,
  formatMoney,
  formatMoneyRange,
  formatMonth,
  formatPercent,
  formatYuan,
  unitFor,
} from './format'

describe('formatMoney', () => {
  it.each([
    [341040, '34.1 万'],
    [10000, '1.0 万'],
    [6000, '6,000 元'],
    [9999.6, '1.0 万'], // 四舍五入到元以后满 1 万
    [-267040, '−26.7 万'],
    [-500, '−500 元'],
    [-0.4, '0 元'], // 四舍五入后是 0，不显示负号
    [0, '0 元'],
  ])('%s → %s', (value, text) => {
    expect(formatMoney(value)).toBe(text)
  })

  it('formats a range', () => {
    expect(formatMoneyRange(341040, 378040)).toBe('34.1 万–37.8 万')
  })
})

describe('formatYuan', () => {
  it.each([
    [-11800, false, '−11,800'],
    [13400, true, '+13,400'],
    [13400, false, '13,400'],
    [0.3, true, '0'],
    [-251000, true, '−251,000'],
  ])('%s (signed=%s) → %s', (value, signed, text) => {
    expect(formatYuan(value, signed)).toBe(text)
  })
})

describe('formatMonth', () => {
  it('shows the month', () => expect(formatMonth(21)).toBe('第 21 个月'))
  it('handles never paying back', () => expect(formatMonth(null)).toBe('10 年内回不了本'))
})

describe('formatPercent', () => {
  it.each([
    [0.36, '36%'],
    [0.266, '27%'],
    [-0.162, '−16%'],
    [-0.001, '0%'],
  ])('%s → %s', (ratio, text) => {
    expect(formatPercent(ratio)).toBe(text)
  })
})

describe('atLeast', () => {
  it('rounds up', () => expect(atLeast(146.83)).toBe(147))
  it('ignores floating point noise', () => expect(atLeast(147.0000000001)).toBe(147))
  it('keeps whole numbers', () => expect(atLeast(147)).toBe(147))
})

describe('unitFor', () => {
  it.each([
    ['drinks', '杯'],
    ['retail', '笔'],
    ['restaurant', '单'],
    [null, '单'],
  ])('%s → %s', (industry, unit) => {
    expect(unitFor(industry)).toBe(unit)
  })
})

describe('formatDate', () => {
  it('uses Beijing time', () => {
    // UTC 11 月 4 日 18:00 = 北京时间 11 月 5 日 02:00
    expect(formatDate('2026-11-04T18:00:00Z')).toBe('2026年11月5日')
  })
  it('returns empty text for bad input', () => expect(formatDate('not a date')).toBe(''))
})
