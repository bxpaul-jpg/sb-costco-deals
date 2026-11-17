#!/usr/bin/env python3
"""SB 코스트코 행사 웹앱 빌드: 원본 데이터를 접속 코드로 암호화해 docs/data.enc.json 으로 만든다.

사용법:
  python3 tools/build.py --private <비공개 폴더>
비공개 폴더 구성 (절대 저장소에 올리지 말 것):
  deals.json   {rows:[...]}  행사 상품 (주차별 누적)
  images.json  {rows:[{item_no,img}]}  상품 사진 (선택)
  access.json  [{"name":"홍길동","code":"원하는코드"}, ...]  접속 허용 명단
코드를 빼거나 바꾸면 다음 빌드부터 그 코드로는 열리지 않는다 (매번 새 데이터 키 사용).
"""
import argparse, base64, json, os, sys, datetime
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

ITER = 250_000
b64 = lambda b: base64.b64encode(b).decode()

def kek(code, salt):
    return PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=ITER).derive(code.strip().encode())

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--private', required=True)
    ap.add_argument('--out', default=os.path.join(os.path.dirname(__file__), '..', 'docs', 'data.enc.json'))
    a = ap.parse_args()
    load = lambda n: json.load(open(os.path.join(a.private, n), encoding='utf-8'))
    deals = load('deals.json')
    images = load('images.json') if os.path.exists(os.path.join(a.private, 'images.json')) else {'rows': []}
    access = load('access.json')
    codes = [p['code'] for p in access if p.get('code', '').strip()]
    if not codes: sys.exit('access.json 에 코드가 없습니다')
    if len(set(c.strip() for c in codes)) != len(codes): sys.exit('같은 코드가 두 번 있습니다')
    payload = json.dumps({'deals': deals.get('rows', deals), 'images': images.get('rows', images),
                          'built_at': datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')},
                         ensure_ascii=False, separators=(',', ':')).encode()
    dk = AESGCM.generate_key(bit_length=256)
    iv = os.urandom(12)
    ct = AESGCM(dk).encrypt(iv, payload, None)
    slots = []
    for c in codes:
        salt, kiv = os.urandom(16), os.urandom(12)
        slots.append({'s': b64(salt), 'i': b64(kiv), 'k': b64(AESGCM(kek(c, salt)).encrypt(kiv, dk, None))})
    os.urandom(1)
    import random; random.shuffle(slots)
    out = {'v': 1, 'iter': ITER, 'slots': slots, 'iv': b64(iv), 'ct': b64(ct)}
    json.dump(out, open(a.out, 'w'), separators=(',', ':'))
    print(f'완료: 상품 {len(out and json.loads(payload)["deals"])}행, 사진 {len(json.loads(payload)["images"])}개, 접속 코드 {len(slots)}개 → {os.path.normpath(a.out)}')

if __name__ == '__main__':
    main()
