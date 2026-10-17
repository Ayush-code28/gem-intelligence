import { useState, type FormEvent } from 'react'
import { useSearchParams } from 'react-router'
import { FreshnessBanner } from '../components/Freshness'
import { PageHeader } from '../components/Layout'
import { ListingList } from '../components/ListingList'
import { ORIGIN_OPTIONS } from '../components/OriginBadge'
import { Pagination } from '../components/Pagination'
import { EmptyState, ErrorState, NotConfiguredNotice, SkeletonRows } from '../components/States'
import { useApi, useRequiredApi } from '../lib/api'
import type { DataOrigin, ListingQuery, ListingSort } from '../lib/types'
import { useAsync } from '../lib/useAsync'

export const PAGE_SIZE = 25
const SORTS: { value: ListingSort; label: string }[] = [
  { value: 'newest', label: 'Newest first' },
  { value: 'oldest', label: 'Oldest first' },
  { value: 'deadline', label: 'Deadline (soonest)' },
]
const DAY = /^\d{4}-\d{2}-\d{2}$/

export function parseQuery(params: URLSearchParams): ListingQuery {
  const sort = params.get('sort')
  const page = Number.parseInt(params.get('page') ?? '1', 10)
  const from = params.get('from') ?? ''
  const to = params.get('to') ?? ''
  const origin = params.get('origin')
  return {
    search: params.get('q')?.slice(0, 100) || undefined,
    category: params.get('category') || undefined,
    origin: ORIGIN_OPTIONS.some((o) => o.value === origin) ? (origin as DataOrigin) : undefined,
    deadlineFrom: DAY.test(from) ? from : undefined,
    deadlineTo: DAY.test(to) ? to : undefined,
    sort: SORTS.some((s) => s.value === sort) ? (sort as ListingSort) : 'newest',
    page: Number.isFinite(page) && page > 0 ? Math.min(page, 100_000) : 1,
    pageSize: PAGE_SIZE,
  }
}

export function ListingsPage() {
  const api = useApi()
  return (
    <>
      <PageHeader title="Listings" description="Search and filter collected GeM listings. Open any listing to verify it on the official portal." />
      {api ? <ConnectedListings /> : <NotConfiguredNotice />}
    </>
  )
}

function ConnectedListings() {
  const api = useRequiredApi()
  const [params, setParams] = useSearchParams()
  const query = parseQuery(params)
  const key = JSON.stringify(query)
  const result = useAsync(() => api.listListings(query), key)
  const categories = useAsync(() => api.listCategories(), 'categories')

  const update = (changes: Record<string, string | undefined>, resetPage = true) => {
    const next = new URLSearchParams(params)
    for (const [k, v] of Object.entries(changes)) {
      if (v) next.set(k, v)
      else next.delete(k)
    }
    if (resetPage) next.delete('page')
    setParams(next)
  }

  const rangeInvalid = query.deadlineFrom && query.deadlineTo && query.deadlineFrom > query.deadlineTo

  return (
    <>
      <FreshnessBanner />
      <div className="card mb-4 grid gap-3 p-4 sm:grid-cols-2 lg:grid-cols-7" role="search" aria-label="Filter listings">
        <SearchBox key={query.search ?? ''} initial={query.search ?? ''} onSearch={(q) => update({ q: q || undefined })} />
        <div>
          <label htmlFor="category" className="eyebrow mb-1 block">
            Category
          </label>
          <select id="category" className="input" value={query.category ?? ''} onChange={(e) => update({ category: e.target.value || undefined })}>
            <option value="">All categories</option>
            {categories.status === 'success' &&
              categories.data.map((c) => (
                <option key={c.category} value={c.category}>
                  {c.category} ({c.listing_count.toLocaleString('en-IN')})
                </option>
              ))}
          </select>
        </div>
        <div>
          <label htmlFor="origin" className="eyebrow mb-1 block">
            Data origin
          </label>
          <select id="origin" className="input" value={query.origin ?? ''} onChange={(e) => update({ origin: e.target.value || undefined })}>
            <option value="">All origins</option>
            {ORIGIN_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="from" className="eyebrow mb-1 block">
            Deadline from
          </label>
          <input id="from" type="date" className="input" value={query.deadlineFrom ?? ''} onChange={(e) => update({ from: e.target.value || undefined })} />
        </div>
        <div>
          <label htmlFor="to" className="eyebrow mb-1 block">
            Deadline to
          </label>
          <input id="to" type="date" className="input" value={query.deadlineTo ?? ''} onChange={(e) => update({ to: e.target.value || undefined })} />
        </div>
        <div>
          <label htmlFor="sort" className="eyebrow mb-1 block">
            Sort
          </label>
          <select id="sort" className="input" value={query.sort} onChange={(e) => update({ sort: e.target.value })}>
            {SORTS.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </select>
        </div>
        <p className="text-xs text-slate-500 sm:col-span-2 lg:col-span-7">
          Deadline dates are interpreted in India Standard Time. Listings without a known deadline are excluded when a deadline filter is set.
          {rangeInvalid && <span className="ml-1 font-medium text-red-700">“Deadline from” is after “Deadline to”.</span>}
        </p>
      </div>

      <section className="card" aria-live="polite" aria-busy={result.status === 'loading'}>
        {result.status === 'loading' && <SkeletonRows rows={8} />}
        {result.status === 'error' && <ErrorState error={result.error} onRetry={result.reload} />}
        {result.status === 'success' &&
          (result.data.rows.length ? (
            <>
              <ListingList listings={result.data.rows} />
              <Pagination
                page={query.page}
                pageSize={query.pageSize}
                total={result.data.total}
                onPage={(p) => update({ page: String(p) }, false)}
              />
            </>
          ) : (
            <EmptyState title="No listings match these filters">
              {params.toString() ? 'Try broadening the search or clearing a filter.' : 'No listings have been collected yet.'}
            </EmptyState>
          ))}
      </section>
    </>
  )
}

/** Keyed by the URL's search term so it resets when the URL changes (e.g. back navigation). */
function SearchBox({ initial, onSearch }: { initial: string; onSearch: (q: string) => void }) {
  const [value, setValue] = useState(initial)
  const submit = (e: FormEvent) => {
    e.preventDefault()
    onSearch(value.trim())
  }
  return (
    <form onSubmit={submit} className="sm:col-span-2">
      <label htmlFor="q" className="eyebrow mb-1 block">
        Search title, organisation or bid number
      </label>
      <div className="flex gap-2">
        <input id="q" type="search" className="input" value={value} onChange={(e) => setValue(e.target.value)} maxLength={100} />
        <button type="submit" className="btn-primary">
          Search
        </button>
      </div>
    </form>
  )
}
