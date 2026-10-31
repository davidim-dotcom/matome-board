#!/usr/bin/env python3
"""운영자 그림 시트에서 VN 그림을 잘라 games/vn/img/*.jpg 와 그 주소표 games/vn/vn-assets-sheet.js 를 쓴다(Pillow·numpy).

  python3 games/vn/sheets.py            # 다시 만들기
  python3 games/vn/sheets.py preview    # /tmp/vn_sheet_preview.jpg 에 자른 칸 모아 보기

원본은 games/vn/src/: sheet1.jpg(이벤트 CG 10·스탠딩·배경 13), sheet2.jpg(표정 일러), capture0.jpg(예전 폰 캡처, 서재 → 도서관).
칸 좌표는 시트를 2000px 폭으로 보고 적었고(PICK), refine() 이 그 근처의 검은 테두리 선을 찾아 안쪽만 자른다.
vn-assets-sheet.js 는 vn-assets.js(운영자 아티팩트 그림) 다음에 읽혀 같은 이름을 덮어쓴다 — 아티팩트를 다시 가져와도 이 그림이 남는다.
시나리오에서 쓰지 않는 그림도 이름을 붙여 넣어 둔다(EXTRA): 시나리오에 {t:'cg',id:'transfer'} 처럼 쓰면 바로 나온다.
"""
import json, os, sys
import numpy as np
from PIL import Image, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "src")

# 이름: (시트, x0, y0, x1, y1 — 2000px 폭 기준, 테두리 대략 위치)
CG = {
    "bully": ("sheet1", 843, 78, 1213, 327),        # 오해와 질투 (복도에서 예린 무리)
    "rhythm": ("sheet1", 1609, 78, 1980, 327),      # 방과 후 오락실 (리듬게임 대결)
    "bingsu3": ("sheet1", 52, 385, 425, 628),       # 빙수와 닥터페퍼
    "farewell": ("sheet1", 439, 385, 830, 628),     # 눈물의 기차역 이별 (상자 든 하나, 앨범 든 주인공)
    # 지금 시나리오에 자리가 없는 CG (EXTRA)
    "transfer": ("sheet1", 52, 78, 425, 327),       # 전학 첫날
    "confess": ("sheet1", 439, 78, 830, 327),       # 고백 공격
    "rescue": ("sheet1", 1227, 78, 1597, 327),      # 옥상의 구출 (시나리오의 stairs 는 혼자 앉은 장면이라 안 맞음)
    "reunion": ("sheet1", 843, 385, 1213, 628),     # 대학에서의 재회
    "campusdate": ("sheet1", 1227, 385, 1597, 628), # 캠퍼스 데이트
    "roomgame": ("sheet1", 1609, 385, 1980, 628),   # 방구석 일상 (시나리오 servertree 는 따로 접속한 장면이라 안 맞음)
}
BG = {
    "physlab": ("sheet1", 1507, 948, 1736, 1092),   # 'BG3 학교 옥상'이라 적혔지만 그림은 개수대 있는 실험실
    "station": ("sheet1", 1749, 948, 1980, 1092),   # BG4 해 질 녘 기차역 플랫폼
    "street": ("sheet1", 52, 1150, 283, 1295),      # BG5 ('교실'이라 적혔지만 그림은 동네 거리)
    "arcade": ("sheet1", 294, 1150, 525, 1295),     # BG6 오락실
    "bingsu": ("sheet1", 537, 1150, 768, 1295),     # BG7 빙수 카페
    "hall": ("sheet1", 1507, 1150, 1738, 1295),     # BG12 대학 강의실 → 대학 강당
    # EXTRA
    "grandma": ("sheet1", 780, 1150, 1010, 1295),   # BG9 시골 조부모 집
    "winter": ("sheet1", 1022, 1150, 1253, 1295),   # BG10 겨울 골목길
    "campus": ("sheet1", 1265, 1150, 1495, 1295),   # BG11 대학교 캠퍼스
    "univroom": ("sheet1", 1749, 1150, 1980, 1295), # BG13 하나의 대학 자취방 (하나가 그려져 있음)
}
LIB = ("capture0", 556, 1662, 1034, 2020)            # 예전 캡처의 서재(실제 픽셀) → library
HX = [(52, 358), (377, 682), (700, 1006), (1024, 1330), (1348, 1655), (1672, 1978)]
CX = [(52, 282), (296, 524), (538, 767), (780, 1009), (1023, 1251), (1265, 1493), (1507, 1736), (1749, 1979)]
CH = {
    "hana": {f: ("sheet2", HX[i][0], 93, HX[i][1], 402)
             for i, f in enumerate(["normal", "happy", "flustered", "focused", "pout", "crying"])},
    "sera": {f: ("sheet2", HX[i][0], 637, HX[i][1], 944) for i, f in enumerate(["normal", "angry", "shocked", "disdain"])},
    "father": {"normal": ("sheet2", CX[4][0], 1083, CX[4][1], 1297),   # 엄격
               "relief": ("sheet2", CX[5][0], 1083, CX[5][1], 1297)},  # 안도
}
EXTRA = {"transfer", "confess", "rescue", "reunion", "campusdate", "roomgame", "grandma", "winter", "campus", "univroom"}

_imgs = {}


def sheet(name):
    if name not in _imgs:
        _imgs[name] = Image.open(os.path.join(SRC, name + ".jpg")).convert("RGB")
    return _imgs[name]


def refine(im, box, win=18):
    """대략 상자의 네 변 근처(±win)에서 변 길이 대부분이 검은(<85) 줄 = 그림 틀을 찾아, 틀 안쪽만 돌려준다.
    (그림 속 선은 변 전체를 가로지르는 일이 드물다. 못 찾은 변은 대략 위치에서 6px 안쪽.)"""
    g = np.asarray(im.convert("L"))
    x0, y0, x1, y1 = box
    H, W = g.shape
    def lines(fr, pos):
        return [p for p in pos if 0 <= p < max(H, W) and fr(p) > .75]
    def pick(c, est, inner_hi):
        if not c:
            return est + (6 if inner_hi else -6)
        groups, cur = [], [c[0]]
        for p in c[1:]:
            if p == cur[-1] + 1: cur.append(p)
            else: groups.append(cur); cur = [p]
        groups.append(cur)
        gsel = min(groups, key=lambda gr: abs((gr[0] + gr[-1]) / 2 - est))
        return gsel[-1] + 2 if inner_hi else gsel[0] - 2
    xs, ys = slice(x0 + 20, x1 - 20), slice(y0 + 20, y1 - 20)
    top = pick(lines(lambda y: (g[y, xs] < 85).mean(), range(y0 - win, y0 + win)), y0, True)
    bot = pick(lines(lambda y: (g[y, xs] < 85).mean() if y < H else 0, range(y1 - win, y1 + win)), y1, False)
    lef = pick(lines(lambda x: (g[ys, x] < 85).mean(), range(x0 - win, x0 + win)), x0, True)
    rig = pick(lines(lambda x: (g[ys, x] < 85).mean() if x < W else 0, range(x1 - win, x1 + win)), x1, False)
    return (lef, top, rig + 1, bot + 1)


def cut(spec, frame=True):
    name, x0, y0, x1, y1 = spec
    im = sheet(name)
    if name.startswith("sheet"):
        k = im.width / 2000
        box = tuple(round(v * k) for v in (x0, y0, x1, y1))
        if frame:
            box = refine(im, box)
    else:
        box = (x0, y0, x1, y1)
    return im.crop(box)


def cutout(im, tol=30, fade=.16):
    """표정 일러의 크림색 종이 바탕을 따낸다(키리누키): 위·양옆 위쪽에서 이어진 종이색만 지우고(인물 윤곽선이 막음),
    가장자리를 1px 깎아 흐리게 하고, 몸이 잘린 아래쪽은 fade 비율만큼 서서히 투명하게 해 배경에 녹아들게 한다."""
    from PIL import ImageFilter
    a = np.asarray(im.convert("RGB")).astype(int)
    H, W, _ = a.shape
    paper = np.median(a[:3].reshape(-1, 3), axis=0)
    near = np.sqrt(((a - paper) ** 2).sum(2)) < tol
    bg = np.zeros((H, W), bool)
    st = [(0, x) for x in range(W)] + [(y, 0) for y in range(int(H * .6))] + [(y, W - 1) for y in range(int(H * .6))]
    st = [p for p in st if near[p]]
    for y, x in st: bg[y, x] = True
    while st:
        y, x = st.pop()
        for yy, xx in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
            if 0 <= yy < H and 0 <= xx < W and near[yy, xx] and not bg[yy, xx]:
                bg[yy, xx] = True; st.append((yy, xx))
    al = Image.fromarray(np.where(bg, 0, 255).astype("uint8"))
    al = al.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(.9))
    al = np.asarray(al).astype(float)
    f0 = int(H * (1 - fade))
    al[f0:] *= np.linspace(1, 0, H - f0)[:, None] ** 1.3
    out = im.convert("RGBA"); out.putalpha(Image.fromarray(al.clip(0, 255).astype("uint8")))
    return out


def build():
    out = {"bg": {}, "ch": {}, "cg": {}}
    for k, s in CG.items():
        out["cg"][k] = cut(s)
    for k, s in BG.items():
        out["bg"][k] = cut(s).filter(ImageFilter.UnsharpMask(1.2, 40, 2))
    out["bg"]["library"] = cut(LIB, frame=False).resize((480, 360), Image.LANCZOS)
    for c, faces in CH.items():
        out["ch"][c] = {}
        for f, s in faces.items():
            im = cut(s)
            w = min(im.size)  # 정사각형으로(인물 칸이 1:1)
            out["ch"][c][f] = cutout(im.crop(((im.width - w) // 2, 0, (im.width - w) // 2 + w, w)))
    return out


def main():
    imgs = build()
    if sys.argv[1:] == ["preview"]:
        tiles = [(k, v) for kind in imgs for k, v in imgs[kind].items() if not isinstance(v, dict)]
        tiles += [(f"{c}.{f}", v) for c, d in imgs["ch"].items() for f, v in d.items()]
        W, cols = 300, 6
        rows = (len(tiles) + cols - 1) // cols
        sheetp = Image.new("RGB", (W * cols, rows * (W + 20)), "white")
        from PIL import ImageDraw
        d = ImageDraw.Draw(sheetp)
        for i, (k, v) in enumerate(tiles):
            t = v.copy(); t.thumbnail((W - 6, W - 6))
            x, y = (i % cols) * W, (i // cols) * (W + 20)
            sheetp.paste(t, (x + 3, y + 3)); d.text((x + 4, y + W + 2), f"{k} {v.size[0]}x{v.size[1]}", fill="black")
        sheetp.save("/tmp/vn_sheet_preview.jpg", quality=85)
        print("/tmp/vn_sheet_preview.jpg")
        return
    # 그림은 파일로(games/vn/img/), 엔진은 vn.html 기준 주소 'vn/img/…' 로 쓴다 — 장면에 나올 때만 받는다
    os.makedirs(os.path.join(HERE, "img"), exist_ok=True)
    for f in os.listdir(os.path.join(HERE, "img")):
        if f.endswith((".jpg", ".webp")): os.remove(os.path.join(HERE, "img", f))
    def save(fn, im):
        if im.mode == "RGBA":  # 따낸 인물은 투명 WebP
            fn = fn[:-4] + ".webp"
            im.save(os.path.join(HERE, "img", fn), "WEBP", quality=88, method=6)
        else:
            im.save(os.path.join(HERE, "img", fn), "JPEG", quality=84, optimize=True, progressive=True)
        return "vn/img/" + fn
    data = {}
    for kind, d in imgs.items():
        data[kind] = {}
        for k, v in d.items():
            if isinstance(v, dict):
                data[kind][k] = {f: save(f"{kind}_{k}_{f}.jpg", im) for f, im in v.items()}
            else:
                data[kind][k] = save(f"{kind}_{k}.jpg", v)
    names = {kind: sorted(d) for kind, d in imgs.items()}
    js = ("/* 운영자 그림 시트에서 잘라 낸 VN 그림 — games/vn/sheets.py 가 쓴다(손으로 고치지 않음).\n"
          "   vn-assets.js(아티팩트 그림) 다음에 읽혀 같은 이름을 덮어쓴다. 인물은 표정 맵(시나리오 show/say 의 face).\n"
          + "".join(f"   {k}: {' '.join(v)}\n" for k, v in names.items())
          + "   hana 표정: normal happy flustered focused pout crying / sera: normal angry shocked disdain / father: normal(엄격) relief(안도)\n"
          + "   시나리오에 아직 자리가 없는 그림: " + " ".join(sorted(EXTRA)) + "\n*/\n"
          + "(function(S){var A=window.VN_ASSETS=window.VN_ASSETS||{};for(var k in S){A[k]=A[k]||{};for(var n in S[k])A[k][n]=S[k][n]}})("
          + json.dumps(data, ensure_ascii=False) + ");\n")
    p = os.path.join(HERE, "vn-assets-sheet.js")
    open(p, "w", encoding="utf-8").write(js)
    print(f"썼음 games/vn/vn-assets-sheet.js ({len(js.encode()) // 1024}KB)")
    for k, v in names.items():
        print(" ", k, ", ".join(v))


if __name__ == "__main__":
    main()
