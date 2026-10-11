"""혼자 시험할 때 쓰는 가짜 백엔드. 워커가 보낸 events와 result를 받아 터미널에 출력한다.

진짜 백엔드(팀장 PC)와 같은 경로, 같은 인증, 같은 중복 규칙(같은 ID와 본문은 200, 다른 본문은 409)만 흉내 낸다.
실행: python voice/mock_worker/fake_backend.py  (BACKEND_URL의 포트로 뜸)
"""
import json
import os
import secrets
from urllib.parse import urlparse

import uvicorn
from dotenv import load_dotenv
from fastapi import Body, Depends, FastAPI, Header, HTTPException

from app import VOICE_DIR


def create_backend(internal_key: str) -> FastAPI:
    app = FastAPI(title="가짜 백엔드 (음성팀 시험용)")
    received: dict[str, dict] = {}

    def require_key(x_internal_key: str | None = Header(None)) -> None:
        if not x_internal_key or not secrets.compare_digest(x_internal_key, internal_key):
            raise HTTPException(401, "Invalid internal key")

    def record(item_id: str | None, body: dict) -> dict:
        if not item_id:
            raise HTTPException(422, "ID required")
        if item_id in received:
            if received[item_id] != body:
                raise HTTPException(409, "Same ID with different body")
            return {"duplicate": True, "applied": True}
        received[item_id] = body
        return {"duplicate": False, "applied": True}

    @app.post("/internal/calls/{call_id}/events", dependencies=[Depends(require_key)])
    def event(call_id: str, body: dict = Body(...)):
        reply = record(body.get("event_id"), body)
        print(f"[event]  {call_id}  {body.get('type'):<10} {body.get('occurred_at')}", flush=True)
        return reply

    @app.post("/internal/calls/{call_id}/result", dependencies=[Depends(require_key)])
    def result(call_id: str, body: dict = Body(...)):
        reply = record(body.get("result_id"), body)
        print(f"[result] {call_id}\n{json.dumps(body, ensure_ascii=False, indent=2)}", flush=True)
        return reply

    return app


if __name__ == "__main__":
    load_dotenv(VOICE_DIR / ".env")
    key, backend_url = os.getenv("INTERNAL_KEY"), os.getenv("BACKEND_URL")
    if not key or not backend_url:
        raise SystemExit("voice/.env에 INTERNAL_KEY와 BACKEND_URL이 필요함")
    uvicorn.run(create_backend(key), host="127.0.0.1", port=urlparse(backend_url).port or 18770)
