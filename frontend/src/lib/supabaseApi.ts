import { createClient, type SupabaseClient } from '@supabase/supabase-js'
import { istDayEnd, istDayStart } from './format'
import type {
  CategoryCount,
  CollectionStatus,
  DashboardStats,
  DataApi,
  Listing,
  ListingChange,
  ListingQuery,
  Page,
  ScrapeRun,
} from './types'

/** Columns granted to the public roles — `select *` would be refused by column privileges. */
export const LISTING_COLUMNS =
  'id,source_name,source_id,bid_number,title,organisation,ministry,department,category,listing_type,' +
  'quantity,published_at,deadline,url,data_origin,first_seen_at,last_seen_at,last_checked_at,created_at,updated_at'

const CHANGE_COLUMNS = 'id,listing_id,field_name,old_value,new_value,observed_at,listing:listings(id,title,bid_number)'

const RUN_COLUMNS =
  'id,started_at,finished_at,status,trigger,records_found,records_inserted,records_updated,' +
  'records_unchanged,records_rejected,error_summary,source_results'

/** Strip characters with meaning in PostgREST filter syntax so user input stays a plain substring. */
export function sanitizeSearch(input: string): string {
  return input
    .replace(/[,()*%\\:"'`]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, 100)
}

function fail(error: { message: string } | null): void {
  if (error) throw new Error(error.message)
}

export function createSupabaseApi(url: string, anonKey: string): DataApi {
  const client: SupabaseClient = createClient(url, anonKey, {
    auth: { persistSession: true, autoRefreshToken: true },
  })

  return {
    async getStats() {
      const { data, error } = await client.rpc('dashboard_stats').single<DashboardStats>()
      fail(error)
      return data as DashboardStats
    },

    async getCollectionStatus() {
      const { data, error } = await client.rpc('collection_status').single<CollectionStatus>()
      fail(error)
      return data as CollectionStatus
    },

    async listListings(q: ListingQuery): Promise<Page<Listing>> {
      let query = client.from('listings').select(LISTING_COLUMNS, { count: 'exact' })
      const term = q.search ? sanitizeSearch(q.search) : ''
      if (term) query = query.or(`title.ilike.*${term}*,organisation.ilike.*${term}*,bid_number.ilike.*${term}*`)
      if (q.category) query = query.eq('category', q.category)
      if (q.origin) query = query.eq('data_origin', q.origin)
      if (q.deadlineFrom) query = query.gte('deadline', istDayStart(q.deadlineFrom))
      if (q.deadlineTo) query = query.lt('deadline', istDayEnd(q.deadlineTo))
      if (q.sort === 'deadline') {
        query = query.order('deadline', { ascending: true, nullsFirst: false })
      } else {
        query = query.order('first_seen_at', { ascending: q.sort === 'oldest' })
      }
      query = query.order('id', { ascending: true })
      const from = (q.page - 1) * q.pageSize
      const { data, error, count } = await query.range(from, from + q.pageSize - 1)
      fail(error)
      return { rows: (data ?? []) as unknown as Listing[], total: count ?? 0 }
    },

    async getListing(id) {
      const { data, error } = await client.from('listings').select(LISTING_COLUMNS).eq('id', id).maybeSingle()
      fail(error)
      return (data as unknown as Listing | null) ?? null
    },

    async getListingHistory(id) {
      const { data, error } = await client
        .from('listing_history')
        .select(CHANGE_COLUMNS)
        .eq('listing_id', id)
        .order('observed_at', { ascending: false })
        .limit(200)
      fail(error)
      return (data ?? []) as unknown as ListingChange[]
    },

    async listChanges(page, pageSize) {
      const from = (page - 1) * pageSize
      const { data, error, count } = await client
        .from('listing_history')
        .select(CHANGE_COLUMNS, { count: 'exact' })
        .order('observed_at', { ascending: false })
        .order('id', { ascending: false })
        .range(from, from + pageSize - 1)
      fail(error)
      return { rows: (data ?? []) as unknown as ListingChange[], total: count ?? 0 }
    },

    async listCategories() {
      const { data, error } = await client.rpc('listing_categories')
      fail(error)
      return (data ?? []) as CategoryCount[]
    },

    async getCurrentUser() {
      const { data } = await client.auth.getSession()
      return data.session ? { email: data.session.user.email ?? null } : null
    },

    async signIn(email, password) {
      const { error } = await client.auth.signInWithPassword({ email, password })
      fail(error)
    },

    async signOut() {
      const { error } = await client.auth.signOut()
      fail(error)
    },

    async isAdmin() {
      const { data, error } = await client.rpc('is_admin')
      fail(error)
      return data === true
    },

    async listRuns(limit) {
      // RLS returns rows only to users listed in public.admins.
      const { data, error } = await client
        .from('scrape_runs')
        .select(RUN_COLUMNS)
        .order('started_at', { ascending: false })
        .limit(limit)
      fail(error)
      return (data ?? []) as unknown as ScrapeRun[]
    },
  }
}

/** Returns null when the public Supabase settings are absent — the UI then shows an explicit
 *  "not connected" state instead of any sample data. */
export function createApiFromEnv(env: ImportMetaEnv = import.meta.env): DataApi | null {
  const url = env.VITE_SUPABASE_URL?.trim()
  const key = env.VITE_SUPABASE_ANON_KEY?.trim()
  if (!url || !key || url.includes('your-project-ref')) return null
  return createSupabaseApi(url, key)
}
