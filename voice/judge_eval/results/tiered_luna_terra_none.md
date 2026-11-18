# 계층 판정 luna_terra_none (tiered-v1)

구성: triage: gpt-5.6-luna(none) / review: gpt-5.6-terra / summary: gpt-5.6-luna(none)

| 세트 | 층 | 항목 | 맞음 | 정확도 | 뒤바뀜 | 모르는데 확정 | 답했는데 미확인 |
|---|---|---|---|---|---|---|---|
| real_1013 | 1차 | 48 | 48 | 100% | 0 | 0 | 0 |
| real_1019 | 1차 | 20 | 20 | 100% | 0 | 0 | 0 |
| synthetic | 1차 | 28 | 26 | 93% | 0 | 2 | 0 |
| heldout | 1차 | 25 | 25 | 100% | 0 | 0 | 0 |
| agent | 1차 | 69 | 68 | 99% | 0 | 1 | 0 |
| 전체 | 1차 | 190 | 187 | 98% | 0 | 3 | 0 |
| real_1013 | 최종 | 48 | 48 | 100% | 0 | 0 | 0 |
| real_1019 | 최종 | 20 | 20 | 100% | 0 | 0 | 0 |
| synthetic | 최종 | 28 | 28 | 100% | 0 | 0 | 0 |
| heldout | 최종 | 25 | 25 | 100% | 0 | 0 | 0 |
| agent | 최종 | 69 | 67 | 97% | 0 | 1 | 1 |
| 전체 | 최종 | 190 | 188 | 99% | 0 | 1 | 1 |

2차로 넘어간 항목 38/190 (20%) · 2차가 고침 2 · 2차가 망가뜨림 1
넘긴 이유: 신호 deferred 13, 신호 corrected 12, 신호 partial_week 5, 정정 가능성 3, 신호 hedge 3, 상담 일부 요일만 2, 신호 off_topic 2, 신호 conditional 2, 근거 불일치 1

## 비용 (캐시 적중은 처음 호출 값)

| 모델 | 호출 | 입력 토큰 | 출력(추론 포함) | 추론 | 시간(초) |
|---|---|---|---|---|---|
| gpt-5.6-luna | 262 | 178,436 | 16,261 | 0 | 526 |
| gpt-5.6-terra | 38 | 32,753 | 4,382 | 1,301 | 28 |

합계 약 $0.173 (사례 131개, 사례당 $0.0013)

## 틀린 항목 (최종)

| 세트 | 통화 | 항목 | 정답 | 1차 | 2차 | 최종 | 넘긴 이유 | 메모 |
|---|---|---|---|---|---|---|---|---|
| agent | G30 | vacancy | refused | no |  | no ✗ |  | 정원 현황 비공개 |
| agent | G44 | class_time | answered | answered | unknown | unknown ✗ | 신호 hedge | 군말과 머뭇거림 속 구체 답 |

## 2차가 바꾼 항목

| 세트 | 통화 | 항목 | 정답 | 1차 | 2차 | 결과 |
|---|---|---|---|---|---|---|
| synthetic | S06 | vacancy | unknown | yes | unknown | 고침 |
| synthetic | S25 | pickup | unknown | yes | unknown | 고침 |
| heldout | H15 | shuttle | unknown | unknown | redirect | 같은 묶음 |
| agent | G44 | class_time | answered | answered | unknown | 망가뜨림 |
