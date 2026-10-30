#!/usr/bin/env python3
"""도로롱 계절 옷: assets/mascot.png 위에 소품을 그려 계절 그림을 만든다(Pillow).
  python3 assets/mascot_season.py          → assets/mascot_halloween.png
그림체(검은 윤곽 + 단색 + 흰 스티커 테두리)에 맞춰 4배로 그린 뒤 줄인다. 운영자가 그린 계절 그림이 오면 그 파일로 바꾸면 된다."""
import math, os
from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
S = 4            # 그리는 배율
TOP = 52         # 모자가 들어가게 위로 늘리는 높이(원본 px)
INK = (34, 24, 36, 255)


def P(x, y):     # 원본 좌표 → 큰 캔버스 좌표(위로 TOP 늘림)
    return (x * S, (y + TOP) * S)


def sticker(layer, px=7):
    """그림 둘레에 흰 스티커 테두리(원본 그림과 같은 느낌)"""
    a = layer.getchannel("A").filter(ImageFilter.MaxFilter(px * 2 * S // 2 * 2 + 1))
    out = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    out.paste((255, 255, 255, 235), (0, 0), a)
    out.alpha_composite(layer)
    return out


def rot(pts, c, deg):
    r = math.radians(deg); cx, cy = c
    return [(cx + (x - cx) * math.cos(r) - (y - cy) * math.sin(r), cy + (x - cx) * math.sin(r) + (y - cy) * math.cos(r)) for x, y in pts]


def witch_hat(W, H, cx, by, wid, deg):
    """보라 마녀 모자: 아래로 휜 챙(옆에서 본 납작한 타원 아래쪽 반) + 끝이 뒤로 꺾인 원뿔 + 주황 띠·금색 버클.
    cx, by: 챙 가운데(원본 좌표), wid: 챙 너비, deg: 기울기. 2026-10 처음엔 경단 머리 위에 크게 얹었는데 떠 보여서, 머리 위 잭오랜턴(귤)이 쓰게 바꿨다."""
    L = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(L)
    k = lambda x, y: P(cx + x * wid / 100, by + y * wid / 100)
    w = 5 * S
    body, dark, band, gold = (96, 64, 146, 255), (66, 42, 104, 255), (245, 140, 40, 255), (250, 210, 70, 255)
    brim = [k(-50, 0), k(-40, 7), k(-20, 11), k(0, 12), k(20, 11), k(40, 7), k(50, 0), k(36, -4), k(0, -6), k(-36, -4)]
    cone = [k(-28, -3), k(-20, -34), k(-10, -62), k(4, -82), k(22, -92), k(36, -86), k(18, -76), k(12, -58), k(20, -30), k(28, -3)]
    d.polygon(brim, fill=dark, outline=INK, width=w)
    d.polygon(cone, fill=body, outline=INK, width=w)
    d.polygon([k(-27, -6), k(-25, -18), k(25, -18), k(27, -6)], fill=band, outline=INK, width=w // 2 + 2)
    d.rectangle([k(-6, -19), k(6, -5)], fill=gold, outline=INK, width=w // 2 + 1)
    d.line([k(-14, -40), k(-8, -66)], fill=(140, 110, 190, 255), width=S * 3)  # 빛 받은 면
    sx, sy = k(10, -46)
    star = [(sx + math.cos(math.radians(a)) * (7 if i % 2 == 0 else 3) * S * wid / 100, sy + math.sin(math.radians(a)) * (7 if i % 2 == 0 else 3) * S * wid / 100) for i, a in enumerate(range(-90, 270, 36))]
    d.polygon(star, fill=gold, outline=INK, width=S * 2)
    if deg: L = L.rotate(deg, center=P(cx, by), resample=Image.BICUBIC)
    return L


def jack_face(d):
    """머리 위 귤을 잭오랜턴으로: 세모 눈·코, 톱니 입(안쪽은 노란 불빛)"""
    glow, hole = (255, 214, 90, 255), (90, 40, 10, 255)
    def tri(cx, cy, s, up=True):
        return [P(cx - s, cy + s * .7), P(cx + s, cy + s * .7), P(cx, cy - s)] if up else [P(cx - s, cy - s * .6), P(cx + s, cy - s * .6), P(cx, cy + s)]
    for cx in (100, 121):
        d.polygon(tri(cx, 37, 6), fill=hole, outline=INK, width=S * 2)
        d.polygon(tri(cx, 38.3, 3), fill=glow)
    d.polygon(tri(110.5, 43.5, 2.4, False), fill=hole)
    m = [P(96, 47), P(100, 51), P(104, 48), P(108, 52), P(112, 48), P(116, 52), P(120, 48), P(123, 51), P(126, 47), P(121, 56), P(101, 56)]
    d.polygon(m, fill=hole, outline=INK, width=S * 2)
    d.polygon([P(101, 50.5), P(105, 53), P(111, 51), P(117, 53), P(121, 50.5), P(119, 54.5), P(103, 54.5)], fill=glow)


def bat(W, H, cx, cy, s, deg=0):
    L = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(L)
    k = lambda x, y: P(cx + x * s, cy + y * s)
    wing = [k(0, -2), k(6, -9), k(12, -7), k(20, -13), k(22, -4), k(26, 0), k(19, 1), k(15, 5), k(10, 2), k(6, 6), k(3, 3), k(0, 6),
            k(-3, 3), k(-6, 6), k(-10, 2), k(-15, 5), k(-19, 1), k(-26, 0), k(-22, -4), k(-20, -13), k(-12, -7), k(-6, -9)]
    d.polygon(wing, fill=(48, 34, 62, 255), outline=INK, width=S * 2)
    d.polygon([k(-4, -7), k(-3, -12), k(-1, -8), k(1, -8), k(3, -12), k(4, -7), k(4, 2), k(-4, 2)], fill=(48, 34, 62, 255), outline=INK, width=S * 2)
    for ex in (-1.8, 1.8):
        d.ellipse([k(ex - 1.1, -5.6), k(ex + 1.1, -3.4)], fill=(255, 205, 80, 255))
    if deg: L = L.rotate(deg, center=P(cx, cy), resample=Image.BICUBIC)
    return sticker(L, 4)


def halloween():
    base = Image.open(os.path.join(HERE, "mascot.png")).convert("RGBA")
    w, h = base.size
    W, H = w * S, (h + TOP) * S
    big = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    big.alpha_composite(base.resize((w * S, h * S), Image.LANCZOS), (0, TOP * S))
    jack_face(ImageDraw.Draw(big))
    big.alpha_composite(sticker(witch_hat(W, H, 110, 12, 62, 8), 5))  # 잭오랜턴(귤, 가운데 x≈111·위 y≈8) 머리에
    big.alpha_composite(bat(W, H, 34, 18, 1.15, 12))
    big.alpha_composite(bat(W, H, 296, 150, .8, -10))
    out = big.resize((w, h + TOP), Image.LANCZOS)
    out = out.quantize(colors=128, method=Image.FASTOCTREE, dither=Image.NONE)
    out.save(os.path.join(HERE, "mascot_halloween.png"), optimize=True)
    print("→ assets/mascot_halloween.png", out.size)


if __name__ == "__main__":
    halloween()
