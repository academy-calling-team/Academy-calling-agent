# 목업 음성 워커

실제 전화를 걸지 않는 가짜 음성 워커. 백엔드의 발신 요청을 접수하고, 몇 초 뒤 정해 둔 가짜 결과를 백엔드로 보낸다.
통화 없이 문의 등록부터 결과 저장, 조회까지 전체 흐름을 시험하는 용도 (테스트 기준 E2E-01, E2E-03).
나중에 `samples.py`의 가짜 결과 부분을 Vapi 호출로 바꾸면 실제 워커가 된다.

계약: 팀 공유 자료의 `worker_openapi.json`, `result_json_schema.json`, 노션 API 명세

## 파일

| 파일 | 하는 일 |
|---|---|
| `app.py` | `POST /internal/calls` 접수(202), `GET /internal/calls/{call_id}` 조회(200, 404). 접수 기록은 `voice/.data/`에 저장 |
| `samples.py` | 가짜 events와 result. 시나리오: 정상 연결, 일부 미확인, 부재중 |
| `sender.py` | events와 result를 백엔드로 보냄. 일시 오류는 다시 보내고, 거절(401, 404, 409, 422)은 멈춤 |
| `fake_backend.py` | 혼자 시험할 때 쓰는 가짜 백엔드. 받은 내용을 터미널에 출력 |
| `test_app.py` | 시험 |

## 설정 (`voice/.env`)

| 항목 | 뜻 | 기본값 |
|---|---|---|
| `INTERNAL_KEY` | 백엔드와 워커가 같이 쓰는 내부키. 진짜 백엔드와 연결할 때는 팀장 키로 바꿈 | 없음 (필수) |
| `BACKEND_URL` | 결과를 보낼 백엔드 주소 | 없음 (필수) |
| `WORKER_PORT` | 워커 포트 | 18780 |
| `MOCK_SCENARIO` | `answered` 정상 / `partial` 마지막 질문 미확인 / `no_answer` 부재중 / `retry` 첫 시도 부재중, 다시 건 전화는 정상 | answered |
| `MOCK_DELAY_SEC` | 접수 후 결과를 보내기까지 기다리는 시간(초) | 2 |

## 혼자 시험하기

터미널 두 개를 열고 `team8-repo`에서 실행한다.

```
python voice/mock_worker/fake_backend.py
python voice/mock_worker/app.py
```

브라우저에서 http://127.0.0.1:18780/docs → `POST /internal/calls` → Try it out → `x-internal-key`에 키 입력 → 예시 본문 그대로 Execute.
2초 뒤 가짜 백엔드 터미널에 events 4개와 result가 찍히면 성공. 같은 요청을 다시 보내려면 `call_id`를 바꾼다 (같은 ID에 다른 내용이면 409).

## 시험

```
python -m pytest voice/mock_worker -q
```

## 진짜 백엔드와 연결할 때

- `BACKEND_URL`을 백엔드 주소로, `INTERNAL_KEY`를 백엔드와 같은 키로 바꾼다. 키는 개인 메시지로 받는다
- 백엔드가 `is_mock=true`인 학원으로 문의를 만들면 이 워커로 발신 요청이 온다
- 워커를 어디에 띄울지(같은 PC, ngrok, Lightsail)는 백엔드와 정할 것. 백엔드 어댑터는 외부 주소면 HTTPS만 허용한다
