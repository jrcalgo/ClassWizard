-- User accounts, sessions, saved state and activity. Idempotent: run on every boot
-- after schema.sql (backend/storage/database/postgres.py main()).
-- Anonymous use never touches these tables.

CREATE TABLE IF NOT EXISTS users (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email              text NOT NULL,
    password_hash      text,                -- NULL for Google-only accounts
    google_sub         text UNIQUE,
    display_name       text,
    email_verified_at  timestamptz,
    created_at         timestamptz NOT NULL DEFAULT now(),
    last_login_at      timestamptz
);
CREATE UNIQUE INDEX IF NOT EXISTS users_email_lower_idx ON users (lower(email));

-- Only the SHA-256 of the cookie value is stored, so a database leak does not
-- hand out live sessions.
CREATE TABLE IF NOT EXISTS user_sessions (
    id            bigserial PRIMARY KEY,
    user_id       uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash    bytea NOT NULL UNIQUE,
    created_at    timestamptz NOT NULL DEFAULT now(),
    expires_at    timestamptz NOT NULL,
    last_seen_at  timestamptz NOT NULL DEFAULT now(),
    ip            text,
    user_agent    text
);
CREATE INDEX IF NOT EXISTS user_sessions_user_idx ON user_sessions (user_id);

CREATE TABLE IF NOT EXISTS email_tokens (
    token_hash  bytea PRIMARY KEY,
    user_id     uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    purpose     text NOT NULL CHECK (purpose IN ('verify', 'reset')),
    created_at  timestamptz NOT NULL DEFAULT now(),
    expires_at  timestamptz NOT NULL,
    used_at     timestamptz
);
CREATE INDEX IF NOT EXISTS email_tokens_user_idx ON email_tokens (user_id, purpose);

-- The parsed audit is Fernet-encrypted (AUDIT_ENCRYPTION_KEY). summary holds
-- only headline fields that are safe to list without decrypting.
CREATE TABLE IF NOT EXISTS saved_audits (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    filename    text,
    ciphertext  bytea NOT NULL,
    summary     jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS saved_audits_user_idx ON saved_audits (user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS searches (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    audit_id        uuid REFERENCES saved_audits(id) ON DELETE SET NULL,
    soc_codes       text[] NOT NULL,
    prefs           jsonb NOT NULL DEFAULT '{}'::jsonb,
    recommendation  jsonb,
    created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS searches_user_idx ON searches (user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS chat_messages (
    id          bigserial PRIMARY KEY,
    search_id   uuid NOT NULL REFERENCES searches(id) ON DELETE CASCADE,
    role        text NOT NULL CHECK (role IN ('user', 'assistant')),
    content     text NOT NULL,
    sources     jsonb,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS chat_messages_search_idx ON chat_messages (search_id, id);

CREATE TABLE IF NOT EXISTS activity_log (
    id          bigserial PRIMARY KEY,
    user_id     uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    event       text NOT NULL,
    detail      jsonb NOT NULL DEFAULT '{}'::jsonb,
    ip          text,
    user_agent  text,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS activity_log_user_idx ON activity_log (user_id, id DESC);
