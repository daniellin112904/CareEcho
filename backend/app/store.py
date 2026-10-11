"""Every read and write of the patient's records, in one place.

Everything is stored in Tiger Data (app/db.py): the patient, memories, caregiver sessions,
answers (a TimescaleDB hypertable), alerts, family messages, and "Remind now" records. Without
DATABASE_URL, the demo memories from app/memory/demo.py and JSON files under backend/data/
(git-ignored) stand in, so a demo still runs offline. The routes, the agent, and the frontend
only call these functions, so they don't care which. The tables are in app/memory/schema.sql
plus app/memory/schema_voice.sql.

Rows are plain dicts with the same keys as the table columns. IDs are strings and times are
ISO 8601 strings with a timezone, whatever the storage: callers like build_facts and the
reminders parse them as strings (see _plain).

Audio (family messages, reminders) isn't stored here: those MP3s are a cache on disk that's
rebuilt from the text when missing.
"""

import json
import os
import threading
import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

from app import db
from app.memory.demo import PATIENT_NAME, demo_memories

PATIENT_ID = "demo"

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
# One lock for every JSON file (only used without a database): concurrent requests never
# overwrite each other. Only covers one process, so run a single uvicorn worker in that mode.
_lock = threading.RLock()


# Memories and the patient: owned by the memory system


_MEMORY_COLUMNS = ("id, kind, summary, details, event_at, all_day, status, certainty, source, source_quote, "
                   "session_id, supersedes_id, created_at, confirmed_at")
# The only statuses ever spoken to the patient (pending, rejected, superseded, and
# self-reported never are). build_facts in app/memory/context.py checks this again.
_SPEAKABLE = ["confirmed", "tentative"]
_demo_rows: list[dict] | None = None


def _plain(row: dict) -> dict:
    """A database row as the rest of the app expects it: UUIDs and times as strings (also
    inside lists, like an answer's memory_ids)."""
    def plain(v):
        if isinstance(v, list):
            return [plain(x) for x in v]
        return str(v) if isinstance(v, uuid.UUID) else v.isoformat() if isinstance(v, datetime) else v
    return {k: plain(v) for k, v in row.items()}


def _demo() -> list[dict]:
    """The demo memories when there's no database, timed once per server start so a plan
    doesn't move from today to tomorrow in the middle of a demo."""
    global _demo_rows
    with _lock:
        if _demo_rows is None:
            _demo_rows = demo_memories(datetime.now(timezone.utc))
        return _demo_rows


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
        return True
    except (ValueError, TypeError, AttributeError):
        return False


def patient_name(patient_id: str) -> str:
    """The demo name if the patient isn't in the database yet (seed not run), so starting a
    conversation never fails over a missing name."""
    if not db.enabled():
        return PATIENT_NAME
    with db.pool().connection() as conn:
        row = conn.execute("SELECT name FROM patients WHERE id = %s", (patient_id,)).fetchone()
    return row["name"] if row else PATIENT_NAME


def set_patient_name(patient_id: str, name: str) -> None:
    """Renames the patient (adds their row if seed_demo.py was never run)."""
    with db.pool().connection() as conn:
        conn.execute("INSERT INTO patients (id, name) VALUES (%s, %s) ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name",
                     (patient_id, name))


def current_memories(patient_id: str) -> list[dict]:
    """What the agent and the patient screen may know: confirmed and tentative memories,
    soonest first, then the ones with no time. Events that already happened are still here;
    build_facts stops telling the agent about them two hours after they start.
    """
    if not db.enabled():
        return [m for m in _demo() if m["status"] in _SPEAKABLE]
    with db.pool().connection() as conn:
        rows = conn.execute(
            f"SELECT {_MEMORY_COLUMNS} FROM memories WHERE patient_id = %s AND status = ANY(%s) "
            "ORDER BY event_at NULLS LAST, created_at",
            (patient_id, _SPEAKABLE),
        ).fetchall()
    return [_plain(r) for r in rows]


def memories_by_id(ids: list[str]) -> dict[str, dict]:
    """The memories behind answer receipts, keyed by ID. Includes superseded and expired
    versions: a receipt shows the version that was true when the answer was given.

    IDs that aren't UUIDs (like "mock-1" in answers logged before the database) are skipped:
    Postgres would reject the whole query over one of them.
    """
    wanted = {i for i in ids if _is_uuid(i)}
    if not wanted:
        return {}
    if not db.enabled():
        return {m["id"]: m for m in _demo() if m["id"] in wanted}
    with db.pool().connection() as conn:
        rows = conn.execute(f"SELECT {_MEMORY_COLUMNS} FROM memories WHERE id = ANY(%s)",
                            ([uuid.UUID(i) for i in wanted],)).fetchall()
    return {m["id"]: m for m in map(_plain, rows)}


# Caregiver sessions: what a caregiver said, and the memories extracted from it (database only)


def add_session(patient_id: str, transcript: str) -> dict:
    """Saved on its own, before extraction starts, so the caregiver's words are kept even if
    Gemini fails."""
    with db.pool().connection() as conn:
        row = conn.execute(
            "INSERT INTO sessions (patient_id, transcript) VALUES (%s, %s) RETURNING *", (patient_id, transcript)
        ).fetchone()
    return _plain(row)


def finish_session(session_id: str, patient_id: str, source: str, extraction: dict,
                   candidates: list[dict]) -> list[dict]:
    """Records what extraction did and saves its candidates as pending memories, all in one
    transaction. Pending memories are never spoken until a caregiver confirms them.

    `candidates` come from app/memory/extraction.py (already validated). Returns the new
    memory rows, in the same order. Each entry in extraction["kept"] gets its memory's ID, so
    the review list can show each pending memory its own warnings.
    """
    with db.pool().connection() as conn:
        rows = [
            conn.execute(
                "INSERT INTO memories (patient_id, kind, summary, details, event_at, all_day, status, certainty, "
                "source, source_quote, session_id, supersedes_id) "
                f"VALUES (%s, %s, %s, %s, %s, %s, 'pending', %s, %s, %s, %s, %s) RETURNING {_MEMORY_COLUMNS}",
                (patient_id, c["kind"], c["summary"], c["details"] and Jsonb(c["details"]), c["event_at"],
                 c["all_day"], c["certainty"], source, c["source_quote"], session_id, c["supersedes_id"]),
            ).fetchone()
            for c in candidates
        ]
        for entry, row in zip(extraction.get("kept", []), rows):
            entry["memory_id"] = str(row["id"])
        conn.execute("UPDATE sessions SET extraction = %s WHERE id = %s", (Jsonb(extraction), session_id))
    return [_plain(r) for r in rows]


def list_sessions(patient_id: str, limit: int = 20) -> list[dict]:
    """Recent caregiver notes, newest first: the words, extraction's error or what it dropped, and
    the memories it made with their status now (pending, confirmed, rejected, cancelled...).
    Gemini's raw output stays in the database. extraction is None while Gemini is still working."""
    with db.pool().connection() as conn:
        sessions = conn.execute(
            "SELECT id, transcript, created_at, extraction FROM sessions WHERE patient_id = %s "
            "ORDER BY created_at DESC LIMIT %s", (patient_id, limit)).fetchall()
        ids = [s["id"] for s in sessions]
        memories = conn.execute(
            f"SELECT {_MEMORY_COLUMNS} FROM memories WHERE session_id = ANY(%s) ORDER BY created_at",
            (ids,)).fetchall() if ids else []
    made: dict[str, list[dict]] = {}
    for m in map(_plain, memories):
        made.setdefault(m["session_id"], []).append(m)
    return [{"id": str(s["id"]), "transcript": s["transcript"], "created_at": s["created_at"].isoformat(),
             "finished": s["extraction"] is not None,
             "error": (s["extraction"] or {}).get("error"),
             "dropped": (s["extraction"] or {}).get("dropped", []),
             "memories": made.get(str(s["id"]), [])}
            for s in sessions]


# Review: staff confirm, reject, or cancel memories (database only). Every function is scoped to
# the patient: another patient's memory counts as not found.


class Conflict(Exception):
    """The memory isn't in a state that allows this (answered as 409, with this message)."""


def pending_memories(patient_id: str) -> list[dict]:
    """Memories waiting for a caregiver, oldest first. Each also has:
    - warnings: what extraction flagged for a human to check (from its session's record)
    - replaces: the current memory it would replace, or None for something new
    - stale: True when that memory was already changed or cancelled, so this one can't be confirmed
    """
    with db.pool().connection() as conn:
        rows = [_plain(r) for r in conn.execute(
            f"SELECT {_MEMORY_COLUMNS} FROM memories WHERE patient_id = %s AND status = 'pending' "
            "ORDER BY created_at", (patient_id,)).fetchall()]
        session_ids = list({r["session_id"] for r in rows if r["session_id"]})
        replaced_ids = list({r["supersedes_id"] for r in rows if r["supersedes_id"]})
        sessions = conn.execute("SELECT id, extraction FROM sessions WHERE id = ANY(%s)",
                                ([uuid.UUID(i) for i in session_ids],)).fetchall() if session_ids else []
        replaced = conn.execute(
            "SELECT id, summary, event_at, all_day, details, status FROM memories WHERE id = ANY(%s)",
            ([uuid.UUID(i) for i in replaced_ids],)).fetchall() if replaced_ids else []
    warnings = {entry["memory_id"]: entry.get("warnings", [])
                for s in sessions for entry in (s["extraction"] or {}).get("kept", []) if entry.get("memory_id")}
    replaced = {m["id"]: m for m in map(_plain, replaced)}
    for r in rows:
        old = replaced.get(r["supersedes_id"])
        r["warnings"] = warnings.get(r["id"], [])
        r["replaces"] = old
        r["stale"] = bool(r["supersedes_id"]) and (old is None or old["status"] not in _SPEAKABLE)
    return rows


def confirm_memory(patient_id: str, memory_id: str, certainty: str | None = None) -> dict | None:
    """A caregiver confirms a pending memory: from now on the agent may say it.

    One transaction. Tentative certainty makes it 'tentative' (said as not certain), otherwise
    'confirmed'. For an update, the version it replaces becomes 'superseded' at the same moment,
    so there's always exactly one current version. The pending row is locked first, then the old
    version: two competing updates queue on the old version, and the second finds it already
    superseded (Conflict) instead of forking the chain.
    """
    try:
        with db.pool().connection() as conn:
            memory = conn.execute(
                "SELECT status, certainty, supersedes_id FROM memories WHERE id = %s AND patient_id = %s FOR UPDATE",
                (memory_id, patient_id)).fetchone()
            if memory is None:
                return None
            if memory["status"] != "pending":
                raise Conflict(f"This memory is already {memory['status']}.")
            certainty = certainty or memory["certainty"] or "definite"
            if memory["supersedes_id"]:
                old = conn.execute("SELECT status FROM memories WHERE id = %s AND patient_id = %s FOR UPDATE",
                                   (memory["supersedes_id"], patient_id)).fetchone()
                if old is None or old["status"] not in _SPEAKABLE:
                    raise Conflict("The plan this changes was already changed or cancelled. "
                                   "Reject this one, or say it again.")
                conn.execute("UPDATE memories SET status = 'superseded' WHERE id = %s", (memory["supersedes_id"],))
            row = conn.execute(
                "UPDATE memories SET status = %s, certainty = %s, confirmed_at = now() "
                f"WHERE id = %s RETURNING {_MEMORY_COLUMNS}",
                ("tentative" if certainty == "tentative" else "confirmed", certainty, memory_id)).fetchone()
    except psycopg.errors.UniqueViolation:
        # The no-fork index (schema.sql); the locks above should already prevent this
        raise Conflict("The plan this changes was already changed. Reject this one, or say it again.")
    return _plain(row)


def reject_memory(patient_id: str, memory_id: str) -> dict | None:
    """A caregiver says a pending memory is wrong. It's kept, as 'rejected', and never spoken."""
    return _move(patient_id, memory_id, ["pending"], "rejected",
                 {"confirmed": "It's already confirmed: cancel it instead.",
                  "tentative": "It's already confirmed: cancel it instead."})


def cancel_memory(patient_id: str, memory_id: str) -> dict | None:
    """Staff remove a current plan (extraction ignores cancellations on purpose). It's kept, as
    'cancelled', so receipts of past answers still show it, but it's never spoken again."""
    return _move(patient_id, memory_id, _SPEAKABLE, "cancelled",
                 {"pending": "It isn't confirmed yet: reject it instead.",
                  "superseded": "Only the current version can be cancelled."})


def _move(patient_id: str, memory_id: str, allowed: list[str], to: str, hints: dict[str, str]) -> dict | None:
    """Changes a memory's status if it's in one of the allowed ones; None if it doesn't exist."""
    with db.pool().connection() as conn:
        row = conn.execute(
            f"UPDATE memories SET status = %s WHERE id = %s AND patient_id = %s AND status = ANY(%s) "
            f"RETURNING {_MEMORY_COLUMNS}", (to, memory_id, patient_id, allowed)).fetchone()
        if row is None:
            current = conn.execute("SELECT status FROM memories WHERE id = %s AND patient_id = %s",
                                   (memory_id, patient_id)).fetchone()
            if current is None:
                return None
            raise Conflict(hints.get(current["status"], f"This memory is already {current['status']}."))
    return _plain(row)


# JSON files: only when there's no database (see the module docstring)


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


def _one(sql: str, params) -> dict | None:
    with db.pool().connection() as conn:
        row = conn.execute(sql, params).fetchone()
    return row and _plain(row)


def _all(sql: str, params) -> list[dict]:
    with db.pool().connection() as conn:
        return [_plain(r) for r in conn.execute(sql, params).fetchall()]


# Interactions: one row per answer the agent gave. A TimescaleDB hypertable: the hourly
# repetition counts on the dashboard (the questions_hourly continuous aggregate) come from it


_INTERACTION_COLUMNS = "id, ts, patient_id, conversation_id, topic, question, answer, memory_ids, answered, latency_ms"


def add_interaction(conversation_id: str | None, topic: str, question: str, answer: str,
                    memory_ids: list[str], answered: bool, latency_ms: int | None = None) -> dict:
    """IDs that aren't UUIDs (like "mock-1" from before the database) are left out of
    memory_ids: the column is UUID[], and receipts skip them anyway."""
    memory_ids = [i for i in memory_ids if _is_uuid(i)]
    if not db.enabled():
        return _insert("interactions", _new_row(conversation_id=conversation_id, topic=topic, question=question,
                                                answer=answer, memory_ids=memory_ids, answered=answered,
                                                latency_ms=latency_ms))
    return _one(
        "INSERT INTO interactions (patient_id, conversation_id, topic, question, answer, memory_ids, answered, latency_ms) "
        f"VALUES (%s, %s, %s, %s, %s, %s::uuid[], %s, %s) RETURNING {_INTERACTION_COLUMNS}",
        (PATIENT_ID, conversation_id, topic, question, answer, memory_ids, answered, latency_ms))


def list_interactions(patient_id: str) -> list[dict]:
    """Newest first, at most 500."""
    if not db.enabled():
        rows = [r for r in _read("interactions") if r["patient_id"] == patient_id]
        return sorted(rows, key=lambda r: r["ts"], reverse=True)[:500]
    return _all(f"SELECT {_INTERACTION_COLUMNS} FROM interactions WHERE patient_id = %s ORDER BY ts DESC LIMIT 500",
                (patient_id,))


# Things the patient said they did ("I took my pills"): memories with status self_reported and
# source patient, which are never spoken and never count as facts


def add_statement(text: str, kind: str) -> dict:
    """Returns {id, ts, text, kind, status}, the same with or without the database."""
    if not db.enabled():
        return _insert("statements", _new_row(text=text, kind=kind, status="self_reported"))
    return _one(
        "INSERT INTO memories (patient_id, kind, summary, status, source, source_quote) "
        "VALUES (%s, %s, %s, 'self_reported', 'patient', %s) "
        "RETURNING id, created_at AS ts, summary AS text, kind, status",
        (PATIENT_ID, kind, text, text))


def list_statements(patient_id: str, since: datetime) -> list[dict]:
    """What the patient said they did since then, newest first."""
    if not db.enabled():
        rows = [r for r in _read("statements")
                if r["patient_id"] == patient_id and datetime.fromisoformat(r["ts"]) >= since]
        return sorted(rows, key=lambda r: r["ts"], reverse=True)
    # Reminders the patient asked for are self-reported too, but they're requests, not things she did
    return _all("SELECT id, created_at AS ts, summary AS text, kind, status FROM memories "
                "WHERE patient_id = %s AND status = 'self_reported' AND kind <> 'reminder' AND created_at >= %s "
                "ORDER BY created_at DESC", (patient_id, since))


# Reminders the patient asked for ("Remind me at 5 to water my tomato plants"): memories with kind
# reminder, source patient, and status self_reported, so like self-reports they're never told to
# the agent as facts. Only app/voice/reminders.py reads them, to say each one at its time.


_PATIENT_REMINDER = "kind = 'reminder' AND source = 'patient'"


def add_patient_reminder(patient_id: str, task: str, said: str, at: datetime) -> dict:
    """Returns the memory row, the same with or without the database."""
    if not db.enabled():
        row = {"id": uuid.uuid4().hex, "patient_id": patient_id, "kind": "reminder", "summary": task, "details": None,
               "event_at": at.isoformat(), "all_day": False, "status": "self_reported", "certainty": None,
               "source": "patient", "source_quote": said, "session_id": None, "supersedes_id": None,
               "created_at": datetime.now(timezone.utc).isoformat(), "confirmed_at": None}
        return _insert("patient_reminders", row)
    return _one("INSERT INTO memories (patient_id, kind, summary, event_at, status, source, source_quote) "
                f"VALUES (%s, 'reminder', %s, %s, 'self_reported', 'patient', %s) RETURNING {_MEMORY_COLUMNS}",
                (patient_id, task, at, said))


def patient_reminders(patient_id: str, since: datetime) -> list[dict]:
    """Reminders the patient asked for, due from `since` on and not cancelled, soonest first."""
    if not db.enabled():
        rows = [r for r in _read("patient_reminders") if r["patient_id"] == patient_id
                and r["status"] == "self_reported" and datetime.fromisoformat(r["event_at"]) >= since]
        return sorted(rows, key=lambda r: datetime.fromisoformat(r["event_at"]))
    return _all(f"SELECT {_MEMORY_COLUMNS} FROM memories WHERE patient_id = %s AND {_PATIENT_REMINDER} "
                "AND status = 'self_reported' AND event_at >= %s ORDER BY event_at", (patient_id, since))


def cancel_patient_reminder(patient_id: str, reminder_id: str) -> dict | None:
    """Staff cancel a reminder the patient asked for: kept, as 'cancelled', and never said.
    Separate from cancel_memory, which stays limited to confirmed plans. None if there's no such
    reminder (any other memory counts as not found); Conflict if it's already cancelled."""
    if not _is_uuid(reminder_id):
        return None
    if not db.enabled():
        with _lock:
            rows = _read("patient_reminders")
            match = next((r for r in rows if r["id"] == reminder_id and r["patient_id"] == patient_id), None)
            if match is None:
                return None
            if match["status"] != "self_reported":
                raise Conflict(f"This reminder is already {match['status']}.")
            match["status"] = "cancelled"
            _write("patient_reminders", rows)
        return match
    with db.pool().connection() as conn:
        row = conn.execute(
            f"UPDATE memories SET status = 'cancelled' WHERE id = %s AND patient_id = %s AND {_PATIENT_REMINDER} "
            f"AND status = 'self_reported' RETURNING {_MEMORY_COLUMNS}", (reminder_id, patient_id)).fetchone()
        if row is None:
            current = conn.execute(f"SELECT status FROM memories WHERE id = %s AND patient_id = %s AND {_PATIENT_REMINDER}",
                                   (reminder_id, patient_id)).fetchone()
            if current is None:
                return None
            raise Conflict(f"This reminder is already {current['status']}.")
    return _plain(row)


# Alerts for the care team. IDs come from the patient screen's URL too, so anything that isn't
# a UUID is "not found" before it reaches Postgres (which would refuse it with an error)


_ALERT_COLUMNS = "id, ts, patient_id, kind, message, resolved"


def add_alert(kind: str, message: str) -> dict:
    if not db.enabled():
        return _insert("alerts", _new_row(kind=kind, message=message, resolved=False))
    return _one(f"INSERT INTO alerts (patient_id, kind, message) VALUES (%s, %s, %s) RETURNING {_ALERT_COLUMNS}",
                (PATIENT_ID, kind, message))


def get_alert(alert_id: str) -> dict | None:
    if not _is_uuid(alert_id):
        return None
    if not db.enabled():
        return next((a for a in _read("alerts") if a["id"] == alert_id), None)
    return _one(f"SELECT {_ALERT_COLUMNS} FROM alerts WHERE id = %s", (alert_id,))


def list_alerts(patient_id: str) -> list[dict]:
    """Open alerts first, newest first within each group (at most 200: open ones always fit)."""
    if not db.enabled():
        rows = sorted((a for a in _read("alerts") if a["patient_id"] == patient_id),
                      key=lambda a: a["ts"], reverse=True)
        return sorted(rows, key=lambda a: a["resolved"])[:200]
    return _all(f"SELECT {_ALERT_COLUMNS} FROM alerts WHERE patient_id = %s ORDER BY resolved, ts DESC LIMIT 200",
                (patient_id,))


def resolve_alert(alert_id: str) -> bool:
    """Whether an alert with that ID exists (it's resolved now either way)."""
    if not _is_uuid(alert_id):
        return False
    if not db.enabled():
        with _lock:
            rows = _read("alerts")
            match = next((a for a in rows if a["id"] == alert_id), None)
            if match:
                match["resolved"] = True
                _write("alerts", rows)
        return match is not None
    return _one("UPDATE alerts SET resolved = true WHERE id = %s RETURNING id", (alert_id,)) is not None


# Family messages (the MP3 for each is cached on disk by app/voice/messages.py, named by the
# message ID's 32 hex digits, so it doesn't matter whether the ID is written with dashes)


_MESSAGE_COLUMNS = "id, patient_id, from_name, voice_id, text, created_at"


def add_family_message(from_name: str, voice_id: str, text: str) -> dict:
    if not db.enabled():
        row = {"id": uuid.uuid4().hex, "patient_id": PATIENT_ID, "from_name": from_name, "voice_id": voice_id,
               "text": text, "created_at": datetime.now(timezone.utc).isoformat()}
        return _insert("family_messages", row)
    return _one("INSERT INTO family_messages (patient_id, from_name, voice_id, text) VALUES (%s, %s, %s, %s) "
                f"RETURNING {_MESSAGE_COLUMNS}", (PATIENT_ID, from_name, voice_id, text))


def list_family_messages(patient_id: str) -> list[dict]:
    """Newest first."""
    if not db.enabled():
        rows = [m for m in _read("family_messages") if m.get("patient_id", PATIENT_ID) == patient_id]
        return sorted(rows, key=lambda m: m["created_at"], reverse=True)
    return _all(f"SELECT {_MESSAGE_COLUMNS} FROM family_messages WHERE patient_id = %s ORDER BY created_at DESC",
                (patient_id,))


def delete_family_message(message_id: str) -> dict | None:
    if not _is_uuid(message_id):
        return None
    if not db.enabled():
        with _lock:
            rows = _read("family_messages")
            match = next((m for m in rows if m["id"] == message_id), None)
            if match:
                _write("family_messages", [m for m in rows if m["id"] != message_id])
        return match
    return _one(f"DELETE FROM family_messages WHERE id = %s RETURNING {_MESSAGE_COLUMNS}", (message_id,))


# Reminders staff sent with "Remind now" (scheduled ones are computed from memories)


def add_sent_reminder(memory_id: str) -> dict:
    reminder_id = f"{memory_id}-now-{uuid.uuid4().hex[:8]}"
    if not db.enabled():
        row = {"id": reminder_id, "patient_id": PATIENT_ID, "memory_id": memory_id,
               "at": datetime.now(timezone.utc).isoformat()}
        with _lock:
            _write("reminders_now", [*_read("reminders_now")[-20:], row])
        return row
    return _one("INSERT INTO reminders_sent (id, patient_id, memory_id) VALUES (%s, %s, %s) "
                "RETURNING id, patient_id, memory_id, at", (reminder_id, PATIENT_ID, memory_id))


def recent_sent_reminders(patient_id: str, since: datetime) -> list[dict]:
    if not db.enabled():
        return [r for r in _read("reminders_now")
                if r.get("patient_id", PATIENT_ID) == patient_id and datetime.fromisoformat(r["at"]) >= since]
    return _all("SELECT id, patient_id, memory_id, at FROM reminders_sent WHERE patient_id = %s AND at >= %s "
                "ORDER BY at", (patient_id, since))


# History: every version of a memory (database only)


# Statuses of a version that was the current one at some point (pending and rejected
# proposals never were, so they aren't versions)
_VERSION_STATUSES = ["confirmed", "tentative", "superseded", "cancelled"]


def memory_history(patient_id: str, memory_id: str) -> list[dict] | None:
    """Oldest first: the versions it replaced, itself, then the versions that replaced it.
    None if the memory doesn't exist. For a pending proposal, the history of the memory it
    would change, ending with the proposal."""
    with db.pool().connection() as conn:
        def find(where: str, value):
            return conn.execute(f"SELECT {_MEMORY_COLUMNS} FROM memories WHERE {where} AND patient_id = %s",
                                (value, patient_id)).fetchone()

        start = find("id = %s", memory_id)
        if start is None:
            return None
        older, row = [], start
        while row["supersedes_id"] and len(older) < 50 and (row := find("id = %s", row["supersedes_id"])):
            older.append(row)
        newer, row = [], start
        while len(newer) < 50 and (row := conn.execute(
                f"SELECT {_MEMORY_COLUMNS} FROM memories WHERE supersedes_id = %s AND patient_id = %s "
                "AND status = ANY(%s)", (row["id"], patient_id, _VERSION_STATUSES)).fetchone()):
            newer.append(row)
    return [_plain(r) for r in [*reversed(older), start, *newer]]


# The care team's dashboard


_ALERT_KINDS = ("help_requested", "missing_info", "self_reported_med")


def dashboard(patient_id: str, now: datetime) -> dict:
    """What the patient keeps asking about today and over the last 24 hours, open alerts by
    kind, and what the patient said they did today. Days are the patient's (TIMEZONE).

    The question counts come from questions_hourly, a TimescaleDB continuous aggregate over the
    interactions hypertable (schema.sql). It's real-time (materialized_only = false), so an
    answer logged a moment ago is already counted.
    """
    tz = ZoneInfo(os.getenv("TIMEZONE", "America/New_York"))
    local = now.astimezone(tz)
    today = local.replace(hour=0, minute=0, second=0, microsecond=0)
    this_hour = now.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
    hours = [this_hour - timedelta(hours=n) for n in range(23, -1, -1)]

    if db.enabled():
        with db.pool().connection() as conn:
            by_topic = [(r["topic"], r["asks"]) for r in conn.execute(
                "SELECT topic, sum(asks)::int AS asks FROM questions_hourly WHERE patient_id = %s AND hour >= %s "
                "GROUP BY topic ORDER BY asks DESC, topic", (patient_id, today)).fetchall()]
            per_hour = {r["hour"]: r["asks"] for r in conn.execute(
                "SELECT hour, sum(asks)::int AS asks FROM questions_hourly WHERE patient_id = %s AND hour >= %s "
                "GROUP BY hour", (patient_id, hours[0])).fetchall()}
            open_alerts = {r["kind"]: r["n"] for r in conn.execute(
                "SELECT kind, count(*)::int AS n FROM alerts WHERE patient_id = %s AND NOT resolved GROUP BY kind",
                (patient_id,)).fetchall()}
    else:
        asked = [(datetime.fromisoformat(r["ts"]), r["topic"]) for r in list_interactions(patient_id)]
        by_topic = Counter(topic for ts, topic in asked if ts >= today).most_common()
        per_hour = Counter(ts.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
                           for ts, _ in asked if ts >= hours[0])
        open_alerts = Counter(a["kind"] for a in list_alerts(patient_id) if not a["resolved"])

    return {
        "day": local.date().isoformat(),
        "asks_today": sum(n for _, n in by_topic),
        "by_topic": [{"topic": topic or "Other", "asks": n} for topic, n in by_topic],
        "by_hour": [{"hour": h.isoformat(), "asks": per_hour.get(h, 0)} for h in hours],
        "open_alerts": {kind: open_alerts.get(kind, 0) for kind in _ALERT_KINDS},
        "self_reported_today": list_statements(patient_id, today),
    }


# Demo reset


_SEED_COLUMNS = ("id", "kind", "summary", "details", "event_at", "all_day", "status", "certainty", "source",
                 "source_quote", "supersedes_id", "created_at", "confirmed_at")


def reset_demo(patient_id: str, name: str, memories: list[dict]) -> dict:
    """Puts the demo patient back to a known state: their name, these memories, and no caregiver
    sessions, answers, alerts, or "Remind now" records. One transaction.

    Family messages are kept: each needs a consented voice and text to speech to make again.
    Without a database, the demo memories are re-timed from now and the JSON records cleared.
    Returns how many of each were removed.
    """
    global _demo_rows
    if not db.enabled():
        removed = {}
        with _lock:
            _demo_rows = None
            for table in ("interactions", "statements", "alerts", "reminders_now", "patient_reminders"):
                rows = _read(table)
                kept = [r for r in rows if r.get("patient_id", PATIENT_ID) != patient_id]
                removed[table] = len(rows) - len(kept)
                _write(table, kept)
        return {"memories": len(_demo()), "removed": removed}

    with db.pool().connection() as conn:
        conn.execute("INSERT INTO patients (id, name) VALUES (%s, %s) ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name",
                     (patient_id, name))
        # In this order: "Remind now" records point at memories, and memories at sessions
        removed = {table: conn.execute(f"DELETE FROM {table} WHERE patient_id = %s", (patient_id,)).rowcount
                   for table in ("reminders_sent", "interactions", "alerts", "memories", "sessions")}
        # In list order: a newer version comes after the one it supersedes
        for m in memories:
            values = {**m, "details": m["details"] and Jsonb(m["details"])}
            conn.execute(f"INSERT INTO memories (patient_id, {', '.join(_SEED_COLUMNS)}) "
                         f"VALUES (%s, {', '.join(['%s'] * len(_SEED_COLUMNS))})",
                         [patient_id, *(values[c] for c in _SEED_COLUMNS)])
    _refresh_question_counts()
    return {"memories": len(memories), "removed": removed}


def _refresh_question_counts():
    """Recounts the stored hourly totals right away, so deleted answers leave the dashboard now
    rather than at the next scheduled refresh.

    Complete hours only: the window ends at the start of the current hour. Recounting the hour
    in progress would store a total for it and move the aggregate's real-time boundary (its
    watermark) past it, and answers logged later in that hour wouldn't show until it ended.

    TimescaleDB refuses this inside a transaction, so this one statement runs in autocommit,
    which is switched back off before the connection goes back to the pool (everything else
    relies on transactions).
    """
    this_hour = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    with db.pool().connection() as conn:
        conn.autocommit = True
        try:
            conn.execute(sql.SQL("CALL refresh_continuous_aggregate('questions_hourly', NULL, {})")
                         .format(sql.Literal(this_hour)))
        finally:
            conn.autocommit = False

