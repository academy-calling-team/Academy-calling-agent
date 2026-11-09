# 질문별 판정 비교 (키워드 사전 vs LLM)

10/28 9주차 회의에서 멘토님이 키워드 사전 판정(`voice/call_worker/extract.py`)에 반대해, LLM으로 바꾸기 전에 같은 시험 세트로 두 방식을 비교한다. 워커 코드는 바꾸지 않는다.

| 파일 | 하는 일 |
|---|---|
| `../call_worker/llm_judge.py` | 전사 + 질문 목록 → LLM 구조화 출력(JSON 스키마). 근거 학원 발화를 인용하게 하고, 인용이 실제 발화에 없으면 미확인으로 돌림 |
| `cases_synthetic.json` | 키워드 사전이 어려워하는 말투 26개(완곡 부정, 이중 부정, 말버릇 '아니요', 정정, 되묻기, 조건부, 학생 기준 불가 등) |
| `run_eval.py` | 10/13 실통화 16통 + 10/19 실통화 2통 + 합성 26개로 두 방식을 채점, `results/`에 표와 항목별 CSV |

```
python voice/judge_eval/run_eval.py              # 키워드만, API 호출 없음
python voice/judge_eval/run_eval.py --llm        # voice/.env의 GEMINI_API_KEY 필요(기본 모델 gemini-3.5-flash), 응답은 .cache/에 저장
python voice/judge_eval/run_eval.py --llm --model gemini-3.5-flash-lite
```

프롬프트 판 judge-v3(11/4 10주차 회의 반영): 애매한 말투마다 규칙을 늘리지 않고, 답의 내용(status)과 학원이 얼마나 확실하게 말했는지(certainty: definite·guess·deferred)를 따로 받는다. 확정이 아닌 yes/no/answered는 코드(`settle`)가 미확인으로 돌리고 기운 쪽은 `leaning`에 남긴다. 학원 원문(`source_text`)은 근거 발화 번호로 코드가 전사에서 꺼내고, 요약의 숫자·요일이 원문에 없으면 요약 대신 인용 원문을 쓴다(`facts_ok`).

채점: 정답과 같으면 맞음(미확인·거절은 같은 묶음). 틀림은 셋으로 나눈다. 예↔아니오 뒤바뀜(가장 해로움), 모르는데 확정 답, 답했는데 미확인.

주의: 합성 사례는 키워드 방식의 약점을 겨냥해 만들었으므로 합성 세트 정확도만으로 일반 성능을 말할 수 없다. 실통화 세트와 함께 본다. 10/13 전사는 Whisper 받아쓰기라 오류가 있다(실제 워커는 ClawOps 전사).
