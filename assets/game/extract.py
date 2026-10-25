#!/usr/bin/env python3
"""운영자가 만든 스프라이트 시트(assets/game/src/sheet1.jpg, sheet2.jpg)에서 조각을 잘라낸다.
   python3 assets/game/extract.py scan OUTDIR     → 영역별로 조각을 번호 매겨 contact sheet(PNG)로 뽑아 고르기용
   python3 assets/game/extract.py                 → PICKS 에 적은 조각을 assets/game/*.png 로 저장
배경(어두운 패널 / 체커보드)을 색으로 걸러내고, 바깥에서 이어진 배경만 지운 뒤(안쪽 어두운 선은 유지)
5×5 이웃으로 이어진 덩어리를 한 조각으로 본다. JPEG 라서 가장자리가 조금 번지므로 알파를 이진화한다."""
import sys, os, json
from collections import deque
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, 'src')

# 영역: 이름 → (시트, (x0,y0,x1,y1), 배경 종류)
REGIONS = {
    'p1_player':  ('sheet1.jpg', (8, 30, 466, 470), 'dark'),
    'p1_minions': ('sheet1.jpg', (474, 30, 1028, 248), 'dark'),
    'p1_boss':    ('sheet1.jpg', (474, 282, 1028, 766), 'dark'),
    'p1_shots':   ('sheet1.jpg', (8, 476, 466, 766), 'dark'),
    'p1_fx':      ('sheet1.jpg', (1034, 300, 1406, 600), 'dark'),
    'p1_patterns':('sheet1.jpg', (1034, 30, 1406, 300), 'dark'),
    'p1_lives':   ('sheet1.jpg', (1034, 600, 1406, 766), 'dark'),
    'p2_all':     ('sheet2.jpg', (0, 0, 1408, 768), 'checker'),
}

def bg_colors(arr, kind):
    """배경으로 볼 색 목록. dark: 가장 흔한 색 2개, checker: 중간 회색 중 가장 흔한 2개."""
    q = (arr // 6) * 6
    if kind == 'checker':
        r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
        m = (np.abs(r - g) < 14) & (b - r > 2) & (b - r < 30) & (r > 80) & (r < 150)
        flat = q[m].reshape(-1, 3)
    else:
        flat = q.reshape(-1, 3)
    vals, counts = np.unique(flat, axis=0, return_counts=True)
    order = np.argsort(-counts); return [tuple(int(v) for v in vals[i]) for i in order[:2]]

def flood_bg(bg):
    h, w = bg.shape; out = np.zeros_like(bg); dq = deque()
    for x in range(w):
        for y in (0, h - 1):
            if bg[y, x] and not out[y, x]: out[y, x] = True; dq.append((y, x))
    for y in range(h):
        for x in (0, w - 1):
            if bg[y, x] and not out[y, x]: out[y, x] = True; dq.append((y, x))
    while dq:
        y, x = dq.popleft()
        for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
            if 0 <= ny < h and 0 <= nx < w and bg[ny, nx] and not out[ny, nx]: out[ny, nx] = True; dq.append((ny, nx))
    return out

def foreground(arr, kind, thr):
    bg = np.zeros(arr.shape[:2], bool)
    if kind == 'checker':
        # 체커보드의 두 회색(어두운 (96,102,114)·밝은 (130,136,148) 근처, 푸른빛 회색)
        mx, mn = arr.max(2), arr.min(2)   # 채도 낮은 중간 밝기의 회색(파란 기 조금)만 배경으로
        bg = (mx - mn <= 30) & (mx >= 78) & (mx <= 170) & (arr[..., 2] >= arr[..., 0])
    else:
        for c in bg_colors(arr, kind): bg |= (np.abs(arr - np.array(c)).sum(2) < thr)
    if kind == 'checker':
        # 체커보드 패널(큰 덩어리)을 찾아 패널 안에서만 배경을 지운다(패널 밖 우주 배경은 통째로 지움)
        panel = np.zeros_like(bg); lab, boxes = components(bg, reach=3, min_px=1500)
        keep = np.zeros_like(bg)
        for (x1, y1, x2, y2, n) in boxes:
            sub = bg[y1:y2, x1:x2]; inner = flood_bg(sub); keep[y1:y2, x1:x2] |= ~inner; panel[y1:y2, x1:x2] = True
        return keep & panel
    return ~flood_bg(bg)

def components(fg, reach=2, min_px=12):
    h, w = fg.shape; lab = np.zeros((h, w), np.int32); n = 0; boxes = []
    ys, xs = np.nonzero(fg)
    for y0, x0 in zip(ys, xs):
        if lab[y0, x0]: continue
        n += 1; lab[y0, x0] = n; dq = deque([(y0, x0)]); px = 0; x1 = x2 = x0; y1 = y2 = y0
        while dq:
            y, x = dq.popleft(); px += 1; x1, x2, y1, y2 = min(x1, x), max(x2, x), min(y1, y), max(y2, y)
            for ny in range(max(0, y - reach), min(h, y + reach + 1)):
                for nx in range(max(0, x - reach), min(w, x + reach + 1)):
                    if fg[ny, nx] and not lab[ny, nx]: lab[ny, nx] = n; dq.append((ny, nx))
        if px >= min_px: boxes.append((x1, y1, x2 + 1, y2 + 1, n))
    boxes.sort(key=lambda b: (round(b[1] / 24), b[0]))  # 대충 줄 → 왼쪽 순
    return lab, boxes

def cut(region, thr=None):
    sheet, box, kind = REGIONS[region]; thr = thr or (48 if kind == 'checker' else 70)
    im = Image.open(os.path.join(SRC, sheet)).convert('RGB').crop(box); arr = np.asarray(im).astype(int)
    fg = foreground(arr, kind, thr); lab, boxes = components(fg)
    pieces = []
    for (x1, y1, x2, y2, n) in boxes:
        m = (lab[y1:y2, x1:x2] == n)
        rgba = np.dstack([arr[y1:y2, x1:x2].astype(np.uint8), (m * 255).astype(np.uint8)])
        pieces.append(Image.fromarray(rgba, 'RGBA'))
    return pieces

def scan(outdir):
    os.makedirs(outdir, exist_ok=True)
    for region in REGIONS:
        pieces = cut(region); scale = 2; pad = 6; x = y = 0; rowh = 0; W = 1400; cells = []
        for i, p in enumerate(pieces):
            w, h = p.width * scale + pad, p.height * scale + pad + 10
            if x + w > W: x = 0; y += rowh; rowh = 0
            cells.append((i, x, y, p)); x += w; rowh = max(rowh, h)
        sheet = Image.new('RGBA', (W, y + rowh + 10), (40, 40, 60, 255))
        from PIL import ImageDraw; d = ImageDraw.Draw(sheet)
        for i, x, y, p in cells:
            sheet.alpha_composite(p.resize((p.width * scale, p.height * scale), Image.NEAREST), (x, y + 10)); d.text((x, y), str(i), fill=(255, 255, 0, 255))
        sheet.save(os.path.join(outdir, region + '.png')); print(region, len(pieces), 'pieces')

# 이름 → (영역, 조각 번호[, 조각 안 자르기 (x0,y0,x1,y1) 비율]). scan 결과를 보고 적는다.
PICKS = {
    # 자기: メイドバスター・リリィ (FLYING TILT 줄) + 헬퍼 고양이
    'player': ('p1_player', 19), 'player_l': ('p1_player', 16), 'player_r': ('p1_player', 20), 'cat': ('p1_player', 7),
    # 1스테이지 ミニオン: 말벌·딱정벌레, 중보스 보라 포드, 보스 メイドボット・オーバーロード
    'wasp': ('p1_minions', 0), 'beetle': ('p1_minions', 3), 'pod': ('p1_minions', 16), 'boss1': ('p1_boss', 2),
    # 2스테이지 蒼の艦隊: UFO·거미 드론, 중보스 호위기, 보스 旗艦 (큰 패널 윗부분만)
    'ufo': ('p2_all', 147), 'spider': ('p2_all', 144), 'escort': ('p2_all', 84), 'boss2': ('p2_all', 17, (0, 0, 1, .66)),
    # 3스테이지: 해파리·삼각별, 중보스 날개 코어, 보스 オーバーロード Mk.II 의 형태 4단계
    'jelly': ('p1_minions', 36), 'tristar': ('p1_minions', 24), 'core': ('p1_boss', 6),
    'boss3a': ('p1_boss', 44), 'boss3b': ('p1_boss', 45), 'boss3c': ('p1_boss', 47), 'boss3d': ('p1_boss', 54),
    # 탄: 주황 구슬·불꽃·미사일·분홍 링·분홍 바늘·파란 초승달 / 자기 탄: 불꽃 화살·시안 화살
    'b_orb': ('p1_fx', 4), 'b_flame': ('p1_shots', 19), 'b_missile': ('p1_shots', 30), 'b_ring': ('p2_all', 27), 'b_needle': ('p2_all', 10), 'b_cres': ('p1_shots', 63),
    'p_shot': ('p1_shots', 16), 'p_arrow': ('p2_all', 7),
    # 아이템·효과
    'coin': ('p1_fx', 60), 'gem_g': ('p1_fx', 61), 'gem_p': ('p1_fx', 62), 'heart': ('p1_lives', 1, (.14, .14, .86, .86)),
    'boom1': ('p1_fx', 35), 'boom2': ('p1_fx', 36), 'boom3': ('p1_fx', 34), 'spark': ('p1_shots', 77),
}

def main():
    if len(sys.argv) > 2 and sys.argv[1] == 'scan': scan(sys.argv[2]); return
    cache = {}
    for name, pick in PICKS.items():
        region, idx = pick[0], pick[1]
        if region not in cache: cache[region] = cut(region)
        p = cache[region][idx]
        if len(pick) > 2:
            fx0, fy0, fx1, fy1 = pick[2]; p = p.crop((int(p.width * fx0), int(p.height * fy0), int(p.width * fx1), int(p.height * fy1)))
            a = np.asarray(p)[..., 3]; ys, xs = np.nonzero(a); p = p.crop((xs.min(), ys.min(), xs.max() + 1, ys.max() + 1))
        p.save(os.path.join(HERE, name + '.png'), optimize=True); print(name, p.size)

if __name__ == '__main__':
    main()
