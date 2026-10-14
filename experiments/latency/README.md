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

두 엔진 모두 GPT-Live(gpt-live-1, 업무 처리 모델 gpt-5.6-luna, 추론 강도 none, 음성 marin), 프롬프트 v3, 같은 대본으로 휴대폰에 발신했다. 두 엔진 모두 ClawOps 서버 녹음(같은 지점)으로 쟀다. Vapi 통화는 ClawOps 070 → SIP → Vapi(미국)로 이어진다. 대본과 정답지는 `voice/prompts/test_script_v3.md`, 결과 JSON은 `data/results/1013_co_*`(ClawOps), `1013_va_*`(Vapi)다. 엔진마다 대본 A~E 5통과 응답 수를 채우려고 더 건 A·D 2통(`*_A2`, `*_D2`)을 합쳤다.

| 엔진 (대본 A~E + A2·D2, 7통) | 응답 수 | 평균 (초) | 중앙값 (초) | p90 (초) | p95 (초) | 최대 (초) | 1.5초 넘음 |
|---|---|---|---|---|---|---|---|
| ClawOps 070 · GPT-Live | 50 | 1.67 | 1.62 | 1.94 | 1.99 | 2.43 | 40 (80%) |
| Vapi (ClawOps SIP) · GPT-Live | 48 | 1.44 | 1.44 | 1.75 | 1.86 | 2.13 | 20 (42%) |

| 항목 | ClawOps | Vapi |
|---|---|---|
| 정답지 대비 정확도 (요약 기준) | 24/24 | 23/23 (A의 ③은 사람이 대본과 다르게 말해 제외) |
| 첫인사의 AI·녹음 고지 | 8/8 | 8/8 |
| 말 중간 쉼(H)에 끼어듦 | 없음 (1.5~7.3초 쉼 4번) | 없음 (0.9~5.7초 쉼 4번) |
| 끼어들었을 때 AI가 더 말한 시간 (H) | 1.3초, 0.8초 | 1.2초 |
| 되짚기 뒤 답을 기다리지 않음 | B 2번, A2 1번 | B 3번, A2 3번 |
| 말하는 도중 120~300ms 완전 무음 (패킷 빠짐 의심) | 0번 / AI 말 6.2분 | 12번 / AI 말 6.5분 |

- **Vapi의 이른 응답.** Vapi A2·D2에서는 0.6~1.0초 응답이 여러 번 나왔다. Vapi 통화 기록을 보면 GPT-Live가 사람 말이 끝나기 직전에 말을 시작했고, 미국을 오가는 시간이 더해져 국내 녹음 지점에서는 짧은 간격으로 잡혔다. Vapi A2 28.05초의 짧은 "네" 뒤 응답(0.67초)은 AI가 앞 질문에 이어 말하던 중이라 응답에서 뺐다.
- **대본 이탈.** ClawOps D2는 대본 D 대신 A로 답해서 A 정답지로 채점했다. 지연에는 영향이 없다. 처음 건 ClawOps 1통(24초)은 중간에 끊어 뺐다.

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

## 파형 보며 직접 재기 (뷰어)

`viewer/latency_viewer.html`을 브라우저로 연다. 설치는 필요 없다. 녹음 파일(WAV·m4a·mp3)과 분석 결과(`data/results/<이름>_rows.json`)를 함께 끌어다 놓으면 파형이 화자 색(사람·AI)으로 칠해지고, 자동으로 잰 응답 간격이 띠로 표시된다. 결과 파일 없이 녹음만 넣으면 소리 크기로 말 구간만 나누므로, 구간을 누르고 `1`(사람)·`2`(AI)로 정한다.

- 표의 응답을 누르면 그 지점으로 확대되고 앞 1초부터 재생 위치가 잡힌다. 0.5배속으로 들으며 확인한다.
- 자동 값이 틀렸으면 표시선(사람 말 끝·AI 시작)을 끌어 옮기고 '선택한 응답을 이 값으로 고치기'를 누른다. 새로 재려면 `[`·`]`로 표시선을 찍고 `Enter`.
- 요약(응답 수, 평균, 중앙값, p95, 1.5초 넘음)은 표에서 '빼기'하지 않은 응답으로 계산한다. 'CSV 복사'로 결과를 가져간다.
- 녹음은 브라우저 안에서만 읽고 어디에도 올리지 않는다. 고친 값은 그 브라우저에만 저장된다.

## 한 번에 돌리기 (`measure.py`)

10/13 측정에 쓴 과정(녹음 받기 → 변환 → 화자 분리·전사 → 화자 재판정 → 응답 간격 → 보고)을 통화 목록 CSV 한 장으로 돌린다. 10/13 통화 목록은 `data/calls_1013.csv`다. 열의 뜻은 `scripts/measure.py` 맨 위 설명에 있다.

```
python scripts/measure.py fetch   data/calls_1013.csv      # ClawOps 서버 녹음 받기 (Vapi 통화는 ClawOps 쪽 통화를 시각으로 찾음)
python scripts/measure.py analyze data/calls_1013.csv      # 통화마다 분석, '?'로 남은 구간을 보여 줌
python scripts/measure.py fix     data/calls_1013.csv      # CSV의 fix 열(직접 정한 화자)만 다시 적용
python scripts/measure.py report  data/calls_1013.csv      # 엔진별 지연·겹침·목소리·끊김
python scripts/measure.py transcript data/calls_1013.csv 1013_va_C   # 정답지 대조용 전사
```

- sherpa-onnx가 깔린 가상환경 파이썬으로 실행하고, 키는 저장소의 `voice/.env`에서 읽는다.
- 화자 판정은 대본(`voice/prompts/test_script_v3.md`)의 사람 대사와 AI 말투로 한다(`scripts/relabel.py`). 새 대본을 쓰면 `relabel.py`의 `SCRIPT`에 사람 대사를 넣는다.
- `one_call.py`는 10/7 통화 1의 사람 목소리를 기준으로 쓰므로 `call1.json`과 `call1_16k.wav`가 있어야 한다.
- **재현 확인 (10/14).** `data/calls_1013.csv`로 `fix`·`report`를 돌리면 저장된 결과와 같은 값이 나온다(ClawOps 50개 중앙값 1.62초, Vapi 48개 중앙값 1.44초). `analyze`로 통화 하나를 처음부터 다시 돌려도 결과 JSON이 같았다.

## 분석 다시 돌리기 (스크립트 하나씩)

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
