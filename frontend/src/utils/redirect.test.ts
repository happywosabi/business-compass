import { describe, expect, it } from 'vitest'

import { safeRedirect } from './redirect'

describe('safeRedirect', () => {
  it.each(['/', '/me', '/me/password', '/profiles/abc?tab=1#top'])('allows %s', (path) => {
    expect(safeRedirect(path)).toBe(path)
  })

  it.each([
    'https://evil.example.com',
    '//evil.example.com',
    '/\\evil.example.com',
    'javascript:alert(1)',
    'me',
    '/me\n/evil',
    '/login',
    '/login?redirect=/me',
    '/register',
    '',
  ])('rejects %j', (path) => {
    expect(safeRedirect(path)).toBe('/')
  })

  it('takes the first value when the query has several', () => {
    expect(safeRedirect(['/me', '/'])).toBe('/me')
  })

  it('falls back for missing values', () => {
    expect(safeRedirect(undefined)).toBe('/')
    expect(safeRedirect(null, '/me')).toBe('/me')
  })
})
