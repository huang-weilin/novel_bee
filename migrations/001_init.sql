-- PostgreSQL 16 initial memory schema.
-- Apply with: psql "$DATABASE_URL" -f migrations/001_init.sql
-- The SQLite development adapter mirrors these tables; see
-- src/novel_pipeline/memory/schema.py.

BEGIN;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version text PRIMARY KEY,
    applied_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS projects (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    title text NOT NULL,
    genre text NOT NULL,
    target_chapters int,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS chapters (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL REFERENCES projects(id),
    seq int NOT NULL,
    status text NOT NULL CHECK (
        status IN ('planned', 'trial', 'generating', 'pending', 'final')
    ),
    title text,
    content text,
    summary text,
    score int,
    rewrite_count int NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (project_id, seq)
);

CREATE TABLE IF NOT EXISTS characters (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL REFERENCES projects(id),
    name text NOT NULL,
    alive boolean NOT NULL DEFAULT true,
    status text,
    core_attributes jsonb NOT NULL DEFAULT '{}'::jsonb,
    first_chapter int,
    last_chapter int,
    UNIQUE (project_id, name)
);

CREATE TABLE IF NOT EXISTS character_events (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    character_id uuid NOT NULL REFERENCES characters(id),
    chapter_seq int NOT NULL,
    event_summary text NOT NULL,
    story_time text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ledger_items (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL REFERENCES projects(id),
    name text NOT NULL,
    quantity numeric NOT NULL DEFAULT 0,
    unit text,
    updated_chapter int,
    UNIQUE (project_id, name)
);

CREATE TABLE IF NOT EXISTS ledger_item_aliases (
    project_id uuid NOT NULL REFERENCES projects(id),
    alias text NOT NULL,
    canonical_name text NOT NULL,
    PRIMARY KEY (project_id, alias)
);

CREATE TABLE IF NOT EXISTS ledger_info_gap (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL REFERENCES projects(id),
    character_id uuid NOT NULL REFERENCES characters(id),
    known_facts jsonb NOT NULL DEFAULT '[]'::jsonb,
    unknown_facts jsonb NOT NULL DEFAULT '[]'::jsonb,
    updated_chapter int,
    UNIQUE (project_id, character_id)
);

CREATE TABLE IF NOT EXISTS foreshadowing (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL REFERENCES projects(id),
    title text NOT NULL,
    planted_chapter int NOT NULL,
    resolved_chapter int,
    status text NOT NULL DEFAULT 'planted' CHECK (
        status IN ('planted', 'resolved', 'abandoned')
    ),
    notes text,
    importance int NOT NULL DEFAULT 1 CHECK (importance BETWEEN 1 AND 5),
    target_chapter int,
    last_touched_chapter int
);

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

CREATE TABLE IF NOT EXISTS quality_failures (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    chapter_id uuid NOT NULL REFERENCES chapters(id),
    layer text NOT NULL CHECK (layer IN ('hard_gate', 'score', 'consistency')),
    rule_id text NOT NULL,
    severity text NOT NULL CHECK (severity IN ('blocker', 'major', 'minor')),
    evidence text,
    resolved boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS confirmations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    chapter_id uuid NOT NULL REFERENCES chapters(id),
    gate_type text NOT NULL CHECK (gate_type IN ('outline', 'trial', 'quality')),
    decision text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_chapters_project_seq
    ON chapters(project_id, seq);
CREATE INDEX IF NOT EXISTS idx_characters_project_name
    ON characters(project_id, name);
CREATE INDEX IF NOT EXISTS idx_foreshadowing_project_status
    ON foreshadowing(project_id, status);
CREATE INDEX IF NOT EXISTS idx_emotional_threads_project_status
    ON emotional_threads(project_id, status);
CREATE INDEX IF NOT EXISTS idx_world_rules_project_status
    ON world_rules(project_id, status);
CREATE INDEX IF NOT EXISTS idx_quality_failures_chapter
    ON quality_failures(chapter_id);

INSERT INTO schema_migrations (version) VALUES ('001_init')
ON CONFLICT (version) DO NOTHING;

COMMIT;
