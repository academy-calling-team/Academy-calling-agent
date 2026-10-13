"""목업 워커가 백엔드로 events와 result를 보낸다.

순서: 접수 후 MOCK_DELAY_SEC만큼 기다림 → events를 차례로 보냄 → result를 보냄 → 전달 완료 기록.
일시적인 오류(연결 실패, 5xx)는 몇 번 다시 보내고, 그래도 안 되면 미전달로 남겨 재시작할 때 다시 보낸다.
명확한 거절(401, 404, 409, 422)은 바로 멈추고 거절로 기록한다. 거절 건은 원인을 확인하기 전에는 자동으로 다시 보내지 않는다.
"""
import logging
import time
from typing import Literal

import httpx

from samples import build_events, build_result

log = logging.getLogger("mock_worker")
RETRYABLE = {429, 500, 502, 503, 504}
Outcome = Literal["ok", "rejected", "failed"]


class Sender:
    def __init__(self, backend_url: str, internal_key: str, *, delay_sec: float = 2.0,
                 attempts: int = 3, retry_wait: float = 1.0, transport: httpx.BaseTransport | None = None):
        self.client = httpx.Client(
            base_url=backend_url.rstrip("/"), headers={"X-Internal-Key": internal_key},
            timeout=5, trust_env=False, follow_redirects=False, transport=transport,
        )
        self.delay_sec = delay_sec
        self.attempts = attempts
        self.retry_wait = retry_wait

    def deliver(self, store, call_id: str) -> bool:
        receipt = store.receipt(call_id)
        if receipt is None:
            log.error("%s: no receipt to deliver", call_id)
            return False
        time.sleep(self.delay_sec)
        path = f"/internal/calls/{call_id}"
        requests = [(f"{path}/events", event) for event in build_events(call_id, receipt.scenario, receipt.received_at)]
        requests.append((f"{path}/result", build_result(receipt.payload, receipt.scenario)))
        for url, body in requests:
            outcome, detail = self._post(url, body)
            if outcome == "rejected":
                store.mark_rejected(call_id, f"{url} {detail}")
                return False
            if outcome == "failed":
                log.warning("%s: left for redelivery (%s)", call_id, detail)
                return False
        store.mark_delivered(call_id)
        log.info("%s: delivered (%s)", call_id, receipt.scenario)
        return True

    def deliver_pending(self, store) -> None:
        """워커가 꺼져 있거나 백엔드가 잠깐 안 돼서 못 보낸 결과를 시작할 때 다시 보낸다. 거절 건은 빼고."""
        for call_id in store.pending():
            self.deliver(store, call_id)

    def _post(self, path: str, body: dict) -> tuple[Outcome, str]:
        detail = ""
        for attempt in range(1, self.attempts + 1):
            try:
                reply = self.client.post(path, json=body)
            except httpx.RequestError as error:
                detail = str(error)
                log.warning("%s: %s (try %d/%d)", path, error, attempt, self.attempts)
            else:
                if reply.status_code == 200:
                    return "ok", ""
                detail = f"{reply.status_code} {reply.text[:300]}"
                if reply.status_code not in RETRYABLE:
                    log.error("%s: rejected %s", path, detail)
                    return "rejected", detail
                log.warning("%s: %d (try %d/%d)", path, reply.status_code, attempt, self.attempts)
            if attempt < self.attempts:
                time.sleep(self.retry_wait * attempt)
        return "failed", detail
