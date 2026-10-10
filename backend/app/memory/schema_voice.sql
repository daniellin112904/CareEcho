-- Tables and columns the voice features need, on top of schema.sql.
-- Kept separate so schema.sql stays the memory system's file. Safe to run more than once.
-- The functions that read and write these are in app/store.py.

-- Groups answers by conversation on the staff Conversations page
ALTER TABLE interactions ADD COLUMN IF NOT EXISTS conversation_id TEXT;
-- A stable ID per answer for the page (hypertables can't have a primary key without ts)
ALTER TABLE interactions ADD COLUMN IF NOT EXISTS id UUID NOT NULL DEFAULT gen_random_uuid();

-- Messages family wrote, read aloud in their cloned voice (the MP3s stay cached on disk)
CREATE TABLE IF NOT EXISTS family_messages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  patient_id TEXT NOT NULL,
  from_name TEXT NOT NULL,
  voice_id TEXT NOT NULL,
  text TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Reminders staff sent with "Remind now" (scheduled reminders are computed from memories)
CREATE TABLE IF NOT EXISTS reminders_sent (
  id TEXT PRIMARY KEY,
  patient_id TEXT NOT NULL,
  memory_id UUID NOT NULL REFERENCES memories(id),
  at TIMESTAMPTZ NOT NULL DEFAULT now()
);
