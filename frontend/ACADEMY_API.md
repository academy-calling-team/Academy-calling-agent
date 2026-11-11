# 학원 계정 및 정보 API

학원 운영자의 회원가입, 계정 유형 조회, 학원 정보 등록·수정 API입니다. 작업 브랜치 구현 기준이며 공동 DB 마이그레이션과 배포 후 사용할 수 있습니다.

## 인증 API 명세

`POST /auth/register`는 기존 login_name, password, terms_agreed 외에 필수 필드 `account_type: "parent" | "academy"`를 추가합니다. 기존 클라이언트가 이 필드를 생략하면 parent로 처리하여 호환성을 유지하는 방안을 권장합니다. 계정의 서비스 이용 유형은 기존 관리자 권한 role과 구분하며, 클라이언트가 회원가입을 통해 admin 권한을 얻을 수 없어야 합니다.

`POST /auth/login`은 공통 아이디·비밀번호 로그인 방식과 기존 token 응답 구조를 유지합니다.

`GET /auth/me`는 기존 필드를 유지하고 다음 정보를 추가합니다.

```json
{
  "inquirer_id": "user-id",
  "login_name": "academy_owner",
  "role": "member",
  "account_type": "academy",
  "academy_id": "academy-id",
  "academy_registration_status": "registered",
  "expires_at": "2026-11-10T15:00:00Z"
}
```

학원 정보가 등록되지 않았다면 academy_id는 null, 등록 상태는 unregistered로 반환합니다. 사용자 신원은 반드시 서버 세션을 기준으로 판단해야 하며, 브라우저에 저장된 계정 유형을 신뢰해서는 안 됩니다. BFF `/api/account`에서는 userId, accountType, academyId, academyRegistrationStatus를 매핑합니다.

## 내 학원 정보

클라이언트가 다른 학원의 ID를 지정하지 않도록, 현재 로그인한 사용자를 기준으로 다음 API를 추가하는 방안을 제안합니다.

| 백엔드 API | 프론트엔드 BFF 경로 | 동작 |
|---|---|---|
| GET /api/my-academy | GET /api/my-academy | 현재 계정에 연결된 학원 조회. 미등록이면 404 반환 |
| POST /api/my-academy | POST /api/my-academy | 학원 생성과 계정 연결을 원자적으로 처리. 성공 시 201 반환 |
| PUT /api/my-academy | PUT /api/my-academy | 현재 계정의 학원 정보 수정. 성공 시 200 반환 |

POST, PUT 요청 본문:

```json
{
  "name": "침산 배움학원",
  "phone": "053-000-0000",
  "region": "대구 북구 침산동",
  "address": "상세 주소",
  "classes": [
    {"subject_code": "MATH", "grade_code": "E3", "level_code": null}
  ],
  "call_hours": [
    {"day_of_week": 0, "start_time": "14:00", "end_time": "18:00"}
  ]
}
```

응답에는 위 정보를 모두 포함하고 academy_id, updated_at(UTC ISO 8601), version을 추가합니다. 다른 세션에서 수정한 내용을 덮어쓰지 않도록 PUT 요청에 조회 당시의 version을 포함하고, 버전이 일치하지 않으면 409를 반환하는 방안을 권장합니다.

지역은 GET /api/options의 regions를 사용합니다. address는 빈 값이 가능하며 최대 160자입니다. name은 필수이며 최대 80자입니다. phone은 필수이며 최대 25자로 제한하고 전화번호 형식을 검증합니다. 과목 코드는 KOR/ENG/MATH/SCI/SOC, 학년 코드는 E1–E6, M1–M3, H1–H3, 수준 코드는 HIGH/MID/LOW/null입니다. classes는 빈 배열을 허용하며 최대 50개까지 설정할 수 있고, 동일한 조합은 중복될 수 없습니다. call_hours는 비어 있을 수 없으며 최대 50개입니다. 요일은 월요일 0부터 일요일 6까지이고, 시간대는 Asia/Seoul입니다. 시작 시간은 종료 시간보다 빨라야 하며 같은 요일의 시간대는 겹칠 수 없습니다.

UI에서는 시간대 한 행에 여러 요일을 선택할 수 있습니다. API 연동 시 이를 여러 call_hours 항목으로 펼치고, 조회 시에는 시작·종료 시간이 같은 항목을 하나로 합칠 수 있습니다. 선호 대상은 기존 classes 구조에 대응하며, 문의 수신 선호를 나타내는 정보로 수강 등록 가능 여부를 의미하지 않습니다.

## 권한, 오류 및 연동 요구사항

- 기존 BFF에서 HttpOnly Cookie를 읽어 Bearer 세션 인증에 사용합니다. 쓰기 요청에는 기존 Origin 및 JSON Content-Type 검증을 유지합니다. token을 브라우저에 노출해서는 안 됩니다.
- academy 유형의 계정만 자신의 학원 정보를 조작할 수 있습니다. 서버는 세션에서 소속 학원을 확인해야 하며, 클라이언트가 임의로 지정하는 owner_id를 받아서는 안 됩니다.
- 401: 미로그인 또는 세션 만료. 403: 계정 유형 또는 소유 관계 불일치. 404: 학원 미등록. 409: 이미 등록됨 또는 버전 충돌. 422: 입력 필드 검증 오류. 429: 요청 횟수 제한. 5xx: 서비스 오류. 422 응답에는 필드 경로를 포함하되 비밀번호를 반환하지 않는 방안을 권장합니다.
- 학원 기본 정보, 선호 대상, 응대 시간 및 계정 연결은 트랜잭션으로 저장해야 합니다. 수정에 실패하면 일부 데이터만 반영된 상태가 남아서는 안 됩니다.
- 기존 `/api/academies/{id}/settings`는 classes/call_hours만 처리하고 임시로 admin 권한을 사용하므로, 학원 운영자의 직접 등록 흐름을 처리하기에는 부족합니다.
- BFF에는 my-academy의 인증 검사와 GET/POST/PUT 전달 처리가 필요합니다. 공개 학원 목록 조회와 학원 정보 관리 API를 구분하고, 관리 API에는 반드시 인증을 적용해야 합니다.
- 시뮬레이터의 가중치, 수동 대기 보정값 및 정렬 결과는 백엔드에 전송하지 않으며, 실제 발신 정책도 변경하지 않습니다.

## 2026-11-11 구현과 적용

- 계정당 학원 1개 등록, 서버에서 소유자 확인, 다른 학원 ID 지정 필드 제외
- 기존 계정의 account_type 기본값 parent, 학원 가입도 role은 member
- POST의 학원 생성·계정 연결·선호 조건·응대 시간 저장을 하나의 트랜잭션으로 처리
- PUT의 version 필수, 관리자 설정 수정도 같은 설정 버전으로 충돌 감지
- 새 학원의 기본 운영시간은 매일 00~24시, 실제 발신 후보 선정에는 등록한 응대 시간과 기존 서버 정책 적용
- 새 학원은 is_mock=false로 등록, 실발신은 기존 지정 시험 학원·계정·허용 번호 검사 적용
- 적용 SQL은 docs/database/migrations/20261111_academy_accounts.sql, 배포 전 백업과 실행 필요
- 기존 학원 계정 연결은 별도 운영자 확인 후속, 이번 등록에서는 서버가 새 academy_id 발급
