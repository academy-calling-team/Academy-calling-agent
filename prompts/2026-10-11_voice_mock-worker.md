# 목업 음성 워커

- 날짜: 2026-10-11
- 작성자: 강유준
- 사용한 도구: Claude (Claude Code)
- 목적: 백엔드 워커 계약(worker_openapi.json, result_json_schema.json)에 맞는 목업 음성 워커 작성

## 프롬프트


```
다했어. 확인하고 app.py 작성해봐.
```

```
ㅇㅇ 전부 진행해봐
```

## 결과를 어떻게 썼는지

- `voice/mock_worker/`의 app.py, samples.py, sender.py, fake_backend.py, test_app.py, README.md를 Claude가 작성
- 시험 26개 통과, 가짜 백엔드와 실제 HTTP 왕복(events 4개, result 1개) 확인 후 사용