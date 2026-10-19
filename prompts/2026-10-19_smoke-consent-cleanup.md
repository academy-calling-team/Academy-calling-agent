# 공동 서버 확인 스크립트의 약관 동의 반영과 로컬 실행 파일 정리

- 날짜: 2026-10-19
- 작성자: 강유준
- 사용한 도구: Claude (Claude Code)
- 목적: 10/18 공동 API 배포 뒤 남은 문제를 고친다. `infra/shared-smoke.ps1`이 약관 동의 없이 가입해 422가 나는 문제를 고치고, 저장소에 잘못 올라간 로컬 실행 파일을 Git 추적에서 뺀다.

## 프롬프트

```
powershell -ExecutionPolicy Bypass -File infra/shared-smoke.ps1 이거 어디에서 써야하는지 잘모르겠네. 너가 발견 했다는 문제 3개는 전부 수정하면 될 것 같아.
```

## 결과를 어떻게 썼는지

- `infra/shared-smoke.ps1`: 회원가입 본문에만 `terms_agreed: true`를 넣었다. 로그인 본문은 그대로 두었다. 백엔드 모델이 모르는 필드를 거부하기 때문이다(`extra='forbid'`). PowerShell 구문 검사와 본문 모양만 확인했다. 공동 서버에 계정을 만드는 실제 실행은 팀원이 직접 한다.
- `docs/collaboration/README.md`: 스크립트를 실행하는 위치(저장소 최상위 폴더)와 명령을 적었다.
- `frontend/.wrangler/`, `frontend/.vinext/`, `meetings/.dev.vars`를 Git 추적에서 뺐다. 로컬 실행 상태 파일과 개인 PC 경로가 들어 있고, 앱 실행에는 쓰이지 않는다. PC에 있는 파일은 지우지 않는다. `.gitignore`에 `.vinext/`를 더했다(`.wrangler/`, `.dev.vars`는 이미 있음).
- `frontend/.openai/`는 D1 설정에서 참조하므로 그대로 두었다.
