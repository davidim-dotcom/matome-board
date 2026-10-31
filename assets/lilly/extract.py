"""메이드 버스터 릴리 새 그림(2026-10 말, 운영자가 Gemini 로 만든 시트)을 잘라 보드에 쓸 PNG 로 만든다.

  python3 assets/lilly/extract.py        # assets/lilly/*.png 와 앱 아이콘(assets/icon-lilly-*.png, apple-touch-icon-lilly.png)을 다시 씀

src/poster.jpg  (2816×1536): 가운데 포스터(날개 달고 쏘는 릴리)와 오른쪽 둥근 배지(윙크·엄지척 얼굴)
src/samples.jpg (2816×1536): 고해상도 도트 견본 5칸(발차기·윙크 얼굴·비행·단말기·전투복)
src/extended.jpg (2760×1504): 확장 도시에(HD 패널: 비행·빗자루(화난 얼굴)·발차기·단말기·표정·전투복)
src/dossier.jpg (2816×1536): 9열×8행 도트 애니메이션 시트(대기·인사·기지개·걷기·달리기·대시·회전 춤·만세·테크노),
                              칸마다 남색 우주 배경 + 격자선
결과
  badge.png        둥근 배지 512px(원 밖 투명) — 제목 옆 로고·아이콘·주말 한 장
  poster.png       포스터 윗부분(글자 위까지) — og 그림용
  cutin.jpg        화난 얼굴(이를 악문 표정) 정사각 — 弾幕 보스 등장·필살 컷인
  ../game/lilly_armor.png  전투복 릴리 전신(높이 46px) — 弾幕 해금 스킨 「アーマー」의 자기 그림, armor.png 는 큰 미리보기(스킨 버튼)
  anim_<이름>.png  애니메이션 한 줄(프레임 8칸, 칸 크기는 그 애니메이션 프레임들을 다 담는 상자, 발 기준 아래 정렬)
                   + anim.json {이름: [칸 폭, 칸 높이, 프레임 수]}
배경 지우기: 칸 가장자리에서 시작해 배경색(칸 가장자리 중앙값)에서 가까운 어두운 색만 flood 로 지우고,
남은 것 중 큰 덩어리(몸통)와 그 근처 덩어리만 둔다(별·성운 점은 작아서 빠진다).
"""
import json, os
from collections import deque
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
SRC = os.path.join(HERE, 'src')

# 시트 격자(2816 폭 기준, 격자선 사이 칸 안쪽)
COLS = [(41, 311), (343, 627), (658, 928), (960, 1241), (1273, 1542), (1575, 1826), (1859, 2136), (2169, 2445), (2478, 2750)]
ROWS = [(145, 298), (303, 455), (459, 615), (620, 759), (764, 913), (917, 1062), (1067, 1217), (1222, 1368)]
ANIMS = {'walk': 3, 'twirl': 6, 'jig': 7}  # 열 번호. 대기(0)·인사(1)는 상반신 그림이라 무대에 안 맞고, 달리기(4)·대시(5)는 먼지·잔상이 몸에 붙어 깨끗이 안 떨어져서 뺐다. 필요하면 여기 더하고 다시 돌린다


def cut_cell(a, thr=34, lum_max=70):
    """칸 하나(RGB 배열) → RGBA. 배경 flood + 큰 덩어리만. thr = 배경색과의 거리 기준(배경이 단색이면 작게)."""
    h, w, _ = a.shape
    ai = a.astype(int)
    edge = np.concatenate([ai[:3].reshape(-1, 3), ai[-3:].reshape(-1, 3), ai[:, :3].reshape(-1, 3), ai[:, -3:].reshape(-1, 3)])
    bg = np.median(edge, 0)
    dist = np.sqrt(((ai - bg) ** 2).sum(2))
    lum = ai.mean(2)
    cand = (dist < thr) & (lum < lum_max)    # 배경 후보: 배경색 근처의 어두운 색
    seen = np.zeros((h, w), bool)
    q = deque()
    for y in range(h):
        for x in (0, w - 1):
            if cand[y, x] and not seen[y, x]: seen[y, x] = True; q.append((y, x))
    for x in range(w):
        for y in (0, h - 1):
            if cand[y, x] and not seen[y, x]: seen[y, x] = True; q.append((y, x))
    while q:
        y, x = q.popleft()
        for yy, xx in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
            if 0 <= yy < h and 0 <= xx < w and cand[yy, xx] and not seen[yy, xx]:
                seen[yy, xx] = True; q.append((yy, xx))
    fg = ~seen
    # 덩어리 나누기
    lab = np.zeros((h, w), int); n = 0; sizes = [0]; boxes = [None]
    for y in range(h):
        for x in range(w):
            if fg[y, x] and not lab[y, x]:
                n += 1; lab[y, x] = n; q = deque([(y, x)]); c = 0; y0 = y1 = y; x0 = x1 = x
                while q:
                    cy, cx = q.popleft(); c += 1; y0 = min(y0, cy); y1 = max(y1, cy); x0 = min(x0, cx); x1 = max(x1, cx)
                    for yy, xx in ((cy + 1, cx), (cy - 1, cx), (cy, cx + 1), (cy, cx - 1)):
                        if 0 <= yy < h and 0 <= xx < w and fg[yy, xx] and not lab[yy, xx]:
                            lab[yy, xx] = n; q.append((yy, xx))
                sizes.append(c); boxes.append((x0, y0, x1, y1))
    if n == 0:
        return None
    big = int(np.argmax(sizes))
    bx0, by0, bx1, by1 = boxes[big]
    keep = np.zeros((h, w), bool)
    for i in range(1, n + 1):
        x0, y0, x1, y1 = boxes[i]
        near = x1 >= bx0 - 10 and x0 <= bx1 + 10 and y1 >= by0 - 10 and y0 <= by1 + 10
        if i == big or (sizes[i] >= 40 and near):
            keep |= lab == i
    out = np.dstack([a, (keep * 255).astype(np.uint8)])
    im = Image.fromarray(out, 'RGBA')
    # 가장자리 1px 을 살짝 부드럽게(JPEG 번짐 테두리)
    al = im.getchannel('A').filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(.6))
    im.putalpha(al)
    return im.crop(im.getbbox())


def anims():
    sheet = np.asarray(Image.open(os.path.join(SRC, 'dossier.jpg')).convert('RGB'))
    meta = {}
    for name, col in ANIMS.items():
        x0, x1 = COLS[col]
        frames = [cut_cell(sheet[y0:y1, x0:x1]) for (y0, y1) in ROWS]
        frames = [f for f in frames if f is not None]
        fw = max(f.width for f in frames) + 2; fh = max(f.height for f in frames) + 2
        strip = Image.new('RGBA', (fw * len(frames), fh), (0, 0, 0, 0))
        for i, f in enumerate(frames):
            strip.paste(f, (i * fw + (fw - f.width) // 2, fh - f.height - 1), f)  # 발 기준 아래 정렬·가운데
        q = strip.quantize(colors=96, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.NONE)  # 도트 그림이라 96색이면 충분, 파일이 1/3
        q.save(os.path.join(HERE, f'anim_{name}.png'), optimize=True)
        meta[name] = [fw, fh, len(frames)]
        print(name, fw, fh, len(frames))
    with open(os.path.join(HERE, 'anim.json'), 'w') as f:
        json.dump(meta, f)


def badge():
    im = Image.open(os.path.join(SRC, 'poster.jpg')).convert('RGB')
    s = im.width / 2000
    crop = im.crop((int(1480 * s), int(250 * s), int(1960 * s), int(720 * s)))
    cx, cy, R = 334.2, 325.3, 318          # 바깥 고리까지(고리 색으로 원을 맞춰 잼)
    box = (int(cx - R), int(cy - R), int(cx + R), int(cy + R))
    sq = crop.crop(box)
    S = 4 * sq.width
    m = Image.new('L', (S, S), 0); ImageDraw.Draw(m).ellipse((2, 2, S - 3, S - 3), fill=255)
    m = m.resize(sq.size, Image.LANCZOS)
    sq = sq.convert('RGBA'); sq.putalpha(m)
    out = sq.resize((512, 512), Image.LANCZOS)
    out.resize((256, 256), Image.LANCZOS).quantize(256, method=Image.Quantize.FASTOCTREE).save(os.path.join(HERE, 'badge.png'), optimize=True)  # 페이지에는 최대 96px 로만 쓴다
    return out


def poster():
    im = Image.open(os.path.join(SRC, 'poster.jpg')).convert('RGB')
    s = im.width / 2000
    p = im.crop((int(672 * s), int(38 * s), int(1418 * s), int(840 * s)))  # 'LILLY BUSTERS' 글자 위까지
    p = p.resize((p.width * 900 // p.height, 900), Image.LANCZOS)
    p.save(os.path.join(HERE, 'poster.jpg'), quality=86, optimize=True)


def cutin():
    im = Image.open(os.path.join(SRC, 'extended.jpg')).convert('RGB')
    s = im.width / 2000
    c = im.crop((int(1158 * s), int(42 * s), int(1560 * s), int(448 * s)))  # 'BATTLE-BROOM (HD)' 칸 안쪽(테두리 빼고)
    c.resize((360, 360), Image.LANCZOS).save(os.path.join(HERE, 'cutin.jpg'), quality=86, optimize=True)


def armor():
    im = Image.open(os.path.join(SRC, 'samples.jpg')).convert('RGB')
    s = im.width / 2000
    a = np.asarray(im.crop((int(1598 * s), int(198 * s), int(1938 * s), int(892 * s))))  # 전투복 칸 안쪽
    f = cut_cell(a, thr=12, lum_max=255)  # 이 칸 배경은 거의 단색(표준편차 0.4)이라 좁게: 넓으면 검은 수트까지 지워졌다
    big = f.resize((f.width * 160 // f.height, 160), Image.LANCZOS)
    big.save(os.path.join(HERE, 'armor.png'), optimize=True)
    # 弾幕 자기 그림 크기(기본 player 36×41 와 비슷). BOX 평균은 얼굴이 뭉개져서 LANCZOS + 선명하게 + 32색
    small = f.resize((max(1, f.width * 48 // f.height), 48), Image.LANCZOS).filter(ImageFilter.UnsharpMask(1.2, 120, 2))
    al = small.getchannel('A').point(lambda v: 255 if v >= 120 else 0)  # 도트답게 알파는 0/255
    small = small.convert('RGB').quantize(32, method=Image.Quantize.MEDIANCUT).convert('RGBA'); small.putalpha(al)
    small.save(os.path.join(ROOT, 'assets', 'game', 'lilly_armor.png'), optimize=True)
    print('armor', small.size, big.size)


def icons(b):
    BG = (19, 21, 42)
    def tile(size, pad, rounded):
        t = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        if rounded:
            k = 4 * size; mm = Image.new('L', (k, k), 0); ImageDraw.Draw(mm).rounded_rectangle((0, 0, k - 1, k - 1), radius=k * .22, fill=255)
            bgl = Image.new('RGBA', (size, size), BG + (255,)); bgl.putalpha(mm.resize((size, size), Image.LANCZOS)); t.alpha_composite(bgl)
        else:
            t = Image.new('RGBA', (size, size), BG + (255,))
        inner = int(size * (1 - 2 * pad))
        bb = b.resize((inner, inner), Image.LANCZOS)
        t.alpha_composite(bb, ((size - inner) // 2, (size - inner) // 2))
        return t
    q = lambda im: im.quantize(256, method=Image.Quantize.FASTOCTREE)  # 256색이면 눈으로 차이가 없고 파일이 1/3
    q(tile(512, .06, True)).save(os.path.join(ROOT, 'assets', 'icon-lilly-512.png'), optimize=True)
    q(tile(192, .06, True)).save(os.path.join(ROOT, 'assets', 'icon-lilly-192.png'), optimize=True)
    tile(180, .07, False).convert('RGB').quantize(256).save(os.path.join(ROOT, 'assets', 'apple-touch-icon-lilly.png'), optimize=True)
    tile(512, .14, False).convert('RGB').quantize(256).save(os.path.join(ROOT, 'assets', 'icon-lilly-maskable-512.png'), optimize=True)  # 안전 영역(가운데 80%) 안


if __name__ == '__main__':
    anims()
    cutin()
    armor()
    b = badge()
    poster()
    icons(b)
