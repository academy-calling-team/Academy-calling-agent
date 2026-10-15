# 응답 지연 측정 자료를 팀 저장소로 옮기기

- 날짜: 2026-10-11
- 작성자: 김규림
- 사용한 도구: Claude (claude.ai, Claude Code)
- 목적: claude.ai에서 9월~10/11에 만든 응답 지연 측정 스크립트, 10/7 측정 결과, 도구 조사 문서를 팀 저장소 구조에 맞게 옮기고, 새 PC에서 측정값이 재현되는지 확인

## 프롬프트

claude.ai 작업분(측정 스크립트, 조사 문서)의 대화 원문은 claude.ai 대화 "종합프로젝트 세션 관리 및 팔랑크스 음성 파이프라인"에 있다.

Claude Code에서 입력한 내용:

```
@capstone8-voice.zip
```

```
https://github.com/academy-calling-team/Academy-calling-agent
깃허브 연동
(노션의 10/11~10/14 날짜별 할 일 목록 붙여넣음)
목업은 다른 팀원이 한다고 했어
```

## 결과를 어떻게 썼는지

- 폴더 배치는 Claude가 제안한 것을 골라 그대로 씀: 측정 스크립트·결과 → `experiments/latency/`, 통화 역할 문구·테스트 케이스 → `voice/prompts/`, 조사·결제 안내·계획서 → `docs/`, 회의 자료 → `meetings/`
- `.env.example`에 ClawOps SIP·Vapi 번호 항목 이름을 추가하고, 모델 폴더(`experiments/latency/models/`)를 `.gitignore`에 추가
- 측정 재현: luna, Vapi Low 통화를 다시 돌려 응답 지연 값이 10/7 결과와 같은 것을 확인. Whisper 전사는 문장부호와 한두 단어가 다름
- 녹음, `.env`, 개인 작업 메모(CLAUDE.md)는 올리지 않음
