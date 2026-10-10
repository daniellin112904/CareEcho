"""What happens during conversations: questions answered, things the patient said, and alerts.

The records are saved through app/store.py, in Tiger Data (JSON files only without a
database). Answers go to the interactions hypertable, which feeds the dashboard's hourly counts.
"""

import re
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app import store
from app.auth import require_staff
from app.memory.context import is_timestamp
from app.store import PATIENT_ID

router = APIRouter(tags=["events"])
staff_router = APIRouter(tags=["events"], dependencies=[Depends(require_staff)])


# Patient side: called by the voice agent's client tools in the browser (the patient page has no login)


class Interaction(BaseModel):
    conversation_id: str | None = Field(default=None, max_length=100)
    topic: str = Field(max_length=100)
    question: str = Field(max_length=1000)
    answer: str = Field(max_length=2000)
    memory_ids: list[str] = Field(default=[], max_length=50)
    answered: bool = True
    latency_ms: int | None = None
    # The patient may need help (an urgent alert went out during this turn)
    urgent: bool = False


class Statement(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    kind: Literal["medication", "meal", "activity", "feeling", "other"] = "other"


class NewAlert(BaseModel):
    kind: Literal["missing_info", "self_reported_med", "help_requested"]
    message: str = Field(min_length=1, max_length=500)


@router.post("/interactions")
def log_interaction(body: Interaction):
    """One answer the agent gave. Its topic is set here, by code, not by the AI: the dashboard
    counts repeated questions by topic, and the agent's own words for it vary ("pickup time",
    "leaving", "Anna"), which would split one question into many."""
    fields = body.model_dump(exclude={"urgent"})
    return store.add_interaction(**{**fields, "topic": topic_for(body)})


def topic_for(body: Interaction) -> str:
    """In order: "Asked for help" for an emergency; "Asked the care team" when the answer was
    to ask them; the memory the answer used ("Dentist appointment", see receipt below);
    otherwise the agent's own topic, or "Other"."""
    if body.urgent:
        return "Asked for help"
    if not body.answered:
        return "Asked the care team"
    sources = receipt(body.model_dump(), store.memories_by_id(body.memory_ids))["sources"]
    if sources:
        return sources[0]["summary"][:100]
    return body.topic.strip() or "Other"


@router.post("/patient/statements")
def log_statement(body: Statement):
    """Something the patient said they did. Stored as self-reported, never as a fact."""
    row = store.add_statement(body.text, body.kind)
    if body.kind == "medication":
        # Staff need to know: a self-report alone must never count as a confirmed dose
        store.add_alert("self_reported_med", f'Said: "{body.text}" (not verified)')
    return row


@router.post("/alerts")
def raise_alert(body: NewAlert):
    return store.add_alert(body.kind, body.message)


@router.get("/alerts/{alert_id}/status")
def alert_status(alert_id: str):
    """Lets the patient screen clear "Your care team has been told" once staff resolve it.
    Only whether it's resolved: the ID is unguessable and the message stays staff-only."""
    match = store.get_alert(alert_id)
    if not match:
        raise HTTPException(404, "That alert no longer exists")
    return {"resolved": match["resolved"]}


# Staff side


@staff_router.get("/alerts")
def list_alerts():
    """Open alerts first, newest first within each group."""
    return {"alerts": store.list_alerts(PATIENT_ID)}


@staff_router.post("/alerts/{alert_id}/resolve", status_code=204)
def resolve_alert(alert_id: str):
    if not store.resolve_alert(alert_id):
        raise HTTPException(404, "That alert no longer exists")


@staff_router.get("/dashboard")
def dashboard():
    """What the care team should see at a glance: what the patient keeps asking about (today and
    per hour, from the TimescaleDB aggregate), open alerts by kind, and what the patient said
    they did today."""
    return store.dashboard(PATIENT_ID, datetime.now(timezone.utc))


@staff_router.get("/interactions")
def list_interactions():
    """Answers, newest first, each with a receipt: the memories it was based on."""
    rows = store.list_interactions(PATIENT_ID)
    memories = store.memories_by_id([i for r in rows for i in r["memory_ids"]])
    return {"interactions": [{**r, **receipt(r, memories)} for r in rows]}


# Words too common to show that an answer used a memory
_COMMON = {"the", "and", "you", "your", "for", "with", "are", "was", "this", "that", "will", "her", "his", "she"}


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]+", text.lower()) if len(w) >= 3 and w not in _COMMON}


def receipt(row: dict, memories: dict[str, dict]) -> dict:
    """Which looked-up memories the answer actually used.

    get_memories returns every current memory, so the IDs logged with an answer are
    everything the agent saw. A memory counts as a source when its key words (summary and
    names, like "dentist" or "Anna") appear in the question or answer.
    """
    said = _words(f"{row['question']} {row['answer']}")
    sources = []
    for memory_id in row["memory_ids"]:
        m = memories.get(memory_id)
        if not m:
            continue
        values = [v for v in (m.get("details") or {}).values() if isinstance(v, str) and not is_timestamp(v)]
        if _words(" ".join([m["summary"], *values])) & said:
            keys = ("id", "summary", "status", "source", "source_quote", "event_at", "confirmed_at")
            sources.append({k: m.get(k) for k in keys})
    return {"sources": sources, "checked": len(row["memory_ids"])}
