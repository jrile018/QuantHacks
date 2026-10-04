-- QuantHaxs storage audit. No existing market tables are changed.
-- Execute only against the authorized DEV service after connection repair.
CREATE SCHEMA IF NOT EXISTS quanthaxs_storage;
CREATE TABLE IF NOT EXISTS quanthaxs_storage.audit_runs (
  run_id text PRIMARY KEY,
  started_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now(),
  workspace text NOT NULL,
  retention_policy jsonb NOT NULL,
  backup_commit text,
  backup_url text,
  drive_audit_url text,
  free_bytes_before bigint,
  free_bytes_after bigint,
  status text NOT NULL
);
CREATE TABLE IF NOT EXISTS quanthaxs_storage.file_inventory (
  run_id text NOT NULL REFERENCES quanthaxs_storage.audit_runs(run_id),
  relative_path text NOT NULL,
  size_bytes bigint NOT NULL CHECK (size_bytes >= 0),
  origin text,
  retention_action text NOT NULL,
  evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
  sha256 text,
  backup_commit text,
  last_observed_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (run_id, relative_path)
);
CREATE TABLE IF NOT EXISTS quanthaxs_storage.file_events (
  event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  run_id text NOT NULL REFERENCES quanthaxs_storage.audit_runs(run_id),
  relative_path text NOT NULL,
  action text NOT NULL,
  size_bytes bigint,
  reason text NOT NULL,
  outcome text NOT NULL,
  event_at timestamptz NOT NULL DEFAULT now(),
  detail jsonb NOT NULL DEFAULT '{}'::jsonb
);
-- Inventory rows can be loaded using a bounded JSON parameter:
-- INSERT INTO quanthaxs_storage.file_inventory (...)
-- SELECT ... FROM jsonb_to_recordset($1::jsonb) AS rows(...)
-- ON CONFLICT (run_id, relative_path) DO UPDATE SET ...;
