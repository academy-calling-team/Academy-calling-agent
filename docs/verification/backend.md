# 백엔드 검증 기록

개발본 0.4.0 · 2026-10-11. 문서 정리 전 브랜치에서 확인한 결과이며 이번 변경은 문서만 다룬다.

| 검증 | 결과 | 범위 |
|---|---|---|
| 백엔드 직렬 API·설정·실발신 차단 | 11 passed | 임시 SQLite |
| 기존 음성 목업 테스트 | 26 passed | 음성 코드 변경 없음 |
| 두 묶음 함께 실행 | 37 passed, 3 warnings | 기존 개발 가상환경+분리된 python-dotenv. 새 PC 설치 시험 아님 |
| 기존 MySQL/Redis 통합 테스트 | 72 tests collected | 이번에는 수집만, 전체 재실행 아님 |
| BE API ↔ 음성 목업 | 정상·일부 미확인·부재중 후 재통화 확인 | 임시 SQLite/TestClient/MockTransport·합성 목적지, 실제 서버 간 HTTP 아님 |
| 번호 null·동일 ID 다른 본문 | 거절·잘못된 성공 해석 재현 | 미해결 사항은 [연결 안내](../api/README.md)에 명시 |
| OpenAPI·결과 스키마·SQL 생성 | 21테이블 정의 생성 | DB 접속·실제 마이그레이션 없음 |

경고 3개는 Starlette TestClient 관련 1개와 FastAPI on_event 폐기 예정 관련 2개다. 과거 10/5의 통합 테스트 72개·합성 문의 100개 결과를 이번 재실행으로 표시하지 않는다.

재현 명령(설치된 개발 환경, 저장소 루트):

```text
python -m pytest backend/tests/test_portable_smoke.py voice/mock_worker -q
```

MySQL/Redis 통합 테스트는 [실행 안내](../../backend/README.md)의 별도 로컬 *_test DB·별도 Redis DB 설정을 따른다. 실제 프론트/음성 서버 연결, 최신 AWS API 배포, Docker·새 PC 설치, 실전화·문자 발신은 아직 확인하지 않았다.

이번 문서 간소화에서는 백엔드 실행 코드·DB 정의·API JSON을 변경하지 않았다. 문서 내부 링크와 변경 범위 및 제외 자료의 로컬 보존을 확인한다. 기존 상세 검증 근거는 로컬 프로젝트 자료와 이전 커밋에 보존한다.
