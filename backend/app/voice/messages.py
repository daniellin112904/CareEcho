"""Family messages: text a family member wrote, spoken once by text to speech in their cloned voice.

Stored as a JSON file plus one MP3 per message under backend/data/ (git-ignored), so the
audio is generated once and replays work offline. Swap for a database table later.
"""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
AUDIO_DIR = DATA_DIR / "family_audio"
INDEX = DATA_DIR / "family_messages.json"


def list_messages() -> list[dict]:
    """Newest first."""
    if not INDEX.exists():
        return []
    return json.loads(INDEX.read_text(encoding="utf-8"))


def _save(messages: list[dict]):
    DATA_DIR.mkdir(exist_ok=True)
    INDEX.write_text(json.dumps(messages, indent=2), encoding="utf-8")


def add_message(from_name: str, voice_id: str, text: str, audio: bytes) -> dict:
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    message = {
        "id": uuid.uuid4().hex,
        "from_name": from_name,
        "voice_id": voice_id,
        "text": text,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    audio_path(message["id"]).write_bytes(audio)
    _save([message, *list_messages()])
    return message


def delete_message(message_id: str) -> bool:
    messages = list_messages()
    kept = [m for m in messages if m["id"] != message_id]
    if len(kept) == len(messages):
        return False
    _save(kept)
    audio_path(message_id).unlink(missing_ok=True)
    return True


def delete_messages_for_voice(voice_id: str):
    """A deleted voice takes its messages with it: no audio outlives the consent behind it."""
    for m in list_messages():
        if m["voice_id"] == voice_id:
            delete_message(m["id"])


def audio_path(message_id: str) -> Path:
    # IDs are uuid hex, so they can't contain path separators
    return AUDIO_DIR / f"{message_id}.mp3"
