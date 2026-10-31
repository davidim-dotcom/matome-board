#!/usr/bin/env python3
"""페이지 스크립트 문법 검사 — index.html·games/merge.html 의 인라인 <script> 와 sw.js·games/holo-voice.js·games/vn/*.js 를 node --check 로.
  python3 tests/jscheck.py      (node 필요)"""
import os, re, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
bad, n = 0, 0
with tempfile.TemporaryDirectory() as tmp:
    jobs = []
    for f in ("index.html", "games/merge.html", "games/idle.html", "games/penlight.html", "games/ensei.html", "games/vn.html"):
        page = open(os.path.join(ROOT, f), encoding="utf-8").read()
        for i, m in enumerate(re.finditer(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", page, re.S)):
            line = page[:m.start(1)].count("\n") + 1
            p = os.path.join(tmp, f"{f.replace('/', '_')}_{i}.js")
            open(p, "w", encoding="utf-8").write("\n" * (line - 1) + m.group(1))  # 줄 번호를 원래 파일과 맞춘다
            jobs.append((f"{f} <script> #{i + 1} (줄 {line})", p))
    jobs += [(f, os.path.join(ROOT, f)) for f in ("sw.js", "games/holo-voice.js", "games/vn/vn-assets.js", "games/vn/vn-assets-sheet.js", "games/vn/vn-script.js", "games/vn/vn-engine.js", "games/vn/vn-bgm.js")]
    for name, p in jobs:
        n += 1
        r = subprocess.run(["node", "--check", p], capture_output=True, text=True)
        if r.returncode:
            bad += 1; print(f"FAIL {name}\n{r.stderr.strip()}")
        else:
            print(f"OK   {name}")
print(f"→ {n - bad}/{n} 통과")
sys.exit(1 if bad else 0)
