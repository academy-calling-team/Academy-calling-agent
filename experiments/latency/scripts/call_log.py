"""시험 통화를 정해진 순서로 걸고 callId를 통화 목록 CSV에 바로 적는다 (11/2 측정용).

대본 A~E와 H를 두 엔진에 한 번씩, 총 12통 건다. 먼저 거는 엔진은 대본마다 바꾼다.
받을 번호는 입력이 보이지 않는 프롬프트로 받고, 저장하거나 출력하지 않는다.
중간에 멈춰도 다시 실행하면 callId가 없는 통화부터 이어서 건다.

  python scripts/call_log.py          실제 발신 (ClawOps 발신 시간 차감, Vapi 크레딧 차감)
  python scripts/call_log.py --dry    발신 없이 순서와 대본만 확인
"""
import csv
import getpass
import re
import sys
import time
from pathlib import Path

L = Path(__file__).resolve().parents[1]          # experiments/latency
sys.path.insert(0, str(L.parents[1] / 'voice' / 'engines'))
from setup_test_agents import CLAWOPS, SETTINGS, VAPI, dig, load_env, request  # noqa: E402

DATE = '1102'
CSV_PATH = L / 'data' / f'calls_{DATE}.csv'
NOTES = L / 'data' / f'calls_{DATE}_notes.txt'
COLUMNS = ['name', 'engine', 'script', 'call_id', 'leg_id', 'latency', 'fix']
ORDER = [('A', 'clawops'), ('A', 'vapi'), ('B', 'vapi'), ('B', 'clawops'), ('C', 'clawops'), ('C', 'vapi'),
         ('D', 'vapi'), ('D', 'clawops'), ('E', 'clawops'), ('E', 'vapi'), ('H', 'vapi'), ('H', 'clawops')]
TAG = {'clawops': 'co', 'vapi': 'va'}

# voice/prompts/test_script_v3.md의 대본
LINES = {
    'A': ['네, 괜찮아요.', '네, 지금 두 자리 남아 있어요.', '화요일이랑 목요일 저녁 일곱 시부터 아홉 시까지예요.',
          '네, 가능해요. 수요일 오후 세 시나 금요일 오후 네 시요.'],
    'B': ['혹시 AI예요? → AI가 답하면 "네, 괜찮아요."', '한 자리 남았어요.', '월수금 여섯 시 반부터 여덟 시 반이요.',
          '목요일 두 시에 오시면 돼요.'],
    'C': ['네.', '세 자리 있어요. → AI가 되짚으면 "아, 아니요. 두 자리예요."', '화목 일곱 시요.', '금요일 오전 열한 시 괜찮아요.'],
    'D': ['네, 말씀하세요.', '지금은 마감이라 대기 등록만 돼요.', '토요일 오전 열 시부터 한 시까지요.', '네, 화요일 오후 다섯 시에 오세요.'],
    'E': ['네.', '그건 원장님이 아셔서 제가 잘 모르겠어요.', '수요일이랑 금요일 저녁 여덟 시요.', '상담은 원장님 일정이라 확인해 봐야 해요.'],
    'H': ['네, 괜찮아요.', '네, 지금… (속으로 하나 세고) 두 자리 남아 있어요.', '화요일이랑… (3초 세고) 목요일, 저녁 일곱 시부터 아홉 시까지요.',
          '음… (하나, 둘 세고) 수요일 오후 세 시나 금요일 오후 네 시요.'],
}


def read_rows():
    if not CSV_PATH.exists():
        rows = [{'name': f'{DATE}_{TAG[e]}_{s}', 'engine': e, 'script': s, 'call_id': '', 'leg_id': '',
                 'latency': '0' if s == 'H' else '1', 'fix': ''} for s, e in ORDER]
        write_rows(rows)
        return rows
    with open(CSV_PATH, encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def write_rows(rows):
    with open(CSV_PATH, 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)


def place(env, engine, to):
    """발신하고 callId를 돌려준다. 실패하면 None. 오류 내용에서 받는 번호를 가린다."""
    if engine == 'vapi':
        body = {'name': f"시험 {SETTINGS['name']}", 'assistantId': env['VAPI_ASSISTANT_ID'],
                'phoneNumberId': env['VAPI_PHONE_NUMBER_ID'],
                'customer': {'number': to, 'numberE164CheckEnabled': False}}
        st, r = request('POST', f'{VAPI}/call', env['VAPI_API_KEY'], env, body)
        cid = r.get('id') if isinstance(r, dict) else None
    else:
        base = CLAWOPS.format(acc=env['CLAWOPS_ACCOUNT_ID'])
        body = {'To': to, 'From': env['CLAWOPS_FROM_NUMBER'], 'AgentId': env['CLAWOPS_AGENT_ID'], 'Timeout': 30}
        st, r = request('POST', f'{base}/calls', env['CLAWOPS_API_KEY'], env, body)
        cid = (r.get('callId') or r.get('sid') or r.get('id')) if isinstance(r, dict) else None
    if st >= 300 or not cid:
        msg = str(r).replace(to, '***').replace(env.get('CLAWOPS_FROM_NUMBER') or '***', '***')
        print(f'  발신 실패 {st}: {msg[:300]}')
        return None
    return cid


def result(env, engine, cid):
    """통화 상태와 길이만 보여 준다. 응답의 번호와 주소는 출력하지 않는다."""
    if engine == 'vapi':
        st, r = request('GET', f'{VAPI}/call/{cid}', env['VAPI_API_KEY'], env)
        return f"{r.get('status')} / {r.get('endedReason')} / 녹음 {'있음' if dig(r, 'artifact', 'recordingUrl') else '없음'}" if st == 200 else f'조회 실패 {st}'
    base = CLAWOPS.format(acc=env['CLAWOPS_ACCOUNT_ID'])
    st, r = request('GET', f'{base}/calls/{cid}', env['CLAWOPS_API_KEY'], env)
    return f"{r.get('status')} / {r.get('duration')}초" if st == 200 else f'조회 실패 {st}'


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    dry = '--dry' in sys.argv
    rows = read_rows()
    todo = [r for r in rows if not r['call_id']]
    print(f'전체 {len(rows)}통 중 남은 통화 {len(todo)}통' + (' (발신 안 함)' if dry else ''))
    env, to = load_env(), ''
    if not dry and todo:
        to = getpass.getpass('받을 휴대폰 번호(화면에 보이지 않음): ').replace('-', '').replace(' ', '')
        if not re.fullmatch(r'01\d{8,9}', to):
            sys.exit('받을 번호는 01012345678 형식으로 넣으세요.')
    for i, r in enumerate(todo, 1):
        print(f"\n===== {i}/{len(todo)}  {r['name']}  엔진 {r['engine']}  대본 {r['script']}")
        print('받자마자: 네, ○○수학학원입니다.')
        for n, line in enumerate(LINES[r['script']]):
            print(f"  {'첫인사 뒤' if n == 0 else f'질문 {n}'}: {line}")
        print('되짚으면: 네, 맞아요. / AI 말이 끝난 뒤 답함 / 마지막: 네, 들어가세요.')
        if input('Enter=발신, q=그만: ').strip().lower() == 'q':
            break
        if dry:
            continue
        cid = place(env, r['engine'], to)
        if not cid:
            sys.exit('멈췄습니다. 원인을 고친 뒤 다시 실행하면 이 통화부터 이어집니다.')
        r['call_id'] = cid
        write_rows(rows)
        print(f'  callId {cid} 저장. 전화를 받으세요.')
        note = input('통화가 끝나면 Enter (메모를 적어도 됨, r=이 통화 다시 걸기, q=여기서 멈춤): ').strip()
        time.sleep(3)
        print('  결과:', result(env, r['engine'], cid))
        with open(NOTES, 'a', encoding='utf-8') as f:
            f.write(f"{r['name']}\t{cid}\t{note}\n")
        if note.lower() == 'r':
            r['call_id'] = ''
            write_rows(rows)
            sys.exit('이 통화를 비웠습니다. 다시 실행하면 이 통화부터 겁니다.')
        if note.lower() == 'q':
            break
    print('\n완료된 통화:', sum(bool(r['call_id']) for r in rows), '/', len(rows))


if __name__ == '__main__':
    main()
