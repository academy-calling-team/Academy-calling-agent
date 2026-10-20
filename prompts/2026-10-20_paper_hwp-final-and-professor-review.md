# 논문 HWP 최종본, 실통화 반영, 지도교수님 코멘트 반영 (10/19~10/20)

- 날짜: 2026-10-19 ~ 2026-10-20
- 작성자: 강유준
- 사용한 도구: Claude (Claude Code)
- 목적: 한국정보기술학회 2026 추계(대학생논문경진대회 부문)에 낼 논문을 학회 표준양식 HWP 5쪽으로 옮기고, 10/19 실통화 통합 시험 결과와 10/20 김재수 교수님 코멘트를 반영한다. 10/14 초안 작성 기록은 `2026-10-14_paper-draft.md`, D2 제외 이유 정정은 `2026-10-19_d2-exclusion-reason.md`에 있다.

## 프롬프트

입력한 내용을 그대로 옮겼다. 공개 저장소라 이메일 주소와 학교 담당자 정보는 `[ ]`로 가렸고, 긴 붙여넣기는 무엇을 붙였는지만 적었다.

### 1. 문장 검수와 날짜 정리 (10/19)

```
/humanizer 최종 검수해줘
```

```
[딩옌 이메일] 이걸로 딩옌님 이메일 바꿔주고, 학생 5명의 영어 이름은 저거 맞는 것 같아. 진행안한 나머지 마저 진행해줘. 그리고 서론은 밑 페이지로 내리자.
```

```
/humanizer AI의 응답이 늦거나 말이 끊기면 통화가 어색해진다. 이거 문장이 너무 짧아서 이상한데 아예 빼거나 다른 문장으로 합치거나 해줘. 이런식의 문장이 더 있는지 확인하고 마찬가지로 수정해줘
```

```
10월 19일, 10월 15일에 ~~했다 같은 실제 날짜는 빼는게 좋을 것 같은데.
```

### 2. 검토 프롬프트 반복 (10/19)

```
ㅇㅇ 같이 올려서 고치고 다음 3가지 프롬프트 실행->수정을 반복해.

1. Review this paragraph for logical flow. Does the argument progress clearly from premise to evidence to conclusion? Identify any gaps in reasoning.
2. Read this section as a hostile reviewer for 한국정보기술학회.List the five weakest points in order of severity, quote the exact sentence each weakness lives in, and say what evidence or rewording would fix it.
3. Here are my abstract and conclusion: [paste both]. List every claim in the abstract that the conclusion does not support, and every conclusion claim missing from the abstract. Then check that every number appearing in both matches exactly.
```

```
논문 실제로 존재하는 논문인지, 본문 내용을 참고해서 적절한 곳에 인용되었는지 살펴봐
```

```
/remove-ai-marks 논문 함 확인해서 수정해줘
```

### 3. HWP 표준양식으로 옮기기 (10/19)

```
hwp로 어케옮겨야함?
```

```
[HWP 파일] 현재 이렇게 했는데 양식 내가 못맞춘 부분 다 지적해주고 현재 6페이지인데 어떻게 할지 생각해줘
```

```
[HWP 파일] 다시 처음부터 양식보고 안맞는거 있는지 확인하고 지금 참고문헌 8만 6페이지에 있는데 뭘 줄여야할지 생각해봐
```

```
/humanizer [영문 초록 붙여넣음] 이거 좀 더 줄여봐
```

머리말·쪽 번호가 안 보이는 문제, 표 2 때문에 쪽이 넘어가는 문제도 HWP 파일을 올리며 물었다.

### 4. 실통화 결과 반영 (10/19)

```
[김규림이 보낸 실통화 시험 결과 정리 붙여넣음] 그렇다는데 내용 변경 해야할까?
```

```
정확한 건수 3 테스트 당시 32 라는데
```

```
[대본 H를 지연 분석에서 뺀 이유를 한 문장 넣자는 검토 의견 붙여넣음] 이라는데
```

### 5. 지도교수님 코멘트 반영 (10/20)

교수님 메일 가운데 논문에 대한 코멘트 부분을 그대로 붙여넣었다.

```
1. 논문 구성
   - IV의 제목을 '실험 및 평가'로 하며, '실험 방법'과 '실험 내용', '논의'를 모두 포함시키는 것이 좋을 것 같음
2. 용어에 대한 설명 :
   - ClawOps, Vapi, RTP, SIP, p90, p95 등의 용어 대해 설명을 하여야 함
   - 실시간 음성 AI Agent 구축 플랫폼인 Vapi
   - 전화번호, 음성 통화, 문자와 실시간 이벤트를 하나의 API로 지원하는 국내 AI 통신 API 플랫폼인 ClawOps
   - Mann-Whitney U 검증
3. 표 2. 와 그림 3.의 위치
   - 그림과 표는 본문의 글자와 가까운 곳에 위치시킴.
   - 표3.에 대한 설명이 필요
4. 논의와 참고문헌을 줄여 전체 5쪽으로 유지

[영문 이름 표기, 저자 소속, 등록비, 대면 회의에 대한 교수님 답변]

/humanizer 이름이랑 저자소속은 내가 바꾸고 있을테니까 나머지 수정해줘
```

```
/humanizer 다음 프롬프트를 모든 글에 순서대로 3번실행해줘

1. Review this paragraph for logical flow. Does the argument progress clearly from premise to evidence to conclusion? Identify any gaps in reasoning.
2. Reduce this paragraph without losing any claim, number, or citation. Keep the academic register
and my terminology.
3. Read this section as a hostile reviewer for 한국정보기술학회. List the five weakest points in order of severity, quote the exact sentence each weakness lives in, and say what evidence or rewording would fix it.
4. Here are my abstract and conclusion. List every claim in the abstract that the conclusion does not support, and every conclusion claim missing from the abstract. Then check that every number appearing in both matches exactly.
```

```
[HWP에서 뽑은 PDF] 이걸로 하면되지? 최종점검 부탁해
```

## 결과를 어떻게 썼는지

- 10/19: 문장 수정은 HTML 판(9~16판)에 파란색으로 표시해 받고, 강유준이 골라서 HWP에 옮겼다. 짧게 끊긴 문장은 앞뒤 문장과 합쳤고, 본문의 실제 날짜는 뺐다. 각주의 교신 날짜와 참고문헌 접속일은 인용 형식이라 남겼다.
- 검토 프롬프트에서 나온 지적은 근거를 바꾸는 표현만 고쳤다. "Vapi가 더 빠르다"를 "빠른 경향이나 통화 단위로는 확정할 수 없다"로 바꿨고, 6.1의 "경로 손해 90ms를 빼면" 계산은 TCP 연결 시간이 음성 경로가 아니어서 뺐다.
- 참고문헌 8개는 원문이 실제로 있는지와 인용 위치를 확인했고, 번호를 처음 인용한 순서로 다시 매겼다.
- HWP 조판은 강유준이 직접 했다. Claude는 HWP 파일을 읽어 양식(글꼴, 크기, 장평, 여백, 캡션 위치)과 어긋난 곳, 머리말·쪽 번호가 첫 문단의 조판 부호와 함께 있어서 생긴 문제, 6쪽으로 넘어가는 원인을 짚었다.
- 실통화 결과(실제 워커 구현, 공동 서버 실통화 3건, 자동 테스트 197개)는 김규림의 정리를 저장소 커밋과 PR로 확인한 뒤 3.3절과 요약·결론에 넣고, 그림 1(시스템 구조, 실제 워커는 실선)을 새로 그렸다. 논문 원고와 그림 파일은 아직 이 저장소에 올리지 않았다.
- 10/20: 수정은 HTML 17판(교수님 코멘트)과 18판(검토 3회)에 파란색으로 받고, 강유준이 HWP v3·v4에 옮겼다. 교수님 코멘트대로 Ⅳ장을 '실험 및 평가'(4.1 실험 방법, 4.2 실험 결과, 4.3 논의)로 묶고, 용어 설명은 교수님이 주신 ClawOps·Vapi 문구를 그대로 썼다. 표 2와 그림 3은 인용 문단 바로 뒤로 옮겼다. 논문에 표 3이 없어 '표 3에 대한 설명'은 그림 3 설명으로 보고 넣었으며, 이 해석과 4.2절 제목('실험 내용' 대신 '실험 결과')은 교수님께 다시 확인을 요청했다.
- 5쪽 유지: 참고문헌 2개(TurnGPT, PARADISE)를 빼고 논의를 줄였다. 쪽이 넘는지는 최종 PDF의 글자 폭과 줄 간격으로 한글 조판을 흉내 내 계산했고, 이 계산은 기존 최종본의 제목·표·그림 위치를 0.5pt 안으로 재현했다. 실제 HWP(v3, v4)도 5쪽이었다.
- 검토 프롬프트 3회 결과 가운데 글로 고칠 수 있는 것(검정이 양측임을 밝힘, 완전 무음 비교의 녹음 지점, 요약과 결론의 낱말 맞춤)만 반영했다. 표본 크기, 판정자 한 명, 판정 정확도 미평가는 데이터가 있어야 해결되므로 한계로 둔다.
- 숫자(지연 중앙값 1.57초·1.42초, p=0.038, 부트스트랩 −0.01~0.35초, 완전 무음 12회)는 바꾸지 않았다. 모두 `experiments/latency/scripts/human_stats.py`로 재현된다.
