# 프론트엔드 전달용 최종 조회 응답 예시 (`GET /api/inquiries/{inquiry_id}`)

## 1. 질문별 6종 상태 판별 기준 (`result.answers[]`)

프론트엔드는 별도 상태 문자열 대신 기존 필드 조합(`asked`, `answered`, `yes_no`, `reason`, `condition`)으로 6종 상태를 표시한다.

| 화면 표시 상태 | `asked` | `answered` | `yes_no` | `reason` | `condition` | 비고 |
|---|---|---|---|---|---|---|
| **가능** | `true` | `true` | `true` | `null` | 없음 | |
| **조건부 가능** | `true` | `true` | `true` | `null` | 조건 문장 (≤200자) | `condition` 배지/안내 표시 |
| **불가능** | `true` | `true` | `false` | `null` | 없음 | |
| **직접 확인 필요** | `true` | `false` | `null` | `"redirect"` | 없음 | 학원 직접 문의 안내 |
| **미확인** | `true` | `false` | `null` | `"unknown"` / `"uncertain"` / `"refused"` | 없음 | 화면에서는 '미확인'으로 통일 |
| **묻지 못함** | `false` | `false` | `null` | `"not_asked"` | 없음 | 중간 끊김(`end_reason`) 시 발생 가능 |

- `class_time` 질문은 확인 시 `answered: true, yes_no: null`이며 `detail`에 요일·시간이 담긴다.
- 모든 상태에 선택적으로 `reason_text`(판정 사유), `source_text`(근거 발화 원문), `evidence_turns`(발화 번호), `evidence_dialogue`(학부모에게 허용된 실제 발화 목록)가 포함될 수 있다.

## 2. 학부모 상세 조회 응답 예시 (`GET /api/inquiries/{inquiry_id}`)

학부모 조회 응답에는 전체 `transcript`와 `recording_url`이 포함되지 않으며, `evidence_turns`에 지정된 허용 발화만 `evidence_dialogue`로 제공된다.

아래는 **시각 미정 재연락 요청이 있는 목업 문의**다. `callback_requested=true`, `callback_at=null`이면 기존 정책상 `retry_wait`와 확인 필요 상태로 반환된다. 이를 `completed`로 표시하면 재연락 대기를 처리 완료로 오해할 수 있어 수정했다. 지정 실통화 시험은 별도의 한도 정책을 따른다.

```json
{
  "inquiry_id": "837c79c4-1ef3-458f-8d05-ba1b866206c0",
  "inquirer_id": "44fa19ec-1d9f-450d-bf63-67a31678bd38",
  "status": "retry_wait",
  "created_at": "2026-11-17T10:00:00+00:00",
  "student": {
    "grade": "M2",
    "subject": "MATH",
    "level": "MID",
    "region": null
  },
  "academy": {
    "academy_id": "shared-mock-4639357f6d7b452ba97d",
    "name": "공유DB 목업 연결시험",
    "is_mock": true,
    "is_test": false,
    "can_submit": true,
    "max_attempts": null,
    "notice": ""
  },
  "questions": [
    {
      "question_id": "q-shuttle",
      "question_code": "shuttle",
      "question_label_kr": "통학 차량",
      "location": { "kind": "학교", "name": "침산초등학교" }
    },
    {
      "question_id": "q-vacancy",
      "question_code": "vacancy",
      "question_label_kr": "남은 자리"
    },
    {
      "question_id": "q-level-test",
      "question_code": "level_test",
      "question_label_kr": "레벨 테스트"
    }
  ],
  "attempts": [
    {
      "call_id": "call-001",
      "attempt_no": 1,
      "status": "finished",
      "status_label_kr": "통화 종료",
      "started_at": "2026-11-17T10:00:02+00:00",
      "outcome": "answered",
      "outcome_label_kr": "연결됨",
      "time_context": {
        "timezone": "Asia/Seoul",
        "inquiry_created_at": "2026-11-17T10:00:00+00:00",
        "dispatch_requested_at": "2026-11-17T10:00:01+00:00"
      }
    }
  ],
  "result": {
    "outcome": "answered",
    "disclosure_played": true,
    "consult_accepted": true,
    "available_times": ["평일 16:00-18:00"],
    "consult": {
      "condition": "사전 문자 예약 시 가능",
      "reason_text": "방문 전 문자 시간 확정 조건부 수락",
      "source_text": "문자로 먼저 시간 잡아주시면 상담 가능합니다.",
      "evidence_turns": [5],
      "evidence_dialogue": [
        {
          "turn_no": 5,
          "speaker": "academy",
          "at_ms": 18200,
          "text": "문자로 먼저 시간 잡아주시면 상담 가능합니다."
        }
      ]
    },
    "answers": [
      {
        "question_id": "q-shuttle",
        "question_code": "shuttle",
        "asked": true,
        "answered": true,
        "yes_no": true,
        "reason": null,
        "condition": "침산초등학교 앞 오후 4시 탑승 시 가능",
        "reason_text": "정류장 및 시간 조건부 운행",
        "detail": "침산초등학교 앞 오후 4시 차량 탑승 가능",
        "source_text": "침산초 앞이면 4시 차로 태울 수 있어요.",
        "evidence_turns": [2],
        "evidence_dialogue": [
          {
            "turn_no": 2,
            "speaker": "academy",
            "at_ms": 7400,
            "text": "침산초 앞이면 4시 차로 태울 수 있어요."
          }
        ]
      },
      {
        "question_id": "q-vacancy",
        "question_code": "vacancy",
        "asked": true,
        "answered": false,
        "yes_no": null,
        "reason": "redirect",
        "reason_text": "담당 선생님 확인 후 안내 필요",
        "detail": "반 정원은 담당 선생님께 직접 확인 필요"
      },
      {
        "question_id": "q-level-test",
        "question_code": "level_test",
        "asked": false,
        "answered": false,
        "yes_no": null,
        "reason": "not_asked",
        "reason_text": "학원 측 통화 종료로 미질문",
        "detail": ""
      }
    ],
    "unresolved": ["q-vacancy", "q-level-test"],
    "summary_text": "셔틀 조건부 가능, 잔여석 직접 확인 필요, 레벨테스트 미질문",
    "notes": "",
    "latency": null,
    "duration_sec": 24,
    "callback_requested": true,
    "callback_at": null,
    "callback_reason_text": "수업 종료 후 재연락 요청",
    "callback_source_text": "지금 수업 중이라 저녁에 다시 전화 주실 수 있을까요?",
    "end_reason": "academy_hung_up",
    "review_revision": 0
  },
  "failure_reason": null,
  "fallback_required": false,
  "fallback_status": null,
  "review_required": true,
  "review_reason": "callback_time_unknown"
}
```

## 3. 학원·운영자 전체 전사 조회 (`GET /api/calls/{call_id}/transcript`)

- 해당 통화의 학원 소유자(`account_type="academy"`) 또는 운영자(`role="admin"`)만 조회 가능하며, 일반 학부모 및 타 학원 계정은 `403 Forbidden`을 반환한다.
- 응답의 `applied`는 이 통화 결과가 문의의 최종 결과에 반영됐는지를 나타낸다. 시간 초과 등으로 `false`여도 권한자는 저장된 전사를 조사할 수 있다. 학부모의 문의 결과 조회에서는 기존 최종 결과 필터를 유지한다.
- 결과 자체가 아직 저장되지 않았으면 `404 Result not found`다. 전사 조회는 문의 상태를 바꾸거나 재발신을 실행하지 않는다.

```json
{
  "call_id": "example-call",
  "inquiry_id": "example-inquiry",
  "academy_id": "example-academy",
  "applied": false,
  "transcript": [
    {"speaker": "academy", "at_ms": 1000, "text": "저장된 통화 발화 예시입니다.", "turn_no": 0}
  ],
  "review_revision": 0
}
```

## 4. 정상 완료·재연락 대기 구분

목업 문의의 `outcome=answered`, `callback_requested=false`, `callback_at=null`은 기존 정책상 `status=completed`, `review_required=false`, `review_reason=null`이다. 같은 결과의 시각 미정 재연락 요청은 2절과 같이 대기로 표시한다. 연결 결과·문의 상태·질문별 판정을 각각 구분하며 `end_reason`만으로 새 자동 재시도를 만들지 않는다.

병합·DB 적용 순서는 [음성 결과 PR58/PR61 반영 순서](../collaboration/voice_result_merge_deploy.md)를 따른다.
