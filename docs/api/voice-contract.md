# 워커 접수·외부 통화 ID·결과 수신

작성 2026-10-05 · 검토용 구현. 실제 음성팀 워커·Vapi 계정·전화 회선에 연결하지 않았다. 이 문서는 백엔드가 준비한 계약과 오프라인 정규화 동작을 설명한다.

## 문의와 통화 ID를 구분한다

inquiry_id는 문의, question_id는 질문, call_id는 한 번의 통화 시도, provider external_id는 실제 제공자 통화, result_id는 워커 결과이다. 하나의 문의에는 최대 3개의 통화 시도가 생길 수 있다. **같은 call_id 전달 재시도와 새 call_id 재발신은 별개**다.

MySQL에서 call/outbox를 먼저 함께 저장한다. Redis Streams는 call_id를 전달하고 consumer가 DB lease를 확보해 DB 트랜잭션 밖에서 워커에 보낸다. 완료·처리 중·확인된 접수에는 ACK, 접수 여부가 불명확하면 같은 ID pending 유지. 운영시간·학원 휴무·연락 간격·동시 상한은 이전 구현을 유지한다.

## 워커 접수 계약

| 요청 | 요구 응답 |
|---|---|
| POST /internal/calls | 202, `{call_id: 동일 ID, accepted: true}`. 영속 접수 후 응답 |
| GET /internal/calls/{call_id} | 이미 접수됐으면 200, `{call_id: 동일 ID, accepted: true}`. 미접수면 404 |

워커는 X-Internal-Key를 런타임으로 받는다. public/member 계정 토큰은 워커 내부키가 아니다. 접수 payload와 조회 응답은 [worker OpenAPI](worker_openapi.json)에 있다. 같은 ID의 다른 payload는 충돌로 거부한다.

`http_worker6.WorkerHttpAdapter`는 POST 응답 유실/비정상 응답 후 GET으로 접수를 조회한다. 확인 실패는 ConnectionError이며 새 ID를 만들어 재발신하지 않는다. 외부 URL은 HTTPS, 로컬만 HTTP를 허용하고 리다이렉트/환경 proxy를 따르지 않는다. URL에 사용자명·암호·query·fragment를 넣지 않는다. 현재 어댑터는 is_mock=true만 처리한다.

이번 별도 프로세스 검증은 실제 로컬 HTTP + MySQL 영속 접수 조회 + Redis 왕복이다. 제공자 실제 발신의 exactly-once나 음성팀 서버 재시작 중복 방지를 보장한 시험은 아니다.

## Vapi 형식 오프라인 어댑터

`provider6.VapiBridge`는 **외부 API 요청도 공개 webhook listener도 제공하지 않는다**. 실제 발신 워커가 만든 외부 ID와 기존 call_id를 먼저 bind하는 구조를 준비했다. 같은 매핑은 중복 응답, 다른 매핑은 409, 알 수 없는 외부 ID는 404이다. 수신 메시지만으로 새 통화를 만들지 않는다.

현재 같은 개발 폴더에서 시험하는 이 모듈은 실제 연동 시 음성 워커의 제공자 변환 경계에서 사용하도록 준비한 것이다. 노션의 “외부 도구 형식은 음성 워커가 다루고 백엔드는 우리 형식만 받는다” 원칙을 유지한다. 백엔드 공개 API로 제공자 메시지를 직접 받는 경로를 추가하지 않았다.

Vapi의 메시지 wrapper와 이벤트 타입은 [공식 Server events](https://docs.vapi.ai/server-url/events)를 기준으로 읽었다. 제공자 통화 객체의 상태·조회 구조는 [Calls get](https://docs.vapi.ai/api-reference/calls/get/)를 참고했다. 실제 계정/실통화의 응답을 받은 것은 아니다.

| message.type / status | 내부 처리 |
|---|---|
| status-update / ringing | ringing 이벤트 |
| status-update / in-progress | initiated, **사람 연결 판정으로 사용하지 않음** |
| status-update / ended | completed 이벤트, 최종 결과를 기다림 |
| end-of-call-report | 명시된 structured output의 ResultInput 검증 |
| 기타 종류/상태 | ignored 기록 |

timestamp는 timezone 있는 ISO 또는 epoch millisecond를 받는다. 상태 역순 도착은 기존 service의 상태 역행 방지로 처리한다. 종료 상태만으로 긍정 답변·고지 완료·상담 수락을 만들지 않는다.

## 결과 출력 형식과 격리

[공식 Structured outputs](https://docs.vapi.ai/assistants/structured-outputs-quickstart/)의 `call.artifact.structuredOutputs[outputId].result` 구조를 기준으로 명시된 output ID만 읽는다. 어댑터는 message.artifact 또는 message.call.artifact를 받으며 개발 기본 ID는 `team8-result-v1`이다. 실제 계정 output ID가 생성됐거나 해당 스키마가 설정됐다는 뜻은 아니다.

실제 계정에서 사용할 ID·추출 prompt·JSON schema와 분석 완료 후 제공 시점을 음성팀이 확인해야 한다. 분석이 늦어 output이 없는 보고는 현재 격리되며 자동 제공자 재조회는 미구현이다. 보완된 결과를 별도 수신/재처리하는 정책을 합의해야 한다. 기존 analysis.structuredData를 자동으로 추정해서 읽지 않는다. [공식 Call analysis](https://docs.vapi.ai/assistants/call-analysis)와 계정 설정을 대조한다.

canonical ResultInput의 전체 계약은 [JSON schema](result_json_schema.json). 모든 요청 질문은 답변 행을 포함하고 미응답은 answered=false, yes_no=null, reason을 기록한다. class_time은 텍스트 답변이라 yes_no=null. unknown과 false를 혼동하지 않는다. 비연결 시 상담/고지/지연/전사에 측정하지 않은 값을 만들어 넣지 않는다. 재통화 시간 미정은 callback_requested=true, callback_at=null로 받는다.

수신함은 canonical payload의 fingerprint로 중복을 식별하고 DB에 pending/processed/ignored/quarantined 상태를 저장한다. 원본 raw message 전문·provider 녹음/전사는 그대로 복사하지 않는다. 정상적으로 정규화된 결과는 내부 결과 계약에 포함된 전사가 있을 수 있으므로 보관 정책은 별도 합의가 필요하다. 공개 조회에는 전사/녹음 URL을 반환하지 않는다.

필드 누락·스키마 불일치·다른 질문 ID·결과 충돌은 quarantined이며 정상 결과로 덮어쓰지 않는다. pending 항목은 새 프로세서에서도 읽어 재처리할 수 있고 event_id/result_id 중복 방지에 의존한다. DB 장애는 처리 완료로 감추지 않는다. 격리 항목을 관리자가 보고 편집/재전송하는 UI는 미구현이다.

## 실제 연동 전 확인표

- [ ] 음성팀 워커 URL·HTTPS·런타임 인증·영속 접수 조회 계약 확인.
- [ ] 실제 외부 발신 시 중복 방지/불명확 응답·제공자 ID 바인딩/재조회 절차 확인.
- [ ] 실제 structured output ID·JSON schema·분석 완료 시간·결과 누락 보완 절차 확인.
- [ ] 사전 허용 시험 회선·발신 번호·고지·녹음/전사 보관·비용 조건 확인.
- [ ] 실제 STT/요약·질문별 정답·1.5초 지연 목표를 실측, ClawOps 같은 조건 비교.

문서 확인·오프라인 메시지 시험은 이 확인표의 실제 연동 완료를 대신하지 않는다.
