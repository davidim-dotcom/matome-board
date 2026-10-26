"""extract.py 의 fit() 과 같은 축소(프리멀티플라이 BOX → 알파 115 → 40색 → 1px 윤곽)를 '배율'로 하는 판. extract_anim.py 가 쓴다
   (선수의 모든 프레임에 같은 배율을 써야 프레임끼리 크기가 맞으므로 최대 변 길이가 아니라 배율을 받는다)"""
import numpy as np
from PIL import Image

def fit(p, sc, outline=True, colors=40):
    a = np.asarray(p).astype(float); al = a[..., 3:4] / 255
    pm = Image.fromarray(np.dstack([(a[..., :3] * al).astype(np.uint8), a[..., 3].astype(np.uint8)]), 'RGBA')
    w, h = max(1, round(p.width * sc)), max(1, round(p.height * sc))
    q = np.asarray(pm.resize((w, h), Image.BOX)).astype(float)
    al = q[..., 3:4] / 255; rgb = np.where(al > 0, q[..., :3] / np.maximum(al, 1e-6), 0)
    a = np.dstack([np.clip(rgb, 0, 255).astype(np.uint8), np.where(q[..., 3] >= 115, 255, 0).astype(np.uint8)])
    if colors:
        rgb = Image.fromarray(a[..., :3], 'RGB').quantize(colors, method=Image.MEDIANCUT, dither=Image.NONE).convert('RGB')
        a[..., :3] = np.asarray(rgb)
    if outline:
        m = a[..., 3] > 0; pad = np.pad(m, 1, constant_values=False)
        ring = (pad[:-2, 1:-1] | pad[2:, 1:-1] | pad[1:-1, :-2] | pad[1:-1, 2:]) & ~m
        a[ring] = (26, 20, 38, 255)
    return Image.fromarray(a, 'RGBA')
