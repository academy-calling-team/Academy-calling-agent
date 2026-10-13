"""one_call.py 결과(<name>_rows.json)의 화자를 대본과 AI 말투로 다시 정한다.

10/13 통화는 목소리 임베딩만으로는 사람/AI가 잘 안 갈려서(D는 거의 전부 AI로 잡힘),
1) AI만 쓰는 말투가 있으면 AI, 2) 대본의 사람 대사와 비슷하면 사람,
3) 통화 1의 사람 목소리와 유사도(human_sim)로 정하고, 4) 애매하면 '?'로 표시해 사람이 확인한다.
원래 판정은 who_emb, 근거는 why에 남긴다.

사용: relabel.py <results 폴더> <이름> <대본 A~H> [--fix 시작초=사람|AI ...]
"""
import json
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

COMMON = ['네 ○○수학학원입니다', '네 수학학원입니다', '네 여보세요', '여보세요', '네 맞아요', '네 맞습니다', '네 들어가세요', '네', '네네']
SCRIPT = {
    'A': ['네 괜찮아요', '네 지금 두 자리 남아 있어요', '화요일이랑 목요일 저녁 일곱 시부터 아홉 시까지예요',
          '네 가능해요 수요일 오후 세 시나 금요일 오후 네 시요'],
    'B': ['혹시 AI예요', '네 괜찮아요', '한 자리 남았어요', '월수금 여섯 시 반부터 여덟 시 반이요', '목요일 두 시에 오시면 돼요'],
    'C': ['세 자리 있어요', '아 아니요 두 자리예요', '화목 일곱 시요', '금요일 오전 열한 시 괜찮아요'],
    'D': ['네 말씀하세요', '지금은 마감이라 대기 등록만 돼요', '토요일 오전 열 시부터 한 시까지요', '네 화요일 오후 다섯 시에 오세요'],
    'E': ['그건 원장님이 아셔서 제가 잘 모르겠어요', '수요일이랑 금요일 저녁 여덟 시요', '상담은 원장님 일정이라 확인해 봐야 해요'],
    'H': ['네 괜찮아요', '네 지금', '두 자리 남아 있어요', '화요일이랑', '목요일 저녁 일곱 시부터 아홉 시까지요', '음',
          '수요일 오후 세 시나 금요일 오후 네 시요', '네네 화목 저녁 일곱 시부터 아홉 시요', '아 잠깐만요 금요일 말고 목요일 네 시예요'],
}
AI_CUES = ['AI상', '상담원', '녹음', '괜찮으실까요', '감사합니다', '맞을까요', '맞으신가요', '말씀이죠', '말씀이시죠', '어떻게되',
           '알려주', '알려 주', '확인이필요', '정리하면', '지금까지', '전해', '좋은하루', '있을까요', '가능한지', '가능하신가요', '될까요',
           '이해했습니다', '두겠습니다', '알겠습니다', '마지막으로', '그럼', '그러면', '부탁드', '여쭤', '궁금', '있는지', '학부모님', '학부님',
           '대신해', '대신에', '문의드', '되시나요', '맞으시면']


def norm(t):
    return re.sub(r'[^0-9A-Za-z가-힣]', '', t)


def main():
    out, name, script = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
    fixes = {}
    if '--fix' in sys.argv:
        for f in sys.argv[sys.argv.index('--fix') + 1:]:
            k, v = f.split('=')
            fixes[round(float(k), 2)] = v
    p = out / f'{name}_rows.json'
    rows = json.load(open(p, encoding='utf-8'))
    lines = [norm(x) for x in COMMON + SCRIPT[script]]
    for r in rows:
        r.setdefault('who_emb', r['who'])
        t = norm(r['text'])
        hs = r.get('human_sim')
        best = max((SequenceMatcher(None, t, l).ratio() for l in lines), default=0) if t else 0
        if round(r['start'], 2) in fixes:
            who, why = fixes[round(r['start'], 2)], '직접 확인'
        elif any(norm(c) in t for c in AI_CUES):
            who, why = 'AI', 'AI 말투'
        elif best >= 0.6:
            who, why = '사람', f'대본 {best:.2f}'
        elif hs is not None and hs >= 0.25:
            who, why = '사람', f'목소리 {hs}'
        elif hs is not None and hs < 0.15:
            who, why = 'AI', f'목소리 {hs}'
        else:
            who, why = '?', f'애매 (대본 {best:.2f}, 목소리 {hs})'
        r['who'], r['why'] = who, why
    json.dump(rows, open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    changed = sum(r['who'] != r['who_emb'] for r in rows)
    print(f'== {name} ({script}) 구간 {len(rows)}개, 처음 판정과 다른 것 {changed}개, 애매 {sum(r["who"] == "?" for r in rows)}개')
    for r in rows:
        mark = '*' if r['who'] != r['who_emb'] else ' '
        print(f"{mark}{r['start']:7.2f}-{r['end']:7.2f} {r['who']:2s} [{r['why']}] {r['text'][:60]}")


if __name__ == '__main__':
    main()
