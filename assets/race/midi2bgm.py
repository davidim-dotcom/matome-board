"""ラン BGM: 운영자가 준 8비트 MIDI(assets/race/src/bgm_run.mid)를 index.html 의 `const RUN_MIDI=…` 한 줄로 바꾼다.
   python3 assets/race/midi2bgm.py            → 그 줄을 출력
   python3 assets/race/midi2bgm.py --write    → index.html 의 RUN_MIDI 줄을 바꿔 씀
   표준 라이브러리만 쓴다. 16분음표 격자로 반올림하고, 트랙(채널) 순서대로 m(리드)·h(화음)·a(아르페지오)·b(베이스)·d(드럼, ch10)에 넣는다.
   음 하나 = 3글자(앞 음과의 칸 차이·길이(칸)·음높이-pb(가장 낮은 음))를 64글자 알파벳으로. 칸 차이가 63을 넘으면 길이 0인 쉼 토큰을 끼운다."""
import json, re, struct, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / 'assets/race/src/bgm_run.mid'
A64 = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'
LOOP_MARK = 2          # 두 번째 마커(스타트 리프)부터 되풀이. 앞은 처음 한 번만 나오는 인트로 팡파레

def vlq(b, i):
    v = 0
    while True:
        c = b[i]; i += 1; v = (v << 7) | (c & 127)
        if c < 128: return v, i

def parse(path):
    b = path.read_bytes()
    assert b[:4] == b'MThd'
    _, nt, div = struct.unpack('>HHH', b[8:14]); i = 14
    tempos, marks, notes = [], [], []
    for _ in range(nt):
        assert b[i:i + 4] == b'MTrk'
        ln = struct.unpack('>I', b[i + 4:i + 8])[0]; j = i + 8; end = j + ln; i = end
        t = 0; run = None; on = {}
        while j < end:
            d, j = vlq(b, j); t += d; s = b[j]
            if s == 0xFF:
                ty = b[j + 1]; l, k = vlq(b, j + 2); data = b[k:k + l]; j = k + l
                if ty == 0x51: tempos.append((t, 60e6 / int.from_bytes(data, 'big')))
                elif ty == 6: marks.append((t, data.decode('utf-8', 'replace')))
                continue
            if s in (0xF0, 0xF7):
                l, k = vlq(b, j + 1); j = k + l; continue
            if s & 0x80: run = s; j += 1
            st, ch = run >> 4, run & 15
            if st in (0xC, 0xD): j += 1; continue
            p, v = b[j], b[j + 1]; j += 2
            if st == 9 and v > 0: on[(ch, p)] = t
            elif st == 8 or st == 9:
                if (ch, p) in on: t0 = on.pop((ch, p)); notes.append((ch, t0, t - t0, p))
    return div, tempos, marks, notes

def enc(v):
    assert 0 <= v < 64, v
    return A64[v]

def build():
    div, tempos, marks, notes = parse(SRC)
    q = div // 4                                   # 16분음표 한 칸의 틱
    chans = sorted({n[0] for n in notes if n[0] != 9})
    lane = dict(zip(chans, 'mhab'))
    lane[9] = 'd'
    out = {k: [] for k in 'mhabd'}
    for ch, t0, dur, p in notes:
        if ch in lane: out[lane[ch]].append((round(t0 / q), max(1, round(dur / q)), p))
    length = max(s + 1 for v in out.values() for s, _, _ in v)
    length = -(-length // 16) * 16                 # 마디 끝까지
    pb = min(n[2] for v in out.values() for n in v)
    tr = {}
    for k, v in out.items():
        v.sort(); s, prev = '', 0
        for st, ln, p in v:
            d = st - prev
            while d > 63: s += enc(63) + enc(0) + enc(0); d -= 63
            s += enc(d) + enc(min(63, ln)) + enc(p - pb); prev = st
        tr[k] = s
    tempo = [[round(t / q), round(b, 1)] for t, b in tempos]
    loop = round(sorted(marks)[LOOP_MARK - 1][0] / q) if len(marks) >= LOOP_MARK else 0
    return {'tempo': tempo, 'loop': loop, 'len': length, 'pb': pb, 'tr': tr}

def line():
    return 'const RUN_MIDI=' + json.dumps(build(), separators=(',', ':')) + '; // assets/race/midi2bgm.py 가 src/bgm_run.mid 에서 만든 줄(손으로 고치지 말 것)'

if __name__ == '__main__':
    L = line()
    if '--write' in sys.argv:
        f = ROOT / 'index.html'; s = f.read_text()
        s2, n = re.subn(r'^const RUN_MIDI=.*$', lambda m: L, s, flags=re.M)
        assert n == 1, 'index.html 에 RUN_MIDI 줄이 하나 있어야 함'
        f.write_text(s2); print('index.html: RUN_MIDI', len(L), '자')
    else:
        print(L)
