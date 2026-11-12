"""ClawOps 서비스 에이전트의 설정과 요청 도구. 외부 호출은 request 실행 시에만 수행한다."""
import hashlib
import json
import re
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENV = ROOT / 'voice' / '.env'
CLAWOPS = 'https://api.claw-ops.com/v1/accounts/{acc}'

# 기존 서비스 에이전트의 모델·음성·말하기 순서를 유지한다.
SETTINGS = {
    'name': '서비스 GPT-Live luna none marin',
    'speaker_model': 'gpt-live-1',
    'reasoner_model': 'gpt-5.6-luna',
    'reasoning_effort': 'none',
    'voice': 'marin',
    'language': 'ko',
    'ai_speaks_first': False,
}


def load_env():
    env = {}
    with ENV.open(encoding='utf-8') as source:
        for line in source:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def save_env(key, value):
    """다른 설정과 줄바꿈 형식을 보존하며 지정 항목만 저장한다."""
    with ENV.open(encoding='utf-8', newline='') as source:
        raw = source.read()
    newline = '\r\n' if '\r\n' in raw else '\n'
    updated, count = re.subn(rf'(?m)^{re.escape(key)}=.*?(\r?)$',
                             lambda match: f'{key}={value}{match.group(1)}', raw)
    if count == 0:
        updated = raw + ('' if raw.endswith(('\n', '\r\n')) else newline) + f'{key}={value}{newline}'
    with ENV.open('w', encoding='utf-8', newline='') as target:
        target.write(updated)


def secrets(env):
    return [value for key, value in env.items()
            if value and any(part in key for part in ('KEY', 'PASSWORD', 'USERNAME'))]


def request(method, url, token, env, body=None):
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json',
               'Content-Type': 'application/json', 'User-Agent': 'curl/8.9.1'}
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return response.status, json.loads(response.read().decode() or 'null')
    except urllib.error.HTTPError as error:
        text = error.read().decode(errors='replace')
        for secret in secrets(env):
            text = text.replace(secret, '***')
        try:
            return error.code, json.loads(text)
        except ValueError:
            return error.code, text[:500]


def dig(obj, *path):
    for part in path:
        if not isinstance(obj, dict):
            return None
        obj = obj.get(part)
    return obj


def fingerprint(text):
    if not text:
        return '(없음)'
    return f"{hashlib.sha256(text.strip().encode()).hexdigest()[:12]} · {len(text.strip())}자"


def clawops_body(prompt):
    settings = SETTINGS
    return {
        'name': settings['name'],
        'instructions': prompt,
        'greeting': settings['ai_speaks_first'],
        'configuration': {
            'outputMode': 'live',
            'language': settings['language'],
            'knowledge': {'enabled': False, 'topK': 3},
            'llm': {
                'provider': 'openai-live',
                'model': settings['speaker_model'],
                'voice': settings['voice'],
                'backend_model': settings['reasoner_model'],
                'backend_reasoning_effort': settings['reasoning_effort'],
            },
        },
    }
