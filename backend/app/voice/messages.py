"""Family messages: text a family member wrote, spoken once by text to speech in their cloned voice.

The message records go through app/store.py (JSON today, a database table later). The MP3 for
each is cached here on disk under backend/data/ (git-ignored), so audio is generated once and
replays work offline.
"""

import re
from pathlib import Path

from app import store
from app.store import DATA_DIR, PATIENT_ID

AUDIO_DIR = DATA_DIR / "family_audio"

# Same shape as uuid.uuid4().hex — rejects path separators and ".." before building paths
_MESSAGE_ID = re.compile(r"^[0-9a-f]{32}$")


def list_messages() -> list[dict]:
    """Newest first."""
    return store.list_family_messages(PATIENT_ID)


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
    """Resolved path to `{id}.mp3` under family_audio. Raises ValueError if id is unsafe."""
    if not _MESSAGE_ID.fullmatch(message_id):
        raise ValueError("invalid message id")
    path = (AUDIO_DIR / f"{message_id}.mp3").resolve()
    root = AUDIO_DIR.resolve()
    if not path.is_relative_to(root):
        raise ValueError("invalid message id")
    return path
