"""통화 녹음 응답 지연 측정을 한 번에 돌린다 (10/13 측정에 쓴 과정을 묶은 것).

통화 목록 CSV 한 장으로 녹음 받기 → 16kHz 변환 → 음성 구간·화자 분리(turns.py)
→ 화자 판정·전사(one_call.py) → 대본·말투로 화자 재판정(relabel.py) → 응답 간격(gaps.py)
→ 엔진별 보고(report_1013.py, dropouts.py)를 차례로 실행한다.

experiments/latency/ 에서 실행한다. sherpa-onnx가 깔린 파이썬(가상환경)으로 실행한다.
  python scripts/measure.py fetch      data/calls_1013.csv            녹음 받기 (있으면 건너뜀)
  python scripts/measure.py analyze    data/calls_1013.csv [이름...]  분석 (이름을 주면 그 통화만)
  python scripts/measure.py fix        data/calls_1013.csv [이름...]  CSV의 fix만 다시 적용하고 간격 재계산
  python scripts/measure.py report     data/calls_1013.csv            엔진별 지연·겹침·목소리·끊김
  python scripts/measure.py transcript data/calls_1013.csv 이름       정답지 대조용 전사
  python scripts/measure.py run        data/calls_1013.csv            fetch + analyze + report

통화 목록 CSV 열: name, engine, script, call_id, leg_id, latency, fix
- name: '<날짜>_co_<대본>'(ClawOps) 또는 '<날짜>_va_<대본>'(Vapi). 녹음·결과 파일 이름이 된다
- engine: clawops 또는 vapi
- script: 대본(A~H). 화자 재판정에 쓴다(relabel.py의 SCRIPT)
- call_id: ClawOps 통화는 ClawOps callId, Vapi 통화는 Vapi callId
- leg_id: Vapi 통화가 ClawOps에 남긴 통화 ID(녹음은 여기서 받는다). 비우면 fetch가 시각으로 찾아 채운다
- latency: 1이면 지연 통계에 넣고, 0이면 뺀다(대본 H처럼 일부러 쉬거나 끼어든 통화)
- fix: 화자를 직접 정한 구간. '시작초=사람|AI|?'를 ;로 구분한다(예: 23.47=AI;95.55=AI). '?'는 판정에서 뺀다
키는 저장소의 voice/.env에서 읽고 출력하지 않는다.
"""
import csv
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

L = Path(__file__).resolve().parents[1]          # experiments/latency
SCRIPTS = L / 'scripts'
REC = L / 'data' / 'recordings'
OUT = L / 'data' / 'results'
ENV_FILE = L.parents[1] / 'voice' / '.env'
COLUMNS = ['name', 'engine', 'script', 'call_id', 'leg_id', 'latency', 'fix']
CHILD_ENV = {**os.environ, 'PYTHONIOENCODING': 'utf-8'}


# ---------- 공통 ----------

def read_calls(path):
    with open(path, encoding='utf-8-sig', newline='') as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        for c in COLUMNS:
            r.setdefault(c, '')
        tag = {'clawops': 'co', 'vapi': 'va'}.get(r['engine'])
        if tag is None:
            sys.exit(f"{r['name']}: engine은 clawops 또는 vapi")
        parts = r['name'].split('_')
        if len(parts) < 3 or parts[1] != tag:
            sys.exit(f"{r['name']}: 이름은 '<날짜>_{tag}_<대본>' 형식이어야 합니다(끊김 집계가 이 부분으로 엔진을 가른다)")
    return rows


def write_calls(path, rows):
    with open(path, 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction='ignore')
        w.writeheader()
        w.writerows(rows)


def pick(rows, names):
    if not names:
        return rows
    known = {r['name']: r for r in rows}
    missing = [n for n in names if n not in known]
    if missing:
        sys.exit(f'CSV에 없는 이름: {missing}')
    return [known[n] for n in names]


def load_env():
    if not ENV_FILE.exists():
        sys.exit(f'{ENV_FILE}가 없습니다. ClawOps·Vapi 키를 넣어 주세요.')
    env = {}
    for line in open(ENV_FILE, encoding='utf-8'):
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def get(url, key, raw=False):
    req = urllib.request.Request(url, headers={'Authorization': f'Bearer {key}', 'User-Agent': 'curl/8.9.1'})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read() if raw else json.load(r)


def items(b):
    if isinstance(b, list):
        return b
    return next((b[k] for k in ('data', 'items', 'calls') if isinstance(b, dict) and isinstance(b.get(k), list)), [])


def ts(s):
    return datetime.fromisoformat(s.replace('Z', '+00:00'))


def script(name, *args, quiet=False):
    """scripts/ 안의 스크립트를 같은 파이썬으로 실행한다. 실패하면 출력 끝부분을 보여 주고 멈춘다."""
    p = subprocess.run([sys.executable, '-I', '-X', 'utf8', str(SCRIPTS / name), *map(str, args)], cwd=L, env=CHILD_ENV,
                       capture_output=True, text=True, encoding='utf-8', errors='replace')
    if p.returncode != 0:
        print((p.stdout + p.stderr)[-1500:])
        sys.exit(f'{name} 실패 (종료 코드 {p.returncode})')
    if not quiet:
        print(p.stdout, end='')
    return p.stdout


def check_python():
    try:
        import numpy, sherpa_onnx, sklearn  # noqa: F401
    except ImportError as e:
        sys.exit(f'{e.name}가 없는 파이썬입니다. sherpa-onnx를 깐 가상환경 파이썬으로 실행하세요 '
                 f'(예: C:\\Users\\561gu\\capstone8-venv\\Scripts\\python.exe).')


# ---------- 명령 ----------

def cmd_fetch(path, names):
    env = load_env()
    rows = read_calls(path)
    base = f"https://api.claw-ops.com/v1/accounts/{env['CLAWOPS_ACCOUNT_ID']}"
    co_calls = None
    changed = False
    for r in pick(rows, names):
        dst = REC / f"{r['name']}.wav"
        if r['engine'] == 'vapi' and not r['leg_id']:
            v = get(f"https://api.vapi.ai/call/{r['call_id']}", env['VAPI_API_KEY'])
            if co_calls is None:
                co_calls = items(get(f'{base}/calls', env['CLAWOPS_API_KEY']))
            leg = min(co_calls, key=lambda c: abs((ts(c['dateCreated']) - ts(v['createdAt'])).total_seconds()))
            gap = abs((ts(leg['dateCreated']) - ts(v['createdAt'])).total_seconds())
            if gap > 5:
                sys.exit(f"{r['name']}: Vapi 통화와 5초 안에 맞는 ClawOps 통화가 없습니다(가장 가까운 것 {gap:.1f}초 차이)")
            r['leg_id'], changed = leg['callId'], True
            print(f"{r['name']}: ClawOps 통화 {leg['callId']} (시각 차 {gap:.1f}초)")
        if dst.exists():
            print(f"{r['name']}: 녹음 있음, 건너뜀")
            continue
        rec_id = r['leg_id'] if r['engine'] == 'vapi' else r['call_id']
        try:
            data = get(f'{base}/recordings/{rec_id}', env['CLAWOPS_API_KEY'], raw=True)
        except urllib.error.HTTPError as e:
            sys.exit(f"{r['name']}: 녹음 받기 실패 {e.code} (통화가 끝나고 녹음이 올라갔는지 확인)")
        dst.write_bytes(data)
        print(f"{r['name']}: 녹음 {len(data) / 1e6:.2f}MB 저장")
    if changed:
        write_calls(path, rows)
        print(f'{path}에 leg_id를 채웠습니다.')


def relabel_args(r):
    args = [OUT, r['name'], r['script']]
    fixes = [f for f in r['fix'].split(';') if f.strip()]
    return args + (['--fix', *fixes] if fixes else [])


def cmd_analyze(path, names):
    check_python()
    for r in pick(read_calls(path), names):
        n = r['name']
        wav = REC / f'{n}.wav'
        if not wav.exists():
            sys.exit(f'{n}: 녹음이 없습니다. 먼저 fetch를 실행하세요.')
        print(f'===== {n} ({r["engine"]}, 대본 {r["script"]})')
        script('to16k.py', wav, quiet=True)
        wav16 = REC / f'{n}_16k.wav'
        script('turns.py', wav16, n, quiet=True)
        out = script('one_call.py', wav16, n, quiet=True)
        print(next((x for x in out.splitlines() if x.startswith('cluster similarity')), ''))
        script('relabel.py', *relabel_args(r))
        print(script('gaps.py', f'{n}_rows.json', quiet=True).splitlines()[-2])
    print("\n'?'로 남은 구간이나 잘못 판정된 구간은 CSV의 fix 열에 적고 fix 명령으로 다시 계산하세요.")


def cmd_fix(path, names):
    for r in pick(read_calls(path), names):
        out = script('relabel.py', *relabel_args(r), quiet=True)
        summary = script('gaps.py', f"{r['name']}_rows.json", quiet=True).splitlines()[-2]
        print(out.splitlines()[0], '|', summary)


def cmd_report(path, names):
    check_python()
    rows = pick(read_calls(path), names)
    all_names = []
    for engine in ('clawops', 'vapi'):
        group = [r for r in rows if r['engine'] == engine]
        if not group:
            continue
        ns = [r['name'] for r in group]
        lat = [r['name'] for r in group if r['latency'].strip() != '0']
        all_names += ns
        print(f'################ {engine}')
        script('report_1013.py', L, engine, *ns, '--latency', *lat)
    print('################ 말하는 도중 무음 (끊김)')
    out = script('dropouts.py', L, *all_names, quiet=True)
    print(out[out.index('엔진별 합계'):] if '엔진별 합계' in out else out)


def cmd_transcript(path, names):
    rows = pick(read_calls(path), names)
    env = None
    for r in rows:
        print(f"===== {r['name']} ({r['engine']}, 대본 {r['script']})")
        if r['engine'] == 'vapi':
            env = env or load_env()
            c = get(f"https://api.vapi.ai/call/{r['call_id']}", env['VAPI_API_KEY'])
            for m in (c.get('artifact') or {}).get('messages') or []:
                if m.get('role') in ('user', 'bot'):
                    print(f"  {m.get('secondsFromStart', 0):6.1f} {'AI ' if m['role'] == 'bot' else '사람'} {m.get('message', '')}")
        else:
            p = OUT / f"{r['name']}_rows.json"
            if not p.exists():
                sys.exit(f"{r['name']}: 분석 결과가 없습니다. 먼저 analyze를 실행하세요.")
            for x in json.load(open(p, encoding='utf-8')):
                print(f"  {x['start']:6.1f} {x['who']:2s} {x['text']}")


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    cmd, path, names = sys.argv[1], Path(sys.argv[2]), sys.argv[3:]
    if not path.exists():
        sys.exit(f'통화 목록 {path}가 없습니다.')
    if cmd == 'run':
        cmd_fetch(path, names)
        cmd_analyze(path, names)
        cmd_report(path, names)
    elif cmd in ('fetch', 'analyze', 'fix', 'report', 'transcript'):
        globals()[f'cmd_{cmd}'](path, names)
    else:
        sys.exit(__doc__)


if __name__ == '__main__':
    main()
