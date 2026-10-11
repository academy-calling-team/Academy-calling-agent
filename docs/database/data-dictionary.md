# 6주차 백엔드 · 로컬 검증용

자동 생성 기준: 실제 SQLAlchemy metadata.

## w5_academies

| 필드 | DB 타입 | 필수 | 키·관계 | 기본값 |
|---|---|---|---|---|
| id | VARCHAR(36) | 예 | PK  |  |
| name | VARCHAR(100) | 예 |   |  |
| region | VARCHAR(80) | 예 |   |  |
| phone | VARCHAR(30) | 아니오 |   |  |
| is_mock | BOOLEAN | 예 |   |  |
| hours | JSON | 예 |   |  |

## w5_control

| 필드 | DB 타입 | 필수 | 키·관계 | 기본값 |
|---|---|---|---|---|
| id | VARCHAR(36) | 예 | PK  |  |

## w5_inquirers

| 필드 | DB 타입 | 필수 | 키·관계 | 기본값 |
|---|---|---|---|---|
| id | VARCHAR(36) | 예 | PK  |  |
| token_hash | VARCHAR(64) | 예 | UK  |  |
- None: token_hash

## w5_mock_worker_receipts

| 필드 | DB 타입 | 필수 | 키·관계 | 기본값 |
|---|---|---|---|---|
| call_id | VARCHAR(36) | 예 | PK  |  |
| payload_hash | VARCHAR(64) | 예 |   |  |
| payload | JSON | 예 |   |  |
| received_at | DATETIME | 예 |   |  |

## w5_academy_policies

| 필드 | DB 타입 | 필수 | 키·관계 | 기본값 |
|---|---|---|---|---|
| academy_id | VARCHAR(36) | 예 | PK,FK w5_academies.id |  |
| enabled | BOOLEAN | 예 |   | True |
| max_concurrent | INTEGER | 예 |   | 1 |
| cooldown_seconds | INTEGER | 예 |   | 300 |
| closed_dates | JSON | 예 |   | <function list at 0x000001EFBE3A04A0> |

## w5_inquiries

| 필드 | DB 타입 | 필수 | 키·관계 | 기본값 |
|---|---|---|---|---|
| id | VARCHAR(36) | 예 | PK  |  |
| inquirer_id | VARCHAR(36) | 예 | FK w5_inquirers.id |  |
| academy_id | VARCHAR(36) | 예 | FK w5_academies.id |  |
| request_key | VARCHAR(80) | 예 |   |  |
| payload_hash | VARCHAR(64) | 예 |   |  |
| student | JSON | 예 |   |  |
| status | VARCHAR(20) | 예 |   |  |
| priority | INTEGER | 예 |   | 0 |
| created_at | DATETIME | 예 |   |  |
| next_at | DATETIME | 예 |   |  |
| failure_reason | VARCHAR(80) | 아니오 |   |  |
| fallback_required | BOOLEAN | 예 |   | False |
- w5_uq_request: inquirer_id, request_key
- w5_ck_status: status IN ('queued','calling','retry_wait','completed','failed')

## w6_accounts

| 필드 | DB 타입 | 필수 | 키·관계 | 기본값 |
|---|---|---|---|---|
| user_id | VARCHAR(36) | 예 | PK,FK w5_inquirers.id |  |
| login_name | VARCHAR(32) | 예 | UK  |  |
| password_hash | VARCHAR(500) | 예 |   |  |
| role | VARCHAR(16) | 예 |   | member |
| enabled | BOOLEAN | 예 |   | True |
| failed_logins | INTEGER | 예 |   | 0 |
| locked_until | DATETIME | 아니오 |   |  |
- None: login_name

## w5_calls

| 필드 | DB 타입 | 필수 | 키·관계 | 기본값 |
|---|---|---|---|---|
| id | VARCHAR(36) | 예 | PK  |  |
| inquiry_id | VARCHAR(36) | 예 | FK w5_inquiries.id |  |
| attempt_no | INTEGER | 예 |   |  |
| status | VARCHAR(30) | 예 |   |  |
| outcome | VARCHAR(30) | 아니오 |   |  |
| created_at | DATETIME | 예 |   |  |
| last_event_at | DATETIME | 아니오 |   |  |
| deadline | DATETIME | 예 |   |  |
| dispatch_payload | JSON | 예 |   |  |
| delivery_count | INTEGER | 예 |   | 0 |
- w5_uq_attempt: inquiry_id, attempt_no
- w5_ck_attempt: attempt_no > 0

## w5_questions

| 필드 | DB 타입 | 필수 | 키·관계 | 기본값 |
|---|---|---|---|---|
| id | VARCHAR(36) | 예 | PK  |  |
| inquiry_id | VARCHAR(36) | 예 | FK w5_inquiries.id |  |
| code | VARCHAR(30) | 예 |   |  |
| position | INTEGER | 예 |   |  |
- w5_uq_question_code: inquiry_id, code
- w5_uq_question_position: inquiry_id, position

## w6_fallback_tasks

| 필드 | DB 타입 | 필수 | 키·관계 | 기본값 |
|---|---|---|---|---|
| inquiry_id | VARCHAR(36) | 예 | PK,FK w5_inquiries.id |  |
| status | VARCHAR(30) | 예 |   |  |
| failure_reason | VARCHAR(80) | 예 |   |  |
| message | TEXT | 아니오 |   |  |
| created_at | DATETIME | 예 |   |  |
| reviewed_at | DATETIME | 아니오 |   |  |
| reviewer | VARCHAR(100) | 아니오 |   |  |
| review_reason | VARCHAR(1000) | 아니오 |   |  |
| dry_run_receipt | JSON | 아니오 |   |  |

## w6_review_actions

| 필드 | DB 타입 | 필수 | 키·관계 | 기본값 |
|---|---|---|---|---|
| id | VARCHAR(36) | 예 | PK  |  |
| inquiry_id | VARCHAR(36) | 예 | FK w5_inquiries.id |  |
| actor | VARCHAR(100) | 예 |   |  |
| action | VARCHAR(30) | 예 |   |  |
| reason | VARCHAR(1000) | 예 |   |  |
| payload | JSON | 예 |   |  |
| created_at | DATETIME | 예 |   |  |

## w6_sessions

| 필드 | DB 타입 | 필수 | 키·관계 | 기본값 |
|---|---|---|---|---|
| token_hash | VARCHAR(64) | 예 | PK  |  |
| id | VARCHAR(36) | 예 | UK  |  |
| user_id | VARCHAR(36) | 예 | FK w6_accounts.user_id |  |
| created_at | DATETIME | 예 |   |  |
| expires_at | DATETIME | 예 |   |  |
| revoked | BOOLEAN | 예 |   | False |
- None: id

## w5_answers

| 필드 | DB 타입 | 필수 | 키·관계 | 기본값 |
|---|---|---|---|---|
| call_id | VARCHAR(36) | 예 | PK,FK w5_calls.id |  |
| question_id | VARCHAR(36) | 예 | PK,FK w5_questions.id |  |
| asked | BOOLEAN | 예 |   |  |
| answered | BOOLEAN | 예 |   |  |
| yes_no | BOOLEAN | 아니오 |   |  |
| reason | VARCHAR(30) | 아니오 |   |  |
| detail | TEXT | 예 |   |  |

## w5_delivery_leases

| 필드 | DB 타입 | 필수 | 키·관계 | 기본값 |
|---|---|---|---|---|
| call_id | VARCHAR(36) | 예 | PK,FK w5_calls.id |  |
| claim_id | VARCHAR(36) | 예 |   |  |
| lease_until | DATETIME | 예 |   |  |

## w5_dispatch_outbox

| 필드 | DB 타입 | 필수 | 키·관계 | 기본값 |
|---|---|---|---|---|
| id | VARCHAR(36) | 예 | PK  |  |
| call_id | VARCHAR(36) | 예 | UK,FK w5_calls.id |  |
| created_at | DATETIME | 예 |   |  |
| last_published_at | DATETIME | 아니오 |   |  |
- None: call_id

## w5_events

| 필드 | DB 타입 | 필수 | 키·관계 | 기본값 |
|---|---|---|---|---|
| id | VARCHAR(80) | 예 | PK  |  |
| call_id | VARCHAR(36) | 예 | FK w5_calls.id |  |
| type | VARCHAR(30) | 예 |   |  |
| occurred_at | DATETIME | 예 |   |  |
| received_at | DATETIME | 예 |   |  |
| payload_hash | VARCHAR(64) | 예 |   |  |
| applied | BOOLEAN | 예 |   |  |

## w5_results

| 필드 | DB 타입 | 필수 | 키·관계 | 기본값 |
|---|---|---|---|---|
| call_id | VARCHAR(36) | 예 | PK,FK w5_calls.id |  |
| result_id | VARCHAR(80) | 예 | UK  |  |
| payload_hash | VARCHAR(64) | 예 |   |  |
| payload | JSON | 예 |   |  |
| received_at | DATETIME | 예 |   |  |
| applied | BOOLEAN | 예 |   |  |
- None: result_id

## w6_provider_calls

| 필드 | DB 타입 | 필수 | 키·관계 | 기본값 |
|---|---|---|---|---|
| call_id | VARCHAR(36) | 예 | PK,FK w5_calls.id |  |
| provider | VARCHAR(24) | 예 |   |  |
| external_id | VARCHAR(100) | 예 |   |  |
| created_at | DATETIME | 예 |   |  |
- w6_uq_provider_call: provider, external_id

## w6_provider_inbox

| 필드 | DB 타입 | 필수 | 키·관계 | 기본값 |
|---|---|---|---|---|
| id | VARCHAR(64) | 예 | PK  |  |
| call_id | VARCHAR(36) | 예 | FK w5_calls.id |  |
| type | VARCHAR(60) | 예 |   |  |
| payload_hash | VARCHAR(64) | 예 |   |  |
| status | VARCHAR(30) | 예 |   |  |
| normalized | JSON | 예 |   |  |
| error | VARCHAR(100) | 아니오 |   |  |
| received_at | DATETIME | 예 |   |  |
| processed_at | DATETIME | 아니오 |   |  |

## w6_review_holds

| 필드 | DB 타입 | 필수 | 키·관계 | 기본값 |
|---|---|---|---|---|
| inquiry_id | VARCHAR(36) | 예 | PK,FK w5_inquiries.id |  |
| call_id | VARCHAR(36) | 예 | FK w5_calls.id |  |
| reason | VARCHAR(80) | 예 |   |  |
| open | BOOLEAN | 예 |   |  |
| created_at | DATETIME | 예 |   |  |

## w5_result_corrections

| 필드 | DB 타입 | 필수 | 키·관계 | 기본값 |
|---|---|---|---|---|
| id | VARCHAR(36) | 예 | PK  |  |
| call_id | VARCHAR(36) | 예 | FK w5_results.call_id |  |
| revision | INTEGER | 예 |   |  |
| reviewer | VARCHAR(100) | 예 |   |  |
| reason | VARCHAR(1000) | 예 |   |  |
| payload | JSON | 예 |   |  |
| created_at | DATETIME | 예 |   |  |
- w5_uq_correction_revision: call_id, revision
