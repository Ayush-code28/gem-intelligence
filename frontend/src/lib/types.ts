export type DataOrigin = 'live' | 'imported' | 'synthetic'

export interface Listing {
  id: string
  source_name: string
  source_id: string | null
  bid_number: string | null
  title: string
  organisation: string | null
  ministry: string | null
  department: string | null
  category: string | null
  listing_type: string | null
  quantity: number | string | null
  published_at: string | null
  deadline: string | null
  url: string | null
  data_origin: DataOrigin
  first_seen_at: string
  last_seen_at: string
  last_checked_at: string
  created_at: string
  updated_at: string
}

export interface ListingChange {
  id: number
  listing_id: string
  field_name: string
  old_value: string | null
  new_value: string | null
  observed_at: string
  listing: Pick<Listing, 'id' | 'title' | 'bid_number'> | null
}

export interface DashboardStats {
  total_listings: number
  new_last_24h: number
  new_last_7d: number
  upcoming_deadlines: number
  changes_last_7d: number
  live_listings: number
  imported_listings: number
  synthetic_listings: number
  generated_at: string
}

export interface CollectionStatus {
  /** Any successful run, including imports. */
  last_success_at: string | null
  /** Last run in which a live source (not an import) succeeded. */
  last_live_success_at: string | null
  last_import_at: string | null
  last_run_at: string | null
  last_run_status: RunStatus | null
  sources_succeeded: string[]
  sources_failed: string[]
}

export type RunStatus = 'running' | 'success' | 'partial' | 'failed' | 'skipped'

export interface SourceRunResult {
  status: string
  origin?: string
  found?: number
  inserted?: number
  updated?: number
  unchanged?: number
  rejected?: number
  pages_fetched?: number
  duration_seconds?: number
  error?: string | null
  passes?: Record<string, string>
  rejection_samples?: string[]
}

export interface ScrapeRun {
  id: string
  started_at: string
  finished_at: string | null
  status: RunStatus
  trigger: string
  records_found: number
  records_inserted: number
  records_updated: number
  records_unchanged: number
  records_rejected: number
  error_summary: string | null
  source_results: Record<string, SourceRunResult>
}

export interface CategoryCount {
  category: string
  listing_count: number
}

export type ListingSort = 'newest' | 'oldest' | 'deadline'

export interface ListingQuery {
  search?: string
  category?: string
  origin?: DataOrigin
  /** Inclusive start date, YYYY-MM-DD, interpreted in IST. */
  deadlineFrom?: string
  /** Inclusive end date, YYYY-MM-DD, interpreted in IST. */
  deadlineTo?: string
  sort: ListingSort
  page: number
  pageSize: number
}

export interface Page<T> {
  rows: T[]
  total: number
}

export interface AdminUser {
  email: string | null
}

/** Everything the UI needs from the backend. Implemented over Supabase; faked in tests. */
export interface DataApi {
  getStats(): Promise<DashboardStats>
  getCollectionStatus(): Promise<CollectionStatus>
  listListings(query: ListingQuery): Promise<Page<Listing>>
  getListing(id: string): Promise<Listing | null>
  getListingHistory(id: string): Promise<ListingChange[]>
  listChanges(page: number, pageSize: number): Promise<Page<ListingChange>>
  listCategories(): Promise<CategoryCount[]>
  getCurrentUser(): Promise<AdminUser | null>
  signIn(email: string, password: string): Promise<void>
  signOut(): Promise<void>
  isAdmin(): Promise<boolean>
  listRuns(limit: number): Promise<ScrapeRun[]>
}
