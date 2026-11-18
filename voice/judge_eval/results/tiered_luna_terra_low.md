# 계층 판정 luna_terra_low (tiered-v1)

구성: triage: gpt-5.6-luna(low) / review: gpt-5.6-terra / summary: gpt-5.6-luna(low)

| 세트 | 층 | 항목 | 맞음 | 정확도 | 뒤바뀜 | 모르는데 확정 | 답했는데 미확인 |
|---|---|---|---|---|---|---|---|
| real_1013 | 1차 | 48 | 48 | 100% | 0 | 0 | 0 |
| real_1019 | 1차 | 20 | 20 | 100% | 0 | 0 | 0 |
| synthetic | 1차 | 28 | 25 | 89% | 0 | 3 | 0 |
| heldout | 1차 | 25 | 25 | 100% | 0 | 0 | 0 |
| agent | 1차 | 69 | 69 | 100% | 0 | 0 | 0 |
| 전체 | 1차 | 190 | 187 | 98% | 0 | 3 | 0 |
| real_1013 | 최종 | 48 | 48 | 100% | 0 | 0 | 0 |
| real_1019 | 최종 | 20 | 20 | 100% | 0 | 0 | 0 |
| synthetic | 최종 | 28 | 28 | 100% | 0 | 0 | 0 |
| heldout | 최종 | 25 | 25 | 100% | 0 | 0 | 0 |
| agent | 최종 | 69 | 68 | 99% | 0 | 0 | 1 |
| 전체 | 최종 | 190 | 189 | 99% | 0 | 0 | 1 |

2차로 넘어간 항목 37/190 (19%) · 2차가 고침 3 · 2차가 망가뜨림 1
넘긴 이유: 신호 corrected 12, 신호 deferred 10, 신호 partial_week 5, 신호 hedge 5, 신호 off_topic 3, 정정 가능성 2, 신호 conditional 2, 상담 일부 요일만 1

## 비용 (캐시 적중은 처음 호출 값)

| 모델 | 호출 | 입력 토큰 | 출력(추론 포함) | 추론 | 시간(초) |
|---|---|---|---|---|---|
| gpt-5.6-luna | 262 | 178,331 | 21,495 | 4,758 | 565 |
| gpt-5.6-terra | 37 | 31,314 | 4,538 | 1,585 | 19 |

합계 약 $0.179 (사례 131개, 사례당 $0.0014)

## 틀린 항목 (최종)

| 세트 | 통화 | 항목 | 정답 | 1차 | 2차 | 최종 | 넘긴 이유 | 메모 |
|---|---|---|---|---|---|---|---|---|
| agent | G44 | class_time | answered | answered | unknown | unknown ✗ | 신호 hedge | 군말과 머뭇거림 속 구체 답 |

## 2차가 바꾼 항목

| 세트 | 통화 | 항목 | 정답 | 1차 | 2차 | 결과 |
|---|---|---|---|---|---|---|
| synthetic | S02 | consult | unknown | no | unknown | 고침 |
| synthetic | S06 | vacancy | unknown | yes | unknown | 고침 |
| synthetic | S25 | pickup | unknown | yes | unknown | 고침 |
| heldout | H15 | shuttle | unknown | unknown | redirect | 같은 묶음 |
| agent | G44 | class_time | answered | answered | unknown | 망가뜨림 |
