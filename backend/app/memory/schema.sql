CREATE TABLE IF NOT EXISTS sessions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  patient_id TEXT NOT NULL,
  transcript TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS memories (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  patient_id TEXT NOT NULL,
  kind TEXT NOT NULL,
  summary TEXT NOT NULL,
  details JSONB,
  event_at TIMESTAMPTZ,
  expires_at TIMESTAMPTZ,
  status TEXT NOT NULL CHECK (status IN ('pending', 'confirmed', 'tentative', 'superseded', 'rejected', 'self_reported')),
  source TEXT NOT NULL CHECK (source IN ('caregiver_session', 'caregiver_typed', 'patient')),
  source_quote TEXT,
  session_id UUID REFERENCES sessions(id),
  supersedes_id UUID REFERENCES memories(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  confirmed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS memories_current_idx ON memories (patient_id, status, event_at);

CREATE TABLE IF NOT EXISTS interactions (
  ts TIMESTAMPTZ NOT NULL DEFAULT now(),
  patient_id TEXT NOT NULL,
  topic TEXT,
  question TEXT,
  answer TEXT,
  memory_ids UUID[],
  answered BOOLEAN,
  latency_ms INT
);

SELECT create_hypertable('interactions', 'ts', if_not_exists => TRUE);

CREATE MATERIALIZED VIEW IF NOT EXISTS questions_hourly
WITH (timescaledb.continuous, timescaledb.materialized_only = false) AS
SELECT time_bucket('1 hour', ts) AS hour, patient_id, topic, count(*) AS asks
FROM interactions
GROUP BY hour, patient_id, topic
WITH NO DATA;

SELECT add_continuous_aggregate_policy('questions_hourly',
  start_offset => INTERVAL '30 days',
  end_offset => INTERVAL '1 minute',
  schedule_interval => INTERVAL '5 minutes',
  if_not_exists => TRUE);

CREATE TABLE IF NOT EXISTS alerts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  ts TIMESTAMPTZ NOT NULL DEFAULT now(),
  patient_id TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('missing_info', 'self_reported_med', 'help_requested')),
  message TEXT NOT NULL,
  resolved BOOLEAN NOT NULL DEFAULT FALSE
);