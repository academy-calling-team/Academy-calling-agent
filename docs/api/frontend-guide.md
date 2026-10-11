# 프론트 구현 기준과 API 예제

작성 2026-10-05 · 백엔드 선행 준비 · 프론트 담당 딩옌에게 전달할 검토용 명세. **실행 가능한 프론트 앱을 만들지 않았으며, 참고 화면은 가상 내용을 표시하는 정적 시안이다.** 실제 팀 전달 메시지는 보내지 않았다.

## 전달물과 역할 표기

진행 보고 문구: “백엔드에서 프론트 구현 기준·API 예제·입력/결과/추가 확인 참고 화면을 선행 준비했다. 프론트 담당의 화면 구현과 팀 API 연동은 후속 작업이다.”

시안은 배치·문구·표시 기준을 설명한다. 디자인 확정·사용자 사용성 시험·브라우저 반응형 구현 완료 근거는 아니다. 로그인 기능은 API 기준을 제공하며 별도 실행 화면을 만들지 않았다.

| 참고 화면 | 표현하는 상황 |
|---|---|
| [문의 입력 PNG](../frontend-reference/01_문의입력_참고.png) | 선택형 학생 조건·학원·질문 1~6개 |
| [결과 조회 PNG](../frontend-reference/02_결과조회_참고.png) | 부정 답변·미확인·수업 시간 텍스트·상담 가능 시간 |
| [추가 확인 PNG](../frontend-reference/03_추가확인_참고.png) | 재통화 시간 미정, 실패 후 안내 검토 대기 |

같은 이름의 SVG는 편집용이다. 상세 계약 원본은 [OpenAPI](openapi.json). [예제 모음](examples.json)은 실제 로컬 HTTP 왕복의 가상 응답과 시간 미정 테스트 예시를 담는다. 테스트 예시는 합성이라고 표시한다.

## 화면 흐름과 입력값

1. 가입/로그인 → `/auth/me`로 본인 inquirer_id 확인. 요청 본문에 임의 사용자 ID를 넣지 않는다.
2. `/api/options`, `/api/academies` 조회 후 선택형 입력. 현재 학원/지역은 개발용 자료다. 지역으로 학원 목록을 좁히는 UI는 프론트 제안이며 서버가 학원-학생 지역 일치를 강제한다고 가정하지 않는다.
3. 질문 1~6개를 중복 없이 선택, 문의 접수 → 돌아온 inquiry_id로 상세 조회.
4. 문의 목록·결과·확인 대기 표시. 관리자 검토 화면은 학부모 조회 화면과 별개다.

| 항목 | 전송값 / 표시 예 |
|---|---|
| 학년 | E1~E6 초1~초6 / M1~M3 중1~중3 / H1~H3 고1~고3 |
| 과목 | KOR 국어 / ENG 영어 / MATH 수학 / SCI 과학 / SOC 사회 |
| 수준 | HIGH 높음 / MID 중간 / LOW 낮음 |
| 지역 | `/api/options.regions`에 있는 문자열 그대로 |
| 질문 | shuttle 통학 차량 / pickup 픽업 / level_fit 수준에 맞는 반 / vacancy 남은 자리 / level_test 레벨 테스트 / class_time 수업 요일·시간 |

상담 수락·가능 시간 확인은 고정 확인 항목이며 사용자가 질문 코드로 추가하지 않는다. 구체 코드는 기존 음성팀/노션 초안을 구현한 것으로 팀 최종 확정은 남아 있다.

## 계정과 API 호출

| 경로 | 동작 | 인증 |
|---|---|---|
| POST /auth/register | 개발 계정 생성, 201, inquirer_id 반환 | 없음 |
| POST /auth/login | access_token·expires_at·inquirer_id | 없음 |
| GET /auth/me | 본인 ID·로그인명·역할·만료 시각 | Bearer |
| POST /auth/logout | 현재 세션 폐기 | Bearer |
| GET /api/options, /api/academies | 선택값·학원 목록 | 없음 |
| POST /api/inquiries | 문의 생성/동일 요청 재응답, 201 | Bearer + Idempotency-Key |
| GET /api/inquiries?limit=50&offset=0 | 본인 목록, 배열 | Bearer |
| GET /api/inquiries/{inquiry_id} | 본인 상세, 아래 결과 규칙 | Bearer |

로그인명 3~32자 소문자 영문 시작, 소문자/숫자/밑줄만 가능. 비밀번호 12~128자. 세션 기본 3600초; 5번 실패 후 300초 잠금은 개발 정책이다. 영구 개발 토큰은 6주차 서버에서 거부한다. 실제 학부모 신원 증명·비밀번호 재설정·refresh API는 제공하지 않는다.

`Authorization: Bearer <로그인 응답의 access_token>`을 사용한다. 실제 비밀번호/토큰/내부키를 예제·노션·화면·오류 로그에 붙이지 않는다. 프론트 세션 저장 방식은 팀 검토가 필요하며 현재 전달 예제는 메모리 세션 기준이다.

문의 생성 예시(자리표시는 실제 반환 ID로 바꾼다):

```http
POST /api/inquiries
Authorization: Bearer <access_token>
Content-Type: application/json
Idempotency-Key: <이 제출 건의 UUID>
```

```json
{
  "inquirer_id": "<auth/me의 inquirer_id>",
  "academy_id": "<api/academies에서 선택한 academy_id>",
  "student": {"grade":"M2","subject":"MATH","level":"MID","region":"대구 북구 침산동"},
  "question_codes": ["shuttle","vacancy","class_time"]
}
```

응답은 `{ "inquiry_id":"…", "status":"queued", "duplicate":false }`. 네트워크 응답 유실 재전송은 **같은 키 + 같은 본문**을 유지한다. 내용이 바뀌거나 새 문의일 때 새 키를 만든다. 동일 키·다른 본문은 409. 버튼 연타만 막아서는 응답 유실 중복을 해결하지 못한다.

## 상태 표시

| 서버 status | 권장 표시 | 해석 |
|---|---|---|
| queued | 접수 대기 | 운영시간/대기열에 따라 처리, 실제 발신 전 |
| calling | 문의 진행 중 | 전달·연결·결과 대기 포함. 사람이 전화받았다는 뜻으로 표시하지 않음 |
| retry_wait | 다시 연결 대기 | 재시도 또는 시간 확인 보류 |
| completed | 처리 완료 | 답변 수집/처리 종료, 상담 예약 확정과 구분 |
| failed | 처리 실패 | 실패 사유별 안내, 무조건 “학원 부재중”으로 단정하지 않음 |

`review_required=true` + `review_reason=callback_time_unknown`이면 우선 **“재통화 시간 확인 필요”**. `result.callback_requested=true`·`callback_at=null`은 요청은 있으나 시간 미정이라는 뜻이다. 임의 재시도 시간/예약 시간을 만들지 않는다. 기존 답변은 보여준다. 관리자가 schedule 또는 cancel 검토 후 상태를 갱신한다.

상세 응답에 예정 재시도 시각(next_at)은 공개되지 않는다. 임의 카운트다운을 만들지 않는다. `result=null`은 결과 수신 전이고 빈 답변 배열과 구분한다. 목록 응답에는 검토 플래그가 없으므로 상세 상태 배지를 그릴 때 상세 조회가 필요하다.

## 질문별 결과 규칙

`questions`의 질문 순서와 question_id를 기준으로 `result.answers`를 연결한다. 코드/ID가 맞지 않거나 값이 누락된 경우 긍정/부정으로 추정하지 않는다.

| 값 | 표시 |
|---|---|
| answered=true, yes_no=true | 예 / 가능 |
| answered=true, yes_no=false | 아니오 / 불가. **정상적으로 얻은 부정 답변** |
| answered=false, yes_no=null, reason=unknown | 추가 확인 필요 |
| answered=false, reason=refused | 답변을 받지 못함(응답 거절) |
| asked=false, reason=not_asked | 질문하지 못함 |
| class_time, answered=true, yes_no=null | detail의 요일·시간 텍스트 표시 |

`unresolved`는 미확인 question_id 목록이다. summary_text만 보여주고 미확인 질문을 숨기지 않는다. consult_accepted=true는 상담 수락, false는 상담 불가/미수락, null은 확인 안 됨. available_times는 답변한 가능 시간이며 예약 확정으로 승격하지 않는다. review_revision>0이면 “검토 후 수정된 결과” 배지를 제안한다.

공개 API는 원문 전사·녹음 URL·내부 결과 ID를 반환하지 않는다. 프론트가 내부 API를 호출해 보완하는 방식은 사용하지 않는다.

## 실패 후 안내와 오류

| fallback_status | 권장 표시 |
|---|---|
| null | 후속 안내 상태 없음 |
| needs_review | 담당자 검토 대기 |
| prepared | 안내 문안 준비됨 |
| dismissed | 후속 안내 제외 |
| dry_run_complete | 발송 모의 확인 완료(실제 발송 아님) |

현재 실제 sent 상태/API가 없다. dry_run_complete를 “문자 발송됨”으로 표시하지 않는다. 관리자 운영 API에는 시간 지정/취소·문안 준비/제외·dry-run·결과 교정이 있지만 사용자 화면에는 관리자 버튼을 노출하지 않는다.

| 오류 | 프론트 동작 제안 |
|---|---|
| 401 | 조회 반복 중지, 로그인 안내, 작성 중 입력은 보존 |
| 403 | 권한 없는 동작 안내; 다른 사용자 ID 전송 여부 점검 |
| 404 | 조회할 수 없는 문의/학원 안내. 타인 문의도 404 |
| 409 | 요청 키 충돌/검토 버전 충돌 안내, 무작정 재전송하지 않음 |
| 422 | detail의 loc/msg/type으로 입력 오류 표시. 응답은 입력 원문을 되비추지 않음 |
| 429 | 로그인 잠금 안내, 자동 로그인 반복 중지 |
| 네트워크/503 | 입력 유지·재시도 안내; 문의 POST는 동일 키/본문 재사용 |

폴링은 초기 2~3초, 반복 오류 시 간격 증가를 제안한다. 완료/실패 후 자동 폴링 중지, 확인 보류에는 수동 새로고침 제공. 시간 미정 검토의 화면 문구·간격은 팀 협의 대상이다. ISO 8601 시간은 Asia/Seoul로 표시하고 null을 현재 시각으로 변환하지 않는다.

## 프론트 담당이 확인할 인수 기준

- [ ] 서버 선택값과 실제 입력값 일치, 질문 중복/0개 제출 방지.
- [ ] 같은 요청 연타·응답 유실에도 한 inquiry_id, 내용 수정은 새 키.
- [ ] 본인 조회만 가능하고 세션 만료/로그아웃 시 401 처리.
- [ ] 아니오·미확인·수업 시간 텍스트·result=null·교정 버전 표시 구분.
- [ ] 재통화 시간 미정은 보류 안내, 상담 수락/완료를 예약 확정으로 표시하지 않음.
- [ ] dry-run을 실제 문자 발송으로 표시하지 않음.
- [ ] 딩옌 화면에서 백엔드 왕복을 실제 수행하고 화면/응답 증거 기록.

위 인수 기준은 전달용이며 실행 프론트 검증으로 체크하지 않았다.
