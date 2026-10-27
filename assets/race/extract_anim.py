#!/usr/bin/env python3
"""ラン 탭 선수 6명의 달리기·슬라이드·스프린트 애니메이션을 운영자 애니메이션 시트(assets/race/src/anim_*.jpg 6장, 2752×1536)에서 잘라낸다.
   python3 assets/race/extract_anim.py scan OUTDIR   → 셀마다 잘라낸 조각을 번호 매긴 contact sheet 로(검토용)
   python3 assets/race/extract_anim.py               → assets/race/{선수}_{프레임}.png 저장(게임 크기로 미리 줄임)

시트는 셀 5개 × 2줄(위 선수·아래 선수). 셀 좌표는 시트를 2000px 폭으로 보고 적는다(SHEETS). 셀 안의 바탕(밝은 회색 또는 남색 + 격자선)을
바깥에서 이어진 만큼만 지우고(keyed_any), 가장 큰 덩어리(선수)만 남긴다 — 먼지·물보라·장식(마법진·골 테이프·아이템)은 따로 떨어져 있어 빠진다.
크기는 선수마다 달리기 프레임 키의 중앙값이 TALL(54px)이 되는 배율 하나를 그 선수의 모든 프레임에 똑같이 써서 프레임끼리 크기가 맞게 한다.
프레임 이름: _0.._4 달리기(contact·down·passing·push-off·flight. 라이스·오구리는 _0.._3 네 장), _sl0.._sl3 슬라이드(들어감·완전·완전·일어남), _d 스프린트(ブースト·점프), 오구리 _i 대기."""
import sys, os
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'game'))
from extract import components, flood_bg  # noqa: E402
from extract_race_fit import fit  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, 'src')
K = 2752 / 2000
TALL = 54

# 시트: 파일, 바탕 종류, 줄(y0,y1)×2, 열(x0,x1)×5, 줄마다 선수 키와 프레임 이름 5개
A_ROWS, A_COLS = [(165, 528), (665, 1062)], [(i * 400, (i + 1) * 400) for i in range(5)]
B_ROWS, B_COLS = [(85, 522), (603, 1052)], [(135, 505), (505, 880), (880, 1250), (1250, 1620), (1620, 1992)]
C_ROWS, C_COLS = [(140, 537), (688, 1087)], [(20, 410), (410, 805), (805, 1200), (1200, 1600), (1600, 1995)]
RUN = ['_0', '_1', '_2', '_3', '_4']
SHEETS = [
    ('anim_run_spe_suzu.jpg',   'light', A_ROWS, A_COLS, [('spe', RUN), ('suzu', RUN)]),
    ('anim_run_teio_gold.jpg',  'dark',  B_ROWS, B_COLS, [('teio', RUN), ('gold', RUN)]),
    # 라이스·오구리의 4번째(push-off)는 오라가 둘러싸 못 쓴다 → 달리기 4프레임(_0,_1,_2,_3=flight)
    ('anim_run_rice_oguri.jpg', 'dark',  C_ROWS, C_COLS, [('rice', ['_0', '_1', '_2', None, '_3']), ('oguri', ['_0', '_1', '_2', None, '_3'])]),
    # 슬라이드: 스페·스즈카 = CROUCH·SLIDE IN·FULL SLIDE·RECOVERY·SPRINT
    ('anim_slide_spe_suzu.jpg', 'light', A_ROWS, A_COLS, [('spe', ['_sl0', '_sl1', '_sl2', '_sl3', '_d']), ('suzu', ['_sl0', '_sl1', '_sl2', '_sl3', '_d'])]),
    # 테이오·골쉽 = BRAKE·KNEE SLIDE·DUCK SLIDE·ROLL UP·BURST
    ('anim_slide_teio_gold.jpg', 'dark', B_ROWS, B_COLS, [('teio', ['_sl0', '_sl1', '_sl2', '_sl3', '_d']), ('gold', ['_sl0', '_sl1', '_sl2', '_sl3', '_d'])]),
    # 라이스·오구리 = 달리기·슬라이드 들어감·완전 슬라이드·다이브(→ 스프린트)·주저앉음(→ 일어남). 완전 슬라이드를 두 칸에 쓴다
    # 1칸(달리기)은 오구리의 대기 그림(_i, 정면 대기 그림이 없어서)으로 쓴다
    ('anim_slide_rice_oguri.jpg', 'dark', C_ROWS, C_COLS, [('rice', [None, '_sl0', '_sl1+_sl2', '_d', '_sl3']), ('oguri', ['_i', '_sl0', '_sl1+_sl2', '_d', '_sl3'])]),
]
BG = {'light': [(210, 218, 221), (186, 194, 200), (170, 178, 186)], 'dark': [(19, 17, 41), (30, 34, 59), (13, 13, 37), (40, 44, 72), (56, 65, 100)]}

_cache = {}
def sheet(name):
    if name not in _cache: _cache[name] = np.asarray(Image.open(os.path.join(SRC, name)).convert('RGB')).astype(int)
    return _cache[name]

def keyed_any(arr, kind):
    """바탕색(격자선 포함)에 가까운 픽셀 중 바깥에서 이어진 것만 지운다. 선수 안의 흰 양말·밝은 옷은 윤곽선으로 막혀 남는다.
    남색 시트는 라이스의 머리카락이 바탕과 몇 단계밖에 차이 나지 않아(예 (26,24,37) vs (28,32,56)) 문턱을 아주 낮게(14) 두고,
    격자선은 색이 아니라 '그 색이 줄 전체에 깔린 행·열'로 찾아 지운다(선수 안의 같은 색은 남김)"""
    if kind == 'light':
        thr, near_thr = 46, 100
        bg = np.zeros(arr.shape[:2], bool)
        for c in BG[kind]: bg |= (np.abs(arr - np.array(c)).sum(2) < thr)
        mx, mn = arr.max(2), arr.min(2); bg |= (mx - mn <= 22) & (mx >= 150) & (mx <= 215)
    else:
        thr, near_thr = 14, 26
        base = np.median(arr.reshape(-1, 3), axis=0)  # 이 셀의 바탕색(가장 흔한 색)
        bg = np.abs(arr - base).sum(2) < thr
        for c in BG[kind]: bg |= (np.abs(arr - np.array(c)).sum(2) < thr)
        # 격자선: 선 색에 가까운 픽셀이 행(또는 열)의 40% 넘게 깔린 줄에서만 지운다
        linec = np.zeros(arr.shape[:2], bool)
        for c in ((36, 40, 64), (28, 32, 56), (56, 65, 100), (36, 40, 68)): linec |= (np.abs(arr - np.array(c)).sum(2) < 22)
        rows = linec.mean(1) > .4; cols = linec.mean(0) > .4
        bg |= linec & (rows[:, None] | cols[None, :])
    fg = ~flood_bg(bg)
    near = np.zeros_like(bg)
    for c in BG[kind]: near |= (np.abs(arr - np.array(c)).sum(2) < near_thr)
    pad = np.pad(fg, 1, constant_values=False)
    touch = ~(pad[:-2, 1:-1] & pad[2:, 1:-1] & pad[1:-1, :-2] & pad[1:-1, 2:])
    return fg & ~(near & touch)

# ---- 라이스 전용(2026-10 '여전히 많이 깨진다') ----
# 라이스는 머리·모자·옷이 다 남색 바탕과 몇 단계 차이라 색 문턱(keyed_any 14)으로는 모자 안쪽이 바탕으로 먹히고 바탕 찌꺼기가 남았다.
# 대신 시트의 선수 윤곽선(11,10,26 처럼 바탕 29,33,58 보다 확실히 어두움)을 벽으로 두고, 바깥에서 이어진 바탕만 넓은 문턱(48)으로 지운다.
# 줄일 때는 BOX 평균 대신 블록 중앙값(경계가 뭉개지지 않음) + 40색 + 감마 .8·채도 1.2.
LINE_DARK = [(56, 65, 100), (36, 40, 64), (36, 40, 68), (43, 46, 81), (61, 64, 97)]
def dilate(m, r=1):
    o = m.copy()
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1): o |= np.roll(np.roll(m, dy, 0), dx, 1)
    return o

def keyed_outline(arr, pole=False):
    """어두운 윤곽선(합 62 미만)을 넘지 못하게 하고 바탕 후보(바탕색에서 48 이내·격자선 색)를 가장자리에서 flood.
    pole: 골 기둥(흰 칸 + 바탕색 칸)이 있는 칸 — 흰 칸이 세로로 깔린 열 띠 안의 흰색도 바탕 후보(앞에 있는 선수 그림은 윤곽선 안이라 남는다)"""
    base = np.median(arr.reshape(-1, 3), axis=0)
    outline = arr.sum(2) < 62
    cand = np.abs(arr - base).sum(2) < 48
    for c in LINE_DARK: cand |= np.abs(arr - np.array(c)).sum(2) < 40
    if pole:
        xs = np.nonzero((arr.min(2) > 200).mean(0) > .25)[0]
        if len(xs):
            band = np.zeros(arr.shape[1], bool); band[max(0, xs.min() - 4):xs.max() + 5] = True
            cand |= (arr.min(2) > 185) & band[None, :]
    cand &= ~dilate(outline, 1)
    bg = flood_bg(cand)
    bg |= dilate(bg, 1) & ~outline & (np.abs(arr - base).sum(2) < 60)  # 윤곽선 바로 바깥의 JPEG 번짐 1px
    return ~bg

def shrink_median(p, sc, colors=40, gamma=.8, sat=1.2):
    """블록 중앙값으로 줄이기: 출력 한 칸 = 원본 블록 안 선수 픽셀의 채널별 중앙값(덮인 비율 .45 이상인 칸만). 그 뒤 밝기·채도·양자화·1px 윤곽"""
    a = np.asarray(p); m = a[..., 3] > 0
    rgb = np.asarray(Image.fromarray(a[..., :3]).filter(ImageFilter.MedianFilter(3))).astype(float)
    H, W = m.shape; h, w = max(1, round(H * sc)), max(1, round(W * sc))
    out = np.zeros((h, w, 4), np.uint8)
    ye = np.linspace(0, H, h + 1).round().astype(int); xe = np.linspace(0, W, w + 1).round().astype(int)
    for j in range(h):
        for i in range(w):
            mm = m[ye[j]:ye[j + 1], xe[i]:xe[i + 1]]
            if mm.size == 0 or mm.mean() < .45: continue
            out[j, i, :3] = np.median(rgb[ye[j]:ye[j + 1], xe[i]:xe[i + 1]][mm], 0); out[j, i, 3] = 255
    on = out[..., 3] > 0
    c = 255 * ((out[..., :3] / 255) ** gamma); g = c.mean(2, keepdims=True); c = np.clip(g + (c - g) * sat, 0, 255)
    out[..., :3] = np.asarray(Image.fromarray(c.astype(np.uint8), 'RGB').quantize(colors, method=Image.MEDIANCUT, dither=Image.NONE).convert('RGB'))
    out[~on] = 0
    pad = np.pad(on, 1, constant_values=False)
    out[(pad[:-2, 1:-1] | pad[2:, 1:-1] | pad[1:-1, :-2] | pad[1:-1, 2:]) & ~on] = (26, 20, 38, 255)
    return drop_specks(Image.fromarray(out, 'RGBA'))

def run_len(mask, axis):
    """각 픽셀이 속한 연속 구간의 길이(axis=1 가로, 0 세로)"""
    m = mask if axis == 1 else mask.T
    out = np.zeros(m.shape, int)
    for i in range(m.shape[0]):
        row = m[i]; j = 0; n = len(row)
        while j < n:
            if row[j]:
                k = j
                while k < n and row[k]: k += 1
                out[i, j:k] = k - j; j = k
            else: j += 1
    return out if axis == 1 else out.T

# 프레임마다 지울 사각형(조각 상자 기준 비율 x0,y0,x1,y1)과 색 규칙. 효과는 선수 윤곽선과 붙어 있어 자동으로 떼기 어려워 자리로 지운다
MASK = {
    ('spe', '_3'): [(0, .78, .3, 1)], ('suzu', '_3'): [(0, .8, .3, 1)],
    ('spe', '_sl1'): [(.62, .85, 1, 1)], ('spe', '_sl3'): [(0, .85, .28, 1)], ('suzu', '_sl1'): [(.6, .75, 1, 1)],
    ('teio', '_3'): [(0, .7, .42, 1)], ('gold', '_3'): [(0, .72, .36, 1), (0, 0, .03, 1)], ('gold', '_d'): [(0, 0, .03, 1), (0, .78, .3, 1)],
    ('rice', '_3'): [(0, .78, .3, 1), (.4, .76, 1, 1)], ('oguri', '_2'): [(0, .92, .45, 1)],
    ('teio', '_sl1'): [(0, .78, .3, 1), (0, .9, .55, 1)], ('teio', '_sl2'): [(0, .4, .28, 1)], ('teio', '_sl3'): [(0, .3, .33, .52)], ('teio', '_d'): [(0, .75, .35, 1)],
    ('gold', '_sl0'): [(0, .85, .3, 1)], ('gold', '_sl2'): [(0, .4, .3, 1)], ('gold', '_sl3'): [(0, .85, .3, 1)],
    ('rice', '_sl0'): [(0, .75, .35, 1), (.62, .82, 1, 1)], ('rice', '_sl1+_sl2'): [(0, .76, .44, 1)], ('oguri', '_sl0'): [(0, .75, .4, 1)], ('oguri', '_sl1+_sl2'): [(0, .62, .35, 1)], ('oguri', '_d'): [(0, .72, .78, 1)],
}
SKY = {('rice', '_sl0'), ('rice', '_sl1+_sl2'), ('oguri', '_sl0'), ('oguri', '_sl1+_sl2'), ('rice', '_d'), ('oguri', '_d')}  # 오라·물보라(밝은 하늘색) 지우기

def strip_fx(arr, fg, kind, ck, fr):
    """선수에 붙은 효과 지우기: 남색 시트 공통(풀 초록, 얇고 긴 밝은 가로 획=속도선, 아래쪽 주황 불꽃), 프레임별 사각형(MASK), 오라·물보라(SKY)"""
    r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]; mx, mn = arr.max(2), arr.min(2)
    h, w = fg.shape; yy, xx = np.mgrid[0:h, 0:w]
    if kind == 'dark':
        fg = fg & ~((g > r + 30) & (g > b + 20))
        light = (mn > 140) & (mx - mn < 80) & fg
        fg = fg & ~(light & (run_len(light, 1) >= 22) & (run_len(light, 0) <= 7))
        fg = fg & ~((r > 225) & (g > 90) & (g < 235) & (b < 130) & (yy > h * .65))
    if (ck, fr) in SKY: fg = fg & ~((b > 150) & (b > r + 40) & (g > 100))
    ys, xs = np.nonzero(fg)
    if len(ys):
        y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
        for (fx0, fy0, fx1, fy1) in MASK.get((ck, fr), []):
            fg[int(y0 + (y1 - y0) * fy0):int(y0 + (y1 - y0) * fy1), int(x0 + (x1 - x0) * fx0):int(x0 + (x1 - x0) * fx1)] = False
    return fg

def strip_tape(arr, fg):
    """골 테이프(흑백 체커): 순검정·순백이 세로로 30% 넘게 깔린 열에서 그 색을 지우고, 양옆이 이어진 줄은 왼쪽 색으로 메운다(소매가 끊기지 않게).
    메운 픽셀의 색은 arr 를 고쳐서 돌려준다"""
    mx, mn = arr.max(2), arr.min(2)
    checker = ((mx < 72) & (mx - mn < 30) | (mn > 205)) & fg
    cols = checker.mean(0) > .3
    if not cols.any(): return fg, arr
    fg = fg & ~(checker & cols[None, :])
    arr = arr.copy(); xs = np.nonzero(cols)[0]; cx0, cx1 = xs.min(), xs.max() + 1
    for y in range(fg.shape[0]):
        L = fg[y, max(0, cx0 - 3):cx0].any(); R = fg[y, cx1:cx1 + 3].any()
        if L and R:
            src = arr[y, cx0 - 1]
            for x in range(cx0, cx1):
                if not fg[y, x]: fg[y, x] = True; arr[y, x] = src
    return fg, arr

def clean_dark(arr, fg):
    """남색 시트 정리(2026-10, 라이스가 '깨져' 보이던 문제): ① 다리·팔 사이에 갇힌 바탕(바깥 flood 가 못 닿아 남던 어두운 네모)을 지운다 —
    바탕색에 아주 가까운 픽셀 덩어리가 25px 이상이면 바탕. 머리카락은 바탕과 거리 25 이상이라 남는다 ② 발밑 어두운 풀(초록 기운의 어두운 색, 아래 20%)을 지운다"""
    base = np.median(arr.reshape(-1, 3), axis=0)
    near = (np.abs(arr - base).sum(2) < 18)
    for c in BG['dark']: near |= (np.abs(arr - np.array(c)).sum(2) < 16)
    lab, boxes = components(near & fg, reach=1, min_px=25)
    for (_, _, _, _, n) in boxes: fg = fg & ~(lab == n)
    r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]; h = fg.shape[0]; yy = np.mgrid[0:h, 0:fg.shape[1]][0]
    fg = fg & ~((g > r + 6) & (g >= b - 12) & (yy > h * .8))
    return fg

# 스즈카: 운영자 애니메이션 시트는 머리·귀·꼬리를 초록으로 그렸지만 원래 그림(suzu_i, 컨셉 시트)은 주황 머리 + 초록 재킷이다.
# 초록(색상 120~190°)을 주황(16°)으로 바꾸되, 재킷 앞소매·몸통 쪽 상자(조각 상자 비율)는 초록으로 둔다
SUZU_KEEP = {'_0': (.5, .47, 1, .72), '_1': (.5, .44, 1, .66), '_2': (.5, .47, 1, .7), '_3': (.5, .45, 1, .7), '_4': (.5, .46, 1, .7),
             '_sl0': (.5, .47, 1, .72), '_sl1': (.5, .5, 1, .78), '_sl2': (.62, .66, 1, 1), '_sl3': (.48, .48, 1, .74), '_d': (.5, .47, 1, .72)}
def recolor_suzu(p, fr):
    a = np.asarray(p).astype(float); rgb = a[..., :3] / 255; mx = rgb.max(2); mn = rgb.min(2); d = mx - mn + 1e-9
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    hue = np.where(mx == g, 60 * ((b - r) / d) + 120, np.where(mx == r, (60 * ((g - b) / d)) % 360, 60 * ((r - g) / d) + 240))
    sat = d / np.maximum(mx, 1e-9)
    m = (hue >= 120) & (hue <= 190) & (sat > .25) & (a[..., 3] > 0)
    h, w = m.shape; kx0, ky0, kx1, ky1 = SUZU_KEEP.get(fr, (1, 1, 1, 1))
    keep = np.zeros_like(m); keep[int(h * ky0):int(h * ky1), int(w * kx0):int(w * kx1)] = True
    m &= ~keep
    # 주황(원래 그림의 머리 팔레트 (233,122,79)~(138,66,62))으로: 밝기는 살리고 색상·채도만 바꾼다
    v = np.clip(mx * 1.12 + .03, 0, 1); s2 = np.clip(sat * .85 + .12, 0, 1); hh = np.where(v < .35, 8, 16) / 360
    import colorsys
    out = a.copy(); ys, xs = np.nonzero(m)
    for y, x in zip(ys, xs):
        rr, gg, bb = colorsys.hsv_to_rgb(hh[y, x], s2[y, x], v[y, x]); out[y, x, :3] = (rr * 255, gg * 255, bb * 255)
    return Image.fromarray(out.astype(np.uint8), 'RGBA')

def piece(arr, kind, ck, fr):
    """셀에서 가장 큰 덩어리(선수)만 RGBA 로"""
    if ck == 'rice':  # 윤곽선을 벽으로 둔 바탕 지우기(위 keyed_outline). 골 기둥은 채워 넣지 않고 흰 칸만 바탕으로
        fg = strip_fx(arr, keyed_outline(arr, pole=(fr == '_d')), kind, ck, fr)
        r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]; yy = np.mgrid[0:fg.shape[0], 0:fg.shape[1]][0]
        fg = fg & ~((g > r + 6) & (g >= b - 12) & (yy > fg.shape[0] * .8))   # 발밑 어두운 풀
        reach = 1
    else:
        fg = keyed_any(arr, kind)
        fg = strip_fx(arr, fg, kind, ck, fr)
        if fr == '_d' and ck == 'oguri': fg, arr = strip_tape(arr, fg)
        if kind == 'dark': fg = clean_dark(arr, fg)
        reach = 2
    lab, boxes = components(fg, reach=reach, min_px=40)
    if not boxes: return None
    counts = {n: int((lab == n).sum()) for (_, _, _, _, n) in boxes}
    n = max(counts, key=counts.get)
    keep = lab == n
    ys, xs = np.nonzero(keep); y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    rgb = arr[y0:y1, x0:x1].astype(np.uint8)
    return Image.fromarray(np.dstack([rgb, (keep[y0:y1, x0:x1] * 255).astype(np.uint8)]), 'RGBA')

def cells():
    """(선수, 프레임이름, RGBA 조각) 을 시트 순서대로"""
    out = []
    for fname, kind, rows, cols, chars in SHEETS:
        arr = sheet(fname)
        for (y0, y1), (ck, frames) in zip(rows, chars):
            for (x0, x1), fr in zip(cols, frames):
                p = piece(arr[int(y0 * K):int(y1 * K), int(x0 * K):int(x1 * K)], kind, ck, fr)
                out.append((ck, fr, p, fname))
    return out

def scan(outdir):
    os.makedirs(outdir, exist_ok=True)
    items = cells(); cw, ch = 220, 240
    img = Image.new('RGB', (cw * 5, ch * ((len(items) + 4) // 5)), (40, 44, 70)); d = ImageDraw.Draw(img)
    for i, (ck, fr, p, fname) in enumerate(items):
        x, y = (i % 5) * cw, (i // 5) * ch
        if p is not None:
            sc = min(1, (ch - 40) / p.height, (cw - 10) / p.width); q = p.resize((max(1, int(p.width * sc)), max(1, int(p.height * sc))), Image.LANCZOS)
            img.paste(q, (x + 5, y + 30), q)
        d.text((x + 4, y + 4), f'{i} {ck}{fr or "-"} {p.size if p else None}', fill=(255, 230, 120))
    img.save(os.path.join(outdir, 'anim_scan.png')); print('wrote', os.path.join(outdir, 'anim_scan.png'))

RICE_IDLE = ('uma2.jpg', (171, 838, 315, 1119))  # extract.py 의 b_idle 28번 칸(원본 좌표)
def rice_idle():
    """라이스 정면 대기 그림(옛 컨셉 시트 uma2 의 b_idle 칸). 달리기 프레임과 같은 keyed_outline·shrink_median 으로"""
    arr = sheet(RICE_IDLE[0]); x0, y0, x1, y1 = RICE_IDLE[1]
    return piece(arr[y0:y1, x0:x1], 'dark', 'rice', '_i')

def drop_specks(img, min_px=8):
    """줄인 뒤 몸에서 떨어진 작은 점(머리카락 끝·JPEG 찌꺼기) 지우기"""
    a = np.asarray(img).copy(); m = a[..., 3] > 0
    lab, boxes = components(m, reach=1, min_px=1)
    for (_, _, _, _, n) in boxes:
        if (lab == n).sum() < min_px: a[lab == n] = 0
    return Image.fromarray(a, 'RGBA')

def main():
    if len(sys.argv) > 2 and sys.argv[1] == 'scan': scan(sys.argv[2]); return
    items = cells()
    hs = {}
    for ck, fr, p, _ in items:
        if fr and fr.startswith('_') and fr[1:].isdigit() and p is not None: hs.setdefault(ck, []).append(p.height)
    scale = {ck: TALL / float(np.median(v)) for ck, v in hs.items()}
    n = 0
    for ck, fr, p, _ in items:
        if not fr or p is None: continue
        if ck == 'suzu': p = recolor_suzu(p, fr)
        for name in fr.split('+'):
            q = shrink_median(p, scale[ck]) if ck == 'rice' else drop_specks(fit(p, scale[ck]))
            q.save(os.path.join(HERE, f'{ck}{name}.png')); n += 1
    ri = rice_idle()
    if ri is not None: shrink_median(ri, 60 / ri.height).save(os.path.join(HERE, 'rice_i.png')); n += 1
    print('saved', n, 'frames; scale', {k: round(v, 3) for k, v in scale.items()})

if __name__ == '__main__': main()
