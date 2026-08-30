-- LedgerLens
-- Migration 006: Authentication -- users and DB-backed sessions


-- ============================================================
-- Users
-- ============================================================

create table if not exists users (
    id uuid primary key default gen_random_uuid(),

    email text not null unique,
    password_hash text not null,
    password_salt text not null,

    role text not null check (role in ('analyst', 'reviewer')),

    created_at timestamptz not null default now()
);


-- ============================================================
-- Sessions
-- ============================================================
-- Opaque, cryptographically random bearer tokens (see
-- backend/app/auth/security.py) rather than a signed/stateless scheme
-- (JWT) -- this lets logout revoke a session immediately by deleting
-- its row, and reuses the same connect()/cursor pattern every other
-- table in this project already uses.

create table if not exists sessions (
    token text primary key,

    user_id uuid not null
        references users(id)
        on delete cascade,

    created_at timestamptz not null default now(),
    expires_at timestamptz not null
);


-- ============================================================
-- Indexes
-- ============================================================

create index if not exists idx_sessions_user_id
    on sessions(user_id);

create index if not exists idx_sessions_expires_at
    on sessions(expires_at);
