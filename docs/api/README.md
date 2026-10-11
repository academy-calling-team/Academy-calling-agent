# API와 파트 연결 · 개발본 0.4.0

전체 필드·제약은 [백엔드 OpenAPI](openapi.json), [결과 JSON Schema](result_json_schema.json)를 따른다. [워커 OpenAPI](worker_openapi.json)는 백엔드 시험 워커의 접수·조회 경로를 설명하며, 요청 상세 구조는 아래와 음성팀 모델을 함께 대조해야 한다.

## 프론트 → 백엔드

| API | 역할 | 인증 |
|---|---|---|
| POST /auth/register, /auth/login | 개발 계정 생성·로그인 | 없음 |
| GET /auth/me, POST /auth/logout | 본인 정보·세션 폐기 | Bearer |
| GET /api/options, /api/academies | 입력 선택값·학원 목록 | 없음 |
| POST /api/inquiries | 문의 접수 | Bearer + Idempotency-Key |
| GET /api/inquiries | 본인 문의 목록 | Bearer |
| GET /api/inquiries/{inquiry_id} | 본인 문의·결과 조회 | Bearer |

학생 조건은 학년 E1~E6/M1~M3/H1~H3, 과목 KOR/ENG/MATH/SCI/SOC, 수준 HIGH/MID/LOW 및 /api/options의 지역값을 사용한다. 질문은 중복 없이 1~6개다. 상담 수락·가능 시간은 고정 확인 항목이다.

| 질문 코드 | 의미 |
|---|---|
| shuttle / pickup | 통학 차량 / 픽업 |
| level_fit / vacancy | 수준에 맞는 반 / 남은 자리 |
| level_test / class_time | 레벨 테스트 / 수업 요일·시간 |

문의 예시(자리표시는 API가 반환한 실제 ID로 바꾼다):

```json
{
  "inquirer_id": "<auth/me의 inquirer_id>",
  "academy_id": "<선택한 academy_id>",
  "student": {"grade":"M2","subject":"MATH","level":"MID","region":"대구 북구 침산동"},
  "question_codes": ["shuttle","vacancy","class_time"]
}
```

동일 제출의 응답 유실은 같은 Idempotency-Key와 같은 본문으로 재전송한다. 같은 키·다른 본문은 409다. 새로운 문의는 새 키를 사용한다. 요청 사용자 ID는 로그인 본인과 일치해야 하며 타인 문의는 조회할 수 없다.

## 백엔드 ↔ 음성 워커

inquiry_id는 문의, question_id는 개별 질문, call_id는 통화 시도, result_id는 결과의 식별자다. 동일 요청 재전송은 같은 call_id를 유지하고, 다시 거는 통화는 새 call_id와 증가한 attempt_no를 사용한다.

| 방향 | API | 응답 |
|---|---|---|
| 백엔드 → 워커 | POST /internal/calls | 영속 접수 후 202, 같은 call_id와 accepted=true |
| 백엔드 → 워커 | GET /internal/calls/{call_id} | 접수됨 200 / 없음 404 |
| 워커 → 백엔드 | POST /internal/calls/{call_id}/events | 정상 수신 200 |
| 워커 → 백엔드 | POST /internal/calls/{call_id}/result | 정상 수신 200 |

내부 요청은 X-Internal-Key를 사용한다. 백엔드 루트 .env의 INTERNAL_API_KEY와 음성 voice/.env의 INTERNAL_KEY는 같은 값으로 설정한다. 내부키·제공업체 비밀키를 프론트에 전달하지 않는다. 외부 워커 URL은 백엔드 어댑터에서 HTTPS를 요구한다.

발신 요청은 call_id, inquiry_id, attempt_no, to, academy_name, student, questions[{question_id,question_code}], fixed_checks, disclosure_text, policy{max_reask,max_seconds,is_retry}, is_mock 필드를 담는다. 현재 개발 어댑터와 음성 목업은 is_mock=true만 허용한다.

진행 이벤트는 event_id, type, timezone을 포함한 occurred_at을 사용한다. 지원 type은 initiated/ringing/answered/completed/no_answer/busy/rejected/machine/invalid_number/barge_in이다. 종료 이벤트만으로 답변을 만들지 않고 결과를 기다린다.

## 결과 해석과 오류

- 요청한 질문마다 같은 question_id·question_code의 답변 행을 포함한다.
- answered=true인 이진 질문은 yes_no=true/false, reason=null, 비어 있지 않은 detail을 사용한다.
- class_time은 yes_no=null이며 detail에 시간을 적는다.
- 미확인은 answered=false, yes_no=null, reason=unknown/refused/not_asked로 구분한다. unresolved는 미확인 question_id 목록과 일치해야 한다.
- 비연결 통화에는 대화·고지·상담·지연 값을 만들어 넣지 않는다. 재통화 요청의 시간이 불명확하면 callback_requested=true, callback_at=null로 전달해 검토를 기다린다.
- 같은 결과 ID·같은 본문은 중복 처리한다. 본문 충돌은 409, 요청 질문 불일치 등은 422다.
- queued/calling/retry_wait/completed/failed를 표시한다. completed는 모든 질문의 답 확보나 상담 예약 확정을 뜻하지 않는다. result=null은 아직 결과가 없는 상태다.
- 공개 조회에는 원문 전사·녹음 URL·내부 결과 ID를 반환하지 않는다. 상담 가능 시간은 예약 확정이 아니며 dry-run 안내도 실제 문자 발송이 아니다.
- 401은 재로그인, 403은 권한 확인, 404는 조회 대상 확인, 409는 충돌 확인, 422는 입력 확인이 필요하다. 네트워크 오류 시 문의 POST의 키·본문을 유지한다.

## 연결 전 해결할 사항

| 항목 | 현재 상태·필요 조치 |
|---|---|
| 목업 목적지 | 백엔드 seed의 phone=None을 음성 워커가 422로 거절. 합성 목적지 또는 목업 null 허용 규칙 합의 필요 |
| 실행기 | run_queue는 백엔드 자체 MockWorker 사용. 음성팀 HTTP 워커 선택과 자체 가짜 결과 생성의 분리 필요 |
| 충돌 처리 | 백엔드 HTTP 어댑터가 409 뒤 접수 조회를 성공으로 해석하는 문제 재현. 명확한 거절과 응답 유실 구분 필요 |
| 접근·실패 | 서로 다른 PC의 localhost는 연결되지 않음. 주소·HTTPS 및 결과 재전송/timeout/늦은 결과 기준 합의 필요 |
| 질문 범위 | 수강료·교재비는 음성 시험 대본에만 있고 양쪽 실행 코드에는 없음. 추가 시 질문·금액 답변 계약을 공동 변경 |

음성 목업은 정상/일부 미확인/부재중/재시도 중심이며 거절·ARS·고지 실패·시간 미정 재통화 등은 후속 시험 대상이다. 고정 답변과 latency=null·duration_sec=0은 합성 값이며 실측이 아니다. 실제 제공업체 발신·웹훅 인증·통화 ID 연결·구조화 결과 추출은 미구현이다. provider6.py는 Vapi 메시지의 오프라인 변환 예제이며 운영 웹훅 서버가 아니다.
