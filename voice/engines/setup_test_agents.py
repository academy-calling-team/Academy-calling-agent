"""ClawOps와 Vapi에 같은 설정의 GPT-Live 시험 에이전트를 만든다 (응답 지연 비교용).

설정은 아래 SETTINGS 한 곳에서 정하고, 두 플랫폼의 요청 본문을 여기서 함께 만든다.
프롬프트는 두 플랫폼이 같은 파일을 읽는다. 키는 voice/.env에서 읽고 화면에 출력하지 않는다.

저장소 맨 위에서 실행한다.
  python voice/engines/setup_test_agents.py plan       보낼 내용과 비교표만 출력 (아무것도 만들지 않음)
  python voice/engines/setup_test_agents.py create     두 플랫폼에 만들고 다시 읽어 비교, ID를 voice/.env에 저장
  python voice/engines/setup_test_agents.py update     SETTINGS나 프롬프트를 바꾼 뒤 두 에이전트를 같이 고침
  python voice/engines/setup_test_agents.py show       저장된 두 에이전트를 읽어 비교표 출력 (읽기만)
  python voice/engines/setup_test_agents.py call vapi 01012345678      시험 통화 1통 (ClawOps 발신 시간 차감)
  python voice/engines/setup_test_agents.py call clawops 01012345678
  python voice/engines/setup_test_agents.py status vapi <callId>       통화 결과 조회 (읽기만)
  python voice/engines/setup_test_agents.py status clawops <callId>
"""
import hashlib
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENV = ROOT / 'voice' / '.env'

# 두 플랫폼에 똑같이 들어갈 설정. 지연이 가장 적은 쪽으로 골랐다.
SETTINGS = {
    'name': '시험 GPT-Live luna none marin',
    'prompt_file': 'voice/prompts/agent_prompt_v2.txt',
    'speaker_model': 'gpt-live-1',       # 말하는 모델. 두 플랫폼 모두 말 끝 판정을 이 모델이 직접 한다
    'reasoner_model': 'gpt-5.6-luna',    # 업무 처리 모델. 두 플랫폼 공통 선택지는 luna, terra
    'reasoning_effort': 'none',          # 가장 빠른 값. 정확도가 떨어지면 두 쪽 모두 'low'로
    'voice': 'marin',                    # GPT-Live 음성 22종은 두 플랫폼에 똑같이 있다
    'language': 'ko',
    'ai_speaks_first': False,            # 학원 쪽이 "네, ○○학원입니다"를 먼저 말한다
    'first_message': '',                 # ai_speaks_first=True일 때 Vapi가 말할 첫마디
    'max_duration_seconds': 600,         # Vapi 전용 (ClawOps에는 항목 없음)
}

CLAWOPS = 'https://api.claw-ops.com/v1/accounts/{acc}'
VAPI = 'https://api.vapi.ai'


# ---------- 공통 ----------

def load_env():
    env = {}
    for line in open(ENV, encoding='utf-8'):
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def save_env(key, value):
    """voice/.env의 key 줄을 바꾸거나 없으면 끝에 붙인다. 다른 줄과 줄바꿈 형식은 그대로 둔다."""
    raw = open(ENV, encoding='utf-8', newline='').read()
    nl = '\r\n' if '\r\n' in raw else '\n'
    new, n = re.subn(rf'(?m)^{key}=.*?(\r?)$', lambda m: f'{key}={value}{m.group(1)}', raw)
    if n == 0:
        new = raw + ('' if raw.endswith(('\n', '\r\n')) else nl) + f'{key}={value}{nl}'
    open(ENV, 'w', encoding='utf-8', newline='').write(new)


def secrets(env):
    return [v for k, v in env.items() if v and any(t in k for t in ('KEY', 'PASSWORD', 'USERNAME'))]


def request(method, url, token, env, body=None):
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json',
               'Content-Type': 'application/json', 'User-Agent': 'curl/8.9.1'}
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            text = r.read().decode() or 'null'
            return r.status, json.loads(text)
    except urllib.error.HTTPError as e:
        text = e.read().decode(errors='replace')
        for s in secrets(env):
            text = text.replace(s, '***')
        try:
            return e.code, json.loads(text)
        except ValueError:
            return e.code, text[:500]


def items(b):
    if isinstance(b, list):
        return b
    if isinstance(b, dict):
        for k in ('data', 'items', 'results', 'agents'):
            if isinstance(b.get(k), list):
                return b[k]
    return []


def dig(obj, *path):
    for p in path:
        if not isinstance(obj, dict):
            return None
        obj = obj.get(p)
    return obj


def prompt_text():
    return (ROOT / SETTINGS['prompt_file']).read_text(encoding='utf-8').strip()


def fingerprint(text):
    if not text:
        return '(없음)'
    return f"{hashlib.sha256(text.strip().encode()).hexdigest()[:12]} · {len(text.strip())}자"


# ---------- 요청 본문 ----------

def clawops_body(prompt):
    s = SETTINGS
    return {
        'name': s['name'],
        'instructions': prompt,
        'greeting': s['ai_speaks_first'],
        'configuration': {
            'outputMode': 'live',
            'language': s['language'],
            'knowledge': {'enabled': False, 'topK': 3},  # 끈 상태에서도 topK(1~10)를 요구한다
            'llm': {
                'provider': 'openai-live',
                'model': s['speaker_model'],
                'voice': s['voice'],
                'backend_model': s['reasoner_model'],
                'backend_reasoning_effort': s['reasoning_effort'],
            },
        },
    }


def vapi_body(prompt):
    s = SETTINGS
    body = {
        'name': s['name'],
        'model': {
            'provider': 'openai',
            'model': s['speaker_model'],
            'messages': [{'role': 'system', 'content': prompt}],
            'reasoner': {'provider': 'openai', 'model': s['reasoner_model'],
                         'reasoningEffort': s['reasoning_effort']},
        },
        'voice': {'provider': 'openai', 'voiceId': s['voice']},
        'firstMessageMode': 'assistant-speaks-first' if s['ai_speaks_first'] else 'assistant-waits-for-user',
        # ClawOps에 없는 것은 끈다: 전화 통화 기본 배경음 'office', 잡음 제거, 음성사서함 감지
        'backgroundSound': 'off',
        'backgroundSpeechDenoisingPlan': {'smartDenoisingPlan': {'enabled': False},
                                          'fourierDenoisingPlan': {'enabled': False}},
        'voicemailDetection': 'off',
        'maxDurationSeconds': s['max_duration_seconds'],
        'artifactPlan': {'recordingEnabled': True, 'recordingFormat': 'wav;l16'},
    }
    if s['ai_speaks_first']:
        body['firstMessage'] = s['first_message']
    return body


# ---------- 비교표 ----------

def compare(co, va):
    """co: ClawOps 에이전트(JSON), va: Vapi 어시스턴트(JSON). 실제 저장된 값끼리 비교한다."""
    llm = dig(co, 'configuration', 'llm') or {}
    msgs = dig(va, 'model', 'messages') or []
    va_prompt = next((m.get('content') for m in msgs if m.get('role') == 'system'), None)
    den = va.get('backgroundSpeechDenoisingPlan') or {}
    rows = [
        ('출력 모드', dig(co, 'configuration', 'outputMode'), 'gpt-live (모델로 정해짐)', None),
        ('말하는 모델', llm.get('model'), dig(va, 'model', 'model'), True),
        ('업무 처리 모델', llm.get('backend_model') or llm.get('backendModel'), dig(va, 'model', 'reasoner', 'model'), True),
        ('추론 강도', llm.get('backend_reasoning_effort') or llm.get('backendReasoningEffort'),
         dig(va, 'model', 'reasoner', 'reasoningEffort'), True),
        ('음성', llm.get('voice'), dig(va, 'voice', 'voiceId'), True),
        ('AI가 먼저 말함', co.get('greeting'), va.get('firstMessageMode') == 'assistant-speaks-first', True),
        ('프롬프트 (해시 · 글자 수)', fingerprint(co.get('instructions')), fingerprint(va_prompt), True),
        ('언어', dig(co, 'configuration', 'language') or co.get('language'), '(항목 없음, 프롬프트로 한국어)', None),
        ('지식 검색', dig(co, 'configuration', 'knowledge', 'enabled'), bool(dig(va, 'model', 'knowledgeBase')), True),
        ('말 끝 판정', '모델 내장 (설정 없음)', '모델 내장 (시작·멈춤 대기 설정 적용 안 됨)', None),
        ('배경음', '(없음)', va.get('backgroundSound'), None),
        ('잡음 제거', '(live 모드에 항목 없음)',
         f"Krisp {dig(den, 'smartDenoisingPlan', 'enabled')}, Fourier {dig(den, 'fourierDenoisingPlan', 'enabled')}", None),
        ('음성사서함 감지', '(발신 요청에서 설정, 기본 꺼짐)', va.get('voicemailDetection'), None),
        ('최대 통화 시간', '(항목 없음)', va.get('maxDurationSeconds'), None),
        ('녹음', '번호 부가서비스 (서버 녹음 8kHz)', f"Vapi 녹음 {dig(va, 'artifactPlan', 'recordingEnabled')}", None),
        ('통화 경로', '휴대폰 → ClawOps(국내) → OpenAI', '휴대폰 → ClawOps → Vapi(미국) → OpenAI', None),
    ]
    w = max(len(r[0]) for r in rows) + 2
    print(f"\n{'항목'.ljust(w)}  {'ClawOps'.ljust(34)}  {'Vapi'.ljust(34)}  비교")
    bad = 0
    for name, a, b, check in rows:
        mark = '' if check is None else ('같음' if a == b else '다름')
        bad += mark == '다름'
        print(f'{name.ljust(w)}  {str(a).ljust(34)}  {str(b).ljust(34)}  {mark}')
    print('\n맞춰야 할 항목이 모두 같습니다.' if not bad else f'\n다른 항목 {bad}개. SETTINGS를 확인하고 update를 실행하세요.')
    return bad


def expected():
    """plan용: 보낼 본문을 저장된 값처럼 보고 비교한다."""
    p = prompt_text()
    return clawops_body(p), vapi_body(p)


# ---------- 명령 ----------

def find_clawops(env, base):
    st, b = request('GET', f'{base}/agents', env['CLAWOPS_API_KEY'], env)
    return next((a for a in items(b) if a.get('name') == SETTINGS['name']), None)


def find_vapi(env):
    st, b = request('GET', f'{VAPI}/assistant?limit=100', env['VAPI_API_KEY'], env)
    return next((a for a in items(b) if a.get('name') == SETTINGS['name']), None)


def fetch(env):
    base = CLAWOPS.format(acc=env['CLAWOPS_ACCOUNT_ID'])
    co_id, va_id = env.get('CLAWOPS_AGENT_ID'), env.get('VAPI_ASSISTANT_ID')
    if not co_id or not va_id:
        sys.exit('voice/.env에 CLAWOPS_AGENT_ID와 VAPI_ASSISTANT_ID가 없습니다. 먼저 create를 실행하세요.')
    st1, co = request('GET', f'{base}/agents/{co_id}', env['CLAWOPS_API_KEY'], env)
    st2, va = request('GET', f'{VAPI}/assistant/{va_id}', env['VAPI_API_KEY'], env)
    if st1 != 200 or st2 != 200:
        sys.exit(f'조회 실패: ClawOps {st1} {co if st1 != 200 else ""} / Vapi {st2} {va if st2 != 200 else ""}')
    return co, va


def cmd_plan(env):
    p = prompt_text()
    co, va = clawops_body(p), vapi_body(p)
    short = lambda b: json.loads(json.dumps(b).replace(json.dumps(p)[1:-1], f'<프롬프트 {fingerprint(p)}>'))
    print('[ClawOps POST /agents]\n' + json.dumps(short(co), ensure_ascii=False, indent=1))
    print('[Vapi POST /assistant]\n' + json.dumps(short(va), ensure_ascii=False, indent=1))
    compare(*expected())


def cmd_create(env):
    base = CLAWOPS.format(acc=env['CLAWOPS_ACCOUNT_ID'])
    p = prompt_text()
    co = find_clawops(env, base)
    if co:
        print('ClawOps: 같은 이름의 에이전트가 있어 그대로 씁니다 →', co.get('agentId'))
    else:
        st, co = request('POST', f'{base}/agents', env['CLAWOPS_API_KEY'], env, clawops_body(p))
        if st >= 300:
            sys.exit(f'ClawOps 에이전트 생성 실패 {st}: {co}')
        print('ClawOps: 에이전트 생성', st, '→', co.get('agentId'))
    save_env('CLAWOPS_AGENT_ID', co['agentId'])
    va = find_vapi(env)
    if va:
        print('Vapi: 같은 이름의 어시스턴트가 있어 그대로 씁니다 →', va.get('id'))
    else:
        st, va = request('POST', f'{VAPI}/assistant', env['VAPI_API_KEY'], env, vapi_body(p))
        if st >= 300:
            sys.exit(f'Vapi 어시스턴트 생성 실패 {st}: {va}  (ClawOps 에이전트는 만들어진 상태)')
        print('Vapi: 어시스턴트 생성', st, '→', va.get('id'))
    save_env('VAPI_ASSISTANT_ID', va['id'])
    print('voice/.env에 CLAWOPS_AGENT_ID, VAPI_ASSISTANT_ID 저장')
    compare(*fetch(load_env()))


def cmd_update(env):
    base = CLAWOPS.format(acc=env['CLAWOPS_ACCOUNT_ID'])
    p = prompt_text()
    co_id, va_id = env.get('CLAWOPS_AGENT_ID'), env.get('VAPI_ASSISTANT_ID')
    if not co_id or not va_id:
        sys.exit('voice/.env에 CLAWOPS_AGENT_ID와 VAPI_ASSISTANT_ID가 없습니다. 먼저 create를 실행하세요.')
    st, r = request('PATCH', f'{base}/agents/{co_id}', env['CLAWOPS_API_KEY'], env, clawops_body(p))
    print('ClawOps 수정', st, '' if st < 300 else r)
    st, r = request('PATCH', f'{VAPI}/assistant/{va_id}', env['VAPI_API_KEY'], env, vapi_body(p))
    print('Vapi 수정', st, '' if st < 300 else r)
    compare(*fetch(env))


def cmd_show(env):
    compare(*fetch(env))


def cmd_call(env, engine, to):
    to = to.replace('-', '').replace(' ', '')
    if not re.fullmatch(r'01\d{8,9}', to):
        sys.exit('받을 번호는 01012345678 형식으로 넣으세요.')
    if engine == 'vapi':
        body = {'name': f"시험 {SETTINGS['name']}", 'assistantId': env['VAPI_ASSISTANT_ID'],
                'phoneNumberId': env['VAPI_PHONE_NUMBER_ID'],
                'customer': {'number': to, 'numberE164CheckEnabled': False}}
        st, r = request('POST', f'{VAPI}/call', env['VAPI_API_KEY'], env, body)
        print('Vapi 발신', st, '→ callId', r.get('id') if isinstance(r, dict) and st < 300 else r)
    elif engine == 'clawops':
        base = CLAWOPS.format(acc=env['CLAWOPS_ACCOUNT_ID'])
        body = {'To': to, 'From': env['CLAWOPS_FROM_NUMBER'], 'AgentId': env['CLAWOPS_AGENT_ID'], 'Timeout': 30}
        st, r = request('POST', f'{base}/calls', env['CLAWOPS_API_KEY'], env, body)
        cid = (r.get('callId') or r.get('sid') or r.get('id')) if isinstance(r, dict) else None
        print('ClawOps 발신', st, '→ callId', cid if st < 300 else r)
    else:
        sys.exit('엔진은 vapi 또는 clawops')


def cmd_status(env, engine, call_id):
    if engine == 'vapi':
        st, r = request('GET', f'{VAPI}/call/{call_id}', env['VAPI_API_KEY'], env)
        keys = ('status', 'endedReason', 'startedAt', 'endedAt', 'type')
        print('Vapi', st, {k: r.get(k) for k in keys} if isinstance(r, dict) else r)
        if isinstance(r, dict):
            print('  녹음 있음' if dig(r, 'artifact', 'recordingUrl') or r.get('recordingUrl') else '  녹음 없음')
    else:
        base = CLAWOPS.format(acc=env['CLAWOPS_ACCOUNT_ID'])
        st, r = request('GET', f'{base}/calls/{call_id}', env['CLAWOPS_API_KEY'], env)
        if isinstance(r, dict):
            r = {k: v for k, v in r.items() if not any(t in k.lower() for t in ('token', 'secret', 'url'))}
        print('ClawOps', st, json.dumps(r, ensure_ascii=False)[:800])


def main():
    args = sys.argv[1:] or ['plan']
    env = load_env()
    cmd = args[0]
    if cmd == 'plan':
        cmd_plan(env)
    elif cmd == 'create':
        cmd_create(env)
    elif cmd == 'update':
        cmd_update(env)
    elif cmd == 'show':
        cmd_show(env)
    elif cmd == 'call' and len(args) == 3:
        cmd_call(env, args[1], args[2])
    elif cmd == 'status' and len(args) == 3:
        cmd_status(env, args[1], args[2])
    else:
        sys.exit(__doc__)


if __name__ == '__main__':
    main()
