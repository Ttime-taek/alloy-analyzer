create table if not exists public.alloy_app_state (
  id text primary key,
  favorites jsonb not null default '[]'::jsonb,
  updated_at timestamptz not null default now()
);

alter table public.alloy_app_state enable row level security;

insert into public.alloy_app_state (id, favorites)
values ('default', '[]'::jsonb)
on conflict (id) do nothing;

comment on table public.alloy_app_state is
  'Server-managed persistent state for the alloy analyzer.';
