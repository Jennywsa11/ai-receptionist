-- Enable vector support
create extension if not exists vector;

create table if not exists public.scraped_sites (
  id bigserial primary key,
  url text not null,
  title text,
  scraped_at timestamptz not null default now()
);

create table if not exists public.site_content (
  id bigserial primary key,
  site_id bigint not null references public.scraped_sites(id) on delete cascade,
  page_url text not null,
  content_chunk text not null,
  embedding vector(1536) not null,
  created_at timestamptz not null default now()
);

create index if not exists idx_scraped_sites_url on public.scraped_sites (url);
create index if not exists idx_site_content_site_id on public.site_content (site_id);
create index if not exists idx_site_content_embedding
  on public.site_content using ivfflat (embedding vector_cosine_ops) with (lists = 100);

-- Supabase API permissions (required when using anon/authenticated keys)
grant usage on schema public to anon, authenticated;
grant select, insert, update, delete on table public.scraped_sites to anon, authenticated;
grant select, insert, update, delete on table public.site_content to anon, authenticated;
grant usage, select on sequence public.scraped_sites_id_seq to anon, authenticated;
grant usage, select on sequence public.site_content_id_seq to anon, authenticated;

alter table public.scraped_sites enable row level security;
alter table public.site_content enable row level security;

drop policy if exists "anon_authenticated_all_scraped_sites" on public.scraped_sites;
create policy "anon_authenticated_all_scraped_sites"
  on public.scraped_sites
  for all
  to anon, authenticated
  using (true)
  with check (true);

drop policy if exists "anon_authenticated_all_site_content" on public.site_content;
create policy "anon_authenticated_all_site_content"
  on public.site_content
  for all
  to anon, authenticated
  using (true)
  with check (true);

create or replace function public.match_site_content(
  p_site_id bigint,
  query_embedding vector(1536),
  match_count int default 6
)
returns table (
  id bigint,
  site_id bigint,
  page_url text,
  content_chunk text,
  similarity float
)
language sql
stable
as $$
  select
    sc.id,
    sc.site_id,
    sc.page_url,
    sc.content_chunk,
    1 - (sc.embedding <=> query_embedding) as similarity
  from public.site_content sc
  where sc.site_id = p_site_id
  order by sc.embedding <=> query_embedding
  limit match_count;
$$;

grant execute on function public.match_site_content(bigint, vector, int) to anon, authenticated;
