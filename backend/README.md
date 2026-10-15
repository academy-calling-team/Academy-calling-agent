# 백엔드 0.4.0

FastAPI·MySQL·Redis 기반의 인증, 문의 접수, 큐 처리, 음성 워커 연동과 결과 저장을 담당합니다. 이번 연동 작업에서는 백엔드 처리 코드와 DB 구조를 변경하지 않았습니다.

- 구현: `schema.py`, `service.py`, `auth6.py`, `run_queue.py`, `http_worker*.py`
- [API·파트 연결 명세](../docs/api/README.md)
- [데이터 사전](../docs/database/data-dictionary.md) · [SQL](../docs/database/schema.sql)
- [공동 API·개인 시험 환경](../docs/collaboration/README.md)
- [서버 운영·배포](../docs/collaboration/서버_운영과_배포.md)

개인 코드 시험에는 공동 DB와 분리한 DB·Redis를 사용합니다. `init-db`는 기존 컬럼 변경을 적용하는 마이그레이션이 아닙니다.