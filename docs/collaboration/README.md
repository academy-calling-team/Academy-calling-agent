# 세 파트 공동 개발 환경

운영 음성 엔진은 ClawOps다. 화면·API 시험은 기본적으로 목업 학원을 사용하며 실제 전화 시험은 음성 담당과 별도로 준비한다.

## 공통 주소

- 공동 API: https://team8-api.3.35.222.227.sslip.io/shared
- API 문서: https://team8-api.3.35.222.227.sslip.io/shared/docs
- 프론트 개발: http://127.0.0.1:5173
- 빌드 미리보기: http://127.0.0.1:4173

현재 프론트는 React·Vite·TypeScript다. `npm run dev`로 실행하며, 빌드 미리보기는 `npm run preview`다. 과거 Next.js의 3000번 주소와 `npm start`는 사용하지 않는다. 공동 API 배포와 각 PC 프론트 갱신은 별도다.

## 팀원 PC의 프론트와 공동 서버 연결

Git과 Node.js 24를 설치한다. 기존 작업이 있으면 새 폴더에 내려받아 첫 설치를 시험한다. Windows PowerShell 기준:

```powershell
git clone https://github.com/academy-calling-team/Academy-calling-agent.git Academy-pc-test
cd Academy-pc-test
git rev-parse HEAD
cd frontend
npm.cmd ci
if (!(Test-Path .env.local)) { Copy-Item .env.example .env.local }
npm.cmd run dev
```

이미 내려받은 폴더에서는 `git status`로 개인 수정사항을 보존한 뒤 팀이 시험할 커밋으로 맞춘다. 서로 같은 커밋을 사용하고 `git rev-parse HEAD` 결과를 기록한다. 설정 양식은 `frontend/.env.example`이다.

`frontend/.env.local`에는 아래 공개 주소를 설정한다. 기존 파일은 통째로 덮어쓰지 않는다.

```dotenv
ACADEMY_BACKEND_URL=https://team8-api.3.35.222.227.sslip.io/shared
FRONTEND_ORIGIN=http://127.0.0.1:5173
```

변경 후 서버를 재시작하고 http://127.0.0.1:5173 에 접속한다. 설치 후 `frontend/프론트_실행.cmd`를 더블클릭해도 된다. 5173번이 사용 중이면 자동으로 다른 포트로 옮기지 않으므로 기존 실행을 확인한다.

macOS/Linux에서는 `npm.cmd` 대신 `npm`을 사용한다. 최초 설정 복사는 `test -e .env.local || cp .env.example .env.local`로 기존 파일을 보존한다. DB 암호·내부 API 키·클라우드 자격증명은 프론트 실행에 필요 없다.

### 팀원별 시험

1. 시험용 학부모 계정 가입·로그인.
2. 홈·내 상담 직접 진입과 새로고침 후 로딩 완료 확인.
3. `is_mock=true`인 가상 시험 학원으로 질문 3개 접수.
4. 같은 문의 ID의 완료 상태와 질문별 결과 조회.
5. 로그아웃·재로그인 후 결과 유지, 다른 계정의 문의 접근 차단 확인.
6. 학원 계정은 별도 시험 계정으로 학원 등록·재조회·수정을 확인.

공동 API를 사용하는 가입·문의·학원 저장은 공동 개발 DB에 남는다. 목업 학원과 학원 계정이 등록한 실제 유형 학원을 구분한다. 새 실제 유형 학원은 현재 실통화 허용 정책에 따라 접수가 차단될 수 있다.

결과는 `이름 / OS / Node 버전 / 프론트 커밋 / API 버전 / 시험 항목 / 성공·실패 / 오류 화면`으로 남긴다. 서버 버전은 `/shared/version`으로 확인한다. 한 사람의 성공을 전원 확인으로 처리하지 않는다.

### 자동 검사와 빌드

```powershell
npm.cmd run typecheck
npx.cmd playwright install chromium
npm.cmd test
npm.cmd run build
```

화면 회귀 시험은 가짜 업무 API 응답을 사용하며 실제 전화나 공동 DB 쓰기를 수행하지 않는다. Windows에 Edge가 있으면 Chromium 설치 대신 `$env:PLAYWRIGHT_CHANNEL='msedge'`를 지정하고 시험할 수 있다.

빌드 화면은 `npm.cmd run preview` 후 http://127.0.0.1:4173 에서 확인한다. 쓰기 시험 시 `FRONTEND_ORIGIN`도 사용하는 주소에 맞추고, 개발 서버로 돌아갈 때는 5173번으로 복구한다.

## 백엔드·목업 워커까지 개인 PC에서 실행

Python 3.12와 Docker Desktop(Compose)을 준비한 뒤 저장소 최상위에서 실행한다.

```powershell
py -3.12 infra/setup-local.py
docker compose up --build -d
docker compose ps
```

macOS/Linux에서는 `py -3.12` 대신 Python 3.12를 가리키는 `python3`를 사용한다. 설정 도구는 기존 루트 `.env`를 덮어쓰지 않고 중단한다. 기존 설정이 있으면 새 시험 폴더를 사용하거나 필요한 `TEAM8_` 항목을 검토한다.

별도 `team8_local` DB, Redis, 목업 접수 볼륨을 사용한다. 공동 DB 설정을 복사하지 않는다.

| 구성 | 로컬 주소 |
|---|---|
| API 문서 | http://127.0.0.1:18770/docs |
| 목업 워커 문서 | http://127.0.0.1:18780/docs |
| MySQL | 127.0.0.1:13307 |
| Redis | 127.0.0.1:16380 |

프론트의 `ACADEMY_BACKEND_URL`을 `http://127.0.0.1:18770`으로 바꾸고 재시작해 같은 접수·조회 흐름을 확인한다. 로컬 주소에는 `/shared`를 붙이지 않는다. 공동 서버 시험으로 돌아갈 때는 `/shared`가 포함된 공통 주소를 복구한다.

코드 반영은 `docker compose up --build -d`, 중지는 `docker compose down`이다. `down -v`는 저장 데이터를 지우므로 일상적인 중지에 사용하지 않는다. 이 구성은 실제 전화를 걸지 않는다. Docker 전체 기동은 실행한 PC별 결과를 따로 기록한다.

## ClawOps 실제 통화와 공동 반영

[운영 기준](../음성_엔진_운영기준.md)과 [실통화 워커](../../voice/call_worker/README.md)를 따른다. `voice/.env.example`은 음성 담당의 설정 양식이다. 서비스 에이전트·허용 번호·지정 계정·서버와 워커의 활성화가 준비된 시험만 진행한다. 화면 확인만 하려고 실제 발신을 켜지 않는다.

코드는 작업 브랜치에서 수정·검증하고 PR로 검토한다. 최신 PR 자동 검사 통과 후 병합하고 배포 성공·`/shared/ready`·`/shared/version`의 대상 커밋을 확인한다. PC 백엔드·큐를 공동 DB에 연결해 서버 큐와 동시에 실행하지 않는다.

공동 목업 API만 확인하는 도구는 저장소 최상위의 `infra/shared-smoke.ps1`이다. 실행하면 전용 합성 계정과 문의가 공동 DB에 생성되며 화면 검증을 대신하지 않는다.

```powershell
powershell -ExecutionPolicy Bypass -File infra/shared-smoke.ps1
```

배포·재시작·로그·복구는 [서버 운영 절차](서버_운영과_배포.md)를 참고한다.
