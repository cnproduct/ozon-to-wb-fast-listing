ALTER TABLE lessons ADD COLUMN published_version INTEGER;

CREATE TABLE IF NOT EXISTS rule_releases (
  version INTEGER PRIMARY KEY,
  rules_json TEXT NOT NULL,
  item_count INTEGER NOT NULL,
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_lessons_published ON lessons(published_version);
