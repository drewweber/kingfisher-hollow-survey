CREATE TABLE yardmic_segments (
  segment TEXT PRIMARY KEY CHECK (segment IN ('recent', 'history')),
  token TEXT,
  lease_until INTEGER NOT NULL DEFAULT 0,
  retry_at INTEGER NOT NULL DEFAULT 0,
  requested_end TEXT NOT NULL DEFAULT '',
  failures INTEGER NOT NULL DEFAULT 0
);
INSERT INTO yardmic_segments (segment) VALUES ('recent'), ('history');

CREATE TABLE yardmic_snapshot_chunks (
  segment TEXT NOT NULL REFERENCES yardmic_segments(segment),
  ordinal INTEGER NOT NULL,
  value TEXT NOT NULL,
  PRIMARY KEY (segment, ordinal)
);
