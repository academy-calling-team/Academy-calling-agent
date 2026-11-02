# 질문별 판정 비교 (키워드만)

| 세트 | 방법 | 항목 | 맞음 | 정확도 | 예↔아니오 뒤바뀜 | 모르는데 확정 | 답했는데 미확인 |
|---|---|---|---|---|---|---|---|
| real_1013 | keyword | 48 | 46 | 96% | 0 | 0 | 2 |
| real_1019 | keyword | 20 | 20 | 100% | 0 | 0 | 0 |
| synthetic | keyword | 28 | 20 | 71% | 6 | 1 | 1 |
| heldout | keyword | 25 | 19 | 76% | 2 | 1 | 3 |
| agent | keyword | 69 | 52 | 75% | 4 | 9 | 4 |
| 전체 | keyword | 190 | 157 | 83% | 12 | 11 | 10 |

## 틀린 항목

| 세트 | 통화 | 항목 | 정답 | keyword | 메모 |
|---|---|---|---|---|---|
| real_1013 | co_A2 | consult | yes | unknown ✗ |  |
| real_1013 | va_D | consult | yes | unknown ✗ |  |
| synthetic | S02 | consult | unknown | yes ✗ | 안 되는 시간만 말함 |
| synthetic | S03 | consult | no | unknown ✗ | '것 같아요' 정중한 거절 |
| synthetic | S05 | shuttle | no | yes ✗ | 있지만 중학생은 안 태움 (학생 기준 no) |
| synthetic | S09 | pickup | yes | no ✗ | 이중 부정 |
| synthetic | S10 | level_test | yes | no ✗ | 없지는 않아요 |
| synthetic | S11 | pickup | yes | no ✗ | 말버릇 '아니요' |
| synthetic | S22 | level_test | no | yes ✗ | 되짚기에서 학원이 정정 (예→아니오) |
| synthetic | S23 | pickup | no | yes ✗ | 되묻기 후 대답 |
| heldout | H11 | shuttle | no | unknown ✗ | 과거에 없앰 |
| heldout | H12 | pickup | no | yes ✗ | 부정어 없는 거절 |
| heldout | H14 | level_test | no | unknown ✗ | 안 보고 다른 방식 |
| heldout | H16 | pickup | yes | no ✗ | '없어요'가 들어간 긍정 |
| heldout | H19 | consult | unknown | no ✗ | 안 되는 요일만 말함 |
| heldout | H21 | class_time | answered | unknown ✗ | 되짚기 시간 정정 |
| agent | G08 | shuttle | no | yes ✗ | 처음 있다고 했다가 정정해서 없음 |
| agent | G16 | pickup | unknown | yes ✗ | 질문과 관계없는 대답 |
| agent | G18 | level_fit | no | not_asked ✗ | 중급반만 없음 |
| agent | G20 | level_fit | yes | not_asked ✗ | 구어체로 긍정 |
| agent | G21 | level_fit | no | not_asked ✗ | 초등 전문이라 중등 안 받음 |
| agent | G30 | vacancy | refused | no ✗ | 정원 현황 비공개 |
| agent | G31 | vacancy | unknown | yes ✗ | 반 개편 이후에야 알 수 있음 |
| agent | G37 | level_test | no | yes ✗ | 예전엔 있었으나 지금은 없음 |
| agent | G38 | level_test | refused | no ✗ | 테스트 안내 거절 |
| agent | G43 | class_time | refused | answered ✗ | 시간표 안내 거절 |
| agent | G45 | class_time | unknown | answered ✗ | 정해진 게 없음 |
| agent | G51 | consult | refused | no ✗ | 상담 가능 여부 안내 거절 |
| agent | G54 | consult | unknown | yes ✗ | 되묻기만 하고 답 없음 |
| agent | G55 | consult | yes | no ✗ | 부정형 질문에 가능하다고 답 |
| agent | G58 | level_fit | yes | not_asked ✗ | 반 있음과 시간 동시 답 |
| agent | G60 | level_fit | unknown | no ✗ | 반은 테스트 후 결정이라 모름, 테스트는 있음 |
| agent | G60 | level_test | yes | no ✗ | 반은 테스트 후 결정이라 모름, 테스트는 있음 |
