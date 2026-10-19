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

발신 요청은 call_id, inquiry_id, attempt_no, to, academy_name, student, questions[{question_id,question_code}], fixed_checks, disclosure_text, policy{max_reask,max_seconds,is_retry}, is_mock 필드를 담는다. 일반 학원은 is_mock=true를 유지한다. 실통화 시험은 지정 학원·번호·계정·서버 활성화를 모두 확인한 뒤 is_mock=false로 동일 계약을 사용하며, 최대 1회만 시도한다. [실통화 시험 절차](../collaboration/실통화_시험.md)를 따른다.

학원 목록과 문의 상세의 academy에는 is_test, can_submit, max_attempts, notice를 추가한다. 실제 번호·시험 계정 ID·키는 공개 응답에 포함하지 않는다. can_submit은 서버 준비 상태이며 최종 계정 권한은 문의 접수와 워커 전달 시 다시 검사한다.

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
| 목업 목적지 | 백엔드 seed의 phone=None 보존. 현재 음성 워커는 422로 거절하며 백엔드는 검토 필요 상태로 전송 중단. 목업 null 허용은 아직 상대 코드에 미반영 |
| 실행기 | --worker-url로 음성팀 HTTP 목업 선택 가능. --simulate-results 동시 사용 금지. 실제 로컬 실행기와 워커 왕복 확인 |
| 충돌 처리 | 4xx는 확정 거절, 429/5xx는 일시 실패. GET 재확인은 네트워크 응답 유실에 한정. 거절/비정상 응답은 자동 전송 중단·검토 필요 |
| 접근·실패 | 서로 다른 PC의 localhost는 연결되지 않음. 주소·HTTPS 및 결과 재전송/timeout/늦은 결과 기준 합의 필요 |
| 질문 범위 | 수강료·교재비는 음성 시험 대본에만 있고 양쪽 실행 코드에는 없음. 추가 시 질문·금액 답변 계약을 공동 변경 |

음성 목업은 정상/일부 미확인/부재중/재시도 중심이며 거절·ARS·고지 실패·시간 미정 재통화 등은 후속 시험 대상이다. 고정 답변과 latency=null·duration_sec=0은 합성 값이며 실측이 아니다. 실제 제공업체 발신·웹훅 인증·통화 ID 연결·구조화 결과 추출은 미구현이다. provider6.py는 Vapi 메시지의 오프라인 변환 예제이며 운영 웹훅 서버가 아니다.

## 로컬 개선 후보의 결과 대기 기준 · 2026-10-13

기한은 통화 예약 시점부터 600초(개발값)이다. 종료 후 600초로 변경하지 않았다.
결과 수신 자체에서도 기한을 확인한다. 기한이 지난 신규 유효 결과는 저장하며 applied=false를 반환한다.
스케줄러 실행 전에도 진행 중 통화는 timeout/실패로 처리한다. 이미 부재중 이벤트로 예약된 재시도는 늦은 보고가 취소하지 않는다.
이미 저장된 동일 결과는 기존 duplicate/applied 응답을 유지한다. ID·본문 충돌, 질문 불일치와 잘못된 형식은 계속 409/422로 거절한다.
늦은 보고의 과거 callback_at은 감사용으로 보존할 수 있지만 재통화 일정을 변경하지 않는다.
완성된 result 한 건과 동일 ID·본문 재전송을 수신한다. 제공업체 분석 완료 판단·워커 재시작 송신 정책은 백엔드가 대신 실행하지 않는다.
수강료·교재비는 질문 코드에 추가하지 않았다. 실제 운영 대기 시간은 실통화·분석 지연을 측정한 후 확정한다.
