"""Records tests: answers, alerts, self-reports, family messages, and "Remind now" in Tiger Data,
plus the dashboard, memory history, and demo reset. Then the same basics without a database.

Run from backend/:  python scripts/records_tests.py

Uses its own patient ("test-records"), created at the start and deleted at the end (also after
a crash, and at the start in case an earlier run was interrupted), so the demo patient is never
touched. No Gemini or ElevenLabs calls. Exits with code 1 if anything fails.
"""

import os
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")
# The staff routes need a PIN; use the team's if it's set, otherwise one that exists only here
os.environ.setdefault("STAFF_PIN", "24680")

from fastapi.testclient import TestClient

from app import db, store
from app.main import app
from app.memory import events, extraction, routes
from app.memory.demo import demo_memories
from app.voice import messages, reminders

PATIENT = "test-records"
# Every module that reads the patient ID when called, pointed at the test patient while it runs
PATIENT_MODULES = (store, events, routes, reminders, messages)
NOW = datetime.now(timezone.utc)
# What a demo reset should leave: every demo row, and the ones Vela may say
DEMO_ROWS = len(demo_memories(NOW))
DEMO_CURRENT = sum(m["status"] in ("confirmed", "tentative") for m in demo_memories(NOW))
failures = 0
message_ids: list[str] = []


def check(name: str, ok, detail=""):
    global failures
    failures += not ok
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  -> {detail}" if detail != "" and not ok else ""))


def clean_up():
    with db.pool().connection() as conn:
        for table in ("reminders_sent", "interactions", "alerts", "family_messages", "memories", "sessions"):
            conn.execute(f"DELETE FROM {table} WHERE patient_id = %s", (PATIENT,))
        conn.execute("DELETE FROM patients WHERE id = %s", (PATIENT,))
    for message_id in message_ids:
        messages.audio_path(message_id).unlink(missing_ok=True)


def count(table: str) -> int:
    with db.pool().connection() as conn:
        return conn.execute(f"SELECT count(*) AS n FROM {table} WHERE patient_id = %s", (PATIENT,)).fetchone()["n"]


def current(summary: str) -> dict:
    return next(m for m in store.current_memories(PATIENT) if m["summary"] == summary)


def answer(client, question, reply, **fields):
    body = {"topic": "", "question": question, "answer": reply, "memory_ids": [], "answered": True, **fields}
    return client.post("/interactions", json=body)


def run(client: TestClient, pin: dict):
    # Reset gives the test patient the demo memories (and checks the reset itself, starting empty)
    result = store.reset_demo(PATIENT, "Test patient", demo_memories(NOW))
    check("reset seeds the memories", result["memories"] == DEMO_ROWS and len(store.current_memories(PATIENT)) == DEMO_CURRENT, result)
    dentist = current("Dentist appointment")

    # Answers (the interactions hypertable), with their topic set by code
    r = answer(client, "When is Anna picking me up?", "Anna is picking you up at two thirty for the dentist.",
               topic="pickup time", memory_ids=[dentist["id"], "mock-1"])
    row = r.json()
    check("an answer is saved in the hypertable", r.status_code == 200 and count("interactions") == 1, r.text)
    check("IDs that aren't UUIDs are left out of memory_ids", row["memory_ids"] == [dentist["id"]], row["memory_ids"])
    check("its topic is the memory it used, not the agent's words", row["topic"] == "Dentist appointment", row["topic"])
    topics = [answer(client, *args, **fields).json()["topic"] for args, fields in [
        (("Is Anna bringing the dog?", "I'm not sure, so I've asked your care team."), {"answered": False}),
        (("I fell.", "I've told your care team right away."), {"urgent": True}),
        (("Can you play music?", "I can't play music, but we can talk about songs."), {}),
        (("What's for lunch?", "I don't know that one."), {"topic": "lunch"}),
    ]]
    check("other topics: care team, help, the agent's topic, or Other",
          topics == ["Asked the care team", "Asked for help", "Other", "lunch"], topics)
    listed = client.get("/interactions", headers=pin).json()["interactions"]
    check("GET /interactions: newest first, with receipts",
          len(listed) == 5 and listed[-1]["sources"][0]["summary"] == "Dentist appointment", len(listed))

    # What the patient said they did: a self-reported memory, never a fact
    r = client.post("/patient/statements", json={"text": "I took my pills", "kind": "medication"})
    statement = r.json()
    check("a self-report is saved as a self_reported memory",
          r.status_code == 200 and statement["status"] == "self_reported" and statement["text"] == "I took my pills",
          r.text)
    check("it's never spoken", statement["id"] not in {m["id"] for m in store.current_memories(PATIENT)})

    # Alerts
    r = client.post("/alerts", json={"kind": "missing_info", "message": "Rose asked about the dog"})
    alert = r.json()
    status = client.get(f"/alerts/{alert['id']}/status").json()
    check("an alert is saved, open", r.status_code == 200 and status == {"resolved": False}, status)
    check("a status check for a bad ID is 404, not an error",
          client.get("/alerts/not-an-id/status").status_code == 404)
    check("resolving it (204), then it reads resolved",
          client.post(f"/alerts/{alert['id']}/resolve", headers=pin).status_code == 204
          and client.get(f"/alerts/{alert['id']}/status").json() == {"resolved": True})
    check("resolving an unknown alert is 404",
          client.post(f"/alerts/{uuid.uuid4()}/resolve", headers=pin).status_code == 404)
    client.post("/alerts", json={"kind": "help_requested", "message": "Rose said: I fell"})
    alerts = client.get("/alerts", headers=pin).json()["alerts"]
    check("open alerts come first", [a["resolved"] for a in alerts] == sorted(a["resolved"] for a in alerts),
          [a["resolved"] for a in alerts])

    # The dashboard: question counts from the continuous aggregate, which is real-time
    board = client.get("/dashboard", headers=pin).json()
    by_topic = {t["topic"]: t["asks"] for t in board["by_topic"]}
    check("dashboard counts today's questions by topic, right away",
          board["asks_today"] == 5 and by_topic.get("Dentist appointment") == 1 and by_topic.get("Asked for help") == 1,
          board["by_topic"])
    check("dashboard has the last 24 hours, every hour",
          len(board["by_hour"]) == 24 and sum(h["asks"] for h in board["by_hour"]) == 5, board["by_hour"][-2:])
    check("dashboard counts open alerts by kind",
          board["open_alerts"] == {"help_requested": 1, "missing_info": 0, "self_reported_med": 1}, board["open_alerts"])
    check("dashboard lists today's self-reports",
          [s["text"] for s in board["self_reported_today"]] == ["I took my pills"], board["self_reported_today"])

    # Family messages: database IDs have dashes, the audio file is named by the hex digits
    message = messages.add_message("Anna", "voice-for-tests", "Hi Mom, see you soon.", b"ID3 test audio")
    message_ids.append(message["id"])
    latest = client.get("/family-messages/latest").json()["message"]
    check("a family message is saved", latest and latest["id"] == message["id"] and "-" in message["id"], latest)
    audio = client.get(f"/family-messages/{message['id']}/audio")
    audio_hex = client.get(f"/family-messages/{uuid.UUID(message['id']).hex}/audio")
    check("its audio plays, by either form of the ID",
          audio.status_code == 200 and audio.content == b"ID3 test audio" and audio_hex.status_code == 200)
    check("a bad message ID is 404", client.get("/family-messages/not-an-id/audio").status_code == 404)
    check("deleting it (204) removes the record and the audio",
          client.delete(f"/family-messages/{message['id']}", headers=pin).status_code == 204
          and client.get("/family-messages/latest").json()["message"] is None
          and not messages.audio_path(message["id"]).exists())

    # "Remind now"
    r = client.post("/reminders/now", json={"memory_id": dentist["id"]}, headers=pin)
    upcoming = client.get("/reminders/upcoming").json()["reminders"]
    check("Remind now is saved and shows up as due",
          r.status_code == 200 and any(u["id"] == r.json()["id"] for u in upcoming), r.text)

    # History: a chain of three versions, the newest cancelled
    said = "Change of plans, Anna will pick her up at two instead."
    session = store.add_session(PATIENT, said)
    kept, _ = extraction.validate(
        [{"kind": "appointment", "summary": "Dentist appointment", "date": dentist["event_at"][:10], "time": "15:00",
          "pickup_time": "14:00", "who": "Anna", "place": None, "certainty": "definite",
          "updates_memory_id": dentist["id"], "source_quote": said}], said, NOW, store.current_memories(PATIENT))
    (update,) = store.finish_session(session["id"], PATIENT, "caregiver_typed", {"kept": []}, kept)
    store.confirm_memory(PATIENT, update["id"])
    store.cancel_memory(PATIENT, update["id"])
    history = client.get(f"/memories/{dentist['id']}/history", headers=pin).json()["versions"]
    check("history: every version, oldest first, from the middle of the chain",
          [v["status"] for v in history] == ["superseded", "superseded", "cancelled"]
          and history[1]["id"] == dentist["id"] and history[2]["id"] == update["id"],
          [v["status"] for v in history])
    check("history from the newest version is the same chain",
          [v["id"] for v in client.get(f"/memories/{update['id']}/history", headers=pin).json()["versions"]]
          == [v["id"] for v in history])
    check("history: unknown is 404, a bad ID is 422",
          client.get(f"/memories/{uuid.uuid4()}/history", headers=pin).status_code == 404
          and client.get("/memories/nope/history", headers=pin).status_code == 422)

    # Answers from two hours ago, which the aggregate has stored as totals (materialized): only a
    # recount removes those, so the reset below must recount, not just delete the rows
    with db.pool().connection() as conn:
        for _ in range(2):
            conn.execute("INSERT INTO interactions (ts, patient_id, topic, question, answer, answered) "
                         "VALUES (now() - interval '2 hours', %s, 'Earlier', 'q', 'a', true)", (PATIENT,))
    store._refresh_question_counts()
    earlier = sum(h["asks"] for h in client.get("/dashboard", headers=pin).json()["by_hour"])
    check("answers from earlier hours are counted (stored totals)", earlier == 7, earlier)

    # Demo reset through the endpoint: everything but family messages starts over
    kept_message = messages.add_message("Anna", "voice-for-tests", "Still here after a reset.", b"ID3")
    message_ids.append(kept_message["id"])
    r = client.post("/demo/reset", headers=pin)
    removed = r.json().get("removed", {})
    board = client.get("/dashboard", headers=pin).json()
    check("demo reset removes answers, alerts, sessions, and Remind now records",
          r.status_code == 200 and removed.get("interactions") == 7 and removed.get("alerts") == 3
          and removed.get("reminders_sent") == 1 and removed.get("sessions") == 1
          and count("interactions") == count("alerts") == count("sessions") == 0, removed)
    check("after a reset the dashboard is empty at once (aggregate recounted)",
          board["asks_today"] == 0 and sum(h["asks"] for h in board["by_hour"]) == 0, board["asks_today"])
    check("after a reset the demo memories are back, and family messages are kept",
          len(store.current_memories(PATIENT)) == DEMO_CURRENT
          and client.get("/family-messages/latest").json()["message"]["id"] == kept_message["id"])
    # The reset's recount must leave the hour in progress live (a recount that included it
    # froze that hour's count until the hour ended: found by this suite, October 10, 2026)
    answer(client, "When is Anna picking me up?", "Anna is picking you up at two thirty.",
           memory_ids=[current("Dentist appointment")["id"]])
    after = client.get("/dashboard", headers=pin).json()["asks_today"]
    check("an answer logged right after a reset counts at once (the current hour stays live)", after == 1, after)
    check("no PIN: the dashboard and reset are refused (401)",
          client.get("/dashboard").status_code == 401 and client.post("/demo/reset").status_code == 401)


def run_without_database(client: TestClient, pin: dict):
    """The same records as JSON files in a temporary folder, as when DATABASE_URL isn't set."""
    real_enabled, real_dir = db.enabled, store.DATA_DIR
    with tempfile.TemporaryDirectory() as folder:
        db.enabled, store.DATA_DIR = (lambda: False), Path(folder)
        store._demo_rows = None
        try:
            dentist = current("Dentist appointment")
            row = answer(client, "When is Anna picking me up?", "Anna is picking you up at two thirty.",
                         memory_ids=[dentist["id"], "mock-1"]).json()
            check("offline: answers are saved, with a topic and only real IDs",
                  row["topic"] == "Dentist appointment" and row["memory_ids"] == [dentist["id"]], row)
            alert = client.post("/alerts", json={"kind": "missing_info", "message": "offline"}).json()
            check("offline: alerts work, and a bad ID is 404",
                  client.get(f"/alerts/{alert['id']}/status").json() == {"resolved": False}
                  and client.get("/alerts/not-an-id/status").status_code == 404)
            client.post("/patient/statements", json={"text": "I had lunch", "kind": "meal"})
            board = client.get("/dashboard", headers=pin).json()
            check("offline: the dashboard counts from the JSON records",
                  board["asks_today"] == 1 and board["open_alerts"]["missing_info"] == 1
                  and len(board["self_reported_today"]) == 1, board)
            result = client.post("/demo/reset", headers=pin).json()
            check("offline: demo reset clears the JSON records",
                  result["removed"] == {"interactions": 1, "statements": 1, "alerts": 1, "reminders_now": 0,
                                        "patient_reminders": 0}
                  and client.get("/dashboard", headers=pin).json()["asks_today"] == 0, result)
        finally:
            db.enabled, store.DATA_DIR = real_enabled, real_dir
            store._demo_rows = None


def main():
    if not db.enabled():
        sys.exit("DATABASE_URL isn't set: these tests need the database.")
    real = {module: module.PATIENT_ID for module in PATIENT_MODULES}
    clean_up()
    client = TestClient(app)
    pin = {"X-Staff-Pin": os.environ["STAFF_PIN"]}
    try:
        for module in PATIENT_MODULES:
            module.PATIENT_ID = PATIENT
        run(client, pin)
        run_without_database(client, pin)
    finally:
        for module, value in real.items():
            module.PATIENT_ID = value
        clean_up()
    left = sum(count(t) for t in ("memories", "interactions", "alerts", "family_messages", "sessions"))
    check("the test patient is cleaned up", left == 0, left)
    print("\nAll records checks passed." if not failures else f"\n{failures} records check(s) failed.")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
