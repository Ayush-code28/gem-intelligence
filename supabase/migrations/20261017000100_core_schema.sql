-- Core schema for the GeM Intelligence Dashboard.
-- Writes happen only from the collector (direct Postgres connection as the owner role);
-- public access is defined in the RLS migration that follows.

create extension if not exists pg_trgm with schema extensions;

-- ---------------------------------------------------------------------------
-- scrape_runs: one row per collection run
-- ---------------------------------------------------------------------------
create table public.scrape_runs (
    id                uuid primary key default gen_random_uuid(),
    started_at        timestamptz not null default now(),
    finished_at       timestamptz,
    status            text not null default 'running'
                      check (status in ('running', 'success', 'partial', 'failed', 'skipped')),
    trigger           text not null default 'manual',
    records_found     integer not null default 0 check (records_found >= 0),
    records_inserted  integer not null default 0 check (records_inserted >= 0),
    records_updated   integer not null default 0 check (records_updated >= 0),
    records_unchanged integer not null default 0 check (records_unchanged >= 0),
    records_rejected  integer not null default 0 check (records_rejected >= 0),
    error_summary     text,
    source_results    jsonb not null default '{}'::jsonb,
    created_at        timestamptz not null default now(),
    constraint scrape_runs_finished_after_start check (finished_at is null or finished_at >= started_at),
    constraint scrape_runs_finished_when_done check (status = 'running' or finished_at is not null)
);

create index scrape_runs_started_at_idx on public.scrape_runs (started_at desc);
create index scrape_runs_status_finished_idx on public.scrape_runs (status, finished_at desc);

-- ---------------------------------------------------------------------------
-- listings: latest known state of each listing
-- ---------------------------------------------------------------------------
create table public.listings (
    id               uuid primary key default gen_random_uuid(),
    source_name      text not null check (source_name ~ '^[a-z0-9_]+$'),
    source_id        text,
    -- 'id:<source_id>' when a stable id exists, otherwise 'url:<canonical url>'
    dedup_key        text not null check (dedup_key ~ '^(id|url):.+'),
    bid_number       text,
    title            text not null check (length(btrim(title)) > 0),
    organisation     text,
    ministry         text,
    department       text,
    category         text,
    listing_type     text,
    quantity         numeric,
    published_at     timestamptz,
    deadline         timestamptz,
    url              text check (url is null or url ~ '^https://'),
    first_seen_at    timestamptz not null default now(),
    last_seen_at     timestamptz not null default now(),
    last_checked_at  timestamptz not null default now(),
    content_hash     text not null,
    created_at       timestamptz not null default now(),
    updated_at       timestamptz not null default now(),
    constraint listings_dedup_unique unique (source_name, dedup_key),
    constraint listings_seen_order check (last_seen_at >= first_seen_at),
    constraint listings_identity check (source_id is not null or url is not null)
);

create index listings_first_seen_idx on public.listings (first_seen_at desc);
create index listings_deadline_idx on public.listings (deadline);
create index listings_category_idx on public.listings (category);
create index listings_source_id_idx on public.listings (source_name, source_id);
create index listings_title_trgm_idx on public.listings using gin (title extensions.gin_trgm_ops);
create index listings_org_trgm_idx on public.listings using gin (organisation extensions.gin_trgm_ops);

-- ---------------------------------------------------------------------------
-- listing_history: meaningful field changes on existing listings
-- ---------------------------------------------------------------------------
create table public.listing_history (
    id            bigint generated always as identity primary key,
    listing_id    uuid not null references public.listings (id) on delete cascade,
    scrape_run_id uuid references public.scrape_runs (id) on delete set null,
    field_name    text not null,
    old_value     text,
    new_value     text,
    observed_at   timestamptz not null default now()
);

create index listing_history_listing_idx on public.listing_history (listing_id, observed_at desc);
create index listing_history_observed_idx on public.listing_history (observed_at desc);
create index listing_history_run_idx on public.listing_history (scrape_run_id);

-- ---------------------------------------------------------------------------
-- admins: Supabase Auth users allowed to see the monitoring view
-- ---------------------------------------------------------------------------
create table public.admins (
    user_id    uuid primary key references auth.users (id) on delete cascade,
    created_at timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- updated_at maintenance
-- ---------------------------------------------------------------------------
create or replace function public.set_updated_at()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
    -- updated_at records the last *content* change; routine last_seen/last_checked
    -- touches by the collector leave it alone.
    if new.content_hash is distinct from old.content_hash then
        new.updated_at := now();
    else
        new.updated_at := old.updated_at;
    end if;
    return new;
end;
$$;

create trigger listings_set_updated_at
before update on public.listings
for each row execute function public.set_updated_at();
