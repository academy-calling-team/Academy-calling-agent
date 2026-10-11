"""목업 워커가 백엔드로 events와 result를 보낸다.

순서: 접수 후 MOCK_DELAY_SEC만큼 기다림 → events를 차례로 보냄 → result를 보냄 → 전달 완료 기록.
일시적인 오류(연결 실패, 5xx)는 몇 번 다시 보내고, 거절(401, 404, 409, 422)은 멈추고 로그에 남긴다.
"""
import logging
import time

import httpx

from samples import build_events, build_result

log = logging.getLogger("mock_worker")
RETRYABLE = {429, 500, 502, 503, 504}


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
        for event in build_events(call_id, receipt.scenario, receipt.received_at):
            if not self._post(f"{path}/events", event):
                return False
        if not self._post(f"{path}/result", build_result(receipt.payload, receipt.scenario)):
            return False
        store.mark_delivered(call_id)
        log.info("%s: delivered (%s)", call_id, receipt.scenario)
        return True

    def deliver_pending(self, store) -> None:
        """워커가 꺼져서 못 보낸 결과를 시작할 때 다시 보낸다."""
        for call_id in store.pending():
            self.deliver(store, call_id)

    def _post(self, path: str, body: dict) -> bool:
        for attempt in range(1, self.attempts + 1):
            try:
                reply = self.client.post(path, json=body)
            except httpx.RequestError as error:
                log.warning("%s: %s (try %d/%d)", path, error, attempt, self.attempts)
            else:
                if reply.status_code == 200:
                    return True
                if reply.status_code not in RETRYABLE:
                    log.error("%s: rejected %d %s", path, reply.status_code, reply.text[:300])
                    return False
                log.warning("%s: %d (try %d/%d)", path, reply.status_code, attempt, self.attempts)
            if attempt < self.attempts:
                time.sleep(self.retry_wait * attempt)
        return False
