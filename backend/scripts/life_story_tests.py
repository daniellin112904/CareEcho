"""Life story tests: the Snowflake client, the endpoints, and real searches.

Run from backend/:  python scripts/life_story_tests.py            (everything)
                    python scripts/life_story_tests.py --offline  (free: no Snowflake)

- Offline: Snowflake is replaced by a stand-in (httpx.MockTransport), so failures, slow answers,
  and the 202 "still running" path can be tested for free.
- Live: real Snowflake, with its own patient ("test-life-story"), whose passages are removed at
  the start and the end. It prints each question's scores, to check MIN_RERANKER_SCORE in
  app/memory/life_story.py.
- Demo: read-only searches of Rose's real life story (app/memory/life_story_demo.json, loaded
  with scripts/seed_life_story.py), with the questions the demo relies on. Skipped if it isn't
  loaded.

Exit code: 0 if everything passed, 1 if anything failed, 2 if nothing failed but the live part
couldn't run (Snowflake isn't set up in backend/.env).
"""

import argparse
import json
import os
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")
os.environ.setdefault("STAFF_PIN", "24680")

import httpx
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.memory import life_story, routes

PATIENT = "test-life-story"
failures = 0


def check(name: str, ok, detail=""):
    global failures
    failures += not ok
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  -> {detail}" if detail != "" and not ok else ""))


# Offline: a stand-in Snowflake


FAKE_SETTINGS = {"SNOWFLAKE_ACCOUNT": "org-fake_account", "SNOWFLAKE_PAT": "fake-token", "SNOWFLAKE_WAREHOUSE": "WH",
                 "SNOWFLAKE_DATABASE": "DB", "SNOWFLAKE_SCHEMA": "SCH", "SNOWFLAKE_SEARCH_SERVICE": "SVC"}


def result(*rows, scores=None):
    """A Cortex Search response: rows as (id, passage, sensitive, reranker_score)."""
    return {"results": [{"ID": i, "TOPIC": "work", "PASSAGE": text, "PEOPLE": "", "SENSITIVE": str(s).lower(),
                         "@scores": {"reranker_score": score, "cosine_similarity": 0.2}}
                        for i, text, s, score in rows], "request_id": "r"}


def table(columns, rows):
    """A SQL API response: columns as (name, type), rows as lists of strings."""
    return {"resultSetMetaData": {"rowType": [{"name": n, "type": t} for n, t in columns]}, "data": rows,
            "statementHandle": "h", "message": "Statement executed successfully."}


class FakeSnowflake:
    """Answers each request from a queue of (status, json) or an exception, and records them."""

    def __init__(self):
        self.answers, self.requests = [], []

    def __call__(self, request: httpx.Request):
        self.requests.append(request)
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        status, body = answer
        return httpx.Response(status, json=body)


def offline():
    real_settings = {k: os.environ.get(k) for k in FAKE_SETTINGS}
    real_http = life_story._http
    fake = FakeSnowflake()
    os.environ.update(FAKE_SETTINGS)
    life_story._http = httpx.Client(transport=httpx.MockTransport(fake), base_url="https://fake.snowflakecomputing.com")
    client, pin = TestClient(app), {"X-Staff-Pin": os.environ["STAFF_PIN"]}
    try:
        urls = []
        for value in ("org-fake_account", "abc123.us-east4.gcp.snowflakecomputing.com", "https://x.snowflakecomputing.com/"):
            os.environ["SNOWFLAKE_ACCOUNT"] = value
            urls.append(life_story._base_url())
        os.environ["SNOWFLAKE_ACCOUNT"] = FAKE_SETTINGS["SNOWFLAKE_ACCOUNT"]
        check("account URLs: org-account (underscore to hyphen), host, or full URL",
              urls == ["https://org-fake-account.snowflakecomputing.com",
                       "https://abc123.us-east4.gcp.snowflakecomputing.com", "https://x.snowflakecomputing.com"], urls)

        fake.answers = [(200, result(("a", "Rose was a teacher.", False, -8.5), ("b", "Rose had a dog.", False, -11.2)))]
        found = life_story.lookup(PATIENT, "What did I do for work?")
        sent = json.loads(fake.requests[-1].content)
        check("search asks for this patient only, 3 results, the right columns",
              fake.requests[-1].url.path == "/api/v2/databases/DB/schemas/SCH/cortex-search-services/SVC:query"
              and sent["filter"] == {"@eq": {"PATIENT_ID": PATIENT}} and sent["limit"] == 3
              and sent["columns"] == ["ID", "TOPIC", "PASSAGE", "PEOPLE", "SENSITIVE"], sent)
        check("only passages that answer are kept (reranker cutoff)",
              found == {"passages": "- Rose was a teacher.", "ids": ["a"]}, found)

        fake.answers = [(200, result(("b", "Rose taught for 31 years.", False, -9.4), ("a", "Rose taught in Flushing.", False, -5.0)))]
        order = life_story.lookup(PATIENT, "What did I do for work?")["ids"]
        check("the best answer comes first, whatever Snowflake's order", order == ["a", "b"], order)

        fake.answers = [(200, result(("w", "Rose's husband Walter died in 2015.", True, -7.0)))]
        found = life_story.lookup(PATIENT, "Where is Walter?")["passages"]
        check("a sensitive passage is marked for the agent", found.endswith(life_story.SENSITIVE_NOTE), found)

        fake.answers = [(200, result(("b", "Rose had a dog.", False, -11.4)))]
        check("nothing that answers: NO_LIFE_STORY",
              life_story.lookup(PATIENT, "What's the capital of France?")["passages"] == life_story.NO_LIFE_STORY)

        fake.answers = [(500, {"message": "boom"}), httpx.ReadTimeout("slow")]
        failed = [life_story.lookup(PATIENT, "q")["passages"] for _ in range(2)]
        check("a Snowflake error or a slow answer: LIFE_STORY_FAILED, never an error to the agent",
              failed == [life_story.LIFE_STORY_FAILED] * 2, failed)

        fake.answers = [(202, {"statementHandle": "h1", "message": "Asynchronous execution in progress."}),
                        (200, table([("number of rows inserted", "fixed")], [["1"]]))]
        added = life_story.add_passage(PATIENT, life_story.Passage(topic="pets", passage="Rose had a dog named Biscuit.",
                                                                    said_by="Anna, daughter", sensitive=True))
        insert = json.loads(fake.requests[-2].content)
        check("adding binds every value, true/false as BOOLEAN",
              insert["bindings"]["7"] == {"type": "BOOLEAN", "value": "true"}
              and insert["bindings"]["2"] == {"type": "TEXT", "value": PATIENT} and insert["warehouse"] == "WH", insert)
        check("a statement still running (202) is polled to the end",
              fake.requests[-1].method == "GET" and fake.requests[-1].url.path == "/api/v2/statements/h1"
              and added["id"] and added["sensitive"] is True)

        fake.answers = [(200, table([("ID", "text"), ("SENSITIVE", "boolean"), ("CREATED_AT", "timestamp_tz")],
                                    [["p1", "false", "1791671080.373000000 1020"]]))]
        rows = life_story.list_passages(PATIENT)
        check("rows come back as Python values (true/false, times with their offset)",
              rows == [{"id": "p1", "sensitive": False, "created_at": "2026-10-10T15:24:40.373000-07:00"}], rows)

        fake.answers = [(200, table([("number of rows deleted", "fixed")], [["0"]]))]
        check("deleting a passage that isn't there says so", life_story.delete_passage(PATIENT, "x") is False)

        fake.answers = [(422, {"message": "SQL compilation error: invalid identifier"})]
        try:
            life_story.list_passages(PATIENT)
            message = None
        except life_story.LifeStoryError as err:
            message = str(err)
        check("a Snowflake error carries Snowflake's message", message and "invalid identifier" in message, message)

        refused = []
        for fields in ({"topic": "work", "passage": "Rose takes her blood pressure pills daily.", "said_by": "x"},
                       {"topic": "health", "passage": "Rose likes long walks by the sea.", "said_by": "x"},
                       {"topic": "work", "passage": "short", "said_by": "x"}):
            try:
                life_story.Passage(**fields)
            except ValidationError as err:
                refused.append(err.errors()[0]["msg"])
        check("medicine, unknown topics, and too-short passages are refused",
              len(refused) == 3 and "medicine" in refused[0], refused)

        fake.answers = [(500, {"message": "Snowflake is down"})]
        r = client.get("/life-story/passages", headers=pin)
        check("staff see Snowflake's errors as 502", r.status_code == 502 and "Snowflake is down" in r.json()["detail"],
              r.text)

        for name in FAKE_SETTINGS:
            os.environ[name] = ""
        agent = client.get("/life-story", params={"q": "Where did I grow up?"})
        staff = client.get("/life-story/passages", headers=pin)
        check("without Snowflake: the agent hears LIFE_STORY_FAILED, staff get 503",
              agent.status_code == 200 and agent.json()["passages"] == life_story.LIFE_STORY_FAILED
              and staff.status_code == 503, (agent.text, staff.status_code))
        check("an empty question is refused (422)", client.get("/life-story", params={"q": ""}).status_code == 422)
    finally:
        life_story._http = real_http
        for name, value in real_settings.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


# Live: real Snowflake


PASSAGES = {
    "work": ("work", "Rose worked as a second-grade teacher at Lincoln Elementary School in Providence for 32 years.", False),
    "dog": ("pets", "When her children were small, Rose had a golden retriever named Biscuit who loved the beach.", False),
    "song": ("music", "Rose loves Frank Sinatra. 'The Way You Look Tonight' was the first dance at her wedding.", False),
    "home": ("childhood", "Rose grew up in Providence, Rhode Island, in a yellow house on Elm Street with two brothers.", False),
    "walter": ("family", "Rose's husband Walter died in 2015, after 48 years of marriage.", True),
}
# Question, and the passage that must answer it first (None: the life story can't answer it)
QUESTIONS = [
    ("What did I do for work?", "work"),
    ("Did I ever have a dog?", "dog"),
    ("What song did we dance to at my wedding?", "song"),
    ("Where did I grow up?", "home"),
    ("Where is Walter?", "walter"),
    ("What is the capital of France?", None),
    ("When is Anna picking me up today?", None),
]


def live():
    client, pin = TestClient(app), {"X-Staff-Pin": os.environ["STAFF_PIN"]}
    real_patient = routes.PATIENT_ID
    routes.PATIENT_ID = PATIENT
    life_story.replace_passages(PATIENT, [])
    try:
        ids = {}
        for key, (topic, text, sensitive) in PASSAGES.items():
            r = client.post("/life-story/passages", headers=pin,
                            json={"topic": topic, "passage": text, "people": "", "said_by": "Life story tests",
                                  "sensitive": sensitive})
            ids[key] = r.json().get("id") if r.status_code == 201 else None
        check("staff add passages (201)", all(ids.values()), ids)
        listed = client.get("/life-story/passages", headers=pin).json()["passages"]
        check("staff list them, with real values",
              {p["id"] for p in listed} == set(ids.values())
              and any(p["sensitive"] is True for p in listed) and all(p["created_at"] for p in listed), len(listed))

        started = time.monotonic()
        while time.monotonic() - started < 180:
            if life_story.lookup(PATIENT, "What did I do for work?")["ids"]:
                break
            time.sleep(10)
        print(f"  (searchable after about {time.monotonic() - started:.0f} seconds)")

        print("  question                                   top passage  reranker  cosine  answered")
        for question, expected in QUESTIONS:
            top = (life_story.search(PATIENT, question) or [{}])[0]
            scores = top.get("scores", {})
            found = client.get("/life-story", params={"q": question}).json()
            answered = next((k for k, v in ids.items() if found["ids"] and found["ids"][0] == v), None)
            print(f"  {question:42} {next((k for k, v in ids.items() if v == top.get('id')), '-'):12} "
                  f"{scores.get('reranker_score', 0):8.2f} {scores.get('cosine_similarity', 0):7.3f}  {answered}")
            if expected is None:
                check(f"can't answer \"{question}\": NO_LIFE_STORY", found["passages"] == life_story.NO_LIFE_STORY, found)
            else:
                check(f"\"{question}\" finds the {expected} passage first", answered == expected, found)
        sensitive = client.get("/life-story", params={"q": "Where is Walter?"}).json()["passages"]
        check("the sensitive passage reaches the agent marked", life_story.SENSITIVE_NOTE in sensitive, sensitive)
        other = life_story.lookup("demo", "What did I do for work?")
        check("another patient never sees these passages", not set(other["ids"]) & set(ids.values()), other)

        r = client.post("/life-story/passages", headers=pin,
                        json={"topic": "work", "passage": "Rose takes two pills every morning.", "said_by": "x"})
        check("medicine is refused (422)", r.status_code == 422 and "medicine" in r.text, r.text)
        check("no PIN: refused (401)", client.get("/life-story/passages").status_code == 401)
        check("deleting a passage (204), then again (404), and a bad ID (422)",
              client.delete(f"/life-story/passages/{ids['dog']}", headers=pin).status_code == 204
              and client.delete(f"/life-story/passages/{ids['dog']}", headers=pin).status_code == 404
              and client.delete("/life-story/passages/nope", headers=pin).status_code == 422)
        check("deleting another patient's passage is not found",
              life_story.delete_passage("demo", ids["work"]) is False)
    finally:
        routes.PATIENT_ID = real_patient
        life_story.replace_passages(PATIENT, [])
    check("the test passages are cleaned up", life_story.list_passages(PATIENT) == [])


# Demo: Rose's real life story


DEMO_FILE = Path(__file__).parent.parent / "app" / "memory" / "life_story_demo.json"
# Question, and the sections whose passage may come first (empty: nothing may be told). The
# first four are the demo questions from the life story document. Plan questions about a person
# ("Is Joan coming for lunch tomorrow?") aren't here: they match that person's paragraph, and the
# agent's rule that plans only come from memories covers them (decision 63 in the docs).
DEMO_QUESTIONS = [
    ("What did I do for work?", {"Career", "School and becoming a teacher", "Favorite teaching memories"}),
    ("Tell me about Joe.", {"Husband", "Talking about Joe"}),
    ("Where does Mark live?", {"Son Mark"}),
    ("Where am I from?", {"Basics", "Childhood"}),
    ("Who is Joan?", {"Friend Joan"}),
    ("How many grandchildren do I have?", {"Grandchildren"}),
    ("What music do I like?", {"Music Rose loves"}),
    ("Who is Tito?", {"Brother Tito"}),
    ("Is Anna bringing the dog?", set()),
    ("Did I take my pills this morning?", set()),
    ("What is the weather today?", set()),
    ("What is the capital of France?", set()),
]


def demo():
    sections = {e["passage"]: e["section"] for e in json.loads(DEMO_FILE.read_text(encoding="utf-8"))}
    loaded = {p["passage"] for p in life_story.list_passages("demo")}
    if not loaded or not loaded <= set(sections):
        print("NOT RUN  demo checks: Rose's life story isn't loaded (run scripts/seed_life_story.py)")
        return
    for question, expected in DEMO_QUESTIONS:
        found = life_story.lookup("demo", question)
        first = found["passages"].splitlines()[0][2:].removesuffix(life_story.SENSITIVE_NOTE) if found["ids"] else None
        if expected:
            check(f"Rose's life story: \"{question}\" -> {sections.get(first)}", sections.get(first) in expected,
                  found["passages"][:200])
        else:
            check(f"Rose's life story: \"{question}\" -> nothing", found["passages"] == life_story.NO_LIFE_STORY,
                  found["passages"][:200])
    joe = life_story.lookup("demo", "Where is Joe?")["passages"]
    check("Rose's life story: Joe's passages reach the agent marked sensitive", life_story.SENSITIVE_NOTE in joe, joe[:200])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", action="store_true", help="only the free checks, no Snowflake")
    args = parser.parse_args()
    offline()
    skipped = False
    if not args.offline:
        if life_story.enabled():
            live()
            demo()
        else:
            skipped = True
            print("NOT RUN  live checks: Snowflake isn't set up in backend/.env")
    print("\nAll life story checks passed." if not failures and not skipped
          else f"\n{failures} life story check(s) failed." if failures else "\nOffline checks passed; live checks didn't run.")
    sys.exit(1 if failures else 2 if skipped else 0)


if __name__ == "__main__":
    main()
