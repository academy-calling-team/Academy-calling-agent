"""Vapi에 ClawOps 070 회선을 BYO SIP 트렁크로 등록하고, 번호 ID를 voice/.env에 넣는다.

ClawOps 대시보드 전화번호 › SIP 단말에서 발급한 계정(CLAWOPS_SIP_USERNAME·PASSWORD)과
SIP 도메인·발신번호가 voice/.env에 있어야 한다. 비밀값은 출력하지 않는다.
Vapi에 트렁크나 번호가 이미 있으면 아무것도 만들지 않고 멈춘다.

  python voice/engines/register_vapi_trunk.py

설정: 신호는 TLS 5061, 음성은 평문 RTP부터 시도(outboundProtocol 'tls'). 소리가 안 나면 'tls/srtp'로 바꾼다.
발신 전용(inboundEnabled False), 번호 앞 + 없음(ClawOps는 0으로 시작하는 국내 형식만 받는다).
"""
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ENV = Path(__file__).resolve().parents[2] / 'voice' / '.env'

env = {}
for line in open(ENV, encoding='utf-8'):
    line = line.strip()
    if line and not line.startswith('#') and '=' in line:
        k, v = line.split('=', 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
H = {'Authorization': f"Bearer {env['VAPI_API_KEY']}", 'Content-Type': 'application/json',
     'Accept': 'application/json', 'User-Agent': 'curl/8.9.1'}


def call(method, url, body=None):
    req = urllib.request.Request(url, method=method, headers=H,
                                 data=json.dumps(body).encode() if body is not None else None)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.load(e)
        except Exception:
            return e.code, None


_, creds = call('GET', 'https://api.vapi.ai/credential?limit=100')
_, nums = call('GET', 'https://api.vapi.ai/phone-number?limit=100')
n_trunk = sum(c.get('provider') == 'byo-sip-trunk' for c in creds or [])
if n_trunk or nums:
    sys.exit(f'이미 등록된 항목이 있어 멈춤: byo 트렁크 {n_trunk}개, 번호 {len(nums or [])}개')

# 1. ClawOps SIP 트렁크
body = {
    'provider': 'byo-sip-trunk',
    'name': 'ClawOps 070 (TLS)',
    'gateways': [{'ip': env['CLAWOPS_SIP_DOMAIN'], 'port': int(env.get('CLAWOPS_SIP_PORT') or 5061),
                  'outboundProtocol': 'tls', 'inboundEnabled': False}],
    'outboundAuthenticationPlan': {'authUsername': env['CLAWOPS_SIP_USERNAME'],
                                   'authPassword': env['CLAWOPS_SIP_PASSWORD']},
    'outboundLeadingPlusEnabled': False,
}
st, cred = call('POST', 'https://api.vapi.ai/credential', body)
if st >= 300:
    msg = json.dumps(cred, ensure_ascii=False)[:500] if cred else ''
    for s in (env['CLAWOPS_SIP_PASSWORD'], env['CLAWOPS_SIP_USERNAME']):
        msg = msg.replace(s, '***')
    sys.exit(f'트렁크 등록 실패 {st}: {msg}')
gw = cred.get('gateways', [{}])[0]
print('1. 트렁크 등록', st, '| id', cred['id'], '| gateway', gw.get('port'), gw.get('outboundProtocol'),
      'inbound', gw.get('inboundEnabled'))

# 2. 070 번호 (E.164 검사 끔)
body = {'provider': 'byo-phone-number', 'name': 'ClawOps 070', 'number': env['CLAWOPS_FROM_NUMBER'],
        'numberE164CheckEnabled': False, 'credentialId': cred['id']}
st, num = call('POST', 'https://api.vapi.ai/phone-number', body)
if st >= 300:
    sys.exit(f'번호 등록 실패 {st}: {json.dumps(num, ensure_ascii=False)[:500] if num else ""} '
             f'(트렁크 id {cred["id"]}는 만들어진 상태)')
print('2. 번호 등록', st, '| id', num['id'], '| number', num.get('number'), '| status', num.get('status'))

# 3. 번호 ID를 voice/.env에 저장 (다른 줄과 줄바꿈 형식은 그대로 둔다)
raw = open(ENV, encoding='utf-8', newline='').read()
new, n = re.subn(r'(?m)^VAPI_PHONE_NUMBER_ID=.*?(\r?)$',
                 lambda m: f"VAPI_PHONE_NUMBER_ID={num['id']}{m.group(1)}", raw)
if n != 1:
    sys.exit('3. voice/.env에서 VAPI_PHONE_NUMBER_ID 줄을 찾지 못함. 직접 넣을 값: ' + num['id'])
open(ENV, 'w', encoding='utf-8', newline='').write(new)
print('3. voice/.env VAPI_PHONE_NUMBER_ID 저장')
