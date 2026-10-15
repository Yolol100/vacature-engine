CREATE TABLE IF NOT EXISTS radar_observations (
  identity TEXT PRIMARY KEY,
  source_instance TEXT NOT NULL,
  canonical_url TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('baseline','pending','excluded','delivered')),
  payload_json TEXT NOT NULL,
  first_seen_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_radar_status ON radar_observations(status,first_seen_at);
CREATE TABLE IF NOT EXISTS radar_metadata (
  name TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
