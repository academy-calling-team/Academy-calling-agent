# 백엔드 0.4.0 · 공동 개발

공동 API: https://team8-api.3.35.222.227.sslip.io/shared/docs
공동 DB: 기존DBeaver의team8_dev,최신테이블w5_/w6_. 공동서버큐와음성팀목업워커가연결돼문의가자동처리된다. 실제전화/문자는발신하지않는다.

회원가입·로그인·세션, 문의·질문·결과, MySQL outbox/Redis큐·재시도, HTTP워커접수/결과, 수정이력·검토보류·실패안내dry-run을구현했다. 21테이블정의는schema.py. API와DB명세는docs/api 및docs/database.

개인PC에서코드를시험할때는공유DB의큐를추가실행하지않고별도로컬DB/Redis를사용한다. 저장소루트에서python infra/setup-local.py, docker compose up --build -d로격리환경을준비한다. API http://127.0.0.1:18770/docs. compose로초기화를담당하므로공유DB에init-db를실행하지않는다.

기존 네이티브 실행은 루트 .env의 MYSQL_*·REDIS_URL·APP_MODE·INTERNAL_API_KEY를 로컬 시험 환경으로 설정하고 backend에서 init-db/seed-mock → uvicorn serve6:build --factory --host 127.0.0.1 --port 18770 순서다. 큐는 python run_queue.py --worker-url http://127.0.0.1:18780으로 실행하며 --simulate-results와 함께 쓰지 않는다.

init-db는create_all이며기존컬럼변경을자동적용하지않는다. DB구조변경은schema.py·SQL/명세와검토된마이그레이션을함께관리한다. 실제값수정은커밋후API재조회에반영되지만Git에자동반영되지는않는다.

자세한공동/개인사용법: [공동 개발 안내](../docs/collaboration/README.md).
