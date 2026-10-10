"""The patient's life story: short passages about their past, stored in Snowflake and searched
with Cortex Search, for the voice agent's search_life_story tool (the voice owner wires the tool;
the contract is in docs/memory-track.md).

Talks to Snowflake's REST APIs with httpx: the SQL API to add, list, and delete passages, and
the Cortex Search query endpoint to search them. The objects come from
scripts/snowflake_setup.sql.

The life story is only ever about the past and preferences. Plans and appointments are memories
(Tiger Data, confirmed by a caregiver), and medicine is never saved anywhere the agent reads.
"""

import logging
import os
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal

import httpx
from pydantic import BaseModel, Field, field_validator

from app.memory.extraction import MEDICATION

log = logging.getLogger(__name__)

# The agent's tool gives up after 5 seconds, so a search must answer (or fail) before that
SEARCH_TIMEOUT = 4.0
# Adding or listing can wait for the warehouse to wake up
SQL_TIMEOUT = 60
# Cortex Search always returns its closest passages, even for a question the life story can't
# answer ("What's the capital of France?"). Its reranker score separates them. With Rose's real
# life story, correct answers scored -9.4 ("What did I do for work?") and higher; unrelated
# questions (a dog, pills, the weather) -10.6 and lower. It can't separate a plan question about
# a person ("Is Joan coming for lunch tomorrow?") from that person's paragraph: the agent's rule
# that plans only come from memories covers that. The live checks in scripts/life_story_tests.py
# print the scores to retune this.
MIN_RERANKER_SCORE = -10.0

# What the agent hears when there's nothing to say, so it never fills the gap itself
NO_LIFE_STORY = "NO_LIFE_STORY: nothing about this in the life story. Say you are not sure; never guess."
LIFE_STORY_FAILED = "LIFE_STORY_FAILED: the life story couldn't be reached. Say you are not sure right now."
SENSITIVE_NOTE = " (SENSITIVE: speak gently, and never bring it up yourself)"

_SETTINGS = ("SNOWFLAKE_ACCOUNT", "SNOWFLAKE_PAT", "SNOWFLAKE_WAREHOUSE", "SNOWFLAKE_DATABASE",
             "SNOWFLAKE_SCHEMA", "SNOWFLAKE_SEARCH_SERVICE")


class LifeStoryError(Exception):
    """Snowflake refused, failed, or couldn't be reached. The message is Snowflake's own."""


class Passage(BaseModel):
    """One short fact about the patient's past, as staff (or the loader) add it."""

    topic: Literal["family", "childhood", "work", "home", "music", "food", "pets", "friends", "faith",
                   "travel", "hobbies", "other"]
    passage: str = Field(min_length=10, max_length=400, description="1-2 sentences, names rather than she or he")
    people: str = Field(default="", max_length=200, description="Names in it, comma separated")
    said_by: str = Field(min_length=1, max_length=100, description="Who it came from, like 'Anna, daughter'")
    sensitive: bool = False

    @field_validator("passage", "people", "said_by")
    @classmethod
    def _strip(cls, value: str) -> str:
        return value.strip()

    @field_validator("passage")
    @classmethod
    def _no_medicine(cls, value: str) -> str:
        # The same rule as memories (app/memory/extraction.py): the agent must never talk about doses
        if MEDICATION.search(value):
            raise ValueError("medicine never goes in the life story (the agent must never talk about doses)")
        return value


def enabled() -> bool:
    return all(_setting(name) for name in _SETTINGS)


def lookup(patient_id: str, query: str) -> dict:
    """What the agent's search_life_story tool gets: spoken-style lines about the patient's past
    that answer the question, plus their IDs. Never fails: without Snowflake, or when it errors
    or is slow, the agent is told to say it isn't sure."""
    if not enabled():
        return {"passages": LIFE_STORY_FAILED, "ids": []}
    try:
        # Best answer first: Cortex Search's own order isn't always its reranker's
        found = sorted((p for p in search(patient_id, query) if _answers(p)),
                       key=lambda p: p["scores"].get("reranker_score", 0), reverse=True)
    except LifeStoryError as err:
        log.warning("Life story search failed: %s", err)
        return {"passages": LIFE_STORY_FAILED, "ids": []}
    return {"passages": facts(found), "ids": [p["id"] for p in found]}


def facts(passages: list[dict]) -> str:
    """One line per passage, the way the agent reads memories (context.py's facts_from)."""
    lines = [f"- {p['passage']}" + (SENSITIVE_NOTE if p["sensitive"] else "") for p in passages]
    return "\n".join(lines) or NO_LIFE_STORY


def search(patient_id: str, query: str, limit: int = 3) -> list[dict]:
    """The closest passages for this patient, with Cortex Search's scores (relevant or not)."""
    service = (f"/api/v2/databases/{_setting('SNOWFLAKE_DATABASE')}/schemas/{_setting('SNOWFLAKE_SCHEMA')}"
               f"/cortex-search-services/{_setting('SNOWFLAKE_SEARCH_SERVICE')}:query")
    body = {"query": query, "columns": ["ID", "TOPIC", "PASSAGE", "PEOPLE", "SENSITIVE"],
            "filter": {"@eq": {"PATIENT_ID": patient_id}}, "limit": limit}
    try:
        response = _client().post(service, headers=_headers(), json=body, timeout=SEARCH_TIMEOUT)
    except httpx.HTTPError as err:
        raise LifeStoryError(f"Snowflake couldn't be reached ({type(err).__name__})") from err
    if response.status_code != 200:
        raise LifeStoryError(_message(response))
    return [{"id": r.get("ID"), "topic": r.get("TOPIC"), "passage": r.get("PASSAGE") or "",
             "people": r.get("PEOPLE") or "", "sensitive": str(r.get("SENSITIVE")).lower() == "true",
             "scores": r.get("@scores") or {}}
            for r in response.json().get("results", [])]


def add_passage(patient_id: str, passage: Passage) -> dict:
    """The ID is made here, so the new passage comes back without asking Snowflake again."""
    passage_id = str(uuid.uuid4())
    _sql("INSERT INTO PASSAGES (ID, PATIENT_ID, TOPIC, PASSAGE, PEOPLE, SAID_BY, SENSITIVE) "
         "VALUES (?, ?, ?, ?, ?, ?, ?)", passage_id, patient_id, *_values(passage))
    return {"id": passage_id, **passage.model_dump()}


def list_passages(patient_id: str) -> list[dict]:
    """Oldest first."""
    return _sql("SELECT ID, TOPIC, PASSAGE, PEOPLE, SAID_BY, SENSITIVE, CREATED_AT FROM PASSAGES "
                "WHERE PATIENT_ID = ? ORDER BY CREATED_AT", patient_id)


def delete_passage(patient_id: str, passage_id: str) -> bool:
    """Whether a passage with that ID existed (for this patient)."""
    rows = _sql("DELETE FROM PASSAGES WHERE ID = ? AND PATIENT_ID = ?", passage_id, patient_id)
    return bool(rows) and int(next(iter(rows[0].values()))) > 0


def replace_passages(patient_id: str, passages: list[Passage]) -> int:
    """The loader's reset: this patient's passages become exactly these. Two statements (the SQL
    API can't bind values in a multi-statement request), so validate everything first."""
    _sql("DELETE FROM PASSAGES WHERE PATIENT_ID = ?", patient_id)
    if not passages:
        return 0
    values = [v for p in passages for v in (str(uuid.uuid4()), patient_id, *_values(p))]
    _sql("INSERT INTO PASSAGES (ID, PATIENT_ID, TOPIC, PASSAGE, PEOPLE, SAID_BY, SENSITIVE) VALUES "
         + ", ".join(["(?, ?, ?, ?, ?, ?, ?)"] * len(passages)), *values)
    return len(passages)


# Snowflake's REST APIs


_http: httpx.Client | None = None
_http_lock = threading.Lock()


def _setting(name: str) -> str:
    return os.getenv(name, "").strip()


def _base_url() -> str:
    """The account URL. Snowflake hostnames use hyphens where account names have underscores."""
    account = _setting("SNOWFLAKE_ACCOUNT").rstrip("/")
    if account.startswith("http"):
        return account
    if ".snowflakecomputing.com" in account:
        return f"https://{account}"
    return f"https://{account.replace('_', '-')}.snowflakecomputing.com"


def _client() -> httpx.Client:
    """One connection pool for the whole app, created on first use (tests swap in their own)."""
    global _http
    with _http_lock:
        if _http is None:
            _http = httpx.Client(base_url=_base_url(), timeout=SQL_TIMEOUT)
        return _http


def _headers() -> dict:
    return {"Authorization": f"Bearer {_setting('SNOWFLAKE_PAT')}",
            "X-Snowflake-Authorization-Token-Type": "PROGRAMMATIC_ACCESS_TOKEN",
            "Accept": "application/json", "Content-Type": "application/json"}


def _values(passage: Passage) -> tuple:
    return passage.topic, passage.passage, passage.people, passage.said_by, passage.sensitive


def _sql(statement: str, *values) -> list[dict]:
    """Runs one statement (values bound to its ? placeholders) and returns its rows as dicts,
    keyed by lowercase column name, with Snowflake's strings turned back into Python values.
    A statement still running after Snowflake's wait comes back as 202, and is polled."""
    body = {"statement": statement, "timeout": SQL_TIMEOUT, "warehouse": _setting("SNOWFLAKE_WAREHOUSE"),
            "database": _setting("SNOWFLAKE_DATABASE"), "schema": _setting("SNOWFLAKE_SCHEMA")}
    if values:
        body["bindings"] = {str(i): _bind(v) for i, v in enumerate(values, start=1)}
    deadline = time.monotonic() + SQL_TIMEOUT
    try:
        response = _client().post("/api/v2/statements", headers=_headers(), json=body)
        while response.status_code == 202:
            if time.monotonic() > deadline:
                raise LifeStoryError("Snowflake took too long to answer")
            time.sleep(1)
            response = _client().get(f"/api/v2/statements/{response.json()['statementHandle']}", headers=_headers())
    except httpx.HTTPError as err:
        raise LifeStoryError(f"Snowflake couldn't be reached ({type(err).__name__})") from err
    if response.status_code != 200:
        raise LifeStoryError(_message(response))
    result = response.json()
    columns = [(c["name"].lower(), c["type"]) for c in result["resultSetMetaData"]["rowType"]]
    return [{name: _value(kind, v) for (name, kind), v in zip(columns, row)} for row in result.get("data") or []]


def _bind(value) -> dict:
    if isinstance(value, bool):
        return {"type": "BOOLEAN", "value": "true" if value else "false"}
    return {"type": "TEXT", "value": str(value)}


def _value(kind: str, value: str | None):
    """Snowflake sends every value as a string: '854e…', 'false', '2', or a TIMESTAMP_TZ as
    'seconds offset', where offset is minutes from UTC plus 1440."""
    if value is None:
        return None
    if kind == "boolean":
        return value.lower() == "true"
    if kind == "fixed":
        return int(value) if value.lstrip("-").isdigit() else float(value)
    if kind == "timestamp_tz":
        seconds, offset = value.split()
        zone = timezone(timedelta(minutes=int(offset) - 1440))
        return datetime.fromtimestamp(float(seconds), tz=zone).isoformat()
    return value


def _answers(passage: dict) -> bool:
    """Whether a passage actually answers the question (see MIN_RERANKER_SCORE)."""
    score = passage["scores"].get("reranker_score")
    return score is None or score >= MIN_RERANKER_SCORE


def _message(response: httpx.Response) -> str:
    try:
        return str(response.json().get("message") or response.text).strip()[:300]
    except ValueError:
        return response.text.strip()[:300] or f"HTTP {response.status_code}"
