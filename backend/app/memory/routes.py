from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app import db, store
from app.auth import require_staff
from app.memory import extraction, life_story
from app.memory.demo import PATIENT_NAME, demo_memories
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


# Review: staff decide what Vela may say. These read PATIENT_ID when called (not at import), so
# the review tests can point them at a test patient.


def _needs_database():
    if not db.enabled():
        raise HTTPException(503, "Reviewing memories needs the database, and DATABASE_URL isn't set")


def _review(action, memory_id: UUID, *args):
    _needs_database()
    try:
        row = action(PATIENT_ID, str(memory_id), *args)
    except store.Conflict as err:
        raise HTTPException(409, str(err))
    if row is None:
        raise HTTPException(404, "That memory doesn't exist")
    return row


@staff_router.get("/sessions")
def list_sessions():
    """The 20 latest caregiver notes, newest first, each with what extraction made of it: an
    error (the words were still saved), what it dropped and why, and the memories it made with
    their status now."""
    _needs_database()
    return {"sessions": store.list_sessions(PATIENT_ID)}


@staff_router.get("/memories/pending")
def pending_memories():
    """Memories waiting for a caregiver, oldest first, with extraction's warnings, the memory
    each update would replace, and whether that memory was already changed (stale)."""
    _needs_database()
    return {"pending": store.pending_memories(PATIENT_ID)}


class Confirmation(BaseModel):
    # The one thing staff may change before confirming; anything else wrong: reject and say it again
    certainty: Literal["definite", "tentative"] | None = None


@staff_router.post("/memories/{memory_id}/confirm")
def confirm_memory(memory_id: UUID, body: Confirmation | None = None):
    """From now on Vela may say it: the agent's next lookup, the patient screen and reminders
    within 15 seconds. An update replaces the version it changes at the same moment."""
    return _review(store.confirm_memory, memory_id, body.certainty if body else None)


@staff_router.post("/memories/{memory_id}/reject")
def reject_memory(memory_id: UUID):
    """A pending memory was wrong. It's kept, as rejected, and never spoken."""
    return _review(store.reject_memory, memory_id)


@staff_router.post("/memories/{memory_id}/cancel")
def cancel_memory(memory_id: UUID):
    """A current plan was cancelled. It's kept for receipts of past answers, never spoken again."""
    return _review(store.cancel_memory, memory_id)


@staff_router.get("/memories/{memory_id}/history")
def memory_history(memory_id: UUID):
    """Every version of a memory, oldest first, so the caregiver can see what changed and when:
    the versions it replaced, itself, and the versions that replaced it."""
    _needs_database()
    versions = store.memory_history(PATIENT_ID, str(memory_id))
    if versions is None:
        raise HTTPException(404, "That memory doesn't exist")
    return {"versions": versions}


@staff_router.post("/demo/reset")
def reset_demo():
    """Back to a known demo: Rose, her memories timed from now, her life story, and no caregiver
    sessions, answers, alerts, or "Remind now" records. Family messages are kept. The database is
    shared, so this resets it for everyone: ask before pressing it."""
    result = store.reset_demo(PATIENT_ID, PATIENT_NAME, demo_memories(datetime.now(timezone.utc)))
    return {**result, "life_story_error": _replace_life_story(life_story.demo_passages())}


# The patient: one per deployment (PATIENT_ID). A new patient replaces the current one.


class PatientName(BaseModel):
    name: str = Field(min_length=1, max_length=60)


@staff_router.get("/patient")
def get_patient():
    return {"name": store.patient_name(PATIENT_ID)}


@staff_router.put("/patient")
def rename_patient(body: PatientName):
    """Changes the name Vela, reminders, and extraction use, from the next conversation on."""
    _needs_database()
    name = _clean_name(body.name)
    store.set_patient_name(PATIENT_ID, name)
    return {"name": name}


@staff_router.post("/patient/new")
def new_patient(body: PatientName):
    """Starts over with someone else: their name, and no memories, caregiver notes, answers,
    alerts, "Remind now" records, or life story. Family messages are kept (staff delete them on
    their page). The demo reset brings Rose back."""
    _needs_database()
    name = _clean_name(body.name)
    result = store.reset_demo(PATIENT_ID, name, [])
    return {**result, "name": name, "life_story_error": _replace_life_story([])}


def _clean_name(name: str) -> str:
    name = " ".join(name.split())
    if not name:
        raise HTTPException(422, "The name is empty")
    return name


def _replace_life_story(passages: list) -> str | None:
    """Tiger Data is already reset by now; the life story follows if Snowflake allows. Returns why
    it couldn't, so staff see it, rather than failing the whole reset."""
    if not life_story.enabled():
        return "The life story wasn't changed: Snowflake isn't set up in backend/.env."
    try:
        life_story.replace_passages(PATIENT_ID, passages)
    except life_story.LifeStoryError as err:
        return f"The life story wasn't changed. Snowflake: {err}"
    return None


# Life story: the patient's past, in Snowflake (app/memory/life_story.py)


@router.get("/life-story")
def search_life_story(q: str = Query(min_length=1, max_length=200)):
    """What the agent's search_life_story tool returns (the patient screen has no login): lines
    about the patient's past that answer the question, plus their IDs. Always 200, so the agent
    always gets something usable: NO_LIFE_STORY when nothing answers, LIFE_STORY_FAILED when
    Snowflake is unset or unreachable, and both tell it to say it isn't sure."""
    return life_story.lookup(PATIENT_ID, q)


def _snowflake(action, *args):
    if not life_story.enabled():
        raise HTTPException(503, "The life story needs Snowflake, and its settings in backend/.env aren't all set")
    try:
        return action(*args)
    except life_story.LifeStoryError as err:
        raise HTTPException(502, f"Snowflake: {err}")


@staff_router.get("/life-story/passages")
def list_life_story():
    """Every passage of the patient's life story, oldest first."""
    return {"passages": _snowflake(life_story.list_passages, PATIENT_ID)}


@staff_router.post("/life-story/passages", status_code=201)
def add_life_story(body: life_story.Passage):
    """One short fact about the patient's past. Searchable by the agent within about a minute
    (the search service's refresh delay). Medicine is refused (422)."""
    return _snowflake(life_story.add_passage, PATIENT_ID, body)


@staff_router.delete("/life-story/passages/{passage_id}", status_code=204)
def delete_life_story(passage_id: UUID):
    if not _snowflake(life_story.delete_passage, PATIENT_ID, str(passage_id)):
        raise HTTPException(404, "That passage doesn't exist")

