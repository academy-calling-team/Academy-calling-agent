# 질문별 판정 비교 (키워드만)

| 세트 | 방법 | 항목 | 맞음 | 정확도 | 예↔아니오 뒤바뀜 | 모르는데 확정 | 답했는데 미확인 |
|---|---|---|---|---|---|---|---|
| real_1013 | keyword | 48 | 46 | 96% | 0 | 0 | 2 |
| real_1019 | keyword | 8 | 8 | 100% | 0 | 0 | 0 |
| synthetic | keyword | 28 | 20 | 71% | 6 | 1 | 1 |
| 전체 | keyword | 84 | 74 | 88% | 6 | 1 | 3 |

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
