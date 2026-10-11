"""Patient reminder tests: reminders the patient asks Vela for ("Remind me at 5 to water my tomato
plants"), from the set_reminder endpoint to the patient screen's reminder list and staff cancel.

Run from backend/:  python scripts/patient_reminders_tests.py            (time rules, database, offline)
                    python scripts/patient_reminders_tests.py --offline  (no database needed)

Uses its own patient ("test-reminders"), created at the start and deleted at the end (also after a
crash, and at the start in case an earlier run was interrupted), so the demo patient is never
touched. No Gemini or ElevenLabs calls. Exits with code 1 if anything fails.
"""

import argparse
import os
import sys
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")
# The staff routes need a PIN; use the team's if it's set, otherwise one that exists only here
os.environ.setdefault("STAFF_PIN", "24680")

from fastapi.testclient import TestClient

from app import db, store
from app.main import app
from app.memory import events, routes
from app.memory.demo import demo_memories
from app.voice import reminders
from app.voice import routes as voice_routes

PATIENT = "test-reminders"
NAME = "Test patient"
# Every module that reads the patient ID when called, pointed at the test patient while it runs
PATIENT_MODULES = (store, events, routes, reminders, voice_routes)
TZ = ZoneInfo(os.getenv("TIMEZONE", "America/New_York"))
failures = 0


def check(name: str, ok, detail=""):
    global failures
    failures += not ok
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  -> {detail}" if detail != "" and not ok else ""))


def refused(**args) -> str:
    """resolve_at's 422 sentence, or "" when it wrongly accepted the input."""
    try:
        reminders.resolve_at(datetime(2026, 10, 10, 13, 20, tzinfo=TZ), **args)
    except ValueError as err:
        return str(err)
    return ""


def time_rules():
    """How a clock time or a number of minutes becomes the moment to say it (no storage)."""
    now = datetime(2026, 10, 10, 13, 20, tzinfo=TZ)  # a Saturday afternoon

    def local(**args):
        return reminders.resolve_at(now, **args).astimezone(TZ)

    at = local(time="17:00")
    check("a time later today is today", at == now.replace(hour=17, minute=0), at)
    check("...and is said back as 'at 5:00 this evening'", reminders.when_words(at, now) == "at 5:00 this evening",
          reminders.when_words(at, now))
    at = local(time="09:00")
    check("a time already past today is tomorrow (the next time it comes)",
          at == (now + timedelta(days=1)).replace(hour=9, minute=0), at)
    check("...and is said back as 'tomorrow at 9:00 in the morning'",
          reminders.when_words(at, now) == "tomorrow at 9:00 in the morning", reminders.when_words(at, now))
    check("the exact current minute counts as past: tomorrow", local(time="13:20").date() == (now + timedelta(days=1)).date())
    check("day 'today' keeps today", local(time="17:00", day="today").date() == now.date())
    check("day 'tomorrow' is tomorrow, even for a time still to come today",
          local(time="17:00", day="TOMORROW") == (now + timedelta(days=1)).replace(hour=17, minute=0))
    check("an empty day is the same as none", local(time="17:00", day="") == local(time="17:00"))

    at = reminders.resolve_at(now, in_minutes=2)
    check("in_minutes counts from now", at == now + timedelta(minutes=2), at)
    check("...and short waits are said as 'in about 2 minutes'", reminders.when_words(at, now, 2) == "in about 2 minutes")
    check("one minute is 'in about a minute', from a string too",
          reminders.when_words(now + timedelta(minutes=1), now, "1") == "in about a minute")
    at = reminders.resolve_at(now, in_minutes="90")
    check("a longer wait is said as a clock time", reminders.when_words(at, now, "90") == "at 2:50 this afternoon",
          reminders.when_words(at, now, "90"))
    check("a time with an empty in_minutes is fine", local(time="17:00", in_minutes="") == local(time="17:00"))

    # The night the clocks go back (America/New_York): 9 AM on Sunday is after the change
    night = datetime(2026, 10, 31, 22, 0, tzinfo=TZ)
    at = reminders.resolve_at(night, time="09:00")
    check("across a clock change the offset is the new day's",
          at.utcoffset() == datetime(2026, 11, 1, 9, 0, tzinfo=TZ).utcoffset() and at.day == 1, at.isoformat())

    for name, args in [
        ("no time at all", {}),
        ("both a time and minutes", {"time": "17:00", "in_minutes": 2}),
        ("a time that isn't HH:MM", {"time": "5pm"}),
        ("an hour past 23", {"time": "24:00"}),
        ("minutes past 59", {"time": "17:60"}),
        ("a single minute digit", {"time": "7:5"}),
        ("an unknown day", {"time": "17:00", "day": "monday"}),
        ("'today' for a time already past", {"time": "09:00", "day": "today"}),
        ("zero minutes", {"in_minutes": 0}),
        ("more than a day of minutes", {"in_minutes": 1441}),
        ("minutes in words", {"in_minutes": "two"}),
        ("negative minutes", {"in_minutes": "-3"}),
    ]:
        check(f"refused: {name}", refused(**args), args)
    check("the refusal for no time tells the agent to ask", "Ask what time" in refused())
    check("the sentence the patient hears",
          reminders.asked_sentence("Rose", "call Joan") == "Rose, you asked me to remind you to call Joan.")


def ask(client: TestClient, **body):
    return client.post("/patient/reminders", json={"task": "", "said": "", "time": "", "day": "", "in_minutes": None,
                                                   **body})


def reminder_ids() -> list[str]:
    return [r["id"] for r in store.patient_reminders(PATIENT, datetime.now(timezone.utc) - timedelta(days=1))]


def flow(client: TestClient, pin: dict, where: str):
    """The same checks with the database and offline (`where` labels them)."""
    now = datetime.now(timezone.utc)

    res = ask(client, task="to call Joan.", said="Remind me in 2 minutes to call Joan", in_minutes=2)
    joan = res.json()
    check(f"{where}: a reminder in 2 minutes is saved", res.status_code == 200, res.text)
    check(f"{where}: ...as a self-reported patient reminder with her words",
          (joan["kind"], joan["source"], joan["status"], joan["all_day"], joan["source_quote"])
          == ("reminder", "patient", "self_reported", False, "Remind me in 2 minutes to call Joan"), joan)
    check(f"{where}: ...with the task cleaned up to be said back", joan["summary"] == "call Joan", joan["summary"])
    at = datetime.fromisoformat(joan["event_at"])
    check(f"{where}: ...due in 2 minutes", timedelta(minutes=1) < at - now < timedelta(minutes=3), joan["event_at"])
    check(f"{where}: ...and said back as 'in about 2 minutes'", joan["when_words"] == "in about 2 minutes",
          joan["when_words"])

    later = (now + timedelta(hours=3)).astimezone(TZ)
    clock = f"{later:%H:%M}"
    res = ask(client, task="water your tomato plants", said="Remind me to water my tomato plants", time=clock)
    plants = res.json()
    check(f"{where}: a clock time with no day is saved for the next time it comes",
          res.status_code == 200 and datetime.fromisoformat(plants["event_at"]).astimezone(TZ).strftime("%H:%M") == clock,
          res.text)

    before = reminder_ids()
    for name, body in [("no time", {"task": "call Joan", "said": "Remind me later to call Joan"}),
                       ("a bad time", {"task": "call Joan", "time": "five"}),
                       ("no task", {"in_minutes": 5})]:
        res = ask(client, **body)
        check(f"{where}: refused with one sentence (422): {name}",
              res.status_code == 422 and isinstance(res.json()["detail"], str), res.text)
    check(f"{where}: ...and nothing refused was saved", reminder_ids() == before, reminder_ids())

    # Never a fact: not on the patient screen's plans, not in what the agent looks up
    current = [m["id"] for m in client.get("/memories/current").json()["memories"]]
    facts = client.get("/voice/facts").json()
    check(f"{where}: never in the current memories (patient screen)", joan["id"] not in current, current)
    check(f"{where}: never in the agent's facts (/voice/facts, get_memories)",
          # Not just "Joan": the demo has a lunch with her
          joan["id"] not in facts["memory_ids"] and "call Joan" not in facts["facts"] and "tomato" not in facts["facts"],
          facts)
    client.post("/patient/statements", json={"text": "I had lunch", "kind": "meal"})
    told = [s["text"] for s in client.get("/dashboard", headers=pin).json()["self_reported_today"]]
    check(f"{where}: the dashboard's self-reports list what she did, not what she asked to be reminded of",
          told == ["I had lunch"], told)

    # Said at its time, through the patient screen's existing reminder list
    due = {r["id"]: r for r in client.get("/reminders/upcoming").json()["reminders"]}
    said = due.get(f"{joan['id']}-at")
    check(f"{where}: in /reminders/upcoming once, with an '-at' ID",
          said is not None and sum(r.get("memory_id") == joan["id"] for r in due.values()) == 1, list(due))
    check(f"{where}: ...at the time it was set", said and datetime.fromisoformat(said["at"]) == at, said)
    check(f"{where}: ...with the right words",
          # Offline the name is always the demo's (store.patient_name)
          said and said["text"] == f"{store.patient_name(PATIENT)}, you asked me to remind you to call Joan.", said)
    late = [r["id"] for r in reminders.due_reminders(at + timedelta(minutes=8))]
    gone = [r["id"] for r in reminders.due_reminders(at + timedelta(minutes=15))]
    check(f"{where}: still due a few minutes late (a slow poll or a reload)", f"{joan['id']}-at" in late, late)
    check(f"{where}: ...but not long after", f"{joan['id']}-at" not in gone, gone)

    # Staff: list and cancel
    listed = client.get("/patient/reminders", headers=pin)
    check(f"{where}: staff list them, soonest first",
          [r["id"] for r in listed.json()["reminders"]] == [joan["id"], plants["id"]], listed.text)
    check(f"{where}: the staff list needs the PIN (401)", client.get("/patient/reminders").status_code == 401)
    check(f"{where}: cancel needs the PIN (401)",
          client.post(f"/patient/reminders/{joan['id']}/cancel").status_code == 401)
    res = client.post(f"/patient/reminders/{joan['id']}/cancel", headers=pin)
    check(f"{where}: staff cancel one", res.status_code == 200 and res.json()["status"] == "cancelled", res.text)
    again = client.post(f"/patient/reminders/{joan['id']}/cancel", headers=pin)
    check(f"{where}: cancelling twice is 409", again.status_code == 409, again.text)
    check(f"{where}: an unknown or malformed ID is 404",
          client.post(f"/patient/reminders/{uuid.uuid4()}/cancel", headers=pin).status_code == 404
          and client.post("/patient/reminders/not-an-id/cancel", headers=pin).status_code == 404)
    check(f"{where}: a cancelled reminder is never said",
          all(r.get("memory_id") != joan["id"] for r in reminders.due_reminders(at)), reminders.due_reminders(at))
    check(f"{where}: ...and leaves the staff list",
          [r["id"] for r in client.get("/patient/reminders", headers=pin).json()["reminders"]] == [plants["id"]])
    return plants


def run(client: TestClient, pin: dict):
    store.reset_demo(PATIENT, NAME, demo_memories(datetime.now(timezone.utc)))
    plants = flow(client, pin, "database")

    # Cancel stays as narrow as it was, both ways
    plan = next(m for m in store.current_memories(PATIENT) if m["status"] == "confirmed")
    res = client.post(f"/patient/reminders/{plan['id']}/cancel", headers=pin)
    check("database: the reminder cancel can't cancel a caregiver plan (404)", res.status_code == 404, res.text)
    res = client.post(f"/memories/{plants['id']}/cancel", headers=pin)
    check("database: the plan cancel still refuses a patient reminder (409)", res.status_code == 409, res.text)

    result = store.reset_demo(PATIENT, NAME, demo_memories(datetime.now(timezone.utc)))
    check("database: the demo reset removes her reminders", reminder_ids() == [], result)


def run_without_database(client: TestClient, pin: dict):
    """The same, as JSON files in a temporary folder, as when DATABASE_URL isn't set."""
    real_enabled, real_dir = db.enabled, store.DATA_DIR
    with tempfile.TemporaryDirectory() as folder:
        db.enabled, store.DATA_DIR = (lambda: False), Path(folder)
        store._demo_rows = None
        try:
            flow(client, pin, "offline")
            # The store's reset, not POST /demo/reset: that one also replaces the life story in Snowflake
            result = store.reset_demo(PATIENT, NAME, demo_memories(datetime.now(timezone.utc)))
            check("offline: the demo reset clears her reminders",
                  result["removed"]["patient_reminders"] == 2 and reminder_ids() == [], result)
        finally:
            db.enabled, store.DATA_DIR = real_enabled, real_dir
            store._demo_rows = None


def clean_up():
    with db.pool().connection() as conn:
        for table in ("reminders_sent", "interactions", "alerts", "memories", "sessions"):
            conn.execute(f"DELETE FROM {table} WHERE patient_id = %s", (PATIENT,))
        conn.execute("DELETE FROM patients WHERE id = %s", (PATIENT,))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", action="store_true", help="skip the database part")
    args = parser.parse_args()
    if not args.offline and not db.enabled():
        sys.exit("DATABASE_URL isn't set: run with --offline, or set it for the database part.")

    time_rules()
    real = {module: module.PATIENT_ID for module in PATIENT_MODULES}
    client = TestClient(app)
    pin = {"X-Staff-Pin": os.environ["STAFF_PIN"]}
    try:
        for module in PATIENT_MODULES:
            module.PATIENT_ID = PATIENT
        if not args.offline:
            clean_up()
            run(client, pin)
        run_without_database(client, pin)
    finally:
        for module, value in real.items():
            module.PATIENT_ID = value
        if not args.offline:
            clean_up()
    if not args.offline:
        with db.pool().connection() as conn:
            left = conn.execute("SELECT count(*) AS n FROM memories WHERE patient_id = %s", (PATIENT,)).fetchone()["n"]
        check("the test patient is cleaned up", left == 0, left)
    print("\nAll patient reminder checks passed." if not failures else f"\n{failures} patient reminder check(s) failed.")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
