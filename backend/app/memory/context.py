"""What the voice companion knows about the patient at the start of each conversation.

Placeholder until the memory system lands: replace the bodies of these two functions
and the agent picks up the real data automatically (it's sent as dynamic variables
in GET /voice/session, see app/voice/routes.py).
"""

import os
from datetime import datetime
from zoneinfo import ZoneInfo

from app.memory.routes import current_memories

PATIENT_ID = "demo"


def get_patient_name(patient_id: str) -> str:
    return "Rose"


def build_memory_context(patient_id: str) -> str:
    """Plain-text facts for the agent prompt. Only confirmed, unexpired memories belong here."""
    tz = ZoneInfo(os.getenv("TIMEZONE", "America/New_York"))
    lines = []
    for m in current_memories()["memories"]:
        line = m["summary"]
        if m.get("event_at"):
            at = datetime.fromisoformat(m["event_at"]).astimezone(tz)
            line += f", {at:%A, %B} {at.day} at {at:%I:%M %p}".replace(" 0", " ")
        # Not source_quote: words like "tomorrow" in it go stale the next day
        for key, value in (m.get("details") or {}).items():
            line += f"; {key}: {value}"
        lines.append(f"- {line}")
    return "\n".join(lines) or "- Nothing has been confirmed yet."
