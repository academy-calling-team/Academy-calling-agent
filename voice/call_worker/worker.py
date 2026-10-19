"""실제 음성 워커. 공동 서버에서 목업 워커 자리에 그대로 들어간다.

- is_mock=true 요청: 목업 워커와 똑같이 가짜 결과를 보낸다 (voice/mock_worker 재사용)
- is_mock=false 요청: ClawOps로 실제 발신하고 통화 결과를 보낸다 (real_call.py)

실제 발신은 세 가지가 모두 맞을 때만 한다. 하나라도 아니면 지금 목업 워커처럼 422로 거절한다.
1. REAL_CALLS_ENABLED=1
2. CLAWOPS_API_KEY, CLAWOPS_ACCOUNT_ID, CLAWOPS_SERVICE_AGENT_ID, CLAWOPS_FROM_NUMBER 설정됨
3. 받는 번호가 REAL_CALL_ALLOWED_TO(쉼표 구분) 목록에 있음

실행: python voice/call_worker/worker.py  (voice/.env 사용, README.md 참고)
"""
import logging
import os
import re
import secrets
import sys
import threading
from pathlib import Path

VOICE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(VOICE_DIR / "mock_worker"))

import uvicorn  # noqa: E402
from dotenv import load_dotenv  # noqa: E402
from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException  # noqa: E402

from app import DEFAULT_DB, CallRequest, ReceiptStore  # noqa: E402  (mock_worker)
from samples import SCENARIO_MODES, pick_scenario  # noqa: E402
from sender import Sender  # noqa: E402

from clawops import ClawOps, ClawOpsConfig  # noqa: E402
from real_call import ProviderCalls, RealCalls  # noqa: E402

log = logging.getLogger("call_worker")
REAL = "real"  # 접수 기록의 scenario 칸에 실제 통화임을 표시


def normalize(number: str) -> str:
    return re.sub(r"\D", "", number)


def create_app(internal_key: str, store: ReceiptStore, sender: Sender | None = None,
               scenario_mode: str = "answered", real: RealCalls | None = None,
               allowed_to: frozenset[str] = frozenset()) -> FastAPI:
    app = FastAPI(title="8조 음성 워커", version="0.4.0")

    def require_key(x_internal_key: str | None = Header(None)) -> None:
        if not x_internal_key or not secrets.compare_digest(x_internal_key, internal_key):
            raise HTTPException(401, "Invalid internal key")

    @app.post("/internal/calls", status_code=202, dependencies=[Depends(require_key)])
    def accept(request: CallRequest, background: BackgroundTasks):
        if request.is_mock:
            scenario = pick_scenario(scenario_mode, request.attempt_no)
        else:
            if real is None:
                raise HTTPException(422, "Real calls are disabled on this worker")
            if normalize(request.to or "") not in allowed_to:
                raise HTTPException(422, "Destination is not on the real-call allow list")
            scenario = REAL
        state = store.accept(request.call_id, request.model_dump(mode="json"), scenario)
        if state == "conflict":
            raise HTTPException(409, "Call ID reused with different payload")
        if state == "new":
            if scenario == REAL:
                background.add_task(real.run, store, request.call_id)
            elif sender is not None:
                background.add_task(sender.deliver, store, request.call_id)
        return {"call_id": request.call_id, "accepted": True, "duplicate": state == "duplicate"}

    @app.get("/internal/calls/{call_id}", dependencies=[Depends(require_key)])
    def lookup(call_id: str):
        if store.receipt(call_id) is None:
            raise HTTPException(404, "Call not accepted")
        return {"call_id": call_id, "accepted": True}

    return app


def resume_pending(store: ReceiptStore, sender: Sender, real: RealCalls | None,
                   provider_calls: ProviderCalls | None) -> None:
    """재시작할 때 못 보낸 건 처리. 실제 통화는 절대 다시 걸지 않는다.

    - 목업: 목업 워커처럼 다시 보낸다
    - 실제, ClawOps 통화 ID 있음: 그 통화를 이어서 따라가 결과를 보낸다
    - 실제, 통화 ID 없음: 걸렸는지 알 수 없어 거절로 기록하고 사람이 확인한다
    """
    for call_id in store.pending():
        receipt = store.receipt(call_id)
        if receipt.scenario != REAL:
            sender.deliver(store, call_id)
        elif real is not None and provider_calls is not None and provider_calls.get(call_id):
            real.follow(store, call_id)
        else:
            store.mark_rejected(call_id, "재시작 전 발신 여부 불명, 다시 걸지 않음. ClawOps 통화 목록 확인 필요")


def load_real(store_path: Path, sender: Sender) -> tuple[RealCalls | None, ProviderCalls | None, frozenset[str]]:
    if os.getenv("REAL_CALLS_ENABLED") != "1":
        log.info("real calls disabled (REAL_CALLS_ENABLED != 1): mock requests only")
        return None, None, frozenset()
    # 에이전트는 시험용(CLAWOPS_AGENT_ID, 프롬프트 v3)이 아니라 범용 프롬프트의 서비스 에이전트를 쓴다
    names = ("CLAWOPS_API_KEY", "CLAWOPS_ACCOUNT_ID", "CLAWOPS_SERVICE_AGENT_ID", "CLAWOPS_FROM_NUMBER")
    missing = [n for n in names if not os.getenv(n)]
    allowed = frozenset(normalize(n) for n in os.getenv("REAL_CALL_ALLOWED_TO", "").split(",") if normalize(n))
    if missing or not allowed:
        raise SystemExit(f"실제 발신 설정 부족: {', '.join(missing) or 'REAL_CALL_ALLOWED_TO'}")
    config = ClawOpsConfig(*(os.environ[n] for n in names))
    provider_calls = ProviderCalls(store_path)
    # sender._post: 목업과 같은 재시도·거절 규칙으로 이벤트와 결과를 보낸다
    real = RealCalls(ClawOps(config), provider_calls, sender._post)
    log.info("real calls enabled for %d allowed number(s)", len(allowed))
    return real, provider_calls, allowed


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
    real, provider_calls, allowed = load_real(DEFAULT_DB, sender)
    threading.Thread(target=resume_pending, args=(store, sender, real, provider_calls), daemon=True).start()
    port = int(os.getenv("WORKER_PORT", "18780"))
    uvicorn.run(create_app(key, store, sender, mode, real, allowed),
                host=os.getenv("WORKER_HOST", "127.0.0.1"), port=port)


if __name__ == "__main__":
    main()
