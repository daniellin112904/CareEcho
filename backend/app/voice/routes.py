import os
import threading
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from elevenlabs.client import ElevenLabs
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.auth import require_staff
from app.memory.context import build_facts
from app.store import PATIENT_ID, patient_name
from app.voice import messages
from app.voice.agent import DEFAULT_VOICE_ID

router = APIRouter(tags=["voice"])
staff_router = APIRouter(tags=["voice"], dependencies=[Depends(require_staff)])

eleven = ElevenLabs(api_key=os.environ["ELEVENLABS_API_KEY"])

# Cloned voices are tagged with this label when staff create them with consent
CLONE_LABEL = {"app": "vela"}
_voice_checked = False
_voice_check_lock = threading.Lock()


def agent_id() -> str:
    value = os.getenv("ELEVENLABS_AGENT_ID")
    if not value:
        raise HTTPException(503, "ELEVENLABS_AGENT_ID is not set. Run scripts/create_agent.py.")
    return value


def ensure_neutral_voice():
    """The live companion always speaks in the stock voice, never a family member's clone.

    Nothing in the app can change the agent's voice any more; this resets agents switched
    before that rule (or by hand in the ElevenLabs dashboard). Checked once per server start.
    """
    global _voice_checked
    if _voice_checked:
        return
    with _voice_check_lock:
        if _voice_checked:
            return
        tts = eleven.conversational_ai.agents.get(agent_id()).conversation_config.tts
        if tts.voice_id != DEFAULT_VOICE_ID:
            eleven.conversational_ai.agents.update(
                agent_id(), conversation_config={"tts": {"voice_id": DEFAULT_VOICE_ID}}
            )
        _voice_checked = True


def family_voices():
    cloned = eleven.voices.search(category="cloned", page_size=100).voices
    return [v for v in cloned if (v.labels or {}).get("app") == CLONE_LABEL["app"]]


@router.get("/voice/session")
def start_session():
    """Everything the patient page needs to start a conversation."""
    ensure_neutral_voice()
    now = datetime.now(ZoneInfo(os.getenv("TIMEZONE", "America/New_York")))
    token = eleven.conversational_ai.conversations.get_webrtc_token(agent_id=agent_id()).token
    return {
        "token": token,
        "dynamic_variables": {
            "patient_name": patient_name(PATIENT_ID),
            "today": f"{now:%A, %B} {now.day}, {now.year}",
            "now": now.strftime("%I:%M %p").lstrip("0"),
        },
    }


@router.get("/voice/facts")
def facts():
    """What the agent's get_memories tool returns: every current memory, see build_facts."""
    return build_facts(PATIENT_ID)


@router.get("/voice/family-messages")
def family_messages_for_agent():
    """What the agent's get_family_messages tool returns: this week's family messages as quotes,
    without any that mention medicine (see messages.for_agent)."""
    return {"messages": messages.for_agent(messages.list_messages(), datetime.now(timezone.utc))}


# Family voices: cloned with consent, used only to read messages family wrote


@staff_router.get("/voice/voices")
def list_voices():
    return {"voices": [{"voice_id": v.voice_id, "name": v.name} for v in family_voices()]}


@staff_router.post("/voice/voices")
def clone_voice(name: str = Form(...), file: UploadFile = File(...)):
    voice = eleven.voices.ivc.create(
        name=name,
        files=[(file.filename, file.file, file.content_type)],
        labels=CLONE_LABEL,
    )
    return {"voice_id": voice.voice_id, "name": name}


@staff_router.delete("/voice/voices/{voice_id}", status_code=204)
def delete_voice(voice_id: str):
    if voice_id == DEFAULT_VOICE_ID:
        raise HTTPException(400, "The companion voice can't be deleted")
    messages.delete_messages_for_voice(voice_id)
    eleven.voices.delete(voice_id)


# Family messages


class NewMessage(BaseModel):
    voice_id: str
    text: str = Field(min_length=1, max_length=500)


@staff_router.get("/family-messages")
def list_family_messages():
    return {"messages": messages.list_messages()}


@staff_router.post("/family-messages")
def create_family_message(body: NewMessage):
    voice = next((v for v in family_voices() if v.voice_id == body.voice_id), None)
    if not voice:
        raise HTTPException(400, "Pick one of the family voices on this page")
    text = body.text.strip()
    audio = b"".join(
        eleven.text_to_speech.convert(
            voice.voice_id,
            text=text,
            model_id="eleven_multilingual_v2",
            output_format="mp3_44100_128",
        )
    )
    # "Anna, daughter" -> "Anna", so the patient screen says "Message from Anna"
    from_name = voice.name.split(",")[0].strip() or voice.name
    return messages.add_message(from_name, voice.voice_id, text, audio)


@staff_router.delete("/family-messages/{message_id}", status_code=204)
def delete_family_message(message_id: str):
    if not messages.delete_message(message_id):
        raise HTTPException(404, "That message no longer exists")


@router.get("/family-messages/latest")
def latest_family_message():
    """The newest message, for the patient screen (which has no login)."""
    latest = next(iter(messages.list_messages()), None)
    return {"message": latest and {k: latest[k] for k in ("id", "from_name", "text", "created_at")}}


@router.get("/family-messages/{message_id}/audio")
def family_message_audio(message_id: str):
    try:
        path = messages.audio_path(message_id)
    except ValueError:
        raise HTTPException(404, "That message no longer exists")
    if not path.exists():
        raise HTTPException(404, "That message no longer exists")
    return FileResponse(path, media_type="audio/mpeg")
