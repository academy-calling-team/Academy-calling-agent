# 응답 지연 측정 도구 (한 번에 돌리기, 파형 뷰어)

- 날짜: 2026-10-14
- 작성자: 김규림
- 사용한 도구: Claude (Claude Code)
- 목적: 10/13 측정에 쓴 분석 과정을 다시 쓸 수 있게 묶고, 사람이 파형을 보고 들으며 지연을 확인할 수 있는 뷰어 만들기

## 프롬프트

```
너가 지금까지 사용한 음성 분석 툴 만들어줄 수 있어?
```

```
가능하면 시각적으로 볼 수 있는 프로그램이 좋을거같아. 파일 넣으면 파형이 보이고 색으로 화자가 보이는 정도. 그렇게 해서 인간이 들으면서 보는걸로 지연을 잴 수 있도록
```

```
올려줘
```

## 결과를 어떻게 썼는지

- `experiments/latency/scripts/measure.py`: Claude가 기존 스크립트(to16k, turns, one_call, relabel, gaps, report_1013, dropouts)를 통화 목록 CSV 하나로 돌리도록 묶었다. 녹음 받기는 ClawOps API로, Vapi 통화의 ClawOps 쪽 통화는 시각으로 찾는다. `data/calls_1013.csv`로 fix·report를 돌려 저장된 결과와 같은 값이 나오는 것, analyze로 통화 하나를 처음부터 돌려도 결과 JSON이 같은 것을 확인했다.
- `experiments/latency/data/calls_1013.csv`: 10/13 측정 16통의 callId, ClawOps 쪽 통화 ID, 지연 통계 포함 여부, 직접 정한 화자 구간을 적었다.
- `experiments/latency/viewer/latency_viewer.html`: Claude가 만든 브라우저용 뷰어. 녹음과 `*_rows.json`을 넣으면 화자 색 파형, 응답 간격, 재생, 표시선으로 직접 재기, 요약, CSV 복사를 한다. WAV 읽기는 실제 녹음 3개로 시험했다(길이 칸이 0인 ClawOps WAV 포함). 같은 내용을 claude.ai Artifact로도 올렸다.
