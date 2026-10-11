# 백엔드 API 검토본

저장소 반입 후보 0.4.0. 팀 공동 계약 확정 전이며 실제 서비스 배포 명세가 아니다.

| 파일 | 내용 |
|---|---|
| openapi.json | 인증·문의·내부 통화 결과·운영 API |
| worker_openapi.json | 가상 워커 0.2.0 접수/조회 계약 |
| result_json_schema.json | 내부 결과 ResultInput 전체 필드 |
| examples.json | 합성 요청·결과 예제 |
| frontend-guide.md | 프론트 화면에 연결할 API와 표시 규칙 |
| voice-contract.md | 음성 워커 접수/조회·ID·결과 정규화·미완료 사항 |

프론트는 Bearer 세션과 문의 등록의 Idempotency-Key를 사용한다.
워커는 X-Internal-Key를 사용한다. 제공자 비밀키와 내부키를 프론트로 전달하지 않는다.
inquiry_id / question_id / call_id / result_id는 서로 다른 대상을 구분한다.
미확인은 null과 reason으로 전달하며 false(아니오)와 구분한다.
음성 제공자 응답은 음성 워커에서 공통 계약으로 변환한다.
