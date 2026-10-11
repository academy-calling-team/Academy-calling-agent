# 음성 목업과 백엔드 간극 검토

2026-10-11. 사용자 요청에 따른 비교 분석이며 GitHub·노션·AWS·기존 구현·DB 변경 없음.

## 비교 기준

- 음성 실행 코드: 기준 main `c724e3c`, 목업 구현 커밋 `7f1f68b`. 읽기 사본 `Academy-calling-agent/voice/mock_worker/`.
- 음성 실험 대본·자료: `origin/voice/latency-measure`를 재조회. 최근 변경은 결제 안내의 전화번호 줄 삭제이며 목업 실행 코드 변경은 아님.
- 백엔드: `제출자료/20261011_GitHub_백엔드_반영검토/Academy-calling-agent/backend/`, 관련 docs·루트 설정. 현재 개발 원본의 service/contracts/schema/http_worker6도 참고. 업로드 준비본은 원격에 아직 반영되지 않음.
- AWS 실행 서버/노션 현행 전체를 이번에 재조회한 것은 아님. AWS 구버전 실행 상태는 기존 기록이며, 이번 테스트는 로컬 임시 환경에 한정.

## 핵심 결론

기본 이벤트·결과·질문 6종 형식은 맞는다. 그러나 바로 연결되는 공동 실행 환경이 준비된 상태는 아니다. 실제 연결을 막는 번호 필드, 외부 워커 선택이 없는 실행기, 서로 다른 환경 설정 이름·위치, 백엔드 어댑터의 충돌 은폐 문제를 먼저 조정해야 한다. 수강료는 두 실행 코드 사이의 차이보다 음성 실험 대본과 양쪽 실행 코드의 차이다.

## 즉시 연결에 영향을 주는 간극

| ID | 차이·근거 | 영향 | 조정 제안·담당 |
|---|---|---|---|
| G01 | BE `manage.py`는 목업 학원 phone=None. `service.reserve()`는 그 값을 to로 전송. 음성 `app.CallRequest.to`는 문자열 필수. | 실제 음성 워커에서 422. 결과 미저장, 백엔드는 접수 불명확 상태로 남음. 임시 DB에서 재현. | BE·음성: mock에서만 null 허용 여부 합의 또는 발신 기능과 분리된 합성 식별값 사용. 실번호 투입으로 해결하지 않음. |
| G02 | BE `run_queue.py`는 `MockWorker`를 직접 만들고 `WorkerHttpAdapter`를 선택하지 않음. `--simulate-results`는 BE `make_result`를 직접 저장. | 워커를 띄워도 문서의 기본 실행 명령은 새 음성 워커에 요청하지 않음. 외부 워커와 자체 결과 생성을 동시에 쓰면 결과 본문 충돌 가능. | BE: 내부 목업/음성팀 HTTP 워커 실행 모드 분리, 외부 모드에서는 자체 결과 생성 비활성. 워커 URL 설정과 README 추가. |
| G03 | BE는 루트 .env의 INTERNAL_API_KEY, 음성은 voice/.env의 INTERNAL_KEY·BACKEND_URL. 음성용 .env.example 항목과 BE 후보 루트 파일의 항목도 다름. HTTP 헤더는 양쪽 모두 X-Internal-Key. | 같은 헤더라도 서로 다른 값을 설정하면 401. 준비 패키지의 .env.example을 그대로 덮어쓰면 음성 설정 항목이 빠짐. | BE·음성: 각 설정 파일 위치, 키 이름 매핑, 동일 값 사용 및 URL을 공동 실행 안내에 명시. 루트 설정 예시를 합칠 때 양쪽 항목 보존. 실제 키는 문서·PR에 쓰지 않음. |
| G04 | 음성 main()은 127.0.0.1 바인딩. BE 외부 어댑터는 원격 URL이면 HTTPS 필수. | 각자의 PC에 실행하면 다른 PC나 AWS가 localhost로 접근할 수 없음. 같은 PC 실행은 가능. | 공동: 먼저 같은 PC 직렬 시험. PC 간 연결 시 승인된 접근 경로·HTTPS·방화벽을 별도 정함. 현재 포트 안내만으로 연결 완료 처리하지 않음. |
| G05 | 음성은 동일 call_id·다른 본문에 409. BE http_worker6.accept는 409도 접수 불명확과 같이 GET 조회하고 accepted=true면 성공 처리. GET에는 payload_hash가 없음. | 기존의 다른 본문을 접수한 기록을 새 요청의 성공으로 오인. 실제 409→GET 200→성공 반환을 재현. | BE: 명확한 401/409/422와 네트워크 응답 유실을 구분. 409를 성공으로 변환하지 않음. 필요하면 접수 본문 지문 대조 계약 추가. 음성의 409 규칙은 유지. |

G05는 이번 실험에서 발견한 백엔드측 결함이다. 어댑터가 수정되지 않으면 충돌 확인을 했더라도 호출자는 성공으로 받아들인다. 또한 Service.deliver는 TimeoutError/ConnectionError만 처리하므로 어댑터의 거절 예외와 큐의 보류/실패 기록 방식도 함께 설계해야 한다.

## 기능 범위·저장·시험의 간극

| ID | 현재 차이 | 영향·다음 조치 |
|---|---|---|
| G06 | 음성 실험 대본은 자리·수업 시간·수강료/교재비·레벨테스트·통학·상담 시간. 양쪽 실행 코드는 shuttle/pickup/level_fit/vacancy/level_test/class_time 6종만 지원. | 수강료가 현재 음성 목업에서는 되는 기능이라는 뜻이 아님. 둘 다 tuition 거절. 추가 합의 시 프론트 선택, InquiryInput, 음성 QuestionCode/결과 생성, AnswerInput, 명세를 함께 변경. 금액은 예/아니오 규칙에 맞지 않으므로 답변 타입도 설계. 새 DB 테이블 생성은 저장 방식 결정 후 판단. |
| G07 | 음성은 SQLite receipts(payload/scenario/received_at/delivered_at), BE는 자신의 시험 워커용 w5_mock_worker_receipts(payload/payload_hash/received_at). | 별도 역할이라 테이블 차이 자체는 오류 아님. 음성팀 워커 연결 시 BE 시험 접수 테이블이 자동 채워지지 않음. 문의·통화·결과는 BE DB, 접수·전송 책임은 음성 DB로 문서화. 음성 접수 202와 백엔드 결과 저장 완료를 구분. |
| G08 | 음성 sender는 일시 오류 3회 후 pending 유지. 실행 중 주기적 재전송 없음. 재시작 때 pending 전부 재전송. BE에는 결과 대기 제한·timeout 처리 있음. | 음성은 접수됨이라고 조회되는데 BE에는 끝내 결과가 없을 수 있음. BE timeout 뒤 늦은 결과는 저장되더라도 적용되지 않을 수 있음. 음성: 실패 이유·다음 시도·영구 거절 상태 추가. 공동: 결과 도착 제한과 늦은 결과 정책 합의. |
| G09 | BE는 answered/no_answer/busy/rejected/machine/invalid_number 및 callback_requested/callback_at, 고지 미완료 실패 등을 지원. 음성 생성 시나리오는 answered/partial/no_answer/retry뿐. callback=false, 고지는 연결 시 항상 true. | 기본 흐름은 시험 가능하지만 바쁨·거절·ARS·잘못된 번호·시간 미정 재통화·고지 실패는 이 목업으로 검증 불가. 음성 시나리오 확장 후 BE 상태·검토 보류·재발신·실패를 같이 시험. |
| G10 | 음성 answered 답은 학생 조건과 무관한 고정 예시. level_fit는 중2 중간 수학반, shuttle는 침산동. BE는 여러 학년·과목·수준·지역을 허용. | 다른 조건 문의에도 동일 답을 받을 수 있음. 계약 오류보다 테스트 데이터의 의미 차이. 가짜임을 유지하고 시험 입력을 고정하거나 조건에 맞게 결과 생성. |
| G11 | 음성 생성 결과는 latency=null, duration_sec=0, transcript=[], recording_url=null. 실험 브랜치는 별도 JSON 통계·전사 자료 보유. BE 결과의 latency는 mean_ms/p95_ms/turns, 전사는 speaker/at_ms/text. | 실험 JSON을 BE result에 그대로 붙이면 필드명·단위·구조가 맞지 않음. 이번 목업의 빈 측정값은 합성 데이터라 허용되는 상태. 실제 연동에서는 변환 책임·초→밀리초·전사 시간 기준·측정 정의 합의 필요. 실험결과를 자동 저장하는 기능은 양쪽에 없음. |
| G12 | 음성 fake_backend는 dict 본문과 ID 중복만 확인. 테스트는 백엔드 규칙 일부를 직접 재작성. BE는 요청 질문 ID/code 대조, 결과 ID 충돌, 원본 불변, 최신 통화 적용 여부 등을 검증. | 음성팀 단독 테스트 성공은 실제 BE 연결 성공과 다름. 공통 스키마를 같은 버전으로 관리하고 실제 BE API 왕복 시험 추가. BE worker_openapi는 dict 요청이라 상세 구조를 충분히 표현하지 못함; 음성 모델과 합의된 요청 스키마로 문서 생성 개선 필요. |

G06/G09/G11은 미지원 기능이나 시험 범위 차이이며 현재 기본 목업 결과의 형식 오류로 분류하지 않는다. 둘 다 실통화 미구현이라는 점도 차이가 아니라 공통 한계다. 대본의 녹취 고지 누락은 실통화 대본 적용 시 추가 점검 항목이며 mock의 disclosure=true가 고지 성공 증거는 아니다.

## 실제 대조 검증

`check_gaps.py`가 임시 SQLite 2개와 TestClient/MockTransport를 사용한다. 실전화·외부 네트워크·MySQL·Redis·AWS 접근 없음. 검증용 학원/사용자만 임시 생성하고 종료 후 삭제. 기존 source/설정/DB 변경 없음.

| 시험 | 결과 |
|---|---|
| BE 기본 목업 phone=None → 음성 워커 | HTTP 422, accepted=false, 결과 0건 |
| 합성 목적지 문자열 + 질문 6종 → 정상 결과 | BE 저장·조회 completed, 미확인 0 |
| 합성 목적지 문자열 + 질문 6종 → 일부 미확인 | BE completed, 마지막 질문 unresolved 1건. completed가 모든 질문의 답 확보를 뜻하지 않음 |
| 첫 시도 부재중 → BE 시계 301초 진행 → 두 번째 요청 | retry_wait → completed |
| 같은 call_id·다른 학원명 | 음성 직접 요청 409. BE 어댑터는 accepted=true 반환: 오류 재현 |
| tuition 결과 항목 | 실제 BE ResultInput 검증 거절 |

이 시험은 BE의 서비스·수신 API와 음성 워커를 연결한 프로세스 내부 직렬 시험이다. 문의 생성은 테스트용 Service의 레거시 토큰을 사용했으므로 실제 로그인·권한 흐름까지 검증했다고 주장하지 않는다. 실제 서버 간 HTTP, Redis 전달, MySQL 동시성, 새 PC 의존성 설치, AWS 배포 검증도 아니다. 기존 음성 단독 26개 테스트 통과 근거는 앞선 검토에 있음.

## 작업 순서 제안

1. G01 번호 규칙, G03 환경 설정을 합의하고 G02 실행기의 워커 선택을 준비.
2. G05의 명확한 충돌 처리부터 수정해 같은 ID의 다른 본문이 성공으로 표시되지 않도록 검증.
3. G04 실행 위치를 정하고 정상/partial/retry를 실제 개발 MySQL·Redis 및 별도 음성 서버로 왕복 검증.
4. G08 결과 전송 실패/timeout/늦은 결과와 G09 예외 시나리오 검증.
5. G06 수강료 추가는 요구사항 합의 후 공동 계약 변경. DB 설계 변경이 있으면 SQL·데이터 사전·ERD 재생성 및 검토.
6. G10~G12 시험 데이터·측정 변환·공통 명세 보완. 담당·기한은 제안이며 팀 합의로 확정된 것이 아님.

위 분석 당시에는 외부 변경을 하지 않았다. 이후 사용자의 업로드 요청으로 이 문서를 백엔드 PR에 포함한다. 분석에서 발견한 코드 수정은 아직 적용하지 않았다. 노션·AWS는 변경하지 않는다.

## 근거 파일

- 음성: `voice/mock_worker/app.py`, `sender.py`, `samples.py`, `fake_backend.py`, `test_app.py`, `README.md`; `voice/prompts/clawops_agent_role.md`.
- BE 후보: `backend/manage.py`, `settings.py`, `serve6.py`, `run_queue.py`, `http_worker6.py`, `service.py`, `schema.py`, `contracts.py`, `api.py`; `docs/api/worker_openapi.json`, `voice-contract.md`; 루트 `.env.example`.
- 재현 결과: `../verification/backend/voice-mock-check-2026-10-11.json`. 재현 도구는 로컬 검토 자료에 보관했다.
- [음성 목업 원본](https://github.com/academy-calling-team/Academy-calling-agent/tree/7f1f68b32ce2e0ff347b1db4963f8e5d9c3ed0f1/voice/mock_worker).
