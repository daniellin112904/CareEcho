"""Review tests: confirming, rejecting, and cancelling memories, against the real database.

Run from backend/:  python scripts/review_tests.py

Uses its own patient ("test-review"), created at the start and deleted at the end (also after a
crash, and at the start in case an earlier run was interrupted), so the demo patient is never
touched. No Gemini calls: pending memories are made the way extraction makes them, from
hand-written candidates (extraction.validate, then store.finish_session).

Exits with code 1 if anything fails.
"""

import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")
# The routes need a staff PIN; use the team's if it's set, otherwise one that exists only here
os.environ.setdefault("STAFF_PIN", "24680")

from fastapi.testclient import TestClient

from app import db, store
from app.main import app
from app.memory import extraction, routes
from app.memory.context import facts_from

PATIENT = "test-review"
TZ = ZoneInfo(os.getenv("TIMEZONE", "America/New_York"))
NOW = datetime.now(timezone.utc)
TOMORROW = (NOW.astimezone(TZ) + timedelta(days=1)).date().isoformat()
failures = 0


def check(name: str, ok, detail=""):
    global failures
    failures += not ok
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  -> {detail}" if detail != "" and not ok else ""))


def conflict(action, *args) -> str | None:
    """The Conflict message if the action is refused, else None."""
    try:
        action(PATIENT, *args)
    except store.Conflict as err:
        return str(err)
    return None


def clean_up():
    with db.pool().connection() as conn:
        conn.execute("DELETE FROM reminders_sent WHERE patient_id = %s", (PATIENT,))
        conn.execute("DELETE FROM memories WHERE patient_id = %s", (PATIENT,))
        conn.execute("DELETE FROM sessions WHERE patient_id = %s", (PATIENT,))
        conn.execute("DELETE FROM patients WHERE id = %s", (PATIENT,))


def item(summary: str, said: str, **fields) -> dict:
    """One candidate as Gemini would fill it in."""
    return {"kind": "appointment", "summary": summary, "date": TOMORROW, "time": "15:00", "pickup_time": None,
            "who": None, "place": None, "certainty": "definite", "updates_memory_id": None,
            "source_quote": said, **fields}


def propose(said: str, *items: dict) -> list[dict]:
    """What POST /sessions/transcript does, minus Gemini: a session, validated candidates, pending rows."""
    session = store.add_session(PATIENT, said)
    kept, dropped = extraction.validate(list(items), said, NOW, store.current_memories(PATIENT))
    record = {"kept": [{"summary": c["summary"], "warnings": c["warnings"]} for c in kept], "dropped": dropped}
    return store.finish_session(session["id"], PATIENT, "caregiver_typed", record, kept)


def current_ids() -> set[str]:
    return {m["id"] for m in store.current_memories(PATIENT)}


def pending(memory_id: str) -> dict | None:
    return next((m for m in store.pending_memories(PATIENT) if m["id"] == memory_id), None)


def run():
    # 1. The review list: each pending memory with its own warnings
    said = "Her eye doctor appointment is tomorrow at ten."
    eye, lunch = propose(said,
                         item("Eye doctor appointment", said, time="10:00"),
                         item("Lunch with Joan", said, kind="plan", time="12:30", who="Joan",
                              source_quote="Joan is coming for lunch"))
    listed = {m["id"]: m for m in store.pending_memories(PATIENT)}
    check("pending list has both, oldest first", list(listed) == [eye["id"], lunch["id"]], list(listed))
    check("each pending memory has its own warnings",
          listed[eye["id"]]["warnings"] == [] and "word for word" in " ".join(listed[lunch["id"]]["warnings"]),
          {k: v["warnings"] for k, v in listed.items()})
    check("pending memories aren't spoken", not current_ids() & {eye["id"], lunch["id"]})

    # 2. Confirm
    row = store.confirm_memory(PATIENT, eye["id"])
    facts = facts_from(store.current_memories(PATIENT), NOW)["facts"]
    check("confirm makes it confirmed, with confirmed_at",
          row["status"] == "confirmed" and row["confirmed_at"] and row["certainty"] == "definite", row)
    check("a confirmed memory reaches the agent", eye["id"] in current_ids() and "Eye doctor appointment" in facts, facts)

    # 3. Confirm as tentative
    row = store.confirm_memory(PATIENT, lunch["id"], "tentative")
    facts = facts_from(store.current_memories(PATIENT), NOW)["facts"]
    check("certainty 'tentative' confirms it as tentative", row["status"] == "tentative" and row["certainty"] == "tentative", row)
    check("the agent is told it isn't certain", "Lunch with Joan" in facts and "TENTATIVE" in facts, facts)

    # 4. An update replaces the current version
    said = "Anna will pick her up at two thirty for the dentist tomorrow."
    (dentist,) = propose(said, item("Dentist appointment", said, pickup_time="14:30", who="Anna"))
    store.confirm_memory(PATIENT, dentist["id"])
    said = "Change of plans, Anna will pick her up at two instead."
    (update,) = propose(said, item("Dentist appointment", said, pickup_time="14:00", who="Anna",
                                   updates_memory_id=dentist["id"]))
    said = "Actually Anna will come at a quarter to two."
    (competing,) = propose(said, item("Dentist appointment", said, pickup_time="13:45", who="Anna",
                                      updates_memory_id=dentist["id"]))
    card = pending(update["id"])
    check("an update shows what it replaces", card["replaces"]["id"] == dentist["id"] and not card["stale"], card)

    store.confirm_memory(PATIENT, update["id"])
    old = store.memories_by_id([dentist["id"], update["id"]])
    facts = facts_from(store.current_memories(PATIENT), NOW)["facts"]
    check("confirming an update supersedes the old version",
          old[dentist["id"]]["status"] == "superseded" and old[update["id"]]["status"] == "confirmed",
          {k: v["status"] for k, v in old.items()})
    check("only the new version is current", update["id"] in current_ids() and dentist["id"] not in current_ids())
    dentist_lines = [line for line in facts.splitlines() if "Dentist" in line]
    check("the agent hears the new pickup only",
          len(dentist_lines) == 1 and "pickup at" in dentist_lines[0] and dentist_lines[0].endswith("at 2:00 PM"), facts)

    # 5. A competing proposal for the replaced version
    check("a competing update is marked stale", pending(competing["id"])["stale"])
    message = conflict(store.confirm_memory, competing["id"])
    check("confirming it is refused", message and "already changed" in message, message)
    check("and it stays pending", pending(competing["id"]) is not None)

    # 6. Reject
    row = store.reject_memory(PATIENT, competing["id"])
    check("reject makes it rejected", row["status"] == "rejected" and competing["id"] not in current_ids(), row)
    check("rejecting again is refused", conflict(store.reject_memory, competing["id"]))
    check("confirming a rejected memory is refused", conflict(store.confirm_memory, competing["id"]))
    check("rejecting a confirmed memory says to cancel it",
          "cancel" in (conflict(store.reject_memory, update["id"]) or ""))

    # 7. Cancel
    said = "The dentist is now at four."
    (late,) = propose(said, item("Dentist appointment", said, time="16:00", pickup_time="14:00", who="Anna",
                                 updates_memory_id=update["id"]))
    row = store.cancel_memory(PATIENT, update["id"])
    facts = facts_from(store.current_memories(PATIENT), NOW)["facts"]
    check("cancel makes a current plan cancelled", row["status"] == "cancelled", row)
    check("a cancelled plan is never spoken", update["id"] not in current_ids() and "Dentist" not in facts, facts)
    check("receipts still find a cancelled plan",
          store.memories_by_id([update["id"]]).get(update["id"], {}).get("status") == "cancelled")
    check("cancelling a pending memory says to reject it",
          "reject" in (conflict(store.cancel_memory, late["id"]) or ""))
    check("cancelling a replaced version is refused",
          "current version" in (conflict(store.cancel_memory, dentist["id"]) or ""))
    check("an update to a cancelled plan is stale, and can't be confirmed",
          pending(late["id"])["stale"] and conflict(store.confirm_memory, late["id"]))

    # 8. Not found: unknown, or another patient's memory
    with db.pool().connection() as conn:
        other = conn.execute("SELECT id, status FROM memories WHERE patient_id <> %s LIMIT 1", (PATIENT,)).fetchone()
    unknown = str(uuid.uuid4())
    check("an unknown memory is not found",
          store.confirm_memory(PATIENT, unknown) is None and store.cancel_memory(PATIENT, unknown) is None)
    if other:
        found = [store.confirm_memory(PATIENT, str(other["id"])), store.reject_memory(PATIENT, str(other["id"])),
                 store.cancel_memory(PATIENT, str(other["id"]))]
        after = store.memories_by_id([str(other["id"])])[str(other["id"])]["status"]
        check("another patient's memory is not found, and stays untouched",
              found == [None, None, None] and after == other["status"], (found, after))

    # 9. The endpoints
    routes.PATIENT_ID = PATIENT
    client = TestClient(app)
    pin = {"X-Staff-Pin": os.environ["STAFF_PIN"]}
    said = "She has a haircut tomorrow at eleven."
    first, second = propose(said, item("Haircut", said, time="11:00"), item("Manicure", said, time="12:00"))
    check("no PIN is refused (401)", client.post(f"/memories/{first['id']}/confirm").status_code == 401)
    check("a bad ID is refused (422)", client.post("/memories/not-an-id/confirm", headers=pin).status_code == 422)
    check("a bad certainty is refused (422)",
          client.post(f"/memories/{first['id']}/confirm", json={"certainty": "maybe"}, headers=pin).status_code == 422)
    listed = client.get("/memories/pending", headers=pin)
    check("GET /memories/pending lists this patient's pending memories",
          listed.status_code == 200 and {first["id"], second["id"]} <= {m["id"] for m in listed.json()["pending"]},
          listed.status_code)
    r = client.post(f"/memories/{first['id']}/confirm", json={"certainty": "tentative"}, headers=pin)
    check("confirm with a certainty (200)", r.status_code == 200 and r.json()["status"] == "tentative", r.text)
    r = client.post(f"/memories/{second['id']}/confirm", headers=pin)
    check("confirm with no body (200)", r.status_code == 200 and r.json()["status"] == "confirmed", r.text)
    r = client.post(f"/memories/{competing['id']}/confirm", headers=pin)
    check("a refused action is 409, with the reason", r.status_code == 409 and "already rejected" in r.json()["detail"],
          r.text)
    check("an unknown memory is 404", client.post(f"/memories/{unknown}/reject", headers=pin).status_code == 404)
    r = client.post(f"/memories/{second['id']}/cancel", headers=pin)
    check("cancel through the endpoint (200)", r.status_code == 200 and r.json()["status"] == "cancelled", r.text)


def main():
    if not db.enabled():
        sys.exit("DATABASE_URL isn't set: these tests need the database.")
    real_patient = routes.PATIENT_ID
    clean_up()
    with db.pool().connection() as conn:
        conn.execute("INSERT INTO patients (id, name) VALUES (%s, 'Test patient')", (PATIENT,))
    try:
        run()
    finally:
        routes.PATIENT_ID = real_patient
        clean_up()
    with db.pool().connection() as conn:
        left = conn.execute("SELECT (SELECT count(*) FROM memories WHERE patient_id = %s) "
                            "+ (SELECT count(*) FROM patients WHERE id = %s) AS n", (PATIENT, PATIENT)).fetchone()["n"]
    check("the test patient is cleaned up", left == 0, left)
    print("\nAll review checks passed." if not failures else f"\n{failures} review check(s) failed.")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
