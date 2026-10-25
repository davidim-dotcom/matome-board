#!/usr/bin/env python3
"""운영자가 만든 스프라이트 시트(assets/game/src/sheet1.jpg, sheet2.jpg)에서 조각을 잘라낸다.
   python3 assets/game/extract.py scan OUTDIR     → 영역별로 조각을 번호 매겨 contact sheet(PNG)로 뽑아 고르기용
   python3 assets/game/extract.py                 → PICKS 에 적은 조각을 assets/game/*.png 로 저장
   python3 assets/game/extract.py holo            → 홀로 스킨(HOLO_CHARS·HOLO) 조각을 assets/game/hc_*·hm_*·hb_*·hx_*.png 로 저장
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
    # 홀로 스킨 시트(2752×1536): sheet3 은 sheet1 과 같은 배치(홀로 멤버·해적 문어·여우·사신 보스), sheet4 는 격자 칸(멤버·몬스터·보스·마법진)
    'h3_player':  ('sheet3.jpg', (16, 48, 905, 935), 'dark'),
    'h3_minions': ('sheet3.jpg', (922, 48, 2002, 495), 'dark'),
    'h3_boss':    ('sheet3.jpg', (922, 557, 2002, 1520), 'dark'),
    'h3_fx':      ('sheet3.jpg', (2018, 612, 2738, 1183), 'dark'),
    'h4_chars':   ('sheet4.jpg', (20, 58, 1355, 1117), 'grid'),
    'h4_mons':    ('sheet4.jpg', (20, 1186, 1355, 1520), 'grid'),
    'h4_dragon':  ('sheet4.jpg', (1376, 58, 2201, 589), 'grid'),
    'h4_ship':    ('sheet4.jpg', (1376, 649, 2201, 1084), 'grid'),
    'h4_bosses':  ('sheet4.jpg', (1376, 1098, 2738, 1520), 'grid'),
    'h4_fx':      ('sheet4.jpg', (2215, 58, 2731, 1080), 'grid'),
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
        if kind == 'grid':  # 칸 사이 격자선(푸른 회색)도 배경
            r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
            bg |= (np.abs(r - 58) < 22) & (np.abs(g - 67) < 22) & (np.abs(b - 100) < 24)
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
    # 추가 활용: 거대 빔(보스 레이저, 왼쪽 드론 부분은 잘라냄)·빗자루 휘두르기(結界 연출)·화면 정리 폭발·피탄 폭발
    'beam': ('p1_boss', 38, (.27, 0, 1, 1)), 'broom1': ('p1_player', 36), 'broom2': ('p1_player', 37), 'clear': ('p1_fx', 52), 'hit': ('p2_all', 102),
    # 라이벌 파일럿(ST2 보스)·그녀의 분홍 기체·컷인 초상(보스1 미니 메이드, 파일럿, 릴리 표정)
    # 4스테이지 要塞宙域: 주황 UFO·포탑, 중보스 X형 전투기, 보스 요새함(형태 3단계) + 必殺 시작 때 비치는 공격 포즈 그림 4장
    'ufo_o': ('p2_all', 171), 'turret': ('p2_all', 164), 'xwing': ('p1_boss', 3),
    'fort': ('p2_all', 115, (.03, 0, 1, 1)), 'fort2': ('p2_all', 131), 'fortcore': ('p2_all', 36),
    'fa_spoke': ('p2_all', 24), 'fa_orbs': ('p2_all', 67), 'fa_cres': ('p2_all', 69, (.03, 0, 1, 1)), 'fa_fan': ('p2_all', 75),
    # 5스테이지 最終決戦: 눈알 포드·U자 함선 (중보스는 라이벌 재전, 보스는 메이드봇 真)
    'eye': ('p1_boss', 14), 'ushp': ('p1_boss', 12),
    # 에너지 지뢰·릴리 스킬 프레임(저속 모드 연출: 마법진·얼음 결정)
    'mine': ('p1_fx', 7), 'mine2': ('p1_fx', 6), 'skill_a': ('p1_player', 52), 'skill_b': ('p1_player', 58), 'skill_c': ('p1_player', 59), 'ice1': ('p1_player', 60), 'ice2': ('p1_player', 61), 'magic': ('p1_player', 56, (0, .52, 1, 1)), 'skill_d': ('p1_player', 69),
    # 보스 고유 공격 탄(대형 화염탄·혜성탄·보라 초승달·보라/푸른 별탄·분홍 파동)과 스테이지 오브젝트(보급 포드·폭발 탱크·소형 편대기)
    'b_fire': ('p1_shots', 72), 'b_comet': ('p1_shots', 66), 'b_pcres': ('p1_shots', 73), 'b_pstar': ('p1_shots', 80), 'b_cstar': ('p1_shots', 81), 'b_wave': ('p2_all', 49),
    'crate': ('p1_boss', 15), 'tank': ('p1_boss', 5), 'fighter': ('p1_boss', 7),
    'pilot': ('p2_all', 77), 'pship': ('p2_all', 124), 'face_b1': ('p1_boss', 1), 'face_pilot': ('p2_all', 3, (.04, .04, .96, .9)), 'face_lilly': ('p1_player', 73), 'face_lilly2': ('p1_player', 77),
}

# 탄막 패턴 타일(sheet1 오른쪽 위 4×3 격자). 보스가 큰 패턴을 쏘기 전 예고로 비친다. 이름 → (행, 열)
TILES = {'tile_ring': (0, 0), 'tile_burst': (0, 2), 'tile_spokes': (1, 1), 'tile_spiral': (2, 3), 'tile_fan': (1, 3), 'tile_cross': (0, 3)}
TILE_BOX = (1034, 30, 1406, 300)
def cut_tile(r, c, thr=70):
    x0, y0, x1, y1 = TILE_BOX; tw, th = (x1 - x0) / 4, (y1 - y0) / 3
    im = Image.open(os.path.join(SRC, 'sheet1.jpg')).convert('RGB').crop((int(x0 + c * tw + 4), int(y0 + r * th + 4), int(x0 + (c + 1) * tw - 4), int(y0 + (r + 1) * th - 4)))
    arr = np.asarray(im).astype(int); lum = arr.max(2)
    a = np.clip((lum - 60) * 4, 0, 255).astype(np.uint8)   # 어두운 바탕은 투명, 밝은 점은 불투명
    return Image.fromarray(np.dstack([arr.astype(np.uint8), a]), 'RGBA')

# 홀로 스킨: 이름 → (영역, 조각 번호, 자르기 또는 None, 최대 변 길이). 게임 크기에 맞게 미리 줄인다(LANCZOS 후 알파 이진화)
HOLO_CHARS = {  # 멤버 키 → (포즈 3장 조각 번호, 오프션 조각 번호 또는 None = 자기 미니)
    'sora': ((0, 1, 2), 6), 'suisei': ((3, 4, 5), 11), 'pekora': ((24, 25, 26), 33), 'aqua': ((27, 28, 29), None),
    'marine': ((44, 45, 44), None), 'fubuki': ((47, 49, 50), 53), 'subaru': ((60, 61, 62), 68), 'korone': ((63, 64, 65), None),
    'okayu': ((73, 74, 73), None), 'miko': ((75, 76, 75), None), 'calli': ((77, 78, 77), None), 'mumei': ((100, 101, 100), None),
    'ollie': ((102, 103, 104), None), 'fauna': ((106, 107, 106), None)}
HOLO = {
    # 몬스터(잡몹 32px, 중보스 72~90px)
    'hm_slime_b': ('h4_mons', 5, None, 32), 'hm_wisp': ('h4_mons', 3, None, 34), 'hm_chest': ('h4_mons', 26, None, 64),
    'hm_drone': ('h4_mons', 0, None, 34), 'hm_slime_g': ('h4_mons', 6, None, 32), 'hm_golem': ('h4_mons', 17, None, 80),
    'hm_skel': ('h4_mons', 33, None, 32), 'hm_devil': ('h4_mons', 8, None, 34), 'hm_crystal': ('h4_mons', 18, None, 70),
    'hm_flame': ('h4_mons', 27, None, 30), 'hm_bflame': ('h4_mons', 29, None, 30), 'hm_skull': ('h4_ship', 19, None, 32),
    'hm_rdevil': ('h4_mons', 9, None, 34), 'hm_knight': ('h4_mons', 23, None, 72),
    # 보스(긴 변 150~170px)
    'hb_ship': ('h4_ship', 0, None, 160), 'hb_mkitsune': ('h3_boss', 7, None, 150), 'hb_mreaper': ('h3_boss', 6, None, 150),
    'hb_dragon': ('h4_dragon', 0, None, 175), 'hb_fox': ('h4_bosses', 0, None, 92), 'hb_reaper': ('h4_bosses', 2, None, 160),
    # 오브젝트의 홀로 판(얼음 결정=운석, 녹색 UFO=보급, 박쥐 마물=편대기, 빨강 슬라임=폭발, 회오리=레이저 울타리 발사기)
    'ho_ice': ('h4_ship', 27, None, 30), 'ho_ufo': ('h4_ship', 10, None, 40), 'ho_bat': ('h4_mons', 13, None, 34),
    'ho_slime': ('h4_mons', 7, None, 34), 'ho_tornado': ('h4_mons', 31, None, 40),
    # 마법진(必殺 예고·저속 모드 발밑)
    'hx_purple': ('h4_fx', 29, None, 96), 'hx_green': ('h4_fx', 30, None, 96), 'hx_orange': ('h4_fx', 32, None, 96),
    'hx_blue': ('h4_fx', 37, None, 96), 'hx_clock': ('h4_fx', 38, None, 96), 'hx_red': ('h4_fx', 39, None, 96), 'hx_foot': ('h4_fx', 29, None, 40),
}
def fit(p, maxdim):
    sc = maxdim / max(p.width, p.height)
    if sc >= 1: return p
    q = p.resize((max(1, round(p.width * sc)), max(1, round(p.height * sc))), Image.LANCZOS)
    a = np.asarray(q).copy(); a[..., 3] = np.where(a[..., 3] >= 110, 255, 0); return Image.fromarray(a, 'RGBA')

def holo(cache):
    def piece(region, idx):
        if region not in cache: cache[region] = cut(region)
        return cache[region][idx]
    out = {}
    for key, (poses, pet) in HOLO_CHARS.items():
        for k, idx in enumerate(poses): out[f'hc_{key}_{k}'] = fit(piece('h4_chars', idx), 44)
        out[f'hc_{key}_m'] = fit(piece('h4_chars', pet if pet is not None else poses[0]), 24)
        out[f'hc_{key}_f'] = fit(piece('h4_chars', poses[0]), 30)   # 스킨 선택 칩 얼굴
    for name, (region, idx, crop, mx) in HOLO.items(): out[name] = fit(piece(region, idx), mx)
    return out

def main():
    if len(sys.argv) > 2 and sys.argv[1] == 'scan': scan(sys.argv[2]); return
    for name, (r, c) in TILES.items():
        t = cut_tile(r, c); t.save(os.path.join(HERE, name + '.png'), optimize=True); print(name, t.size)
    cache = {}
    if len(sys.argv) > 1 and sys.argv[1] == 'holo':
        for n, im in holo(cache).items(): im.save(os.path.join(HERE, n + '.png'), optimize=True)
        print('holo', len(HOLO_CHARS), 'members'); return
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
