-- M3.5 long-span memory upgrade.
-- Apply after 001_init.sql:
--   psql "$DATABASE_URL" -f migrations/002_long_span.sql
-- Fresh installs already get these columns from 001; the IF NOT EXISTS
-- clauses make this migration safe for both fresh and existing databases.

BEGIN;

ALTER TABLE foreshadowing
    ADD COLUMN IF NOT EXISTS importance int NOT NULL DEFAULT 1;
ALTER TABLE foreshadowing
    ADD COLUMN IF NOT EXISTS target_chapter int;
ALTER TABLE foreshadowing
    ADD COLUMN IF NOT EXISTS last_touched_chapter int;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conrelid = 'foreshadowing'::regclass
          AND conname = 'foreshadowing_importance_check'
    ) THEN
        ALTER TABLE foreshadowing
            ADD CONSTRAINT foreshadowing_importance_check
            CHECK (importance BETWEEN 1 AND 5);
    END IF;
END
$$;

CREATE TABLE IF NOT EXISTS world_rules (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL REFERENCES projects(id),
    name text NOT NULL,
    content text NOT NULL,
    importance int NOT NULL DEFAULT 3 CHECK (importance BETWEEN 1 AND 5),
    source_chapter int,
    updated_chapter int,
    status text NOT NULL DEFAULT 'active' CHECK (
        status IN ('active', 'deprecated')
    ),
    UNIQUE (project_id, name)
);

CREATE INDEX IF NOT EXISTS idx_world_rules_project_status
    ON world_rules(project_id, status);

INSERT INTO schema_migrations (version) VALUES ('002_long_span')
ON CONFLICT (version) DO NOTHING;

COMMIT;
