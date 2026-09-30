-- QVeris Sentinel — initial schema (backend plan section 11.1)

CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL);

CREATE TABLE nodes (
  id TEXT PRIMARY KEY, name TEXT NOT NULL,
  role TEXT NOT NULL CHECK(role IN ('signer','verifier','adversary')),
  label TEXT, color TEXT, pos_x REAL, pos_y REAL, pos_z REAL,
  hidden INTEGER NOT NULL DEFAULT 0, suspended INTEGER NOT NULL DEFAULT 0,
  meta TEXT NOT NULL DEFAULT '{}', created_at REAL NOT NULL);

CREATE TABLE groups (
  id TEXT PRIMARY KEY, signer_id TEXT NOT NULL REFERENCES nodes(id), recipients TEXT NOT NULL,
  hidden INTEGER NOT NULL DEFAULT 0, reservoir_target INTEGER NOT NULL DEFAULT 3, created_at REAL NOT NULL);

CREATE TABLE links (
  id TEXT PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN ('quantum','classical')),
  a TEXT NOT NULL REFERENCES nodes(id), b TEXT NOT NULL REFERENCES nodes(id),
  length_km REAL NOT NULL DEFAULT 0, baseline_channel TEXT NOT NULL DEFAULT '[]',
  authenticated_classical INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK(status IN ('ACTIVE','QUARANTINED','DEGRADED')),
  status_reason TEXT, hidden INTEGER NOT NULL DEFAULT 0, updated_at REAL NOT NULL, created_at REAL NOT NULL);

CREATE TABLE link_secrets (link_id TEXT PRIMARY KEY REFERENCES links(id), mac_key BLOB NOT NULL);

CREATE TABLE baselines (
  link_id TEXT PRIMARY KEY REFERENCES links(id), calibrated_at REAL NOT NULL, samples INTEGER NOT NULL,
  spec_hash TEXT NOT NULL, stats TEXT NOT NULL);

CREATE TABLE bundles (
  id TEXT PRIMARY KEY, group_id TEXT NOT NULL REFERENCES groups(id), signer_id TEXT NOT NULL,
  recipients TEXT NOT NULL, preset TEXT NOT NULL, params TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('DISTRIBUTING','ACTIVE','SIGNED','CONSUMED','BURNED','COMPROMISED','REVOKED','EXPIRED')),
  origin TEXT NOT NULL, design TEXT, summary TEXT, session_id TEXT, injected_attack TEXT,
  material_path TEXT, created_at REAL NOT NULL, updated_at REAL NOT NULL, expires_at REAL);
CREATE INDEX ix_bundles_group_status ON bundles(group_id, status, created_at);

CREATE TABLE bundle_consumption (
  bundle_id TEXT NOT NULL, verifier_id TEXT NOT NULL, session_id TEXT NOT NULL,
  consumed_at REAL NOT NULL, PRIMARY KEY (bundle_id, verifier_id));

CREATE TABLE nonces (verifier_id TEXT NOT NULL, nonce TEXT NOT NULL, session_id TEXT, seen_at REAL NOT NULL,
  PRIMARY KEY (verifier_id, nonce));
CREATE TABLE signer_sequences (signer_id TEXT NOT NULL, verifier_id TEXT NOT NULL, last_seq INTEGER NOT NULL,
  PRIMARY KEY (signer_id, verifier_id));
CREATE TABLE signer_counters (group_id TEXT PRIMARY KEY, next_seq INTEGER NOT NULL);

CREATE TABLE sessions (
  id TEXT PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN ('distribution','signature')),
  origin TEXT NOT NULL, group_id TEXT, bundle_id TEXT, signer_id TEXT, recipients TEXT,
  message_preview TEXT, message_sha256 TEXT, encoding TEXT,
  injected_attack TEXT, attack_category TEXT,
  verdict TEXT NOT NULL, threat_level TEXT NOT NULL, category TEXT, subtype TEXT,
  threat_score REAL NOT NULL DEFAULT 0, counterfactual INTEGER NOT NULL DEFAULT 0,
  latency_ms REAL, summary TEXT NOT NULL, report TEXT,
  created_at REAL NOT NULL);
CREATE INDEX ix_sessions_created ON sessions(created_at DESC);
CREATE INDEX ix_sessions_kind ON sessions(kind, created_at DESC);

CREATE TABLE attack_runs (
  id TEXT PRIMARY KEY, attack_id TEXT NOT NULL, category TEXT NOT NULL, group_id TEXT, origin TEXT NOT NULL,
  detected INTEGER NOT NULL, correct INTEGER NOT NULL, report TEXT NOT NULL, created_at REAL NOT NULL);
CREATE INDEX ix_attack_runs_created ON attack_runs(created_at DESC);

CREATE TABLE incidents (
  id TEXT PRIMARY KEY, created_at REAL NOT NULL, updated_at REAL NOT NULL,
  severity TEXT NOT NULL, category TEXT NOT NULL, subtype TEXT, title TEXT NOT NULL, summary TEXT NOT NULL,
  link_id TEXT, group_id TEXT, session_id TEXT, bundle_id TEXT, occurrences INTEGER NOT NULL DEFAULT 1,
  status TEXT NOT NULL DEFAULT 'OPEN' CHECK(status IN ('OPEN','ACKNOWLEDGED','RESOLVED')),
  assessment TEXT NOT NULL, actions TEXT NOT NULL DEFAULT '[]', recommended TEXT NOT NULL DEFAULT '[]',
  attributed_to TEXT, ledger_tx_id TEXT);
CREATE INDEX ix_incidents_status ON incidents(status, updated_at DESC);

CREATE TABLE link_monitor (
  link_id TEXT NOT NULL, t REAL NOT NULL, bundle_id TEXT, qber REAL, chsh REAL, fidelity REAL,
  cusum_qber REAL, cusum_chsh REAL, ewma_qber REAL, h_qber REAL, h_chsh REAL, alarm INTEGER NOT NULL DEFAULT 0);
CREATE INDEX ix_link_monitor ON link_monitor(link_id, t DESC);
CREATE TABLE link_monitor_state (link_id TEXT PRIMARY KEY, state TEXT NOT NULL);

CREATE TABLE ledger_blocks (height INTEGER PRIMARY KEY, hash TEXT NOT NULL, prev_hash TEXT NOT NULL,
  merkle_root TEXT NOT NULL, timestamp REAL NOT NULL, tx_count INTEGER NOT NULL);
CREATE TABLE ledger_txs (id TEXT PRIMARY KEY, block_height INTEGER REFERENCES ledger_blocks(height),
  idx INTEGER, kind TEXT NOT NULL, payload TEXT NOT NULL, payload_hash TEXT NOT NULL, ref_id TEXT, created_at REAL NOT NULL);
CREATE INDEX ix_ledger_pending ON ledger_txs(block_height, created_at);
CREATE INDEX ix_ledger_ref ON ledger_txs(ref_id);
CREATE TABLE ledger_tamper_log (id INTEGER PRIMARY KEY AUTOINCREMENT, tx_id TEXT NOT NULL,
  original_payload TEXT NOT NULL, tampered_at REAL NOT NULL, reverted_at REAL);

CREATE TABLE jobs (id TEXT PRIMARY KEY, kind TEXT NOT NULL, preset TEXT NOT NULL, params TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('QUEUED','RUNNING','SUCCEEDED','FAILED','CANCELLED')),
  progress REAL NOT NULL DEFAULT 0, message TEXT, result TEXT, error TEXT,
  created_at REAL NOT NULL, started_at REAL, finished_at REAL);
CREATE INDEX ix_jobs_kind ON jobs(kind, created_at DESC);

CREATE TABLE kv_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
