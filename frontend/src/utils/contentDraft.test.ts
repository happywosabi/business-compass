import { describe, expect, it } from 'vitest'
import { fillField, pendingFields, removeFieldLine } from './contentDraft'

describe('待填草稿', () => {
  const field = '【待填：赠品款式】'
  const content = `今天买奶茶送周边🎁\n\n周边：${field}\n\n#深圳奶茶`

  it('区分未填提示和已确认内容，填入后保留正文排版', () => {
    expect(pendingFields(content)).toEqual([field])
    const filled = fillField(content, field, ' 哪吒贴纸 ')
    expect(filled).toContain('周边：哪吒贴纸')
    expect(filled).toContain('今天买奶茶送周边🎁')
    expect(pendingFields(filled)).toEqual([])
    expect(fillField(content, field, '  ')).toBe(content)
    expect(fillField(content, field, '【待填：还不知道】')).toBe(content)
  })

  it('同一提示只需填一次，也可以明确删去整条待填行', () => {
    expect(pendingFields(`${content}\n${field}`)).toEqual([field])
    expect(fillField(`${field}\n${field}`, field, '贴纸')).toBe('贴纸\n贴纸')
    expect(removeFieldLine(content, field)).toBe('今天买奶茶送周边🎁\n\n#深圳奶茶')
  })
})
