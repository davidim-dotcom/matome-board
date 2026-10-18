#!/usr/bin/env python3
"""마토메 보드 수집기 — GitHub 공개 보드용

GitHub Actions가 정해진 시간마다 실행해서 data/ 폴더의 JSON을 갱신한다.
  python3 collector.py           소식 수집 → data/items.json, data/meta.json
  python3 collector.py --anime   방영 목록·썸네일 → data/anime.json, data/thumbs.json, data/thumbs/*.jpg
직접 추가할 소식은 data/manual.json, 공개 보드에서 빼고 싶은 소식은 data/blocklist.json에 적는다.

(아래는 원래 설명)

  - site     : 사이트 주소만 적으면 RSS를 스스로 찾아서 읽음
  - rss      : 공식 사이트 뉴스 RSS, 또는 직접 띄운 RSSHub 주소(X·인스타 경로)
  - youtube  : 유튜브 채널 RSS (API 키 불필요)
  - holodex  : 버튜버 방송 예정 (환경변수 HOLODEX_API_KEY 필요)

실행: python3 collector.py          →  items.json(소식)
      python3 collector.py --anime  →  anime.json(이번 시즌 방영 목록) + thumbs.json(썸네일), ANNICT_TOKEN 필요
      둘 다 보드의 ‘규칙·가져오기’에서 불러오기
유행 감지: 실행할 때마다 뉴스 제목의 『』「」 작품명을 세어 trends.json에 기록하고,
          자주 나온 이름을 다음 실행부터 작품 태그로 자동 사용한다.
표준 라이브러리만 사용. GitHub Actions나 cron으로 하루 몇 번 돌리면 된다.
"""
import json, os, re, sys, html
import urllib.request, urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta

JST = timezone(timedelta(hours=9))
ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(DATA, "items.json")
KEEP = 600  # items.json에 남길 최대 건수

# ── 여기만 고쳐서 쓰면 된다 ─────────────────────────────────────
SOURCES = [
    # 넓게 훑는 뉴스 소스: 유행 감지의 재료이자, 공연·이벤트 공지만 걸러서 보드로 보냄
    {"type": "site", "name": "コミックナタリー", "url": "https://natalie.mu/comic"},
    {"type": "site", "name": "音楽ナタリー", "url": "https://natalie.mu/music"},
    {"type": "site", "name": "アニメ!アニメ!", "url": "https://animeanime.jp/"},
    {"type": "site", "name": "アニメイトタイムズ", "url": "https://www.animatetimes.com/"},
    {"type": "site", "name": "アニメハック", "url": "https://anime.eiga.com/"},
    {"type": "site", "name": "電撃オンライン", "url": "https://dengekionline.com/"},
    {"type": "site", "name": "4Gamer", "url": "https://www.4gamer.net/"},
    {"type": "site", "name": "MoguLive", "url": "https://www.moguravr.com/"},
    # 콜라보 카페·팝업
    {"type": "site", "name": "コラボカフェ", "url": "https://collabo-cafe.com/"},
    # 만화·전시
    {"type": "site", "name": "原画展.info", "url": "https://gengaten.info/"},
    # 공식 행사·동인 즉매회
    {"type": "site", "name": "コミックマーケット", "url": "https://www.comiket.co.jp/"},
    {"type": "site", "name": "同人イベントNAVI", "url": "https://shimeken.com/"},
    {"type": "site", "name": "スイーツパラダイス", "url": "https://www.sweets-paradise.jp/collaboration/"},
    # 버튜버 방송 예정 (HOLODEX_API_KEY 필요, holodex.net 계정 설정에서 무료 발급)
    {"type": "holodex", "name": "Hololive", "org": "Hololive", "hours": 48},
    {"type": "holodex", "name": "Nijisanji", "org": "Nijisanji", "hours": 48},
    {"type": "holodex", "name": "VSPO", "org": "VSpo", "hours": 48},
    # 직접 추가 예시
    # {"type": "rss", "name": "@official_x", "url": "http://localhost:1200/twitter/user/official_x"},  # RSSHub
    # {"type": "youtube", "name": "채널명", "channel_id": "UCxxxxxxxx", "works": ["이름"]},
]
# 작품 태그 씨앗: 2026년 10월 기준 화제작. 유행 감지 결과가 여기에 자동으로 더해진다.
WORKS_SEED = [
    "薬屋のひとりごと", "アオのハコ", "らんま1/2", "転生したらスライムだった件", "攻殻機動隊", "黄泉のツガイ",
    "アオアシ", "PSYREN", "幻想水滸伝", "ケロロ軍曹", "東京リベンジャーズ", "ラブライブ", "Liella!", "BanG Dream!",
    "Roselia", "ドラゴンクエスト", "鳴潮", "第五人格", "ウマ娘", "アイドルマスター", "原神", "崩壊：スターレイル",
    "ホロライブ", "hololive", "にじさんじ", "ぶいすぽっ", "初音ミク",
]
TREND_DAYS = 14      # 최근 며칠치 언급을 셀지
TREND_MIN = 3        # 이만큼 이상 다른 기사에 나와야 유행으로 본다
TREND_TOP = 30
# 이 단어가 하나도 없으면 버린다(빈 리스트면 전부 통과). 공지 이외 잡담을 1차로 거른다.
MUST_HAVE_ANY = ["即売会", "オンリー", "コミケ", "コミックマーケット", "COMITIA", "単行本", "新連載", "完結", "アニメ化", "原画展", "展覧会", "ライブ", "LIVE", "公演", "イベント", "チケット", "先行", "抽選", "コラボ", "開催", "ツアー", "フェス", "POP UP", "ポップアップ", "カフェ", "ストア"]
# ────────────────────────────────────────────────────────────────

TICKET_DOMAINS = ["eplus.jp", "l-tike.com", "pia.jp", "ticket.rakuten.co.jp", "livepocket.jp",
                  "tiget.net", "zaiko.io", "teket.jp", "asobistore.jp", "passmarket.yahoo.co.jp", "peatix.com"]
CAT_RULES = [
    ("doujin", r"同人誌即売会|同人イベント|オンリーイベント|オンリー即売会|プチオンリー|WEBオンリー|コミックマーケット|コミケ|COMITIA|コミティア|COMIC CITY|コミックシティ|即売会"),
    ("official", r"ジャンプフェスタ|AnimeJapan|東京ゲームショウ|ワンダーフェスティバル|コミコン|ニコニコ超会議|超会議|ファンフェスタ|ファン感謝祭|公式イベント"),
    ("live", r"ライブ|LIVE|Live|公演|コンサート|ツアー|フェス"),
    ("exhibit", r"原画展|複製原画|展覧会|展示会|EXHIBITION|Exhibition|EXPO|美術館|展(?=[\s　」』〜～]|$| in)"),
    ("popup", r"ポップアップ|ポップストア|POP ?UP|期間限定ショップ|オンリーショップ|ストア in"),
    ("collab", r"コラボ"),
    ("event", r"イベント|展示|展覧会|ポップアップ|POP ?UP|フェア|上映会|ファンミ"),
    ("campaign", r"キャンペーン"),
    ("manga", r"単行本|最新刊|新刊|コミックス|新連載|連載開始|連載再開|最終回|完結|マンガ大賞|漫画賞|アニメ化決定|第\d+巻"),
    ("goods", r"グッズ|一番くじ|予約受付"),
    ("stream", r"配信|生放送|プレミア公開"),
]
OPEN_WORDS = r"受付|発売|先行|抽選|販売"
END_WORDS = r"締切|〆切|しめきり|まで"
UA = {"User-Agent": "matome-board-collector/0.1 (personal use)"}


def fetch(url, headers=None):
    req = urllib.request.Request(url, headers={**UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read()


def clean(text):
    text = re.sub(r"<br\s*/?>", "\n", text or "", flags=re.I)
    return html.unescape(re.sub(r"<[^>]+>", " ", text)).strip()


def urls_in(text):
    return re.findall(r"https?://[^\s\"'<>）)」]+", text or "")


def ticket_url(urls):
    for u in urls:
        host = urllib.parse.urlparse(u).hostname or ""
        if any(d in host for d in TICKET_DOMAINS):
            return u
    return ""


DATE_RE = re.compile(
    r"(?:(?P<y>20\d\d)\s*[年/.\-]\s*)?(?P<m>\d{1,2})\s*[月/]\s*(?P<d>\d{1,2})\s*日?"
    r"(?:\s*[（(][^)）]{1,3}[)）])?(?:\s*(?P<h>\d{1,2})\s*[:：時]\s*(?P<mi>\d{2})?)?")


def find_dates(text, ref):
    """본문 속 날짜를 (iso, 앞뒤 문맥) 목록으로."""
    out = []
    for m in DATE_RE.finditer(text):
        mo, d = int(m["m"]), int(m["d"])
        if not (1 <= mo <= 12 and 1 <= d <= 31):
            continue
        y = int(m["y"]) if m["y"] else ref.year
        try:
            dt = datetime(y, mo, d, int(m["h"] or 0) % 24, int(m["mi"] or 0), tzinfo=JST)
        except ValueError:
            continue
        if not m["y"] and dt < ref - timedelta(days=60):  # 연도 없으면 내년으로
            dt = dt.replace(year=y + 1)
        ctx = text[max(0, m.start() - 14): m.end() + 10]
        out.append((dt.strftime("%Y-%m-%dT%H:%M"), ctx))
    return out


def classify(text, default="other"):
    for cat, pat in CAT_RULES:
        if re.search(pat, text):
            return cat
    return default


def build(title, body, link, src, ref, default_cat="other"):
    text = f"{title}\n{body}"
    if MUST_HAVE_ANY and default_cat != "stream" and not any(w in text for w in MUST_HAVE_ANY):
        return None
    event = opening = deadline = end = ""
    rng = re.search(DATE_RE.pattern + r"\s*[〜～~\-－]\s*" + DATE_RE.pattern.replace("?P<", "?P<e_"), text)
    if rng:  # 「10月30日(金)〜11月24日(火)」 같은 기간
        ds = find_dates(rng.group(0), ref)
        if len(ds) >= 2 and ds[1][0] > ds[0][0]:
            event, end = ds[0][0], ds[1][0]
    for iso, ctx in find_dates(text, ref):
        if iso in (event, end):
            continue
        if not deadline and re.search(END_WORDS, ctx):
            deadline = iso
        elif not opening and re.search(OPEN_WORDS, ctx):
            opening = iso
        elif not event:
            event = iso
    works = list(src.get("works", []))
    for w in WATCH:
        if w.lower() in text.lower() and w not in works:
            works.append(w)
    return {
        "title": title[:200], "category": classify(text, default_cat), "source": src.get("name", ""),
        "platform": src["type"], "works": works[:5], "eventDate": event, "endDate": end, "ticketOpen": opening,
        "deadline": deadline, "venue": "", "ticketUrl": ticket_url(urls_in(body) + [link]),
        "url": link, "summary": re.sub(r"\s+", " ", body)[:140],
    }


def parse_feed(xml_bytes):
    root = ET.fromstring(xml_bytes)
    ns = {"a": "http://www.w3.org/2005/Atom", "media": "http://search.yahoo.com/mrss/"}
    entries = []
    for it in root.iter("item"):  # RSS 2.0
        entries.append((it.findtext("title") or "", it.findtext("description") or "", it.findtext("link") or ""))
    for e in root.findall("a:entry", ns):  # Atom(유튜브 포함)
        link = e.find("a:link", ns)
        desc = e.findtext("media:group/media:description", default="", namespaces=ns) or e.findtext("a:summary", default="", namespaces=ns) or e.findtext("a:content", default="", namespaces=ns)
        entries.append((e.findtext("a:title", default="", namespaces=ns), desc, link.get("href") if link is not None else ""))
    return entries


CACHE = os.path.join(DATA, ".feedcache.json")
_cache = json.load(open(CACHE, encoding="utf-8")) if os.path.exists(CACHE) else {}


def discover(site):
    """사이트 첫 화면의 <link rel=alternate>에서 RSS/Atom 주소를 찾는다. 결과는 캐시."""
    if site in _cache:
        return _cache[site]
    page = fetch(site).decode("utf-8", "replace")
    for tag in re.findall(r"<link[^>]+>", page, flags=re.I):
        if re.search(r"rel=[\"']?alternate", tag, re.I) and re.search(r"(rss|atom)\+xml", tag, re.I):
            m = re.search(r"href=[\"']([^\"']+)", tag, re.I)
            if m:
                _cache[site] = urllib.parse.urljoin(site, html.unescape(m.group(1)))
                return _cache[site]
    for guess in ("feed", "rss", "index.rdf", "rss/index.xml", "feed/"):  # 흔한 주소 추측
        u = urllib.parse.urljoin(site if site.endswith("/") else site + "/", guess)
        try:
            parse_feed(fetch(u)); _cache[site] = u; return u
        except Exception:
            pass
    raise ValueError("RSS를 찾지 못함 (rss 종류로 주소를 직접 적어 주세요)")


SEEN_TEXT = []  # 유행 감지용: (제목+본문)


def collect(src, ref):
    t = src["type"]
    if t in ("rss", "youtube", "site"):
        url = {"rss": lambda: src["url"], "site": lambda: discover(src["url"]),
               "youtube": lambda: f"https://www.youtube.com/feeds/videos.xml?channel_id={src['channel_id']}"}[t]()
        cat = "stream" if t == "youtube" else "other"
        out = []
        for ti, de, li in parse_feed(fetch(url)):
            ti, de = clean(ti), clean(de)
            SEEN_TEXT.append(f"{ti}\n{de[:300]}")
            x = build(ti, de, li, src, ref, cat)
            if x: out.append(x)
        return out
    if t == "holodex":
        key = os.environ.get("HOLODEX_API_KEY")
        if not key:
            print("  HOLODEX_API_KEY가 없어 건너뜀", file=sys.stderr); return []
        q = urllib.parse.urlencode({"org": src["org"], "status": "upcoming", "type": "stream",
                                    "max_upcoming_hours": src.get("hours", 72), "limit": 50})
        data = json.loads(fetch(f"https://holodex.net/api/v2/live?{q}", {"X-APIKEY": key}))
        out = []
        for v in data:
            start = v.get("start_scheduled", "")
            ev = datetime.fromisoformat(start.replace("Z", "+00:00")).astimezone(JST).strftime("%Y-%m-%dT%H:%M") if start else ""
            ch = (v.get("channel") or {}).get("name", "")
            out.append({"title": v.get("title", "")[:200], "category": "stream", "source": ch, "platform": "youtube",
                        "works": [ch] if ch else [], "eventDate": ev, "ticketOpen": "", "deadline": "", "venue": "",
                        "ticketUrl": "", "url": f"https://www.youtube.com/watch?v={v.get('id','')}", "summary": ""})
        return out
    raise ValueError(f"알 수 없는 소스 종류: {t}")


TRENDS = os.path.join(DATA, "trends.json")
NAME_RE = re.compile(r"[『「]([^』」\n]{2,30})[』」]")
STOP = re.compile(r"^(第?\d+[話期弾回]|PV|MV|特報|本予告|公式)|^[\d\s:：.、/]+$")


def base_title(n):
    """『薬屋のひとりごと 第3期』→『薬屋のひとりごと』처럼 시즌 표기를 떼어 같은 작품으로 묶는다."""
    n = re.sub(r"[\s　]*(第\d+期|Season\s*\d+|シーズン\d+|\d+(st|nd|rd|th)\s*Season|劇場版|映画)\s*", " ", n, flags=re.I)
    return re.sub(r"\s+", " ", n).strip(" 　-~〜")


def load_trends():
    if not os.path.exists(TRENDS):
        return {"history": {}, "top": []}
    try: return json.load(open(TRENDS, encoding="utf-8"))
    except Exception: return {"history": {}, "top": []}


def update_trends(tr, ref):
    """오늘 본 기사에서 작품명을 세고, 최근 TREND_DAYS일 합계로 순위를 낸다."""
    today = ref.strftime("%Y-%m-%d")
    counts = {}
    for text in SEEN_TEXT:
        for n in {base_title(m) for m in NAME_RE.findall(text)}:
            if len(n) >= 2 and not STOP.search(n):
                counts[n] = counts.get(n, 0) + 1
    day = tr["history"].setdefault(today, {})
    for n, c in counts.items():
        day[n] = max(day.get(n, 0), c)  # 같은 날 여러 번 돌려도 중복 집계하지 않음
    cutoff = (ref - timedelta(days=TREND_DAYS)).strftime("%Y-%m-%d")
    tr["history"] = {d: v for d, v in tr["history"].items() if d >= cutoff}
    total = {}
    for v in tr["history"].values():
        for n, c in v.items():
            total[n] = total.get(n, 0) + c
    old_top = set(tr.get("top", []))
    tr["top"] = [n for n, c in sorted(total.items(), key=lambda x: -x[1]) if c >= TREND_MIN][:TREND_TOP]
    tr["updated"] = ref.isoformat()
    json.dump(tr, open(TRENDS, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    rising = [n for n in tr["top"] if n not in old_top]
    if rising:
        print("새로 뜨는 작품:", ", ".join(rising[:10]))


_tr = load_trends()
WATCH = list(dict.fromkeys(WORKS_SEED + _tr.get("top", [])))



def load_json(path, default):
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception:
        return default


def save_json(path, data, indent=1):
    tmp = path + ".tmp"
    json.dump(data, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=indent)
    os.replace(tmp, path)


def item_end(it):
    v = it.get("endDate") or it.get("eventDate") or ""
    try:
        return datetime.fromisoformat(v if re.search(r"[+-]\d\d:\d\d$|Z$", v) else v + "+09:00")
    except Exception:
        return None


def blocked(it, block):
    t = (it.get("title") or "").lower()
    return (it.get("url") and it["url"] in block.get("urls", [])) or it.get("id") in block.get("ids", []) \
        or any(k.lower() in t for k in block.get("titles", []) if k)


def main():
    ref = datetime.now(JST)
    old = load_json(OUT, [])
    block = load_json(os.path.join(DATA, "blocklist.json"), {})
    seen = {(o.get("url"), o.get("title")) for o in old}
    new = []
    for src in SOURCES:
        try:
            got = collect(src, ref)
            fresh = [g for g in got if (g["url"], g["title"]) not in seen and not blocked(g, block)]
            seen.update((g["url"], g["title"]) for g in fresh)
            new += fresh
            print(f"{src.get('name', src['type'])}: {len(got)}건 중 새 소식 {len(fresh)}건")
        except Exception as e:
            print(f"{src.get('name', src['type'])}: 실패 ({e})", file=sys.stderr)
    for n in new:
        n["addedAt"] = ref.isoformat()
    update_trends(_tr, ref)
    json.dump(_cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)
    # 정리: 끝난 지 30일 넘은 것, 날짜 없이 45일 지난 것, 차단 목록에 걸린 것은 뺀다
    keep = []
    for it in new + old:
        if blocked(it, block):
            continue
        end = item_end(it)
        if end and end < ref - timedelta(days=30):
            continue
        if not end:
            try:
                if datetime.fromisoformat(it.get("addedAt", ref.isoformat())) < ref - timedelta(days=45):
                    continue
            except Exception:
                pass
        keep.append(it)
    items = keep[:KEEP]
    save_json(OUT, items)
    meta = load_json(os.path.join(DATA, "meta.json"), {})
    meta.update({"updated": ref.isoformat(), "trends": _tr.get("top", [])[:20], "count": len(items)})
    save_json(os.path.join(DATA, "meta.json"), meta)
    print(f"→ data/items.json: 총 {len(items)}건 (이번에 {len(new)}건 추가)")


def og_image(site):
    """작품 공식 사이트(소개 페이지) 첫 화면의 og:image = 키 비주얼."""
    if not site:
        return ""
    try:
        page = fetch(site).decode("utf-8", "replace")
    except Exception:
        return ""
    for prop in ("og:image", "twitter:image"):
        for tag in re.findall(r"<meta[^>]+>", page, flags=re.I):
            if re.search(r"(property|name)=[\"']" + re.escape(prop) + r"[\"']", tag, re.I):
                m = re.search(r"content=[\"']([^\"']+)", tag, re.I)
                if m:
                    return urllib.parse.urljoin(site, html.unescape(m.group(1)))
    return ""


def tkey(t):
    return re.sub(r"[\s\u3000]", "", t or "").lower()


def save_thumb(title, url, thumbs):
    """이미지를 받아 208x117 JPEG로 줄여 data/thumbs/에 저장. 이미 있으면 건너뜀."""
    import hashlib, io
    name = hashlib.sha1(tkey(title).encode()).hexdigest()[:16] + ".jpg"
    path = os.path.join(DATA, "thumbs", name)
    if os.path.exists(path):
        thumbs[title] = "data/thumbs/" + name
        return True
    try:
        from PIL import Image
        raw = fetch(url)
        im = Image.open(io.BytesIO(raw)).convert("RGB")
        w, h = 208, 117
        r = max(w / im.width, h / im.height)
        im = im.resize((max(w, round(im.width * r)), max(h, round(im.height * r))))
        l, t = (im.width - w) // 2, (im.height - h) // 2
        im.crop((l, t, l + w, t + h)).save(path, "JPEG", quality=80)
        thumbs[title] = "data/thumbs/" + name
        return True
    except Exception as e:
        print(f"  썸네일 실패: {title} ({e})", file=sys.stderr)
        return False


def export_anime(ref):
    """방영 목록 갱신 + 썸네일.
    - ANNICT_TOKEN이 있으면 이번 시즌 작품 목록·공식 사이트·공식 X를 받아 합친다(요일·시각은 기존 값 유지).
    - 썸네일은 ① 공식 사이트 og:image ② Annict 이미지 ③ 공식 PV(YouTube) 대표 이미지 순서로 찾는다."""
    path = os.path.join(DATA, "anime.json")
    doc = load_json(path, {"season": "", "name": "", "src": "", "list": []})
    m = ref.month
    season = f"{ref.year}-" + ("winter" if m <= 3 else "spring" if m <= 6 else "summer" if m <= 9 else "autumn")
    names = {"winter": "겨울", "spring": "봄", "summer": "여름", "autumn": "가을"}
    if doc.get("season") != season:  # 시즌이 바뀌면 새 목록으로
        doc = {"season": season, "name": f"{ref.year}년 {names[season.split('-')[1]]} 애니", "src": "Annict", "list": []}
    by = {tkey(a["t"]): a for a in doc["list"]}
    extra = {}  # title -> annict image
    token = os.environ.get("ANNICT_TOKEN")
    if token:
        page = 1
        while page <= 6:
            q = urllib.parse.urlencode({"filter_season": season, "sort_watchers_count": "desc", "per_page": 50,
                                        "page": page, "access_token": token})
            try:
                data = json.loads(fetch(f"https://api.annict.com/v1/works?{q}"))
            except Exception as e:
                print(f"Annict 실패: {e}", file=sys.stderr); break
            for w in data.get("works", []):
                t = w.get("title", "")
                a = by.get(tkey(t)) or {"t": t, "d": 7 if w.get("media") == "web" else 8, "tm": "", "st": "", "s": "", "r": None, "pv": ""}
                a["site"] = w.get("official_site_url") or a.get("site", "")
                a["x"] = w.get("twitter_username") or a.get("x", "")
                a["w"] = w.get("watchers_count")
                by[tkey(t)] = a
                extra[t] = (w.get("images") or {}).get("recommended_url") or ""
            if not data.get("next_page"):
                break
            page += 1
    else:
        print("ANNICT_TOKEN 없음: 기존 방영 목록으로 썸네일만 갱신", file=sys.stderr)
    doc["list"] = list(by.values())
    save_json(path, doc)
    thumbs = load_json(os.path.join(DATA, "thumbs.json"), {})
    got = 0
    for a in doc["list"][:200]:
        t = a["t"]
        if t in thumbs and os.path.exists(os.path.join(ROOT, thumbs[t])):
            continue
        cands = [og_image(a.get("site", "")), extra.get(t, "")]
        pv = re.search(r"[?&]v=([\w-]{11})", a.get("pv", "") or "")
        if pv:
            cands.append(f"https://i.ytimg.com/vi/{pv.group(1)}/hqdefault.jpg")
        for u in cands:
            if u and save_thumb(t, u, thumbs):
                got += 1
                break
    save_json(os.path.join(DATA, "thumbs.json"), thumbs)
    print(f"→ data/anime.json {len(doc['list'])}편, 썸네일 새로 {got}개 (전체 {len(thumbs)}개)")


if __name__ == "__main__":
    os.makedirs(os.path.join(DATA, "thumbs"), exist_ok=True)
    if "--anime" in sys.argv:
        export_anime(datetime.now(JST))
    else:
        main()
