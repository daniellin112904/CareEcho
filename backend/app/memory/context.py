"""What the voice companion knows about the patient.

The agent looks facts up live with its get_memories tool (GET /voice/facts, see
app/voice/routes.py), so a plan confirmed mid-conversation is picked up on the next question.
Placeholder until the memory system lands: once current_memories() returns real data, the
agent uses it automatically.
"""

import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.memory.routes import current_memories

PATIENT_ID = "demo"


def get_patient_name(patient_id: str) -> str:
    return "Rose"


# Tells the agent exactly what to do when nothing matches, so it never fills the gap itself
NO_MEMORY = "NO_MEMORY: nothing confirmed. Say you are not sure, and call ask_caregiver with the question."

# An event this long past is over and isn't mentioned any more
EXPIRED_AFTER = timedelta(hours=2)


def build_facts(patient_id: str) -> dict:
    """Spoken-style facts for the agent, plus the IDs of the memories they came from.

    Only confirmed and tentative memories that haven't ended. Every current memory is
    returned whatever the topic: the list is short, and filtering by the agent's guess at a
    topic ("leaving") could hide the memory that answers it ("Dentist appointment").
    """
    cutoff = datetime.now(timezone.utc) - EXPIRED_AFTER
    lines, ids = [], []
    for m in current_memories()["memories"]:
        if m["status"] not in ("confirmed", "tentative"):
            continue
        if m.get("event_at") and datetime.fromisoformat(m["event_at"]) < cutoff:
            continue
        line = m["summary"]
        if m.get("event_at"):
            line += f", {spoken_time(m['event_at'])}"
        # Not source_quote: words like "tomorrow" in it go stale the next day
        for key, value in (m.get("details") or {}).items():
            line += f"; {key.replace('_', ' ')}: {spoken_time(value) if is_timestamp(value) else value}"
        if m["status"] == "tentative":
            line += " (TENTATIVE: say it isn't certain yet)"
        lines.append(f"- {line}")
        ids.append(m["id"])
    return {"facts": "\n".join(lines) or NO_MEMORY, "memory_ids": ids}


def memories_by_id(ids: list[str]) -> dict[str, dict]:
    """The memories an answer was based on, for the staff's answer receipts.

    Placeholder: searches the current list. The real query should also return superseded
    versions, so a receipt still shows the version that was true when the answer was given.
    """
    wanted = set(ids)
    return {m["id"]: m for m in current_memories()["memories"] if m["id"] in wanted}


def spoken_time(iso: str) -> str:
    """'2026-10-10T14:30:00-04:00' -> 'Saturday, October 10 at 2:30 PM', in the patient's timezone."""
    at = datetime.fromisoformat(iso).astimezone(ZoneInfo(os.getenv("TIMEZONE", "America/New_York")))
    return f"{at:%A, %B} {at.day} at {at:%I:%M %p}".replace(" 0", " ")


def is_timestamp(value) -> bool:
    if not isinstance(value, str) or "T" not in value:
        return False
    try:
        datetime.fromisoformat(value)
        return True
    except ValueError:
        return False
