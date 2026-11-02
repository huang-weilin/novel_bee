-- M4 T4-1c pending-chapter review items.
-- Apply after 001_init.sql:
--   psql "$DATABASE_URL" -f migrations/005_chapter_review.sql
-- Fresh installs already get this column from 001; IF NOT EXISTS keeps this
-- migration safe for both fresh and existing databases.

BEGIN;

ALTER TABLE chapters ADD COLUMN IF NOT EXISTS review_json jsonb;

INSERT INTO schema_migrations (version) VALUES ('005_chapter_review')
ON CONFLICT (version) DO NOTHING;

COMMIT;
