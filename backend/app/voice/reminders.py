"""Reminders: Vela tells the patient about an upcoming plan before it happens.

The sentences are built from confirmed memories by code, not by the AI, so a reminder can
only say what a caregiver confirmed. They're spoken in the companion's own neutral voice
(never a family clone), generated once by text to speech and cached under backend/data/.

Each confirmed upcoming plan gets two reminders: 30 minutes before, and 5 minutes before.
The time that matters is the pickup if there is one ("Anna is picking you up at 2:30"),
otherwise the event itself. Staff can also send one right away from the Memories page.
"""

import hashlib
import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app import store
from app.auth import require_staff
from app.store import DATA_DIR, PATIENT_ID
from app.voice.agent import DEFAULT_VOICE_ID

AUDIO_DIR = DATA_DIR / "reminder_audio"

LEADS = [(timedelta(minutes=30), "30min"), (timedelta(minutes=5), "5min")]
# A reminder still plays if the patient screen catches it up to this late (e.g. after a reload)
GRACE = timedelta(minutes=10)

router = APIRouter(tags=["reminders"])
staff_router = APIRouter(tags=["reminders"], dependencies=[Depends(require_staff)])


def _tz() -> ZoneInfo:
    return ZoneInfo(os.getenv("TIMEZONE", "America/New_York"))


def _spoken(at: datetime, now: datetime) -> str:
    """'2:30 this afternoon', or 'tomorrow at 9:00 in the morning'."""
    at, now = at.astimezone(_tz()), now.astimezone(_tz())
    clock = f"{at.hour % 12 or 12}:{at.minute:02d}"
    part = "morning" if at.hour < 12 else "afternoon" if at.hour < 17 else "evening"
    if at.date() == now.date():
        return f"{clock} this {part}"
    if at.date() == (now + timedelta(days=1)).date():
        return f"tomorrow at {clock} in the {part}"
    return f"{at:%A} at {clock} in the {part}"


def _plan(memory: dict):
    """(when it matters, who's coming or None, what it's for) for a confirmed upcoming plan."""
    if memory["status"] != "confirmed" or not memory.get("event_at"):
        return None
    details = memory.get("details") or {}
    who = details.get("who") if isinstance(details.get("who"), str) else None
    pickup = details.get("pickup_at")
    at = datetime.fromisoformat(pickup if who and isinstance(pickup, str) else memory["event_at"])
    summary = memory["summary"]
    return at, (who if pickup else None), summary[:1].lower() + summary[1:]


def _sentence(memory: dict, lead: str, now: datetime) -> str | None:
    plan = _plan(memory)
    if not plan:
        return None
    at, who, what = plan
    name = store.patient_name(PATIENT_ID)
    if who and lead == "5min":
        return f"{name}, {who} will be here in about five minutes to pick you up for your {what}."
    main = (
        f"{who} is picking you up at {_spoken(at, now)} for your {what}"
        if who
        else f"your {what} is at {_spoken(at, now)}"
    )
    soon = {"30min": " That's in about 30 minutes.", "5min": " That's in about five minutes."}.get(lead, "")
    return f"{name}, a reminder: {main}.{soon}"


def due_reminders(now: datetime | None = None) -> list[dict]:
    """Reminders due within the next 12 hours, or due in the last few minutes."""
    now = now or datetime.now(timezone.utc)
    memories = {m["id"]: m for m in store.current_memories(PATIENT_ID)}
    out = []
    for memory in memories.values():
        plan = _plan(memory)
        if not plan:
            continue
        for lead, kind in LEADS:
            at = plan[0] - lead
            if now - GRACE <= at <= now + timedelta(hours=12):
                text = _sentence(memory, kind, now)
                out.append({"id": f"{memory['id']}-{kind}", "at": at.isoformat(), "text": text, "memory_id": memory["id"]})
    for sent in store.recent_sent_reminders(PATIENT_ID, since=now - GRACE):
        if sent["memory_id"] in memories:
            text = _sentence(memories[sent["memory_id"]], "now", now)
            if text:
                out.append({**sent, "text": text})
    return sorted(out, key=lambda r: r["at"])


@router.get("/reminders/upcoming")
def upcoming():
    return {"reminders": due_reminders()}


@router.get("/reminders/{reminder_id}/audio")
def reminder_audio(reminder_id: str):
    """The reminder in the companion's own voice, generated once per sentence."""
    from app.voice.routes import eleven  # here, not at the top: routes needs the API key at import

    reminder = next((r for r in due_reminders() if r["id"] == reminder_id), None)
    if not reminder:
        raise HTTPException(404, "That reminder isn't due any more")
    path = AUDIO_DIR / f"{hashlib.sha1(reminder['text'].encode()).hexdigest()}.mp3"
    if not path.exists():
        audio = b"".join(
            eleven.text_to_speech.convert(
                DEFAULT_VOICE_ID, text=reminder["text"], model_id="eleven_flash_v2", output_format="mp3_44100_128"
            )
        )
        AUDIO_DIR.mkdir(parents=True, exist_ok=True)
        path.write_bytes(audio)
    return FileResponse(path, media_type="audio/mpeg")


class RemindNow(BaseModel):
    memory_id: str


@staff_router.post("/reminders/now")
def remind_now(body: RemindNow):
    """Staff send a reminder right away. The patient screen picks it up within 15 seconds."""
    memory = next((m for m in store.current_memories(PATIENT_ID) if m["id"] == body.memory_id), None)
    if not memory or not _plan(memory):
        raise HTTPException(400, "Only a confirmed plan with a time can be sent as a reminder")
    sent = store.add_sent_reminder(body.memory_id)
    return {**sent, "text": _sentence(memory, "now", datetime.now(timezone.utc))}
