"""11/11 응답 지연 시험: 프롬프트 길이와 말하는 모델이 지연을 줄이는지 본다 (ClawOps만).

세 묶음을 같은 밤에 섞어서 건다. 날짜가 다르면 같은 설정도 중앙값이 0.16초 달랐기 때문이다(10/13 1.57초 → 11/2 1.73초).
  L (기준)  지금 시험 에이전트(CLAWOPS_AGENT_ID): 프롬프트 v3, gpt-live-1 + gpt-5.6-luna, 추론 none, 음성 marin
  S (짧게)  프롬프트만 agent_prompt_v3_short.txt(약 절반)로 바꾼 새 에이전트
  M (모델)  프롬프트 v3, 말하는 모델만 gpt-realtime-2.1-mini(realtime_voice, vad·session은 기본값)로 바꾼 새 에이전트
대본 A~E·H마다 세 묶음을 한 번씩, 거는 순서를 대본마다 바꿔 18통. H는 지연 통계에서 빼고 끼어들기만 본다.

저장소 맨 위에서 실행한다. 키와 받는 번호는 출력하지 않는다.
  python experiments/latency/scripts/variants_1111.py plan      보낼 설정과 거는 순서만 출력 (아무것도 만들지 않음. 묶음이 보이니 측정 전에는 보지 않음)
  python experiments/latency/scripts/variants_1111.py create    S·M 에이전트를 만들고 ID를 voice/.env에 저장 (CLAWOPS_AGENT_ID_S, _M)
  python experiments/latency/scripts/variants_1111.py show      세 에이전트 설정을 다시 읽어 비교 (읽기만)
  python experiments/latency/scripts/variants_1111.py call      섞은 순서로 발신. 화면에는 측정 번호와 대본만 나옴 (--dry: 발신 안 함)
  python experiments/latency/scripts/variants_1111.py blind     measure.py fetch·analyze 뒤에 실행. 묶음을 가린 측정용 사본을 만듦
  python experiments/latency/scripts/variants_1111.py report    묶음별 자동 지연 보고서 (직접 측정이 끝난 뒤에 볼 것)

통화 이름은 measure.py 규칙(<날짜>_co_<대본>)에 묶음을 붙인 1111_co_A_L 형식이다.

묶음 가리기: 김규림이 지연을 직접 재므로, 어느 묶음인지 모른 채 재도록 한다.
- 대본 안의 거는 순서도 무작위로 정해 data/calls_1111_order.json에만 둔다.
- 통화마다 무작위 '측정 번호'(01~18)를 붙이고, 대응표는 data/calls_1111_key.csv에만 둔다. 측정이 끝날 때까지 열지 않는다.
- 통화 화면과 메모 파일에는 측정 번호와 대본만 나온다. data/calls_1111.csv에는 묶음이 들어 있으니 측정 중에는 열지 않는다.
- 측정용 사본은 바탕화면 Call/1111_측정용/<번호>_<대본>.wav와 같은 이름의 _rows.json이다.
- 목소리나 말투로 묶음을 짐작할 수는 있다(M은 다른 모델). 완전히 가릴 수 없다는 한계는 결과에 적는다.
"""
import csv
import getpass
import json
import random
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

L = Path(__file__).resolve().parents[1]          # experiments/latency
ROOT = L.parents[1]
sys.path.insert(0, str(ROOT / 'voice' / 'engines'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from call_log import LINES  # noqa: E402  (11/2와 같은 대본)
from setup_test_agents import CLAWOPS, SETTINGS, clawops_body, load_env, request, save_env  # noqa: E402

DATE = '1111'
CSV_PATH = L / 'data' / f'calls_{DATE}.csv'
NOTES = L / 'data' / f'calls_{DATE}_notes.txt'          # 통화 중 메모 (측정 번호·대본만)
KEY_PATH = L / 'data' / f'calls_{DATE}_key.csv'          # 이름 ↔ 측정 번호. 측정이 끝날 때까지 열지 않음
BLIND_DIR = Path.home() / 'Desktop' / 'Call' / f'{DATE}_측정용'
COLUMNS = ['name', 'engine', 'script', 'call_id', 'leg_id', 'latency', 'fix']   # measure.py와 같은 열
PROMPT_V3 = ROOT / 'voice' / 'prompts' / 'agent_prompt_v3.txt'
PROMPT_SHORT = ROOT / 'voice' / 'prompts' / 'agent_prompt_v3_short.txt'

VARIANTS = {
    'L': {'env': 'CLAWOPS_AGENT_ID', 'desc': '기준: v3 프롬프트, gpt-live-1'},
    'S': {'env': 'CLAWOPS_AGENT_ID_S', 'desc': '짧은 프롬프트, gpt-live-1'},
    'M': {'env': 'CLAWOPS_AGENT_ID_M', 'desc': 'v3 프롬프트, gpt-realtime-2.1-mini'},
}
# 대본마다 거는 순서의 틀. 여섯 가지 순열을 한 번씩 써서 각 묶음이 첫째·둘째·셋째에 두 번씩 온다.
# 실제 순서는 x·y·z에 L·S·M을 무작위로 붙여 정하고 ORDER_PATH에만 저장한다(측정하는 사람이 순서로 묶음을 짐작하지 못하게)
PATTERN = {'A': 'xyz', 'B': 'yzx', 'C': 'zxy', 'D': 'xzy', 'E': 'zyx', 'H': 'yxz'}
ORDER_PATH = L / 'data' / f'calls_{DATE}_order.json'


def order() -> dict:
    if not ORDER_PATH.exists():
        m = dict(zip('xyz', random.SystemRandom().sample('LSM', 3)))
        ORDER_PATH.write_text(json.dumps({s: ''.join(m[c] for c in pat) for s, pat in PATTERN.items()}), encoding='utf-8')
    return json.loads(ORDER_PATH.read_text(encoding='utf-8'))


def body_s():
    b = clawops_body(PROMPT_SHORT.read_text(encoding='utf-8').strip())
    b['name'] = '시험 S 짧은 프롬프트 GPT-Live luna none marin'
    return b


def body_m():
    return {
        'name': '시험 M realtime-2.1-mini marin',
        'instructions': PROMPT_V3.read_text(encoding='utf-8').strip(),
        'greeting': SETTINGS['ai_speaks_first'],
        'configuration': {
            # vad·session을 넣지 않으면 기본값. ClawOps 답변(10/14): vad를 끄면 realtime 모델 서버가 말 끝을 판단하고 이 구성이 가장 빠름
            'outputMode': 'realtime_voice',
            'language': SETTINGS['language'],
            'knowledge': {'enabled': False, 'topK': 3},
            'llm': {'provider': 'openai-realtime', 'model': 'gpt-realtime-2.1-mini', 'voice': SETTINGS['voice']},
        },
    }


BODIES = {'S': body_s, 'M': body_m}


def base(env):
    return CLAWOPS.format(acc=env['CLAWOPS_ACCOUNT_ID'])


def short(body):
    """프롬프트 본문 대신 길이만 보여 준다."""
    b = json.loads(json.dumps(body))
    b['instructions'] = f"<프롬프트 {len(body['instructions'].encode('utf-8'))}바이트>"
    return b


def cmd_plan():
    for k in ('S', 'M'):
        print(f'[{k}] POST /agents\n' + json.dumps(short(BODIES[k]()), ensure_ascii=False, indent=1))
    print('\n거는 순서 (묶음이 보이므로 측정이 끝나기 전에는 보지 않음):')
    for i, r in enumerate(rows_template(), 1):
        print(f"  {i:2}. {r['name']}  ({VARIANTS[r['name'][-1]]['desc']})")


def cmd_create():
    env = load_env()
    for k in ('S', 'M'):
        name = VARIANTS[k]['env']
        if env.get(name):
            print(f'{k}: 이미 있음 ({name}). 건너뜀')
            continue
        st, r = request('POST', f'{base(env)}/agents', env['CLAWOPS_API_KEY'], env, BODIES[k]())
        if st >= 300 or not isinstance(r, dict) or not r.get('agentId'):
            sys.exit(f'{k} 생성 실패 {st}: {str(r)[:500]}')
        save_env(name, r['agentId'])
        print(f'{k}: 생성 {st} → {r["agentId"]} (voice/.env의 {name})')
    cmd_show()


def cmd_show():
    env = load_env()
    for k, v in VARIANTS.items():
        aid = env.get(v['env'])
        if not aid:
            print(f'{k}: 없음 ({v["env"]})')
            continue
        st, r = request('GET', f'{base(env)}/agents/{aid}', env['CLAWOPS_API_KEY'], env)
        if st != 200:
            print(f'{k}: 조회 실패 {st}')
            continue
        cfg = r.get('configuration') or {}
        llm = cfg.get('llm') or {}
        prompt = r.get('instructions') or ''
        print(f"{k}: {r.get('name')} | mode {cfg.get('outputMode')} | {llm.get('model')} {llm.get('backend_model') or ''}"
              f" {llm.get('backend_reasoning_effort') or ''} | 음성 {llm.get('voice')} | vad {cfg.get('vad')} | session {cfg.get('session')}"
              f" | 프롬프트 {len(prompt.encode('utf-8'))}바이트")


def rows_template():
    return [{'name': f'{DATE}_co_{s}_{v}', 'engine': 'clawops', 'script': s, 'call_id': '', 'leg_id': '',
             'latency': '0' if s == 'H' else '1', 'fix': ''} for s, seq in order().items() for v in seq]


def read_key() -> dict:
    """이름 → 측정 번호. 없으면 무작위로 만들어 저장한다(화면에 출력하지 않음)."""
    if not KEY_PATH.exists():
        names = [r['name'] for r in rows_template()]
        nums = random.SystemRandom().sample(range(1, len(names) + 1), len(names))
        with open(KEY_PATH, 'w', encoding='utf-8', newline='') as f:
            w = csv.writer(f)
            w.writerow(['name', 'blind'])
            w.writerows((n, f'{b:02d}') for n, b in zip(names, nums))
    with open(KEY_PATH, encoding='utf-8-sig', newline='') as f:
        return {r['name']: r['blind'] for r in csv.DictReader(f)}


def read_rows():
    if not CSV_PATH.exists():
        write_rows(rows_template())
    with open(CSV_PATH, encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def write_rows(rows):
    with open(CSV_PATH, 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)


def place(env, agent_id, to):
    body = {'To': to, 'From': env['CLAWOPS_FROM_NUMBER'], 'AgentId': agent_id, 'Timeout': 30}
    st, r = request('POST', f'{base(env)}/calls', env['CLAWOPS_API_KEY'], env, body)
    cid = (r.get('callId') or r.get('sid') or r.get('id')) if isinstance(r, dict) else None
    if st >= 300 or not cid:
        msg = str(r).replace(to, '***').replace(env.get('CLAWOPS_FROM_NUMBER') or '***', '***')
        print(f'  발신 실패 {st}: {msg[:300]}')
        return None
    return cid


def memo(b, script, text):
    """메모를 줄마다 바로 저장한다(중간에 창이 닫혀도 남음). 측정 번호와 대본만 적는다."""
    with open(NOTES, 'a', encoding='utf-8') as f:
        f.write(f"{b}\t대본 {script}\t{time.strftime('%H:%M:%S')}\t{text}\n")


def cmd_call(dry):
    rows = read_rows()
    key = read_key()
    todo = [r for r in rows if not r['call_id']]
    print(f'전체 {len(rows)}통 중 남은 통화 {len(todo)}통' + (' (발신 안 함)' if dry else ''))
    env, to = load_env(), ''
    missing = [v['env'] for v in VARIANTS.values() if not env.get(v['env'])]
    if missing and not dry:
        sys.exit(f'에이전트 ID 없음: {", ".join(missing)}. 먼저 create를 실행하세요.')
    if not dry and todo:
        to = getpass.getpass('받을 휴대폰 번호(화면에 보이지 않음): ').replace('-', '').replace(' ', '')
        if not re.fullmatch(r'01\d{8,9}', to):
            sys.exit('받을 번호는 01012345678 형식으로 넣으세요.')
    already = len(rows) - len(todo)
    for i, r in enumerate(todo, 1):
        v, b = r['name'][-1], key[r['name']]
        print(f"\n===== 통화 {already + i}/{len(rows)}  ·  측정 번호 {b}  ·  대본 {r['script']}")
        print('받자마자: 네, ○○수학학원입니다.')
        for n, line in enumerate(LINES[r['script']]):
            print(f"  {'첫인사 뒤' if n == 0 else f'질문 {n}'}: {line}")
        print('되짚으면: 네, 맞아요. / AI 말이 끝난 뒤 답함 / 마지막: 네, 들어가세요.')
        if input('Enter=발신, q=그만: ').strip().lower() == 'q':
            break
        if dry:
            continue
        cid = place(env, env[VARIANTS[v]['env']], to)
        if not cid:
            sys.exit('멈췄습니다. 원인을 고친 뒤 다시 실행하면 이 통화부터 이어집니다.')
        r['call_id'] = cid
        write_rows(rows)
        print('  발신했습니다. 전화를 받으세요. (휴대폰 녹음을 쓰면 지금 켜기)')
        print('  특이사항은 한 줄씩 적고 Enter (통화 중에도, 여러 줄 가능).')
        print('  통화가 끝나면 빈 Enter.  r = 이 통화 버리고 다시 걸기,  q = 여기서 멈춤')
        while True:
            line = input(f'  [{b} 메모] ').strip()
            if line.lower() in ('', 'r', 'q'):
                note = line.lower()
                break
            memo(b, r['script'], line)
        time.sleep(3)
        st, c = request('GET', f"{base(env)}/calls/{cid}", env['CLAWOPS_API_KEY'], env)
        print('  결과:', f"{c.get('status')} / {c.get('duration')}초" if st == 200 else f'조회 실패 {st}')
        if note == 'r':
            memo(b, r['script'], '(이 통화 버림. 다시 걸기)')
            r['call_id'] = ''
            write_rows(rows)
            sys.exit('이 통화를 비웠습니다. 다시 실행하면 이 통화부터 겁니다.')
        if note == 'q':
            break
    print('\n완료된 통화:', sum(bool(r['call_id']) for r in rows), '/', len(rows))
    if NOTES.exists():
        print('\n지금까지 메모:\n' + NOTES.read_text(encoding='utf-8'))


def cmd_blind():
    """measure.py fetch·analyze 뒤에 실행. 녹음과 화자 결과를 측정 번호 이름으로 복사하고 측정 메모 양식을 만든다."""
    key, rows = read_key(), [r for r in read_rows() if r['call_id']]
    BLIND_DIR.mkdir(parents=True, exist_ok=True)
    from paths import rec_file
    out, made = L / 'data' / 'results', []
    for r in rows:
        stem = f"{key[r['name']]}_{r['script']}"
        wav = rec_file(f"{r['name']}.wav")
        if not wav.exists():
            wav = rec_file(f"{r['name']}_16k.wav")
        if not wav.exists():
            print(f'{stem}: 녹음 없음. measure.py fetch를 먼저 실행하세요.')
            continue
        shutil.copyfile(wav, BLIND_DIR / f'{stem}.wav')
        rows_json = out / f"{r['name']}_rows.json"
        if rows_json.exists():
            shutil.copyfile(rows_json, BLIND_DIR / f'{stem}_rows.json')
        made.append((key[r['name']], r['script'], r['latency'] == '0'))
    sheet = BLIND_DIR / '측정메모.csv'
    if not sheet.exists():
        with open(sheet, 'w', encoding='utf-8-sig', newline='') as f:
            w = csv.writer(f)
            w.writerow(['측정번호', '대본', '지연 통계', '특이사항'])
            w.writerows((b, s, '제외(H: 끼어들기만 봄)' if h else '포함', '') for b, s, h in sorted(made))
    if NOTES.exists():
        shutil.copyfile(NOTES, BLIND_DIR / '통화중메모.txt')
    print(f'측정용 사본 {len(made)}통 → {BLIND_DIR}')
    print('뷰어(experiments/latency/viewer/latency_viewer.html)에 <번호>_<대본>.wav와 같은 이름의 _rows.json을 함께 끌어다 놓는다.')
    print(f'측정 중 특이사항은 {sheet.name}에 적는다 (CSV UTF-8로 저장). 통화 중 메모는 통화중메모.txt')


def cmd_report():
    """직접 측정이 끝난 뒤에 볼 것. 묶음마다 measure.py report를 따로 돌린다."""
    rows = [r for r in read_rows() if r['call_id']]
    for v, info in VARIANTS.items():
        names = [r['name'] for r in rows if r['name'].endswith(f'_{v}')]
        if names:
            print(f'\n################################ 묶음 {v}: {info["desc"]}')
            subprocess.run([sys.executable, str(L / 'scripts' / 'measure.py'), 'report', str(CSV_PATH), *names])


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'plan'
    {'plan': cmd_plan, 'create': cmd_create, 'show': cmd_show, 'report': cmd_report, 'blind': cmd_blind,
     'call': lambda: cmd_call('--dry' in sys.argv)}.get(cmd, lambda: sys.exit(__doc__))()
