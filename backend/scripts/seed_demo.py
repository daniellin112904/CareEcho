"""Resets the demo patient in Tiger Data: Rose, plus memories timed relative to now.

Run from backend/ before a demo:  python scripts/seed_demo.py

Deletes only the demo patient's memories, sessions, and "Remind now" records, then writes the
memories from app/memory/demo.py, all in one transaction (it either fully happens or not at
all). Interactions, alerts, and family messages are untouched: they're still JSON files in
backend/data/ until they move to the database.
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from psycopg.types.json import Jsonb

from app import db
from app.memory.context import build_facts
from app.memory.demo import PATIENT_NAME, demo_memories
from app.store import PATIENT_ID

COLUMNS = ("id", "patient_id", "kind", "summary", "details", "event_at", "all_day", "status", "certainty", "source",
           "source_quote", "supersedes_id", "created_at", "confirmed_at")

if not db.enabled():
    sys.exit("DATABASE_URL isn't set in backend/.env, so there's no database to seed.")

memories = demo_memories(datetime.now(timezone.utc))

with db.pool().connection() as conn:
    conn.execute(
        "INSERT INTO patients (id, name) VALUES (%s, %s) ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name",
        (PATIENT_ID, PATIENT_NAME),
    )
    conn.execute("DELETE FROM reminders_sent WHERE patient_id = %s", (PATIENT_ID,))
    conn.execute("DELETE FROM memories WHERE patient_id = %s", (PATIENT_ID,))
    conn.execute("DELETE FROM sessions WHERE patient_id = %s", (PATIENT_ID,))
    # In list order: a newer version comes after the one it supersedes
    for m in memories:
        values = {**m, "patient_id": PATIENT_ID, "details": m["details"] and Jsonb(m["details"])}
        conn.execute(
            f"INSERT INTO memories ({', '.join(COLUMNS)}) VALUES ({', '.join(['%s'] * len(COLUMNS))})",
            [values[c] for c in COLUMNS],
        )

print(f"Seeded {PATIENT_NAME} ({PATIENT_ID}) with {len(memories)} memories:")
for m in memories:
    print(f"  {m['status']:11} {m['summary']}" + (f"  ({m['event_at']})" if m["event_at"] else ""))
print("\nWhat the agent will be told:\n" + build_facts(PATIENT_ID)["facts"])
