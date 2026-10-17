-- Provenance: every listing records how it entered the database, so the UI can always
-- distinguish live-collected GeM data from operator imports and synthetic demo records.
--   live       collected by a live source adapter from the original publisher
--   imported   loaded by an operator from a CSV/JSON file (provenance is the operator's responsibility)
--   synthetic  invented demonstration/test data — never real listings

alter table public.listings
    add column data_origin text not null default 'live'
        check (data_origin in ('live', 'imported', 'synthetic'));

create index listings_data_origin_idx on public.listings (data_origin);

grant select (data_origin) on public.listings to anon, authenticated;

-- Statistics now include a per-origin breakdown.
drop function if exists public.dashboard_stats();
create function public.dashboard_stats()
returns table (
    total_listings      bigint,
    new_last_24h        bigint,
    new_last_7d         bigint,
    upcoming_deadlines  bigint,
    changes_last_7d     bigint,
    live_listings       bigint,
    imported_listings   bigint,
    synthetic_listings  bigint,
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
        (select count(*) from public.listings where data_origin = 'live'),
        (select count(*) from public.listings where data_origin = 'imported'),
        (select count(*) from public.listings where data_origin = 'synthetic'),
        now();
$$;

-- Freshness distinguishes live collection from imports. A source result counts as "live"
-- when its recorded origin is 'live' (results written before this migration had no origin
-- and were live adapters).
drop function if exists public.collection_status();
create function public.collection_status()
returns table (
    last_success_at       timestamptz,
    last_live_success_at  timestamptz,
    last_import_at        timestamptz,
    last_run_at           timestamptz,
    last_run_status       text,
    sources_succeeded     text[],
    sources_failed        text[]
)
language sql
stable
security definer
set search_path = ''
as $$
    with finished as (
        select r.started_at, r.finished_at, r.status, r.source_results
        from public.scrape_runs r
        where r.status <> 'running'
    ),
    results as (
        select f.finished_at, f.status as run_status, s.key as source, s.value ->> 'status' as status,
               coalesce(s.value ->> 'origin', 'live') as origin
        from finished f, jsonb_each(f.source_results) s
    ),
    last_run as (
        select * from finished order by started_at desc limit 1
    )
    select
        (select max(finished_at) from finished where status in ('success', 'partial')),
        (select max(finished_at) from results where status = 'success' and origin = 'live'
            and run_status in ('success', 'partial')),
        (select max(finished_at) from results where status = 'success' and origin <> 'live'),
        (select started_at from last_run),
        (select status from last_run),
        coalesce((select array_agg(key order by key) from last_run, jsonb_each(last_run.source_results)
                  where value ->> 'status' = 'success'), '{}'),
        coalesce((select array_agg(key order by key) from last_run, jsonb_each(last_run.source_results)
                  where value ->> 'status' = 'failed'), '{}');
$$;

revoke execute on function public.dashboard_stats(), public.collection_status() from public, anon, authenticated;
grant execute on function public.dashboard_stats(), public.collection_status() to anon, authenticated;
