# 프론트 Node 공동 개발 환경

기존 상담 화면·가입/로그인·문의 접수/조회 기능을 표준 Next.js Node에서 실행한다. 공동백엔드는 team8_dev를 사용하는 /shared이다.

검증 환경: Node24, npm, Next16.3.4. frontend폴더에서:

```powershell
npm ci
Copy-Item .env.node.example .env.local
npm run dev
```

기존 .env.local이 있으면 덮어쓰지 않고 값을 확인한다. 브라우저는 http://127.0.0.1:3000.

ACADEMY_BACKEND_URL=https://team8-api.3.35.222.227.sslip.io/shared
FRONTEND_ORIGIN=http://127.0.0.1:3000

정식 실행은 npm run build → npm start. 타입 검사는 npm run typecheck. 현재PC에서실제설치·빌드·standalone기동·공동서버워커전체왕복을검증했다.

DB/API키를 프론트 설정에 넣지 않는다. 로컬Node서버가로그인쿠키를백엔드토큰으로중계한다. 이전Cloudflare플러그인설정과D1데이터는원래환경에보존되며,Node실행에서는현재상담흐름에필요한API만사용한다. 임시초안API는현재사용불가응답을준다.

세 파트 사용방법과 개인격리환경은 [공동 개발 안내](../docs/collaboration/README.md), 배포/로그/복구는 [서버 운영](../docs/collaboration/서버_운영과_배포.md) 참고.
