# 실제 음성 워커

백엔드의 발신 요청을 받아 ClawOps로 실제 전화를 걸고, 통화 결과를 질문별로 정리해 백엔드에 보낸다.
공동 서버에서 목업 워커 자리(`127.0.0.1:18780`)에 그대로 들어간다.

- `is_mock=true` 요청: 목업 워커와 똑같이 가짜 결과를 보낸다 (`voice/mock_worker`의 코드를 그대로 씀)
- `is_mock=false` 요청: 실제로 발신한다. 아래 세 조건이 모두 맞을 때만. 하나라도 아니면 422로 거절한다
  1. `REAL_CALLS_ENABLED=1`
  2. ClawOps 값 4개가 설정됨
  3. 받는 번호가 `REAL_CALL_ALLOWED_TO` 목록에 있음

설정을 하나도 바꾸지 않으면 지금 목업 워커와 똑같이 동작한다.

## 파일

| 파일 | 하는 일 |
|---|---|
| `worker.py` | 접수(202)와 조회. 목업/실제로 나눔. 재시작할 때 못 보낸 건 처리 |
| `real_call.py` | 실제 통화 한 건: 발신 → 상태 조회 → 진행 이벤트 → 전사 → 결과 |
| `clawops.py` | ClawOps API 호출 (발신, 통화 조회, 전사, 요약) |
| `extract.py` | 전사에서 AI/학원 구분, 질문별 대답 찾기, 예·아니오·미확인 판정 |
| `test_worker.py` | 시험. ClawOps와 백엔드를 가짜로 바꿔서 전화는 걸지 않음 |

## 처리 순서

1. 접수 기록 저장(목업과 같은 SQLite) → 202
2. ClawOps `POST /calls`로 발신. 서비스 에이전트(`CLAWOPS_SERVICE_AGENT_ID`)를 쓰고, 이번 문의의 학원·학생·질문·고지 문구는 `CallContext`로 넘긴다. 학생 조건은 백엔드 코드(`M2`, `MATH`)가 아니라 "중학교 2학년, 과목 수학"처럼 풀어서 넘긴다
3. ClawOps 통화 ID를 바로 저장한다. 같은 `call_id`는 다시 걸지 않는다
4. 2초마다 `GET /calls/{id}`로 상태를 보고 진행 이벤트를 보낸다

   | ClawOps 상태 | 진행 이벤트 |
   |---|---|
   | queued | initiated |
   | ringing | ringing |
   | in-progress | answered (자동응답기면 machine) |
   | completed | completed |
   | no-answer / busy / rejected | no_answer / busy / rejected |
   | failed / canceled | 결과의 outcome으로만 알림 (번호 문제면 invalid_number, 그 외 rejected) |

5. 끝나면 전사와 요약을 받아 결과 JSON을 만들어 보낸다. 연결이 안 된 통화는 모든 질문이 `not_asked`

웹훅을 쓰지 않으므로 공동 서버에 외부 공개 경로가 필요 없다. 이벤트·결과 전송은 목업 워커의 `Sender`와 같은 재시도·거절 규칙을 쓴다.

## 전화를 다시 걸지 않는 규칙

- 같은 `call_id`가 다시 오면 접수 기록으로 중복 처리하고 발신하지 않는다
- 발신 요청에 응답을 못 받으면(네트워크 오류) 이미 걸렸을 수 있어 거절로 기록하고 사람이 ClawOps 통화 목록을 확인한다
- 워커가 재시작되면, ClawOps 통화 ID가 저장된 건은 그 통화를 이어서 따라가고, 없는 건은 다시 걸지 않고 거절로 기록한다
- 거절 건은 `ReceiptStore.rejected()`로 이유를 본다
- 진행 이벤트의 `event_id`는 `evt_{call_id}_{종류}`이고, 본문을 보내기 전에 저장해 둔다. 재시작해서 다시 보낼 때도 같은 ID·같은 본문이라 백엔드가 중복으로 처리한다(다른 본문이면 409)

## ClawOps에 넘기는 형식

- `CallContext.Instruction`: 이번 통화 지시(학원, 학생, 질문 목록, 고지 문구). 4000자 이내
- `CallContext.Variables`: 값은 문자열·숫자·참거짓만 된다(배열·객체는 400). 백엔드가 보낸 질문 배열은 그대로 두고, 워커가 `"shuttle, pickup"` 같은 문자열로 바꿔 넘긴다

## 설정 (`voice/.env`, 공동 서버는 워커 설정 파일)

| 항목 | 뜻 |
|---|---|
| `INTERNAL_KEY`, `BACKEND_URL`, `WORKER_PORT`, `MOCK_SCENARIO`, `MOCK_DELAY_SEC` | 목업 워커와 같음 |
| `REAL_CALLS_ENABLED` | `1`이면 실제 발신을 켬. 없으면 목업 요청만 받음 |
| `REAL_CALL_ALLOWED_TO` | 실제로 걸어도 되는 번호, 쉼표 구분. 하이픈은 무시 |
| `CLAWOPS_API_KEY` | ClawOps API 키 |
| `CLAWOPS_ACCOUNT_ID` | ClawOps 계정 ID |
| `CLAWOPS_SERVICE_AGENT_ID` | 서비스 에이전트 ID. `voice/engines/setup_service_agent.py create`로 만든다 |
| `CLAWOPS_FROM_NUMBER` | 발신 번호(팀 070) |

키 값은 Git, 단톡, 로그에 남기지 않는다.

### 서비스 에이전트

10/13 지연 비교용 시험 에이전트(`CLAWOPS_AGENT_ID`, 프롬프트 v3)는 학생(중2 수학)과 질문 세 개가 프롬프트에 박혀 있다.
ClawOps의 `CallContext` 지시는 기본 프롬프트를 바꾸지 않고 위에 얹히므로, 그대로 쓰면 고른 질문과 v3 질문이 섞일 수 있다.
그래서 같은 모델·음성 설정에 범용 프롬프트(`voice/prompts/service_agent_prompt.txt`)를 넣은 서비스 에이전트를 따로 만든다.
시험 에이전트는 측정 조건을 지키려고 그대로 둔다.

```
python voice/engines/setup_service_agent.py create   # 만들고 ID를 voice/.env에 저장
python voice/engines/setup_service_agent.py show     # 설정 확인
python voice/engines/setup_service_agent.py update   # 프롬프트를 바꾼 뒤
```

## 혼자 시험하기

```
python -m pytest voice/call_worker -q
```

가짜 백엔드로 실제 통화 한 건을 시험할 때는 터미널 두 개에서 실행한다. `voice/.env`에 위 실제 발신 설정을 넣고, 받는 번호는 팀원 휴대폰만 허용한다.

```
python voice/mock_worker/fake_backend.py
python voice/call_worker/worker.py
```

http://127.0.0.1:18780/docs 에서 `POST /internal/calls`에 `is_mock: false`, `to: 허용한 번호`로 보낸다.

## 공동 서버에 켤 때 (찬원)

1. 이 PR이 main에 합쳐지면 자동 배포로 워커 이미지가 이 워커로 바뀐다. 설정을 안 바꾸면 목업과 똑같다
2. 서버의 워커 설정 파일(`worker_env`)에 `REAL_CALLS_ENABLED=1`, `REAL_CALL_ALLOWED_TO`, ClawOps 값 4개를 넣는다
3. **워커 컨테이너를 새로 만들어야 설정이 반영된다.** `docker restart`는 이전 설정을 그대로 쓴다. Actions에서 배포를 다시 돌리거나 같은 옵션으로 워커를 다시 만든다
4. `docker logs team8-shared-worker`에 `real calls enabled for 1 allowed number(s)`가 보이면 켜진 것이다
5. 시연이 끝나면 `REAL_CALLS_ENABLED`를 지우고 다시 만들면 목업으로 돌아간다

## 아직 안 한 것

- 판정 규칙(`extract.judge`)은 10/19 정한 키워드 규칙이다(부정어 우선, 추측은 미확인 등, 사례는 `test_judge_rules`). 판정이 안 되면 미확인(`unknown`)으로 보내고 대답 원문은 `detail`에 남긴다. 10/13 통화 16개 전사에서 자리·수업 시간은 모두 맞았고, 상담은 2개가 받아쓰기 오류로 미확인이 됐다
- 상담 가능 시간은 학원 대답 원문을 그대로 `available_times`에 넣는다
- 응답 지연(`latency`)은 아직 계산하지 않아 `null`
- 부재중 재통화는 백엔드가 새 `call_id`로 다시 요청하는 기존 규칙을 따른다. 담당 범위는 백엔드와 다시 맞춘다
- 통화가 `policy.max_seconds`를 넘을 때 워커가 직접 끊지는 않는다. 에이전트 지시로 마무리를 유도한다
