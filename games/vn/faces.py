#!/usr/bin/env python3
"""VN 대사 표정 넣기 — games/vn/faces.json 의 표정을 games/vn/vn-script.js 의 say 줄에 face:'…' 로 적는다.

  python3 games/vn/faces.py          # 적용(import.py 가 아티팩트를 가져올 때마다 부른다)

faces.json 은 한 줄에 하나 {scene, who, text(대사 앞 70자), face}. 운영자 아티팩트 시나리오에는 표정이 없어서,
가져온 뒤 이 표로 다시 넣는다(같은 장면·인물·대사 앞부분이 같은 줄, 같은 대사가 여럿이면 차례대로).
아티팩트에 이미 face 가 적힌 줄은 그대로 둔다. 대사가 바뀌어 못 찾은 줄은 끝에 알려 준다(표정은 그 줄만 빠짐).
표정 이름: hana normal happy flustered focused pout crying / sera normal angry shocked disdain / father normal relief.
엔진은 say 의 face 로 그 인물이 화면에 있으면 표정을 바꾸고, 다음 face 까지 유지한다(show 는 face 가 없으면 normal).
"""
import collections, json, os, re

HERE = os.path.dirname(os.path.abspath(__file__))


def apply(verbose=True):
    rows = json.load(open(os.path.join(HERE, "faces.json"), encoding="utf-8"))
    q = collections.defaultdict(collections.deque)
    for r in rows:
        q[(r["scene"], r["who"], r["text"][:70])].append(r["face"])
    p = os.path.join(HERE, "vn-script.js")
    src = open(p, encoding="utf-8").read()
    out, scene, n = [], None, 0
    for ln in src.split("\n"):
        m = re.match(r"\s*(\w+):\[\s*$", ln)
        if m:
            scene = m.group(1)
        def put(mo):
            nonlocal n
            op = mo.group(0)
            if "face:" in op:
                return op
            w = re.search(r"who:'(\w+)'", op); t = re.search(r"text:'((?:[^'\\]|\\.)*)'", op)
            if not (w and t):
                return op
            key = (scene, w.group(1), t.group(1)[:70])
            if not q.get(key):
                return op
            n += 1
            return op.replace(f"who:'{w.group(1)}',", f"who:'{w.group(1)}',face:'{q[key].popleft()}',", 1)
        out.append(re.sub(r"\{t:'say'[^{}]*\}", put, ln))
    open(p, "w", encoding="utf-8").write("\n".join(out))
    left = [(k, len(v)) for k, v in q.items() if v]
    if verbose:
        print(f"표정 넣음 {n}줄" + (f" · 못 찾은 대사 {sum(c for _, c in left)}줄" if left else ""))
        for (sc, who, t), c in left[:20]:
            print(f"  ! {sc} {who}: {t[:40]}")
    return n, left


if __name__ == "__main__":
    apply()
