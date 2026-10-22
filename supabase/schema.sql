-- Supabase schema for the Fog Waste Console cloud tier.
-- Run once in the Supabase dashboard: SQL Editor -> New query -> paste -> Run.
-- Safe to re-run.
--
-- One row (id = 'live') holds the latest snapshot published by the fog layer.
--   * The dashboard (publishable/anon key) can only READ it.
--   * Only the fog layer (secret/service_role key, kept on the laptop) can WRITE it.
-- Grants are explicit so the table works whether or not the project exposes new
-- tables to the Data API by default.

create table if not exists public.snapshots (
    id           text primary key,
    published_at timestamptz not null default now(),
    payload      jsonb       not null
);

comment on table public.snapshots is
    'Latest fog-layer snapshot (bins, routes, network, events) for the public dashboard';

-- Stamp every insert/update with the database clock, so "last updated" on the
-- dashboard doesn't depend on the publishing laptop's clock.
create or replace function public.touch_published_at()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
    new.published_at := now();
    return new;
end;
$$;

drop trigger if exists snapshots_touch_published_at on public.snapshots;
create trigger snapshots_touch_published_at
    before insert or update on public.snapshots
    for each row execute function public.touch_published_at();

-- Row Level Security: public read-only
alter table public.snapshots enable row level security;

drop policy if exists "Snapshots are publicly readable" on public.snapshots;
create policy "Snapshots are publicly readable"
    on public.snapshots
    for select
    to anon, authenticated
    using (true);

-- Explicit privileges. anon/authenticated: read only. service_role (secret key)
-- bypasses RLS and is the only role allowed to write.
revoke all on public.snapshots from anon, authenticated;
grant select on public.snapshots to anon, authenticated;
grant select, insert, update, delete on public.snapshots to service_role;
