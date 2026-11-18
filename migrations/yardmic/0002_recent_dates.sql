-- Preserve the last version of a completed date after it leaves recent's window.
CREATE TABLE yardmic_completed_date_chunks (
  date TEXT NOT NULL,
  ordinal INTEGER NOT NULL,
  estimated_at TEXT NOT NULL,
  value TEXT NOT NULL,
  PRIMARY KEY (date, ordinal)
);
