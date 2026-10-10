"""Resets the demo patient: Rose, memories timed relative to now, and nothing else.

Run from backend/ before a demo:  python scripts/seed_demo.py
(the staff endpoint POST /demo/reset does exactly the same)

In one transaction it removes the demo patient's memories (including what the patient said
they did), caregiver sessions, answers, alerts, and "Remind now" records, then writes the
memories from app/memory/demo.py. Family messages are kept. The database is shared, so this
resets the demo for everyone.
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from app import db, store
from app.memory.context import build_facts
from app.memory.demo import PATIENT_NAME, demo_memories
from app.store import PATIENT_ID

if not db.enabled():
    sys.exit("DATABASE_URL isn't set in backend/.env, so there's no database to seed.")

memories = demo_memories(datetime.now(timezone.utc))
result = store.reset_demo(PATIENT_ID, PATIENT_NAME, memories)

removed = ", ".join(f"{n} {table}" for table, n in result["removed"].items() if n) or "nothing"
print(f"Reset {PATIENT_NAME} ({PATIENT_ID}). Removed: {removed}.")
print(f"Seeded {len(memories)} memories:")
for m in memories:
    print(f"  {m['status']:11} {m['summary']}" + (f"  ({m['event_at']})" if m["event_at"] else ""))
print("\nWhat the agent will be told:\n" + build_facts(PATIENT_ID)["facts"])
