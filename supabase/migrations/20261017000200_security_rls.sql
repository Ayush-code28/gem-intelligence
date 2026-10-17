-- Row Level Security and privileges.
--
-- Roles (Supabase conventions):
--   anon           public website visitors (anon/publishable key)
--   authenticated  signed-in Supabase Auth users (admins are a subset, see public.admins)
--   postgres       table owner; used by the collector via DATABASE_URL (owner bypasses RLS)
--
-- Supabase grants broad default privileges on the public schema to anon/authenticated,
-- so everything is revoked first and then granted back explicitly.

revoke all on public.listings, public.listing_history, public.scrape_runs, public.admins
    from anon, authenticated;
revoke all on all sequences in schema public from anon, authenticated;
revoke execute on all functions in schema public from public, anon, authenticated;

alter table public.listings        enable row level security;
alter table public.listing_history enable row level security;
alter table public.scrape_runs     enable row level security;
alter table public.admins          enable row level security;

-- The collector connects as the table owner, which bypasses RLS by design.
-- Every other role is limited by the policies below.

-- ---------------------------------------------------------------------------
-- Admin check
-- ---------------------------------------------------------------------------
create or replace function public.is_admin()
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
    select exists (
        select 1 from public.admins a where a.user_id = (select auth.uid())
    );
$$;

-- New functions get EXECUTE for PUBLIC (and, on Supabase, anon) by default: revoke explicitly.
revoke execute on function public.is_admin() from public, anon;
grant execute on function public.is_admin() to authenticated;
revoke execute on function public.set_updated_at() from public, anon, authenticated;

-- ---------------------------------------------------------------------------
-- listings: public read of display columns only; no public writes
-- ---------------------------------------------------------------------------
grant select (
    id, source_name, source_id, bid_number, title, organisation, ministry, department,
    category, listing_type, quantity, published_at, deadline, url,
    first_seen_at, last_seen_at, last_checked_at, created_at, updated_at
) on public.listings to anon, authenticated;

create policy listings_public_read on public.listings
    for select to anon, authenticated using (true);

-- ---------------------------------------------------------------------------
-- listing_history: public read; no public writes
-- ---------------------------------------------------------------------------
grant select (id, listing_id, field_name, old_value, new_value, observed_at)
    on public.listing_history to anon, authenticated;

create policy listing_history_public_read on public.listing_history
    for select to anon, authenticated using (true);

-- ---------------------------------------------------------------------------
-- scrape_runs: admins only (read). Nobody but the collector writes.
-- ---------------------------------------------------------------------------
grant select on public.scrape_runs to authenticated;

create policy scrape_runs_admin_read on public.scrape_runs
    for select to authenticated using ((select public.is_admin()));

-- ---------------------------------------------------------------------------
-- admins: a signed-in user may see only their own membership row
-- ---------------------------------------------------------------------------
grant select on public.admins to authenticated;

create policy admins_self_read on public.admins
    for select to authenticated using (user_id = (select auth.uid()));
