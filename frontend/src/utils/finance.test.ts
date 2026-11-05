import { describe, expect, it } from 'vitest'
import { fundingRange, money, monthLabel, payback } from './finance'

describe('结果页数字展示', () => {
  it('明确区分无法给出资金建议和零资金', () => {
    expect(fundingRange(null)).toBe('先调整方案')
    expect(fundingRange([0, 10000])).toBe('0–1 万')
    expect(fundingRange([341040, 378040])).toBe('34.1–37.8 万')
  })
  it('保留超过展示窗口的回本月份并统一负数格式', () => {
    expect(payback(41)).toBe('第 41 个月')
    expect(payback(null)).toBe('10 年内回不了本')
    expect(money(-34000)).toBe('−34,000')
    expect(monthLabel(0)).toBe('开业前')
  })
})
