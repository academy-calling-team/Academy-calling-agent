# 백엔드 데이터 구조 검토본

`backend/schema.py`가 기준이며 21테이블·125필드·20외래키이다.
`schema.sql`은 MySQL 신규 개발 DB의 구조 검토용 DDL, `data-dictionary.md`는 필드 자료다.
기존 테이블의 데이터/계정/마이그레이션이 포함된 덤프가 아니다.
직접 SQL 실행 대신 별도 개발 DB에서 backend/manage.py init-db로 시작한다.

2026-10-07 로컬 기록에는 AWS 공유 DB에 이 구조 21개 추가와 기존 5개 보존이 확인되어 있다.
이 제출 작업에서는 AWS에 접속하거나 DB를 변경하지 않았으며 최신 API 배포를 뜻하지 않는다.
[가로 ERD](../erd/README.md)를 함께 검토한다.
