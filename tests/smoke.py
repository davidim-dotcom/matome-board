#!/usr/bin/env python3
"""수집기 스모크 테스트 — 네트워크 없이 가짜 피드로 collector.py 를 한 바퀴 돌린다(.github/workflows/test.yml, PR 마다).

저장소를 임시 폴더에 복사해서 돌리므로 data/ 는 바뀌지 않는다. 표준 라이브러리만 쓴다.
  python3 tests/smoke.py
확인하는 것: 모든 출처가 가짜 피드를 읽어 OK(이름 오류 같은 코드 고장이면 여기서 FAIL), main() 이 끝까지 돌아
items/meta/feed/달력 파일을 씀, 출처 절반 넘게 실패하면 데이터를 안 쓰고 종료 코드 3, 출처·고장 알림 이슈 흐름, 번역 용어집, 주간 초안.
"""
import json, os, shutil, sys, tempfile, traceback, urllib.parse
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from xml.sax.saxutils import escape

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = tempfile.mkdtemp(prefix="matome-smoke-")
shutil.copy(os.path.join(ROOT, "collector.py"), TMP)
shutil.copytree(os.path.join(ROOT, "data"), os.path.join(TMP, "data"))
os.environ["RUNNER_TEMP"] = TMP
os.environ.pop("HOLODEX_API_KEY", None)
sys.path.insert(0, TMP)
import collector as C  # noqa: E402  (임시 폴더의 사본: DATA 도 사본을 가리킨다)

assert C.DATA.startswith(TMP), C.DATA
C.time.sleep = lambda *_: None
NOW = datetime.now(timezone(timedelta(hours=9)))
D1, D2 = (NOW + timedelta(days=20)), (NOW + timedelta(days=30))
JA = [f"「薬屋のひとりごと」コラボカフェ 池袋で{D1.month}月{D1.day}日〜{D2.month}月{D2.day}日開催",
      f"ホロライブ 3Dライブ {D1.month}月{D1.day}日 東京ガーデンシアター チケット先行受付開始",
      f"ちいかわ ポップアップストア 渋谷で開催決定 {D1.month}月{D1.day}日から",
      f"『ウマ娘』原画展 {D1.month}月{D1.day}日〜{D2.month}月{D2.day}日 秋葉原UDX"]
KO = [f"성수 '귀멸의 칼날' 팝업스토어 오픈…{D1.month}월 {D1.day}일까지",
      f"홍대에 '체인소 맨' 애니 콜라보 카페 상륙 {D1.month}월 {D1.day}일",
      "코엑스 '진격의 거인' 애니 전시회 개최"]
calls = []
FAIL_ALL = False


def rss(titles, base):
    d = format_datetime(NOW - timedelta(hours=1))
    items = "".join(f"<item><title>{t}</title><link>{escape(base)}#{i}</link><description>{t} 詳細</description><pubDate>{d}</pubDate></item>"
                    for i, t in enumerate(titles))
    return f'<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>t</title>{items}</channel></rss>'.encode()


def fake_fetch(url, headers=None, data=None):
    calls.append(url)
    if FAIL_ALL:
        raise OSError("가짜 네트워크 고장")
    u = urllib.parse.urlparse(url)
    if "translate.googleapis.com" in url:
        q = urllib.parse.parse_qs(u.query)["q"][0]
        return json.dumps([[["[번역]" + q, q]]], ensure_ascii=False).encode()
    if "/wp-json/" in url:
        return json.dumps([{"title": {"rendered": t}, "excerpt": {"rendered": t}, "link": f"https://collabo-cafe.com/events/smoke{i}/",
                            "date_gmt": (NOW - timedelta(hours=2)).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")}
                           for i, t in enumerate(JA)], ensure_ascii=False).encode()
    if "nijisanji.jp/api/news" in url:
        return json.dumps({"newsList": [{"id": f"s{i}", "title": "にじさんじ " + t, "publishedAtForUser": NOW.strftime("%Y-%m-%d %H:%M"),
                                         "thumbnail": {"url": "https://example.com/a.jpg"}} for i, t in enumerate(JA)]}, ensure_ascii=False).encode()
    if "anime.eiga.com/event/cal/" in url:
        evs = [{"@type": "Event", "name": t, "url": f"{url}e{i}", "startDate": D1.strftime("%Y-%m-%dT18:00:00"), "description": "イベント",
                "location": {"@type": "Place", "name": "東京ガーデンシアター", "geo": {"latitude": 35.645, "longitude": 139.79}}} for i, t in enumerate(JA)]
        return f'<html><script type="application/ld+json">{json.dumps(evs, ensure_ascii=False)}</script></html>'.encode()
    if "news.google.com" in url and "hl=ko" in url:
        return rss([t + " - 스모크일보" for t in KO], url)
    if url.rstrip("/") in SITES:  # site 종류: 첫 화면에서 RSS 링크를 찾는다
        return f'<html><head><link rel="alternate" type="application/rss+xml" href="{url.rstrip("/")}/smoke.rss"></head></html>'.encode()
    return rss(JA, url)  # rss·youtube·Togetter·기사 페이지(보강)


class Resp:
    def __init__(self, b, url): self.b, self.url, self.status, self.headers = b, url, 200, {}
    def read(self, *a): return self.b
    def geturl(self): return self.url
    def __enter__(self): return self
    def __exit__(self, *a): return False


def fake_urlopen(req, timeout=None, **kw):
    # collector.fetch 는 그대로 두고 그 아래(urlopen)만 바꾼다 → fetch 안의 코드(UA 헤더 등)가 고장 나도 여기서 걸린다
    url = req.full_url if hasattr(req, "full_url") else req
    return Resp(fake_fetch(url), url)


SITES = {s["url"].rstrip("/") for s in C.SOURCES if s["type"] == "site"}
C.urllib.request.urlopen = fake_urlopen
C._cache.clear()
results = []


def check(name, fn):
    try:
        fn(); results.append((name, None)); print(f"OK   {name}")
    except Exception:
        results.append((name, traceback.format_exc())); print(f"FAIL {name}\n{traceback.format_exc()}")


def t_sources():
    ref, bad = C.datetime.now(C.JST), []
    for s in C.SOURCES:
        if s["type"] == "holodex": continue
        try:
            C.collect(s, ref)
            if C.RAW.get(s.get("name", s["type"])) == 0: bad.append(f"{s.get('name')}: 원본 0건")
        except Exception as e:
            bad.append(f"{s.get('name')}: {type(e).__name__}: {e}")
    assert not bad, "가짜 피드를 못 읽은 출처:\n  " + "\n  ".join(bad)


def t_main():
    C.SEEN_TEXT.clear(); C.RAW.clear()
    before = len(json.load(open(C.OUT, encoding="utf-8")))
    C.main()
    items = json.load(open(C.OUT, encoding="utf-8"))
    meta = json.load(open(os.path.join(C.DATA, "meta.json"), encoding="utf-8"))
    st = meta["sources"]
    bad = [x for x in st if x.get("ok") is False]
    assert not bad, f"실패한 출처: {bad}"
    assert any(x.get("new") for x in st), "새 소식이 하나도 없음"
    assert len(items) >= min(before, C.KEEP) * 0.5, f"소식이 크게 줄었다 {before} → {len(items)}"
    new = [x for x in items if x.get("addedAt", "")[:16] == meta["updated"][:16]]
    assert new and all(x.get("title") and x.get("url") for x in new)
    assert any(x.get("region") == "KR" for x in new), "한국 소식이 하나도 안 남음"
    assert any("[번역]" in (x.get("title_ko") or "") for x in new), "번역이 안 붙음"
    for f in ("feed.xml", "calendar.ics", "calendar-events.ics", "calendar-tickets.ics", "xbuzz.json"):
        assert os.path.getsize(os.path.join(C.DATA, f)) > 0, f
    import xml.etree.ElementTree as ET
    ET.parse(os.path.join(C.DATA, "feed.xml"))


def t_guard():
    global FAIL_ALL
    path = C.OUT
    snap = open(path, "rb").read()
    FAIL_ALL = True
    try:
        try:
            C.main(); raise AssertionError("다 실패했는데 main() 이 끝까지 돌았다")
        except SystemExit as e:
            assert e.code == 3, e.code
    finally:
        FAIL_ALL = False
    assert open(path, "rb").read() == snap, "고장 때 items.json 이 바뀌었다"
    info = json.load(open(C.BROKEN_FILE, encoding="utf-8"))
    assert info["tried"] >= 6 and len(info["bad"]) == info["tried"]


def fake_gh(log, issues):
    def call(method, path, body=None):
        log.append((method, path, body))
        if method == "GET": return [dict(i) for i in issues]
        if method == "POST" and path == "/issues":
            issues.append({"number": 7, "title": body["title"], "body": body["body"]}); return {"number": 7}
        return {}
    return call


def t_alerts():
    log, issues = [], []
    C.alert_run([{"n": "A", "ok": False, "f": 3, "e": "x"}, {"n": "B", "ok": True, "zr": 0}], fake_gh(log, issues))
    assert issues and issues[0]["title"] == C.ALERT_TITLE and "bad:A" in issues[0]["body"]
    log2 = []
    C.alert_run([{"n": "A", "ok": True, "zr": 0}], fake_gh(log2, issues))
    assert ("PATCH", "/issues/7", {"state": "closed"}) in log2
    log3, iss3 = [], []
    C.broken_run(fake_gh(log3, iss3), {"at": "t", "tried": 10, "bad": [{"n": "A", "e": "name 'UA' is not defined"}]}, "https://run")
    C.broken_run(fake_gh(log3, iss3), None, "https://run")  # 이미 열려 있으면 댓글
    assert len(iss3) == 1 and iss3[0]["title"] == C.BROKEN_TITLE and any(p.endswith("/comments") for _, p, _ in log3)
    log4 = []
    C.broken_close(fake_gh(log4, iss3))
    assert ("PATCH", "/issues/7", {"state": "closed"}) in log4


def t_gloss():
    assert "약사의 혼잣말" in C.gloss_pre("「薬屋のひとりごと」原画展")
    it = {"title": "「薬屋のひとりごと」原画展", "title_ko": "「약국의 독백」 원화전", "summary": "", "summary_ko": ""}
    assert C.gloss_miss(it)
    C.translate_items([it])
    assert "약사의 혼잣말" in it["title_ko"] and it.get("tg") == C.GLOSS_VER and not C.gloss_miss(it)


def t_weekly():
    w = C.load_json(C.WEEKLY, {})
    w["week"] = "2000-01-03"; C.save_json(C.WEEKLY, w)
    C.weekly_draft(C.datetime.now(C.JST))
    w = json.load(open(C.WEEKLY, encoding="utf-8"))
    assert w.get("auto") and w["week"] != "2000-01-03"
    C.write_feed(C.datetime.now(C.JST))


for n, f in [("출처마다 가짜 피드 읽기", t_sources), ("main() 한 바퀴", t_main), ("고장 방지(절반 넘게 실패)", t_guard),
             ("출처·고장 알림 이슈", t_alerts), ("번역 용어집", t_gloss), ("주간 요약 자동 초안", t_weekly)]:
    check(n, f)
shutil.rmtree(TMP, ignore_errors=True)
fails = [n for n, e in results if e]
print(f"→ {len(results) - len(fails)}/{len(results)} 통과" + (f", 실패: {', '.join(fails)}" if fails else ""))
sys.exit(1 if fails else 0)
