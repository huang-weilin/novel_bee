-- M4 T4-0f ledger item alias upgrade.
-- Apply after 001_init.sql:
--   psql "$DATABASE_URL" -f migrations/004_item_aliases.sql
-- Fresh installs already get this table from 001; the IF NOT EXISTS clause
-- makes this migration safe for both fresh and existing databases.

BEGIN;

CREATE TABLE IF NOT EXISTS ledger_item_aliases (
    project_id uuid NOT NULL REFERENCES projects(id),
    alias text NOT NULL,
    canonical_name text NOT NULL,
    PRIMARY KEY (project_id, alias)
);

INSERT INTO schema_migrations (version) VALUES ('004_item_aliases')
ON CONFLICT (version) DO NOTHING;

COMMIT;
