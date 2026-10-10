from datetime import datetime, timezone
from typing import Literal

import psycopg
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app import db, store
from app.auth import require_staff
from app.memory import extraction
from app.store import PATIENT_ID

router = APIRouter(tags=["memory"])
staff_router = APIRouter(tags=["memory"], dependencies=[Depends(require_staff)])


@router.get("/memories/current")
def current_memories(topic: str | None = None):
    """Confirmed and tentative memories, for the patient screen (which has no login).

    Never pending, rejected, or superseded ones: those stay staff-only. `topic` is accepted
    but ignored, like the agent's lookups (see build_facts in app/memory/context.py).
    """
    return {"memories": store.current_memories(PATIENT_ID)}


class Transcript(BaseModel):
    transcript: str = Field(min_length=1, max_length=4000)
    # Typed on the staff page today; a listening session (speech to text) sends caregiver_session
    source: Literal["caregiver_typed", "caregiver_session"] = "caregiver_typed"


@staff_router.post("/sessions/transcript", status_code=201)
def add_transcript(body: Transcript):
    """What a caregiver said, turned into pending memories for staff to confirm or reject.

    The words are saved first, so they're kept even if Gemini fails. Pending memories are
    never spoken (see app/memory/extraction.py). Returns the new pending memories, each with
    warnings worth checking before confirming, and anything left out with the reason.
    """
    if not db.enabled():
        raise HTTPException(503, "Extraction needs the database, and DATABASE_URL isn't set")
    text = body.transcript.strip()
    if not text:
        raise HTTPException(422, "The transcript is empty")
    now = datetime.now(timezone.utc)
    try:
        session = store.add_session(PATIENT_ID, text)
    except psycopg.errors.ForeignKeyViolation:
        raise HTTPException(503, "The demo patient isn't in the database yet. Run scripts/seed_demo.py.")

    try:
        # No database connection is held while Gemini thinks: the pool only has a few
        result = extraction.extract(text, now, store.current_memories(PATIENT_ID), store.patient_name(PATIENT_ID))
    except extraction.ExtractionError as err:
        store.finish_session(session["id"], PATIENT_ID, body.source,
                             {"now": now.isoformat(), "error": str(err), "raw": err.raw,
                              "retry_after": err.retry_after, "daily": err.daily}, [])
        if err.retry_after is not None:
            wait = extraction.wait_words(err.retry_after)
            if err.daily:
                cap = f"daily limit of {err.limit} requests" if err.limit else "daily request limit"
                message = f"Gemini's {cap} was reached. The words were saved; try again in {wait}."
            else:
                message = f"Gemini is busy right now. The words were saved; try again in {wait}."
            raise HTTPException(503, message, headers={"Retry-After": str(err.retry_after)})
        raise HTTPException(502, f"Gemini: {err}. The words were saved; try again.")

    record = {
        "model": result["model"],
        "model_version": result["model_version"],
        "now": now.isoformat(),
        "raw": result["raw"],
        "kept": [{"summary": c["summary"], "warnings": c["warnings"]} for c in result["candidates"]],
        "dropped": result["dropped"],
    }
    rows = store.finish_session(session["id"], PATIENT_ID, body.source, record, result["candidates"])
    return {
        "session_id": session["id"],
        "candidates": [{**row, "warnings": c["warnings"]} for row, c in zip(rows, result["candidates"])],
        "dropped": result["dropped"],
    }
