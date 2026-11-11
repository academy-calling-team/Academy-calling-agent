# 학원 운영 반 기반 문의 우선순위 스코어링 및 스키마 설계 기록

## 1. 프롬프트 작성 목적
- 학원 선호도 매칭 시 학년/과목/수준 개별 매칭으로 발생하는 교차곱 오류(Cartesian product) 해결
- 기아 상태(Starvation) 방지를 위한 대기 시간 에이징(Aging) 점수 산정 알고리즘 구축
- Pydantic strict 검증 및 SQLAlchemy 스키마 설계

## 2. 주요 프롬프트 및 논의 내용
- 학원 선호도 설정 입력 시 가상의 반 조합으로 잘못 매칭되는 문제를 방지하기 위해 `w5_academy_classes` (학년·과목·수준 조합) 테이블 구조 도출
- 선호 조건 미맞춤 문의의 무한 대기 현상을 방지하기 위해 10분당 1점씩 최대 40점의 대기 보정 점수 계산 로직 작성
- 기존 `test_portable_smoke.py` 스모크 테스트 수치 동기화 (테이블 24개, 컬럼 146개, 외래키 23개)

## 3. 적용 결과
- `backend/schema.py`, `backend/contracts.py`, `backend/service.py` 내 우선순위 계산 알고리즘 및 스키마 적용
- PR #44 작성 및 CI 테스트 통과 후 `main` 병합 완료