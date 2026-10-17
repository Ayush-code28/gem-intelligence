import { useApi } from '../lib/api'
import { formatDateTime, formatRelative, isStale, STALE_AFTER_HOURS } from '../lib/format'
import type { CollectionStatus } from '../lib/types'
import { useAsync } from '../lib/useAsync'

function Pill({ tone, children }: { tone: 'ok' | 'warn' | 'neutral'; children: string }) {
  const styles = {
    ok: ['bg-emerald-100 text-emerald-900', 'bg-emerald-600'],
    warn: ['bg-amber-100 text-amber-900', 'bg-amber-600'],
    neutral: ['bg-slate-200 text-slate-800', 'bg-slate-500'],
  }[tone]
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-semibold ${styles[0]}`}>
      <span className={`size-1.5 rounded-full ${styles[1]}`} aria-hidden />
      {children}
    </span>
  )
}

/** Freshness is judged on *live* collection only; imports are reported separately. */
export function FreshnessPanel({ status }: { status: CollectionStatus }) {
  const live = status.last_live_success_at
  const stale = live !== null && isStale(live)
  const lastRunProblem = status.last_run_status === 'partial' || status.last_run_status === 'failed'
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
        {live === null ? (
          <Pill tone="neutral">No live collection</Pill>
        ) : stale ? (
          <Pill tone="warn">Live data may be out of date</Pill>
        ) : (
          <Pill tone="ok">Live data is current</Pill>
        )}
        <span className="text-slate-700">
          Last successful live collection:{' '}
          <strong>{live ? `${formatDateTime(live)} (${formatRelative(live)})` : 'none yet'}</strong>
        </span>
        {status.last_import_at && (
          <span className="text-slate-700">
            · Last file import: <strong>{formatDateTime(status.last_import_at)}</strong>
          </span>
        )}
      </div>
      {live === null && (
        <p role="alert" className="text-sm text-slate-700">
          No live GeM collection has succeeded. Any records shown were imported from files by the operator or are synthetic
          demonstration data — check each record’s origin label.
        </p>
      )}
      {stale && (
        <p role="alert" className="text-sm text-amber-900">
          No successful live collection in the last {STALE_AFTER_HOURS} hours. Listings may have changed on GeM — always
          verify on the official portal.
        </p>
      )}
      {lastRunProblem && (
        <p role="alert" className="text-sm text-amber-900">
          The most recent run ({formatDateTime(status.last_run_at)}) was{' '}
          {status.last_run_status === 'partial' ? 'only partially successful' : 'unsuccessful'}
          {status.sources_failed.length > 0 && <> — sources not updated: {status.sources_failed.join(', ')}</>}.
        </p>
      )}
    </div>
  )
}

/** Compact banner shown at the top of data pages. */
export function FreshnessBanner() {
  const api = useApi()
  const state = useAsync(() => (api ? api.getCollectionStatus() : Promise.reject(new Error('not configured'))), 'status')
  if (!api || state.status !== 'success') return null
  return (
    <div className="card mb-6 px-4 py-3">
      <FreshnessPanel status={state.data} />
    </div>
  )
}
