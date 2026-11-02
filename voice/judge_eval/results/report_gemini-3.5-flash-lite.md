# 질문별 판정 비교 (키워드 vs LLM gemini-3.5-flash-lite)

| 세트 | 방법 | 항목 | 맞음 | 정확도 | 예↔아니오 뒤바뀜 | 모르는데 확정 | 답했는데 미확인 |
|---|---|---|---|---|---|---|---|
| real_1013 | keyword | 48 | 46 | 96% | 0 | 0 | 2 |
| real_1019 | keyword | 8 | 8 | 100% | 0 | 0 | 0 |
| synthetic | keyword | 28 | 20 | 71% | 6 | 1 | 1 |
| 전체 | keyword | 84 | 74 | 88% | 6 | 1 | 3 |
| real_1013 | llm | 48 | 47 | 98% | 0 | 0 | 1 |
| real_1019 | llm | 8 | 8 | 100% | 0 | 0 | 0 |
| synthetic | llm | 28 | 24 | 86% | 1 | 2 | 1 |
| 전체 | llm | 84 | 79 | 94% | 1 | 2 | 2 |

실제 응답 모델: ['gemini-3.5-flash-lite'] / 프롬프트 판: judge-v1
토큰: 입력 40,568 / 출력 7,959 (캐시된 결과는 처음 호출 때 값)

## 틀린 항목

| 세트 | 통화 | 항목 | 정답 | keyword | llm | 메모 |
|---|---|---|---|---|---|---|
| real_1013 | co_A2 | consult | yes | unknown ✗ | yes |  · LLM: 가능 ['수요일 오후 3시', '금요일 오후 4시'] / 불가 [] |
| real_1013 | co_E | class_time | answered | answered | unknown ✗ |  · LLM: 근거 확인 실패: 　いじよんえ じ え じ ええ |
| real_1013 | va_D | consult | yes | unknown ✗ | yes |  · LLM: 가능 ['화요일 오후 5시'] / 불가 [] |
| synthetic | S02 | consult | unknown | yes ✗ | no ✗ | 안 되는 시간만 말함 · LLM: 가능 [] / 불가 ['금토일'] |
| synthetic | S03 | consult | no | unknown ✗ | no | '것 같아요' 정중한 거절 · LLM: 가능 [] / 불가 ['이번 주'] |
| synthetic | S05 | shuttle | no | yes ✗ | no | 있지만 중학생은 안 태움 (학생 기준 no) · LLM: 중학생은 통학 차량을 이용할 수 없습니다. |
| synthetic | S08 | level_fit | yes | yes | no ✗ | 반은 있지만 꽉 참 (level_fit은 yes) · LLM: 중2 중급반은 있지만 마감되었습니다. |
| synthetic | S09 | pickup | yes | no ✗ | yes | 이중 부정 · LLM: 집 앞까지 픽업을 해 드립니다. |
| synthetic | S10 | level_test | yes | no ✗ | answered ✗ | 없지는 않아요 · LLM: 등록 전에 레벨 테스트를 봅니다. |
| synthetic | S11 | pickup | yes | no ✗ | yes | 말버릇 '아니요' · LLM: 수업 후 픽업을 해 드리고 있습니다 |
| synthetic | S22 | level_test | no | yes ✗ | no | 되짚기에서 학원이 정정 (예→아니오) · LLM: 레벨 테스트는 없고 바로 반 배정합니다. |
| synthetic | S23 | pickup | no | yes ✗ | unknown ✗ | 되묻기 후 대답 · LLM: 근거 확인 실패: ㅃㅈ 미사스니다 |
