#!/usr/bin/env python3
"""ダービー 탭(まとめダービー)의 그림을 운영자 컨셉 시트(assets/race/src/uma1~6.jpg, 2752×1536)에서 잘라낸다.
   python3 assets/race/extract.py scan OUTDIR   → 격자 칸·조각을 번호 매긴 contact sheet 로 뽑아 고르기용
   python3 assets/race/extract.py               → PICKS 에 적은 칸·조각을 assets/race/*.png 로 저장(게임 크기로 미리 줄임)
시트는 어두운 남색 바탕에 푸른 회색 격자선. 격자 구역(GRIDS)은 격자선을 자동으로 찾아 칸 단위로 자르고(한 칸 = 한 그림, 떨어진 꼬리·속도선도 같이),
불규칙한 구역(REGIONS)은 게임 시트와 같은 덩어리 분리(assets/game/extract.py 의 foreground/components)를 쓴다."""
import sys, os
import numpy as np
from PIL import Image, ImageDraw
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'game'))
from extract import foreground, components, flood_bg  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, 'src')
K = 2752 / 2000  # 시트를 2000px 폭으로 보고 적은 좌표를 원본으로
def B(x0, y0, x1, y1): return (int(x0 * K), int(y0 * K), int(x1 * K), int(y1 * K))

# 격자 구역: 이름 → (시트, 상자). 칸 번호는 줄 → 왼쪽 순
GRIDS = {
    'a_jog': ('uma1.jpg', B(10, 65, 672, 296)), 'a_sprint': ('uma1.jpg', B(10, 320, 672, 426)), 'a_dash': ('uma1.jpg', B(10, 458, 672, 566)),
    'a_stumble': ('uma1.jpg', B(10, 590, 672, 702)), 'a_win': ('uma1.jpg', B(10, 735, 672, 946)), 'a_expr': ('uma1.jpg', B(10, 1000, 672, 1112)),
    'a_items': ('uma1.jpg', B(1600, 68, 1992, 222)), 'a_ui': ('uma1.jpg', B(1600, 250, 1992, 440)), 'a_gems': ('uma1.jpg', B(1600, 440, 1992, 522)),
    'a_track': ('uma1.jpg', B(1600, 540, 1992, 882)), 'a_part': ('uma1.jpg', B(1600, 920, 1992, 1112)),
    'c_jog': ('uma3.jpg', B(10, 65, 672, 296)), 'c_sprint': ('uma3.jpg', B(10, 320, 672, 426)), 'c_dash': ('uma3.jpg', B(10, 458, 672, 566)),
    'c_stumble': ('uma3.jpg', B(10, 590, 672, 702)), 'c_win': ('uma3.jpg', B(10, 735, 672, 946)), 'c_expr': ('uma3.jpg', B(10, 1000, 672, 1112)),
    'c_items': ('uma3.jpg', B(1600, 68, 1992, 222)), 'c_ui': ('uma3.jpg', B(1600, 250, 1992, 440)), 'c_gems': ('uma3.jpg', B(1600, 440, 1992, 522)),
    'c_track': ('uma3.jpg', B(1600, 540, 1992, 882)), 'c_part': ('uma3.jpg', B(1600, 920, 1992, 1112)),
    'b_idle': ('uma2.jpg', B(10, 40, 992, 822)), 'b_run': ('uma2.jpg', B(1000, 40, 1992, 432)), 'b_face': ('uma2.jpg', B(10, 860, 992, 1112)),
    'f_idle': ('uma6.jpg', B(10, 40, 992, 822)), 'f_run': ('uma6.jpg', B(1000, 40, 1992, 432)), 'f_face': ('uma6.jpg', B(10, 860, 992, 1112)),
    'd_chars': ('uma4.jpg', B(10, 40, 992, 822)), 'd_emo': ('uma4.jpg', B(1000, 40, 1992, 800)), 'd_fx': ('uma4.jpg', B(1340, 840, 1992, 1112)),
    'e_chars': ('uma5.jpg', B(10, 40, 992, 822)), 'e_emo': ('uma5.jpg', B(1000, 40, 1600, 800)), 'e_aura': ('uma5.jpg', B(1610, 40, 1992, 582)), 'e_shoe': ('uma5.jpg', B(1610, 590, 1992, 800)),
}
# 덩어리 구역: 이름 → (시트, 상자)
REGIONS = {
    'a_cutin': ('uma1.jpg', B(700, 45, 1582, 428)), 'a_boss': ('uma1.jpg', B(700, 480, 1582, 1112)),
    'c_cutin': ('uma3.jpg', B(700, 45, 1582, 428)), 'c_boss': ('uma3.jpg', B(700, 480, 1582, 1112)),
    'b_row4': ('uma2.jpg', B(1000, 432, 1992, 622)), 'b_row5': ('uma2.jpg', B(1000, 622, 1992, 822)), 'b_fx': ('uma2.jpg', B(1000, 860, 1992, 1112)),
    'f_row4': ('uma6.jpg', B(1000, 432, 1992, 622)), 'f_row5': ('uma6.jpg', B(1000, 622, 1992, 822)), 'f_fx': ('uma6.jpg', B(1000, 860, 1992, 1112)),
    'd_props': ('uma4.jpg', B(10, 860, 992, 1112)), 'd_podium': ('uma4.jpg', B(1000, 800, 1340, 1112)),
    'e_props': ('uma5.jpg', B(10, 860, 992, 1112)), 'e_bottom': ('uma5.jpg', B(1000, 800, 1992, 1112)),
}

_cache = {}
def sheet(name):
    if name not in _cache: _cache[name] = np.asarray(Image.open(os.path.join(SRC, name)).convert('RGB')).astype(int)
    return _cache[name]

def line_mask(arr):
    r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
    return (np.abs(r - 56) < 20) & (np.abs(g - 65) < 20) & (np.abs(b - 100) < 24)

def lines(mask, axis, thr=.42):
    """격자선 위치(중심) 목록. axis=0: 세로선의 x, axis=1: 가로선의 y"""
    frac = mask.mean(axis=0 if axis == 0 else 1)
    out = []; s = None
    for i, v in enumerate(frac):
        if v > thr and s is None: s = i
        elif v <= thr and s is not None: out.append((s + i - 1) // 2); s = None
    if s is not None: out.append((s + len(frac) - 1) // 2)
    return out

def cells(grid):
    sh, (x0, y0, x1, y1) = GRIDS[grid]; arr = sheet(sh)[y0:y1, x0:x1]; m = line_mask(arr)
    xs = [0] + lines(m, 0) + [arr.shape[1]]; ys = [0] + lines(m, 1) + [arr.shape[0]]
    xs = [x for i, x in enumerate(xs) if i == 0 or x - xs[i - 1] > 18]; ys = [y for i, y in enumerate(ys) if i == 0 or y - ys[i - 1] > 18]
    out = []
    for r in range(len(ys) - 1):
        for c in range(len(xs) - 1):
            cx0, cy0, cx1, cy1 = xs[c] + 3, ys[r] + 3, xs[c + 1] - 3, ys[r + 1] - 3
            if cx1 - cx0 < 12 or cy1 - cy0 < 12: continue
            out.append(((cx0 + x0, cy0 + y0, cx1 + x0, cy1 + y0), piece(arr[cy0:cy1, cx0:cx1])))
    return out

BG = ((30, 36, 60), (12, 12, 36), (24, 30, 54))
def keyed(arr, thr=26):
    """바탕(어두운 남색 2색 + 격자선)을 바깥에서 이어진 만큼만 지운 전경 마스크. 문턱을 낮게(26) 잡아 검은 윤곽선은 남긴다.
    JPEG 라 그림 가장자리에 바탕색이 번진 1px 테두리(bg 에 가까운 색이면서 투명 칸에 닿은 픽셀)는 한 번 더 지운다"""
    bg = np.zeros(arr.shape[:2], bool)
    for c in BG: bg |= (np.abs(arr - np.array(c)).sum(2) < thr)
    bg |= line_mask(arr)
    fg = ~flood_bg(bg)
    near = np.zeros_like(bg)
    for c in BG: near |= (np.abs(arr - np.array(c)).sum(2) < 90)
    pad = np.pad(fg, 1, constant_values=False)
    touch = ~(pad[:-2, 1:-1] & pad[2:, 1:-1] & pad[1:-1, :-2] & pad[1:-1, 2:])
    return fg & ~(near & touch)

def piece(arr):
    """칸 안의 그림을 내용 상자로 자른 RGBA(원본 해상도)"""
    fg = keyed(arr)
    ys, xs = np.nonzero(fg)
    if len(ys) == 0: return None
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    rgba = np.dstack([arr[y0:y1, x0:x1].astype(np.uint8), (fg[y0:y1, x0:x1] * 255).astype(np.uint8)])
    return Image.fromarray(rgba, 'RGBA')

def fit(p, maxdim, outline=True, colors=40):
    """게임 크기로 줄인다. 시트는 부드럽게 번진 '가짜 도트'라 BOX(면적 평균)로 줄이고 알파를 이진화한 뒤,
    색을 40색으로 묶어 도트 그림답게 평평하게 하고, 바탕(잔디)과 구분되게 1px 어두운 윤곽선을 두른다"""
    sc = maxdim / max(p.width, p.height)
    if sc < 1:
        a = np.asarray(p).astype(float); al = a[..., 3:4] / 255
        pm = Image.fromarray(np.dstack([(a[..., :3] * al).astype(np.uint8), a[..., 3].astype(np.uint8)]), 'RGBA')
        w, h = max(1, round(p.width * sc)), max(1, round(p.height * sc))
        q = np.asarray(pm.resize((w, h), Image.BOX)).astype(float)
        al = q[..., 3:4] / 255; rgb = np.where(al > 0, q[..., :3] / np.maximum(al, 1e-6), 0)
        a = np.dstack([np.clip(rgb, 0, 255).astype(np.uint8), np.where(q[..., 3] >= 115, 255, 0).astype(np.uint8)])
    else:
        a = np.asarray(p).copy(); a[..., 3] = np.where(a[..., 3] >= 128, 255, 0)
    if colors:
        rgb = Image.fromarray(a[..., :3], 'RGB').quantize(colors, method=Image.MEDIANCUT, dither=Image.NONE).convert('RGB')
        a[..., :3] = np.asarray(rgb)
    if outline:
        m = a[..., 3] > 0; pad = np.pad(m, 1, constant_values=False)
        ring = (pad[:-2, 1:-1] | pad[2:, 1:-1] | pad[1:-1, :-2] | pad[1:-1, 2:]) & ~m
        a[ring] = (26, 20, 38, 255)
    return Image.fromarray(a, 'RGBA')

def region_pieces(region, thr=70):
    sh, (x0, y0, x1, y1) = REGIONS[region]; arr = sheet(sh)[y0:y1, x0:x1]
    # 덩어리 나누기는 느슨한 문턱(70)으로(번호가 안정되게), 각 조각의 알파는 그 덩어리 근처(3px 팽창)에서 빡빡한 키잉(keyed)으로
    fg = foreground(arr, 'grid', thr); lab, boxes = components(fg, reach=3, min_px=40)
    tight = keyed(arr)
    out = []
    for (bx1, by1, bx2, by2, n) in boxes:
        m = (lab[by1:by2, bx1:bx2] == n); d = m.copy()
        for _ in range(3):
            pd = np.pad(d, 1, constant_values=False); d = d | pd[:-2, 1:-1] | pd[2:, 1:-1] | pd[1:-1, :-2] | pd[1:-1, 2:]
        m = d & tight[by1:by2, bx1:bx2]
        out.append(Image.fromarray(np.dstack([arr[by1:by2, bx1:bx2].astype(np.uint8), (m * 255).astype(np.uint8)]), 'RGBA'))
    return out

def contact(pieces, path, scale=1.0):
    pad = 6; x = y = 0; rowh = 0; W = 1600; cells_ = []
    for i, p in enumerate(pieces):
        if p is None: continue
        w, h = int(p.width * scale) + pad, int(p.height * scale) + pad + 12
        if x + w > W: x = 0; y += rowh; rowh = 0
        cells_.append((i, x, y, p)); x += w; rowh = max(rowh, h)
    im = Image.new('RGBA', (W, y + rowh + 12), (40, 40, 60, 255)); d = ImageDraw.Draw(im)
    for i, x, y, p in cells_:
        q = p if scale == 1 else p.resize((max(1, int(p.width * scale)), max(1, int(p.height * scale))), Image.NEAREST)
        im.alpha_composite(q, (x, y + 12)); d.text((x, y), str(i), fill=(255, 255, 0, 255))
    im.save(path)

def scan(outdir):
    os.makedirs(outdir, exist_ok=True)
    for g in GRIDS:
        cs = cells(g); contact([p for _, p in cs], os.path.join(outdir, g + '.png'), .5); print(g, len(cs), 'cells')
    for r in REGIONS:
        ps = region_pieces(r); contact(ps, os.path.join(outdir, r + '.png'), .5); print(r, len(ps), 'pieces')

# 이름 → ('g', 격자, 칸 번호, 최대 변 길이) 또는 ('r', 구역, 조각 번호, 최대 변 길이)[, 자르기 비율 (x0,y0,x1,y1)]
PICKS = {
    # ---- 선수(측면 달리기 프레임 _0.., 정면 대기 _i, 스프린트 틸트 _s, 라스트 스퍼트 _d, 승리 _w). 없는 포즈는 게임이 달리기 프레임으로 대신한다
    'spe_i': ('g', 'b_idle', 0, 60),
    'suzu_i': ('g', 'b_idle', 4, 60),
    'teio_i': ('g', 'b_idle', 10, 60),
    'gold_i': ('g', 'b_idle', 13, 60),
    'rudo_i': ('g', 'f_idle', 0, 60),
    'hime_i': ('g', 'f_idle', 18, 60),
    # 라이벌 전용(프레임이 적음)
    'blon_i': ('g', 'f_idle', 27, 60),
    'dark_i': ('g', 'f_idle', 9, 60),
    'rice_i': ('g', 'b_idle', 28, 60),
    # ---- 아이템
    'carrot': ('g', 'a_items', 0, 22), 'gcarrot': ('g', 'a_items', 2, 24), 'drink': ('g', 'a_items', 3, 22), 'shoe': ('g', 'a_items', 10, 22), 'potion': ('g', 'a_items', 11, 22),
    'gem': ('r', 'b_fx', 16, 20), 'heart': ('r', 'b_fx', 13, 20),
    # ---- 코스·소품
    'grass': ('g', 'a_track', 0, 96, (.04, .04, .96, .96)), 'dirt': ('g', 'c_track', 2, 96, (.04, .04, .96, .96)), 'snow': ('g', 'c_track', 3, 96, (.04, .04, .96, .96)),
    'crowd': ('r', 'e_props', 21, 220), 'arch': ('r', 'e_bottom', 4, 150),
    'sign200': ('r', 'e_props', 7, 48), 'sign400': ('r', 'e_props', 9, 48), 'signgoal': ('r', 'e_props', 10, 48), 'gate': ('r', 'e_props', 3, 120),
    'hurdle': ('r', 'd_props', 1, 40), 'mine': ('r', 'b_row4', 9, 24), 'boom': ('r', 'b_row4', 18, 64),
    'dust': ('r', 'b_fx', 25, 48), 'dust2': ('r', 'b_fx', 28, 56), 'wind': ('g', 'a_track', 3, 120, (.5, 0, 1, 1)), 'streak': ('g', 'a_track', 4, 110, (0, 0, .5, 1)),
    'podium': ('r', 'b_fx', 20, 96), 'trophy': ('r', 'a_boss', 17, 80), 'ura': ('r', 'c_boss', 4, 110), 'tape': ('r', 'b_fx', 23, 120),
    'camera': ('r', 'e_bottom', 45, 48), 'flag': ('r', 'e_bottom', 47, 40),
    # ---- 보스(스타팅 게이트 장치·스코어보드 장치·시계 마법진)와 디버프
    'boss_gate': ('r', 'a_boss', 8, 200), 'boss_board': ('r', 'c_boss', 2, 200), 'boss_clock': ('r', 'f_row4', 5, 170, (.4, .02, 1, .55)),
    'eye': ('g', 'c_track', 8, 40), 'vortex': ('g', 'c_part', 2, 48), 'spot': ('g', 'c_part', 1, 48),
    # ---- 필살 컷인·오라·스킬 FX·파티클
    'cut_blue': ('r', 'a_cutin', 0, 200), 'cut_sakura': ('r', 'a_cutin', 4, 200), 'cut_idol': ('r', 'c_cutin', 0, 200), 'cut_rocket': ('r', 'c_cutin', 2, 200),
    'aura_blue': ('g', 'e_aura', 9, 64), 'aura_red': ('g', 'e_aura', 10, 64), 'aura_gold': ('g', 'e_aura', 11, 64), 'tornado': ('g', 'e_aura', 0, 48),
    'bolt': ('g', 'd_fx', 1, 48), 'feather': ('r', 'f_fx', 30, 40), 'crown': ('r', 'f_fx', 0, 36), 'shoe_fx': ('r', 'f_fx', 32, 48),
    'spark': ('g', 'a_part', 0, 32), 'burst': ('g', 'a_part', 7, 48), 'drops': ('g', 'a_part', 2, 24),
    # ---- 훈련 카드 그림
    'tire': ('r', 'd_props', 0, 64), 'pool': ('r', 'd_props', 7, 90), 'uphill': ('r', 'd_props', 6, 90), 'downhill': ('r', 'd_props', 16, 90),
}

# 윤곽선을 두르지 않는 것(타일·효과·컷인·관중)과 색을 묶지 않는 것(컷인·보스·큰 소품)
NO_OUTLINE = ('grass', 'dirt', 'snow', 'crowd', 'dust', 'wind', 'streak', 'aura', 'tornado', 'bolt', 'spark', 'burst', 'drops', 'cut_', 'spot', 'eye', 'vortex', 'boom', 'shoe_fx', 'feather', 'tape', 'arch', 'crown')
NO_QUANT = ('cut_', 'boss_', 'crowd', 'arch', 'podium', 'trophy', 'ura', 'gate', 'grass', 'dirt', 'snow')

def main():
    if len(sys.argv) > 2 and sys.argv[1] == 'scan': scan(sys.argv[2]); return
    got = {}
    for name, spec in PICKS.items():
        kind, src, idx, maxdim = spec[:4]
        key = (kind, src)
        if key not in got: got[key] = [p for _, p in cells(src)] if kind == 'g' else region_pieces(src)
        p = got[key][idx]
        if len(spec) > 4:
            fx0, fy0, fx1, fy1 = spec[4]; p = p.crop((int(p.width * fx0), int(p.height * fy0), int(p.width * fx1), int(p.height * fy1)))
        out = fit(p, maxdim, outline=not name.startswith(NO_OUTLINE), colors=0 if name.startswith(NO_QUANT) else 40)
        out.save(os.path.join(HERE, name + '.png')); print(name, out.size)

if __name__ == '__main__':
    main()
