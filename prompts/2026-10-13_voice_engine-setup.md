# ClawOps·Vapi 동일 설정 시험 에이전트

- 날짜: 2026-10-12 ~ 10-13
- 작성자: 김규림
- 사용한 도구: Claude (Claude Code)
- 목적: Vapi를 ClawOps 070 회선에 SIP로 연결하고, 응답 지연을 공정하게 비교하도록 두 플랫폼에 같은 설정의 GPT-Live 시험 에이전트를 만드는 스크립트 작성

## 프롬프트

Vapi와 ClawOps 연결:

```
진행해줘
```

```
실행했어 확인해줘
```

같은 설정의 시험 에이전트:

```
지금 clawops와 vapi의 설정을 동일하게 하고 실행하려는데 가능한한 지연이 적은 방향으로 동일 세팅 설정 가능해?
```

```
응 1번 시험 어시스턴트 스크립트 만들어줘 양쪽이 최대한 동일하게 그리고 빠지는것 없이
```

```
에이전트 생성 실패 400
```

```
create 성공했어 올려줘
```

## 결과를 어떻게 썼는지

- Claude가 두 플랫폼의 공개 API 명세(api.claw-ops.com/openapi.json, api.vapi.ai/api-json)에서 설정 항목을 대조했다. 같은 모델로 맞출 수 있는 조합은 GPT-Live뿐이었다(realtime 모델은 ClawOps 2.1, Vapi 2로 버전이 다름).
- `voice/engines/register_vapi_trunk.py`: Vapi에 ClawOps SIP 트렁크와 070 번호를 등록. Claude가 작성하고, 자동 권한 검사가 외부 설정 생성을 막아 김규림이 직접 실행했다.
- `voice/engines/setup_test_agents.py`: 두 플랫폼 설정을 한 곳에서 정해 에이전트를 만들고, 저장된 값을 다시 읽어 비교한다. 첫 실행은 ClawOps가 지식 검색을 끈 상태에서도 `topK`를 요구해 400으로 실패했고, 고친 뒤 성공했다. 다시 읽은 값에서 맞춰야 할 항목(모델, 업무 처리 모델, 추론 강도, 음성, 첫마디, 프롬프트, 지식 검색)이 모두 같은 것을 확인했다.
- `voice/prompts/agent_prompt_v2.txt`: 10/7 역할 문구 v2를 그대로 옮긴 것. 두 플랫폼이 같은 파일을 읽는다.
