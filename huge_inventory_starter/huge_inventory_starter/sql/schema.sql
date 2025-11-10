-- SQL schema for HUGE Inventory (MVP)
-- Enable UUID extension (already enabled in most Supabase projects)
create extension if not exists "uuid-ossp";

-- Users (basic)
create table if not exists users (
  id uuid primary key default uuid_generate_v4(),
  full_name text not null,
  email text unique,
  role text check (role in ('admin','user')) default 'user',
  created_at timestamp with time zone default now()
);

-- Categories
create table if not exists categories (
  id uuid primary key default uuid_generate_v4(),
  name text unique not null
);

-- Tools
create table if not exists tools (
  id uuid primary key default uuid_generate_v4(),
  name text not null,
  category_id uuid references categories(id) on delete set null,
  quantity int not null default 1,
  current_out int not null default 0,
  location text,
  condition text,
  notes text,
  created_at timestamp with time zone default now()
);

-- Supplies (consumables)
create table if not exists supplies (
  id uuid primary key default uuid_generate_v4(),
  name text not null,
  category_id uuid references categories(id) on delete set null,
  quantity int not null default 0,
  reorder_threshold int not null default 0,
  location text,
  notes text,
  created_at timestamp with time zone default now()
);

-- Transactions (check in/out logs)
create table if not exists transactions (
  id uuid primary key default uuid_generate_v4(),
  tool_id uuid references tools(id) on delete cascade,
  user_id uuid references users(id) on delete set null,
  user_name text, -- for quick MVP logging if you don't yet create users
  action text check (action in ('check_out','check_in')) not null,
  note text,
  ts timestamp with time zone default now()
);

-- Helpful view for availability
create or replace view tool_status as
select
  t.id,
  t.name,
  t.quantity,
  t.current_out,
  (t.quantity - t.current_out) as available_qty
from tools t;

-- Sample categories
insert into categories (name) values
('Power Tools'), ('Hand Tools'), ('Ladders'), ('Fasteners'), ('Electrical')
on conflict (name) do nothing;

-- Sample users
insert into users (full_name, email, role) values
('Greg Schmitt', 'greg@example.com', 'admin'),
('Mason', 'mason@example.com', 'user')
on conflict (email) do nothing;

-- Sample tools
insert into tools (name, quantity, location, condition, notes)
values
('Milwaukee Drill', 3, 'Shop A', 'Good', 'With charger'),
('DeWalt Miter Saw', 1, 'Truck 2', 'Excellent', '12 in. blade'),
('Fiberglass Ladder 8ft', 2, 'Shop B', 'Fair', 'Label #LAD-8')
;

-- Sample supplies
insert into supplies (name, quantity, reorder_threshold, location, notes)
values
('Caulk - White', 24, 6, 'Shelf C', 'DAP Alex Plus'),
('SDS Screws 3"', 900, 200, 'Bin F', 'Exterior grade'),
('Painter''s Tape 1.5"', 12, 4, 'Shelf D', 'Blue')
;
