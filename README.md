## 공동 개발 환경 · 2026-10-14

공동 API: https://team8-api.3.35.222.227.sslip.io/shared/docs

PC프론트→공동API/DB→큐→음성목업워커→결과표시까지실제연결검증했다. 프론트는frontend에서npm ci→.env.node.example을.env.local로복사→npm run dev.

[세 파트 실행·개인 격리 환경](docs/collaboration/README.md) · [운영·배포·복구](docs/collaboration/서버_운영과_배포.md)

아래는 기존 프로젝트 안내다. 현재 공동 환경 주소·실행 상태는 위 문서를 따른다.

# 학원 문의 대행 보이스 에이전트

학부모가 고른 문의 항목으로 AI가 학원에 전화하고, 받은 답을 문의자별로 저장하는 시스템.

2026-2 종합설계프로젝트1 산학협력 8조 (㈜팔랑크스시스템즈)

## 팀

| 이름 | 파트 |
|------|------|
| 박찬원 (팀장) | 백엔드 |
| 유종민 | 백엔드 |
| 강유준 | 음성 AI |
| 김규림 | 음성 AI |
| 딩옌 | 프론트엔드 |

멘토: 이재현 이사 (팔랑크스시스템즈) / 지도교수: 김재수 교수

## 폴더 구조

```
backend/       FastAPI 서버, 발신 큐, 결과 저장 (MySQL)
voice/         음성 워커: 도구 연동(Vapi, ClawOps), 질문 문장 생성, 결과 추출
frontend/      문의 입력, 결과 조회 화면 (React)
docs/          설계 문서, API 명세, 데이터 명세, 테스트 기준
experiments/   음성인식 비교, 응답 지연 측정 같은 실험 기록과 결과
meetings/      주차별 회의록
prompts/       생성형 AI 사용 기록 (과목 요건)
```

## 작업 규칙

- `main`에 바로 올리지 않고 브랜치를 만들어 PR로 합침
- 브랜치 이름은 `파트/작업` 형식: `voice/stt-compare`, `backend/inquiry-api`, `frontend/result-page`, `docs/api-spec`
- 커밋 메시지는 `[파트] 한 일` 형식: `[voice] Vapi 웹 통화 연동`
- API 키와 비밀번호는 `.env`에만 두고 절대 커밋하지 않음 (`.env.example`에 항목 이름만 적기)
- 통화 녹음 파일은 올리지 않음. 필요하면 노션이나 드라이브 링크로
- 생성형 AI를 쓴 작업은 `prompts/`에 기록

## 문서

정리된 문서는 노션 "종프 8조 홈"에 있고, 확정된 버전은 `docs/`에도 올림.
