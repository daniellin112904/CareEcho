"""Family messages: text a family member wrote, spoken once by text to speech in their cloned voice.

The message records go through app/store.py (the family_messages table in Tiger Data). The MP3
for each is cached here on disk under backend/data/ (git-ignored), so audio is generated once
and replays work offline.
"""

import uuid
from datetime import datetime, timedelta
from pathlib import Path

from app import store
from app.memory.context import spoken_day
from app.memory.extraction import MEDICATION
from app.store import DATA_DIR, PATIENT_ID

AUDIO_DIR = DATA_DIR / "family_audio"

NO_MESSAGES = "NO_MESSAGES: no family messages this week. Say there are no new messages; never invent one."
# Older messages ("Happy birthday!") would confuse more than help
AGENT_WINDOW = timedelta(days=7)
AGENT_LIMIT = 5


def list_messages() -> list[dict]:
    """Newest first."""
    return store.list_family_messages(PATIENT_ID)


def for_agent(messages: list[dict], now: datetime) -> str:
    """What the agent's get_family_messages tool returns: the newest messages from the last week,
    as quotes. Messages mentioning medicine are left out: the agent never talks about medicine,
    and staff write those on the Family messages page, not as memories."""
    recent = [m for m in messages
              if datetime.fromisoformat(m["created_at"]) >= now - AGENT_WINDOW and not MEDICATION.search(m["text"])]
    lines = [f'- From {m["from_name"]}, {spoken_day(m["created_at"])}: "{m["text"]}"' for m in recent[:AGENT_LIMIT]]
    return "\n".join(lines) or NO_MESSAGES


def add_message(from_name: str, voice_id: str, text: str, audio: bytes) -> dict:
    message = store.add_family_message(from_name, voice_id, text)
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    audio_path(message["id"]).write_bytes(audio)
    return message


def delete_message(message_id: str) -> bool:
    try:
        path = audio_path(message_id)
    except ValueError:
        return False
    if not store.delete_family_message(message_id):
        return False
    path.unlink(missing_ok=True)
    return True


def delete_messages_for_voice(voice_id: str):
    """A deleted voice takes its messages with it: no audio outlives the consent behind it."""
    for m in list_messages():
        if m["voice_id"] == voice_id:
            delete_message(m["id"])


def audio_path(message_id: str) -> Path:
    """Resolved path to the message's MP3 under family_audio. Raises ValueError if the ID is unsafe.

    The file is named by the ID's 32 hex digits, so the database's dashed UUIDs and the hex IDs
    of the offline JSON mode find the same file. Only a real UUID gets this far, which rules out
    path separators and ".." before any path is built.
    """
    try:
        name = uuid.UUID(message_id).hex
    except (ValueError, TypeError, AttributeError):
        raise ValueError("invalid message id")
    path = (AUDIO_DIR / f"{name}.mp3").resolve()
    root = AUDIO_DIR.resolve()
    if not path.is_relative_to(root):
        raise ValueError("invalid message id")
    return path
