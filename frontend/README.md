# 프론트엔드 · Node 실행

기존 화면을 표준 Next.js·Node로 실행하고 공동 백엔드에 연결합니다. 검증 환경은 Node.js 24.x입니다.

`frontend`에서 최초 실행:

```powershell
npm.cmd ci
Copy-Item .env.node.example .env.local
npm.cmd run dev
```

기존 `.env.local`은 덮어쓰지 않고 `.env.node.example`의 주소와 비교합니다. 접속 주소는 http://127.0.0.1:3000 입니다.

- 개발: `npm.cmd run dev`
- 타입 검사: `npm.cmd run typecheck`
- 빌드·정식 실행: `npm.cmd run build` → `npm.cmd start`

로그인은 공동 백엔드 기준이며, 현재 쓰지 않는 D1 초안 저장과 ChatGPT 로그인 대체 경로는 사용하지 않습니다. 공동 서버의 답변은 음성 목업 결과입니다.

[공동 환경·개인 백엔드 연결](../docs/collaboration/README.md)