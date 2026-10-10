CREATE TABLE IF NOT EXISTS patients (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

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

-- Changes made after the first deploy. Each one works on a new or an existing database and
-- is safe to run again. Constraints are dropped and re-added because Postgres has no
-- ADD CONSTRAINT IF NOT EXISTS, and init_db.py splits on ";" so a DO block can't be used.

-- What extraction proposed, so a pending memory remembers whether it was tentative
ALTER TABLE memories ADD COLUMN IF NOT EXISTS certainty TEXT CHECK (certainty IN ('definite', 'tentative'));

-- Every memory and session belongs to a real patient
ALTER TABLE memories DROP CONSTRAINT IF EXISTS memories_patient_fk;
ALTER TABLE memories ADD CONSTRAINT memories_patient_fk FOREIGN KEY (patient_id) REFERENCES patients(id);
ALTER TABLE sessions DROP CONSTRAINT IF EXISTS sessions_patient_fk;
ALTER TABLE sessions ADD CONSTRAINT sessions_patient_fk FOREIGN KEY (patient_id) REFERENCES patients(id);

-- Nothing can be spoken without a recorded confirmation
ALTER TABLE memories DROP CONSTRAINT IF EXISTS memories_confirmed_has_time;
ALTER TABLE memories ADD CONSTRAINT memories_confirmed_has_time
  CHECK (status NOT IN ('confirmed', 'tentative') OR confirmed_at IS NOT NULL);

-- A version chain can't fork: each memory is replaced by at most one confirmed version
-- (several pending proposals for the same memory are still allowed)
CREATE UNIQUE INDEX IF NOT EXISTS memories_one_successor ON memories (supersedes_id)
  WHERE status IN ('confirmed', 'tentative', 'superseded');

-- Gemini's raw output for each session, to debug extraction and build the test set
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS extraction JSONB;

-- A plan with a day but no time ("Anna might visit Saturday"). Its event_at is local midnight
-- of that day, and it's never told with a clock time
ALTER TABLE memories ADD COLUMN IF NOT EXISTS all_day BOOLEAN NOT NULL DEFAULT false;

-- A plan staff cancelled: kept so receipts of past answers still show it, never spoken again.
-- Re-adds the status check from CREATE TABLE (same name on a new database) with one more value
ALTER TABLE memories DROP CONSTRAINT IF EXISTS memories_status_check;
ALTER TABLE memories ADD CONSTRAINT memories_status_check CHECK (status IN
  ('pending', 'confirmed', 'tentative', 'superseded', 'rejected', 'self_reported', 'cancelled'));