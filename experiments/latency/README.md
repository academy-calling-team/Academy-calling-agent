# 응답 지연 측정

통화 녹음으로 AI 응답 지연(학원 담당자 말이 끝난 뒤 AI 첫 소리까지)을 잰다. 목표는 1.5초 이내다. 10/7 체험 통화 5건의 결과가 `data/results/`에 있다.

## 측정 결과 (10/7 체험 통화)

| 통화 | 응답 수 | 평균 (초) | 중앙값 (초) | 최대 (초) | 1.5초 넘음 |
|---|---|---|---|---|---|
| ClawOps 070 · gpt-realtime-2.1 통화 1 | 7 | 1.91 | 1.76 | 2.65 | 7 |
| ClawOps 070 · gpt-realtime-2.1 통화 2 | 11 | 2.13 | 2.14 | 2.73 | 11 |
| ClawOps 070 · gpt-realtime-2.1 합계 | 18 | 2.05 | 2.03 | 2.73 | 18 |
| ClawOps 070 · live·luna·낮음 | 8 | 1.92 | 1.56 | 4.16 | 5 |
| Vapi 웹 · 추론 High (참고) | 6 | 1.70 | 1.68 | 2.15 | 3 |
| Vapi 웹 · 추론 Low (참고) | 2 | 2.14 | 2.14 | 2.21 | 2 |

- ClawOps 값은 서버 녹음이라 휴대폰망 구간이 빠져 있다. 실제로 기다리는 시간은 더 길다.
- Vapi는 웹 통화를 휴대폰으로 녹음했고 대본도 달라 참고값이다.
- 통화 중 관찰한 문제는 `voice/prompts/test_cases.md`에 있다.

## 측정 결과 (10/13 같은 설정 비교)

두 엔진 모두 GPT-Live(gpt-live-1, 업무 처리 모델 gpt-5.6-luna, 추론 강도 none, 음성 marin), 프롬프트 v3, 같은 대본으로 휴대폰에 발신했다. 두 엔진 모두 ClawOps 서버 녹음(같은 지점)으로 쟀다. Vapi 통화는 ClawOps 070 → SIP → Vapi(미국)로 이어진다. 대본과 정답지는 `voice/prompts/test_script_v3.md`, 결과 JSON은 `data/results/1013_co_*`(ClawOps), `1013_va_*`(Vapi)다.

| 엔진 (대본 A~E) | 응답 수 | 평균 (초) | 중앙값 (초) | p95 (초) | 최대 (초) | 1.5초 넘음 |
|---|---|---|---|---|---|---|
| ClawOps 070 · GPT-Live | 35 | 1.66 | 1.61 | 1.99 | 2.15 | 29 (83%) |
| Vapi (ClawOps SIP) · GPT-Live | 36 | 1.52 | 1.48 | 1.99 | 2.13 | 17 (47%) |

| 항목 | ClawOps | Vapi |
|---|---|---|
| 정답지 대비 정확도 (요약 기준) | 18/18 | 17/17 (A의 ③은 사람이 대본과 다르게 말해 제외) |
| 첫인사의 AI·녹음 고지 | 6/6 | 6/6 |
| 말 중간 쉼(H)에 끼어듦 | 없음 (1.5~7.3초 쉼 4번) | 없음 (0.9~5.7초 쉼 4번) |
| 끼어들었을 때 AI가 더 말한 시간 (H) | 1.3초, 0.8초 | 1.2초 |
| 되짚기 뒤 답을 기다리지 않음 | B에서 2번 | B에서 3번 |
| 말하는 도중 120~300ms 완전 무음 (패킷 빠짐 의심) | 0번 / AI 말 4.7분 | 10번 / AI 말 4.8분 |

- **화자 판정.** 녹음이 두 목소리가 섞인 모노라 `one_call.py`의 목소리 군집만으로는 D·E 등에서 사람과 AI가 갈리지 않았다. 대본의 사람 대사와 AI 말투로 다시 판정하고, 애매한 구간 몇 개는 전사를 보고 직접 정했다(`*_rows.json`의 `who_emb`가 처음 판정, `why`가 근거).
- **H는 지연 통계에서 뺐다.** 일부러 쉬고 끼어든 통화라 따로 본다. 끼어든 시간은 화자 분리 결과로 잰 근삿값이다.
- **목소리.** 통화마다 목소리가 달라진다는 느낌이 있었지만, 화자 임베딩(ERes2Net)으로 비교하면 AI 목소리는 통화끼리 유사도 평균 0.92(0.86~0.97)로, 같은 사람(김규림) 목소리의 통화 간 유사도 0.75보다 높다. 목소리 자체보다 말투·억양이 달라진 것으로 보인다.
- **발음.** 두 엔진 모두 좋지 않다는 평가였다. 같은 GPT-Live 모델의 특성으로 보인다.

## 측정 방법

- 응답 지연 = AI 첫 소리 시작 − 사람 말 끝. 사람 → AI로 바뀌는 지점마다 잰다.
- silero VAD로 음성 구간을 찾고, 에너지로 경계를 10ms 단위로 맞춘다. ClawOps 녹음은 말 사이가 디지털 0이라 경계가 뚜렷하다.
- 화자는 ERes2Net 임베딩으로 가르고, Whisper turbo 전사로 확인한다.
- 간격이 0초 이하인 겹침(맞장구 '네', 끼어들기)은 응답에서 빼고 따로 출력한다. p95는 nearest-rank다.

## 준비

1. Python 3.10 이상과 ffmpeg(새 녹음을 변환할 때만)를 준비한다.
2. `pip install -r requirements.txt`
3. `python scripts/download_models.py`로 모델을 받는다. 약 610MB를 받아 1.1GB로 풀고, 10/7 측정에 쓴 파일과 SHA-256으로 대조한다. 기본 위치는 `models/`(커밋하지 않음)이고, 다른 곳에 두려면 환경 변수 `MODELS_DIR`을 지정한다.
4. 녹음을 `data/recordings/`에 넣는다. 녹음은 저장소에 올리지 않는다(`.gitignore`). 10/7 녹음은 김규림 Google Drive에 있으니 필요하면 요청한다.

## 녹음

| 파일 | 통화 | 길이 |
|---|---|---|
| `call1.wav` | ClawOps 070 · gpt-realtime-2.1 · 통화 1 (서버 녹음 8kHz) | 2분 10초 |
| `call2.wav` | ClawOps 070 · gpt-realtime-2.1 · 통화 2 (서버 녹음 8kHz) | 4분 7초 |
| `luna.wav` | ClawOps 070 · live·luna·낮음 (서버 녹음 8kHz) | 1분 48초 |
| `vapi.m4a` | Vapi 웹 통화 · GPT live + GPT-5.6 Terra · 추론 High (휴대폰 녹음) | 1분 55초 |
| `vapi_low.m4a` | Vapi 웹 통화 · 추론 Low (휴대폰 녹음) | 52초 |

`*_16k.wav`는 분석에 쓴 16kHz 모노 변환본이다. `scripts/to16k.py`로 만든다.

## 분석 다시 돌리기

명령은 모두 이 폴더(`experiments/latency/`)에서 실행한다. 결과는 `data/results/`에 쓴다.

**ClawOps 통화 1·2 (측정 표의 18개 응답)**

```
python scripts/turns.py data/recordings/call1_16k.wav call1
python scripts/turns.py data/recordings/call2_16k.wav call2
python scripts/analyze.py        # 화자 판정 + Whisper 전사, 몇 분 걸린다
python scripts/stats.py          # -> stats.json
```

**새 ClawOps 통화 한 건** (예: `call3.wav`를 `data/recordings/`에 넣은 뒤)

```
python scripts/to16k.py data/recordings/call3.wav
python scripts/turns.py data/recordings/call3_16k.wav call3
python scripts/one_call.py data/recordings/call3_16k.wav call3
python scripts/gaps.py call3_rows.json
```

`one_call.py`는 통화 1의 사람 목소리를 기준으로 화자를 가른다. 담당자 역할이 다른 사람이면 출력된 전사를 보고 화자 판정을 확인한다.

**화자 분리가 되는 녹음 (Vapi 웹 통화)**

```
python scripts/to16k.py data/recordings/vapi.m4a
python scripts/turns.py data/recordings/vapi_16k.wav vapi
python scripts/transcribe_turns.py data/recordings/vapi_16k.wav vapi
python scripts/gaps.py vapi_asr.json --ai-spk 1     # 전사를 보고 AI 쪽 번호를 고른다 (vapi_low는 0)
```

**재현 확인 (10/11).** Windows · Python 3.14에서 luna와 Vapi Low를 다시 돌려 응답 지연 값이 `data/results/`와 같게 나오는 것을 확인했다. Whisper 전사는 문장부호와 한두 단어가 다르게 나왔다.
