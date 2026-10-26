"""放置(Test) 탭의 도트 리소스를 만든다.

설비 아이콘 7개(32×32)는 소품을 1px 도트로 그리고 저장소 스프라이트(릴리 얼굴·고양이 등)를 원래 크기 그대로 얹는다.
결과는 assets/idle/*.png 와, index.html 에 붙여 넣을 window.IDLE_ASSETS 정의(data URI 인라인)를 assets/idle/assets.js 로 쓴다.
  python3 assets/game/idle.py
"""
import base64, io, json, os
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, '..', 'idle')
G = lambda n: Image.open(os.path.join(HERE, n + '.png')).convert('RGBA')

OL, PAPER, PINK, PINK2, PURP, YEL, CYAN, GRAY, WOOD, WHITE, DARK = (
    (26, 20, 38), (244, 236, 216), (255, 111, 163), (200, 60, 120), (138, 92, 246), (255, 209, 102),
    (125, 249, 255), (154, 164, 184), (160, 96, 58), (255, 255, 255), (40, 34, 60))


def box(d, x0, y0, x1, y1, fill, ol=OL):
    d.rectangle([x0, y0, x1, y1], fill=ol)
    d.rectangle([x0 + 1, y0 + 1, x1 - 1, y1 - 1], fill=fill)


def paste(im, spr, x, y):
    im.alpha_composite(spr, (x, y))


def icon(i):
    im = Image.new('RGBA', (32, 32), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if i == 0:  # 낙서: 종이 + 분홍 낙서 + 연필
        box(d, 3, 4, 24, 28, PAPER)
        for x in range(6, 21):
            d.point((x, 10 + (x % 4 in (1, 2))), fill=PINK)
            d.point((x, 16 + (x % 3 == 0)), fill=PURP)
        for x in range(6, 15):
            d.point((x, 22 - (x % 2)), fill=PINK)
        for k in range(9):  # 연필(대각선)
            x, y = 17 + k, 27 - k
            d.rectangle([x, y - 1, x + 1, y], fill=YEL)
            d.point((x + 2, y - 1), fill=OL)
        d.rectangle([25, 17, 27, 19], fill=PINK)
        d.point((16, 28), fill=OL)
    elif i == 1:  # 일러스트: 이젤 위 캔버스에 릴리
        d.line([8, 27, 11, 20], fill=WOOD, width=2); d.line([24, 27, 21, 20], fill=WOOD, width=2)
        box(d, 2, 1, 29, 23, WHITE)
        paste(im, G('face_lilly2').crop((0, 3, 25, 24)), 4, 2)
        d.rectangle([2, 22, 29, 23], fill=WOOD)
    elif i == 2:  # 동인지: 분홍 표지 책에 릴리
        box(d, 4, 2, 27, 30, PINK)
        d.rectangle([5, 3, 7, 29], fill=PINK2)
        d.rectangle([26, 4, 27, 29], fill=WHITE)
        face = G('face_lilly').crop((1, 0, 25, 24))
        paste(im, face, 6, 5)
        d.rectangle([9, 26, 22, 27], fill=YEL)
    elif i == 3:  # 굿즈: 아크릴 키홀더(고리 + 투명판 + 고양이)
        d.ellipse([12, 0, 19, 7], outline=GRAY); d.line([15, 7, 15, 9], fill=GRAY)
        d.rounded_rectangle([3, 9, 28, 31], 4, fill=(190, 240, 255, 150), outline=CYAN)
        paste(im, G('cat'), 6, 7)
        d.point((25, 12), fill=WHITE); d.point((24, 13), fill=WHITE)
    elif i == 4:  # 콜라보카페: 라테 컵(하트 라테아트) + 김
        for k, x in enumerate((10, 15, 20)):
            for y in range(1, 8):
                d.point((x + ((y + k) % 3 == 0) - ((y + k) % 3 == 2), y), fill=(230, 230, 240, 170))
        box(d, 4, 10, 23, 26, WHITE)
        d.rectangle([5, 11, 22, 14], fill=(190, 130, 80))
        for p in [(12, 12), (13, 12), (15, 12), (16, 12), (12, 13), (13, 13), (14, 13), (15, 13), (16, 13), (13, 14), (14, 14), (15, 14)]:
            d.point(p, fill=PINK)
        d.arc([20, 13, 29, 22], -90, 90, fill=OL, width=2)
        box(d, 1, 26, 28, 29, PINK)
    elif i == 5:  # 애니화: 보라 TV 에 스이세이 + 안테나
        d.line([10, 0, 15, 5], fill=GRAY); d.line([21, 0, 16, 5], fill=GRAY)
        box(d, 1, 5, 30, 28, PURP)
        d.rectangle([3, 7, 24, 26], fill=DARK)
        face = G('hc_suisei_f').crop((0, 0, 20, 19))
        paste(im, face, 4, 7)
        d.rectangle([26, 9, 28, 11], fill=YEL); d.rectangle([26, 14, 28, 16], fill=CYAN)
        d.rectangle([6, 28, 9, 30], fill=OL); d.rectangle([22, 28, 25, 30], fill=OL)
    elif i == 6:  # 극장판: 클래퍼보드 + 별
        box(d, 2, 12, 29, 30, DARK)
        for k in range(0, 28, 6):
            d.polygon([(3 + k, 7), (6 + k, 7), (3 + k + 3, 11), (k, 11)], fill=WHITE)
        d.rectangle([2, 6, 29, 6], fill=OL); d.rectangle([2, 11, 29, 11], fill=OL)
        d.rectangle([1, 6, 3, 30], fill=OL)
        star = [(16, 14), (18, 19), (23, 19), (19, 22), (21, 27), (16, 24), (11, 27), (13, 22), (9, 19), (14, 19)]
        d.polygon(star, fill=YEL, outline=OL)
    return im


RANK_NAMES = ['신입 서클', '섬 서클', '생일석', '셔터 앞', '벽 서클', '대형 서클', '기업 부스']


def rank_badge(k):
    """서클 랭크 배지 16×16: 종이 팻말 → 섬(책상) → 케이크(생일석) → 셔터 → 벽돌 벽 → 왕관 → 기업 부스 빌딩"""
    im = Image.new('RGBA', (16, 16), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if k == 0:
        box(d, 3, 2, 12, 10, PAPER); d.line([7, 10, 7, 14], fill=WOOD, width=2)
        d.line([5, 5, 10, 5], fill=GRAY); d.line([5, 7, 9, 7], fill=GRAY)
    elif k == 1:
        d.ellipse([0, 9, 15, 15], fill=(60, 170, 120), outline=OL)
        box(d, 3, 5, 12, 10, PINK); d.rectangle([5, 3, 10, 5], fill=PAPER)
    elif k == 2:
        box(d, 2, 7, 13, 14, PINK); d.rectangle([3, 8, 12, 9], fill=WHITE)
        for x in (5, 8, 11):
            d.line([x, 3, x, 6], fill=CYAN); d.point((x, 2), fill=YEL)
    elif k == 3:
        box(d, 1, 2, 14, 14, GRAY)
        for y in range(4, 14, 2):
            d.line([2, y, 13, y], fill=(110, 118, 140))
        d.rectangle([6, 12, 9, 13], fill=OL)
    elif k == 4:
        d.rectangle([0, 1, 15, 14], fill=OL)
        for r, y in enumerate(range(2, 14, 3)):
            for x in range(-3 if r % 2 else 0, 16, 6):
                d.rectangle([x + 1, y, x + 4, y + 1], fill=(200, 80, 70))
        box(d, 4, 4, 11, 10, PINK)
    elif k == 5:
        d.polygon([(1, 12), (1, 4), (5, 8), (8, 2), (11, 8), (14, 4), (14, 12)], fill=YEL, outline=OL)
        d.rectangle([1, 12, 14, 14], fill=YEL, outline=OL)
        d.point((8, 9), fill=PINK); d.point((4, 11), fill=CYAN); d.point((11, 11), fill=CYAN)
    else:
        box(d, 3, 1, 12, 15, PURP)
        for y in range(3, 14, 3):
            d.rectangle([5, y, 6, y + 1], fill=CYAN); d.rectangle([9, y, 10, y + 1], fill=CYAN)
        d.polygon([(8, 0), (9, 2), (11, 2), (9, 3), (10, 5), (8, 4), (6, 5), (7, 3), (5, 2), (7, 2)], fill=YEL)
    return im


def catalog_icon():
    """환생(코미케 참가) 버튼 아이콘 24×24: 두꺼운 카탈로그 책 + 별"""
    im = Image.new('RGBA', (24, 24), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    box(d, 3, 2, 20, 21, (176, 48, 107)); d.rectangle([4, 3, 6, 20], fill=(120, 30, 80))
    d.rectangle([19, 4, 21, 22], fill=PAPER); d.line([19, 22, 21, 22], fill=OL)
    d.polygon([(13, 6), (14, 9), (17, 9), (15, 11), (16, 14), (13, 12), (10, 14), (11, 11), (9, 9), (12, 9)], fill=YEL, outline=OL)
    d.rectangle([8, 16, 17, 17], fill=WHITE)
    return im


def uri(im):
    b = io.BytesIO(); im.save(b, 'PNG', optimize=True)
    return 'data:image/png;base64,' + base64.b64encode(b.getvalue()).decode()


def furi(name):
    return uri(G(name))


# 어시스턴트 11명(카드·배치) = 홀로 스킨 전신 도트, 설비 일꾼 7명 = 고양이 + 미니 도트
AST = ['sora', 'subaru', 'korone', 'pekora', 'okayu', 'suisei', 'marine', 'calli', 'fauna', 'miko', 'fubuki']
WORK = ['cat', 'hc_aqua_m', 'hc_mumei_m', 'hc_ollie_m', 'hc_korone_m', 'hc_subaru_m', 'hc_marine_m']

if __name__ == '__main__':
    os.makedirs(OUT, exist_ok=True)
    gens = []
    for i in range(7):
        im = icon(i); im.save(os.path.join(OUT, f'gen{i}.png')); gens.append(uri(im))
    sheet = Image.new('RGBA', (7 * 36, 36), (30, 30, 40, 255))
    for i in range(7):
        sheet.alpha_composite(Image.open(os.path.join(OUT, f'gen{i}.png')), (i * 36 + 2, 2))
    ranks = Image.new('RGBA', (7 * 20 + 28, 20), (30, 30, 40, 255))
    for k in range(7):
        ranks.alpha_composite(rank_badge(k), (k * 20 + 2, 2))
    ranks.alpha_composite(catalog_icon().resize((16, 16), Image.NEAREST), (7 * 20 + 4, 2))
    pv = Image.new('RGBA', (max(sheet.width, ranks.width), sheet.height + ranks.height), (30, 30, 40, 255))
    pv.alpha_composite(sheet, (0, 0)); pv.alpha_composite(ranks, (0, sheet.height))
    pv.resize((pv.width * 3, pv.height * 3), Image.NEAREST).save(os.path.join(OUT, '_preview.png'))
    bg = G('bg3').quantize(64).convert('RGBA')
    A = {
        'pixel': True,
        'gen': gens,
        'cheer': furi('player'),
        'bg': uri(bg),
        # 아래는 放置 장면용(모듈이 있으면 쓴다)
        'cheerFever': furi('skill_b'),
        'ast': [furi(f'hc_{m}_0') for m in AST],
        'astMini': [furi(f'hc_{m}_f') for m in AST],  # 장면 속 어시스턴트(작은 도트)
        'work': [furi(n) for n in WORK],
        'fx': {k: furi(k) for k in ('heart', 'coin', 'spark', 'gem_p')},
        'rank': [uri(rank_badge(k)) for k in range(7)],  # 서클 랭크 배지(직접 그린 도트)
        'prestige': uri(catalog_icon()),
    }
    js = 'window.IDLE_ASSETS=' + json.dumps(A, separators=(',', ':')) + ';'
    open(os.path.join(OUT, 'assets.js'), 'w').write(js)
    print('assets.js', len(js), 'bytes')
