"""목업 음성 워커: 백엔드의 발신 요청을 접수하고, 실제 전화 대신 가짜 결과를 백엔드로 보낸다.

계약: 팀 공유 자료의 worker_openapi.json, result_json_schema.json, 노션 API 명세
실행: python voice/mock_worker/app.py  (voice/.env 사용, 사용법은 README.md)
"""
import hashlib
import json
import logging
import os
import secrets
import sqlite3
import threading
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import uvicorn
from dotenv import load_dotenv
from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator

from samples import SAMPLE_REQUEST, SCENARIO_MODES, pick_scenario
from sender import Sender

VOICE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB = VOICE_DIR / ".data" / "mock_worker.sqlite3"

QuestionCode = Literal["shuttle", "pickup", "level_fit", "vacancy", "level_test", "class_time"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Student(Strict):
    grade: str
    subject: str
    level: str
    region: str


class Question(Strict):
    question_id: str = Field(min_length=1, max_length=36)
    question_code: QuestionCode


class Policy(Strict):
    max_reask: int = Field(ge=0)
    max_seconds: int = Field(gt=0)
    is_retry: bool


class CallRequest(Strict):
    """백엔드가 POST /internal/calls로 보내는 발신 요청"""

    model_config = ConfigDict(extra="forbid", strict=True, json_schema_extra={"examples": [SAMPLE_REQUEST]})

    call_id: str = Field(min_length=1, max_length=36)
    inquiry_id: str = Field(min_length=1, max_length=36)
    attempt_no: int = Field(ge=1)
    to: str = Field(min_length=1)
    academy_name: str = Field(min_length=1)
    student: Student
    questions: list[Question] = Field(min_length=1, max_length=6)
    fixed_checks: list[str]
    disclosure_text: str = Field(min_length=1)
    policy: Policy
    is_mock: bool

    @model_validator(mode="after")
    def unique_questions(self):
        ids = [q.question_id for q in self.questions]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate question_id")
        return self


@dataclass(frozen=True)
class Receipt:
    payload: dict
    scenario: str
    received_at: datetime


class ReceiptStore:
    """접수 기록을 SQLite에 저장한다. 응답(202) 전에 커밋해서 워커가 재시작해도 조회된다."""

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with closing(self._connect()) as db, db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS receipts ("
                "call_id TEXT PRIMARY KEY, payload_hash TEXT NOT NULL, payload TEXT NOT NULL,"
                " scenario TEXT NOT NULL, received_at TEXT NOT NULL, delivered_at TEXT)"
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=5)

    def accept(self, call_id: str, payload: dict, scenario: str) -> Literal["new", "duplicate", "conflict"]:
        body = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
        with closing(self._connect()) as db, db:
            inserted = db.execute(
                "INSERT OR IGNORE INTO receipts (call_id, payload_hash, payload, scenario, received_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (call_id, digest, body, scenario, datetime.now(timezone.utc).isoformat()),
            ).rowcount
            if inserted:
                return "new"
            (stored,) = db.execute(
                "SELECT payload_hash FROM receipts WHERE call_id = ?", (call_id,)
            ).fetchone()
        return "duplicate" if stored == digest else "conflict"

    def receipt(self, call_id: str) -> Receipt | None:
        with closing(self._connect()) as db:
            row = db.execute(
                "SELECT payload, scenario, received_at FROM receipts WHERE call_id = ?", (call_id,)
            ).fetchone()
        if row is None:
            return None
        return Receipt(json.loads(row[0]), row[1], datetime.fromisoformat(row[2]))

    def mark_delivered(self, call_id: str) -> None:
        with closing(self._connect()) as db, db:
            db.execute(
                "UPDATE receipts SET delivered_at = ? WHERE call_id = ?",
                (datetime.now(timezone.utc).isoformat(), call_id),
            )

    def pending(self) -> list[str]:
        with closing(self._connect()) as db:
            rows = db.execute(
                "SELECT call_id FROM receipts WHERE delivered_at IS NULL ORDER BY received_at"
            ).fetchall()
        return [call_id for (call_id,) in rows]


def create_app(internal_key: str, store: ReceiptStore, sender: Sender | None = None,
               scenario_mode: str = "answered") -> FastAPI:
    """sender가 없으면 접수와 조회만 한다 (결과는 보내지 않음)."""
    app = FastAPI(title="8조 음성팀 목업 워커", version="0.2.0")

    def require_key(x_internal_key: str | None = Header(None)) -> None:
        if not x_internal_key or not secrets.compare_digest(x_internal_key, internal_key):
            raise HTTPException(401, "Invalid internal key")

    @app.post("/internal/calls", status_code=202, dependencies=[Depends(require_key)])
    def accept(request: CallRequest, background: BackgroundTasks):
        if not request.is_mock:
            raise HTTPException(422, "Mock worker accepts mock calls only")
        scenario = pick_scenario(scenario_mode, request.attempt_no)
        state = store.accept(request.call_id, request.model_dump(mode="json"), scenario)
        if state == "conflict":
            raise HTTPException(409, "Call ID reused with different payload")
        if state == "new" and sender is not None:
            background.add_task(sender.deliver, store, request.call_id)
        return {"call_id": request.call_id, "accepted": True, "duplicate": state == "duplicate"}

    @app.get("/internal/calls/{call_id}", dependencies=[Depends(require_key)])
    def lookup(call_id: str):
        if store.receipt(call_id) is None:
            raise HTTPException(404, "Call not accepted")
        return {"call_id": call_id, "accepted": True}

    return app


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    load_dotenv(VOICE_DIR / ".env")
    key = os.getenv("INTERNAL_KEY")
    backend_url = os.getenv("BACKEND_URL")
    if not key or not backend_url:
        raise SystemExit("voice/.env에 INTERNAL_KEY와 BACKEND_URL이 필요함")
    mode = os.getenv("MOCK_SCENARIO", "answered")
    if mode not in SCENARIO_MODES:
        raise SystemExit(f"MOCK_SCENARIO는 {', '.join(SCENARIO_MODES)} 중 하나")
    store = ReceiptStore(DEFAULT_DB)
    sender = Sender(backend_url, key, delay_sec=float(os.getenv("MOCK_DELAY_SEC", "2")))
    threading.Thread(target=sender.deliver_pending, args=(store,), daemon=True).start()
    port = int(os.getenv("WORKER_PORT", "18780"))
    uvicorn.run(create_app(key, store, sender, mode), host="127.0.0.1", port=port)


if __name__ == "__main__":
    main()
