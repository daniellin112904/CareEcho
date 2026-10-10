"""What the voice companion knows about the patient.

The agent looks facts up live with its get_memories tool (GET /voice/facts, see
app/voice/routes.py), so a plan confirmed mid-conversation is picked up on the next question.
Memories come from app/store.py, so once the memory system returns real data there, the
agent uses it automatically.
"""

import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app import store


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
    return facts_from(store.current_memories(patient_id), datetime.now(timezone.utc))


def facts_from(memories: list[dict], now: datetime) -> dict:
    """build_facts for given memories at a given time (the safety tests use a fixed time)."""
    cutoff = now - EXPIRED_AFTER
    today = now.astimezone(_tz()).date()
    lines, ids = [], []
    for m in memories:
        if m["status"] not in ("confirmed", "tentative"):
            continue
        if m.get("event_at") and _ended(m, cutoff, today):
            continue
        line = m["summary"]
        if m.get("event_at"):
            # An all-day plan has no time, so none is said ("Saturday, October 17")
            line += f", {spoken_day(m['event_at']) if m.get('all_day') else spoken_time(m['event_at'])}"
        # Not source_quote: words like "tomorrow" in it go stale the next day
        for key, value in (m.get("details") or {}).items():
            line += f"; {key.replace('_', ' ')}: {spoken_time(value) if is_timestamp(value) else value}"
        if m["status"] == "tentative":
            line += " (TENTATIVE: say it isn't certain yet)"
        lines.append(f"- {line}")
        ids.append(m["id"])
    return {"facts": "\n".join(lines) or NO_MEMORY, "memory_ids": ids}


def _ended(memory: dict, cutoff: datetime, today) -> bool:
    """A timed event ends two hours after it starts; an all-day one when its day is over."""
    at = datetime.fromisoformat(memory["event_at"])
    if memory.get("all_day"):
        return at.astimezone(_tz()).date() < today
    return at < cutoff


def _tz() -> ZoneInfo:
    return ZoneInfo(os.getenv("TIMEZONE", "America/New_York"))


def spoken_time(iso: str) -> str:
    """'2026-10-10T14:30:00-04:00' -> 'Saturday, October 10 at 2:30 PM', in the patient's timezone."""
    at = datetime.fromisoformat(iso).astimezone(_tz())
    return f"{at:%A, %B} {at.day} at {at:%I:%M %p}".replace(" 0", " ")


def spoken_day(iso: str) -> str:
    """'2026-10-17T00:00:00-04:00' -> 'Saturday, October 17': for all-day plans, which have no time."""
    at = datetime.fromisoformat(iso).astimezone(_tz())
    return f"{at:%A, %B} {at.day}"


def is_timestamp(value) -> bool:
    if not isinstance(value, str) or "T" not in value:
        return False
    try:
        datetime.fromisoformat(value)
        return True
    except ValueError:
        return False
