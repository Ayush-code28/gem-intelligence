import { deadlineState, formatDateTime } from '../lib/format'

const STYLES = {
  unknown: 'bg-slate-100 text-slate-500',
  closed: 'bg-slate-200 text-slate-600',
  'closing-soon': 'bg-saffron-100 text-amber-900',
  open: 'bg-emerald-50 text-emerald-800',
} as const

const LABELS = { unknown: 'Deadline not available', closed: 'Closed', 'closing-soon': 'Closing soon', open: 'Open' }

export function DeadlineBadge({ deadline, now }: { deadline: string | null; now?: Date }) {
  const state = deadlineState(deadline, now)
  return (
    <span className={`inline-flex rounded px-2 py-0.5 text-xs font-medium ${STYLES[state]}`}>{LABELS[state]}</span>
  )
}

export function DeadlineText({ deadline }: { deadline: string | null }) {
  const text = formatDateTime(deadline)
  return text ? <span>{text}</span> : <span className="italic text-slate-400">Not available</span>
}
