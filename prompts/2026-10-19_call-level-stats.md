# 응답 지연의 통화 단위 분석 추가 (논문 7판)

- 날짜: 2026-10-19
- 작성자: 강유준
- 사용한 도구: Claude (Claude Code)
- 목적: 논문 심사 관점 검토에서 "같은 통화의 응답 93개를 독립으로 보고 p<0.001을 냈다"는 지적이 나와, 통화를 단위로 한 비교를 계산하고 재현할 수 있게 한다.

## 프롬프트

```
Read this section as a hostile reviewer for 한국정보기술학회.
List the five weakest points in order of severity, quote the exact sentence each weakness lives in, and say what evidence or rewording would fix it.
```

```
다섯가지 반영한 7판 만들고 이후 다음 프롬프트 실행해줘.
```

## 결과를 어떻게 썼는지

- `experiments/latency/scripts/human_stats.py`: 10/14에 docs/meeting-1014 브랜치에만 올라가 있던 스크립트와 그림(32eed2e)을 가져오고, 통화 단위 비교를 더했다. 통화별 중앙값에 Mann-Whitney 검정을, 통화를 복원 추출하는 부트스트랩(20,000번, 시드 0)으로 중앙값 차이의 95% 구간을 구한다.
- 결과: 통화별 중앙값 ClawOps 1.42~1.89초, Vapi 1.27~1.58초, Mann-Whitney p=0.038, 부트스트랩 구간 -0.01~0.35초(0 포함). 논문 7판과 `docs/음성_엔진_비교_측정.md`에 반영했다.
- 기존 응답 단위 값(p=0.00028, 구간 0.02~0.29초)도 스크립트에 그대로 남겨 비교할 수 있게 했다.
