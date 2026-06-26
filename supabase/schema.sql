create extension if not exists postgis;

create table if not exists activations (
  id text primary key,
  name_en text not null,
  name_es text not null,
  provider text not null,
  status text not null,
  updated_at timestamptz not null default now()
);

create table if not exists aois (
  id text primary key,
  activation_id text references activations(id),
  name_en text not null,
  name_es text not null,
  status text not null,
  priority text not null default 'normal',
  expected_delivery timestamptz,
  bounds geometry(Polygon, 4326),
  catalog_url text,
  updated_at timestamptz not null default now()
);

create table if not exists products (
  id uuid primary key default gen_random_uuid(),
  aoi_id text references aois(id),
  product_type text not null,
  provider text not null,
  version text,
  status text not null,
  source_url text,
  download_url text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists damage_features (
  id text primary key,
  aoi_id text references aois(id),
  source_product_id uuid references products(id),
  source_label text,
  damage_class text,
  damage_percent numeric,
  confidence numeric,
  review_status text not null default 'unreviewed',
  geom geometry(Geometry, 4326),
  centroid geometry(Point, 4326),
  properties jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);

create index if not exists damage_features_geom_idx on damage_features using gist (geom);
create index if not exists damage_features_aoi_status_idx on damage_features (aoi_id, review_status, damage_class);

create table if not exists vlm_jobs (
  id uuid primary key default gen_random_uuid(),
  damage_feature_id text references damage_features(id),
  status text not null default 'queued',
  priority integer not null default 100,
  model text not null default 'MiniMax-M3',
  chip_url text,
  prompt_version text not null default 'blind-before-after-v1',
  result jsonb,
  error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists vlm_jobs_status_priority_idx on vlm_jobs (status, priority, created_at);

alter table activations enable row level security;
alter table aois enable row level security;
alter table products enable row level security;
alter table damage_features enable row level security;
alter table vlm_jobs enable row level security;

drop policy if exists "public read activations" on activations;
drop policy if exists "public read aois" on aois;
drop policy if exists "public read products" on products;
drop policy if exists "public read damage" on damage_features;
drop policy if exists "public read completed vlm" on vlm_jobs;

create policy "public read activations" on activations for select using (true);
create policy "public read aois" on aois for select using (true);
create policy "public read products" on products for select using (true);
create policy "public read damage" on damage_features for select using (true);
create policy "public read completed vlm" on vlm_jobs for select using (status = 'completed');
