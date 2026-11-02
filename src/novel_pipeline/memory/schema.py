"""Portable development schema.

The production target is PostgreSQL 16 (``migrations/001_init.sql``). This
SQLite mirror keeps M3 logic testable on machines without Docker or a
PostgreSQL server. Types differ only where PostgreSQL has native UUID/JSONB
support; column names and constraints match the production schema.
"""

SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    genre TEXT NOT NULL,
    target_chapters INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS chapters (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id),
    seq INTEGER NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('planned', 'trial', 'generating', 'pending', 'final')
    ),
    title TEXT,
    content TEXT,
    summary TEXT,
    score INTEGER,
    rewrite_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(project_id, seq)
);

CREATE TABLE IF NOT EXISTS characters (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id),
    name TEXT NOT NULL,
    alive INTEGER NOT NULL DEFAULT 1 CHECK (alive IN (0, 1)),
    status TEXT,
    core_attributes TEXT NOT NULL DEFAULT '{}',
    first_chapter INTEGER,
    last_chapter INTEGER,
    UNIQUE(project_id, name)
);

CREATE TABLE IF NOT EXISTS character_events (
    id TEXT PRIMARY KEY,
    character_id TEXT NOT NULL REFERENCES characters(id),
    chapter_seq INTEGER NOT NULL,
    event_summary TEXT NOT NULL,
    story_time TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ledger_items (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id),
    name TEXT NOT NULL,
    quantity REAL NOT NULL DEFAULT 0,
    unit TEXT,
    updated_chapter INTEGER,
    UNIQUE(project_id, name)
);

CREATE TABLE IF NOT EXISTS ledger_item_aliases (
    project_id TEXT NOT NULL REFERENCES projects(id),
    alias TEXT NOT NULL,
    canonical_name TEXT NOT NULL,
    PRIMARY KEY (project_id, alias)
);

CREATE TABLE IF NOT EXISTS ledger_info_gap (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id),
    character_id TEXT NOT NULL REFERENCES characters(id),
    known_facts TEXT NOT NULL DEFAULT '[]',
    unknown_facts TEXT NOT NULL DEFAULT '[]',
    updated_chapter INTEGER,
    UNIQUE(project_id, character_id)
);

CREATE TABLE IF NOT EXISTS foreshadowing (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id),
    title TEXT NOT NULL,
    planted_chapter INTEGER NOT NULL,
    resolved_chapter INTEGER,
    status TEXT NOT NULL DEFAULT 'planted' CHECK (
        status IN ('planted', 'resolved', 'abandoned')
    ),
    notes TEXT,
    importance INTEGER NOT NULL DEFAULT 1 CHECK (
        importance BETWEEN 1 AND 5
    ),
    target_chapter INTEGER,
    last_touched_chapter INTEGER
);

CREATE TABLE IF NOT EXISTS emotional_threads (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id),
    title TEXT NOT NULL,
    debt_from TEXT NOT NULL,
    debt_to TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'other' CHECK (
        kind IN (
            'approval', 'apology', 'belonging', 'recognition',
            'rescue', 'other'
        )
    ),
    setup_chapter INTEGER NOT NULL,
    target_payoff_chapter INTEGER,
    status TEXT NOT NULL DEFAULT 'open' CHECK (
        status IN ('open', 'paid', 'abandoned')
    ),
    importance INTEGER NOT NULL DEFAULT 3 CHECK (
        importance BETWEEN 1 AND 5
    ),
    last_touched_chapter INTEGER,
    notes TEXT,
    UNIQUE(project_id, title)
);

CREATE TABLE IF NOT EXISTS world_rules (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id),
    name TEXT NOT NULL,
    content TEXT NOT NULL,
    importance INTEGER NOT NULL DEFAULT 3 CHECK (
        importance BETWEEN 1 AND 5
    ),
    source_chapter INTEGER,
    updated_chapter INTEGER,
    status TEXT NOT NULL DEFAULT 'active' CHECK (
        status IN ('active', 'deprecated')
    ),
    UNIQUE(project_id, name)
);

CREATE TABLE IF NOT EXISTS quality_failures (
    id TEXT PRIMARY KEY,
    chapter_id TEXT NOT NULL REFERENCES chapters(id),
    layer TEXT NOT NULL CHECK (
        layer IN ('hard_gate', 'score', 'consistency')
    ),
    rule_id TEXT NOT NULL,
    severity TEXT NOT NULL CHECK (
        severity IN ('blocker', 'major', 'minor')
    ),
    evidence TEXT,
    resolved INTEGER NOT NULL DEFAULT 0 CHECK (resolved IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS confirmations (
    id TEXT PRIMARY KEY,
    chapter_id TEXT NOT NULL REFERENCES chapters(id),
    gate_type TEXT NOT NULL CHECK (
        gate_type IN ('outline', 'trial', 'quality')
    ),
    decision TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
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
"""
