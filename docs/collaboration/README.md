# 세 파트 공동 개발 환경

## 지금 사용할 공통 주소

- API: https://team8-api.3.35.222.227.sslip.io/shared
- Swagger: https://team8-api.3.35.222.227.sslip.io/shared/docs
- DB: 기존 DBeaver 연결의 team8_dev. 최신 테이블은 w5_/w6_.

프론트 PC → 공동 API → 공유 MySQL/Redis → 서버 큐 → 음성팀 목업 워커 → API 결과 저장 → 프론트 결과 표시가 실제 연결돼 있다. 큐와 워커는 서버에서 상시 실행한다. 정상 answered 목업이며 실제 전화는 걸지 않는다. /docs의 과거 프론트용 별도 환경은 보존했지만 공동 개발 기준은 /shared로 통일한다.

## 프론트 담당과 화면 시험을 할 팀원

검증 환경은 Node 24와 npm이다. 이 전달 소스를 풀고 frontend에서 실행한다.

```powershell
npm ci
Copy-Item .env.node.example .env.local
npm run dev
```

이미 .env.local이 있으면 덮어쓰지 말고 ACADEMY_BACKEND_URL을 위 /shared 주소로, FRONTEND_ORIGIN을 http://127.0.0.1:3000으로 확인한다. 브라우저는 http://127.0.0.1:3000 에서 연다. 새 개발계정으로 회원가입/로그인→새상담→가상시험학원→학생조건/질문→접수→결과를 확인한다. 학원·학생 정보와 계정은 목업이다. DB암호·INTERNAL_KEY·AWS자격증명은 프론트 실행에 필요 없다.

정식 Node 실행 확인은 npm run build 후 npm start. 표준 Next.js의 standalone 실행을 사용하며 기존 Cloudflare 플러그인은 필요 없다. 기존 화면·문의 API는 유지했고, 현재 화면에서 쓰지 않는 D1 초안/ChatGPT로그인은 Node공동환경에서 사용하지 않는다. 과거 원본과 데이터는 원래 브랜치/환경에 보존된다.

## 백엔드·음성 담당의 개인 코드 시험

공동 서버 버전을 그대로 이용하려면 위 API 또는 프론트를 사용한다. PC에서 수정한 코드는 서버에 자동 적용되지 않는다.

서버 데이터와 분리한 개인 환경은 Docker Desktop(Compose)과 Python으로 준비할 수 있다.

```powershell
python infra/setup-local.py
docker compose up --build -d
docker compose ps
```

이 명령은 별도 로컬 team8_local DB와 Redis, 워커 접수 볼륨을 사용한다. 공동 DB 설정을 복사하지 않는다. 로컬 API는 http://127.0.0.1:18770/docs, 목업 워커는 http://127.0.0.1:18780/docs. 로컬 DBeaver 포트는 13307, Redis는 16380이다. 프론트까지 개인 코드로 시험하려면 frontend/.env.local의 ACADEMY_BACKEND_URL을 http://127.0.0.1:18770으로 바꾼다. 공동 서버 시험을 할 때는 /shared 주소로 되돌린다.

수정한 로컬코드 반영은 docker compose up --build -d. 중지는 docker compose down. down -v는 저장데이터를 지우므로 사용하지 않는다. 현재 PC에는 Docker CLI가 없어 개인Compose기동은 실제검증하지 않았으며, 정의·환경변수·포트·모듈은 정적검증했다. 공동서버의실제MySQL/Redis/워커왕복과PC의정식Node기동은별도실검증완료다.

PC에서 공동서버 접근만 확인하려면 PowerShell에서 infra/shared-smoke.ps1을 실행한다. 전용 합성계정·문의가공유DB에생기고,토큰/비밀번호는출력하지않는다.

## 공동 서버에 코드 반영

파트담당은개인브랜치에서수정·검증하고PR로검토한다. 검토된버전만배포담당이서버에반영한다. PC의백엔드와서버큐를같은공유DB로동시에실행하지않는다. 개인시험은위로컬DB를사용한다.

현재 소스는 backend/shared-collaboration-env 로컬 작업 브랜치와 ZIP으로 제공한다. 원격 GitHub에 push/병합하지 않았다. 최초 안내문의 재시도·실통화·실측 지연 등 최종 요구 완료로 해석하지 않는다.

배포·재시작·로그·복구는 [운영 절차](서버_운영과_배포.md) 참고.
