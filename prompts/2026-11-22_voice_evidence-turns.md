# 결과에 근거 발화(evidence_turns) 보내기 (11/22)

- 날짜: 2026-11-22
- 작성자: 김규림
- 사용한 도구: Claude (Claude Code)
- 목적: 백엔드 계약(PR #58·#61)에 있는 선택 필드 `transcript[].turn_no`, `answers[].evidence_turns`, `consult`를 음성 워커가 채워, 프론트가 판정 근거가 된 발화를 보여 줄 수 있게 한다.

## 프롬프트

```
근거 발화 보내기 작업부터 해줘
```

## 결과를 어떻게 썼는지

- Claude가 백엔드 계약(`backend/contracts.py`)과 저장·조회 코드(`backend/service.py`의 `attach_evidence_dialogue`)를 읽고, 워커가 전사에 번호를 붙이지 않아 근거를 못 보내던 것을 확인했다.
- 변경
  - `llm_judge.evidence_turns()`: 근거 발화 번호를 고른다. 학원 원문(`source_text`)과 같은 발화이고, 학원이 확인만 했으면 앞의 AI 되짚기를 넣는다. 최대 10개(계약 한도)
  - 단일 판정과 계층 판정 모두 답변 행과 상담 결과에 `evidence_turns`를 넣는다. 묻지 않은 질문에는 넣지 않는다(계약 검사)
  - `real_call.number_transcript()`: 전사에 `turn_no`를 붙이고, 보내는 전사(최대 1000발화) 밖을 가리키는 번호는 지운다
  - `real_call.consult_explanation()`: 상담 설명(`consult`)을 만든다. 확정이 안 됐으면 사유, 학원 원문, 근거 발화. 묻지 않은 상담에는 사유만 넣는다
- 확인: 새 시험 5개 포함 워커·목업 시험 103개 통과. 결과는 `ResultInput` 계약 검사를 통과하고, 백엔드의 `attach_evidence_dialogue` 함수 소스를 그대로 실행해 답변과 상담에 근거 발화가 붙는 것을 확인했다(로컬에 백엔드 실행 환경이 없어 함수만 꺼내 실행).
- 목업 워커는 전사를 빈 목록으로 보내 근거 발화가 없다. 프론트가 목업 모드로 표시를 만들려면 목업 시나리오에 전사와 근거를 넣는 작업이 따로 필요하다.
