"""실제 음성 워커가 쓸 ClawOps 서비스 에이전트를 만든다.

10/13 지연 비교용 시험 에이전트(setup_test_agents.py, 프롬프트 v3)는 측정 조건을 지키려고 그대로 두고,
같은 모델·음성 설정에 범용 프롬프트(voice/prompts/service_agent_prompt.txt)를 넣은 에이전트를 따로 만든다.
학원·학생·질문은 워커가 통화마다 CallContext로 넘긴다.

저장소 맨 위에서 실행한다. 키는 voice/.env에서 읽고 화면에 출력하지 않는다.
  python voice/engines/setup_service_agent.py create    만들고 ID를 voice/.env의 CLAWOPS_SERVICE_AGENT_ID에 저장
  python voice/engines/setup_service_agent.py update    프롬프트를 바꾼 뒤 서비스 에이전트를 고침
  python voice/engines/setup_service_agent.py show      서비스 에이전트 설정 확인 (읽기만)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import setup_test_agents as t  # noqa: E402  (같은 모델·음성 설정과 요청 함수를 그대로 쓴다)

NAME = '서비스 GPT-Live luna none marin'
PROMPT = t.ROOT / 'voice' / 'prompts' / 'service_agent_prompt.txt'


def body():
    b = t.clawops_body(PROMPT.read_text(encoding='utf-8').strip())
    b['name'] = NAME
    return b


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'show'
    env = t.load_env()
    base = t.CLAWOPS.format(acc=env['CLAWOPS_ACCOUNT_ID'])
    key = env['CLAWOPS_API_KEY']
    agent_id = env.get('CLAWOPS_SERVICE_AGENT_ID')
    if cmd == 'create':
        if agent_id:
            sys.exit(f'이미 있습니다: {agent_id}. 프롬프트를 바꿨으면 update를 실행하세요.')
        st, r = t.request('POST', f'{base}/agents', key, env, body())
        if st >= 300:
            sys.exit(f'생성 실패 {st}: {r}')
        t.save_env('CLAWOPS_SERVICE_AGENT_ID', r['agentId'])
        print('서비스 에이전트 생성 →', r['agentId'], '(voice/.env의 CLAWOPS_SERVICE_AGENT_ID에 저장)')
    elif cmd in ('update', 'show'):
        if not agent_id:
            sys.exit('voice/.env에 CLAWOPS_SERVICE_AGENT_ID가 없습니다. 먼저 create를 실행하세요.')
        if cmd == 'update':
            st, r = t.request('PATCH', f'{base}/agents/{agent_id}', key, env, body())
            print('수정', st, '' if st < 300 else r)
        st, r = t.request('GET', f'{base}/agents/{agent_id}', key, env)
        if st >= 300:
            sys.exit(f'조회 실패 {st}: {r}')
        llm = t.dig(r, 'configuration', 'llm') or {}
        print('이름:', r.get('name'), '| 모델:', llm.get('model'), llm.get('backend_model'),
              llm.get('backend_reasoning_effort'), '| 음성:', llm.get('voice'),
              '| 프롬프트:', t.fingerprint(r.get('instructions')), '(파일', t.fingerprint(PROMPT.read_text(encoding='utf-8')), ')')
    else:
        sys.exit(__doc__)


if __name__ == '__main__':
    main()
