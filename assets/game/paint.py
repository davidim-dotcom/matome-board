#!/usr/bin/env python3
"""弾幕 탭 그림 생성기(일러스트형 픽셀 아트).
   python3 assets/game/paint.py              → assets/game/*.png
   python3 assets/game/paint.py preview.png  → 확대 미리보기 한 장
각 그림을 목표 크기의 SS배로 그라데이션·광원·반투명으로 그린 뒤 LANCZOS 로 줄이고, 색을 N개로 제한하고
알파를 이진화해 '도트' 느낌을 만든다. 캐릭터에는 1px 어두운 외곽선을 두른다.
그림을 바꾸려면 아래 draw_* 함수를 고치거나, 같은 크기의 PNG 로 교체하면 된다(게임은 파일만 읽는다)."""
import sys, os, math, random
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

SS = 6
HERE = os.path.dirname(os.path.abspath(__file__))

def hexrgb(c): return tuple(int(c[i:i+2], 16) for i in (1, 3, 5))
def mix(a, b, t): return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(len(a)))

class Painter:
    """목표 크기 (w,h) 단위로 그리면 내부에서 ss배로 그린다."""
    def __init__(self, w, h, ss=SS): self.w, self.h, self.ss = w, h, ss; self.im = Image.new('RGBA', (w * ss, h * ss), (0, 0, 0, 0))
    def s(self, v): return v * self.ss
    def _mask(self, fn):
        m = Image.new('L', self.im.size, 0); d = ImageDraw.Draw(m); fn(d, 255); return m
    def _grad(self, c1, c2, kind, p1, p2, alpha, bbox):
        x0, y0, x1b, y1b = bbox; c1, c2 = np.array(hexrgb(c1), float), np.array(hexrgb(c2), float)
        X, Y = np.meshgrid(np.arange(x0, x1b), np.arange(y0, y1b))
        ax, ay, bx, by = self.s(p1[0]), self.s(p1[1]), self.s(p2[0]), self.s(p2[1])
        if kind == 'lin':
            dx, dy = bx - ax, by - ay; t = ((X - ax) * dx + (Y - ay) * dy) / ((dx * dx + dy * dy) or 1)
        else:  # 'rad': p1 중심, p2[0] 반지름
            t = np.hypot(X - ax, Y - ay) / max(1, bx)
        t = np.clip(t, 0, 1)[..., None]
        rgb = c1 + (c2 - c1) * t
        arr = np.concatenate([rgb, np.full(rgb.shape[:2] + (1,), alpha, float)], axis=2)
        return Image.fromarray(arr.astype(np.uint8), 'RGBA')
    def fill(self, fn, c1, c2=None, kind='lin', p1=(0, 0), p2=(0, 1), alpha=255):
        """fn(d, v)는 ImageDraw d 에 모양을 그린다(채움값 v). c2 가 없으면 단색."""
        m = self._mask(fn); bbox = m.getbbox()
        if not bbox: return
        if c2 is None:
            layer = Image.new('RGBA', (bbox[2] - bbox[0], bbox[3] - bbox[1]), hexrgb(c1) + (alpha,))
        else:
            layer = self._grad(c1, c2, kind, p1, p2, alpha, bbox)
        self.im.paste(layer, (bbox[0], bbox[1]), m.crop(bbox))
    # 모양 도우미(목표 단위 좌표)
    def ellipse(self, box, **kw): self.fill(lambda d, v: d.ellipse([self.s(b) for b in box], fill=v), **kw)
    def poly(self, pts, **kw): self.fill(lambda d, v: d.polygon([(self.s(x), self.s(y)) for x, y in pts], fill=v), **kw)
    def rect(self, box, **kw): self.fill(lambda d, v: d.rectangle([self.s(b) for b in box], fill=v), **kw)
    def line(self, pts, color, width=1, alpha=255):
        d = ImageDraw.Draw(self.im); d.line([(self.s(x), self.s(y)) for x, y in pts], fill=hexrgb(color) + (alpha,), width=max(1, round(self.s(width))))
    def glow(self, center, r, color, alpha=160, blur=1.5):
        g = Image.new('RGBA', self.im.size, (0, 0, 0, 0)); d = ImageDraw.Draw(g)
        cx, cy, rr = self.s(center[0]), self.s(center[1]), self.s(r)
        d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=hexrgb(color) + (alpha,))
        g = g.filter(ImageFilter.GaussianBlur(self.s(blur))); self.im.alpha_composite(g)
    def mirror_x(self): return self  # (대칭은 각 함수에서 직접 그린다)
    def done(self, colors=48, outline='#1b1230', pixel_alpha=True):
        im = self.im.resize((self.w, self.h), Image.LANCZOS)
        a = im.getchannel('A')
        if pixel_alpha: a = a.point(lambda v: 255 if v >= 110 else 0)
        rgb = im.convert('RGB').quantize(colors=colors, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE).convert('RGB')
        out = Image.new('RGBA', (self.w, self.h), (0, 0, 0, 0)); out.paste(rgb, (0, 0), a)
        if outline:
            px = out.load(); src = out.copy().load(); oc = hexrgb(outline) + (255,)
            for y in range(self.h):
                for x in range(self.w):
                    if src[x, y][3] == 0 and any(0 <= x + dx < self.w and 0 <= y + dy < self.h and src[x + dx, y + dy][3] > 0 for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                        px[x, y] = oc
        return out

# ---------------- 공통: 미소녀풍 얼굴 ----------------
# 기준(조사): 눈은 머리 세로의 약 1/3 크기, 얼굴 가로선보다 조금 아래, 좌우 간격은 넓게. 이마는 크고 턱은 작게.
def head(p, cx, top, S, hair1, hair2, iris1, iris2, strands='#4a2399', mouth='#c94a6a', eye=1.0, bangs=True, hl=None):
    """폭 S 의 머리를 (cx, top) 아래에 그린다: 얼굴 → 앞머리 → 눈 → 볼 → 입. 눈 크기는 eye 배율."""
    p.ellipse((cx - S / 2, top + S * .12, cx + S / 2, top + S * 1.08), c1='#fff0e6', c2='#f0bfa8', kind='rad', p1=(cx - S * .15, top + S * .4), p2=(S * .65, 0))
    if bangs:
        pts = [(cx - S / 2, top + S * .38)]
        for i in range(8):
            t = i / 7; x = cx - S / 2 + S * t; pts.append((x, top + S * (.55 if i % 2 else .42) + (S * .08 if i in (3, 4) else 0)))
        pts += [(cx + S / 2, top + S * .38), (cx + S / 2, top + S * .2), (cx + S * .2, top - S * .02), (cx, top - S * .05), (cx - S * .2, top - S * .02), (cx - S / 2, top + S * .2)]
        p.poly(pts, c1=hair1, c2=hair2, kind='lin', p1=(cx - S * .4, top), p2=(cx + S * .4, top + S * .55))
        for i in range(4):
            x = cx - S * .38 + i * S * .25; p.line([(x, top + S * .12), (x + (i - 1.5) * S * .04, top + S * .42)], strands, S * .03, 140)
        p.poly([(cx - S * .35, top + S * .08), (cx - S * .05, top + S * .02), (cx - S * .15, top + S * .22), (cx - S * .4, top + S * .26)], c1=hl or '#ffffff', alpha=70)
    eh, ew = S * .30 * eye, S * .21 * eye; ey = top + S * .53
    for sx in (-1, 1):
        ex = cx + sx * S * .26 - ew / 2
        p.ellipse((ex, ey, ex + ew, ey + eh), c1='#ffffff', c2='#e6e8f4', kind='lin', p1=(0, ey), p2=(0, ey + eh))
        p.ellipse((ex + ew * .12, ey + eh * .12, ex + ew * .88, ey + eh * .98), c1=iris1, c2=iris2, kind='lin', p1=(0, ey), p2=(0, ey + eh))
        p.ellipse((ex + ew * .3, ey + eh * .42, ex + ew * .72, ey + eh * .9), c1='#1a0a3a')
        p.ellipse((ex + ew * .18, ey + eh * .18, ex + ew * .46, ey + eh * .42), c1='#ffffff')
        p.line([(ex - ew * .1, ey + eh * .05), (ex + ew * 1.1, ey - eh * .05)], '#2a1a3a', S * .035)
    p.ellipse((cx - S * .45, top + S * .76, cx - S * .22, top + S * .86), c1='#ff8fb0', alpha=110); p.ellipse((cx + S * .22, top + S * .76, cx + S * .45, top + S * .86), c1='#ff8fb0', alpha=110)
    p.ellipse((cx - S * .05, top + S * .9, cx + S * .05, top + S * .96), c1=mouth)

# ---------------- 자기: 森の小魔女(보라 머리, 마녀 모자, 줄무늬 스타킹) 32×48 ----------------
def draw_player():
    p = Painter(32, 48); M = lambda pts: [(32 - x, y) for x, y in pts]
    HAIR1, HAIR2 = '#b58cff', '#5e2fb8'; PINK, DARK = '#ff79c6', '#2a1446'
    tail = [(4.5, 16), (9.5, 16), (10.5, 36), (6.5, 41), (2.5, 36)]
    for q in (tail, M(tail)): p.poly(q, c1=HAIR1, c2=HAIR2, kind='lin', p1=(0, 16), p2=(0, 41))
    for x0 in (4.5, 23.5):
        p.line([(x0 + 1, 18), (x0 + .5, 35)], '#4a2399', .6, 150); p.poly([(x0 + .9, 18), (x0 + 2.6, 18), (x0 + 2.6, 30), (x0 + 1.3, 32)], c1='#e2ccff', alpha=90)
    for x in (12.2, 16.8):
        p.rect((x, 36.5, x + 3, 45), c1='#6a3fc4', c2='#3d2080', kind='lin', p1=(x, 0), p2=(x + 3, 0))
        for yy in (37.5, 39.5, 41.5, 43.5): p.rect((x, yy, x + 3, yy + 1), c1=PINK, alpha=230)
    for x in (11.7, 16.3): p.ellipse((x, 43.5, x + 4, 47.2), c1='#3a2a5c', c2='#160b2a', kind='lin', p1=(0, 43), p2=(0, 47))
    p.poly([(10.5, 31), (21.5, 31), (25, 38.5), (7, 38.5)], c1='#5a3a9a', c2='#241347', kind='lin', p1=(0, 31), p2=(0, 38.5))
    p.poly([(7.6, 37), (24.4, 37), (25, 38.5), (7, 38.5)], c1=PINK, c2='#c23f93', kind='lin', p1=(0, 37), p2=(0, 38.5))
    for x in (11, 14.5, 17.5, 21): p.line([(x, 32), (x - 1 + (x - 16) * .25, 36.8)], '#1a0d33', .6, 140)
    p.poly([(11.5, 25), (20.5, 25), (21.6, 32), (10.4, 32)], c1='#6b47b3', c2='#2f1a66', kind='lin', p1=(0, 25), p2=(0, 32))
    p.poly([(11, 25), (21, 25), (16, 29)], c1='#ffffff', c2='#d8dcf0', kind='lin', p1=(0, 25), p2=(0, 29))
    p.poly([(16, 27.4), (13.8, 29.6), (16, 29), (18.2, 29.6)], c1=PINK)
    for lx in (8.2, 19.8):
        p.ellipse((lx, 26, lx + 4, 31), c1='#6b47b3', c2='#2f1a66', kind='lin', p1=(0, 26), p2=(0, 31)); p.rect((lx + .3, 29.4, lx + 3.7, 30.3), c1=PINK, alpha=220)
    p.ellipse((8.9, 30, 11.6, 32.8), c1='#ffe3d2', c2='#e8b9a4', kind='lin', p1=(0, 30), p2=(0, 33)); p.ellipse((20.4, 30, 23.1, 32.8), c1='#ffe3d2', c2='#e8b9a4', kind='lin', p1=(0, 30), p2=(0, 33))
    p.rect((14.5, 23, 17.5, 26), c1='#f0c7b2')
    head(p, 16, 8, 19, HAIR1, HAIR2, '#e0a0ff', '#4a1aa8')
    # 마녀 모자
    p.ellipse((3, 8, 29, 14.2), c1='#4a2d8a', c2=DARK, kind='lin', p1=(0, 8), p2=(0, 14))
    p.poly([(8, 11), (24, 11), (21, 1.5), (15.5, -1), (13, 3)], c1='#6b47b3', c2='#2a1446', kind='lin', p1=(10, 0), p2=(24, 11))
    p.poly([(8.3, 10.8), (23.7, 10.8), (22.9, 8.3), (9.1, 8.3)], c1=PINK, c2='#c23f93', kind='lin', p1=(0, 8), p2=(0, 11))
    for x in (10.5, 13.5, 16.5, 19.5, 22.5): p.rect((x, 8.3, x + 1.4, 10.8), c1=DARK, alpha=210)
    p.ellipse((20.5, 4, 23, 6.5), c1='#ffe68a', c2='#d9a63a', kind='rad', p1=(21.3, 4.8), p2=(1.4, 0))
    p.glow((22, 30.5), 3.2, '#ff9ae0', 150, 1.2); p.ellipse((20.6, 29.2, 23.4, 32), c1='#ffffff', c2='#c23f93', kind='rad', p1=(21.4, 30), p2=(1.6, 0))
    return p.done(colors=64)

# ---------------- 잡몹: キノコの精 24×24 / ウィスプ 24×24 ----------------
def draw_mush():
    p = Painter(24, 24)
    p.rect((8.5, 11, 15.5, 21.5), c1='#fff3dc', c2='#d9b78f', kind='lin', p1=(8, 0), p2=(16, 0))
    p.ellipse((7, 20, 11, 23), c1='#c99a6b'); p.ellipse((13, 20, 17, 23), c1='#c99a6b')
    p.ellipse((2, 3, 22, 15), c1='#ff6a6a', c2='#a51a2c', kind='rad', p1=(8, 6), p2=(14, 0))
    p.rect((2, 11, 22, 13.5), c1='#8a1626', alpha=120)
    for cx, cy, r in ((7, 7, 1.6), (13.5, 5, 1.3), (17, 9, 1.4), (10.5, 10.5, .9)):
        p.ellipse((cx - r, cy - r, cx + r, cy + r), c1='#fff6f0', c2='#f0d8c8', kind='lin', p1=(0, cy - r), p2=(0, cy + r))
    p.ellipse((10, 14.5, 11.6, 17), c1='#2a1a3a'); p.ellipse((13, 14.5, 14.6, 17), c1='#2a1a3a')
    p.ellipse((10.3, 14.8, 10.9, 15.5), c1='#ffffff'); p.ellipse((13.3, 14.8, 13.9, 15.5), c1='#ffffff')
    p.ellipse((9, 17.3, 10.6, 18.3), c1='#ff9a9a', alpha=150); p.ellipse((13.8, 17.3, 15.4, 18.3), c1='#ff9a9a', alpha=150)
    p.ellipse((11.5, 18, 12.9, 18.9), c1='#9e3a3a')
    return p.done(colors=40)

def draw_wisp():
    p = Painter(24, 24)
    p.glow((12, 14), 8, '#4fd0ff', 120, 2)
    p.poly([(12, 1), (16, 7), (19.5, 13), (18, 20), (12, 23), (6, 20), (4.5, 13), (8, 7)], c1='#bffcff', c2='#2f6fe0', kind='lin', p1=(0, 3), p2=(0, 23))
    p.poly([(12, 6), (15, 11), (16, 16), (12, 20), (8, 16), (9, 11)], c1='#ffffff', c2='#7df9ff', kind='lin', p1=(0, 6), p2=(0, 20), alpha=200)
    p.ellipse((8.5, 11.5, 10.8, 15.5), c1='#1a2e6b'); p.ellipse((13.2, 11.5, 15.5, 15.5), c1='#1a2e6b')
    p.ellipse((9, 12, 9.9, 13), c1='#ffffff'); p.ellipse((13.7, 12, 14.6, 13), c1='#ffffff')
    p.ellipse((11.2, 16.5, 12.8, 17.6), c1='#1a2e6b', alpha=180)
    return p.done(colors=40, outline='#163a6b')

# ---------------- 중보스: 宝箱ゴーレム 40×40 ----------------
def draw_chest():
    p = Painter(40, 40)
    p.glow((20, 17), 9, '#ffd166', 130, 2.2)
    # 뚜껑(열림)
    p.poly([(5, 14), (35, 14), (37, 4), (3, 4)], c1='#8a5a2b', c2='#4a2c12', kind='lin', p1=(0, 4), p2=(0, 14))
    p.rect((3, 3, 37, 6.5), c1='#c89a52', c2='#8c6a2e', kind='lin', p1=(0, 3), p2=(0, 7))
    for x in (8, 32): p.rect((x - 1.5, 4, x + 1.5, 14), c1='#e0b45a', c2='#9a7230', kind='lin', p1=(0, 4), p2=(0, 14))
    # 안쪽 어둠 + 눈
    p.rect((6, 13.5, 34, 19), c1='#1a0f24')
    for x in (13, 24): p.ellipse((x, 14.5, x + 3.5, 18), c1='#ffe36b', c2='#ff8a2a', kind='rad', p1=(x + 1.2, 15.8), p2=(2, 0))
    p.rect((10, 17.5, 30, 19), c1='#fff2b0', alpha=140)
    # 몸통
    p.rect((5, 19, 35, 36), c1='#9a6433', c2='#4f2f14', kind='lin', p1=(0, 19), p2=(0, 36))
    p.rect((5, 19, 35, 21.5), c1='#c89a52', c2='#8c6a2e', kind='lin', p1=(0, 19), p2=(0, 22))
    for x in (8, 32): p.rect((x - 1.5, 19, x + 1.5, 36), c1='#e0b45a', c2='#9a7230', kind='lin', p1=(0, 19), p2=(0, 36))
    p.rect((17.5, 22, 22.5, 28), c1='#ffd166', c2='#b8862a', kind='lin', p1=(0, 22), p2=(0, 28)); p.ellipse((19, 24, 21, 26), c1='#2a1a0a')
    for x in (10, 25): p.line([(x, 23), (x + 5, 23)], '#6b4420', .7, 160); p.line([(x, 30), (x + 5, 30)], '#6b4420', .7, 160)
    # 발
    for x in (7, 27): p.ellipse((x, 34.5, x + 6, 39), c1='#5a3a1c', c2='#2e1a0a', kind='lin', p1=(0, 34), p2=(0, 39))
    return p.done(colors=48)

# ---------------- 보스 1: 森の魔女「ノイズ」 56×72 (초록 망토·보라 모자·지팡이) ----------------
def draw_boss():
    p = Painter(56, 72)
    p.line([(46, 26), (49, 66)], '#5a3a1c', 1.6); p.glow((45.5, 24), 5, '#9dffb0', 170, 1.6)
    p.ellipse((42.5, 21, 48.5, 27), c1='#ffffff', c2='#2fbf6b', kind='rad', p1=(44.5, 23), p2=(3.2, 0))
    p.poly([(15, 24), (41, 24), (45, 54), (39, 67), (17, 67), (11, 54)], c1='#4a3a8a', c2='#1a1033', kind='lin', p1=(0, 24), p2=(0, 67))
    for x in (16, 22, 34, 40): p.line([(x, 28), (x + (x - 28) * .2, 64)], '#2a1d5c', .7, 120)
    p.poly([(17, 42), (39, 42), (46, 68), (10, 68)], c1='#2f7a4f', c2='#0e2e1e', kind='lin', p1=(0, 42), p2=(0, 68))
    for x in (19, 25, 31, 37): p.line([(x, 46), (x + (x - 28) * .25, 67)], '#0a2015', .8, 120)
    p.poly([(17, 42), (39, 42), (28, 48)], c1='#ffd166', c2='#b8862a', kind='lin', p1=(0, 42), p2=(0, 48))
    p.ellipse((8, 42, 18, 54), c1='#2f7a4f', c2='#143d28', kind='lin', p1=(0, 42), p2=(0, 54)); p.ellipse((38, 42, 48, 54), c1='#2f7a4f', c2='#143d28', kind='lin', p1=(0, 42), p2=(0, 54))
    p.ellipse((11, 51, 16, 56), c1='#ffe3d2', c2='#e8b9a4', kind='lin', p1=(0, 51), p2=(0, 56)); p.ellipse((43, 50, 48, 55), c1='#ffe3d2', c2='#e8b9a4', kind='lin', p1=(0, 50), p2=(0, 55))
    p.rect((25.5, 38, 30.5, 43), c1='#f0c7b2')
    head(p, 28, 16, 24, '#6a55b8', '#2d2060', '#e0a0ff', '#5a1aa8', strands='#241a50')
    p.ellipse((3, 14, 53, 23.5), c1='#4a3a8a', c2='#1d1540', kind='lin', p1=(0, 14), p2=(0, 24))
    p.poly([(13, 18.5), (43, 18.5), (37, 2), (27, -2), (23, 4)], c1='#6b55c4', c2='#2a1d5c', kind='lin', p1=(20, 2), p2=(40, 19))
    p.poly([(13.6, 18.2), (42.4, 18.2), (41.2, 14.8), (14.8, 14.8)], c1='#ffd166', c2='#b8862a', kind='lin', p1=(0, 15), p2=(0, 18))
    p.ellipse((36, 12.5, 40, 16.5), c1='#ff6b85', c2='#c91d3e', kind='lin', p1=(0, 12), p2=(0, 17))
    return p.done(colors=64)

# ================= 2스테이지 電脳都市: ドローン · ホロ · 自販機ゴーレム · 電脳アイドル「ビット」 =================
def draw_drone():
    p = Painter(24, 24)
    for dx, dy in ((-7, -5), (7, -5), (-7, 5), (7, 5)):
        p.line([(12, 12), (12 + dx, 12 + dy)], '#4a4e66', 1.4); p.ellipse((12 + dx - 5, 12 + dy - 1.6, 12 + dx + 5, 12 + dy + 1.6), c1='#9aa0b8', c2='#4a4e66', kind='lin', p1=(0, 12 + dy - 2), p2=(0, 12 + dy + 2), alpha=200)
    p.ellipse((6, 6.5, 18, 17.5), c1='#c9d3e6', c2='#4f5878', kind='rad', p1=(9.5, 9.5), p2=(8, 0))
    p.ellipse((8.5, 9.5, 15.5, 15), c1='#1a1f3a'); p.ellipse((10, 10.5, 14, 14), c1='#ff5c5c', c2='#8a0f1f', kind='rad', p1=(11.3, 11.6), p2=(2.4, 0)); p.ellipse((10.6, 11, 11.8, 12.2), c1='#ffffff')
    p.glow((12, 12.3), 2.5, '#ff5c5c', 90, .8)
    return p.done(colors=40, outline='#141828')
def draw_holo():
    p = Painter(24, 24)
    p.glow((12, 12), 8, '#ff5cf0', 90, 2)
    p.poly([(12, 2), (19, 6), (20, 16), (16, 22), (8, 22), (4, 16), (5, 6)], c1='#ffb8f5', c2='#8a1fb0', kind='lin', p1=(0, 2), p2=(0, 22), alpha=210)
    for y in range(4, 22, 2): p.line([(5, y), (19, y)], '#ffffff', .4, 60)
    p.ellipse((7.5, 9, 10.5, 13.5), c1='#2a0a3a'); p.ellipse((13.5, 9, 16.5, 13.5), c1='#2a0a3a')
    p.ellipse((8, 9.5, 9.2, 10.8), c1='#ffffff'); p.ellipse((14, 9.5, 15.2, 10.8), c1='#ffffff')
    p.rect((9.5, 16, 14.5, 17.2), c1='#2a0a3a', alpha=180)
    p.rect((3, 7, 21, 8), c1='#ffffff', alpha=90); p.rect((4, 15, 20, 16), c1='#ffffff', alpha=70)
    return p.done(colors=40, outline='#4a1060')
def draw_vending():
    p = Painter(40, 40)
    p.rect((7, 3, 33, 37), c1='#e0484f', c2='#7a1a2a', kind='lin', p1=(7, 0), p2=(33, 0))
    p.rect((7, 3, 33, 6), c1='#ff8a90', c2='#c23a44', kind='lin', p1=(0, 3), p2=(0, 6))
    p.glow((16, 13), 8, '#9fe3ff', 100, 1.5); p.rect((9.5, 7.5, 24, 20), c1='#bfeeff', c2='#3a7fb8', kind='lin', p1=(0, 8), p2=(0, 20))
    for r, cols in ((9.5, ['#ff5c5c', '#ffd166', '#5ad1ff', '#7ad96b']), (14, ['#ffd166', '#ff5c5c', '#c77dff', '#5ad1ff'])):
        for i, c in enumerate(cols): p.rect((10.5 + i * 3.4, r, 12.8 + i * 3.4, r + 3.6), c1=c)
    p.rect((26, 8, 31.5, 14), c1='#1a1f3a'); p.ellipse((27.3, 9.3, 30.2, 12.2), c1='#ffd166', c2='#ff8a2a', kind='rad', p1=(28.3, 10.3), p2=(1.6, 0))
    p.rect((26, 16, 31.5, 18), c1='#1a1f3a'); p.rect((9.5, 24, 30.5, 31), c1='#2a1f2a', c2='#120a12', kind='lin', p1=(0, 24), p2=(0, 31))
    p.rect((11, 26, 29, 29), c1='#3a2a3a')
    for x in (3, 33): p.rect((x, 20, x + 4, 30), c1='#9aa0b8', c2='#4a4e66', kind='lin', p1=(x, 0), p2=(x + 4, 0)); p.ellipse((x - .5, 29, x + 4.5, 33.5), c1='#c9d3e6', c2='#4a4e66', kind='lin', p1=(0, 29), p2=(0, 34))
    p.rect((9, 35, 15, 39), c1='#3a3a4a'); p.rect((25, 35, 31, 39), c1='#3a3a4a')
    return p.done(colors=48)
def draw_boss2():
    p = Painter(56, 72)
    p.glow((28, 44), 16, '#5ad1ff', 50, 4)
    for r in (22, 25): p.fill(lambda d, v, r=r: d.ellipse([p.s(28 - r), p.s(44 - r * .35), p.s(28 + r), p.s(44 + r * .35)], outline=v, width=max(1, round(p.s(.7)))), c1='#7df9ff', alpha=150)
    # 트윈 번 머리(하늘색)
    for cx in (13, 43): p.ellipse((cx - 6, 8, cx + 6, 20), c1='#9ff6ff', c2='#2a8fb8', kind='rad', p1=(cx - 2, 11), p2=(7, 0)); p.ellipse((cx - 4, 9.5, cx - 1, 11.5), c1='#ffffff', alpha=70)
    for cx, dx in ((15, -1), (41, 1)): p.poly([(cx, 18), (cx + dx * 4, 18), (cx + dx * 6, 48), (cx + dx * 1, 52)], c1='#7fe8ff', c2='#1f6f9a', kind='lin', p1=(0, 18), p2=(0, 52))
    # 몸: 아이돌 드레스(흰/하늘, LED 줄)
    p.poly([(19, 42), (37, 42), (43, 66), (13, 66)], c1='#ffffff', c2='#9fd8f0', kind='lin', p1=(0, 42), p2=(0, 66))
    for y in (50, 56, 62): p.line([(16 + (y - 42) * .25, y), (40 - (y - 42) * .25, y)], '#ff5cf0', .9, 200)
    p.poly([(20, 42), (36, 42), (28, 48)], c1='#5ad1ff', c2='#2a8fb8', kind='lin', p1=(0, 42), p2=(0, 48))
    p.ellipse((12, 42, 21, 52), c1='#ffffff', c2='#9fd8f0', kind='lin', p1=(0, 42), p2=(0, 52)); p.ellipse((35, 42, 44, 52), c1='#ffffff', c2='#9fd8f0', kind='lin', p1=(0, 42), p2=(0, 52))
    p.ellipse((13, 50, 18, 55), c1='#ffe3d2', c2='#e8b9a4', kind='lin', p1=(0, 50), p2=(0, 55)); p.ellipse((38, 50, 43, 55), c1='#ffe3d2', c2='#e8b9a4', kind='lin', p1=(0, 50), p2=(0, 55))
    for x in (22, 31): p.rect((x, 64, x + 3.5, 70), c1='#9fd8f0', c2='#5a8fb0', kind='lin', p1=(x, 0), p2=(x + 3.5, 0))
    p.rect((25.5, 38, 30.5, 43), c1='#f0c7b2')
    head(p, 28, 14, 24, '#9ff6ff', '#2a8fb8', '#ff9ae0', '#a01aa8', strands='#1f6f9a')
    # 헤드셋 + 마이크
    p.fill(lambda d, v: d.arc([p.s(15), p.s(12), p.s(41), p.s(34)], 190, 350, fill=v, width=max(1, round(p.s(1.6)))), c1='#2a2f4a')
    for x in (14, 38): p.rect((x, 24, x + 4, 31), c1='#3a3f5a', c2='#1a1f2a', kind='lin', p1=(x, 0), p2=(x + 4, 0)); p.ellipse((x + .8, 26, x + 3.2, 28.4), c1='#5ad1ff')
    p.line([(18, 30), (23, 36)], '#2a2f4a', .9); p.ellipse((22, 35, 25, 38), c1='#ff5cf0')
    p.poly([(24, 4), (32, 4), (34, 10), (22, 10)], c1='#ff5cf0', c2='#a01aa8', kind='lin', p1=(0, 4), p2=(0, 10))  # 리본
    return p.done(colors=64)

# ================= 3스테이지 月夜の神社: 狐火 · 式神 · 狛犬 · 月の巫女「ルナ」 =================
def draw_foxfire():
    p = Painter(24, 24); p.glow((12, 14), 8, '#ffb347', 120, 2)
    p.poly([(12, 1), (16.5, 8), (19.5, 14), (18, 20.5), (12, 23), (6, 20.5), (4.5, 14), (7.5, 8)], c1='#fff0a0', c2='#ff6a1a', kind='lin', p1=(0, 3), p2=(0, 23))
    p.poly([(12, 7), (15, 12), (15.5, 17), (12, 20), (8.5, 17), (9, 12)], c1='#ffffff', c2='#ffd166', kind='lin', p1=(0, 7), p2=(0, 20), alpha=210)
    p.poly([(8, 12), (10.5, 15.5), (8.5, 15)], c1='#8a2a0a'); p.poly([(16, 12), (13.5, 15.5), (15.5, 15)], c1='#8a2a0a')
    p.ellipse((10.8, 16.5, 13.2, 17.8), c1='#8a2a0a', alpha=180)
    return p.done(colors=40, outline='#6b2a0a')
def draw_shiki():
    p = Painter(24, 24)
    p.poly([(12, 1.5), (16, 5), (15, 9), (18, 12), (16, 22), (8, 22), (6, 12), (9, 9), (8, 5)], c1='#ffffff', c2='#d8d0c0', kind='lin', p1=(6, 2), p2=(18, 22))
    p.poly([(12, 4), (14.5, 7), (12, 9.5), (9.5, 7)], c1='#e63950')
    p.line([(10, 12), (10, 14.5)], '#2a1a3a', .9); p.line([(14, 12), (14, 14.5)], '#2a1a3a', .9)
    p.line([(9.5, 16.5), (14.5, 16.5)], '#e63950', .7); p.line([(12, 18), (12, 21)], '#e63950', .6, 160)
    p.line([(8, 11), (16, 11)], '#bfb4a0', .5, 160)
    return p.done(colors=32, outline='#3a2a3a')
def draw_komainu():
    p = Painter(40, 40)
    p.ellipse((6, 10, 34, 36), c1='#c9cdd8', c2='#5c6180', kind='rad', p1=(15, 18), p2=(20, 0))
    for cx, cy in ((9, 12), (31, 12)): p.ellipse((cx - 4, cy - 3, cx + 4, cy + 3), c1='#dfe3ec', c2='#7a8098', kind='rad', p1=(cx - 1, cy - 1), p2=(4, 0))
    for i in range(9):
        a = -math.pi * .95 + i * math.pi * .9 / 8; cx, cy = 20 + math.cos(a) * 13, 24 + math.sin(a) * 12
        p.ellipse((cx - 3, cy - 3, cx + 3, cy + 3), c1='#e3e7ef', c2='#6c7290', kind='rad', p1=(cx - 1, cy - 1), p2=(3.5, 0))
    p.ellipse((10, 14, 30, 30), c1='#e6e9f1', c2='#8a90a8', kind='rad', p1=(16, 19), p2=(12, 0))
    p.poly([(14, 25), (26, 25), (24, 32), (16, 32)], c1='#e63950', c2='#9e1f36', kind='lin', p1=(0, 25), p2=(0, 32))
    p.ellipse((12.5, 18, 17.5, 22.5), c1='#1a1f3a'); p.ellipse((22.5, 18, 27.5, 22.5), c1='#1a1f3a')
    p.ellipse((13.5, 19, 16.5, 21.5), c1='#ffd166', c2='#ff8a2a', kind='rad', p1=(14.5, 19.8), p2=(1.6, 0)); p.ellipse((23.5, 19, 26.5, 21.5), c1='#ffd166', c2='#ff8a2a', kind='rad', p1=(24.5, 19.8), p2=(1.6, 0))
    p.poly([(16, 24), (24, 24), (20, 28)], c1='#3a3f5a'); p.poly([(18, 28), (22, 28), (21, 31), (19, 31)], c1='#ffffff')
    p.ellipse((8, 31, 16, 37), c1='#c9cdd8', c2='#5c6180', kind='lin', p1=(0, 31), p2=(0, 37)); p.ellipse((24, 31, 32, 37), c1='#c9cdd8', c2='#5c6180', kind='lin', p1=(0, 31), p2=(0, 37))
    return p.done(colors=40, outline='#20233a')
def draw_boss3():
    p = Painter(56, 72)
    p.glow((48, 16), 6, '#ffe9a8', 170, 2); p.line([(46, 22), (43, 60)], '#e0c08a', 1.3)
    p.ellipse((44, 11, 52, 19), c1='#ffffff', c2='#ffd166', kind='rad', p1=(46.5, 13.5), p2=(4.5, 0))
    for y in (24, 28, 32): p.poly([(45.5 - (y - 22) * .1, y), (49, y), (50, y + 3), (46, y + 3)], c1='#ffffff', c2='#e6e8f4', kind='lin', p1=(0, y), p2=(0, y + 3))
    # 은백색 긴 머리(뒤)
    p.poly([(14, 22), (42, 22), (46, 50), (42, 70), (14, 70), (10, 50)], c1='#f4f1ff', c2='#9a93c8', kind='lin', p1=(0, 22), p2=(0, 70))
    for x in (15, 22, 34, 41): p.line([(x, 26), (x + (x - 28) * .18, 68)], '#b8b0e0', .7, 140)
    # 하카마(빨강) + 흰 상의
    p.poly([(16, 46), (40, 46), (44, 70), (12, 70)], c1='#e63950', c2='#8e1a2e', kind='lin', p1=(0, 46), p2=(0, 70))
    for x in (20, 28, 36): p.line([(x, 48), (x + (x - 28) * .2, 69)], '#6b1020', .8, 150)
    p.poly([(18, 40), (38, 40), (40, 48), (16, 48)], c1='#ffffff', c2='#d8dcf0', kind='lin', p1=(0, 40), p2=(0, 48))
    p.poly([(21, 40), (35, 40), (28, 47)], c1='#e63950', alpha=200)
    p.poly([(8, 41), (20, 41), (20, 54), (6, 54)], c1='#ffffff', c2='#d8dcf0', kind='lin', p1=(0, 41), p2=(0, 54)); p.poly([(36, 41), (48, 41), (50, 54), (36, 54)], c1='#ffffff', c2='#d8dcf0', kind='lin', p1=(0, 41), p2=(0, 54))
    p.line([(8, 52), (20, 52)], '#e63950', .9); p.line([(36, 52), (50, 52)], '#e63950', .9)
    p.ellipse((10, 52, 15, 57), c1='#ffe3d2', c2='#e8b9a4', kind='lin', p1=(0, 52), p2=(0, 57)); p.ellipse((42, 52, 47, 57), c1='#ffe3d2', c2='#e8b9a4', kind='lin', p1=(0, 52), p2=(0, 57))
    p.rect((25.5, 36, 30.5, 41), c1='#f0c7b2')
    head(p, 28, 12, 24, '#fbf8ff', '#a8a0d8', '#ffd166', '#b86a10', strands='#b8b0e0', hl='#ffffff')
    # 여우 귀 + 리본
    for cx, dx in ((17, -1), (39, 1)):
        p.poly([(cx - 5, 16), (cx + 5, 16), (cx + dx * 2, 2)], c1='#fbf8ff', c2='#a8a0d8', kind='lin', p1=(0, 2), p2=(0, 16)); p.poly([(cx - 2.5, 14.5), (cx + 2.5, 14.5), (cx + dx * 1.2, 6)], c1='#ffb3c7')
    p.poly([(28, 12), (22, 8), (23, 15)], c1='#e63950', c2='#9e1f36', kind='lin', p1=(0, 8), p2=(0, 15)); p.poly([(28, 12), (34, 8), (33, 15)], c1='#e63950', c2='#9e1f36', kind='lin', p1=(0, 8), p2=(0, 15)); p.ellipse((26.5, 10.5, 29.5, 13.5), c1='#ff8aa0')
    return p.done(colors=64)

# ---------------- 아이템 14×14: 光の実(파워) · 金貨(점수) · 妖精の鈴(結界 +1) ----------------
def draw_berry():
    p = Painter(14, 14); p.glow((7, 8), 5, '#ff7a8a', 120, 1.2)
    p.ellipse((2.5, 4, 11.5, 13), c1='#ff8a9a', c2='#b3152e', kind='rad', p1=(5.5, 6.5), p2=(6, 0))
    p.poly([(7, 4.5), (9.5, 1), (11.5, 2.5), (8, 5)], c1='#7ad96b', c2='#2a7a3a', kind='lin', p1=(7, 1), p2=(11, 5))
    p.ellipse((4.5, 6, 6.5, 7.6), c1='#ffffff', alpha=200)
    return p.done(colors=32)
def draw_coin():
    p = Painter(14, 14); p.ellipse((1.5, 1.5, 12.5, 12.5), c1='#ffe68a', c2='#c98b1a', kind='rad', p1=(5, 5), p2=(8, 0))
    p.ellipse((3.5, 3.5, 10.5, 10.5), c1='#e0a93a', alpha=160); p.ellipse((4.3, 4.3, 9.7, 9.7), c1='#ffe68a', c2='#d9a63a', kind='rad', p1=(6, 6), p2=(4, 0))
    p.rect((6.2, 5, 7.8, 9.2), c1='#b07a1a', alpha=200); p.ellipse((4, 3.5, 6, 5.2), c1='#ffffff', alpha=200)
    return p.done(colors=32)
def draw_bell():
    p = Painter(14, 14); p.glow((7, 8), 5, '#9dd9ff', 110, 1.2)
    p.poly([(7, 1.5), (10, 3), (11.5, 9), (13, 11.5), (1, 11.5), (2.5, 9), (4, 3)], c1='#eaf6ff', c2='#5b8fd6', kind='lin', p1=(3, 2), p2=(12, 12))
    p.ellipse((5.5, 10, 8.5, 13), c1='#ffe68a', c2='#c98b1a', kind='lin', p1=(0, 10), p2=(0, 13)); p.ellipse((6, 0.5, 8, 2.5), c1='#c98b1a')
    p.ellipse((4.5, 3.5, 6.5, 6), c1='#ffffff', alpha=190)
    return p.done(colors=32, outline='#1d3a6b')

# ---------------- 배경: 妖精の森 180×240 (세로로 이어 붙는 타일, 게임에서 2배) ----------------
def draw_bg(seed=11):
    random.seed(seed); W, H = 180, 240; p = Painter(W, H, ss=3); TAU = math.tau
    wrap = lambda fn, y: [fn(y), fn(y - H), fn(y + H)]
    def soft(draw_fn, blur):  # 흐린 층(빛줄기·안개)
        g = Image.new('RGBA', p.im.size, (0, 0, 0, 0)); d = ImageDraw.Draw(g); draw_fn(d); p.im.alpha_composite(g.filter(ImageFilter.GaussianBlur(p.s(blur))))
    def canopy(x, y, r, dark, light, n=14, squash=.75):  # 잎 뭉치: 작은 잎을 겹쳐 위쪽이 밝게
        leaves = sorted([(random.uniform(0, TAU), random.uniform(0, r * .85), random.uniform(r * .22, r * .42)) for _ in range(n)], key=lambda t: -math.sin(t[0]))
        for a, d, lr in leaves:
            lx, dy = x + math.cos(a) * d, math.sin(a) * d * squash
            wrap(lambda yy, lx=lx, dy=dy, lr=lr: p.ellipse((lx - lr, yy + dy - lr * .8, lx + lr, yy + dy + lr * .8), c1=light, c2=dark, kind='rad', p1=(lx - lr * .45, yy + dy - lr * .55), p2=(lr * 1.35, 0)), y)
    def trunk(x, w, top, bot, c1, c2, bark=True):
        wrap(lambda yy: p.poly([(x - w / 2, yy - top), (x + w / 2, yy - top), (x + w / 2 + w * .18, yy + bot), (x - w / 2 - w * .18, yy + bot)], c1=c1, c2=c2, kind='lin', p1=(x - w / 2, 0), p2=(x + w / 2 + w * .2, 0)), 0)
        if bark:
            for _ in range(int(H / 9)):
                yy0 = random.uniform(0, H); wrap(lambda yy: p.line([(x - w / 2 + random.uniform(0, w * .25), yy), (x + w / 2 - random.uniform(0, w * .25), yy + random.uniform(-5, 5))], '#120a05', .7, 110), yy0)
    # 1) 깊이 그라데이션
    p.rect((0, 0, W, H), c1='#0d3a40', c2='#071a22', kind='lin', p1=(0, 0), p2=(0, H))
    # 2) 먼 숲: 안개 낀 청록 실루엣(대비 낮게)
    for _ in range(14):
        x = random.uniform(0, W); trunk(x, random.uniform(4, 9), 150, 150, '#1c5a5c', '#12404a', bark=False)
    for _ in range(40):
        canopy(random.uniform(0, W), random.uniform(0, H), random.uniform(14, 24), '#114248', '#1f6a62', n=10)
    soft(lambda d: [d.rectangle([0, 0, p.im.size[0], p.im.size[1]], fill=(120, 190, 180, 40))], 1)
    # 3) 빛줄기
    for _ in range(4):
        x = random.uniform(20, W - 20); y0 = random.uniform(0, H)
        wrap(lambda yy, x=x: soft(lambda d: d.polygon([(p.s(x - 5), p.s(yy - 170)), (p.s(x + 7), p.s(yy - 170)), (p.s(x + 34), p.s(yy + 170)), (p.s(x + 6), p.s(yy + 170))], fill=(200, 255, 210, 34)), 2.5), y0)
    # 4) 중간 나무: 갈색 줄기 + 가지 + 잎 뭉치
    mids = [random.uniform(6, 60), random.uniform(120, 174), random.uniform(60, 120)]
    for x in mids:
        w = random.uniform(9, 14); trunk(x, w, 150, 150, '#5a3d24', '#20120a')
        for _ in range(5):
            y = random.uniform(0, H); dx = random.choice([-1, 1]) * random.uniform(14, 30)
            wrap(lambda yy, x=x, dx=dx: p.line([(x, yy), (x + dx, yy - abs(dx) * .5)], '#2b1a0e', 1.6), y)
            canopy(x + dx, y - abs(dx) * .5, random.uniform(11, 17), '#17503a', '#3f9a5a', n=12)
    for _ in range(26):
        canopy(random.uniform(0, W), random.uniform(0, H), random.uniform(12, 20), '#164a36', '#3a8f55', n=12)
    # 5) 가운데 개울(세로로 주기 함수라 타일이 이어진다) + 돌 + 연잎
    cxs = lambda t: 90 + 20 * math.sin(TAU * t / H) + 9 * math.sin(TAU * 2 * t / H + 1.3)
    ts = list(range(-H, 2 * H + 1, 3)); left = [(cxs(t) - 16 - 3 * math.sin(TAU * 3 * t / H), t) for t in ts]; right = [(cxs(t) + 16 + 3 * math.cos(TAU * 3 * t / H), t) for t in ts]
    p.poly(left + right[::-1], c1='#1f5c58', c2='#123a3c', kind='lin', p1=(60, 0), p2=(120, 0))  # 둑(이끼)
    left2 = [(x + 4, t) for x, t in left]; right2 = [(x - 4, t) for x, t in right]
    p.poly(left2 + right2[::-1], c1='#1f5f8a')
    left3 = [(x + 9, t) for x, t in left]; right3 = [(x - 9, t) for x, t in right]
    p.poly(left3 + right3[::-1], c1='#4fb6c9', alpha=170)
    left4 = [(x + 13, t) for x, t in left]; right4 = [(x - 13, t) for x, t in right]
    p.poly(left4 + right4[::-1], c1='#8fe3ea', alpha=110)
    for t in range(-H, 2 * H, 5):
        x = cxs(t) + random.uniform(-11, 11); p.line([(x, t), (x + random.uniform(2, 7), t + random.uniform(.5, 2))], '#f0ffff', .6, random.randint(120, 220))
    for _ in range(22):
        t = random.uniform(0, H); side = random.choice([-1, 1]); x = cxs(t) + side * random.uniform(13, 19); r = random.uniform(2, 4.5)
        wrap(lambda yy, x=x, r=r: p.ellipse((x - r, yy - r * .7, x + r, yy + r * .7), c1='#9aa7b0', c2='#3b4650', kind='rad', p1=(x - r * .4, yy - r * .5), p2=(r * 1.3, 0)), t)
    for _ in range(9):
        t = random.uniform(0, H); x = cxs(t) + random.uniform(-9, 9); r = random.uniform(2.5, 4)
        wrap(lambda yy, x=x, r=r: [p.ellipse((x - r, yy - r * .6, x + r, yy + r * .6), c1='#7fd36b', c2='#2a7a3a', kind='rad', p1=(x - r * .3, yy - r * .3), p2=(r * 1.2, 0)), p.poly([(x, yy), (x + r, yy - r * .6), (x + r, yy - r * .1)], c1='#2a6b96', alpha=200)], t)
    # 6) 가까운 층(양쪽 가장자리): 큰 잎 뭉치, 양치식물, 버섯, 꽃
    for _ in range(18):
        side = random.random() < .5; x = random.uniform(-6, 40) if side else random.uniform(W - 40, W + 6)
        canopy(x, random.uniform(0, H), random.uniform(16, 26), '#0f3b26', '#4fb86a', n=16)
    for _ in range(14):
        side = random.random() < .5; x = random.uniform(2, 34) if side else random.uniform(W - 34, W - 2); y = random.uniform(0, H)
        ang = random.uniform(-.9, .9) + (0 if side else math.pi); L = random.uniform(16, 26)
        def fern(yy, x=x, ang=ang, L=L):
            pts = []
            for i in range(7):
                t = i / 6; px, py = x + math.cos(ang) * L * t, yy - math.sin(ang) * L * t - L * .3 * t; wv = (1 - t) * 4 + .5
                pts.append((px + math.sin(ang) * wv, py + math.cos(ang) * wv))
            for i in range(6, -1, -1):
                t = i / 6; px, py = x + math.cos(ang) * L * t, yy - math.sin(ang) * L * t - L * .3 * t; wv = (1 - t) * 4 + .5
                pts.append((px - math.sin(ang) * wv, py - math.cos(ang) * wv))
            p.poly(pts, c1='#6fd27a', c2='#1d5a30', kind='lin', p1=(x, yy), p2=(x + math.cos(ang) * L, yy - math.sin(ang) * L))
            p.line([(x, yy), (x + math.cos(ang) * L, yy - math.sin(ang) * L - L * .3)], '#2a7a3a', .6, 170)
        wrap(fern, y)
    for _ in range(9):
        x = random.choice([random.uniform(8, 42), random.uniform(W - 42, W - 8)]); y = random.uniform(0, H); r = random.uniform(2.5, 5)
        def shroom(yy, x=x, r=r):
            p.rect((x - r * .4, yy, x + r * .4, yy + r * 1.4), c1='#f4e6cc', c2='#b89a78', kind='lin', p1=(x - r * .4, 0), p2=(x + r * .4, 0))
            p.ellipse((x - r, yy - r * .9, x + r, yy + r * .4), c1='#ff6b6b', c2='#8e1a2e', kind='rad', p1=(x - r * .35, yy - r * .6), p2=(r * 1.25, 0))
            for dx, dy, rr in ((-.5, -.5, .22), (.3, -.7, .18), (.1, -.1, .15)): p.ellipse((x + dx * r - rr * r, yy + dy * r - rr * r, x + dx * r + rr * r, yy + dy * r + rr * r), c1='#fff6f0')
        wrap(shroom, y)
    for _ in range(40):
        x = random.choice([random.uniform(0, 48), random.uniform(W - 48, W)]); y = random.uniform(0, H); r = random.uniform(1, 2); c = random.choice(['#ffd6f5', '#fff6a0', '#ffffff', '#ffb3c7'])
        wrap(lambda yy, x=x, r=r, c=c: [p.ellipse((x - r, yy - r, x + r, yy + r), c1=c, alpha=235), p.ellipse((x - r * .35, yy - r * .35, x + r * .35, yy + r * .35), c1='#ffd166', alpha=230)], y)
    # 7) 안개 띠·주변 어둡게
    for _ in range(3):
        y = random.uniform(0, H); wrap(lambda yy: soft(lambda d: d.rectangle([0, p.s(yy - 10), p.im.size[0], p.s(yy + 10)], fill=(160, 230, 200, 26)), 3), y)
    return p.done(colors=64, outline=None, pixel_alpha=False)

# ---------------- 배경 2: 電脳都市 180×240 (네온 거리, 세로 타일) ----------------
def draw_bg2(seed=23):
    random.seed(seed); W, H = 180, 240; p = Painter(W, H, ss=3); TAU = math.tau
    wrap = lambda fn, y: [fn(y), fn(y - H), fn(y + H)]
    def soft(draw_fn, blur):
        g = Image.new('RGBA', p.im.size, (0, 0, 0, 0)); d = ImageDraw.Draw(g); draw_fn(d); p.im.alpha_composite(g.filter(ImageFilter.GaussianBlur(p.s(blur))))
    p.rect((0, 0, W, H), c1='#0a0f2e', c2='#050616', kind='lin', p1=(0, 0), p2=(0, H))
    # 먼 빌딩 실루엣(창 불빛)
    for _ in range(26):
        x = random.uniform(-10, W); w = random.uniform(10, 26); c = random.choice(['#141a44', '#1a2050', '#10163a'])
        wrap(lambda yy: p.rect((x, yy - 120, x + w, yy + 120), c1=c), random.uniform(0, H))
        for _ in range(int(w * 1.2)):
            wx, wy = x + random.uniform(1, w - 2), random.uniform(0, H); wc = random.choice(['#ffd166', '#7df9ff', '#ff5cf0', '#ffffff'])
            wrap(lambda yy, wx=wx, wc=wc: p.rect((wx, yy, wx + 1.3, yy + 1.8), c1=wc, alpha=random.randint(90, 200)), wy)
    # 가운데 도로(차선·횡단보도) — 세로 직선이라 타일이 이어진다
    p.rect((56, -H, 124, 2 * H), c1='#1b1d33', c2='#101223', kind='lin', p1=(56, 0), p2=(124, 0))
    p.rect((56, -H, 59, 2 * H), c1='#3a3f5a'); p.rect((121, -H, 124, 2 * H), c1='#3a3f5a')
    for t in range(-H, 2 * H, 16): p.rect((89, t, 91, t + 8), c1='#ffd166', alpha=200)
    for t in (60, 180):
        for i in range(8): wrap(lambda yy, i=i: p.rect((60 + i * 8, yy, 65 + i * 8, yy + 10), c1='#e6e8f4', alpha=170), t)
    for _ in range(10):
        t = random.uniform(0, H); x = random.choice([random.uniform(62, 80), random.uniform(100, 116)]); c = random.choice(['#ff5c5c', '#5ad1ff', '#ffffff', '#ffd166'])
        wrap(lambda yy, x=x, c=c: [p.poly([(x - 4, yy - 7), (x + 4, yy - 7), (x + 5, yy + 7), (x - 5, yy + 7)], c1=c, c2='#1a1f3a', kind='lin', p1=(0, yy - 7), p2=(0, yy + 7)), p.rect((x - 3, yy - 4, x + 3, yy - 1), c1='#9fe3ff', alpha=200), p.glow((x, yy + 7), 3, '#ff3a3a', 150, 1)], t)
    # 가까운 빌딩(양쪽) + 네온 간판
    for x0, side in ((0, 1), (W, -1)):
        for k in range(3):
            w = random.uniform(22, 40); x = x0 if side > 0 else x0 - w; c = random.choice(['#232a5c', '#2a2f6b', '#1c2252'])
            wrap(lambda yy, x=x, w=w, c=c: p.rect((x, yy - 120, x + w, yy + 120), c1=c, c2='#0c0f2a', kind='lin', p1=(x if side > 0 else x + w, 0), p2=(x + w if side > 0 else x, 0)), random.uniform(0, H))
            for _ in range(22):
                wx, wy = x + random.uniform(2, w - 3), random.uniform(0, H); wc = random.choice(['#ffd166', '#7df9ff', '#ffffff'])
                wrap(lambda yy, wx=wx, wc=wc: p.rect((wx, yy, wx + 2, yy + 2.6), c1=wc, alpha=random.randint(80, 190)), wy)
        for _ in range(7):
            y = random.uniform(0, H); w, h = random.uniform(8, 20), random.uniform(5, 10); x = random.uniform(2, 44) if side > 0 else random.uniform(W - 46, W - 2 - w)
            c = random.choice(['#ff2d9a', '#5ad1ff', '#ffd166', '#7dff8a', '#ff5c5c', '#c77dff'])
            def sign(yy, x=x, y=y, w=w, h=h, c=c):
                p.glow((x + w / 2, yy), max(w, h) * .6, c, 70, 2.5); p.rect((x, yy - h / 2, x + w, yy + h / 2), c1='#0b0d20')
                p.fill(lambda d, v: d.rectangle([p.s(x), p.s(yy - h / 2), p.s(x + w), p.s(yy + h / 2)], outline=v, width=max(1, round(p.s(.7)))), c1=c)
                for i in range(int(w // 3)): p.rect((x + 1.5 + i * 3, yy - h / 2 + 1.5, x + 3 + i * 3, yy + h / 2 - 1.5), c1=c, alpha=random.randint(120, 230))
            wrap(sign, y)
    # 전선·홀로그램 링
    for _ in range(5):
        y = random.uniform(0, H); x = random.uniform(20, W - 20)
        wrap(lambda yy, x=x: p.fill(lambda d, v: d.ellipse([p.s(x - 9), p.s(yy - 3), p.s(x + 9), p.s(yy + 3)], outline=v, width=max(1, round(p.s(.6)))), c1='#7df9ff', alpha=120), y)
    for _ in range(3):
        y = random.uniform(0, H); wrap(lambda yy: soft(lambda d: d.rectangle([0, p.s(yy - 12), p.im.size[0], p.s(yy + 12)], fill=(120, 80, 255, 22)), 3), y)
    return p.done(colors=64, outline=None, pixel_alpha=False)

# ---------------- 배경 3: 月夜の神社 180×240 (돌계단·도리이·석등·벚나무, 세로 타일) ----------------
def draw_bg3(seed=31):
    random.seed(seed); W, H = 180, 240; p = Painter(W, H, ss=3); TAU = math.tau
    wrap = lambda fn, y: [fn(y), fn(y - H), fn(y + H)]
    def soft(draw_fn, blur):
        g = Image.new('RGBA', p.im.size, (0, 0, 0, 0)); d = ImageDraw.Draw(g); draw_fn(d); p.im.alpha_composite(g.filter(ImageFilter.GaussianBlur(p.s(blur))))
    def canopy(x, y, r, dark, light, n=14):
        for a, d, lr in sorted([(random.uniform(0, TAU), random.uniform(0, r * .85), random.uniform(r * .22, r * .42)) for _ in range(n)], key=lambda t: -math.sin(t[0])):
            lx, dy = x + math.cos(a) * d, math.sin(a) * d * .75
            wrap(lambda yy, lx=lx, dy=dy, lr=lr: p.ellipse((lx - lr, yy + dy - lr * .8, lx + lr, yy + dy + lr * .8), c1=light, c2=dark, kind='rad', p1=(lx - lr * .45, yy + dy - lr * .55), p2=(lr * 1.35, 0)), y)
    p.rect((0, 0, W, H), c1='#1a1440', c2='#0b0a22', kind='lin', p1=(0, 0), p2=(0, H))
    for _ in range(60):
        x, y, r = random.uniform(0, W), random.uniform(0, H), random.uniform(.4, 1); wrap(lambda yy, x=x, r=r: p.ellipse((x - r, yy - r, x + r, yy + r), c1='#ffffff', alpha=random.randint(80, 220)), y)
    # 먼 숲(남보라)
    for _ in range(30): canopy(random.uniform(0, W), random.uniform(0, H), random.uniform(14, 24), '#1d1850', '#3a2f80', n=10)
    # 돌계단(가운데)
    p.rect((60, -H, 120, 2 * H), c1='#5c6180', c2='#3a3f5a', kind='lin', p1=(60, 0), p2=(120, 0))
    for t in range(-H, 2 * H, 8):
        p.rect((60, t, 120, t + 1.2), c1='#8a90a8', alpha=200); p.rect((60, t + 6.5, 120, t + 8), c1='#262a44', alpha=200)
    for x in (57, 120): p.rect((x, -H, x + 3, 2 * H), c1='#8a90a8', c2='#4a4e66', kind='lin', p1=(x, 0), p2=(x + 3, 0))
    # 벚나무(양쪽) + 줄기
    for x0 in (random.uniform(10, 40), random.uniform(140, 170)):
        wrap(lambda yy, x=x0: p.poly([(x - 5, yy - 150), (x + 5, yy - 150), (x + 7, yy + 150), (x - 7, yy + 150)], c1='#4a3550', c2='#1a1020', kind='lin', p1=(x - 6, 0), p2=(x + 7, 0)), 0)
    for _ in range(30):
        side = random.random() < .5; x = random.uniform(-6, 50) if side else random.uniform(W - 50, W + 6)
        canopy(x, random.uniform(0, H), random.uniform(13, 22), '#8a3a6a', '#ffb3d1', n=14)
    # 도리이(계단을 가로지름)
    for t in (40, 160):
        def torii(yy):
            p.rect((54, yy - 2, 126, yy + 2), c1='#ff4d3d', c2='#a8231a', kind='lin', p1=(0, yy - 2), p2=(0, yy + 2)); p.rect((58, yy + 5, 122, yy + 7.5), c1='#e63950', c2='#8e1a2e', kind='lin', p1=(0, yy + 5), p2=(0, yy + 8))
            for x in (62, 114): p.rect((x, yy, x + 4, yy + 26), c1='#ff6b5c', c2='#8e1a2e', kind='lin', p1=(x, 0), p2=(x + 4, 0))
            p.rect((53, yy - 4, 127, yy - 2), c1='#2a1a20')
        wrap(torii, t)
    # 석등(양쪽, 불빛)
    for t in range(0, H, 48):
        for x in (48, 128):
            def lantern(yy, x=x):
                p.glow((x, yy + 4), 7, '#ffd166', 110, 2); p.rect((x - 2, yy + 8, x + 2, yy + 18), c1='#9aa0b8', c2='#4a4e66', kind='lin', p1=(x - 2, 0), p2=(x + 2, 0))
                p.poly([(x - 6, yy + 1), (x + 6, yy + 1), (x + 3, yy - 4), (x - 3, yy - 4)], c1='#c9cdd8', c2='#5c6180', kind='lin', p1=(0, yy - 4), p2=(0, yy + 1))
                p.rect((x - 4, yy + 1, x + 4, yy + 8), c1='#fff2b0', c2='#ffb347', kind='lin', p1=(0, yy + 1), p2=(0, yy + 8)); p.rect((x - 1, yy + 1, x + 1, yy + 8), c1='#5c6180', alpha=150)
                p.rect((x - 5, yy + 18, x + 5, yy + 20.5), c1='#8a90a8', c2='#3a3f5a', kind='lin', p1=(0, yy + 18), p2=(0, yy + 21))
            wrap(lantern, t + random.uniform(-6, 6))
    # 꽃잎
    for _ in range(50):
        x, y = random.uniform(0, W), random.uniform(0, H); r = random.uniform(.8, 1.6)
        wrap(lambda yy, x=x, r=r: p.ellipse((x - r, yy - r * .6, x + r, yy + r * .6), c1='#ffd1e3', alpha=random.randint(150, 240)), y)
    for _ in range(3):
        y = random.uniform(0, H); wrap(lambda yy: soft(lambda d: d.rectangle([0, p.s(yy - 12), p.im.size[0], p.s(yy + 12)], fill=(200, 180, 255, 24)), 3), y)
    return p.done(colors=64, outline=None, pixel_alpha=False)

ASSETS = {'player': draw_player, 'mush': draw_mush, 'wisp': draw_wisp, 'chest': draw_chest, 'boss': draw_boss, 'bg': draw_bg,
          'drone': draw_drone, 'holo': draw_holo, 'vending': draw_vending, 'boss2': draw_boss2, 'bg2': draw_bg2,
          'foxfire': draw_foxfire, 'shiki': draw_shiki, 'komainu': draw_komainu, 'boss3': draw_boss3, 'bg3': draw_bg3,
          'berry': draw_berry, 'coin': draw_coin, 'bell': draw_bell}

def main():
    ims = {n: f() for n, f in ASSETS.items()}
    if len(sys.argv) > 1:
        scale = 4; gap = 12; chars = {k: v for k, v in ims.items() if not k.startswith('bg')}; bgs = [ims[k] for k in ('bg', 'bg2', 'bg3')]
        W = sum(i.width * scale + gap for i in chars.values()); H = max(i.height for i in chars.values()) * scale
        bw = sum(b.width * 2 + gap for b in bgs); bh = max(b.height * 2 for b in bgs)
        sheet = Image.new('RGBA', (max(W, bw), H + bh + 20), (18, 20, 40, 255)); x = 0
        for i in chars.values():
            sheet.alpha_composite(i.resize((i.width * scale, i.height * scale), Image.NEAREST), (x, H - i.height * scale)); x += i.width * scale + gap
        x = 0
        for b in bgs: sheet.alpha_composite(b.resize((b.width * 2, b.height * 2), Image.NEAREST), (x, H + 20)); x += b.width * 2 + gap
        sheet.save(sys.argv[1]); print('preview', sys.argv[1]); return
    for n, i in ims.items(): i.save(os.path.join(HERE, n + '.png'), optimize=True); print(n, i.size)

if __name__ == '__main__':
    main()
