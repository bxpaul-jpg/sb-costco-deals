#!/usr/bin/env python3
"""우리 코스트코 매입 엑셀 → purchases.json (상품코드 기준).
사용법: python3 tools/prep_purchases.py 매입.xlsx <비공개 폴더>/purchases.json
- 상품코드 앞 숫자만 사용(사이즈 접미사 제거), 연회비 제외
- *** CPN 줄은 바로 윗줄 상품에 개당 할인(쿠폰 합계 ÷ 수량)으로 반영
- *** 취소/환불 줄은 같은 상품의 최근 구매 1건 제거
"""
import openpyxl, re, json, sys, collections
src, out = sys.argv[1], sys.argv[2]
# 묶음 단위 보정: <출력 폴더>/pack_factors.json {"상품코드": 묶음 개수}. 매입이 낱개 단가일 때 행사(묶음) 단가로 맞춤
import os
pf_path = os.path.join(os.path.dirname(os.path.abspath(out)), 'pack_factors.json')
PACK = {str(k): v for k, v in json.load(open(pf_path)).items()} if os.path.exists(pf_path) else {}
ws = openpyxl.load_workbook(src, data_only=True).active
rows = list(ws.iter_rows(min_row=2, values_only=True))
def base(c):
    m = re.match(r'\s*(\d+)', str(c)) if c is not None else None
    return m.group(1) if m else None
def date(s):
    m = re.match(r'(\d{1,2})[-/.](\d{1,2})', str(s or ''))
    return f'2026-{int(m.group(1)):02d}-{int(m.group(2)):02d}' if m else None
buys = []; stats = collections.Counter()
for i, r in enumerate(rows):
    d, tgt, f, nm_clean, nm, code, unit, qty = r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7]
    if not isinstance(unit, (int, float)) or not code: stats['skip_empty'] += 1; continue
    raw = str(nm or '')
    if '연회비' in raw or '업그레이드' in raw: stats['skip_membership'] += 1; continue
    if raw.startswith('***'):
        if 'CPN' in raw:
            # 쿠폰: 바로 윗줄 상품 구매에 반영. 개당 할인 = 쿠폰 금액 합계 ÷ 그 상품 수량
            prev = buys[-1] if buys and buys[-1]['_i'] == i - 1 else None
            if prev is None: stats['coupon_unmatched'] += 1; continue
            total = r[8] if isinstance(r[8], (int, float)) else unit * (qty if isinstance(qty, (int, float)) else 1)
            per = round(total / prev['qty']) if prev['qty'] else unit
            prev['coupon'] = -per; prev['eff'] = prev['unit'] + per; stats['coupon'] += 1
        else:
            # 취소·환불: 같은 상품번호의 가장 최근 구매 1건 제거
            bc = base(code)
            for j in range(len(buys) - 1, -1, -1):
                if buys[j]['code'] == bc: buys.pop(j); stats['cancel'] += 1; break
            else: stats['cancel_unmatched'] += 1
        continue
    if unit <= 0: stats['skip_nonpos'] += 1; continue
    f_ = PACK.get(base(code), 1)
    if f_ != 1:
        unit = unit * f_; qty = (qty / f_) if isinstance(qty, (int, float)) else qty; stats['pack_adjusted'] += 1
    buys.append({'code': base(code), 'raw_code': str(code), 'date': date(d), 'name': nm_clean or nm, 'unit': int(round(unit)), 'eff': int(round(unit)),
                 'qty': qty if isinstance(qty, (int, float)) else 1, 'target': tgt == '대상', '_f': f, '_i': i})
by = collections.defaultdict(list)
for b in buys: by[b['code']].append(b)
outp = []
for code, bs in by.items():
    bs.sort(key=lambda b: (b['date'] or '', b['_i']))
    last = bs[-1]; tq = sum(b['qty'] for b in bs)
    outp.append({'item_no': code, 'name': last['name'], 'count': len(bs), 'qty': tq,
                 'last_eff': last['eff'], 'last_unit': last['unit'], 'last_date': last['date'],
                 'avg_eff': round(sum(b['eff'] * b['qty'] for b in bs) / tq) if tq else None,
                 'min_eff': min(b['eff'] for b in bs), 'target': any(b['target'] for b in bs),
                 'hist': [{'d': b['date'], 'u': b['unit'], 'e': b['eff'], 'q': b['qty']} for b in bs][-12:]})
json.dump({'rows': outp, 'meta': {'source': '코스트코 판가정리.xlsx', 'purchases': len(buys), 'items': len(outp)}}, open(out, 'w'), ensure_ascii=False)
print(dict(stats), 'purchases', len(buys), 'items', len(outp))
