"""The demo patient and her memories, with times relative to now so the demo never goes stale.

Used by scripts/seed_demo.py (writes them to Tiger Data), by app/store.py when there's no
database, and by scripts/safety_tests.py (with a fixed `now`, so the tests stay the same).

The memories cover every rule the agent depends on:
- Dentist appointment, confirmed: the main demo question. Always at 3 PM ("Anna picks you up
  at two thirty"): today if that's still at least 90 minutes away, otherwise tomorrow.
- The same appointment's earlier version (pickup at 2:00), superseded: never spoken, but
  receipts and history can still show it.
- Lunch with Joan, tentative: said as not certain.
- Mark, a person with no time: never expires.
- A haircut waiting for review, pending: never spoken.
Names don't overlap between memories on purpose: answer receipts match memories by their words
(receipt() in app/memory/events.py), so two memories naming Anna would both claim an answer.
"""

import os
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

PATIENT_NAME = "Rose"


def demo_memories(now: datetime) -> list[dict]:
    """Rows shaped like the memories table: IDs and times as strings (see app/store.py)."""
    tz = ZoneInfo(os.getenv("TIMEZONE", "America/New_York"))
    local = now.astimezone(tz)
    three_pm = local.replace(hour=15, minute=0, second=0, microsecond=0)
    dentist = three_pm if local + timedelta(minutes=90) <= three_pm else three_pm + timedelta(days=1)
    told, told_earlier = local - timedelta(hours=1), local - timedelta(hours=3)

    def at(day_offset: int, hour: int, minute: int = 0) -> datetime:
        return (dentist + timedelta(days=day_offset)).replace(hour=hour, minute=minute)

    def row(summary, kind, status, source, quote, event_at=None, details=None, confirmed_at=None, supersedes_id=None):
        return {
            "id": str(uuid.uuid4()),
            "kind": kind,
            "summary": summary,
            "details": details,
            "event_at": event_at and event_at.isoformat(),
            "all_day": False,
            "status": status,
            "certainty": {"confirmed": "definite", "superseded": "definite", "pending": "definite",
                          "tentative": "tentative"}.get(status),
            "source": source,
            "source_quote": quote,
            "session_id": None,
            "supersedes_id": supersedes_id,
            "created_at": (confirmed_at or local).isoformat(),
            "confirmed_at": confirmed_at and confirmed_at.isoformat(),
        }

    old_dentist = row(
        "Dentist appointment", "appointment", "superseded", "caregiver_session",
        f"Your dentist appointment is {_day_words(dentist, told_earlier)} at three. Anna will pick you up at two.",
        event_at=dentist, details={"who": "Anna", "pickup_at": (dentist - timedelta(hours=1)).isoformat()},
        confirmed_at=told_earlier,
    )
    return [
        old_dentist,
        row(
            "Dentist appointment", "appointment", "confirmed", "caregiver_session",
            f"Change of plan: Anna will pick you up at two thirty {_day_words(dentist, told)}, not two.",
            event_at=dentist, details={"who": "Anna", "pickup_at": (dentist - timedelta(minutes=30)).isoformat()},
            confirmed_at=told, supersedes_id=old_dentist["id"],
        ),
        row(
            "Lunch with Joan", "plan", "tentative", "caregiver_session",
            f"Joan said she might come by for lunch {_day_words(at(1, 12, 30), told)}, we'll see.",
            event_at=at(1, 12, 30), details={"who": "Joan"}, confirmed_at=told,
        ),
        row(
            "Mark is your son and lives in Boston", "person", "confirmed", "caregiver_typed",
            "Mark is her son. He lives in Boston.", confirmed_at=told_earlier,
        ),
        row(
            "Haircut", "appointment", "pending", "caregiver_session",
            f"She has a haircut {_day_words(at(2, 10), local)} at ten.", event_at=at(2, 10),
        ),
    ]


def _day_words(when: datetime, said_at: datetime) -> str:
    """How the caregiver would have said the day: 'today', 'tomorrow', or 'on Monday'."""
    days = (when.date() - said_at.astimezone(when.tzinfo).date()).days
    return "today" if days == 0 else "tomorrow" if days == 1 else f"on {when:%A}"
