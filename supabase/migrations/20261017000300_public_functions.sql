-- Narrow, read-only functions for the public dashboard.
-- They are SECURITY DEFINER so the public can see aggregates and run freshness
-- without being granted access to scrape_runs or to non-display columns.

-- Dashboard statistics computed from real rows (never hard-coded).
create or replace function public.dashboard_stats()
returns table (
    total_listings      bigint,
    new_last_24h        bigint,
    new_last_7d         bigint,
    upcoming_deadlines  bigint,
    changes_last_7d     bigint,
    generated_at        timestamptz
)
language sql
stable
security definer
set search_path = ''
as $$
    select
        (select count(*) from public.listings),
        (select count(*) from public.listings where first_seen_at >= now() - interval '24 hours'),
        (select count(*) from public.listings where first_seen_at >= now() - interval '7 days'),
        (select count(*) from public.listings where deadline >= now() and deadline < now() + interval '7 days'),
        (select count(*) from public.listing_history where observed_at >= now() - interval '7 days'),
        now();
$$;

-- Data freshness: when did a collection last succeed (fully or partially)?
-- Exposes timestamps and status only — no errors, counts or source internals.
create or replace function public.collection_status()
returns table (
    last_success_at      timestamptz,
    last_full_success_at timestamptz,
    last_run_at          timestamptz,
    last_run_status      text,
    sources_succeeded    text[],
    sources_failed       text[]
)
language sql
stable
security definer
set search_path = ''
as $$
    with last_run as (
        select r.started_at, r.status, r.source_results
        from public.scrape_runs r
        where r.status <> 'running'
        order by r.started_at desc
        limit 1
    )
    select
        (select max(finished_at) from public.scrape_runs where status in ('success', 'partial')),
        (select max(finished_at) from public.scrape_runs where status = 'success'),
        (select started_at from last_run),
        (select status from last_run),
        coalesce((select array_agg(key order by key) from last_run, jsonb_each(last_run.source_results)
                  where value ->> 'status' = 'success'), '{}'),
        coalesce((select array_agg(key order by key) from last_run, jsonb_each(last_run.source_results)
                  where value ->> 'status' = 'failed'), '{}');
$$;

-- Distinct categories for the listings filter.
create or replace function public.listing_categories()
returns table (category text, listing_count bigint)
language sql
stable
security definer
set search_path = ''
as $$
    select l.category, count(*)
    from public.listings l
    where l.category is not null
    group by l.category
    order by l.category;
$$;

revoke execute on function public.dashboard_stats(), public.collection_status(), public.listing_categories()
    from public, anon, authenticated;
grant execute on function public.dashboard_stats(), public.collection_status(), public.listing_categories()
    to anon, authenticated;
