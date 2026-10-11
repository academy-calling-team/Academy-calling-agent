# 백엔드 개발본 0.4.0

상태: 로컬 검토용. FastAPI + MySQL + Redis, 실제 전화·문자 발신은 미구현.
기존 5·6주차 소스를 저장소 구조에 맞춰 정리한 사본이며 팀 공동 버전 확정 전이다.

## 구현 범위

- 개발용 회원가입/로그인, Argon2 암호 해시, 세션 만료/폐기, member/admin 구분
- 문의·질문 저장, 본인 목록/상세 조회, 동일 요청 중복 방지
- MySQL outbox + Redis Streams, 통화 예약/재시도/동시 처리 제한
- 가상 워커 접수/조회, 통화 상태·결과 중복/역순 처리
- 시간 미정 재통화 검토 보류, 원본 보존 교정 이력, 실패 안내 dry-run
- readiness와 운영 조회, Vapi 형식 오프라인 변환·격리

## 파일 안내

| 파일 | 역할 |
|---|---|
| api.py / contracts*.py | 프론트·워커 요청 검증과 HTTP API |
| schema.py / service.py | 21테이블 정의와 문의/통화 처리 |
| auth6.py / ops6.py | 인증·권한·운영 검토 |
| redis_queue.py / run_queue.py | 큐 처리와 명시적인 가상 결과 생성 |
| worker.py / http_worker*.py | 가상 워커와 HTTP 접수 계약 |
| provider6.py | Vapi 형식 오프라인 변환. 실제 발신/공개 웹훅 서버 아님 |
| settings.py / local_runtime.py / serve6.py | 환경 설정·DB 연결·서버 시작 |
| manage.py / manage_admin6.py | 명시적인 개발 DB 준비·관리자 생성 |
| tests/ | 기존 통합 테스트와 이번 제출 구조 검증 |

숫자 6이 붙은 파일명은 기존 코드의 이력이며 저장소의 명명 규칙을 새로 확정한 것은 아니다.

## 개발 환경 실행

Python 3.12, 별도 개발 MySQL 8+, Redis가 필요하다. 아래 명령은 저장소 루트에서 시작한다.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend/requirements.txt
Copy-Item backend/.env.example .env
```

루트 `.env`에 개발 DB의 MYSQL_* 값과 REDIS_URL을 입력한다. INTERNAL_API_KEY는
암호관리 도구 등에서 생성한 32자 이상의 임의 값으로 설정한다. 실제 값을 문서/PR에 붙이지 않는다.
CORS_ORIGINS에는 프론트 개발 화면의 Origin을 쉼표로 구분한다. APP_MODE는 development_mock만 허용한다.
OS 환경 변수가 `.env`보다 우선한다. 공유/AWS DB 대신 별도 개발 DB를 먼저 사용한다.

```powershell
cd backend
python manage.py init-db
python manage.py seed-mock
uvicorn serve6:build --factory --host 127.0.0.1 --port 18770
```

API 문서: http://127.0.0.1:18770/docs. 상태: /health와 /ready.
초기화는 create_all이며 기존 테이블의 변경/마이그레이션을 수행하지 않는다.
`/auth/register`와 `/auth/login`으로 개발 계정을 만들고 Bearer 세션을 사용한다.
가상 학원 ID는 demo-academy. 개발 계정은 실제 학부모 신원 인증을 의미하지 않는다.
큐 실행은 별도 터미널에서 `python run_queue.py --simulate-results`를 사용한다.
생성 결과는 합성 값이며 업무 시간/학원 정책에 따라 처리 시점이 달라진다.

## 검증

```powershell
cd backend
python -m pytest tests/test_portable_smoke.py -q
```

위 검증은 임시 SQLite에서 직렬 API 왕복·설정·목업 제한을 확인한다. MySQL/Redis 동시성 검증을 대체하지 않는다.
기존 72개 통합 테스트는 별도 로컬 MySQL DB(이름 끝 `_test`)와 Redis의 0이 아닌 DB 번호를
TEST_* 환경 변수로 설정한 뒤 아래처럼 실행한다. 해당 테스트 DB에 감사 행이 누적된다.
설정 누락 시 건너뛰지 않고 실패하며 실제 서비스 DB를 테스트 대상으로 사용하지 않는다.

```powershell
python -m pytest tests/test_backend.py tests/test_extensions.py tests/test_week6.py -q
```

## 이번 업로드와 음성 목업 대조

이번 코드는 backend/development-api-040 브랜치의 검토 대상이다. 기존 음성팀 구현과 루트 설정 파일은 보존했다.
[검증 결과](../docs/verification/backend.md)와 [파트 연결 안내](../docs/api/README.md)을 먼저 확인한다.
기본 큐는 자체 목업을 사용하며 음성팀 워커를 자동 선택하지 않는다. 외부 워커 연결용 설정·번호 규칙·409 처리는 후속 검토 대상이다.
루트 .env가 이미 있으면 덮어쓰지 말고 backend/.env.example의 필요한 항목만 검토해 추가한다. 음성팀 설정은 voice/.env를 사용한다.

## 명세와 남은 작업

[문서 안내](../docs/README.md), [API·파트 연결](../docs/api/README.md),
[데이터 사전](../docs/database/data-dictionary.md), [SQL](../docs/database/schema.sql),
[검증 결과](../docs/verification/backend.md)를 참고한다.
`python generate_docs.py`는 DB 접속 없이 OpenAPI/결과 스키마/MySQL DDL을 생성한다.
데이터 사전과 ERD는 schema.py 변경 후 별도 검토가 필요하며 자동 갱신 완료로 간주하지 않는다.

실제 음성 워커·번호·Vapi/ClawOps API·웹훅 인증·분석 지연·프론트 실제 연결과
최신 API AWS 배포는 남아 있다. 워커 HTTP 어댑터는 is_mock=true만 허용한다.
Vapi 결제와 실제 통합 성공은 구분한다. 기본 정책 수치는 개발값이며 팀/멘토 확정 전이다.
