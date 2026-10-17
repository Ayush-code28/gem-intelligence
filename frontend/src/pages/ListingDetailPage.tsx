import type { ReactNode } from 'react'
import { Link, useParams } from 'react-router'
import { DeadlineBadge, DeadlineText } from '../components/DeadlineBadge'
import { FreshnessBanner } from '../components/Freshness'
import { OriginBadge } from '../components/OriginBadge'
import { SourceLink } from '../components/SourceLink'
import { EmptyState, ErrorState, Field, NotConfiguredNotice, SkeletonRows } from '../components/States'
import { useApi, useRequiredApi } from '../lib/api'
import { formatDateTime, isStale } from '../lib/format'
import type { Listing } from '../lib/types'
import { useAsync } from '../lib/useAsync'
import { ChangeList } from './ChangesPage'

function ProvenanceNotice({ listing }: { listing: Listing }) {
  if (listing.data_origin === 'synthetic') {
    return (
      <div role="note" className="mb-4 rounded-lg border-2 border-fuchsia-300 bg-fuchsia-50 px-4 py-3 text-sm text-fuchsia-950">
        <strong>Synthetic demonstration record.</strong> This listing was invented for testing. It is not a real GeM listing
        and has no official source.
      </div>
    )
  }
  if (listing.data_origin === 'imported') {
    return (
      <div role="note" className="mb-4 rounded-lg border border-sky-200 bg-sky-50 px-4 py-3 text-sm text-sky-950">
        <strong>Imported record.</strong> Loaded from a file by the site operator; this site has not collected or verified it
        against GeM. Check the official portal before relying on it.
      </div>
    )
  }
  if (isStale(listing.last_seen_at)) {
    return (
      <div role="note" className="mb-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-950">
        <strong>Not re-observed recently.</strong> The collector last saw this listing at the source on{' '}
        {formatDateTime(listing.last_seen_at)}. It may have closed, changed or been withdrawn.
      </div>
    )
  }
  return null
}

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid gap-1 py-3 sm:grid-cols-3 sm:gap-4">
      <dt className="text-sm font-medium text-slate-500">{label}</dt>
      <dd className="text-sm text-ink sm:col-span-2">{children}</dd>
    </div>
  )
}

export function ListingDetailPage() {
  const api = useApi()
  const { id = '' } = useParams()
  if (!api) return <NotConfiguredNotice />
  if (!UUID.test(id)) return <EmptyState title="Listing not found">The link may be incorrect.</EmptyState>
  return <ConnectedDetail id={id} />
}

function ConnectedDetail({ id }: { id: string }) {
  const api = useRequiredApi()
  const listing = useAsync(() => api.getListing(id), `listing:${id}`)
  const history = useAsync(() => api.getListingHistory(id), `history:${id}`)

  if (listing.status === 'loading') return <SkeletonRows rows={6} />
  if (listing.status === 'error') return <ErrorState error={listing.error} onRetry={listing.reload} />
  const l = listing.data
  if (!l) {
    return (
      <EmptyState title="Listing not found">
        <Link to="/listings" className="text-navy-700 underline">
          Back to listings
        </Link>
      </EmptyState>
    )
  }

  return (
    <>
      <nav aria-label="Breadcrumb" className="mb-4 text-sm">
        <Link to="/listings" className="text-navy-700 hover:underline">
          ← Listings
        </Link>
      </nav>
      <FreshnessBanner />
      <ProvenanceNotice listing={l} />
      <article className="card">
        <header className="border-b border-rule p-5">
          <p className="font-mono text-xs text-slate-500">
            <Field value={l.bid_number} />
          </p>
          <h1 className="mt-1 text-xl font-semibold leading-snug text-ink sm:text-2xl">{l.title}</h1>
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <OriginBadge origin={l.data_origin} />
            <DeadlineBadge deadline={l.deadline} />
            <SourceLink url={l.url} label="Verify on the official GeM portal" />
          </div>
        </header>
        <dl className="divide-y divide-rule px-5">
          <Row label="Buyer organisation">
            <Field value={l.organisation} />
          </Row>
          <Row label="Ministry">
            <Field value={l.ministry} />
          </Row>
          <Row label="Department">
            <Field value={l.department} />
          </Row>
          <Row label="Category">
            <Field value={l.category} />
          </Row>
          <Row label="Listing type">
            <Field value={l.listing_type} />
          </Row>
          <Row label="Quantity">
            <Field value={l.quantity} />
          </Row>
          <Row label="Bid start">
            <Field value={formatDateTime(l.published_at)} />
          </Row>
          <Row label="Submission deadline">
            <DeadlineText deadline={l.deadline} />
          </Row>
          <Row label="Source identifier">
            <span className="font-mono">
              <Field value={l.source_id} />
            </span>
          </Row>
          <Row label="Collected from">
            <span className="font-mono">{l.source_name}</span>
          </Row>
          <Row label="Data origin">
            <OriginBadge origin={l.data_origin} />
          </Row>
          <Row label="First discovered">{formatDateTime(l.first_seen_at)}</Row>
          <Row label={l.data_origin === 'live' ? 'Last observed at source' : 'Last imported'}>{formatDateTime(l.last_seen_at)}</Row>
          <Row label="Last checked">{formatDateTime(l.last_checked_at)}</Row>
          <Row label="Record last changed">{formatDateTime(l.updated_at)}</Row>
        </dl>
        <p className="border-t border-rule bg-navy-50 px-5 py-3 text-xs text-slate-600">
          This is a copy made by an independent collector and may be outdated. The official GeM listing is authoritative.
        </p>
      </article>

      <section className="card mt-6" aria-labelledby="history-h">
        <h2 id="history-h" className="border-b border-rule px-4 py-3 font-semibold">
          Change history
        </h2>
        {history.status === 'loading' && <SkeletonRows rows={2} />}
        {history.status === 'error' && <ErrorState error={history.error} onRetry={history.reload} />}
        {history.status === 'success' &&
          (history.data.length ? (
            <ChangeList changes={history.data} hideListing />
          ) : (
            <EmptyState title="No changes recorded">The collected fields have not changed since this listing was first discovered.</EmptyState>
          ))}
      </section>
    </>
  )
}
