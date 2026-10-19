"""ClawOps REST API에서 실제 워커가 쓰는 부분만 감싼다.

명세: https://api.claw-ops.com/openapi.json
- POST /calls: 매니지드 에이전트로 발신. 이번 통화의 질문은 CallContext로 넘긴다
- GET  /calls/{id}: 통화 상태(queued, ringing, in-progress, completed, no-answer, busy, rejected, failed, canceled)
- GET/POST /calls/{id}/transcript: 전사. 화자는 speaker_0, speaker_1 같은 번호뿐이라 AI/학원 구분은 워커가 한다
- GET  /calls/{id}/summary: 조직 스키마(기본 default:v1)에 맞춘 LLM 요약
"""
from dataclasses import dataclass

import httpx

API = "https://api.claw-ops.com/v1/accounts/{account}"


class ClawOpsError(Exception):
    """ClawOps가 요청을 거절함. code는 명세의 기계 판독용 에러 코드(없으면 HTTP 상태)."""

    def __init__(self, status: int, code: str, message: str):
        super().__init__(f"{status} {code}: {message}")
        self.status = status
        self.code = code


@dataclass(frozen=True)
class ClawOpsConfig:
    api_key: str
    account_id: str
    agent_id: str
    from_number: str


class ClawOps:
    def __init__(self, config: ClawOpsConfig, transport: httpx.BaseTransport | None = None):
        self.config = config
        self.client = httpx.Client(
            base_url=API.format(account=config.account_id),
            headers={"Authorization": f"Bearer {config.api_key}"},
            timeout=15, trust_env=False, transport=transport,
        )

    def _call(self, method: str, path: str, **kwargs) -> tuple[int, dict]:
        reply = self.client.request(method, path, **kwargs)
        body = reply.json() if reply.content else {}
        if reply.status_code >= 400 and reply.status_code != 409:
            raise ClawOpsError(reply.status_code, str(body.get("code") or reply.status_code), str(body.get("error", ""))[:300])
        return reply.status_code, body

    def create_call(self, to: str, instruction: str, variables: dict, ring_timeout: int = 30) -> str:
        """발신하고 ClawOps 통화 ID를 돌려준다. 자동응답기는 감지만 하고 통화는 계속한다."""
        _, body = self._call("POST", "/calls", json={
            "To": to,
            "From": self.config.from_number,
            "AgentId": self.config.agent_id,
            "CallContext": {"Instruction": instruction, "Variables": variables},
            "Timeout": ring_timeout,
            "MachineDetection": "Enable",
        })
        return body["callId"]

    def get_call(self, call_id: str) -> dict:
        return self._call("GET", f"/calls/{call_id}")[1]

    def get_transcript(self, call_id: str) -> dict:
        """status가 completed면 segments[{speaker, start, end, text}]가 같이 온다."""
        return self._call("GET", f"/calls/{call_id}/transcript")[1]

    def request_transcript(self, call_id: str) -> None:
        """'통화 받아쓰기'가 꺼져 있을 때 이 통화만 전사를 요청한다. 이미 요청된 건(409)은 그냥 넘어간다."""
        self._call("POST", f"/calls/{call_id}/transcript")

    def get_summary(self, call_id: str) -> dict:
        return self._call("GET", f"/calls/{call_id}/summary")[1]
