"""Reminders: Vela tells the patient about an upcoming plan before it happens.

The sentences are built from confirmed memories by code, not by the AI, so a reminder can
only say what a caregiver confirmed. They're spoken in the companion's own neutral voice
(never a family clone), generated once by text to speech and cached under backend/data/.

Each confirmed upcoming plan gets two reminders: 30 minutes before, and 5 minutes before.
The time that matters is the pickup if there is one ("Anna is picking you up at 2:30"),
otherwise the event itself. Staff can also send one right away from the Memories page.

The patient can also ask for her own ("Remind me at 5 to water my tomato plants"): the agent's
set_reminder tool posts what she said, code works out the exact time, and the reminder is said
once, at that time. Those are stored as self-reported memories, never told to the agent as facts.
"""

import hashlib
import os
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

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
    """'at 2:30 this afternoon', 'tomorrow at 9:00 in the morning', or 'on Monday at ...'. Each
    brings its own "at"/"on", so the sentence never says "at tomorrow at"."""
    at, now = at.astimezone(_tz()), now.astimezone(_tz())
    clock = f"{at.hour % 12 or 12}:{at.minute:02d}"
    part = "morning" if at.hour < 12 else "afternoon" if at.hour < 17 else "evening"
    if at.date() == now.date():
        return f"at {clock} this {part}"
    if at.date() == (now + timedelta(days=1)).date():
        return f"tomorrow at {clock} in the {part}"
    return f"on {at:%A} at {clock} in the {part}"


def _plan(memory: dict):
    """(when it matters, who's coming or None, what it's for) for a confirmed upcoming plan."""
    if memory["status"] != "confirmed" or not memory.get("event_at"):
        return None
    details = memory.get("details") or {}
    who = details.get("who") if isinstance(details.get("who"), str) else None
    pickup = details.get("pickup_at")
    # An all-day plan ("Anna might visit Saturday") has no time to remind at, unless a pickup has one
    if memory.get("all_day") and not (who and isinstance(pickup, str)):
        return None
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
        f"{who} is picking you up {_spoken(at, now)} for your {what}"
        if who
        else f"your {what} is {_spoken(at, now)}"
    )
    soon = {"30min": " That's in about 30 minutes.", "5min": " That's in about five minutes."}.get(lead, "")
    return f"{name}, a reminder: {main}.{soon}"


def asked_sentence(name: str, task: str) -> str:
    """What's said for a reminder the patient asked for, in her words said back to her."""
    return f"{name}, you asked me to remind you to {task}."


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
    # Ones the patient asked for: once, at the time she gave. The "-at" ID keeps them apart
    # from plan reminders in the patient screen's record of what it already played.
    asked = [r for r in store.patient_reminders(PATIENT_ID, since=now - GRACE)
             if datetime.fromisoformat(r["event_at"]) <= now + timedelta(hours=12)]
    if asked:
        name = store.patient_name(PATIENT_ID)
        out += [{"id": f"{r['id']}-at", "at": r["event_at"], "text": asked_sentence(name, r["summary"]),
                 "memory_id": r["id"]} for r in asked]
    # By time, not text: the times can be written with different offsets
    return sorted(out, key=lambda r: datetime.fromisoformat(r["at"]))


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


# Reminders the patient asks for, through the agent's set_reminder tool. The model only passes a
# clock time or a number of minutes; the exact moment is worked out here, with TIMEZONE.


class AskedReminder(BaseModel):
    # Loosely typed on purpose: every problem gets one plain 422 sentence (below), never a list
    task: str = ""
    said: str = ""
    time: str | None = None
    day: str | None = None
    in_minutes: int | str | None = None


_CLOCK = re.compile(r"(\d{1,2}):(\d{2})")


def resolve_at(now: datetime, time: str | None = None, day: str | None = None,
               in_minutes: int | str | None = None) -> datetime:
    """When to say it. Exactly one of a clock time ("17:00", with day "today", "tomorrow", or
    none: the next time it comes) or a number of minutes from now (1 to 1440). Raises
    ValueError with a sentence for the agent's handler when there's no clear time."""
    time, day = (time or "").strip(), (day or "").strip().lower()
    minutes = str(in_minutes).strip() if in_minutes is not None else ""
    if not time and not minutes:
        raise ValueError("No time was given. Ask what time they would like.")
    if time and minutes:
        raise ValueError("Give either a clock time or a number of minutes, not both.")
    if minutes:
        if not minutes.isdigit() or not 1 <= int(minutes) <= 1440:
            raise ValueError("in_minutes must be a whole number from 1 to 1440.")
        return now + timedelta(minutes=int(minutes))
    match = _CLOCK.fullmatch(time)
    if not match or int(match[1]) > 23 or int(match[2]) > 59:
        raise ValueError("time must be a 24 hour clock time, like 17:00.")
    if day not in ("", "today", "tomorrow"):
        raise ValueError("day must be 'today', 'tomorrow', or empty.")
    tz = _tz()
    local = now.astimezone(tz)

    def on(days: int) -> datetime:
        # Built from the date, so a day that changes the clocks still gets the right offset
        date = local.date() + timedelta(days=days)
        return datetime(date.year, date.month, date.day, int(match[1]), int(match[2]), tzinfo=tz)

    if day == "tomorrow":
        return on(1)
    if on(0) > now:
        return on(0)
    if day == "today":
        raise ValueError(f"{time} has already passed today. Ask what time they would like.")
    return on(1)


def when_words(at: datetime, now: datetime, in_minutes: int | str | None = None) -> str:
    """What the agent says back: "in about 2 minutes" for a short wait, otherwise the same words
    as the plan reminders ("at 5:00 this evening", "tomorrow at 9:00 in the morning")."""
    minutes = str(in_minutes).strip() if in_minutes is not None else ""
    if minutes.isdigit() and int(minutes) <= 60:
        return "in about a minute" if int(minutes) == 1 else f"in about {int(minutes)} minutes"
    return _spoken(at, now)


@router.post("/patient/reminders")
def set_patient_reminder(body: AskedReminder):
    """A reminder the patient asked the agent for (the patient page has no login, like
    /patient/statements). Never saved without a clear time: 422 tells the agent to ask."""
    # Said back as "remind you to <task>", so a leading "to" or a final period would be doubled
    task = re.sub(r"^to\s+", "", " ".join(body.task.split()), flags=re.IGNORECASE).rstrip(".")
    if not task:
        raise HTTPException(422, "No task was given. Ask what they would like to be reminded of.")
    if len(task) > 200:
        raise HTTPException(422, "The task is too long. Keep it to a few words.")
    now = datetime.now(timezone.utc)
    try:
        at = resolve_at(now, body.time, body.day, body.in_minutes)
    except ValueError as err:
        raise HTTPException(422, str(err))
    said = " ".join(body.said.split())[:500] or task
    row = store.add_patient_reminder(PATIENT_ID, task, said, at)
    return {**row, "when_words": when_words(at, now, body.in_minutes)}


@staff_router.get("/patient/reminders")
def list_patient_reminders():
    """Upcoming reminders the patient asked for, soonest first (cancelled ones left out)."""
    return {"reminders": store.patient_reminders(PATIENT_ID, datetime.now(timezone.utc))}


@staff_router.post("/patient/reminders/{reminder_id}/cancel")
def cancel_patient_reminder(reminder_id: str):
    """Kept, as cancelled, and never said. Only for reminders the patient asked for: plans keep
    their own cancel (/memories/{id}/cancel)."""
    try:
        row = store.cancel_patient_reminder(PATIENT_ID, reminder_id)
    except store.Conflict as err:
        raise HTTPException(409, str(err))
    if row is None:
        raise HTTPException(404, "That reminder doesn't exist")
    return row
