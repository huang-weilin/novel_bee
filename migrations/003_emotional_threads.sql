-- M4 T4-0d emotional-debt ledger upgrade.
-- Apply after 001_init.sql and 002_long_span.sql:
--   psql "$DATABASE_URL" -f migrations/003_emotional_threads.sql
-- Fresh installs already get this table from 001; the IF NOT EXISTS clauses
-- make this migration safe for both fresh and existing databases.

BEGIN;

CREATE TABLE IF NOT EXISTS emotional_threads (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL REFERENCES projects(id),
    title text NOT NULL,
    debt_from text NOT NULL,
    debt_to text NOT NULL,
    kind text NOT NULL DEFAULT 'other' CHECK (
        kind IN (
            'approval', 'apology', 'belonging', 'recognition',
            'rescue', 'other'
        )
    ),
    setup_chapter int NOT NULL,
    target_payoff_chapter int,
    status text NOT NULL DEFAULT 'open' CHECK (
        status IN ('open', 'paid', 'abandoned')
    ),
    importance int NOT NULL DEFAULT 3 CHECK (importance BETWEEN 1 AND 5),
    last_touched_chapter int,
    notes text,
    UNIQUE (project_id, title)
);

CREATE INDEX IF NOT EXISTS idx_emotional_threads_project_status
    ON emotional_threads(project_id, status);

INSERT INTO schema_migrations (version) VALUES ('003_emotional_threads')
ON CONFLICT (version) DO NOTHING;

COMMIT;
