"""What happens during conversations: questions answered, things the patient said, and alerts.

Placeholder until the memory system lands: rows go to JSON files under backend/data/
(git-ignored) in the same shape as the `interactions` and `alerts` tables in schema.sql.
Replace the bodies of _append/_read with Tiger Data queries and the endpoints stay the same.
"""

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth import require_staff
from app.memory.context import PATIENT_ID

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
_lock = threading.Lock()

router = APIRouter(tags=["events"])
staff_router = APIRouter(tags=["events"], dependencies=[Depends(require_staff)])


def _path(table: str) -> Path:
    return DATA_DIR / f"{table}.json"


def _read(table: str) -> list[dict]:
    path = _path(table)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def _write(table: str, rows: list[dict]):
    DATA_DIR.mkdir(exist_ok=True)
    tmp = _path(table).with_suffix(".tmp")
    tmp.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    os.replace(tmp, _path(table))


def _append(table: str, row: dict) -> dict:
    row = {"id": uuid.uuid4().hex, "ts": datetime.now(timezone.utc).isoformat(), "patient_id": PATIENT_ID, **row}
    with _lock:
        _write(table, [*_read(table), row])
    return row


# Patient side: called by the voice agent's client tools in the browser (the patient page has no login)


class Interaction(BaseModel):
    topic: str = Field(max_length=100)
    question: str = Field(max_length=1000)
    answer: str = Field(max_length=2000)
    memory_ids: list[str] = []
    answered: bool = True
    latency_ms: int | None = None


class Statement(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    kind: Literal["medication", "meal", "activity", "feeling", "other"] = "other"


class NewAlert(BaseModel):
    kind: Literal["missing_info", "self_reported_med", "help_requested"]
    message: str = Field(min_length=1, max_length=500)


@router.post("/interactions")
def log_interaction(body: Interaction):
    return _append("interactions", body.model_dump())


@router.post("/patient/statements")
def log_statement(body: Statement):
    """Something the patient said they did. Stored as self-reported, never as a fact."""
    row = _append("statements", {**body.model_dump(), "status": "self_reported"})
    if body.kind == "medication":
        # Staff need to know: a self-report alone must never count as a confirmed dose
        _append("alerts", {"kind": "self_reported_med", "message": f'Said: "{body.text}" (not verified)', "resolved": False})
    return row


@router.post("/alerts")
def raise_alert(body: NewAlert):
    return _append("alerts", {**body.model_dump(), "resolved": False})


# Staff side


@staff_router.get("/alerts")
def list_alerts():
    """Open alerts first, newest first within each group."""
    rows = sorted(_read("alerts"), key=lambda a: a["ts"], reverse=True)
    return {"alerts": sorted(rows, key=lambda a: a["resolved"])}


@staff_router.post("/alerts/{alert_id}/resolve", status_code=204)
def resolve_alert(alert_id: str):
    with _lock:
        rows = _read("alerts")
        match = next((a for a in rows if a["id"] == alert_id), None)
        if not match:
            raise HTTPException(404, "That alert no longer exists")
        match["resolved"] = True
        _write("alerts", rows)


@staff_router.get("/interactions")
def list_interactions():
    return {"interactions": sorted(_read("interactions"), key=lambda r: r["ts"], reverse=True)}
