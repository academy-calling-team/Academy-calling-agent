# 재연락 대기 화면 및 API 확인 사항

## 현재 응답으로 구분하는 정보

`GET /api/inquiries/{inquiry_id}`의 status를 최우선으로 사용합니다.

| 응답 | 화면 안내 |
|---|---|
| retry_wait + 최신 attempts[].outcome = no_answer/busy/machine/rejected | 부재중·통화 중·자동 응답·수신 거절에 따른 연결 재시도 대기 |
| retry_wait + 최신 outcome = answered | 통화 후 재연락 대기 |
| result.callback_requested = true | 학원의 재연락 요청 안내. 더 최신 통화의 결과가 있으면 이전 요청보다 최신 통화 결과를 우선함 |
| review_required + review_reason = callback_time_unknown | 통화 후 재연락 시간 확인 중, 자동 발신 보류 |
| review_required + 기타 사유 | 재연락 검토 중, 자동 발신 보류 |
| retry_wait이나 근거 정보가 부족함 | 연결 실패로 단정하지 않고 중립적인 재연락 대기 안내 |
| completed | 처리 완료. 과거 callback 정보가 남아 있어도 대기로 변경하지 않음 |

result.callback_at은 학원 요청 시간으로 한국 시간(Asia/Seoul)에 맞추어 표시합니다. 시간대 없는 문자열·유효하지 않은 값은 표시하지 않습니다. 시간 확인 보류 중에는 요청 시간을 확정 일정으로 표시하지 않습니다. available_times는 추가 상담 가능 시간으로, 자동 회신 일정에 사용하지 않습니다.

## 백엔드 확인 결과 및 한계

- backend/service.py의 상세 조회는 result.callback_requested와 result.callback_at을 포함한 결과를 반환하지만 inquiries.next_at은 반환하지 않습니다.
- callback_at은 원래 요청 시간입니다. 운영자의 검토 후 정한 시간이나 실제 응대 가능 시간에 따른 발신 시각과 다를 수 있습니다.
- 결과가 아직 도착하지 않은 최신 통화와 이전 통화의 result가 함께 반환될 수 있습니다. 현재 API에는 result가 어느 call_id/attempt_no에 속하는지 명시되어 있지 않습니다.
- 실통화 시험은 answered 이후 callback 요청이 있어도 completed로 종료하며 자동으로 재발신하지 않는 정책입니다. 프론트엔드는 이를 임의로 retry_wait로 바꾸지 않습니다.
- completed는 처리 종료를 의미하며, 모든 질문에 답변했다는 뜻은 아닙니다.

## 백엔드에 요청할 응답 보완 (제안, 미구현)

상세 응답에 다음 정보를 추가하면 대기 사유와 실제 재연락 가능 시각을 정확히 표시할 수 있습니다.

```json
{
  "status": "retry_wait",
  "retry": {
    "reason": "callback_requested",
    "source_call_id": "call-id",
    "source_attempt_no": 1,
    "requested_at": "2030-01-02T06:00:00Z",
    "next_eligible_at": "2030-01-02T06:00:00Z",
    "on_hold": false
  }
}
```

- reason: callback_requested/no_answer/busy/machine/rejected/unknown 등 서버에서 결정한 현재 대기 사유.
- source_call_id/source_attempt_no: 현재 재연락 상태를 만든 통화 식별자. result에도 해당 식별자를 제공하면 과거 결과의 오인 표시를 방지할 수 있습니다.
- requested_at: 학원에서 요청한 시각. 미확정이면 null.
- next_eligible_at: 검토 결과·지연 정책 등을 반영한 다음 발신 가능 시각. 보류·미확정이면 null. 실제 발신을 보장하는 예약 시각과 구분해야 합니다.
- on_hold: 자동 발신 보류 여부. 보류 사유 및 관리자 검토 결과도 현재 상태에 맞게 반환해야 합니다.
- 모든 시간은 시간대가 포함된 ISO 8601 형식으로 반환합니다. 응대 시간·대기열에 따라 달라지는 정책을 명시해야 합니다.

이 제안은 현재 프론트엔드가 이미 소비하는 필드가 아니며, 백엔드와 계약 확정 후 별도 연동이 필요합니다. 실제 재발신·운영자 일정 변경 API는 이번 프론트엔드 수정에 포함하지 않습니다.

## 격리 미리보기

- `/detail/mock-callback-scheduled?preview=mock`: 통화 후 재연락 요청 시간 표시.
- `/detail/mock-retry-no-answer?preview=mock`: 부재중으로 인한 재시도 대기.
- `/detail/mock-callback-unknown?preview=mock`: 요청 시간 미확정으로 자동 발신 보류.

모두 모의 데이터이며 실제 전화나 서버 저장을 실행하지 않습니다.
