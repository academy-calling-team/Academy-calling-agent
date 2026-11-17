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

## 계층 판정 (11/17, 평가용)

11/12 멘토 의견(프롬프트 하나에 역할 하나, 1차 AI가 대부분 처리하고 2차 AI가 특수 사례 처리)을 따른 구조다. 워커는 아직 단일 프롬프트(`llm_judge.py`)를 쓰고, 이 도구로 구성을 정한 뒤 옮긴다.

| 파일 | 하는 일 |
|---|---|
| `tiered.py` | 1차 분류(근거 인용, 2차로 넘길 신호) → 코드 검사(근거 불일치, 신호, 상담 일부 요일, 정정 가능성) → 2차 특수 사례(넘어온 항목만) → 요약 → 요약 사실 검사. 호출마다 모델·토큰·시간을 기록 |
| `run_tiered.py` | 구성(`--config`)과 추론 설정(`--reasoning`)을 골라 시험 세트를 채점. 1차와 최종을 따로 채점하고 2차 이관·고침·망가뜨림, 모델별 비용을 `results/tiered_<구성>.md`에 냄 |

```
python voice/judge_eval/run_tiered.py --config luna_terra                  # 1차 gpt-5.6-luna → 2차 gpt-5.6-terra
python voice/judge_eval/run_tiered.py --config gemini_terra                # 1차 gemini-3.5-flash-lite → 2차 terra
python voice/judge_eval/run_tiered.py --config luna_terra --reasoning low   # 1차·요약의 추론 설정
python voice/judge_eval/run_tiered.py --config luna_terra --sets real_1013,real_1019 --limit 3
```

190항목 결과 (11/17, 2차는 모두 terra. 뒤바뀜은 모든 구성에서 0):

| 구성 | 1차 | 최종 | 2차 이관 | 2차 고침/망가뜨림 | 비용 |
|---|---|---|---|---|---|
| 단일 gemini (judge-v3, 11/6) | — | 189 | — | — | 무료 키 |
| luna 단일 | 189 | 189 | 0 | — | $0.072 |
| luna → terra (기본 추론) | 189 | 189 | 30 (16%) | 1 / 1 | $0.161 |
| luna(none) → terra | 187 | 188 | 38 | 2 / 1 | $0.173 |
| luna(low) → terra | 187 | 189 | 37 | 3 / 1 | $0.179 |
| gemini → terra | 187 | 190 | 36 | 3 / 0 | $0.205 |
| luna → gemini (2차가 1차보다 가벼움) | 189 | 188 | 30 | 0 / 1 | $0.086 |

- 2차는 1차보다 강한 모델(terra)일 때 고치기만 했고, 가벼운 모델(gemini)일 때 딴 얘기(G16)를 yes로 망가뜨렸다. 결과를 가른 것은 회사 차이보다 2차가 1차보다 강한지로 보인다.
- luna 1차는 '쯤'이 붙은 확정 답(G44)을 짐작 신호로 넘겨 terra가 미확인으로 바꿨다. gemini 1차는 넘기지 않아 맞았다. 구성의 성패는 1차의 신호 성향에도 달려 있다.
- luna 추론을 끄거나 낮춰도 호출당 시간은 비슷했고(약 2초) 1차 정확도는 189 → 187로 떨어졌다.
- 한계: 차이가 1~2항목이고 190항목 중 122개는 Claude가 쓴 문항, 68개는 모든 구성이 다 맞히는 대본 통화다. 구성은 사람 작성 30문항으로 정한다. 그 문항으로 프롬프트를 고치지 않는다.

정답 확인 자료: `results/review56.csv`(사람이 아직 전사와 대조하지 않은 실통화 56항목 대조표), `results/review56_transcripts.md`(18통 전체 전사), `results/regress68_*.csv`(judge-v3.2-context 실통화 68항목 회귀, 68/68).
