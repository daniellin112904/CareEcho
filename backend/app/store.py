"""Every read and write of the voice features' records, in one place.

Today these are JSON files under backend/data/ (git-ignored). To move to Tiger Data, replace
the body of each function with the SQL in its docstring: the routes, the agent, and the
frontend only call these functions, so nothing else changes. The tables are in
app/memory/schema.sql plus app/memory/schema_voice.sql.

Rows are plain dicts with the same keys as the table columns. IDs are strings (uuid hex
today, UUID in Postgres) and times are ISO 8601 strings with a timezone.

Audio (family messages, reminders) isn't stored here: those MP3s are a cache on disk that's
rebuilt from the text when missing.
"""

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.memory.routes import current_memories as _memories_route

PATIENT_ID = "demo"

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
# One lock for every JSON file: concurrent requests never overwrite each other. Only covers
# one process, so run a single uvicorn worker until this moves to a database.
_lock = threading.RLock()


# Memories and the patient: owned by the memory system


def patient_name(patient_id: str) -> str:
    """SELECT name FROM patients WHERE id = %s  (no patients table yet)"""
    return "Rose"


def current_memories(patient_id: str) -> list[dict]:
    """What the agent may know. Comes from GET /memories/current in app/memory/routes.py, so
    replacing that route's mock with the real query updates the agent too.

    Real query: SELECT * FROM memories WHERE patient_id = %s
                AND status IN ('confirmed', 'tentative', ...) ORDER BY event_at
    (build_facts in app/memory/context.py still filters status and ended events itself.)
    """
    return _memories_route()["memories"]


def memories_by_id(ids: list[str]) -> dict[str, dict]:
    """The memories behind answer receipts, keyed by ID.

    SELECT * FROM memories WHERE id = ANY(%s)
    Include superseded and expired versions: a receipt should show the version that was true
    when the answer was given, not only what's current now.
    """
    wanted = set(ids)
    return {m["id"]: m for m in current_memories(PATIENT_ID) if m["id"] in wanted}


# JSON file helpers (delete once everything below is SQL)


def _read(name: str) -> list[dict]:
    path = DATA_DIR / f"{name}.json"
    with _lock:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def _write(name: str, rows: list[dict]):
    path = DATA_DIR / f"{name}.json"
    with _lock:
        DATA_DIR.mkdir(exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(rows, indent=2), encoding="utf-8")
        os.replace(tmp, path)


def _new_row(**fields) -> dict:
    return {"id": uuid.uuid4().hex, "ts": datetime.now(timezone.utc).isoformat(), "patient_id": PATIENT_ID, **fields}


def _insert(name: str, row: dict) -> dict:
    with _lock:
        _write(name, [*_read(name), row])
    return row


# Interactions: one row per answer the agent gave


def add_interaction(conversation_id: str | None, topic: str, question: str, answer: str,
                    memory_ids: list[str], answered: bool, latency_ms: int | None = None) -> dict:
    """INSERT INTO interactions (ts, patient_id, conversation_id, topic, question, answer,
           memory_ids, answered, latency_ms)
       VALUES (now(), %s, %s, %s, %s, %s, %s::uuid[], %s, %s) RETURNING *
    """
    row = _new_row(conversation_id=conversation_id, topic=topic, question=question, answer=answer,
                   memory_ids=memory_ids, answered=answered, latency_ms=latency_ms)
    return _insert("interactions", row)


def list_interactions(patient_id: str) -> list[dict]:
    """SELECT * FROM interactions WHERE patient_id = %s ORDER BY ts DESC LIMIT 500"""
    rows = [r for r in _read("interactions") if r["patient_id"] == patient_id]
    return sorted(rows, key=lambda r: r["ts"], reverse=True)


# Things the patient said they did ("I took my pills"): never facts


def add_statement(text: str, kind: str) -> dict:
    """In the schema these are memories the patient reported:
       INSERT INTO memories (patient_id, kind, summary, status, source, source_quote)
       VALUES (%s, %s, %s, 'self_reported', 'patient', %s) RETURNING *
    """
    return _insert("statements", _new_row(text=text, kind=kind, status="self_reported"))


# Alerts for the care team


def add_alert(kind: str, message: str) -> dict:
    """INSERT INTO alerts (patient_id, kind, message) VALUES (%s, %s, %s) RETURNING *"""
    return _insert("alerts", _new_row(kind=kind, message=message, resolved=False))


def get_alert(alert_id: str) -> dict | None:
    """SELECT * FROM alerts WHERE id = %s"""
    return next((a for a in _read("alerts") if a["id"] == alert_id), None)


def list_alerts(patient_id: str) -> list[dict]:
    """SELECT * FROM alerts WHERE patient_id = %s ORDER BY resolved, ts DESC"""
    rows = sorted((a for a in _read("alerts") if a["patient_id"] == patient_id), key=lambda a: a["ts"], reverse=True)
    return sorted(rows, key=lambda a: a["resolved"])


def resolve_alert(alert_id: str) -> bool:
    """UPDATE alerts SET resolved = true WHERE id = %s  (returns whether a row matched)"""
    with _lock:
        rows = _read("alerts")
        match = next((a for a in rows if a["id"] == alert_id), None)
        if match:
            match["resolved"] = True
            _write("alerts", rows)
    return match is not None


# Family messages (the MP3 for each is cached on disk by app/voice/messages.py)


def add_family_message(from_name: str, voice_id: str, text: str) -> dict:
    """INSERT INTO family_messages (patient_id, from_name, voice_id, text)
       VALUES (%s, %s, %s, %s) RETURNING *
    """
    row = {"id": uuid.uuid4().hex, "patient_id": PATIENT_ID, "from_name": from_name, "voice_id": voice_id,
           "text": text, "created_at": datetime.now(timezone.utc).isoformat()}
    return _insert("family_messages", row)


def list_family_messages(patient_id: str) -> list[dict]:
    """SELECT * FROM family_messages WHERE patient_id = %s ORDER BY created_at DESC"""
    rows = [m for m in _read("family_messages") if m.get("patient_id", PATIENT_ID) == patient_id]
    return sorted(rows, key=lambda m: m["created_at"], reverse=True)


def delete_family_message(message_id: str) -> dict | None:
    """DELETE FROM family_messages WHERE id = %s RETURNING *"""
    with _lock:
        rows = _read("family_messages")
        match = next((m for m in rows if m["id"] == message_id), None)
        if match:
            _write("family_messages", [m for m in rows if m["id"] != message_id])
    return match


# Reminders staff sent with "Remind now" (scheduled ones are computed from memories)


def add_sent_reminder(memory_id: str) -> dict:
    """INSERT INTO reminders_sent (id, patient_id, memory_id) VALUES (%s, %s, %s) RETURNING *"""
    row = {"id": f"{memory_id}-now-{uuid.uuid4().hex[:8]}", "patient_id": PATIENT_ID, "memory_id": memory_id,
           "at": datetime.now(timezone.utc).isoformat()}
    with _lock:
        _write("reminders_now", [*_read("reminders_now")[-20:], row])
    return row


def recent_sent_reminders(patient_id: str, since: datetime) -> list[dict]:
    """SELECT * FROM reminders_sent WHERE patient_id = %s AND at >= %s ORDER BY at"""
    return [r for r in _read("reminders_now")
            if r.get("patient_id", PATIENT_ID) == patient_id and datetime.fromisoformat(r["at"]) >= since]
