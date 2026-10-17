import { Link, useSearchParams } from 'react-router'
import { FreshnessBanner } from '../components/Freshness'
import { PageHeader } from '../components/Layout'
import { ListingList } from '../components/ListingList'
import { Pagination } from '../components/Pagination'
import { EmptyState, ErrorState, NotConfiguredNotice, SkeletonRows } from '../components/States'
import { useApi, useRequiredApi } from '../lib/api'
import { fieldLabel, formatDateTime, formatFieldValue } from '../lib/format'
import type { Listing, ListingChange } from '../lib/types'
import { useAsync } from '../lib/useAsync'

const PAGE_SIZE = 25

type ChangesResult =
  | { kind: 'updates'; rows: ListingChange[]; total: number }
  | { kind: 'new'; rows: Listing[]; total: number }

function Value({ field, value }: { field: string; value: string | null }) {
  const text = formatFieldValue(field, value)
  return text === null ? <span className="italic text-slate-400">empty</span> : <span className="break-words">{text}</span>
}

export function ChangeList({ changes, compact = false, hideListing = false }: { changes: ListingChange[]; compact?: boolean; hideListing?: boolean }) {
  return (
    <ul className="divide-y divide-rule">
      {changes.map((c) => (
        <li key={c.id} className="px-4 py-3 text-sm">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <span className="rounded bg-navy-50 px-2 py-0.5 text-xs font-semibold text-navy-800">{fieldLabel(c.field_name)} changed</span>
            <time dateTime={c.observed_at} className="text-xs text-slate-500">
              {formatDateTime(c.observed_at)}
            </time>
          </div>
          {!hideListing && (
            <Link to={`/listings/${c.listing_id}`} className={`mt-1 block font-medium text-navy-800 hover:underline ${compact ? 'line-clamp-1' : ''}`}>
              {c.listing?.title ?? 'Listing'}
            </Link>
          )}
          <p className="mt-1 text-slate-700">
            <Value field={c.field_name} value={c.old_value} /> <span aria-label="changed to">→</span>{' '}
            <strong className="font-medium text-ink">
              <Value field={c.field_name} value={c.new_value} />
            </strong>
          </p>
        </li>
      ))}
    </ul>
  )
}

export function ChangesPage() {
  const api = useApi()
  return (
    <>
      <PageHeader title="Changes" description="Newly discovered listings and updates detected between daily collections, such as deadline extensions." />
      {api ? <ConnectedChanges /> : <NotConfiguredNotice />}
    </>
  )
}

function ConnectedChanges() {
  const api = useRequiredApi()
  const [params, setParams] = useSearchParams()
  const tab = params.get('view') === 'new' ? 'new' : 'updates'
  const page = Math.max(1, Number.parseInt(params.get('page') ?? '1', 10) || 1)
  const result = useAsync<ChangesResult>(
    async () =>
      tab === 'new'
        ? { kind: 'new', ...(await api.listListings({ sort: 'newest', page, pageSize: PAGE_SIZE })) }
        : { kind: 'updates', ...(await api.listChanges(page, PAGE_SIZE)) },
    `${tab}:${page}`,
  )

  const go = (next: Record<string, string>) => setParams(new URLSearchParams(next))

  return (
    <>
      <FreshnessBanner />
      <div role="tablist" aria-label="Change type" className="mb-4 inline-flex rounded-md border border-rule bg-white p-1">
        {(['updates', 'new'] as const).map((t) => (
          <button
            key={t}
            role="tab"
            type="button"
            aria-selected={tab === t}
            onClick={() => go(t === 'new' ? { view: 'new' } : {})}
            className={`rounded px-4 py-1.5 text-sm font-medium ${tab === t ? 'bg-navy-800 text-white' : 'text-slate-700 hover:bg-slate-100'}`}
          >
            {t === 'updates' ? 'Updated listings' : 'Newly discovered'}
          </button>
        ))}
      </div>
      <section className="card" aria-live="polite">
        {result.status === 'loading' && <SkeletonRows rows={8} />}
        {result.status === 'error' && <ErrorState error={result.error} onRetry={result.reload} />}
        {result.status === 'success' &&
          (result.data.rows.length === 0 ? (
            <EmptyState title={tab === 'new' ? 'No listings discovered yet' : 'No updates detected yet'}>
              {tab === 'new' ? 'New listings appear after a successful collection.' : 'Updates are recorded when a later collection sees different values.'}
            </EmptyState>
          ) : (
            <>
              {result.data.kind === 'new' ? <ListingList listings={result.data.rows} /> : <ChangeList changes={result.data.rows} />}
              <Pagination
                page={page}
                pageSize={PAGE_SIZE}
                total={result.data.total}
                onPage={(p) => go({ ...(tab === 'new' ? { view: 'new' } : {}), page: String(p) })}
              />
            </>
          ))}
      </section>
    </>
  )
}
