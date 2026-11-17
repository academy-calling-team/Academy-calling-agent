# 음성 결과 계약 1차 확장 · 백엔드 선행 작업

이 PR은 **조건·사유·근거 발화·상담·재연락·종료 원인을 받는 계약, 입력 검증, 기존 결과 호환**을 준비한다. 전송값으로 저장된 정보를 사용하며, 백엔드가 발화 문장을 분석해서 라벨을 다시 붙이지 않는다. 새 상태 필드와 판정기 내부 `certainty` 등은 추가하지 않는다.

실행 가능한 전체 요청 예시는 [voice_result_examples.json](examples/voice_result_examples.json), 필드 구조는 [결과 JSON Schema](result_json_schema.json)와 [OpenAPI](openapi.json)를 따른다. JSON Schema만으로 표현되지 않는 필드 간 조합·근거 참조는 아래 런타임 검증도 적용한다.

## 추가 필드

모두 선택 필드이며 생략/null을 허용한다. 기존 `extra='forbid'`, 필수 필드, `refused`, `class_time` 예외를 유지한다. 문자열은 비어 있거나 공백뿐인 값을 거부하고, 원문의 공백·날짜를 임의로 바꾸지 않는다.

| 위치 | 필드 | 제한·의미 |
|---|---|---|
| answers[] | condition | 1~200자. answered=true, yes_no=true일 때만 |
| answers[] | reason_text | 1~500자. 모든 상태의 판정 사유 |
| answers[] | evidence_turns | 최대 10개의 중복 없는 음이 아닌 정수. 실제 질문을 했을 때만 근거 참조 |
| answers[] | reason | 기존 값 유지, `redirect` 추가 |
| transcript[] | turn_no | 선택적 음이 아닌 정수, 동일 결과에서 고유 |
| ResultInput | consult | 아래 AnswerDetail 객체. 기존 consult_accepted/available_times 유지 |
| ResultInput | callback_reason_text | 1~500자. callback_requested=true일 때만 |
| ResultInput | callback_source_text | 1~500자. callback_requested=true일 때만 |
| ResultInput | end_reason | completed / academy_hung_up / connection_lost / agent_error. outcome=answered일 때만 |

기존 answers[].source_text의 1~2000자 제한도 유지한다. consult는 `reason, condition, reason_text, source_text, evidence_turns`를 가지며 설명·근거 필드 제한은 질문 답변과 같다.

## 조합 규칙

| 질문 결과 의미 | asked | answered | yes_no | reason | condition |
|---|---|---|---|---|---|
| 가능 | true | true | true | null | 없음 |
| 조건부 가능 | true | true | true | null | 조건 문장 |
| 불가 | true | true | false | null | 없음 |
| 직접 확인 필요 | true | false | null | redirect | 없음 |
| 미확인 | true | false | null | unknown / uncertain | 없음 |
| 묻지 못함 | false | false | null | not_asked | 없음 |

- `class_time`의 확인된 답은 기존대로 answered=true, yes_no=null, detail에 요일·시간을 넣는다. 이 PR은 class_time의 새로운 조건부 조합을 추가하지 않는다.
- 과거 `refused`는 계속 받는다. unknown/uncertain은 서로 다른 저장값으로 유지한다. 새 reason 때문에 과거 결과를 일괄 변경하지 않는다.
- 질문별 unresolved는 기존대로 answered=false인 질문 ID 집합과 정확히 같아야 한다.
- consult 생략은 과거 워커와 호환된다. consult가 있으면 consult_accepted=true/false일 때 reason=null, null일 때 reason 필수다. condition은 consult_accepted=true일 때만 허용한다.
- consult.reason=not_asked이면 source_text와 비어 있지 않은 evidence_turns를 금지한다. reason_text는 미질문 사유로도 쓸 수 있다.
- available_times가 있으면 consult_accepted=true여야 한다. 시간 문자열은 원문 표현을 그대로 받으며, 요일·날짜·오전/오후 추정이나 시간표 파싱을 추가하지 않는다.
- callback_at은 기존대로 시간대가 있는 절대시각만 받는다. 모호한 재연락은 callback_requested=true/callback_at=null과 사유·원문을 사용할 수 있다. 기존 워커를 위해 새 사유/원문을 필수로 만들지는 않는다.
- 사람이 연결되지 않은 outcome은 consult와 end_reason를 보낼 수 없다. ARS와 질문별 미확인은 같은 상태가 아니며 기존 연결 결과 규칙을 유지한다.

## 라벨 기준과 음성팀 인계

사용자가 지정한 발화 예시의 라벨·판정 근거를 유지한다. 문자 요청을 절차라고 재해석하여 가능으로 바꾸거나, 내부 확인이라는 문구만 보고 redirect를 uncertain으로 덮어쓰는 로직은 없다. 요일별 조건을 조건부 가능으로 보내려면 예시 라벨과 condition의 조합도 일치시켜야 한다.

이 PR은 가능한 전송 조합을 검증한다. 특정 발화를 어떤 reason/condition으로 보내는지는 음성팀이 기준 예시에 맞춰 작성하고 연동 사례로 확인한다. 전송 형식과 판정 모델/계층 구성의 선택은 독립된 작업이다.

## 발화 식별·참조

- 식별 범위는 `(call_id, turn_no)`. call_id는 `/internal/calls/{call_id}/result` 경로가 정한다.
- 번호가 없는 과거 transcript도 그대로 받으며 임의로 번호를 붙이지 않는다. 번호를 쓸 때는 0 이상이며 같은 결과 안에서 중복될 수 없다. 배열 위치와 식별 번호를 혼동하지 않는다.
- evidence_turns는 **그 결과의 transcript에 실제 turn_no로 명시된 번호**만 가리킨다. 다른 결과나 배열 인덱스로 추측해 참조하지 않는다. 정수 대신 bool/실수/문자열을 보내는 것도 거부한다.
- source_text의 문장 의미를 백엔드가 다시 판정하거나 원문과의 의미 일치를 자동 확정하지 않는다.

## 기존 JSON 저장·교정 호환

기존 `w5_results.payload`에 유효한 새 필드도 보존된다. 학부모의 기존 소유권 검사와 전체 transcript/녹음 URL 비공개를 유지한다. 현행 조회는 새 메타데이터를 그대로 포함하지만, evidence_turns를 실제 발화 목록으로 풀어주는 새 조회 기능은 이번에 추가하지 않았다.

새 선택 필드가 없는 기존 결과의 직렬화·해시는 바뀌지 않는다. 새 null 필드, 빈 evidence_turns, null turn_no도 생략으로 정규화하므로 이전 결과의 동일 ID 재전송이 새 기본값 때문에 409가 되지 않는다. 실제 조건·사유·참조 번호가 바뀌면 기존 불변 결과 충돌 검사는 유지한다.

구형 검토 요청이 새 필드를 모른 채 요약만 수정해도 기존 추가 정보·번호를 보존한다. 질문의 판정 조합을 바꾸면 기존 condition/사유/근거를 무조건 복사하지 않는다. consult·재연락·종료 등 운영 필드를 바꾸는 교정은 현재 허용 범위를 넓히지 않았으며 후속 설계가 필요하다.

## 후속 저장·조회 담당 작업

1. 질문별 `w5_answers` 등 별도 저장 구조와 신규 필드를 어떻게 연결할지 결정한다. 전체 결과 JSON에 저장되는 것과 별도 테이블·집계용 필드 반영은 다르다. 현행 metadata 변경이 없으므로 **이 PR에는 DDL이 없다**. 컬럼/별도 테이블이 필요하면 후속 PR에서 SQL·기존 데이터 보존·생성 명세를 함께 준비한다.
2. 허용된 근거 번호를 발화로 풀어 학부모에게 반환하는 응답 구조와 권한·최소 범위를 구현한다. 학원/운영 전체 전사 조회도 역할·학원 관계와 API 범위를 확정한 후 구현한다. 프론트에서 숨기기만 하는 방식은 사용하지 않는다.
3. consult를 포함한 설명 교정 범위·참조 일관성 및 프론트용 최종 응답 계약을 정한다.
4. 프론트에서 6종 상태·조건·사유·상담 결과·재연락·종료 안내를 표시하고 워커가 새 형식을 보내도록 연결한다.

## 상태 전이와 배포 범위

end_reason는 이 단계에서 기록 정보다. connection_lost/agent_error 자동 재시도, 내부 확인 후 재확인 통화, 남은 질문만 재통화하는 정책은 구현하지 않는다. 기존 일반 재시도·callback 처리·실통화 시험 한도를 유지한다. outcome=answered인데 새 종료 원인만 보고 자동 발신이 늘어났다고 해석하면 안 된다.

남은 질문 재통화는 발신 시도별 질문 범위·이전 답변 병합·전체 질문 결과 검증을 함께 바꾸는 별도 작업이다.

현재 산출물은 **검토용 미병합 PR**이다. 후속 저장/조회·화면과 음성 시험을 마친 뒤 백엔드 → 프론트 → 워커 순서로 적용한다. 이 PR 업로드는 공동 DB 적용·배포·실제 발신 승인이 아니다.
