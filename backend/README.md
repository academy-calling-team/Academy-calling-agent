# 백엔드 0.4.0

FastAPI·MySQL·Redis 기반의 인증, 문의 접수, 큐 처리, 음성 워커 연동과 결과 저장을 담당합니다. 이번 연동 작업에서는 백엔드 처리 코드와 DB 구조를 변경하지 않았습니다.

- 구현: `schema.py`, `service.py`, `auth6.py`, `run_queue.py`, `http_worker*.py`
- [API·파트 연결 명세](../docs/api/README.md)
- [데이터 사전](../docs/database/data-dictionary.md) · [SQL](../docs/database/schema.sql)
- [공동 API·개인 시험 환경](../docs/collaboration/README.md)
- [서버 운영·배포](../docs/collaboration/서버_운영과_배포.md)

개인 코드 시험에는 공동 DB와 분리한 DB·Redis를 사용합니다. `init-db`는 기존 컬럼 변경을 적용하는 마이그레이션이 아닙니다.

## 회원가입 약관 동의

`POST /auth/register`는 `login_name`, `password`, `terms_agreed: true`가 필요하다.
false·누락·문자열·숫자는 422로 거부하며, 성공 시 서버 UTC 시각을
`w6_accounts.terms_agreed_at`에 저장한다. 로그인 본문은 기존 아이디·비밀번호만 사용한다.
프론트는 실제 동의 체크 상태를 가입 요청에 넣고, `/api/auth/register` 중계에서도 전달해야 한다.
UI만 추가하거나 중계에서 일괄 true로 설정하지 않는다. 프론트 연동 후 서버 코드 전환을 함께 확인한다.

공동 API를 쓰는 팀원은 동일한 `team8_dev` DB를 사용한다. PR 작성자는 해당 DB의 컬럼을
이미 추가했다고 보고했다. 다른 기존 DB에 코드를 적용할 때는 먼저 아래 조회로 확인한다.
`init-db`는 기존 테이블을 변경하지 않는다. 이 절차는 공유 DB에 다시 실행하라는 지시가 아니다.

```sql
SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'w6_accounts'
  AND COLUMN_NAME = 'terms_agreed_at';
```

결과가 없을 때만 해당 DB 관리자가 코드 전환 전에 적용한다. 기존 계정의 동의 시각은 NULL로 유지한다.

```sql
ALTER TABLE w6_accounts ADD COLUMN terms_agreed_at DATETIME NULL;
```

기존 로컬 관리자 생성 도구 `manage_admin6.py`는 가입 입력 변경에 아직 대응하지 않았다.
현재 공동 개발에서 사용하지 않으며, 사용 재개 전에 명시적 동의 처리와 입력 모델을 보완해야 한다.
