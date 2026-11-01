# 질문별 판정 비교 (키워드 vs LLM gemini-3.5-flash-lite)

| 세트 | 방법 | 항목 | 맞음 | 정확도 | 예↔아니오 뒤바뀜 | 모르는데 확정 | 답했는데 미확인 |
|---|---|---|---|---|---|---|---|
| real_1013 | keyword | 48 | 46 | 96% | 0 | 0 | 2 |
| real_1019 | keyword | 20 | 20 | 100% | 0 | 0 | 0 |
| synthetic | keyword | 28 | 20 | 71% | 6 | 1 | 1 |
| heldout | keyword | 25 | 19 | 76% | 2 | 1 | 3 |
| 전체 | keyword | 121 | 105 | 87% | 8 | 2 | 6 |
| real_1013 | llm | 48 | 48 | 100% | 0 | 0 | 0 |
| real_1019 | llm | 20 | 20 | 100% | 0 | 0 | 0 |
| synthetic | llm | 28 | 27 | 96% | 0 | 1 | 0 |
| heldout | llm | 25 | 25 | 100% | 0 | 0 | 0 |
| 전체 | llm | 121 | 120 | 99% | 0 | 1 | 0 |

실제 응답 모델: ['gemini-3.5-flash-lite'] / 프롬프트 판: judge-v2
토큰: 입력 58,703 / 출력 11,357 (캐시된 결과는 처음 호출 때 값)

## 틀린 항목

| 세트 | 통화 | 항목 | 정답 | keyword | llm | 메모 |
|---|---|---|---|---|---|---|
| real_1013 | co_A2 | consult | yes | unknown ✗ | yes |  · LLM: 가능 ['수요일 오후 3시', '금요일 오후 4시'] / 불가 [] |
| real_1013 | va_D | consult | yes | unknown ✗ | yes |  · LLM: 가능 ['화요일 오후 5시'] / 불가 [] |
| synthetic | S02 | consult | unknown | yes ✗ | unknown | 안 되는 시간만 말함 · LLM: 가능 [] / 불가 ['금토일'] |
| synthetic | S03 | consult | no | unknown ✗ | no | '것 같아요' 정중한 거절 · LLM: 가능 [] / 불가 ['이번 주'] |
| synthetic | S05 | shuttle | no | yes ✗ | no | 있지만 중학생은 안 태움 (학생 기준 no) · LLM: 중학생은 통학 차량을 이용할 수 없습니다. |
| synthetic | S06 | vacancy | unknown | unknown | yes ✗ | 추측 (아마) · LLM: 중2 수학반에 한두 자리 정도 여유가 있습니다. |
| synthetic | S09 | pickup | yes | no ✗ | yes | 이중 부정 · LLM: 집 앞까지 픽업 서비스를 제공합니다. |
| synthetic | S10 | level_test | yes | no ✗ | yes | 없지는 않아요 · LLM: 등록 전에 레벨 테스트를 봅니다. |
| synthetic | S11 | pickup | yes | no ✗ | yes | 말버릇 '아니요' · LLM: 수업 후 픽업을 해 드립니다. |
| synthetic | S22 | level_test | no | yes ✗ | no | 되짚기에서 학원이 정정 (예→아니오) · LLM: 작년부터 레벨 테스트를 하지 않습니다. |
| synthetic | S23 | pickup | no | yes ✗ | no | 되묻기 후 대답 · LLM: 수업 후 픽업은 하지 않습니다. |
| heldout | H11 | shuttle | no | unknown ✗ | no | 과거에 없앰 · LLM: 차량은 작년에 처분하여 운행하지 않습니다. |
| heldout | H12 | pickup | no | yes ✗ | no | 부정어 없는 거절 · LLM: 부모님이 직접 데리러 오셔야 합니다. |
| heldout | H14 | level_test | no | unknown ✗ | no | 안 보고 다른 방식 · LLM: 별도의 레벨 테스트는 없고 첫 수업 때 선생님이 봐 주십니다. |
| heldout | H16 | pickup | yes | no ✗ | yes | '없어요'가 들어간 긍정 · LLM: 선생님이 집까지 데려다줍니다 |
| heldout | H19 | consult | unknown | no ✗ | unknown | 안 되는 요일만 말함 · LLM: 가능 [] / 불가 ['월화수'] |
| heldout | H21 | class_time | answered | unknown ✗ | answered | 되짚기 시간 정정 · LLM: 화요일 목요일 여덟 시입니다. |
