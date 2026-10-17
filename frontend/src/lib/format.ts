export const IST_TZ = 'Asia/Kolkata'

const dateTimeFmt = new Intl.DateTimeFormat('en-IN', {
  timeZone: IST_TZ,
  day: '2-digit',
  month: 'short',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
  hour12: true,
})

const dateFmt = new Intl.DateTimeFormat('en-IN', { timeZone: IST_TZ, day: '2-digit', month: 'short', year: 'numeric' })

function parse(value: string | null | undefined): Date | null {
  if (!value) return null
  const d = new Date(value)
  return Number.isNaN(d.getTime()) ? null : d
}

/** "17 Oct 2026, 05:17 pm IST", or null for missing/invalid input. */
export function formatDateTime(value: string | null | undefined): string | null {
  const d = parse(value)
  return d ? `${dateTimeFmt.format(d)} IST` : null
}

export function formatDate(value: string | null | undefined): string | null {
  const d = parse(value)
  return d ? dateFmt.format(d) : null
}

export function formatRelative(value: string | null | undefined, now: Date = new Date()): string | null {
  const d = parse(value)
  if (!d) return null
  const diffMs = d.getTime() - now.getTime()
  const abs = Math.abs(diffMs)
  const units: [Intl.RelativeTimeFormatUnit, number][] = [
    ['day', 86_400_000],
    ['hour', 3_600_000],
    ['minute', 60_000],
  ]
  const rtf = new Intl.RelativeTimeFormat('en', { numeric: 'auto' })
  for (const [unit, ms] of units) {
    if (abs >= ms) return rtf.format(Math.round(diffMs / ms), unit)
  }
  return 'just now'
}

export type DeadlineState = 'unknown' | 'closed' | 'closing-soon' | 'open'

export function deadlineState(deadline: string | null, now: Date = new Date()): DeadlineState {
  const d = parse(deadline)
  if (!d) return 'unknown'
  const ms = d.getTime() - now.getTime()
  if (ms < 0) return 'closed'
  if (ms < 3 * 86_400_000) return 'closing-soon'
  return 'open'
}

/** Start of a calendar day in IST as an ISO instant. Input: YYYY-MM-DD. */
export function istDayStart(day: string): string {
  return `${day}T00:00:00+05:30`
}

/** Exclusive end (start of the next day) in IST. */
export function istDayEnd(day: string): string {
  const [y, m, d] = day.split('-').map(Number)
  const next = new Date(Date.UTC(y ?? 1970, (m ?? 1) - 1, (d ?? 1) + 1))
  return `${next.toISOString().slice(0, 10)}T00:00:00+05:30`
}

export const STALE_AFTER_HOURS = 36

export function isStale(lastSuccess: string | null, now: Date = new Date()): boolean {
  const d = parse(lastSuccess)
  if (!d) return true
  return now.getTime() - d.getTime() > STALE_AFTER_HOURS * 3_600_000
}

export function formatNumber(n: number | null | undefined): string {
  return typeof n === 'number' ? new Intl.NumberFormat('en-IN').format(n) : '—'
}

const FIELD_LABELS: Record<string, string> = {
  bid_number: 'Bid number',
  title: 'Title',
  organisation: 'Organisation',
  ministry: 'Ministry',
  department: 'Department',
  category: 'Category',
  listing_type: 'Listing type',
  quantity: 'Quantity',
  published_at: 'Bid start',
  deadline: 'Deadline',
  url: 'Source link',
}

export function fieldLabel(field: string): string {
  return FIELD_LABELS[field] ?? field
}

const DATE_FIELDS = new Set(['deadline', 'published_at'])

export function formatFieldValue(field: string, value: string | null): string | null {
  if (value === null) return null
  return DATE_FIELDS.has(field) ? (formatDateTime(value) ?? value) : value
}

/** Only https links to the official GeM domains are rendered as links. */
export function isSafeSourceUrl(url: string | null): url is string {
  if (!url) return false
  try {
    const u = new URL(url)
    return u.protocol === 'https:' && (u.hostname === 'gem.gov.in' || u.hostname.endsWith('.gem.gov.in'))
  } catch {
    return false
  }
}
