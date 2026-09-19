CREATE TABLE IF NOT EXISTS ingest_tokens (
  id TEXT PRIMARY KEY,
  token_hash TEXT NOT NULL UNIQUE,
  created_at TEXT NOT NULL,
  revoked_at TEXT
);

CREATE TABLE IF NOT EXISTS lessons (
  fingerprint TEXT PRIMARY KEY,
  category TEXT NOT NULL,
  observation TEXT NOT NULL,
  outcome TEXT NOT NULL,
  suggestion TEXT NOT NULL,
  evidence TEXT NOT NULL,
  review_status TEXT NOT NULL DEFAULT 'candidate',
  created_at TEXT NOT NULL,
  reviewed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_lessons_created ON lessons(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_lessons_status ON lessons(review_status, created_at DESC);
