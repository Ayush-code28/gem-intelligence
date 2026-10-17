import { vi } from 'vitest'
import type { CollectionStatus, DashboardStats, DataApi, Listing, ListingChange, ScrapeRun } from '../lib/types'

// Synthetic test data only — never shown in the application.
export function makeListing(n: number, overrides: Partial<Listing> = {}): Listing {
  return {
    id: `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`,
    source_name: 'test_source',
    source_id: String(n),
    bid_number: `GEM/TEST/B/${String(n).padStart(6, '0')}`,
    title: `Synthetic listing ${n}`,
    organisation: 'Department of Test Fixtures',
    ministry: null,
    department: 'Department of Test Fixtures',
    category: 'Products',
    listing_type: 'Bid',
    quantity: 3,
    published_at: '2030-01-10T04:30:00+00:00',
    deadline: '2030-01-20T11:30:00+00:00',
    url: `https://bidplus.gem.gov.in/showbidDocument/${n}`,
    data_origin: 'live',
    first_seen_at: '2030-01-10T01:00:00+00:00',
    last_seen_at: '2030-01-10T01:00:00+00:00',
    last_checked_at: '2030-01-10T01:00:00+00:00',
    created_at: '2030-01-10T01:00:00+00:00',
    updated_at: '2030-01-10T01:00:00+00:00',
    ...overrides,
  }
}

export const STATS: DashboardStats = {
  total_listings: 1234,
  new_last_24h: 56,
  new_last_7d: 300,
  upcoming_deadlines: 78,
  changes_last_7d: 9,
  live_listings: 1000,
  imported_listings: 200,
  synthetic_listings: 0,
  generated_at: '2030-01-10T02:00:00+00:00',
}

export function freshStatus(overrides: Partial<CollectionStatus> = {}): CollectionStatus {
  const recent = new Date(Date.now() - 3 * 3_600_000).toISOString()
  return {
    last_success_at: recent,
    last_live_success_at: recent,
    last_import_at: null,
    last_run_at: recent,
    last_run_status: 'success',
    sources_succeeded: ['test_source'],
    sources_failed: [],
    ...overrides,
  }
}

export const CHANGE: ListingChange = {
  id: 1,
  listing_id: makeListing(1).id,
  field_name: 'deadline',
  old_value: '2030-01-20T11:30:00+00:00',
  new_value: '2030-01-25T11:30:00+00:00',
  observed_at: '2030-01-11T01:00:00+00:00',
  listing: { id: makeListing(1).id, title: 'Synthetic listing 1', bid_number: 'GEM/TEST/B/000001' },
}

export const RUN: ScrapeRun = {
  id: 'run-1',
  started_at: '2030-01-10T01:00:00+00:00',
  finished_at: '2030-01-10T01:10:00+00:00',
  status: 'partial',
  trigger: 'schedule',
  records_found: 10,
  records_inserted: 8,
  records_updated: 1,
  records_unchanged: 0,
  records_rejected: 1,
  error_summary: 'b_source: fetch: SourceAccessBlocked',
  source_results: {
    a_source: { status: 'success' },
    b_source: { status: 'failed', error: 'fetch: SourceAccessBlocked' },
  },
}

export function fakeApi(overrides: Partial<DataApi> = {}): DataApi {
  return {
    getStats: vi.fn(async () => STATS),
    getCollectionStatus: vi.fn(async () => freshStatus()),
    listListings: vi.fn(async () => ({ rows: [makeListing(1), makeListing(2)], total: 2 })),
    getListing: vi.fn(async (id: string) => (id === makeListing(1).id ? makeListing(1) : null)),
    getListingHistory: vi.fn(async () => [CHANGE]),
    listChanges: vi.fn(async () => ({ rows: [CHANGE], total: 1 })),
    listCategories: vi.fn(async () => [{ category: 'Products', listing_count: 2 }]),
    getCurrentUser: vi.fn(async () => null),
    signIn: vi.fn(async () => undefined),
    signOut: vi.fn(async () => undefined),
    isAdmin: vi.fn(async () => false),
    listRuns: vi.fn(async () => [RUN]),
    ...overrides,
  }
}

/** A promise that never settles — keeps a component in its loading state. */
export const pending = <T,>(): Promise<T> => new Promise<T>(() => undefined)
