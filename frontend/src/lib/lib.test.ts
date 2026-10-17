import { describe, expect, it } from 'vitest'
import { sourceHealth } from '../pages/AdminPage'
import { RUN } from '../test/fakeApi'
import { deadlineState, formatDateTime, isSafeSourceUrl, isStale, istDayEnd, istDayStart } from './format'
import { createApiFromEnv, sanitizeSearch } from './supabaseApi'

describe('format', () => {
  it('formats in IST and labels it', () => {
    expect(formatDateTime('2026-10-17T11:47:03Z')).toMatch(/17 Oct 2026.*05:17.*pm IST/i)
    expect(formatDateTime(null)).toBeNull()
    expect(formatDateTime('garbage')).toBeNull()
  })

  it('computes IST day bounds', () => {
    expect(istDayStart('2030-01-31')).toBe('2030-01-31T00:00:00+05:30')
    expect(istDayEnd('2030-01-31')).toBe('2030-02-01T00:00:00+05:30')
    expect(istDayEnd('2028-12-31')).toBe('2029-01-01T00:00:00+05:30')
  })

  it('classifies deadlines', () => {
    const now = new Date('2030-01-10T00:00:00Z')
    expect(deadlineState(null, now)).toBe('unknown')
    expect(deadlineState('2030-01-09T00:00:00Z', now)).toBe('closed')
    expect(deadlineState('2030-01-11T00:00:00Z', now)).toBe('closing-soon')
    expect(deadlineState('2030-02-01T00:00:00Z', now)).toBe('open')
  })

  it('detects stale data', () => {
    const now = new Date('2030-01-10T00:00:00Z')
    expect(isStale(null, now)).toBe(true)
    expect(isStale('2030-01-09T00:00:00Z', now)).toBe(false)
    expect(isStale('2030-01-08T00:00:00Z', now)).toBe(true)
  })

  it('only allows https GeM links', () => {
    expect(isSafeSourceUrl('https://bidplus.gem.gov.in/showbidDocument/1')).toBe(true)
    expect(isSafeSourceUrl('https://gem.gov.in/')).toBe(true)
    for (const bad of ['http://gem.gov.in/', 'https://gem.gov.in.evil.com/', 'javascript:alert(1)', 'https://evilgem.gov.in/', null]) {
      expect(isSafeSourceUrl(bad)).toBe(false)
    }
  })
})

describe('supabase api', () => {
  it('neutralises PostgREST filter syntax in search input', () => {
    expect(sanitizeSearch('a,b),title.eq.x(*%')).toBe('a b title.eq.x')
    expect(sanitizeSearch('  GEM/2026/B/1  ')).toBe('GEM/2026/B/1')
    expect(sanitizeSearch('x'.repeat(500))).toHaveLength(100)
  })

  it('is not configured without public env values or with placeholders', () => {
    expect(createApiFromEnv({} as ImportMetaEnv)).toBeNull()
    expect(
      createApiFromEnv({ VITE_SUPABASE_URL: 'https://your-project-ref.supabase.co', VITE_SUPABASE_ANON_KEY: 'x' } as ImportMetaEnv),
    ).toBeNull()
  })
})

describe('source health', () => {
  it('summarises the latest status per source', () => {
    const older = { ...RUN, id: 'run-0', started_at: '2030-01-09T01:00:00+00:00', source_results: { b_source: { status: 'success' } } }
    const health = sourceHealth([RUN, older])
    expect(health.map((h) => [h.name, h.lastStatus, h.lastSuccessAt])).toEqual([
      ['a_source', 'success', RUN.started_at],
      ['b_source', 'failed', older.started_at],
    ])
  })
})
