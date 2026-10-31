#!/usr/bin/env python3
"""비주얼 노벨 가져오기 — 운영자 아티팩트(한 장짜리 미연시 HTML)를 세 파일로 나눠 저장소에 넣는다.

  python3 games/vn/import.py 페이지.html
  python3 games/vn/import.py 읽기결과1.txt 읽기결과2.txt ...   (read_artifact 결과 JSON 을 여러 조각으로 받았을 때, 순서 상관없음)

페이지 안의 표시 주석 세 블록을 찾는다:
  <!-- ===== VN 리소스 ... -->   … <!-- ===== end VN 리소스 ===== -->   → games/vn/vn-assets.js   (window.VN_ASSETS)
  <!-- ===== VN 시나리오 ... -->  … <!-- ===== end VN 시나리오 ===== --> → games/vn/vn-script.js   (window.VN_SCRIPT)
  <!-- ===== VN 엔진 ... -->     … <!-- ===== end VN 엔진 ===== -->   → games/vn/vn-engine.js + vn-engine.css
games/vn.html 은 <section id="vn"> 과 assets → script → engine 순서로 읽는 껍데기라 건드리지 않는다.

덧붙이는 처리
  · 그림: vn-assets.js 는 아티팩트 그림 그대로. 운영자 그림 시트에서 자른 그림은 따로 vn-assets-sheet.js(games/vn/sheets.py)가
    그 다음에 읽혀 같은 이름을 덮어쓰므로, 아티팩트를 다시 가져와도 시트 그림이 남는다.
  · 엔진의 영어 표기 두 곳을 한국어로(장 카드 CHAPTER n → 제n장, 빈 CG 칸 [CG] → [이벤트 그림]), 대사 face 로 표정 바꾸기 한 줄.
  · 대사 표정: games/vn/faces.json 의 표정을 faces.py 가 시나리오 say 줄에 다시 넣는다(아티팩트 시나리오엔 표정이 없어서).
"""
import json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
BLOCKS = [("assets", "VN 리소스"), ("script", "VN 시나리오"), ("engine", "VN 엔진")]
KO_FIX = [(r"`CHAPTER \$\{n\}`", "`제${n}장`"), (r"\[CG\]", "[이벤트 그림]"),
          # 대사(say)의 face 로 화면의 그 인물 표정을 바꾼다(원본 엔진은 show 의 face 만 봄)
          (r"case 'say':return show\(op\.who,op\.text\);", "case 'say':if(op.face&&G.chars[op.who])G.chars[op.who].face=op.face;return show(op.who,op.text);")]


def read_source(paths):
    """HTML 파일 하나, 또는 read_artifact 결과(JSON [{type,text}]) 조각들을 offset 순으로 이어 붙인다."""
    parts = []
    for p in paths:
        raw = open(p, encoding="utf-8").read()
        try:
            d = json.loads(raw)
        except ValueError:
            parts.append((0, raw)); continue
        meta = {}
        try:
            meta = json.loads(d[0]["text"])
        except Exception:
            pass
        body = max((x["text"] for x in d), key=len)
        body = re.sub(r"^<untrusted-document-[0-9a-f]+>", "", body)
        body = re.sub(r"</untrusted-document-[0-9a-f]+>\s*$", "", body)
        parts.append((int(meta.get("offset") or 1), body))
    parts.sort(key=lambda x: x[0])
    out = ""
    for _, b in parts:
        if out and not out.endswith("\n"):
            out += "\n"
        out += b
    return out


def block(page, name):
    i = page.find("<!-- ===== " + name)
    j = page.find("<!-- ===== end " + name, i)
    if i < 0 or j < 0:
        sys.exit(f"'{name}' 블록 표시 주석을 못 찾음 — 아티팩트 구조가 바뀌었는지 확인")
    return page[i:j]


def split(b):
    comments = [c.strip() for c in re.findall(r"<!--(.*?)-->", b, re.S)]
    css = "\n".join(m.strip() for m in re.findall(r"<style[^>]*>(.*?)</style>", b, re.S))
    js = "\n".join(m.strip("\n") for m in re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", b, re.S))
    head = "\n".join(c for c in comments if c).replace("*/", "* /")
    return head, css, js


def merge_assets(js, keep_old):
    m = re.match(r"\s*window\.VN_ASSETS\s*=\s*(\{.*\})\s*;?\s*$", js, re.S)
    if not m:
        print("! VN_ASSETS 를 JSON 으로 못 읽어 그대로 씀(저장소 그림 합치기 건너뜀)")
        return js, []
    new = json.loads(m.group(1))
    kept = []
    old_p = os.path.join(HERE, "vn-assets.js")
    if keep_old and os.path.exists(old_p):
        om = re.search(r"window\.VN_ASSETS\s*=\s*(\{.*\})\s*;", open(old_p, encoding="utf-8").read(), re.S)
        if om:
            old = json.loads(om.group(1))
            for kind, items in old.items():
                for k, v in items.items():
                    if k not in new.setdefault(kind, {}):
                        new[kind][k] = v; kept.append(f"{kind}.{k}")
    return "window.VN_ASSETS=" + json.dumps(new, ensure_ascii=False) + ";", kept


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        sys.exit(__doc__)
    page = read_source(args)
    out = {}
    for key, name in BLOCKS:
        out[key] = split(block(page, name))
    # 그림
    head, _, js = out["assets"]
    js, kept = merge_assets(js, False)
    files = {"vn-assets.js": f"/*\n{head}\n*/\n{js}\n"}
    # 시나리오
    head, _, js = out["script"]
    files["vn-script.js"] = f"/*\n{head}\n*/\n{js}\n"
    # 엔진
    head, css, js = out["engine"]
    for pat, rep in KO_FIX:
        js, n = re.subn(pat, rep, js)
        if not n:
            print(f"! 한국어 표기 바꾸기: '{pat}' 를 못 찾음(엔진 문구가 바뀌었으면 KO_FIX 를 고칠 것)")
    files["vn-engine.js"] = f"/*\n{head}\n*/\n{js}\n"
    files["vn-engine.css"] = f"/* VN 엔진 스타일(운영자 vn-engine 블록의 <style>) */\n{css}\n"
    for f, s in files.items():
        open(os.path.join(HERE, f), "w", encoding="utf-8").write(s)
        print(f"썼음 games/vn/{f} ({len(s.encode()) // 1024}KB)")
    sys.path.insert(0, HERE)
    import faces
    faces.apply()
    # 요약
    sc = files["vn-script.js"]
    ver = re.search(r"ver:'([^']*)'", sc)
    print(f"시나리오 버전 {ver.group(1) if ver else '?'} · 장면 {len(re.findall(chr(10) + r'\s*\w+:\[', sc))}개")
    a = json.loads(re.search(r"=(\{.*\});", files["vn-assets.js"], re.S).group(1)) if files["vn-assets.js"].count("window.VN_ASSETS={") else {}
    print("그림:", " / ".join(f"{k} {', '.join(v)}" for k, v in a.items()))
    if kept:
        print("저장소에만 있어 남긴 그림:", ", ".join(kept))


if __name__ == "__main__":
    main()
