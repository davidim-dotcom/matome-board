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

# ---------------- 자기: 妖精の巫女(분홍 트윈테일, 날개, 빛 구슬) 32×48 ----------------
def draw_player():
    p = Painter(32, 48); M = lambda pts: [(32 - x, y) for x, y in pts]
    # 날개(반투명)
    for pts in ([(13, 21), (2, 9), (0, 18), (9, 25)], [(13, 25), (3, 27), (6, 37), (13, 29)]):
        for q in (pts, M(pts)):
            p.poly(q, c1='#ffffff', c2='#7df9ff', kind='lin', p1=(16, 24), p2=(2, 14), alpha=150)
    for q in ([(13, 22), (4, 12)], [(13, 23), (3, 18)], [(13, 26), (5, 33)]):
        p.line(q, '#ffffff', .5, 120); p.line(M(q), '#ffffff', .5, 120)
    # 트윈테일
    tail = [(4, 13), (9.5, 13), (10.5, 35), (6.5, 40), (2, 35)]
    for q in (tail, M(tail)):
        p.poly(q, c1='#ff8ac6', c2='#c4256e', kind='lin', p1=(0, 14), p2=(0, 40))
    for q in ([(5, 15), (7.5, 15), (7.5, 30), (5.5, 32)],):
        p.poly(q, c1='#ffd2ea', alpha=110); p.poly(M(q), c1='#ffd2ea', alpha=110)
    # 다리·신발 (몸 뒤)
    for x in (12, 17): p.rect((x, 39, x + 3, 45.5), c1='#ffffff', c2='#d8dcf0', kind='lin', p1=(0, 39), p2=(0, 46))
    for x in (11.5, 16.5): p.ellipse((x, 43.5, x + 4, 47), c1='#ff5c7a', c2='#b3253e', kind='lin', p1=(0, 43), p2=(0, 47))
    # 치마
    p.poly([(10.5, 32), (21.5, 32), (25, 41.5), (7, 41.5)], c1='#6b93ff', c2='#2f4fc0', kind='lin', p1=(0, 32), p2=(0, 42))
    for x in (11, 14.5, 18, 21.5): p.line([(x, 33), (x - 1.2 + (x - 16) * .25, 41)], '#2a3f9a', .6, 140)
    # 상의·소매·손
    p.poly([(11, 25), (21, 25), (22.2, 33), (9.8, 33)], c1='#ffffff', c2='#dfe3f3', kind='lin', p1=(0, 25), p2=(0, 33))
    p.poly([(10.5, 25), (21.5, 25), (16, 29.5)], c1='#2a3f9a', c2='#1b2a6b', kind='lin', p1=(0, 25), p2=(0, 30))
    p.poly([(16, 27.5), (13.5, 30), (16, 29.3), (18.5, 30)], c1='#ff4f6d')
    for q in ([(8, 26, 12.2, 31)],): p.ellipse(q[0], c1='#ffffff', c2='#d8dcf0', kind='lin', p1=(0, 26), p2=(0, 31)); p.ellipse(M([(q[0][0], 0), (q[0][2], 0)])[1][0:1] + (q[0][1],) + M([(q[0][0], 0)])[0][0:1] + (q[0][3],), c1='#ffffff', c2='#d8dcf0', kind='lin', p1=(0, 26), p2=(0, 31))
    p.ellipse((8.6, 30, 11.6, 33), c1='#ffe3d2', c2='#e8b9a4', kind='lin', p1=(0, 30), p2=(0, 33)); p.ellipse((20.4, 30, 23.4, 33), c1='#ffe3d2', c2='#e8b9a4', kind='lin', p1=(0, 30), p2=(0, 33))
    # 목·얼굴
    p.rect((14.3, 22.5, 17.7, 26), c1='#f0c7b2')
    p.ellipse((6, 4.5, 26, 24.5), c1='#fff0e6', c2='#f0bfa8', kind='rad', p1=(13, 11), p2=(13, 0))
    # 머리(앞머리 지그재그)
    p.poly([(5, 11), (7, 14.5), (9.3, 11.5), (11.5, 15.5), (13.5, 12), (16, 16.5), (18.5, 12), (20.5, 15.5), (22.7, 11.5), (25, 14.5), (27, 11), (27, 6), (22, 2), (16, 1), (10, 2), (5, 6)],
           c1='#ffa0d0', c2='#e24a93', kind='lin', p1=(8, 2), p2=(24, 16))
    p.poly([(9, 4), (14, 2.5), (12, 7), (8, 8)], c1='#ffe0f0', alpha=140)
    for q in ([(8, 7), (6.5, 12)], [(12, 5), (11, 12.5)], [(20, 5), (21, 12.5)], [(24, 7), (25.5, 12)]): p.line(q, '#d93a86', .6, 150)
    for x0 in (4.5, 23.5): p.line([(x0 + 1, 16), (x0 + .5, 34)], '#d93a86', .6, 130); p.line([(x0 + 3.5, 16), (x0 + 4.5, 36)], '#b0206a', .6, 110)
    # 리본
    for q in ([(16, 3.5), (10.5, 1), (11.5, 6)], [(16, 3.5), (21.5, 1), (20.5, 6)]): p.poly(q, c1='#ff6b85', c2='#c91d3e', kind='lin', p1=(16, 1), p2=(16, 6))
    p.ellipse((14.8, 2.3, 17.2, 4.7), c1='#ff8aa0')
    # 눈
    for lx in (9, 18):
        p.ellipse((lx, 13, lx + 5, 20.5), c1='#ffffff', c2='#e6e8f4', kind='lin', p1=(0, 13), p2=(0, 21))
        p.ellipse((lx + .6, 14, lx + 4.4, 20.2), c1='#6fe3ff', c2='#1a3ea8', kind='lin', p1=(0, 14), p2=(0, 20))
        p.ellipse((lx + 1.4, 16.2, lx + 3.6, 19.6), c1='#0d1a4a')
        p.ellipse((lx + .9, 14.4, lx + 2.4, 16), c1='#ffffff'); p.ellipse((lx + 3, 18, lx + 3.9, 18.9), c1='#ffffff', alpha=220)
        p.line([(lx - .3, 13.2), (lx + 5.3, 12.6)], '#2a1a3a', .7)
    p.ellipse((6.5, 19.5, 10, 21.5), c1='#ff8fb0', alpha=120); p.ellipse((22, 19.5, 25.5, 21.5), c1='#ff8fb0', alpha=120)
    p.ellipse((15.2, 21.6, 16.8, 22.6), c1='#c94a6a')
    # 손의 빛 구슬
    p.glow((22, 30.5), 3.2, '#7df9ff', 150, 1.2); p.ellipse((20.6, 29.2, 23.4, 32), c1='#ffffff', c2='#35c2d6', kind='rad', p1=(21.4, 30), p2=(1.6, 0))
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

# ---------------- 보스: 森の魔女「ノイズ」 56×72 ----------------
def draw_boss():
    p = Painter(56, 72); M = lambda pts: [(56 - x, y) for x, y in pts]
    # 지팡이(뒤)
    p.line([(46, 26), (49, 66)], '#5a3a1c', 1.6); p.glow((45.5, 24), 5, '#9dffb0', 170, 1.6)
    p.ellipse((42.5, 21, 48.5, 27), c1='#ffffff', c2='#2fbf6b', kind='rad', p1=(44.5, 23), p2=(3.2, 0))
    # 긴 머리(남보라) + 망토
    p.poly([(14, 22), (42, 22), (46, 52), (40, 66), (16, 66), (10, 52)], c1='#3d2d6b', c2='#1a1033', kind='lin', p1=(0, 22), p2=(0, 66))
    p.poly([(16, 40), (40, 40), (47, 68), (9, 68)], c1='#2f7a4f', c2='#0e2e1e', kind='lin', p1=(0, 40), p2=(0, 68))
    for x in (18, 24, 32, 38): p.line([(x, 44), (x + (x - 28) * .25, 67)], '#0a2015', .8, 120)
    p.poly([(16, 40), (40, 40), (28, 46)], c1='#ffd166', c2='#b8862a', kind='lin', p1=(0, 40), p2=(0, 46))
    # 소매·손
    p.ellipse((8, 40, 18, 52), c1='#2f7a4f', c2='#143d28', kind='lin', p1=(0, 40), p2=(0, 52)); p.ellipse((38, 40, 48, 52), c1='#2f7a4f', c2='#143d28', kind='lin', p1=(0, 40), p2=(0, 52))
    p.ellipse((11, 49, 16, 54), c1='#ffe3d2', c2='#e8b9a4', kind='lin', p1=(0, 49), p2=(0, 54)); p.ellipse((43, 48, 48, 53), c1='#ffe3d2', c2='#e8b9a4', kind='lin', p1=(0, 48), p2=(0, 53))
    # 얼굴
    p.rect((25, 36, 31, 41), c1='#f0c7b2')
    p.ellipse((16, 18, 40, 42), c1='#fff0e6', c2='#f0bfa8', kind='rad', p1=(24, 26), p2=(15, 0))
    # 앞머리
    p.poly([(15, 27), (17, 31), (19.5, 27.5), (22, 32), (25, 28), (28, 33), (31, 28), (34, 32), (36.5, 27.5), (39, 31), (41, 27), (41, 20), (28, 15), (15, 20)],
           c1='#6a55b8', c2='#2d2060', kind='lin', p1=(18, 16), p2=(38, 33))
    # 눈(보라)
    for lx in (19.5, 30):
        p.ellipse((lx, 29, lx + 6.5, 37.5), c1='#ffffff', c2='#e6e8f4', kind='lin', p1=(0, 29), p2=(0, 38))
        p.ellipse((lx + .7, 30, lx + 5.8, 37.2), c1='#e0a0ff', c2='#5a1aa8', kind='lin', p1=(0, 30), p2=(0, 37))
        p.ellipse((lx + 1.8, 32.5, lx + 4.7, 36.6), c1='#1a0a3a')
        p.ellipse((lx + 1.2, 30.6, lx + 3, 32.4), c1='#ffffff'); p.line([(lx - .3, 29.2), (lx + 6.8, 28.6)], '#2a1a3a', .8)
    p.ellipse((16.5, 36.5, 20.5, 38.5), c1='#ff8fb0', alpha=110); p.ellipse((35.5, 36.5, 39.5, 38.5), c1='#ff8fb0', alpha=110)
    p.ellipse((27, 38.6, 29, 39.8), c1='#b8405a')
    # 모자
    p.ellipse((4, 15, 52, 24), c1='#4a3a8a', c2='#1d1540', kind='lin', p1=(0, 15), p2=(0, 24))
    p.poly([(14, 19), (42, 19), (36, 2), (26, -2), (22, 4)], c1='#6b55c4', c2='#2a1d5c', kind='lin', p1=(20, 2), p2=(40, 19))
    p.poly([(14.5, 18.5), (41.5, 18.5), (40.3, 15.2), (16.2, 15.2)], c1='#ffd166', c2='#b8862a', kind='lin', p1=(0, 15), p2=(0, 19))
    p.ellipse((35, 13, 39, 17), c1='#ff6b85', c2='#c91d3e', kind='lin', p1=(0, 13), p2=(0, 17))
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

ASSETS = {'player': draw_player, 'mush': draw_mush, 'wisp': draw_wisp, 'chest': draw_chest, 'boss': draw_boss,
          'berry': draw_berry, 'coin': draw_coin, 'bell': draw_bell, 'bg': draw_bg}

def main():
    ims = {n: f() for n, f in ASSETS.items()}
    if len(sys.argv) > 1:
        scale = 4; gap = 12; chars = {k: v for k, v in ims.items() if k != 'bg'}
        W = sum(i.width * scale + gap for i in chars.values()); H = max(i.height for i in chars.values()) * scale
        bg = ims['bg'].resize((ims['bg'].width * 2, ims['bg'].height * 2), Image.NEAREST)
        sheet = Image.new('RGBA', (max(W, bg.width), H + bg.height + 20), (18, 20, 40, 255)); x = 0
        for i in chars.values():
            sheet.alpha_composite(i.resize((i.width * scale, i.height * scale), Image.NEAREST), (x, H - i.height * scale)); x += i.width * scale + gap
        sheet.alpha_composite(bg, (0, H + 20)); sheet.save(sys.argv[1]); print('preview', sys.argv[1]); return
    for n, i in ims.items(): i.save(os.path.join(HERE, n + '.png'), optimize=True); print(n, i.size)

if __name__ == '__main__':
    main()
