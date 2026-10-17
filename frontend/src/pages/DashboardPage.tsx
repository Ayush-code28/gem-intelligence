import { Link } from 'react-router'
import { FreshnessPanel } from '../components/Freshness'
import { PageHeader } from '../components/Layout'
import { ListingList } from '../components/ListingList'
import { ChangeList } from './ChangesPage'
import { SyntheticNotice } from '../components/OriginBadge'
import { EmptyState, ErrorState, NotConfiguredNotice, SkeletonRows } from '../components/States'
import { useApi, useRequiredApi } from '../lib/api'
import { formatNumber } from '../lib/format'
import { useAsync } from '../lib/useAsync'

function StatCard({ label, value, hint }: { label: string; value: string; hint: string }) {
  return (
    <div className="card p-4">
      <p className="eyebrow">{label}</p>
      <p className="mt-2 text-3xl font-semibold tabular-nums text-ink">{value}</p>
      <p className="mt-1 text-xs text-slate-500">{hint}</p>
    </div>
  )
}

export function DashboardPage() {
  const api = useApi()
  if (!api) {
    return (
      <>
        <PageHeader title="Dashboard" />
        <NotConfiguredNotice />
      </>
    )
  }
  return <ConnectedDashboard />
}

function ConnectedDashboard() {
  const api = useRequiredApi()
  const stats = useAsync(() => api.getStats(), 'stats')
  const status = useAsync(() => api.getCollectionStatus(), 'status')
  const recent = useAsync(() => api.listListings({ sort: 'newest', page: 1, pageSize: 8 }), 'recent')
  const changes = useAsync(() => api.listChanges(1, 8), 'changes')

  return (
    <>
      <PageHeader
        title="Dashboard"
        description="Publicly available GeM listings collected once a day. Figures are calculated from the stored records."
      />

      {stats.status === 'success' && <SyntheticNotice count={stats.data.synthetic_listings} />}

      <section aria-labelledby="freshness-h" className="card mb-6 p-4">
        <h2 id="freshness-h" className="eyebrow mb-2">
          Data freshness
        </h2>
        {status.status === 'loading' && <SkeletonRows rows={1} />}
        {status.status === 'error' && <ErrorState error={status.error} onRetry={status.reload} />}
        {status.status === 'success' && <FreshnessPanel status={status.data} />}
      </section>

      <section aria-label="Statistics" className="mb-8">
        {stats.status === 'loading' && <SkeletonRows rows={2} />}
        {stats.status === 'error' && <ErrorState error={stats.error} onRetry={stats.reload} />}
        {stats.status === 'success' && (
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
            <StatCard label="Total listings" value={formatNumber(stats.data.total_listings)} hint="All stored records" />
            <StatCard label="New · 24 h" value={formatNumber(stats.data.new_last_24h)} hint="First discovered in the last day" />
            <StatCard label="New · 7 days" value={formatNumber(stats.data.new_last_7d)} hint="First discovered this week" />
            <StatCard
              label="Deadlines · 7 days"
              value={formatNumber(stats.data.upcoming_deadlines)}
              hint="Closing within the next week"
            />
            <StatCard label="Changes · 7 days" value={formatNumber(stats.data.changes_last_7d)} hint="Field updates detected" />
            <p className="col-span-2 text-xs text-slate-600 lg:col-span-5">
              By origin: <strong>{formatNumber(stats.data.live_listings)}</strong> live-collected ·{' '}
              <strong>{formatNumber(stats.data.imported_listings)}</strong> imported ·{' '}
              <strong>{formatNumber(stats.data.synthetic_listings)}</strong> synthetic demo
            </p>
          </div>
        )}
      </section>

      <div className="grid gap-6 lg:grid-cols-5">
        <section aria-labelledby="recent-h" className="card lg:col-span-3">
          <div className="flex items-center justify-between border-b border-rule px-4 py-3">
            <h2 id="recent-h" className="font-semibold">
              Recently discovered
            </h2>
            <Link to="/listings" className="text-sm font-medium text-navy-700 hover:underline">
              All listings →
            </Link>
          </div>
          {recent.status === 'loading' && <SkeletonRows />}
          {recent.status === 'error' && <ErrorState error={recent.error} onRetry={recent.reload} />}
          {recent.status === 'success' &&
            (recent.data.rows.length ? (
              <ListingList listings={recent.data.rows} compact />
            ) : (
              <EmptyState title="No listings collected yet">
                Listings appear here after the first successful collection run.
              </EmptyState>
            ))}
        </section>

        <section aria-labelledby="changes-h" className="card lg:col-span-2">
          <div className="flex items-center justify-between border-b border-rule px-4 py-3">
            <h2 id="changes-h" className="font-semibold">
              Recently detected changes
            </h2>
            <Link to="/changes" className="text-sm font-medium text-navy-700 hover:underline">
              All changes →
            </Link>
          </div>
          {changes.status === 'loading' && <SkeletonRows />}
          {changes.status === 'error' && <ErrorState error={changes.error} onRetry={changes.reload} />}
          {changes.status === 'success' &&
            (changes.data.rows.length ? (
              <ChangeList changes={changes.data.rows} compact />
            ) : (
              <EmptyState title="No changes detected yet">
                Changes are recorded when a later collection observes different values for a listing.
              </EmptyState>
            ))}
        </section>
      </div>
    </>
  )
}
