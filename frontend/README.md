# 학원의신 · React 프론트

React·Vite·TypeScript 화면과 같은 출처의 `/api` 중계를 사용한다. 공동 백엔드는 배포된 서버를 사용하며 프론트는 각 PC에서 실행한다.

## 최초 실행 · Windows PowerShell

Node.js 24를 설치하고 이 폴더에서 실행한다.

```powershell
npm.cmd ci
if (!(Test-Path .env.local)) { Copy-Item .env.example .env.local }
npm.cmd run dev
```

브라우저: http://127.0.0.1:5173 . 설치 후 `프론트_실행.cmd`를 더블클릭해도 된다. 기존 `.env.local`은 덮어쓰지 않는다.

```dotenv
ACADEMY_BACKEND_URL=https://team8-api.3.35.222.227.sslip.io/shared
FRONTEND_ORIGIN=http://127.0.0.1:5173
```

설정 변경 후 서버를 재시작한다. DB 암호·내부 API 키는 프론트에 필요 없다. `VITE_` 변수에 비밀값을 넣지 않는다. macOS/Linux는 `npm.cmd` 대신 `npm`, 최초 복사는 `test -e .env.local || cp .env.example .env.local`을 사용한다.

## 검사와 빌드

```powershell
npm.cmd run typecheck
npx.cmd playwright install chromium
npm.cmd test
npm.cmd run build
```

Edge를 사용하려면 `$env:PLAYWRIGHT_CHANNEL='msedge'`를 지정한 뒤 `npm.cmd test`를 실행한다. 회귀 시험의 업무 API는 가짜 응답이며 실제 전화·공동 DB 쓰기가 없다.

빌드 미리보기는 `npm.cmd run preview`, 주소는 http://127.0.0.1:4173 이다. 개발 5173·미리보기 4173은 점유 시 다른 포트로 자동 이동하지 않는다. `npm start`는 제공하지 않는다.

## 화면과 데이터

- `/`, `/tasks`, `/new`, `/detail/:id`: 본인 문의·접수·결과·통화 기록.
- `/login`, `/register`: 학부모/학원 계정 가입과 공통 로그인.
- `/academy/register`, `/academy/manage`: 학원 계정의 실제 API 등록·조회·수정. 버전 충돌은 새로고침 후 확인한다.
- `?preview=mock`: 브라우저 내 격리된 미리보기. 모의 계정 비밀번호는 저장·검증하지 않으며 실제 계정과 연결되지 않는다.

실제 모드의 가입·문의·학원 저장은 연결한 백엔드 DB에 반영된다. 화면 시험은 목업 학원을 사용하고, ClawOps 실제 전화는 지정 계정·허용 번호·서버 설정을 맞춘 별도 시험으로 진행한다.

프론트의 `/api/auth/*`, `/api/account`, `/api/options`, `/api/academies`, `/api/inquiries`, `/api/my-academy`는 기존 HttpOnly 세션·소유 권한을 유지하는 중계 경로다. 자세한 학원 입력 계약은 [ACADEMY_API.md](ACADEMY_API.md)를 참고한다.

[팀원 설치·접수/조회 시험·전체 로컬 환경](../docs/collaboration/README.md), [ClawOps 운영 기준](../docs/음성_엔진_운영기준.md).
