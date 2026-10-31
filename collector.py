#!/usr/bin/env python3
"""마토메 보드 수집기 — GitHub 공개 보드용

GitHub Actions가 정해진 시간마다 실행해서 data/ 폴더의 JSON을 갱신한다.
  python3 collector.py           소식 수집 → data/items.json, data/meta.json(출처 상태 포함), data/feed.xml(RSS), data/calendar*.ics(구독용 달력), data/xbuzz.json(X 화제)
  python3 collector.py --anime   방영 목록·썸네일 → data/anime.json, data/thumbs.json, data/thumbs/*.jpg
  python3 collector.py --comics  디시 만화갤러리 개념글의 연재작 색인 → data/comics.json
  python3 collector.py --alert-broken   소식 수집 단계가 실패했을 때(출처 절반 넘게 실패 → 종료 코드 3, 또는 오류) 바로 이슈(워크플로 전용)
  python3 collector.py --alert          출처가 3회 연속 실패하거나 2일 연속 빈 피드면 GitHub 이슈(워크플로 전용, GITHUB_TOKEN)
  python3 collector.py --weekly-draft   지금 주간 요약의 7일이 끝났으면 이번 주(월요일 시작) 자동 초안 → data/weekly.json
  python3 collector.py --check   소스별로 가져오기만 해 보고 OK/FAIL 출력(파일은 쓰지 않음)
  python3 collector.py --translate-test   일본어 한 문장을 번역해 보고 결과만 출력(번역 경로 점검)
직접 추가할 소식은 data/manual.json, 공개 보드에서 빼고 싶은 소식은 data/blocklist.json에 적는다.

(아래는 원래 설명)

  - site     : 사이트 주소만 적으면 RSS를 스스로 찾아서 읽음
  - rss      : 공식 사이트 뉴스 RSS, 또는 직접 띄운 RSSHub 주소(X·인스타 경로). Google 뉴스 사이트맵도 읽음.
               "headers": {...} 를 주면 요청에 함께 보냄(쿠키 등)
  - youtube  : 유튜브 채널 RSS (API 키 불필요)
  - wpjson   : WordPress REST API 글 목록(/wp-json/wp/v2/posts?...). RSS가 비어 있는 WP 사이트용.
               "link_prefix" 를 주면 그 주소로 시작하는 글만 남김(번역본 제외)
  - json     : 임의의 JSON API. "items"(목록 키 경로) "title" "body" "date" 필드명과 "link" 틀("https://…/{id}")을 적는다
  - ldjson   : 페이지의 schema.org Event(JSON-LD) 목록. url 의 {ym} 에 YYYYMM 이 들어가며 "months" 달치를 읽는다
  공통 옵션: "works": [...] 모든 소식에 붙일 작품 태그, "extra_words": [...] MUST_HAVE_ANY 에 더할 통과 단어
썸네일: 피드의 enclosure/media:*/본문 <img>, WP 대표 이미지, JSON 의 image 키에서 그림 주소를 "image" 에 담는다.
기사 보강: 소식마다 기사 페이지를 한 번 열어(실행당 ENRICH_MAX 건) 빠진 og:image 와 e+ 등 티켓 링크를 채우고 "scanned" 로 표시.
        그림 파일은 저장하지 않고 주소만 둔다.
  - holodex  : 버튜버 방송 예정 (환경변수 HOLODEX_API_KEY 필요)

실행: python3 collector.py          →  items.json(소식)
      python3 collector.py --anime  →  anime.json(이번 시즌 방영 목록) + thumbs.json(썸네일), ANNICT_TOKEN 필요
      둘 다 보드의 ‘규칙·가져오기’에서 불러오기
유행 감지: 실행할 때마다 뉴스 제목의 『』「」 작품명을 세어 trends.json에 기록하고,
          자주 나온 이름을 다음 실행부터 작품 태그로 자동 사용한다.
표준 라이브러리만 사용. GitHub Actions나 cron으로 하루 몇 번 돌리면 된다.
"""
import json, os, re, sys, html, time, tempfile, unicodedata
import urllib.request, urllib.parse, urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime

JST = timezone(timedelta(hours=9))
ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(DATA, "items.json")
KEEP = 900  # items.json에 남길 최대 건수(앞으로 일정이 있는 소식을 먼저 채운다, keep_items)

# ── 여기만 고쳐서 쓰면 된다 ─────────────────────────────────────
VTUBER_WORDS = ["グッズ", "フェア", "物販", "受注", "周年", "お披露目", "展"]  # 버튜버 전용 소스에서 추가로 통과시키는 단어
FRESH_DAYS = 60  # 게시일이 이보다 오래된 글은 피드에 남아 있어도 무시(오래된 글이 쌓인 피드 대비)
SOURCES = [
    # 넓게 훑는 뉴스 소스: 유행 감지의 재료이자, 공연·이벤트 공지만 걸러서 보드로 보냄
    # natalie.mu는 GitHub Actions(해외 IP)의 모든 요청을 405로 거부해 수집 불가(2026-10 확인). 국내 PC에서 돌릴 때만 켤 것.
    # {"type": "rss", "name": "コミックナタリー", "url": "https://natalie.mu/comic/feed/news"},
    # {"type": "rss", "name": "音楽ナタリー", "url": "https://natalie.mu/music/feed/news"},
    {"type": "site", "name": "アニメ!アニメ!", "url": "https://animeanime.jp/"},
    # アニメイトタイムズ: RSS 없음(/rss/*.xml 은 빈 응답). 2026-10 확인.
    # {"type": "site", "name": "アニメイトタイムズ", "url": "https://www.animatetimes.com/"},
    {"type": "rss", "name": "アニメハック", "url": "https://anime.eiga.com/feed/news/rss.xml"},
    # アニメハック 이벤트 캘린더: 페이지의 schema.org Event(JSON-LD)에서 공연·이벤트·전시를 날짜·장소째 가져온다(이번 달부터 3달).
    # e+ 등 티켓 링크는 기사 보강(enrich)이 상세 페이지에서 찾는다. e+ 자체는 Actions 에서 503 으로 막혀 소스로 못 쓴다(2026-10).
    {"type": "ldjson", "name": "アニメハック イベント", "url": "https://anime.eiga.com/event/cal/{ym}/", "months": 3},
    # 電撃オンライン: RSS가 없어 Google 뉴스 사이트맵(제목+링크만)을 피드처럼 읽음
    # 게임 뉴스(game=True): 게임 안 이벤트·가챠·참전·업데이트 소식은 GAME_NOISE_RE 로 거른다(실제 행사·매장 콜라보·굿즈 단어가 있으면 남김)
    {"type": "rss", "name": "電撃オンライン", "url": "https://dengekionline.com/newsSitemap.xml", "game": True},
    {"type": "rss", "name": "4Gamer", "url": "https://www.4gamer.net/rss/index.xml", "game": True},
    {"type": "site", "name": "インサイド", "url": "https://www.inside-games.jp/", "game": True},
    {"type": "rss", "name": "GAME Watch", "url": "https://game.watch.impress.co.jp/data/rss/1.0/gmw/feed.rdf", "game": True},
    # ファミ通.com: 첫 화면에 RSS 링크가 없고 흔한 주소도 없음. Gamer(gamer.ne.jp): Actions 요청을 403 으로 거부. 둘 다 2026-10 확인.
    {"type": "site", "name": "MoguLive", "url": "https://www.moguravr.com/"},
    # 콜라보 카페·팝업. /feed/ 가 빈 응답(Content-Length 0)을 돌려줘서 WordPress REST API로 읽음
    {"type": "wpjson", "name": "コラボカフェ", "url": "https://collabo-cafe.com/wp-json/wp/v2/events?per_page=40&orderby=date&order=desc&lang=ja&_embed=wp:featuredmedia&_fields=title,excerpt,link,date_gmt,_links,_embedded",
     "link_prefix": "https://collabo-cafe.com/events/"},  # 콜라보 글은 'event' 글 타입. 번역본(/en/, /zh-hant/ …)은 링크 접두사로 걸러낸다
    # 만화·전시
    {"type": "site", "name": "原画展.info", "url": "https://gengaten.info/"},
    # 공식 행사·동인 즉매회
    # コミックマーケット, 同人イベントNAVI(shimeken.com): RSS 없음. 2026-10 확인. 소식은 data/manual.json에 직접 추가.
    # {"type": "site", "name": "コミックマーケット", "url": "https://www.comiket.co.jp/"},
    # {"type": "site", "name": "同人イベントNAVI", "url": "https://shimeken.com/"},
    {"type": "site", "name": "スイーツパラダイス", "url": "https://www.sweets-paradise.jp/collaboration/"},
    # 버튜버 이벤트·라이브·상품전. 전용 소스라 그룹명을 작품 태그로 붙이고, 굿즈·전시 단어도 통과시킨다
    {"type": "rss", "name": "PANORA", "url": "https://panora.tokyo/feed", "extra_words": VTUBER_WORDS},
    {"type": "rss", "name": "KAI-YOU", "url": "https://kai-you.net/contents/feed.rss"},
    # hololivepro.com: 2026-10 초 RSS(/news/feed/)가 404 여서 뉴스 목록 HTML 만 읽었는데, 10-30 에 RSS 가 다시 열리고 HTML 링크는 절대 주소로 바뀌어 HTML 이 0건이 됐다.
    # 그래서 RSS 를 먼저 읽고, 실패하거나 비면 fallback(HTML, 링크는 상대·절대 둘 다)을 읽는다.
    {"type": "rss", "name": "ホロライブ公式", "url": "https://hololivepro.com/news/feed/", "works": ["ホロライブ"], "extra_words": VTUBER_WORDS,
     "fallback": {"type": "html", "url": "https://hololivepro.com/news/",
                  "item": r'<a href="(?P<link>(?:https://hololivepro\.com)?/news/[^"]+)" class="news_li">.*?<img src="(?P<image>[^"]*)".*?<p class="date">(?P<date>[\d.]+)</p>\s*<h2 class="tit">(?P<title>.*?)</h2>\s*<p class="txt">(?P<summary>.*?)</p>'}},
    {"type": "rss", "name": "ぶいすぽっ！公式", "url": "https://vspo.jp/news/feed", "works": ["ぶいすぽっ"], "extra_words": VTUBER_WORDS},
    # にじさんじ 공식: RSS가 없어 사이트가 쓰는 JSON API를 읽음(제목·게시일만 있고 본문 없음)
    {"type": "json", "name": "にじさんじ公式", "url": "https://www.nijisanji.jp/api/news", "items": "newsList",
     "title": "title", "date": "publishedAtForUser", "image": "thumbnail.url", "link": "https://www.nijisanji.jp/news/{id}", "works": ["にじさんじ"], "extra_words": VTUBER_WORDS},
    # 버튜버 방송 예정 (HOLODEX_API_KEY 필요, holodex.net 계정 설정에서 무료 발급)
    {"type": "holodex", "name": "Hololive", "org": "Hololive", "hours": 48},
    {"type": "holodex", "name": "Nijisanji", "org": "Nijisanji", "hours": 48},
    {"type": "holodex", "name": "VSPO", "org": "VSpo", "hours": 48},
    # 한국에서 열리는 일본 IP 행사(region=KR): 한국 매체마다 따로 붙이지 않고 Google 뉴스 한국어 검색 RSS 로 모은다(gnews: 제목 끝 ' - 매체'를 떼어 출처로).
    # 제목에 일본 IP 단어(KR_IP_RE·works.json 의 한국어 이름)와 행사 단어(KR_EVENT_RE)가 둘 다 있어야 통과
    {"type": "rss", "name": "한국 뉴스(애니 팝업스토어)", "url": "https://news.google.com/rss/search?q=%EC%95%A0%EB%8B%88%20%ED%8C%9D%EC%97%85%EC%8A%A4%ED%86%A0%EC%96%B4%20when%3A30d&hl=ko&gl=KR&ceid=KR:ko", "region": "KR", "gnews": True},
    {"type": "rss", "name": "한국 뉴스(애니메이션 콜라보 카페)", "url": "https://news.google.com/rss/search?q=%EC%95%A0%EB%8B%88%EB%A9%94%EC%9D%B4%EC%85%98%20%EC%BD%9C%EB%9D%BC%EB%B3%B4%20%EC%B9%B4%ED%8E%98%20when%3A30d&hl=ko&gl=KR&ceid=KR:ko", "region": "KR", "gnews": True},
    {"type": "rss", "name": "한국 뉴스(애니 전시회)", "url": "https://news.google.com/rss/search?q=%EC%95%A0%EB%8B%88%20%EC%A0%84%EC%8B%9C%ED%9A%8C%20when%3A30d&hl=ko&gl=KR&ceid=KR:ko", "region": "KR", "gnews": True},
    {"type": "rss", "name": "한국 뉴스(애니 내한 공연)", "url": "https://news.google.com/rss/search?q=%EC%95%A0%EB%8B%88%20%EB%82%B4%ED%95%9C%20%EA%B3%B5%EC%97%B0%20when%3A30d&hl=ko&gl=KR&ceid=KR:ko", "region": "KR", "gnews": True},
    # 한국 정식 공개·발매(2026-10): 애니플러스·라프텔 방영 시작, 국내 정식 발매 굿즈. KR_LOC_RE 의 플랫폼 이름이 한국 신호
    {"type": "rss", "name": "한국 뉴스(애니 국내 방영)", "url": "https://news.google.com/rss/search?q=%EC%95%A0%EB%8B%88%ED%94%8C%EB%9F%AC%EC%8A%A4%20OR%20%EB%9D%BC%ED%94%84%ED%85%94%20%EC%8B%A0%EC%9E%91%20%EB%B0%A9%EC%98%81%20when%3A30d&hl=ko&gl=KR&ceid=KR:ko", "region": "KR", "gnews": True},
    {"type": "rss", "name": "한국 뉴스(애니 국내 발매)", "url": "https://news.google.com/rss/search?q=%EC%95%A0%EB%8B%88%20%EA%B5%AD%EB%82%B4%20%EC%A0%95%EC%8B%9D%20%EB%B0%9C%EB%A7%A4%20when%3A30d&hl=ko&gl=KR&ceid=KR:ko", "region": "KR", "gnews": True},
    {"type": "rss", "name": "한국 뉴스(일본 애니 콜라보)", "url": "https://news.google.com/rss/search?q=%EC%9D%BC%EB%B3%B8%20%EC%95%A0%EB%8B%88%20%EC%BD%9C%EB%9D%BC%EB%B3%B4%20when%3A30d&hl=ko&gl=KR&ceid=KR:ko", "region": "KR", "gnews": True},
    # 작은 갤러리의 원화전·색지전(2026-10 말): X 에만 올라오는 게 많아 일본어 Google 뉴스 검색으로 보도자료라도 잡는다(링크는 Google 이동 주소라 기사 보강은 안 함)
    {"type": "rss", "name": "일본 뉴스(原画展·色紙展)", "url": "https://news.google.com/rss/search?q=" + urllib.parse.quote("原画展 OR 色紙展 OR 複製原画展 OR イラスト展 when:30d") + "&hl=ja&gl=JP&ceid=JP:ja", "gnews": True,
     # 그림책·지역 미술전 같은 원화전이 많아(첫 점검 100건 중 94건 통과) 제목에 전시 말 + 작품·애니·만화 신호가 둘 다 있어야 한다
     "title_re": [r"原画展|色紙展|複製原画|イラスト展|原画展示", r"[『「].+?[』」]|アニメ|漫画|マンガ|コミック|ゲーム|声優|劇場版|周年|画業"]},
    # 제보(2026-10 말): 보드 사이트 개요의 '소식 제보'로 들어온 주소(X 글·행사 페이지)를 게시판 웹 앱 ?tips=1 에서 읽는다. X 글은 oEmbed 로 본문을 읽는다(collect_tips)
    {"type": "tips", "name": "제보(X·행사 페이지)"},
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
MUST_HAVE_ANY = ["即売会", "オンリー", "コミケ", "コミックマーケット", "COMITIA", "単行本", "新連載", "完結", "アニメ化", "原画展", "色紙展", "複製原画", "イラスト展", "展覧会", "ライブ", "LIVE", "公演", "イベント", "チケット", "先行", "抽選", "コラボ", "開催", "ツアー", "フェス", "POP UP", "ポップアップ", "カフェ", "ストア"]
# 제목이 이런 식이면 반복성 기사로 보고 버린다: 어디서 볼 수 있나, 몇 화 줄거리·선행 컷, 감상·고찰, 주간 순위, 세일.
# 단 상영회·이벤트·개최·라이브처럼 행사 단어가 함께 있으면 남긴다.
NOISE_RE = re.compile(r"どこで(見|観|視聴)|配信(サービス|サイト|先)|視聴方法|見逃し|無料(で|配信|視聴)|見る順番|何話まで|第\d+話|話数|"
                      r"あらすじ|先行カット|ネタバレ|感想|考察|レビュー|週間ランキング|今週の|来週の|ランキング(TOP|まとめ)|セール|%OFF|％OFF|Kindle|電子書籍|"
                      r"放送時間|放送日程|いつから|何時から|サービス終了情報まとめ|人気投票|アンケート|診断", re.I)
EVENT_WORDS_RE = re.compile(r"上映会|イベント|開催|ライブ|LIVE|公演|展|フェス|コラボ|ポップアップ|POP ?UP", re.I)


def is_noise(title):
    return bool(NOISE_RE.search(title or "")) and not EVENT_WORDS_RE.search(title or "")


# 게임 뉴스 출처(game=True)의 게임 안 소식: 가챠·참전·새 캐릭터·업데이트·서비스 종료 등. 공연·매장·굿즈 같은 바깥 행사 단어가 제목에 있으면 남긴다.
# 2026-10 電撃オンライン 85건에서 22건이 걸렸고 모두 게임 안 소식이었다.
GAME_NOISE_RE = re.compile(r"ガチャ|ガシャ|召喚|SSR|★5|参戦|実装|新階層|育成イベント|イベントクエスト|ログインボーナス|ピックアップ|アップデート|アプデ|配布|復刻|"
                           r"新キャラ|新衣装|新スキン|シーズン\d|DLC|メンテナンス|サービス終了|配信開始|事前登録|ネットワークテスト|βテスト|攻略|新章|新ストーリー|スナップイベント")
GAME_REAL_RE = re.compile(r"会場|店舗|カフェ|ストア|ショップ|展(?!開|望)|ライブ|LIVE|ファンフェス|フェスティバル|上映|舞台|ステージ|POP ?UP|ポップアップ|フェア|物販|"
                          r"イオン|幕張|試遊会|体験会|オフライン|ゲームショウ|ジャンプフェスタ|コミケ|AnimeJapan|グッズ|一番くじ|ローソン|ファミマ|ファミリーマート|セブン|コンビニ|プライズ|ROUND1|キャンペーン", re.I)
GAME_SOURCES = {s["name"] for s in SOURCES if s.get("game")}


GAME_STORE_RE = re.compile(r"(Steam|PlayStation|PS|ニンテンドー|Nintendo|Microsoft|Xbox|Epic Games|App |Google Play)\s*ストア(ページ)?|ストアページ|eショップ", re.I)


def game_title(title):
    """게임 판매처 이름(Steamストアページ 등)의 'ストア'가 매장으로 잡히지 않게 지운 제목"""
    return GAME_STORE_RE.sub(" ", title or "")


def is_game_noise(title):
    t = game_title(title)
    return bool(GAME_NOISE_RE.search(t)) and not GAME_REAL_RE.search(t)


# ────────────────────────────────────────────────────────────────

TICKET_DOMAINS = ["eplus.jp", "l-tike.com", "pia.jp", "ticket.rakuten.co.jp", "livepocket.jp",
                  "tiget.net", "zaiko.io", "teket.jp", "asobistore.jp", "passmarket.yahoo.co.jp", "peatix.com"]
CAT_RULES = [
    ("doujin", r"同人誌即売会|同人イベント|オンリーイベント|オンリー即売会|プチオンリー|WEBオンリー|コミックマーケット|コミケ|COMITIA|コミティア|COMIC CITY|コミックシティ|即売会"),
    ("official", r"ジャンプフェスタ|AnimeJapan|東京ゲームショウ|ワンダーフェスティバル|コミコン|ニコニコ超会議|超会議|ファンフェスタ|ファン感謝祭|公式イベント"),
    # 제목이 스토어·팝업숍이면 'ライブ'가 들어 있어도(ラブライブ, ホロライブ, 学園祭ライブVer. ストア …) 공연이 아니라 팝업으로 본다. \A…[^\n]* 는 제목 줄만 본다
    ("popup", r"\A[^\n]*(?:ストア|ショップ|SHOP|STORE|POP ?UP|ポップアップ)"),
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
OPEN_WORDS = r"受付|発売|先行|抽選|販売|예매|예약|판매|오픈"
END_WORDS = r"締切|〆切|しめきり|まで|마감|까지"
# 한국 출처(region=KR)는 이 규칙을 먼저 본다(일본어 CAT_RULES 는 한국어 기사에 안 걸림)
KR_CAT_RULES = [("popup", r"팝업|스토어"), ("exhibit", r"전시|원화전|展"), ("live", r"내한|공연|콘서트|페스티벌"),  # '라이브'는 러브라이브·홀로라이브와 겹쳐 뺐다
                ("collab", r"콜라보|컬래버|카페"), ("stream", r"방영|방송|동시 ?공개|독점 ?공개|더빙|자막|개봉"),  # 한국 정식 공개(애니플러스·라프텔·극장 개봉)
                ("event", r"행사|팬미팅|상영회|페스타|체험"), ("goods", r"굿즈|발매|출시|피규어")]
KR_EVENT_RE = re.compile(r"팝업|스토어|콜라보|컬래버|카페|전시|원화전|展|내한|공연|콘서트|페스티벌|페스타|팬미팅|상영회|행사|"
                         r"방영|동시 ?공개|독점 ?공개|더빙|개봉|정식 발매|발매|출시|예약 판매")  # 뒤쪽은 한국 정식 공개·발매(2026-10)
# 일본 IP 신호. '애니'는 뒤에 다른 한글이 붙지 않을 때만(애니모·애니런·애니모어 제외), 만화·게임처럼 넓은 말은 빼고 작품·회사 이름으로 본다(+ works.json 의 한국어 이름)
KR_IP_RE = re.compile(r"애니(?:메이션|송)?(?![가-힣])|日|일본|버튜버|VTuber|홀로라이브|니지산지|극장판|포켓몬|산리오|헬로키티|쿠로미|마이멜로디|시나모롤|리락쿠마|스밋코|"
                      r"짱구|코난|원피스|나루토|귀멸|주술회전|체인소|스파이 ?패밀리|하이큐|최애의 아이|진격의 거인|드래곤볼|슬램덩크|건담|에반게리온|지브리|도라에몽|"
                      r"치이카와|먼작귀|마리오|젤다|커비|파이널 ?판타지|페르소나|블루 ?아카이브|블루록|우마무스메|프리큐어|세일러문|블리치|헌터|러브라이브|아이돌마스터|"
                      r"하츠네 ?미쿠|보컬로이드|카드캡터|히로아카|나의 히어로|은혼|강철의 연금술사|원펀맨|케로로|앙상블 ?스타즈|프로세카|명탐정", re.I)
KR_ABROAD_RE = re.compile(r"도쿄|오사카|교토|후쿠오카|나고야|삿포로|요코하마|일본 현지|현지 개최|업데이트|인게임|게임 ?내|사전 ?예약|정식 출시|일본 (?:방영|개봉|발매)")  # 일본에서 열리는 행사·게임 안 콜라보(한국 기사)
# 한국에서 열린다는 신호(제목). 2026-10 첫 수집에서 일본 현지 콜라보(나라현·하드록 카페 등)·게임 안 콜라보·부동산 기사가 섞여, 한국 장소·내한 말이 있어야 통과
KR_LOC_RE = re.compile(r"국내|한국|韓|서울|부산|대구|인천|광주|대전|울산|수원|성남|고양|일산|판교|제주|홍대|성수|강남|잠실|여의도|명동|용산|신촌|합정|건대|서울숲|"
                       r"코엑스|더현대|롯데|현대백화점|신세계|스타필드|아이파크몰|킨텍스|벡스코|덕스|애니메이트|내한|상륙|첫 해외|"
                       r"애니플러스|라프텔|애니맥스|애니박스|대원|CGV|메가박스|한국어 더빙|한국어 자막|우리말")  # 한국 플랫폼·극장(국내 공개 신호)
KR_IP_GENERIC = {"애니", "애니메이션", "애니송", "日", "일본"}


def kr_ok(title):
    """한국 행사 기사 판정: 행사 단어 + 일본 IP 신호 + 한국 장소 신호, 일본 현지·게임 안 콜라보 말 없음"""
    return bool(KR_EVENT_RE.search(title) and (KR_IP_RE.search(title) or any(k in wnorm(title) for k, _ in KO_NAMES))
                and KR_LOC_RE.search(title) and not KR_ABROAD_RE.search(title))


def kr_key(title, cat):
    """같은 행사 판정용: (제목의 첫 구체적 IP 이름, 분류). 애니·일본 같은 일반어만 있으면 None"""
    for m in KR_IP_RE.finditer(title):
        if m.group(0) not in KR_IP_GENERIC: return (m.group(0), cat)
    k = next((c for k, c in KO_NAMES if k in wnorm(title)), None)
    return (k, cat) if k else None


UA = {"User-Agent": "matome-board-collector/0.1 (personal use)"}


def fetch(url, headers=None, data=None):
    req = urllib.request.Request(url, headers={**UA, **(headers or {})}, data=data)
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read()


def clean(text):
    text = re.sub(r"<br\s*/?>", "\n", text or "", flags=re.I)
    return html.unescape(re.sub(r"<[^>]+>", " ", text)).strip()


def urls_in(text):
    return re.findall(r"https?://[^\s\"'<>）)」]+", text or "")


def ticket_site(u):
    """주소가 어느 티켓 사이트 것인지(TICKET_DOMAINS 의 값). 아니면 ""."""
    host = urllib.parse.urlparse(u).hostname or ""
    return next((d for d in TICKET_DOMAINS if d in host), "")


def ticket_urls(urls):
    """티켓 사이트 링크만 골라 사이트별로 첫 번째 하나씩(e+, ローチケ, ぴあ … 순서는 등장 순)."""
    out, seen = [], set()
    for u in urls:
        d = ticket_site(u)
        if d and d not in seen:
            seen.add(d); out.append(u)
    return out


def ticket_url(urls):
    tk = ticket_urls(urls)
    return tk[0] if tk else ""


DATE_RE = re.compile(
    r"(?:(?P<y>20\d\d)\s*[年/.\-년]\s*)?(?P<m>\d{1,2})\s*(?:[月/]\s*(?P<d>\d{1,2})\s*日?|월\s*(?P<d2>\d{1,2})\s*일)"  # 한국어는 '11월 7일'처럼 일까지(10월 3주차 제외)
    r"(?:\s*[（(][^)）]{1,3}[)）])?(?:\s*(?P<h>\d{1,2})\s*[:：時]\s*(?P<mi>\d{2})?)?")


def find_dates(text, ref):
    """본문 속 날짜를 (iso, 앞뒤 문맥) 목록으로."""
    out = []
    for m in DATE_RE.finditer(text):
        mo, d = int(m["m"]), int(m["d"] or m["d2"])
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


# 티켓 접수 단계: 「FC先行」「最速先行」「2次先行」「プレイガイド先行」「一般発売」처럼 공연은 여러 번 접수한다(2026-10). 라벨 뒤 80자 안의 날짜(기간)를 그 단계의 시작·끝으로.
PHASE_RE = re.compile(r"(?P<n>(?:FC|ファンクラブ|最速|オフィシャル|公式|プレイガイド|(?:第?[一二三四五六七八九\d１-９]次)|CD|アプリ|モバイル|[A-Za-z\u30a0-\u30ff\u4e00-\u9fff]{1,8})\s*(?:抽選|先着)?先行(?:抽選|先着|予約|受付|販売)?(?:\s*[（(](?:抽選|先着)[）)])?"
                      r"|一般(?:発売|販売|先着)|先行(?:抽選|販売|予約)|抽選(?:受付|販売|予約)?)")
PHASE_MAX, PHASE_SPAN, PHASE_RESCAN_MAX = 6, 80, 40
PHASE_CATS = {"live", "official", "event", "exhibit", "doujin", "other"}  # 기사 본문에서 단계를 찾아 넣을 분류(굿즈·만화 기사의 '先行'은 상품 선행 판매)
PHASE_SKIP = re.compile(r"^(?:は|が|の|で|と|に|も|や|・|、|を|から|より)")  # 「は先行」처럼 조사가 라벨로 잡힌 것


def find_phases(text, ref):
    """본문에서 [{n:단계 이름, s:시작, e:끝}] 을 시작 순으로(최대 PHASE_MAX). 같은 이름은 처음 것만. 날짜가 없는 라벨은 버린다."""
    out, seen = [], set()
    for m in PHASE_RE.finditer(text):
        n = re.sub(r"\s+", "", m.group(0))
        if PHASE_SKIP.match(n) or n in seen:
            continue
        win = text[m.end(): m.end() + PHASE_SPAN]
        cut = PHASE_RE.search(win)
        if cut:
            win = win[:cut.start()]  # 다음 단계 라벨 앞까지만
        win = re.split(r"[。\n]", win)[0]  # 문장·줄이 끝나면 그 뒤 날짜는 다른 얘기
        ds = find_dates(win, ref)
        if not ds:
            continue
        s_, e_ = ds[0][0], (ds[1][0] if len(ds) >= 2 and ds[1][0] > ds[0][0] and re.search(r"[〜～~\-－]|まで|から", win) else "")
        dm = DATE_RE.search(win)
        if not e_ and len(ds) == 1 and dm and re.match(r"\s*(まで|締切|〆切)", win[dm.end():]) and not re.search(r"から|より|開始|[〜～~]", win[:dm.start()]):
            s_, e_ = "", s_  # 「抽選販売 期間は11月8日23時まで」처럼 날짜 하나가 마감이면 끝으로
        seen.add(n); out.append({"n": n[:30], "s": s_, **({"e": e_} if e_ else {})})
    out.sort(key=lambda x: x["s"] or x.get("e", ""))
    return out[:PHASE_MAX]


def kr_gram(t):
    k = wkey(re.sub(r"\[[^\]]*\]|【[^】]*】", "", t or ""))  # [포토]·[현장] 같은 머리말은 뺀다
    return {k[i:i + 2] for i in range(len(k) - 1)}


def dice(a, b):
    return 2 * len(a & b) / (len(a) + len(b)) if a and b else 0


def classify(text, default="other", kr=False):
    for cat, pat in (KR_CAT_RULES if kr else []) + CAT_RULES:
        if re.search(pat, text):
            return cat
    return default


def build(title, body, link, src, ref, default_cat="other"):
    text = f"{title}\n{body}"
    if is_noise(title) or (src.get("game") and is_game_noise(title)):
        return None
    if any(not re.search(r, title) for r in src.get("title_re", [])):  # 출처별로 제목에 꼭 있어야 하는 말(정규식마다 하나 이상)
        return None
    kr = src.get("region") == "KR"
    words = MUST_HAVE_ANY + list(src.get("extra_words", []))  # 소스별로 걸러낼 단어를 더할 수 있다
    if kr:  # 한국 출처: 제목에 일본 IP 단어(또는 works.json 의 한국어 작품 이름)와 행사 단어가 둘 다
        if not kr_ok(title):
            return None
    elif words and default_cat != "stream" and not src.get("trust") and not any(w in text for w in words):  # trust: 제보처럼 사람이 고른 출처
        return None
    # 게임 뉴스는 본문에 '이벤트'(게임 안 이벤트)가 흔해서 제목에 행사 단어나 바깥 행사 단어가 있어야 통과(신작 발표·Steam 페이지 공개 등을 거름)
    if src.get("game") and not (any(w in game_title(title) for w in words) or GAME_REAL_RE.search(game_title(title))):
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
    works = tag_works(text, src.get("works", []))
    cat = classify(text, default_cat, kr)
    phases = find_phases(text, ref) if not kr and cat in PHASE_CATS else []
    if phases:  # 단계가 있으면 첫 단계 시작·끝을 판매 시작·마감으로(비어 있을 때만)
        pd = {p["s"] for p in phases if p["s"]} | {p["e"] for p in phases if p.get("e")}
        if event in pd or end in pd:  # 「FC先行 11/19 12:00〜11/22」 기간이 행사 기간으로 잡힌 것 → 단계 날짜가 아닌 첫 날짜를 행사일로
            event, end = next((iso for iso, _ in find_dates(text, ref) if iso not in pd), ""), ""
        opening = opening if opening and opening not in pd else next((p["s"] for p in phases if p["s"]), "")
        deadline = deadline if deadline and deadline not in pd else next((p["e"] for p in phases if p.get("e")), "")
    return {
        "title": title[:200], "category": cat, "source": src.get("name", ""), **({"region": "KR"} if kr else {}),
        "platform": src["type"], "works": works[:5], "eventDate": event, "endDate": end, "ticketOpen": opening,
        "deadline": deadline, "venue": "", "ticketUrl": ticket_url(urls_in(body) + [link]), "ticketUrls": ticket_urls(urls_in(body) + [link]),
        "url": link, "summary": re.sub(r"\s+", " ", body)[:140], **({"phases": phases} if phases else {}),
    }


def parse_when(text):
    """RFC 822(RSS pubDate)나 ISO 8601(Atom, 사이트맵, WP) 날짜 문자열 → aware datetime. 모르면 None."""
    text = (text or "").strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:
            dt = parsedate_to_datetime(text)
        except Exception:
            return None
    return dt if dt.tzinfo else dt.replace(tzinfo=JST)


IMG_SRC_RE = re.compile(r"<img[^>]+src=[\"']([^\"']+)", re.I)


def first_img(html_text):
    """본문 HTML 속 첫 <img src>. 1px 추적 이미지·이모지는 건너뛴다."""
    for u in IMG_SRC_RE.findall(html_text or ""):
        u = html.unescape(u)
        if re.search(r"emoji|/s\.w\.org/|pixel|1x1|spacer|blank\.gif|feedburner|gravatar", u, re.I):
            continue
        return u
    return ""


def feed_image(el, ns):
    """RSS/Atom 항목에서 대표 이미지 주소: enclosure → media:content/thumbnail → 본문 첫 <img> 순."""
    for tag in ("enclosure", "media:content", "media:thumbnail"):
        for m in el.findall(tag, ns):
            u = m.get("url") or m.get("href") or ""
            if u and (tag != "enclosure" or (m.get("type") or "image").startswith("image")):
                return u
    for m in el.findall("media:group/media:thumbnail", ns):
        if m.get("url"):
            return m.get("url")
    return first_img((el.findtext("content:encoded", default="", namespaces=ns) or "") + (el.findtext("description") or "")
                     + (el.findtext("a:content", default="", namespaces=ns) or "") + (el.findtext("a:summary", default="", namespaces=ns) or ""))


def parse_feed(xml_bytes):
    """RSS 2.0 · Atom · Google 뉴스 사이트맵 → [(제목, 본문, 링크, 게시일 datetime|None, 이미지 주소)]"""
    m = re.match(rb'\s*<\?xml[^>]*encoding=["\']([\w-]+)', xml_bytes)
    if m and m.group(1).lower() not in (b"utf-8", b"utf8", b"us-ascii", b"iso-8859-1"):  # Shift_JIS·EUC-JP 는 XML 파서가 못 읽어 UTF-8 로 바꾼다
        enc = m.group(1).decode()
        xml_bytes = re.sub(rb'encoding=["\'][\w-]+["\']', b'encoding="utf-8"', xml_bytes.decode(enc, "replace").encode("utf-8"), count=1)
    root = ET.fromstring(xml_bytes)
    ns = {"a": "http://www.w3.org/2005/Atom", "media": "http://search.yahoo.com/mrss/", "dc": "http://purl.org/dc/elements/1.1/",
          "content": "http://purl.org/rss/1.0/modules/content/"}
    entries = []
    r1 = "{http://purl.org/rss/1.0/}"  # RSS 1.0(RDF)은 item·title 등에 이 이름공간이 붙는다(4Gamer·GAME Watch). 2026-10 전에는 못 읽어 0건이었다
    for it in [*root.iter("item"), *root.iter(r1 + "item")]:  # RSS 2.0 / RSS 1.0
        q = r1 if it.tag.startswith(r1) else ""
        when = parse_when(it.findtext("pubDate") or it.findtext("dc:date", default="", namespaces=ns))
        desc = it.findtext(q + "description") or it.findtext("content:encoded", default="", namespaces=ns) or ""
        entries.append((it.findtext(q + "title") or "", desc, it.findtext(q + "link") or "", when, feed_image(it, ns)))
    for e in root.findall("a:entry", ns):  # Atom(유튜브 포함)
        link = e.find("a:link", ns)
        desc = e.findtext("media:group/media:description", default="", namespaces=ns) or e.findtext("a:summary", default="", namespaces=ns) or e.findtext("a:content", default="", namespaces=ns)
        when = parse_when(e.findtext("a:published", default="", namespaces=ns) or e.findtext("a:updated", default="", namespaces=ns))
        entries.append((e.findtext("a:title", default="", namespaces=ns), desc, link.get("href") if link is not None else "", when, feed_image(e, ns)))
    sm = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9", "n": "http://www.google.com/schemas/sitemap-news/0.9", "i": "http://www.google.com/schemas/sitemap-image/1.1"}
    for u in root.findall("s:url", sm):  # Google 뉴스 사이트맵(RSS가 없는 사이트용): 제목과 링크만 있다
        title = u.findtext("n:news/n:title", default="", namespaces=sm)
        if title:
            entries.append((title, "", u.findtext("s:loc", default="", namespaces=sm), parse_when(u.findtext("n:news/n:publication_date", default="", namespaces=sm)),
                            u.findtext("i:image/i:loc", default="", namespaces=sm)))
    return entries


def ld_events(page):
    """HTML 속 JSON-LD 블록에서 schema.org Event 노드만 모은다."""
    out = []
    for block in re.findall(r"<script[^>]+ld\+json[^>]*>(.*?)</script>", page, re.S):
        try:
            data = json.loads(html.unescape(block.strip()))
        except Exception:
            continue
        nodes = data if isinstance(data, list) else (data.get("@graph") or [data]) if isinstance(data, dict) else []
        out += [n for n in nodes if isinstance(n, dict) and n.get("@type") == "Event"]
    return out


def ld_when(v):
    """schema.org 날짜("2026-10-12T10:00:00" / "2026-10-12") → "YYYY-MM-DDTHH:MM"(JST)."""
    m = re.match(r"(\d{4}-\d{2}-\d{2})(?:T(\d{2}:\d{2}))?", str(v or ""))
    return f"{m.group(1)}T{m.group(2) or '00:00'}" if m else ""


def ld_item(ev, src, ref):
    """JSON-LD Event 하나 → 소식 항목. 제목·날짜·장소가 구조화돼 있어 본문 날짜 추출을 거치지 않는다."""
    title, link = clean(str(ev.get("name") or "")), str(ev.get("url") or "")
    if not title or not link:
        return None
    kind = clean(str(ev.get("description") or ""))
    start, end = ld_when(ev.get("startDate")), ld_when(ev.get("endDate"))
    if end and end[:10] <= start[:10]:
        end = ""
    loc = ev.get("location") if isinstance(ev.get("location"), dict) else {}
    venue = clean(str(loc.get("name") or ""))
    geo, addr = ld_place(loc, venue)
    offers = ev.get("offers") if isinstance(ev.get("offers"), dict) else {}
    text = f"{title} {kind}"
    works = tag_works(text, src.get("works", []))
    return {"title": title[:200], "category": classify(text, "event"), "source": src.get("name", ""), "platform": src["type"],
            "works": works[:5], "eventDate": start, "endDate": end, "ticketOpen": "", "deadline": "", "venue": venue[:80],
            "ticketUrl": ticket_url([str(offers.get("url") or "")]), "ticketUrls": ticket_urls([str(offers.get("url") or "")]), "url": link, "summary": kind[:140],
            "image": ev["image"] if isinstance(ev.get("image"), str) else "", "geo": geo, "address": addr}


# アニメハック이 장소를 못 찾으면 東京都庁 좌표를 넣는다(예: 秋葉原UDX가 新宿에 찍힘). 이 좌표는 新宿 쪽 장소가 아니면 버린다.
GEO_FALLBACK = (35.689487, 139.691706)


def geo_ok(geo, venue):
    """좌표가 쓸 만한가: 일본 범위 안이고, 장소를 감춘 행사(某所)나 都庁 대체 좌표가 아니어야 한다."""
    try:
        lat, lon = float(geo[0]), float(geo[1])
    except (TypeError, ValueError, IndexError):
        return False
    if "某所" in (venue or "") or not (20 < lat < 46 and 122 < lon < 154):
        return False
    near_gov = abs(lat - GEO_FALLBACK[0]) < 0.002 and abs(lon - GEO_FALLBACK[1]) < 0.002
    return not (near_gov and not re.search(r"新宿|都庁", venue or ""))


def ld_place(loc, venue):
    """schema.org Place → ([위도, 경도], 주소 문자열). '都内某所'처럼 장소를 감춘 행사와 都庁 대체 좌표는 좌표를 두지 않는다."""
    a = loc.get("address") if isinstance(loc.get("address"), dict) else {}
    addr = " ".join(clean(str(a.get(k) or "")) for k in ("addressRegion", "addressLocality", "streetAddress") if a.get(k))
    g = loc.get("geo") if isinstance(loc.get("geo"), dict) else {}
    geo = [g.get("latitude"), g.get("longitude")]
    if not geo_ok(geo, venue):
        return [], addr[:80]
    return [round(float(geo[0]), 6), round(float(geo[1]), 6)], addr[:80]


def wp_entries(data, link_prefix=""):
    """WordPress REST API(/wp-json/wp/v2/posts 등)의 글 목록을 (제목, 발췌, 링크)로. RSS가 비어 있는 WP 사이트용.
    link_prefix 를 주면 그 주소로 시작하는 글만 남긴다(다국어 사이트의 번역본 제외용)."""
    if not isinstance(data, list):
        raise ValueError(f"WP REST 응답이 목록이 아님: {str(data)[:80]}")
    out = []
    for p in data:
        if not (isinstance(p, dict) and (p.get("link") or "").startswith(link_prefix)):
            continue
        media = ((p.get("_embedded") or {}).get("wp:featuredmedia") or [{}])[0] or {}
        sizes = (media.get("media_details") or {}).get("sizes") or {}
        img = (sizes.get("medium_large") or sizes.get("medium") or {}).get("source_url") or media.get("source_url") \
            or p.get("jetpack_featured_media_url") or first_img((p.get("content") or {}).get("rendered", ""))
        out.append(((p.get("title") or {}).get("rendered", ""), (p.get("excerpt") or {}).get("rendered", ""), p.get("link", ""),
                    parse_when(p.get("date_gmt") and p["date_gmt"] + "+00:00" or p.get("date")), img or ""))
    return out


def json_entries(data, src):
    """임의의 JSON API 글 목록 → (제목, 본문, 링크, 게시일).
    src: "items" 목록까지의 키 경로("a.b"), "title"/"body"/"date" 필드명, "image" 는 이미지 주소까지의 키 경로("thumbnail.url"),
    "link" 은 "https://…/{id}" 처럼 필드명을 끼운 틀."""
    for k in [k for k in src.get("items", "").split(".") if k]:
        data = data[k]
    if not isinstance(data, list):
        raise ValueError(f"JSON 글 목록이 아님: {str(data)[:80]}")
    out = []
    for x in data:
        if not isinstance(x, dict):
            continue
        body = str(x.get(src["body"], "") or "") if src.get("body") else ""
        try:
            link = src["link"].format(**{k: v for k, v in x.items() if isinstance(v, (str, int))})
        except (KeyError, IndexError):
            continue
        img = x
        for k in [k for k in (src.get("image") or "").split(".") if k]:
            img = img.get(k) if isinstance(img, dict) else None
        out.append((str(x.get(src.get("title", "title"), "") or ""), body, link, parse_when(str(x.get(src.get("date", ""), "") or "")),
                    img if isinstance(img, str) else ""))
    return out


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
RAW = {}  # 출처 이름 → 이번에 피드에서 읽은 글 수(거르기 전). 0 이 이어지면 피드가 고장 난 것(출처 상태·이슈 알림)
DROPPED = {}  # 출처 이름 → 걸러진 글 제목 몇 개(--check 에서 보여 줌)


def html_entries(page, src):
    """뉴스 목록 HTML → (제목, 요약, 링크, 게시일, 그림). src["item"] 은 항목 하나에 맞는 정규식(이름 묶음 link·title·date·summary·image, re.S).
    RSS 도 API 도 없는 사이트용. 날짜는 2026.10.20 / 2026-10-20 / 2026/10/20 꼴을 JST 로 읽는다."""
    out = []
    for m in re.finditer(src["item"], page, re.S):
        d = m.groupdict()
        link = urllib.parse.urljoin(src["url"], html.unescape(d.get("link") or ""))
        when = None
        dm = re.search(r"(\d{4})[./-](\d{1,2})[./-](\d{1,2})", d.get("date") or "")
        if dm:
            try:
                when = datetime(int(dm.group(1)), int(dm.group(2)), int(dm.group(3)), tzinfo=JST)
            except ValueError:
                pass
        out.append((d.get("title") or "", d.get("summary") or "", link, when, d.get("image") or ""))
    return out


def collect(src, ref):
    """출처 하나를 읽는다. fallback 이 있으면 본 주소가 실패하거나 0건일 때 fallback 설정(같은 이름)으로 다시 읽는다."""
    fb = src.get("fallback")
    if not fb:
        return collect_one(src, ref)
    main_src = {k: v for k, v in src.items() if k != "fallback"}
    try:
        out = collect_one(main_src, ref)
        if RAW.get(src.get("name", src["type"])):
            return out
        print(f"  {src.get('name')}: 0건이라 fallback({fb.get('type')})으로 읽음", file=sys.stderr)
    except Exception as e:
        print(f"  {src.get('name')}: 실패({e})라 fallback({fb.get('type')})으로 읽음", file=sys.stderr)
    return collect_one({**main_src, **fb}, ref)


def collect_one(src, ref):
    t = src["type"]
    if t in ("rss", "youtube", "site", "wpjson", "json", "html"):
        url = {"rss": lambda: src["url"], "site": lambda: discover(src["url"]), "wpjson": lambda: src["url"], "json": lambda: src["url"], "html": lambda: src["url"],
               "youtube": lambda: f"https://www.youtube.com/feeds/videos.xml?channel_id={src['channel_id']}"}[t]()
        cat = "stream" if t == "youtube" else "other"
        raw = fetch(url, src.get("headers"))
        if t == "wpjson":
            entries = wp_entries(json.loads(raw), src.get("link_prefix", ""))
        elif t == "json":
            entries = json_entries(json.loads(raw), src)
        elif t == "html":
            entries = html_entries(raw.decode("utf-8", "replace"), src)
        else:
            entries = parse_feed(raw)
        out = []
        RAW[src.get("name", t)] = len(entries)
        for ti, de, li, when, img in entries:
            if when and when < ref - timedelta(days=FRESH_DAYS):
                continue
            ti, de = clean(ti), clean(de)
            pub = ""
            if src.get("gnews"):  # Google 뉴스: '제목 - 매체' → 제목·출처. 요약은 제목 링크 반복이라 버린다
                m = re.match(r"^(.*\S)\s+-\s+([^-]{1,40})$", ti)
                if m: ti, pub = m.group(1), m.group(2).strip()
                de = ""
            if not src.get("region"): SEEN_TEXT.append(f"{ti}\n{de[:300]}")  # 한국 기사는 유행 감지(일본 작품명)에 넣지 않는다
            x = build(ti, de, li, src, ref, cat)
            if x and pub: x["source"] = pub
            if not x:
                DROPPED.setdefault(src.get("name", t), []).append(ti)
            if x:
                if img: x["image"] = urllib.parse.urljoin(li or src.get("url", ""), img.strip())  # 피드에 그림이 있으면 그대로, 없으면 main()에서 og:image 를 찾는다
                out.append(x)
        return out
    if t == "ldjson":
        out, seen_u = [], set()
        for k in range(src.get("months", 1)):
            y, m = ref.year + (ref.month - 1 + k) // 12, (ref.month - 1 + k) % 12 + 1
            page = fetch(src["url"].format(ym=f"{y}{m:02d}"), src.get("headers")).decode("utf-8", "replace")
            for ev in ld_events(page):
                x = ld_item(ev, src, ref)
                if x and x["url"] not in seen_u:
                    seen_u.add(x["url"]); out.append(x)
        RAW[src.get("name", t)] = len(out)
        return out
    if t == "tips":
        return collect_tips(src, ref)
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
            out.append({"title": v.get("title", "")[:200], "category": "stream", "source": ch, "platform": "holodex", "image": f"https://i.ytimg.com/vi/{v.get('id','')}/mqdefault.jpg" if v.get("id") else "",
                        "works": [ch] if ch else [], "eventDate": ev, "ticketOpen": "", "deadline": "", "venue": "",
                        "ticketUrl": "", "url": f"https://www.youtube.com/watch?v={v.get('id','')}", "summary": ""})
        return out
    raise ValueError(f"알 수 없는 소스 종류: {t}")


# ---- 제보(2026-10 말) ----
# 보드 사이트 개요의 '소식 제보'(X 글 주소나 행사 페이지 주소 + 메모)가 게시판 웹 앱(bbs/Code.gs)의 tips 시트에 쌓이고, 여기서 GET ?tips=1 로 읽는다.
# 시트의 상태 칸에 no 를 적은 제보는 웹 앱이 돌려주지 않는다(숨김). X 글은 키 없는 oEmbed(publish.twitter.com)로 본문·작성자를 읽고,
# 그 밖의 주소는 페이지의 og:title·og:description·og:image 를 읽는다. 이미 보드에 있는 주소는 다시 열지 않는다(TIPS_MAX 건까지).
TIPS_MAX = 60
X_URL_RE = re.compile(r"^https://(?:www\.|mobile\.)?(?:x|twitter)\.com/(\w{1,15})/status/(\d+)")


def tips_api():
    """게시판 웹 앱 주소: 환경변수 TIPS_API, 없으면 index.html 의 BBS.api(한 곳에만 적어 두려고)."""
    if os.environ.get("TIPS_API"): return os.environ["TIPS_API"]
    try:
        m = re.search(r'const BBS\s*=\s*\{\s*api:\s*"(https://script\.google\.com/macros/[^"]+)"', open(os.path.join(ROOT, "index.html"), encoding="utf-8").read())
        return m.group(1) if m else ""
    except Exception:
        return ""


def tip_x(url):
    """X 글 → (본문, 작성자). oEmbed 의 html 은 <blockquote><p>본문</p>&mdash; 이름 (@id) <a>날짜</a></blockquote>."""
    m = X_URL_RE.match(url)
    q = urllib.parse.urlencode({"url": f"https://twitter.com/{m.group(1)}/status/{m.group(2)}", "omit_script": "true", "dnt": "true", "lang": "ja"})
    d = json.loads(fetch(f"https://publish.twitter.com/oembed?{q}"))
    h = d.get("html", "")
    p = re.search(r"<p[^>]*>(.*?)</p>", h, re.S)
    body = html.unescape(re.sub(r"<br\s*/?>", "\n", p.group(1) if p else "")) if p else ""
    body = re.sub(r"<[^>]+>", "", body)
    body = re.sub(r"https?://t\.co/\w+|pic\.twitter\.com/\w+", "", body).strip()
    return body, (d.get("author_name") or m.group(1))


def tip_page(url):
    """일반 페이지 → (제목, 설명, 그림)."""
    page = fetch(url).decode("utf-8", "replace")
    def meta(prop):
        m = re.search(r'<meta[^>]+(?:property|name)=["\']' + prop + r'["\'][^>]*content=["\']([^"\']*)', page, re.I) \
            or re.search(r'<meta[^>]+content=["\']([^"\']*)["\'][^>]*(?:property|name)=["\']' + prop + r'["\']', page, re.I)
        return html.unescape(m.group(1)).strip() if m else ""
    t = meta("og:title") or html.unescape((re.search(r"<title[^>]*>(.*?)</title>", page, re.S | re.I) or [None, ""])[1]).strip()
    return t, meta("og:description") or meta("description"), og_from_html(page, url)


def tip_title(body):
    """제목이 없는 X 글: 『』「」 안 이름이 있으면 그 줄, 없으면 첫 줄(해시태그·이모지 정리), 80자."""
    lines = [re.sub(r"[#＃]\S+", "", x).strip(" 　・|") for x in body.splitlines()]
    lines = [x for x in lines if len(x) >= 4]
    pick = next((x for x in lines if re.search(r"[『「].+?[』」]", x) and re.search(r"展|開催|イベント|フェア", x)), None) or (lines[0] if lines else "")
    return pick[:80]


def collect_tips(src, ref):
    api = tips_api()
    if not api:
        raise ValueError("게시판 웹 앱 주소(index.html 의 BBS.api 또는 TIPS_API)를 못 찾음")
    data = json.loads(fetch(api + ("&" if "?" in api else "?") + "tips=1"))
    tips = [t for t in data.get("tips", []) if re.match(r"^https?://", str(t.get("url", "")))]
    RAW[src["name"]] = len(tips)
    try: known = {x.get("url") for x in json.load(open(OUT, encoding="utf-8"))}
    except Exception: known = set()
    out, seen = [], set()
    trust = {**src, "trust": True}
    for t in tips[:TIPS_MAX]:
        url, note = str(t["url"]).strip()[:300], str(t.get("note", "")).strip()[:300]
        mx = X_URL_RE.match(url)
        key = f"https://x.com/{mx.group(1)}/status/{mx.group(2)}" if mx else url  # x.com·twitter.com·?s= 꼬리를 하나로
        if key in known or key in seen: continue
        seen.add(key)
        try:
            if mx:
                body, who = tip_x(url)
                title, img, source = tip_title(body), "", f"X · {who}"[:40]
            else:
                title, body, img = tip_page(url)
                source = urllib.parse.urlparse(url).hostname or "제보"
        except Exception as e:
            print(f"  제보 {url[:60]}: 읽지 못함 ({e})", file=sys.stderr); continue
        if not title and note: title = note.splitlines()[0][:80]
        if not title: continue
        x = build(title, f"{body}\n{note}".strip(), key, trust, ref, "exhibit")
        if not x: continue
        x["source"], x["platform"], x["tip"] = source, "tip", True
        if img: x["image"] = img
        if mx: x["scanned"] = True  # X 페이지는 열어도 그림·티켓 링크를 못 얻는다(기사 보강 건너뜀)
        out.append(x)
    return out


# ---- 작품 이름 정리(data/works.json, 사람이 고침) ----
# 같은 작품이 『ゴジラ-0.0』/『ゴジラ－0.0』, 『超かぐや姫！』/『超かぐや姫!』처럼 갈라지지 않게 NFKC·소문자·공백·문장부호를 뗀 키(wkey)로 비교하고,
# 다른 이름(hololive→ホロライブ 등)은 works.json 의 alias 로, 'X 부제'는 X 가 작품이면 X 로 묶는다.
WORKS_FILE = os.path.join(DATA, "works.json")
WK_STRIP = re.compile(r"[\s・·:!?~〜\-_.,()\[\]【】「」『』'\"/|&＆×✕]")
def wnorm(s): return unicodedata.normalize("NFKC", s or "").lower()
def wkey(n): return WK_STRIP.sub("", wnorm(n))
def clean_name(n): return re.sub(r"^[『「【\s]+|[』」】\s]+$", "", n or "").strip()
try: _works = json.load(open(WORKS_FILE, encoding="utf-8"))
except Exception: _works = {}
ALIAS = {wkey(k): str(v) for k, v in (_works.get("alias") or {}).items() if wkey(k)}
SKIP = {wkey(x) for x in (_works.get("skip") or []) if wkey(x)}
KO_NAMES = [(wnorm(v), str(k)) for k, v in (_works.get("ko") or {}).items() if len(wnorm(v)) >= 2]  # 한국어 이름 → 대표 이름(한국 기사 작품 태그용)
def canon(n):
    """앞뒤 괄호를 떼고 별칭이면 대표 이름으로"""
    n = clean_name(n)
    return ALIAS.get(wkey(n), n)


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


def rank_works(history):
    """history({날짜: {이름: 횟수}})의 이름을 같은 작품끼리 묶어 [(대표 이름, 합계)]를 많은 순으로.
    같은 키(wkey)끼리 합치고, 'X 부제'는 X 가 작품(씨앗·별칭 대상·혼자서도 TREND_MIN 이상)이면 X 에 더한다.
    대표 이름은 씨앗·별칭 대상과 같은 표기가 있으면 그것, 없으면 가장 많이 나온 표기."""
    total, spell = {}, {}
    for v in history.values():
        for n, c in v.items():
            n = canon(n); k = wkey(n)
            if len(k) < 2 or k in SKIP: continue
            total[k] = total.get(k, 0) + c
            spell.setdefault(k, {})[n] = spell.get(k, {}).get(n, 0) + c
    preferred = {wkey(w): w for w in WORKS_SEED} | {wkey(v): v for v in ALIAS.values()}
    parents = set(preferred) | {k for k, c in total.items() if c >= TREND_MIN}
    for k in sorted(total, key=lambda x: -total[x]):
        if k not in total: continue
        best = max(spell[k], key=spell[k].get)
        head = canon(re.split(r"[\s　]+", best)[0]); hk = wkey(head)
        if hk != k and len(hk) >= 2 and hk in parents and hk not in SKIP:
            total[hk] = total.get(hk, 0) + total.pop(k)
            sp = spell.setdefault(hk, {}); sp.setdefault(head, 0)
    def name(k):
        if k in preferred: return preferred[k]
        return max(spell[k], key=spell[k].get)
    return [(name(k), c) for k, c in sorted(total.items(), key=lambda x: -x[1])]


RISE_DAYS = 3  # 급상승: 최근 며칠과 그 전을 비교


def rising_works(history, names):
    """유행 작품(names) 중 최근 RISE_DAYS일 하루 평균이 그 전 평균의 2배+1 이상이고 최근 합계가 6건 이상인 것.
    x = 최근 하루 평균 / (그 전 하루 평균 + .5). 큰 순으로 6개"""
    days = sorted(history)
    if len(days) < RISE_DAYS + 4: return []
    rec = {wkey(n): c for n, c in rank_works({d: history[d] for d in days[-RISE_DAYS:]})}
    old = {wkey(n): c for n, c in rank_works({d: history[d] for d in days[:-RISE_DAYS]})}
    nb = len(days) - RISE_DAYS
    out = []
    for n in names:
        k = wkey(n); r = rec.get(k, 0); b = old.get(k, 0) / nb
        if r >= 6 and r / RISE_DAYS >= 2 * b + 1:
            out.append({"n": n, "r": r, "b": round(b, 2), "x": round((r / RISE_DAYS) / (b + .5), 1)})
    return sorted(out, key=lambda x: -x["x"])[:6]


def update_trends(tr, ref):
    """오늘 본 기사에서 작품명을 세고, 최근 TREND_DAYS일 합계로 순위를 낸다."""
    today = ref.strftime("%Y-%m-%d")
    counts = {}
    for text in SEEN_TEXT:
        for n in {canon(base_title(clean_name(m))) for m in NAME_RE.findall(text)}:
            if len(n) >= 2 and not STOP.search(n) and wkey(n) not in SKIP:
                counts[n] = counts.get(n, 0) + 1
    day = tr["history"].setdefault(today, {})
    for n, c in counts.items():
        day[n] = max(day.get(n, 0), c)  # 같은 날 여러 번 돌려도 중복 집계하지 않음
    cutoff = (ref - timedelta(days=TREND_DAYS)).strftime("%Y-%m-%d")
    tr["history"] = {d: v for d, v in tr["history"].items() if d >= cutoff}
    old_top = set(tr.get("top", []))
    tr["top"] = [n for n, c in rank_works(tr["history"]) if c >= TREND_MIN][:TREND_TOP]
    tr["rising"] = rising_works(tr["history"], tr["top"])
    tr["updated"] = ref.isoformat()
    json.dump(tr, open(TRENDS, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    rising = [n for n in tr["top"] if n not in old_top]
    if rising:
        print("새로 뜨는 작품:", ", ".join(rising[:10]))


_tr = load_trends()


def _watch():
    """태깅할 작품: 씨앗 + 유행 상위(키로 중복 제거). 본문에서 찾을 표기는 대표 이름과 별칭(3글자 이상만, 짧은 별칭은 다른 낱말에 섞이기 쉬움)"""
    out = {}
    top = [n for n, c in rank_works(_tr.get("history", {})) if c >= TREND_MIN][:TREND_TOP]  # 저장된 top 은 예전 방식(부제 따로)일 수 있어 다시 묶는다
    for w in WORKS_SEED + top:
        c = canon(w); k = wkey(c)
        if len(k) >= 2 and k not in SKIP: out.setdefault(k, [c, {wnorm(c)}])
    for a, v in (_works.get("alias") or {}).items():
        k = wkey(v)
        if k in out and len(wkey(a)) >= 3: out[k][1].add(wnorm(a))
    return out
WATCH = _watch()  # 키 → [대표 이름, {찾을 표기}]


def canon_work(n):
    """소식의 작품 태그 하나를 대표 이름으로: 별칭 → 같은 키의 대표 이름 → 'X 부제'면 X"""
    c = canon(n); k = wkey(c)
    if k in WATCH: return WATCH[k][0]
    head = canon(re.split(r"[\s　]+", c)[0]); hk = wkey(head)
    if hk != k and hk in WATCH: return WATCH[hk][0]
    return c


def tag_works(text, base=()):
    """작품 태그: 소스가 준 이름(정리해서) + 본문에 나오는 WATCH 작품. 같은 작품은 하나만, 최대 5개"""
    out, keys, t = [], set(), wnorm(text)
    for w in list(base) + [c for c, vs in WATCH.values() if any(v in t for v in vs)] + [c for k, c in KO_NAMES if k in t]:
        c = canon_work(w); k = wkey(c)
        if c and k not in keys: keys.add(k); out.append(c)
    return out[:5]



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


def _jst(v):
    try:
        return datetime.fromisoformat(v if re.search(r"[+-]\d\d:\d\d$|Z$", v) else v + "+09:00") if v else None
    except Exception:
        return None


def next_date(it, ref):
    """아직 오지 않았거나 진행 중인 일정(행사 끝·행사일·판매 시작·마감·접수 단계) 중 가장 이른 것. 없으면 None."""
    ds = [_jst(it.get(k)) for k in ("endDate", "eventDate", "ticketOpen", "deadline")]
    ds += [_jst(p.get(k)) for p in it.get("phases") or [] for k in ("s", "e")]
    ds = [d for d in ds if d and d >= ref]
    return min(ds) if ds else None


def keep_items(keep, ref, n=KEEP):
    """n건으로 자를 때 앞으로 일정이 있는 소식(가까운 일정 먼저)을 먼저 남기고, 남는 자리를 나머지(새로 들어온 순)로 채운다.
    예전에는 새로 들어온 순으로만 잘라 6일치(약 600건)만 남아, 몇 주 전에 발표된 행사가 열리기도 전에 빠졌다
    (2026-10 말 池袋ハロウィンコスプレフェス: 7월 말 발표 기사가 행사 당일 보드에 없었다). 순서는 원래대로 둔다."""
    fut = sorted((it for it in keep if next_date(it, ref)), key=lambda it: next_date(it, ref))[:n]
    pick = {id(it) for it in fut}
    pick |= {id(it) for it in [it for it in keep if id(it) not in pick][:n - len(pick)]}
    return [it for it in keep if id(it) in pick]


def blocked(it, block):
    t = (it.get("title") or "").lower()
    return (it.get("url") and it["url"] in block.get("urls", [])) or it.get("id") in block.get("ids", []) \
        or any(k.lower() in t for k in block.get("titles", []) if k)


# 수집기 고장 기록(이번 실행만). 워크플로의 --alert-broken 이 읽어 이슈를 연다
BROKEN_FILE = os.path.join(os.environ.get("RUNNER_TEMP") or tempfile.gettempdir(), "matome-broken.json")


def main():
    ref = datetime.now(JST)
    if os.path.exists(BROKEN_FILE): os.remove(BROKEN_FILE)
    old = load_json(OUT, [])
    block = load_json(os.path.join(DATA, "blocklist.json"), {})
    seen = {(o.get("url"), o.get("title")) for o in old}
    by_key = {(o.get("url"), o.get("title")): o for o in old}
    new = []
    meta = load_json(os.path.join(DATA, "meta.json"), {})
    prev = {x.get("n"): x for x in meta.get("sources", []) if isinstance(x, dict)}
    status = []  # 출처마다 이번 실행 결과(페이지 사이트 개요의 '출처 상태' 표)
    for src in SOURCES:
        name = src.get("name", src["type"])
        p = prev.get(name, {})
        if src["type"] == "holodex" and not os.environ.get("HOLODEX_API_KEY"):
            status.append({"n": name, "ok": None, "e": "HOLODEX_API_KEY 없음(건너뜀)"}); continue
        try:
            got = collect(src, ref)
            for g in got:  # 이미 있는 소식에도 나중에 생긴 필드(좌표·주소)를 채운다
                o = by_key.get((g["url"], g["title"]))
                for k in ("geo", "address"):
                    if o is not None and g.get(k) and not o.get(k):
                        o[k] = g[k]
            fresh = [g for g in got if (g["url"], g["title"]) not in seen and not blocked(g, block)]
            seen.update((g["url"], g["title"]) for g in fresh)
            new += fresh
            print(f"{name}: {len(got)}건 중 새 소식 {len(fresh)}건")
            raw = RAW.get(name, len(got))
            # zr: 피드가 비어 있던(원본 0건) 연속 횟수. 거른 뒤 0건은 흔하지만 원본 0건이 이어지면 주소·구조가 바뀐 것
            status.append({"n": name, "ok": True, "c": len(got), "raw": raw, "new": len(fresh), "at": ref.isoformat(timespec="minutes"),
                           "zr": int(p.get("zr", 0)) + 1 if raw == 0 else 0})
        except Exception as e:
            print(f"{name}: 실패 ({e})", file=sys.stderr)
            # f: 연속 실패 횟수, at: 마지막으로 성공한 시각(이전 기록에서 이어받음)
            status.append({"n": name, "ok": False, "e": str(e)[:160], "f": int(p.get("f", 0)) + 1, "at": p.get("at", "")})
    # 한국 기사: 같은 행사를 여러 매체가 쓰고 날짜가 '11월'뿐이라 페이지의 묶기도 못 잡는다 → 제목이 비슷하면(2-gram Dice .5 이상) 처음 것만
    kr_seen = [kr_gram(o.get("title", "")) for o in old if o.get("region") == "KR"]
    kr_keys = {kr_key(o.get("title", ""), o.get("category")) for o in old if o.get("region") == "KR"} - {None}
    keep_new = []
    for g in new:
        if g.get("region") == "KR":  # 제목이 비슷하거나, 같은 작품 이름·같은 분류면 같은 행사로 본다
            gg, kk = kr_gram(g.get("title", "")), kr_key(g.get("title", ""), g.get("category"))
            if any(dice(gg, h) >= .5 for h in kr_seen) or (kk and kk in kr_keys): continue
            kr_seen.append(gg); kr_keys.add(kk)
        keep_new.append(g)
    new = keep_new
    tried = [x for x in status if x["ok"] is not None]
    bad = [x for x in tried if x["ok"] is False]
    if len(tried) >= 6 and len(bad) * 2 > len(tried):
        # 절반 넘게 실패 = 출처가 아니라 수집기(코드·네트워크)가 고장. 데이터를 쓰지 않고 멈춰 워크플로가 커밋을 건너뛰고 바로 이슈를 연다
        json.dump({"at": ref.isoformat(timespec="minutes"), "tried": len(tried), "bad": bad},
                  open(BROKEN_FILE, "w", encoding="utf-8"), ensure_ascii=False)
        print(f"수집 중단: 출처 {len(tried)}곳 중 {len(bad)}곳 실패 → 데이터를 쓰지 않음", file=sys.stderr)
        sys.exit(3)
    p = prev.get(BUZZ_NAME, {})
    try:  # X 화제(Togetter): 소식 피드와 별개 파일. 출처 상태·알림에는 같이 들어간다
        braw = collect_buzz(ref)
        status.append({"n": BUZZ_NAME, "ok": True, "c": braw, "raw": braw, "new": 0, "at": ref.isoformat(timespec="minutes"),
                       "zr": int(p.get("zr", 0)) + 1 if braw == 0 else 0})
    except Exception as e:
        print(f"{BUZZ_NAME}: 실패 ({e})", file=sys.stderr)
        status.append({"n": BUZZ_NAME, "ok": False, "e": str(e)[:160], "f": int(p.get("f", 0)) + 1, "at": p.get("at", "")})
    for n in new:
        n["addedAt"] = ref.isoformat()
    enrich(new + old, ref)
    translate_items(new + old)
    update_trends(_tr, ref)
    json.dump(_cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)
    # 정리: 끝난 지 30일 넘은 것, 날짜 없이 45일 지난 것, 차단 목록에 걸린 것은 뺀다
    keep = []
    kr_best = {}  # 한국 기사: 같은 행사(kr_key) 중 날짜·장소가 있는 기사 하나만 남긴다
    for it in new + old:
        if it.get("region") == "KR" and kr_ok(it.get("title", "")):
            kk = kr_key(it.get("title", ""), classify(it.get("title", ""), "other", True))
            score = (2 if it.get("eventDate") else 0) + (1 if it.get("venue") or re.search(r"홍대|성수|서울숲|코엑스|더현대", it.get("title", "")) else 0)
            if kk and (kk not in kr_best or score > kr_best[kk][0]): kr_best[kk] = (score, id(it))
    for it in new + old:
        if it.get("geo") and not geo_ok(it["geo"], it.get("venue", "")):  # 예전에 저장된 都庁 대체 좌표 정리
            it["geo"] = []
        if it.get("category") == "live" and re.search(CAT_RULES[2][1], it.get("title", "")):  # 예전에 공연으로 잘못 분류된 스토어 소식
            it["category"] = classify(it["title"] + "\n" + it.get("summary", ""), "other")
        if blocked(it, block) or (it.get("platform") != "ldjson" and is_noise(it.get("title", ""))) \
                or (it.get("source") in GAME_SOURCES and is_game_noise(it.get("title", ""))):
            continue
        if it.get("works"): it["works"] = tag_works("", it["works"])  # 예전 태그도 대표 이름으로(ゴジラ－0.0 → ゴジラ-0.0 등)
        if it.get("region") == "KR":  # 한국 기사: 지금 기준으로 다시 거르고 분류하고, 같은 행사(작품 이름·분류)는 하나만
            if not kr_ok(it.get("title", "")): continue
            it["category"] = classify(it.get("title", ""), "other", True)
            kk = kr_key(it.get("title", ""), it["category"])
            if kk and kr_best.get(kk, (0, id(it)))[1] != id(it): continue
        guess_place(it)  # 장소 칸이 비면 data/venues.json 으로 채움(예전 추정은 다시 찾음)
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
    items = keep_items(keep, ref)
    save_json(OUT, items)
    meta.update({"updated": ref.isoformat(), "trends": _tr.get("top", [])[:20], "rising": _tr.get("rising", []), "count": len(items), "sources": status})
    save_json(os.path.join(DATA, "meta.json"), meta)
    write_feed(ref)
    write_calendars(ref)
    write_share_pages()
    print(f"→ data/items.json: 총 {len(items)}건 (이번에 {len(new)}건 추가)")


SITE = "https://davidim-dotcom.github.io/matome-board/"
FEED = os.path.join(DATA, "feed.xml")
FEED_N = 60
CAT_KO = {"live": "공연", "event": "행사", "official": "공식", "doujin": "동인", "collab": "콜라보", "popup": "팝업",
          "exhibit": "전시", "manga": "만화", "goods": "굿즈", "stream": "방송", "campaign": "캠페인", "other": "기타"}

def write_feed(ref):
    """data/feed.xml: 새로 들어온 소식 FEED_N 건과 이번 주간 요약을 RSS 2.0 으로. RSS 앱·디스코드 RSS 봇으로 구독한다.
    방송 예정(stream)은 너무 많고 금방 지나가서 뺀다."""
    from email.utils import format_datetime
    from xml.sax.saxutils import escape as xe
    items = [it for it in load_json(OUT, []) if (it.get("category") != "stream" or it.get("region") == "KR") and it.get("url")]  # 한국 방영 소식은 넣는다
    def added(it):
        try: return datetime.fromisoformat(it.get("addedAt", ""))
        except ValueError: return ref - timedelta(days=60)
    items.sort(key=added, reverse=True)
    def when(v):
        try: return _kdate(v)
        except Exception: return ""
    out = []
    wk = load_json(WEEKLY, {})
    if wk.get("picks"):
        body = "\n".join(f"{i + 1}. {p.get('title', '')}" + (f" ({p['when']})" if p.get("when") else "") for i, p in enumerate(wk["picks"]))
        try: wd = datetime.fromisoformat(str(wk.get("updated") or wk.get("week"))[:10]).replace(tzinfo=JST)
        except ValueError: wd = ref
        out.append((f"[주간 요약] {wk.get('title', '')} {wk.get('range', '')}".strip(), SITE + "#weekly", body,
                    wd, f"weekly-{wk.get('week', '')}", "주간 요약"))
    for it in items[:FEED_N]:
        bits = [x for x in (
            f"{when(it['eventDate'])}" + (f" ~ {when(it['endDate'])}" if it.get("endDate") else "") if it.get("eventDate") else "",
            f"장소: {it['venue']}" if it.get("venue") else "",
            f"판매·추첨 시작: {when(it['ticketOpen'])}" if it.get("ticketOpen") else "",
            f"마감: {when(it['deadline'])}" if it.get("deadline") else "",
            it.get("title_ko") or "", (it.get("summary") or "")[:300]) if x]
        out.append((it.get("title", ""), it["url"], "\n".join(bits), added(it), it["url"], CAT_KO.get(it.get("category"), "기타")))
    xml = ['<?xml version="1.0" encoding="UTF-8"?>', '<rss version="2.0"><channel>',
           f"<title>마토메 보드</title><link>{SITE}</link><description>일본 게임·애니·버튜버·만화 공연·이벤트 소식</description><language>ja</language>",
           f"<lastBuildDate>{format_datetime(ref)}</lastBuildDate>"]
    for title, link, desc, d, guid, cat in out:
        xml.append(f"<item><title>{xe(title)}</title><link>{xe(link)}</link><guid isPermaLink=\"false\">{xe(guid)}</guid>"
                   f"<category>{xe(cat)}</category><pubDate>{format_datetime(d)}</pubDate><description>{xe(desc)}</description></item>")
    xml.append("</channel></rss>")
    with open(FEED, "w", encoding="utf-8") as f:
        f.write("\n".join(xml) + "\n")


# ---- X 화제(data/xbuzz.json): Togetter 의 인기·새 정리 ----
# X 는 무료 API 가 없어 직접 못 읽는다. 대신 X 게시물을 사람이 묶은 Togetter 의 RSS(인기 10건·새 정리 100건)를 모은다.
# 제목·요약·링크·썸네일만 두고(X 게시물 본문은 가져오지 않음), 보드 작품 이름 태그와 오타쿠 화제 여부를 붙인다. 유행 순위(trends)에는 넣지 않는다.
BUZZ = os.path.join(DATA, "xbuzz.json")
BUZZ_NAME = "Togetter(X 화제)"
BUZZ_FEEDS = [("hot", "https://togetter.com/rss/hot"), ("news", "https://togetter.com/rss/news")]
BUZZ_DAYS, BUZZ_MAX = 7, 400
BUZZ_IMG_MAX = 20  # 실행마다 그림(og:image)을 찾으러 여는 Togetter 페이지 수. RSS 에 그림이 없어서(2026-10), 인기·오타쿠 화제만 한 번씩 연다
OTAKU_RE = re.compile(r"アニメ|漫画|マンガ|まんが|コミック|ゲーム|声優|VTuber|Vtuber|ブイチューバー|ホロライブ|にじさんじ|コミケ|同人|ラノベ|イラスト|絵師|"
                      r"ガンプラ|フィギュア|アニメイト|ポケモン|任天堂|Switch|プレステ|PS5|ガチャ|ソシャゲ|コスプレ|推し|オタク|特撮|プリキュア|ジャンプ|"
                      r"劇場版|聖地巡礼|一番くじ|ボカロ|初音ミク|ニコニコ|コラボカフェ", re.I)


def collect_buzz(ref):
    """Togetter RSS 두 개를 읽어 data/xbuzz.json 을 갱신하고 읽은 글 수를 돌려준다. 둘 다 실패하면 예외.
    h: 인기 목록에 오른 실행 횟수, ha: 마지막으로 인기 목록에 있던 시각, hot: 이번 실행의 인기 목록(순서대로)."""
    old = load_json(BUZZ, {})
    by = {x["u"]: x for x in old.get("items", []) if isinstance(x, dict) and x.get("u")}
    hot_now, raw, errs = [], 0, []
    now = ref.isoformat(timespec="minutes")
    for kind, url in BUZZ_FEEDS:
        try:
            entries = parse_feed(fetch(url))
        except Exception as e:
            errs.append(f"{kind}: {e}"); print(f"{BUZZ_NAME} {kind}: 실패 ({e})", file=sys.stderr); continue
        raw += len(entries)
        for ti, de, li, when, img in entries:
            if not li or not ti: continue
            ti, de = clean(ti), clean(de)
            x = by.get(li) or {"u": li, "at": now, "h": 0}
            text = f"{ti}\n{de}"
            de = re.sub(r"\s+", " ", de)
            if de[:30] == ti[:30]: de = ""  # Togetter RSS 의 요약은 대개 제목 그대로라 겹치면 비운다
            x.update(t=ti[:200], s=de[:200], d=(when or _when(x["at"]) or ref).astimezone(JST).isoformat(timespec="minutes"))
            if img: x["img"] = urllib.parse.urljoin(li, img.strip())
            x["w"] = tag_works(text, [])[:5]
            x["o"] = bool(x["w"] or OTAKU_RE.search(text))
            if kind == "hot" and li not in hot_now:
                x["h"] = int(x.get("h", 0)) + 1; x["ha"] = now; hot_now.append(li)
            by[li] = x
    if len(errs) == len(BUZZ_FEEDS):
        raise RuntimeError("; ".join(errs))
    want = [x for x in by.values() if not x.get("img") and not x.get("it") and (x["u"] in hot_now or x.get("o"))]
    want.sort(key=lambda x: (x["u"] not in hot_now, x.get("d", "")))  # 지금 인기부터
    for x in want[:BUZZ_IMG_MAX]:
        x["it"] = 1  # 한 번 열어 본 정리는 다시 열지 않는다
        try:
            img = og_from_html(fetch(x["u"]).decode("utf-8", "replace"), x["u"])
            if img.startswith("https://"): x["img"] = img
        except Exception as e:
            print(f"{BUZZ_NAME}: 그림 실패 {x['u']} ({e})", file=sys.stderr)
    cut = ref - timedelta(days=BUZZ_DAYS)
    items = sorted((x for x in by.values() if (_when(x.get("d")) or ref) > cut or x["u"] in hot_now), key=lambda x: x.get("d", ""), reverse=True)[:BUZZ_MAX]
    # X 에서 화제인 작품 이름: 일주일치 정리 제목의 『』「」 이름을 유행 감지와 같은 규칙으로 센다(뉴스 기반 trends 와는 따로)
    names = {}
    for x in items:
        for n in {canon(base_title(clean_name(m))) for m in NAME_RE.findall(x.get("t", ""))}:
            if len(n) >= 2 and not STOP.search(n) and wkey(n) not in SKIP:
                names[n] = names.get(n, 0) + 1
    ranked = [[n, c] for n, c in rank_works({"x": names}) if c >= 2][:40]
    save_json(BUZZ, {"updated": now, "hot": hot_now, "names": ranked, "items": items})
    print(f"→ data/xbuzz.json: 인기 {len(hot_now)}건, 모두 {len(items)}건 (오타쿠 화제 {sum(1 for x in items if x.get('o'))}건)")
    return raw


# ---- 장소 사전(data/venues.json, 사람이 고침) ----
# 콜라보·팝업 기사는 대개 장소 칸이 비어 있어 지도·이번 주말 보기에 안 잡힌다. 제목·요약에 아는 장소 이름이 있으면 venue·geo·address 를 채운다.
VENUES_FILE = os.path.join(DATA, "venues.json")
AREA_SKIP_RE = re.compile(r"巡回|全国|各地|\d+都市|\d+会場|ツアー|順次|ほか|・(?:大阪|名古屋|福岡|札幌|東京)|순회|전국|지점|곳에서")  # 여러 곳에서 열리는 행사는 한 점으로 찍지 않는다
_VENUES = None


def _venue_table():
    global _VENUES
    if _VENUES is None:
        v = load_json(VENUES_FILE, {})
        nf = lambda t: unicodedata.normalize("NFKC", t)
        spots = sorted(((nf(nm), x) for x in v.get("venues", []) if x.get("geo") for nm in [x["n"], *x.get("a", [])]), key=lambda t: -len(t[0]))
        areas = [(nf(nm), x) for x in v.get("areas", []) if x.get("geo") for nm in [x["n"], *x.get("a", [])]]
        _VENUES = (spots, areas)
    return _VENUES


def guess_place(it):
    """장소 칸이 빈 소식에 장소 사전으로 venue·geo·address 를 넣는다(placeGuess=True). 예전 추정은 매번 지우고 다시 찾아 사전 수정이 반영된다.
    구체 장소는 제목 → 요약 순(긴 이름 먼저), 동네·도시는 제목에 딱 하나만 있고 순회·여러 도시 말이 없을 때만 '○○周辺'."""
    if it.get("placeGuess"):
        for k in ("venue", "address"): it[k] = ""
        it["geo"] = []; it.pop("placeGuess", None)
    if it.get("venue") or it.get("category") == "stream" or it.get("platform") in ("holodex", "youtube"):
        return False
    spots, areas = _venue_table()
    t = unicodedata.normalize("NFKC", it.get("title", ""))
    if AREA_SKIP_RE.search(t):
        return False
    for text in (t, unicodedata.normalize("NFKC", it.get("summary", ""))):
        for nm, x in spots:
            if nm in text:
                it.update(venue=x["n"], geo=list(x["geo"]), address=x.get("addr", ""), placeGuess=True)
                return True
    hits = {x["n"]: x for nm, x in areas if nm in t}
    if len(hits) == 1:
        x = next(iter(hits.values()))
        it.update(venue=x["n"].split("(")[0] + "周辺", geo=list(x["geo"]), address=x.get("addr", ""), placeGuess=True)
        return True
    return False


# ---- 구독용 달력(data/calendar*.ics) ----
# 구글 캘린더·아이폰 캘린더에서 'URL로 구독'하면 새 일정이 자동으로 들어온다. 페이지의 '달력에 추가'(한 번 받는 .ics)와 같은 규칙.
CALENDARS = [("calendar.ics", "마토메 보드", ("ev", "ticketOpen", "deadline")),
             ("calendar-events.ics", "마토메 보드 · 행사", ("ev",)),
             ("calendar-tickets.ics", "마토메 보드 · 예매·마감", ("ticketOpen", "deadline"))]


def _when(v):
    if not v: return None
    try: return datetime.fromisoformat(v if re.search(r"[+-]\d\d:\d\d$|Z$", v) else v + "+09:00").astimezone(JST)
    except ValueError: return None


def ics_events(it, ref):
    """(종류, 시작, 끝|None, 머리말) 목록. 끝난 지 7일 넘은 행사, 지난 판매 시작·마감은 뺀다."""
    out = []
    ev, end = _when(it.get("eventDate")), _when(it.get("endDate"))
    if ev and (end or ev) > ref - timedelta(days=7):
        out.append(("ev", ev, end if end and end > ev else None, ""))
    phases = [p for p in (it.get("phases") or []) if isinstance(p, dict) and p.get("s")]
    if phases:  # 단계가 있으면 단계마다 시작·마감(ticketOpen·deadline 은 첫 단계와 겹치므로 안 넣음)
        for i, p in enumerate(phases[:PHASE_MAX]):
            for k, v, label in ((f"p{i}s", p.get("s") or "", f"{p.get('n', '')} 시작"), (f"p{i}e", p.get("e") or "", f"{p.get('n', '')} 마감")):
                d = _when(v)
                if d and d > ref:
                    out.append((k, d, None, label))
        return out
    for k, label in (("ticketOpen", "판매·추첨 시작"), ("deadline", "마감")):
        d = _when(it.get(k))
        if d and d > ref:
            out.append((k, d, None, label))
    return out


def _ics_text(t):
    return str(t or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\r", "").replace("\n", "\\n")


def _ics_fold(line):
    out, n = "", 0
    for ch in line:
        b = len(ch.encode("utf-8"))
        if n + b > 73:
            out += "\r\n "; n = 1
        out += ch; n += b
    return out


SHARE_DIR = os.path.join(DATA, "share")


def page_url(u):
    """페이지 normalize 의 safeUrl(new URL(u).href)과 같은 주소: http(s)만, 한글·일본어 등은 퍼센트 인코딩(id 가 같아야 공유가 맞는다)"""
    u = (u or "").strip()
    if not re.match(r"https?://", u, re.I):
        return ""
    p = urllib.parse.urlsplit(u)
    q = lambda t, safe: urllib.parse.quote(t, safe=safe + "%")
    path = q(p.path, "/:@!$&'()*+,;=~-._") or "/"
    return urllib.parse.urlunsplit((p.scheme.lower(), p.netloc.lower(), path, q(p.query, "/?:@!$&'()*+,;=~-._[]|"), q(p.fragment, "/?:@!$&'()*+,;=~-._#[]|")))


def page_id(it):
    """페이지 hashId((url|title|eventDate)) 를 그대로: FNV-1a 32비트, 코드포인트 단위, 36진수 앞에 'i'"""
    if it.get("id"):
        return str(it["id"])
    s = f"{page_url(it.get('url'))}|{str(it.get('title') or '')[:200].strip()}|{it.get('eventDate') or ''}"
    h = 2166136261
    for ch in s:
        h = ((h ^ ord(ch)) * 16777619) & 0xFFFFFFFF
    d, out = "0123456789abcdefghijklmnopqrstuvwxyz", ""
    while True:
        h, r = divmod(h, 36); out = d[r] + out
        if not h: return "i" + out


def write_share_pages():
    """data/share/{id}.html: 소식마다 og 태그(제목·날짜·장소·대표 그림)를 담은 작은 페이지. 카톡·디스코드·X 에 링크를 붙이면 그 소식 사진과 제목이 미리보기로 뜨고,
    사람이 열면 보드의 #item={id} 로 바로 넘어간다(JS). 지금 소식(items.json + manual.json, 방송 제외)만 두고 나머지 파일은 지운다. 바뀐 파일만 쓴다."""
    os.makedirs(SHARE_DIR, exist_ok=True)
    keep, n_new = set(), 0
    esc = lambda t: html.escape(str(t or ""), quote=True)
    for it in load_json(os.path.join(DATA, "manual.json"), []) + load_json(OUT, []):
        if not isinstance(it, dict) or it.get("category") == "stream" or not it.get("title"):
            continue
        pid = page_id(it)
        if not re.fullmatch(r"[\w-]{1,20}", pid) or pid in keep:
            continue
        keep.add(pid)
        when = _kdate(it.get("eventDate") or "") if it.get("eventDate") else ""
        if when and it.get("endDate"):
            when += " ~ " + _kdate(it["endDate"], False)
        cat = CAT_KO.get(it.get("category"), "")
        head = " · ".join(x for x in (("📅 " + when) if when else "", ("📍 " + it["venue"]) if it.get("venue") else "", cat, it.get("source", "")) if x)
        body = it.get("summary_ko") or it.get("summary") or ""
        ko = it.get("title_ko") or ""
        desc = (head + (" — " + ko if ko else "") + (" | " + body if body else ""))[:200]
        img = it.get("image") if str(it.get("image") or "").startswith("https://") else SITE + "assets/og-lilly.png"
        go = f"../../#item={pid}"
        page = f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(it['title'])} · 마토메 보드</title>
<meta name="robots" content="noindex">
<meta property="og:type" content="article">
<meta property="og:site_name" content="마토메 보드">
<meta property="og:title" content="{esc(it['title'])}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:image" content="{esc(img)}">
<meta property="og:url" content="{SITE}data/share/{pid}.html">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{esc(it['title'])}">
<meta name="twitter:description" content="{esc(desc)}">
<meta name="twitter:image" content="{esc(img)}">
<link rel="canonical" href="{SITE}#item={pid}">
<script>location.replace("{go}")</script>
</head><body style="margin:0;padding:24px;font-family:sans-serif;background:#13152A;color:#ECEDF6">
<p><a href="{go}" style="color:#4FC3D9">마토메 보드에서 보기 →</a></p><h1 style="font-size:18px">{esc(it['title'])}</h1><p>{esc(desc)}</p>
</body></html>
"""
        path = os.path.join(SHARE_DIR, pid + ".html")
        try:
            if open(path, encoding="utf-8").read() == page:
                continue
        except OSError:
            pass
        with open(path, "w", encoding="utf-8") as f:
            f.write(page)
        n_new += 1
    gone = [f for f in os.listdir(SHARE_DIR) if f.endswith(".html") and f[:-5] not in keep]
    for f in gone:
        os.remove(os.path.join(SHARE_DIR, f))
    print(f"→ data/share/: 공유 페이지 {len(keep)}개 (새로 쓰거나 바뀜 {n_new}, 지움 {len(gone)})")


def write_calendars(ref):
    import hashlib
    items = [it for it in load_json(OUT, []) if it.get("category") != "stream" or it.get("region") == "KR"]
    utc = lambda d: d.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    day = lambda d: d.strftime("%Y%m%d")
    stamp = utc(ref)
    for fname, title, kinds in CALENDARS:
        L = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//matome-board//calendar//KO", "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
             f"X-WR-CALNAME:{_ics_text(title)}", "X-WR-TIMEZONE:Asia/Tokyo", "REFRESH-INTERVAL;VALUE=DURATION:PT6H", "X-PUBLISHED-TTL:PT6H"]
        n = 0
        for it in items:
            uid = hashlib.sha1(f"{it.get('url', '')}|{it.get('title', '')}|{it.get('eventDate', '')}".encode()).hexdigest()[:16]
            for k, d, e, label in ics_events(it, ref):
                if k not in kinds: continue
                allday = d.hour == 0 and d.minute == 0 and (not e or (e.hour == 0 and e.minute == 0))
                L += ["BEGIN:VEVENT", f"UID:{uid}-{k}@matome-board", f"DTSTAMP:{stamp}"]
                if allday:
                    L += [f"DTSTART;VALUE=DATE:{day(d)}", f"DTEND;VALUE=DATE:{day((e or d) + timedelta(days=1))}"]
                else:
                    L += [f"DTSTART:{utc(d)}", f"DTEND:{utc(e if e and e > d else d + timedelta(hours=2 if k == 'ev' else 0.5))}"]
                L.append("SUMMARY:" + _ics_text((f"[{label}] " if label else "") + it.get("title", "")))
                if it.get("venue"):
                    L.append("LOCATION:" + _ics_text(it["venue"] + (" " + it["address"] if it.get("address") and it["address"] not in it["venue"] else "")))
                desc = [x for x in (it.get("title_ko"), it.get("source"), it.get("url"), *(it.get("ticketUrls") or [])[:2]) if x]
                L.append("DESCRIPTION:" + _ics_text("\n".join(desc)))
                if it.get("url"): L.append("URL:" + it["url"])
                if k != "ev" and not allday:
                    L += ["BEGIN:VALARM", "ACTION:DISPLAY", "DESCRIPTION:" + _ics_text(label), "TRIGGER:-PT30M", "END:VALARM"]
                L.append("END:VEVENT"); n += 1
        L.append("END:VCALENDAR")
        with open(os.path.join(DATA, fname), "w", encoding="utf-8", newline="") as f:
            f.write("\r\n".join(_ics_fold(x) for x in L) + "\r\n")
        print(f"→ data/{fname}: 일정 {n}개")


ALERT_FAILS = 3   # 이만큼 연속 실패하면 이슈
ALERT_EMPTY = 8   # 피드가 이만큼 연속으로 비어 있으면(하루 4번이라 2일) 이슈
ALERT_TITLE = "[자동] 소식 출처 수집 이상"

def source_alert():
    """meta.json 의 출처 상태를 보고 오래 고장 난 출처가 있으면 GitHub 이슈를 열거나 고치고, 다 회복되면 닫는다(--alert, 워크플로 전용).
    이슈는 하나만 쓴다(제목으로 찾음). 문제 출처 목록이 바뀔 때만 댓글을 달아 알림이 너무 자주 가지 않게 한다. 실패해도 워크플로는 이어 간다."""
    call = gh_api()
    if not call: return
    alert_run(load_json(os.path.join(DATA, "meta.json"), {}).get("sources", []), call)
    broken_close(call)


def gh_api():
    """GitHub REST 호출 함수(워크플로가 주는 GITHUB_TOKEN·GITHUB_REPOSITORY). 없으면 None."""
    repo, tok = os.environ.get("GITHUB_REPOSITORY"), os.environ.get("GITHUB_TOKEN")
    if not repo or not tok:
        print("GitHub 알림: GITHUB_REPOSITORY/GITHUB_TOKEN 이 없어 건너뜀"); return None
    def call(method, path, body=None):
        req = urllib.request.Request(f"https://api.github.com/repos/{repo}{path}", method=method,
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json",
                                              "User-Agent": "matome-board", "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read() or b"null")
    return call


BROKEN_TITLE = "[자동] 수집기 고장 — 데이터 갱신 멈춤"

def _open_issue(call, title):
    return next((i for i in call("GET", "/issues?state=open&per_page=100") or []
                 if i.get("title") == title and "pull_request" not in i), None)


def broken_run(call, info, run_url):
    """소식 수집 단계가 실패했을 때(--alert-broken): 출처 절반 넘게 실패(BROKEN_FILE)거나 수집기가 오류로 멈춘 것.
    이슈를 하나 열고(이미 열려 있으면 댓글), 다음에 정상 실행되면 broken_close 가 닫는다."""
    if info:
        rows = "\n".join(f"| {x['n']} | `{(x.get('e') or '')[:120]}` |" for x in info.get("bad", [])[:30])
        body = (f"이번 실행({info.get('at')})에서 출처 {info.get('tried')}곳 중 **{len(info.get('bad', []))}곳**이 실패해서, "
                "출처 문제가 아니라 수집기 코드나 네트워크가 고장 난 것으로 보고 **데이터를 커밋하지 않았어요**(보드는 이전 소식 그대로).\n\n"
                "오류가 모두 같다면(예: `name '…' is not defined`) 최근 `collector.py` 변경을 의심해 주세요.\n\n"
                f"| 출처 | 오류 |\n|---|---|\n{rows}\n\n실행 기록: {run_url}\n\n다음 실행이 정상이면 자동으로 닫혀요.")
    else:
        body = ("소식 수집 단계가 오류로 멈춰서 **데이터를 커밋하지 않았어요**(보드는 이전 소식 그대로). "
                f"실행 기록의 「소식 수집」 단계 로그에서 Traceback 을 확인해 주세요.\n\n실행 기록: {run_url}\n\n다음 실행이 정상이면 자동으로 닫혀요.")
    cur = _open_issue(call, BROKEN_TITLE)
    if cur:
        call("POST", f"/issues/{cur['number']}/comments", {"body": "또 실패했어요.\n\n" + body})
        print(f"고장 알림: 이슈 #{cur['number']} 댓글")
    else:
        r = call("POST", "/issues", {"title": BROKEN_TITLE, "body": body})
        print(f"고장 알림: 이슈 #{(r or {}).get('number')} 열음")


def broken_close(call):
    cur = _open_issue(call, BROKEN_TITLE)
    if cur:
        call("POST", f"/issues/{cur['number']}/comments", {"body": "수집이 다시 정상으로 돌았어요. 이슈를 닫습니다."})
        call("PATCH", f"/issues/{cur['number']}", {"state": "closed"})
        print(f"고장 알림: 회복 → 이슈 #{cur['number']} 닫음")


def alert_run(sources, call):
    bad = [x for x in sources if isinstance(x, dict) and (
        (x.get("ok") is False and int(x.get("f", 0)) >= ALERT_FAILS) or (x.get("ok") is True and int(x.get("zr", 0)) >= ALERT_EMPTY))]
    names = sorted(x["n"] for x in bad)
    cur = _open_issue(call, ALERT_TITLE)
    old = set()
    if cur:
        m = re.search(r"<!-- bad:(.*?) -->", cur.get("body") or "")
        old = set(filter(None, (m.group(1) if m else "").split("|")))
    if not bad:
        if cur:
            call("POST", f"/issues/{cur['number']}/comments", {"body": "모든 출처가 다시 정상이에요. 이슈를 닫습니다."})
            call("PATCH", f"/issues/{cur['number']}", {"state": "closed"})
            print(f"출처 알림: 회복 → 이슈 #{cur['number']} 닫음")
        else:
            print("출처 알림: 문제 없음")
        return
    def line(x):
        if x.get("ok") is False:
            return f"| {x['n']} | {x.get('f')}회 연속 실패 | {x.get('at') or '기록 없음'} | `{(x.get('e') or '')[:120]}` |"
        return f"| {x['n']} | 피드가 {x.get('zr')}회 연속 비어 있음 | {x.get('at', '')} | 원본 0건 |"
    body = ("수집기가 이 출처들에서 소식을 못 가져오고 있어요. 사이트 주소나 RSS 구조가 바뀌었을 수 있으니 "
            "`collector.py` 의 `SOURCES` 를 고치고 Actions 의 **소스 점검**으로 확인해 주세요. 모두 회복되면 이 이슈는 자동으로 닫혀요.\n\n"
            "| 출처 | 상태 | 마지막 성공 | 오류 |\n|---|---|---|---|\n" + "\n".join(line(x) for x in bad) +
            f"\n\n기준: {ALERT_FAILS}회 연속 실패 또는 {ALERT_EMPTY}회(약 2일) 연속 빈 피드.\n<!-- bad:{'|'.join(names)} -->")
    if not cur:
        r = call("POST", "/issues", {"title": ALERT_TITLE, "body": body})
        print(f"출처 알림: 이슈 #{(r or {}).get('number')} 열음 ({', '.join(names)})"); return
    call("PATCH", f"/issues/{cur['number']}", {"body": body})
    if set(names) != old:
        add, fixed = sorted(set(names) - old), sorted(old - set(names))
        msg = " / ".join(t for t in ((f"새로 문제: {', '.join(add)}" if add else ""), (f"회복: {', '.join(fixed)}" if fixed else "")) if t)
        call("POST", f"/issues/{cur['number']}/comments", {"body": msg})
        print(f"출처 알림: 이슈 #{cur['number']} 갱신 ({msg})")
    else:
        print(f"출처 알림: 이슈 #{cur['number']} 그대로 ({', '.join(names)})")


WEEKLY = os.path.join(DATA, "weekly.json")
WEEKDAY_KO = "월화수목금토일"


def _kdate(v, with_time=True):
    """ISO → '11/3(화) 18:00' (00:00 이면 날짜만)"""
    try: d = datetime.fromisoformat(v if re.search(r"[+-]\d\d:\d\d$|Z$", v) else v + "+09:00").astimezone(JST)
    except Exception: return ""
    t = d.strftime("%H:%M")
    return f"{d.month}/{d.day}({WEEKDAY_KO[d.weekday()]})" + (f" {t}" if with_time and t != "00:00" else "")


def weekly_draft(ref):
    """지금 주간 요약의 기간(week 부터 7일)이 끝났으면 이번 주(월요일 시작) 자동 초안을 유행 순위로 쓴다.
    사람이나 Claude 가 쓴 요약(수요일 시작처럼 주 중간에 시작하는 것도)은 그 7일 동안 덮어쓰지 않는다. 설명은 유행 수치 + 대표 소식 원문 요약이고, auto=true 로 표시한다."""
    cur = load_json(WEEKLY, {})
    monday = (ref - timedelta(days=ref.weekday())).date()
    try: start = datetime.strptime(str(cur.get("week", ""))[:10], "%Y-%m-%d").date()
    except ValueError: start = None
    if start and start + timedelta(days=6) >= ref.date():
        print(f"주간 요약: 지금 것({start}~{start + timedelta(days=6)})이 아직 이번 기간 — 그대로 둠"); return
    items = load_json(OUT, [])
    tr = load_trends()
    ranked = [(n, c) for n, c in rank_works(tr.get("history", {})) if c >= TREND_MIN][:15]
    rise = {wkey(x["n"]): x for x in tr.get("rising", []) if isinstance(x, dict) and x.get("n")}
    sunday = monday + timedelta(days=6)
    week_end = datetime.combine(sunday, datetime.max.time(), JST)
    def when_key(it):
        try: s = datetime.fromisoformat((it.get("eventDate") or "") + ("" if re.search(r"[+-]\d\d:\d\d$", it.get("eventDate") or "") else "+09:00")) if it.get("eventDate") else None
        except Exception: s = None
        if s and ref - timedelta(days=1) <= s <= week_end: return (0, s.timestamp())          # 이번 주 일정
        if s and s > week_end and s <= ref + timedelta(days=21): return (1, s.timestamp())    # 3주 안 일정
        try: a = datetime.fromisoformat(it.get("addedAt", ""))
        except Exception: a = ref - timedelta(days=99)
        return (2, -a.timestamp())                                                             # 그 밖엔 새로 들어온 순
    picks = []
    for rank, (w, total) in enumerate(ranked, 1):
        k = wkey(w)
        rel = [it for it in items if any(wkey(x) == k for x in it.get("works", [])) or (len(k) >= 3 and wnorm(w) in wnorm(it.get("title", "")))]
        live = [it for it in rel if not (item_end(it) and item_end(it) < ref - timedelta(hours=12))]
        if not live: continue
        live.sort(key=when_key)
        main = live[0]
        whens = []
        if main.get("eventDate"):
            whens.append(_kdate(main["eventDate"]) + (f" ~ {_kdate(main['endDate'], False)}" if main.get("endDate") else ""))
        if main.get("ticketOpen") and main["ticketOpen"][:10] != (main.get("eventDate") or "")[:10]: whens.append("판매·추첨 " + _kdate(main["ticketOpen"]))
        if main.get("deadline"): whens.append("마감 " + _kdate(main["deadline"]))
        rs = rise.get(k)
        head = f"최근 14일 기사 {total}건으로 유행 {rank}위" + (f", 최근 {RISE_DAYS}일 {rs['r']}건으로 평소의 {rs['x']}배 급상승" if rs else "") + f". 보드에 지금 소식 {len(live)}건이 있어요."
        body = re.sub(r"\s*The post .*$", "", main.get("summary") or "").strip()  # 기계 번역은 어색해서 원문 요약을 쓴다(WordPress 꼬리 'The post …' 는 뗌)
        links, seen = [], set()
        for it in live:
            if it.get("url") and it["url"] not in seen and len(links) < 3:
                seen.add(it["url"]); links.append({"label": f"{it.get('source') or '원문'}: {(it.get('title_ko') or it.get('title', ''))[:40]}", "url": it["url"]})
        picks.append({"title": (main.get("title") or "")[:120], "works": [w], "category": main.get("category", "other"),
                      "tag": f"유행 {rank}위" + (" · 급상승" if rs else ""), "when": " · ".join(x for x in whens if x)[:200],
                      "where": (main.get("venue") or "")[:160], "desc": (head + (" 대표 소식: " + body[:240] if body else ""))[:1500],
                      "links": links, "items": [it["url"] for it in live[:6] if it.get("url")]})
        if len(picks) >= 8: break
    if not picks:
        print("주간 요약: 초안을 만들 소식이 없음"); return
    out = {"week": monday.isoformat(), "range": f"{monday.month}/{monday.day}(월) ~ {sunday.month}/{sunday.day}(일)",
           "title": "이번 주 요약 · 자동 정리", "updated": ref.date().isoformat(), "auto": True, "picks": picks}
    save_json(WEEKLY, out)
    print(f"주간 요약: {monday} 주 자동 초안 {len(picks)}건 → data/weekly.json")


TRANSLATE_MAX = 150  # 한 번 실행에서 한국어로 번역할 최대 소식 수(제목+요약, 소식당 요청 2번)
JA_RE = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff]")  # 가나·한자가 있으면 일본어 글


def _gtx(text):
    """Google 번역(키 없는 gtx 엔드포인트) 응답의 문장 조각 [(한국어, 일본어)]. 실패하면 예외."""
    q = urllib.parse.urlencode({"client": "gtx", "sl": "ja", "tl": "ko", "dt": "t", "q": text})
    data = json.loads(fetch("https://translate.googleapis.com/translate_a/single?" + q,
                            {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"}))
    return [(seg[0] or "", seg[1] or "") for seg in (data[0] or []) if seg and isinstance(seg[0], str) and len(seg) > 1]


SPLIT_RE = re.compile(r"(?<=[…!?！？☆★♪。　])(?![…!?！？☆★♪。　])")  # 이어진 부호(…!?)는 한 덩어리로


def translate_ja_ko(text, deep=True):
    """일본어 → 한국어. 구글이 한 조각 안에서 뒷부분을 통째로 빠뜨리는 일이 있어서(2026-10: 「ゴジラの表皮を履いたら…!?「ゴジラ-0.0」×…」 47자 → '고질라의 표피를 신으면…'),
    번역이 원문 조각의 절반도 안 되면 그 조각을 문장부호(…!?☆♪ 등) 뒤에서 나눠 따로 번역해 잇는다."""
    out = []
    for ko, ja in _gtx(text):
        if deep and len(ja) >= 12 and len(ko.strip()) < .5 * len(ja.strip()):
            parts = [p for p in SPLIT_RE.split(ja) if p.strip()]
            if len(parts) > 1:
                ko = " ".join(translate_ja_ko(p, False) for p in parts) + " "
        out.append(ko)
    return re.sub(r" {2,}", " ", "".join(out)).strip()


def ko_short(it):
    """예전 번역 제목이 원문의 절반도 안 되면(뒷부분이 빠진 번역) True"""
    t, k = it.get("title", ""), it.get("title_ko", "")
    return bool(k) and len(t) >= 20 and len(k) < .5 * len(t)


def _gloss():
    """번역 용어집: works.json 의 ko(대표 이름 → 한국어 이름)·terms(캐릭터·멤버 이름)와, 대표 이름 이상으로 긴 별칭(ウマ娘 プリティーダービー 등).
    짧은 별칭(ガンダム·ポケモン)은 기계 번역(건담·포켓몬)이 더 자연스러워서 넣지 않는다. 전각·반각 표기를 둘 다 둔다."""
    ko = {str(k): str(v) for k, v in (_works.get("ko") or {}).items() if v}
    g = {**{str(k): str(v) for k, v in (_works.get("terms") or {}).items() if v}, **ko}  # terms: 캐릭터·멤버 이름(猫猫 → 마오마오)
    for a, c in (_works.get("alias") or {}).items():
        if c in ko and len(a) >= len(c): g.setdefault(a, ko[c])
    out = {}
    full = str.maketrans("!?:&", "！？：＆")
    for k, v in g.items():
        for f in {k, unicodedata.normalize("NFKC", k), unicodedata.normalize("NFKC", k).translate(full)}:
            if len(f) >= 2: out.setdefault(f, v)
    return sorted(out.items(), key=lambda kv: -len(kv[0]))
GLOSS = _gloss()
GLOSS_VER = format(sum(ord(c) * (i + 1) for i, c in enumerate(json.dumps(GLOSS, ensure_ascii=False))) % 99991, "x")


def gloss_pre(text):
    """번역 전에 작품 이름을 한국어 이름으로 바꿔 둔다(구글 번역은 한글을 그대로 둔다) → 「薬屋のひとりごと」가 매번 다르게 옮겨지지 않음"""
    for ja, ko in GLOSS:
        if ja in text: text = text.replace(ja, ko)
    return text


GLOSS_SP = {ko: re.compile(r"\s*".join(re.escape(c) for c in re.sub(r"\s", "", ko))) for _, ko in GLOSS}


def gloss_fix(it):
    """구글 번역이 미리 넣은 한국어 이름도 띄어 쓴다(홀로라이브 → 홀로 라이브). 원문에 그 작품이 있으면 띄어쓰기만 다른 표기를 용어집 표기로 되돌린다."""
    src = it.get("title", "") + "\n" + it.get("summary", "")
    for ja, ko in GLOSS:
        if ja in src:
            for k in ("title_ko", "summary_ko"):
                if it.get(k): it[k] = GLOSS_SP[ko].sub(ko, it[k])


def gloss_miss(it):
    """용어집 작품 이름이 원문에 있는데 번역문에 한국어 이름이 없으면 True(예전 번역 다시 하기). 띄어쓰기는 무시."""
    if it.get("tg") == GLOSS_VER: return False
    src, ko = it.get("title", "") + "\n" + it.get("summary", ""), re.sub(r"\s", "", it.get("title_ko", "") + it.get("summary_ko", ""))
    return any(ja in src and re.sub(r"\s", "", k) not in ko for ja, k in GLOSS)


def translate_items(items):
    """아직 번역하지 않은 소식의 제목·요약을 한국어로 번역해 title_ko / summary_ko 에 넣는다.
    작품 이름은 용어집(GLOSS, works.json 의 ko)대로 미리 바꿔 넣고, 예전 번역에 한국어 이름이 빠졌으면 한 번 다시 번역한다(tg=용어집 버전).
    일본어가 없는 글은 빈 문자열(원문 그대로 표시). 번역이 실패하면 그 자리에서 멈추고 다음 실행에 다시 시도한다(키를 안 남김)."""
    done = 0
    for it in items:
        if "title_ko" in it and not gloss_miss(it) and not (it.get("tg") != GLOSS_VER and ko_short(it)):
            gloss_fix(it); continue
        if done >= TRANSLATE_MAX:
            break
        try:
            if JA_RE.search(it.get("title", "")):
                tko = translate_ja_ko(gloss_pre(it["title"]))[:200]
                time.sleep(0.2)
                sko = translate_ja_ko(gloss_pre(it["summary"]))[:400] if it.get("summary") and JA_RE.search(it["summary"]) else ""
                time.sleep(0.2)
                it["title_ko"], it["summary_ko"] = tko, sko
                gloss_fix(it)
                it["tg"] = GLOSS_VER  # 지금 방식(용어집·잘림 보정)으로 번역함 → 다시 하지 않는다
            else:
                it["title_ko"], it["summary_ko"] = "", ""
            done += 1
        except Exception as e:
            print(f"번역 중단: {e} (다음 실행에서 다시 시도)", file=sys.stderr)
            break
    if done:
        print(f"번역: {done}건")


ENRICH_MAX = 120  # 한 번 실행에서 기사 페이지를 열어 볼 최대 건수(썸네일·티켓 링크 보강)
LINK_RE = re.compile(r"https?://[^\s\"'<>()]+")


def og_from_html(page, base):
    """HTML 의 og:image / twitter:image 절대 주소. 없으면 ""."""
    for prop in ("og:image", "twitter:image"):
        for tag in re.findall(r"<meta[^>]+>", page, flags=re.I):
            if re.search(r"(property|name)=[\"']" + re.escape(prop) + r"[\"']", tag, re.I):
                m = re.search(r"content=[\"']([^\"']+)", tag, re.I)
                if m:
                    return urllib.parse.urljoin(base, html.unescape(m.group(1)))
    return ""


def ticket_links_in(page, exclude=()):
    """페이지 안의 티켓 사이트 링크를 사이트별로 하나씩(e+, ローチケ, ぴあ …). 기사 본문(<article>/<main>) 안에 하나라도 있으면 거기서만, 없으면 전체에서.
    사이트 첫 화면으로 가는 링크(경로 없음), 이미지·스크립트 주소, exclude(사이트 공통 배너)는 제외."""
    regions = re.findall(r"<article[\s>].*?</article>", page, re.S | re.I) or re.findall(r"<main[\s>].*?</main>", page, re.S | re.I)
    for text in [" ".join(regions), page]:
        cands = []
        for u in LINK_RE.findall(html.unescape(text)):
            u = u.rstrip(".,、。")
            p = urllib.parse.urlparse(u)
            if ticket_site(u) and p.path.strip("/") and u not in exclude and not re.search(r"\.(png|jpe?g|gif|svg|css|js)$", p.path, re.I):
                cands.append(u)
        if cands:
            return ticket_urls(cands)
    return []


_site_links = {}


def site_ticket_links(url):
    """기사가 실린 사이트 첫 화면에 걸려 있는 티켓 링크 모음(헤더·사이드바 배너). 기사에서 찾은 링크가 여기 있으면 기사 것이 아니다."""
    host = urllib.parse.urlparse(url).hostname or ""
    if host not in _site_links:
        try:
            page = html.unescape(fetch(f"https://{host}/").decode("utf-8", "replace"))
            _site_links[host] = {u.rstrip(".,、。") for u in LINK_RE.findall(page) if any(d in (urllib.parse.urlparse(u).hostname or "") for d in TICKET_DOMAINS)}
        except Exception:
            _site_links[host] = set()
    return _site_links[host]


def page_text(page):
    """기사 본문(<article>/<main>, 없으면 <body>)의 글자만. 티켓 단계(find_phases)용."""
    m = re.search(r"<article[\s>].*?</article>", page, re.S | re.I) or re.search(r"<main[\s>].*?</main>", page, re.S | re.I) \
        or re.search(r"<body[\s>].*?</body>", page, re.S | re.I)
    t = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", m.group(0) if m else page, flags=re.S | re.I)
    t = re.sub(r"<br\s*/?>|</(p|div|li|tr|h\d)>", "\n", t, flags=re.I)
    return html.unescape(re.sub(r"[ \t\u3000]+", " ", re.sub(r"<[^>]+>", " ", t)))[:20000]


def page_info(url, ref=None):
    """기사 페이지를 한 번 열어 (og:image, 티켓 링크 목록, 티켓 단계)를 돌려준다. 실패하면 ("", [], [])."""
    try:
        page = fetch(url).decode("utf-8", "replace")
    except Exception:
        return "", [], []
    return og_from_html(page, url), ticket_links_in(page, site_ticket_links(url)), (find_phases(page_text(page), ref) if ref else [])


def enrich(items, ref=None):
    """소식마다 기사 페이지를 한 번 열어 빠진 썸네일(og:image)과 티켓 링크(ticketUrls, 사이트별 하나씩), 티켓 단계(phases, 피드 요약에 없던 것)를 채운다.
    한 번 연 소식은 "scanned": true 로 표시해 다시 열지 않는다. 새 소식부터 차례로 ENRICH_MAX 건까지."""
    tried = imgs = phs = 0
    ref = ref or datetime.now(JST)
    found = []  # (항목, 링크): 같은 출처에서 같은 링크가 여러 기사에 나오면 사이트 공통 배너로 보고 버린다
    for it in items:
        if it.get("scanned") or not it.get("url"):
            continue
        if it.get("platform") in ("holodex", "youtube") or it.get("region") == "KR" or "news.google.com/" in it.get("url", ""):  # 방송 항목은 열어 볼 게 없고, 한국 기사(Google 뉴스 링크)는 열면 이동 페이지라 소용없다
            it["scanned"] = True
            continue
        if tried >= ENRICH_MAX:
            break
        tried += 1
        img, tks_found, phases = page_info(it["url"], ref)
        it["scanned"] = True
        if not it.get("image"):
            it["image"] = img
            imgs += bool(img)
        if it.get("category") in PHASE_CATS and len(phases) > len(it.get("phases") or []):  # 기사 본문이 피드 요약보다 단계를 더 안다
            it["phases"] = phases; phs += 1
            it["ticketOpen"] = it.get("ticketOpen") or next((p["s"] for p in phases if p["s"]), "")
            it["deadline"] = it.get("deadline") or next((p["e"] for p in phases if p.get("e")), "")
        for tk in tks_found:
            found.append((it, tk))
    dup = {}
    for it, tk in found:
        dup[(it.get("source"), tk)] = dup.get((it.get("source"), tk), 0) + 1
    tks = 0
    for it, tk in found:
        if dup[(it.get("source"), tk)] >= 3:
            continue
        have = it.get("ticketUrls") or ([it["ticketUrl"]] if it.get("ticketUrl") else [])
        if ticket_site(tk) in {ticket_site(u) for u in have}:
            continue  # 그 사이트 링크는 이미 있다
        have.append(tk)
        it["ticketUrls"] = have
        it["ticketUrl"] = have[0]
        tks += 1
    # 2026-10 티켓 단계를 넣기 전에 이미 연 공연·공식 행사 소식은 단계를 찾으러 한 번 더 연다(실행당 PHASE_RESCAN_MAX 건, ps 로 표시해 되풀이하지 않음)
    re_n = 0
    for it in items:
        if re_n >= PHASE_RESCAN_MAX: break
        if it.get("ps") or it.get("phases") or not it.get("scanned") or it.get("category") not in ("live", "official") or not it.get("url") or item_end(it) and item_end(it) < ref:
            continue
        re_n += 1; it["ps"] = True
        try:
            phases = find_phases(page_text(fetch(it["url"]).decode("utf-8", "replace")), ref)
        except Exception:
            continue
        if phases:
            it["phases"] = phases; phs += 1
            it["ticketOpen"] = it.get("ticketOpen") or next((p["s"] for p in phases if p["s"]), "")
            it["deadline"] = it.get("deadline") or next((p["e"] for p in phases if p.get("e")), "")
    if tried or re_n:
        print(f"기사 보강: {tried}건 열어 썸네일 {imgs}건, 티켓 링크 {tks}건, 티켓 단계 {phs}건 채움(단계 재확인 {re_n}건)")


def og_image(site):
    """작품 공식 사이트(소개 페이지) 첫 화면의 og:image = 키 비주얼."""
    if not site:
        return ""
    try:
        page = fetch(site).decode("utf-8", "replace")
    except Exception:
        return ""
    return og_from_html(page, site)


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


ANILIST_Q = """query($page:Int,$status:MediaStatus,$startBefore:FuzzyDateInt,$startAfter:FuzzyDateInt){
  Page(page:$page,perPage:50){pageInfo{hasNextPage}
    media(type:ANIME,status:$status,startDate_lesser:$startBefore,startDate_greater:$startAfter,countryOfOrigin:"JP",format_in:[TV,TV_SHORT,ONA],isAdult:false,sort:POPULARITY_DESC){
      title{native romaji} format status isAdult episodes startDate{year month day} popularity coverImage{large}
      trailer{id site} externalLinks{url site type} nextAiringEpisode{airingAt episode}}}}"""


def anilist_skip(m):
    """목록에서 뺄 작품: 성인물, 그리고 TV 방송도 스트리밍 링크도 공식 사이트도 없는 단편·티저(볼 곳이 없는 것)."""
    if m.get("isAdult"):
        return "성인물"
    links = [l for l in (m.get("externalLinks") or []) if isinstance(l, dict)]
    has_stream = any(l.get("type") == "STREAMING" for l in links)
    has_info = any(l.get("type") == "INFO" for l in links)
    if m.get("format") == "ONA" and not (m.get("nextAiringEpisode") or {}).get("airingAt") and not has_stream and not has_info:
        return "볼 곳 없음"
    if (m.get("episodes") or 0) <= 3 and re.search(r"PV|ティザー|予告|CM\b|MV|プロモーション", (m.get("title") or {}).get("native") or ""):
        return "티저·PV"  # 화수가 적거나 미정인데 제목이 예고 영상이면 작품이 아니다
    return ""


def anilist_start(m):
    """startDate → date. 월이 없으면 None(날짜 미정으로 본다)."""
    sd = m.get("startDate") or {}
    if not (sd.get("year") and sd.get("month")):
        return None
    try:
        return datetime(sd["year"], sd["month"], sd.get("day") or 1, tzinfo=JST)
    except ValueError:
        return None


def anilist(variables, pages=1):
    """AniList 공개 GraphQL API(키 불필요). 페이지마다 50편."""
    out = []
    for page in range(1, pages + 1):
        body = json.dumps({"query": ANILIST_Q, "variables": {**variables, "page": page}}).encode()
        data = json.loads(fetch("https://graphql.anilist.co", {"Content-Type": "application/json", "Accept": "application/json"}, body))
        pg = (data.get("data") or {}).get("Page") or {}
        out += pg.get("media") or []
        if not (pg.get("pageInfo") or {}).get("hasNextPage"):
            break
        time.sleep(0.7)  # 분당 90회 제한
    return out


def anilist_entry(m, old):
    """AniList 작품 하나 → anime.json 항목. 방송국(st)처럼 AniList에 없는 값은 기존 항목에서 이어받는다."""
    t = (m.get("title") or {}).get("native") or (m.get("title") or {}).get("romaji") or ""
    a = {"t": t, "d": old.get("d", 8), "tm": old.get("tm", ""), "st": old.get("st", ""), "s": old.get("s", ""), "r": None,
         "pv": old.get("pv", ""), "site": old.get("site", ""), "x": old.get("x", ""), "w": m.get("popularity")}
    nae = m.get("nextAiringEpisode") or {}
    ona = m.get("format") == "ONA"  # TV 방송 없이 넷플릭스 등 스트리밍으로만 나오는 작품 → '스트리밍' 칸(d=7)
    if nae.get("airingAt"):
        dt = datetime.fromtimestamp(nae["airingAt"], JST)
        h, d = dt.hour, (dt.weekday() + 1) % 7  # 0=일
        if h < 5:  # 심야 방송은 전날 25:30 식으로
            h, d = h + 24, (d - 1) % 7
        a["tm"] = f"{h:02d}:{dt.minute:02d}"
        # AniList 의 ONA 에는 TV 심야 편성(22:00~28:59)에 맞춰 나오는 작품도 섞여 있다. 그런 건 TV 방송작으로 보고 요일 칸에 둔다.
        # 넷플릭스류 글로벌 공개는 보통 16~17시라 스트리밍 칸에 남는다.
        if ona and not (22 <= h < 29):
            a["d"], a["rd"] = 7, d  # rd: 매주 공개되는 요일
        else:
            a["d"] = d
            a.pop("rd", None)
    elif ona:
        a["d"] = 7
        a.pop("rd", None)
    sd = m.get("startDate") or {}
    if sd.get("year") and sd.get("month"):
        a["s"] = f"{sd['year']}-{sd['month']:02d}-{sd.get('day') or 1:02d}"
    tr = m.get("trailer") or {}
    if tr.get("site") == "youtube" and tr.get("id"):
        a["pv"] = f"https://www.youtube.com/watch?v={tr['id']}"
    links = [l for l in (m.get("externalLinks") or []) if isinstance(l, dict) and l.get("url")]
    official = next((l["url"] for l in links if l.get("type") == "INFO" and "official" in (l.get("site") or "").lower()), "") \
        or next((l["url"] for l in links if l.get("type") == "INFO"), "")
    if official:
        a["site"] = official
    tw = next((l["url"] for l in links if (l.get("site") or "").lower() in ("twitter", "x")), "")
    if tw:
        a["x"] = tw.rstrip("/").split("/")[-1]
    return a, (m.get("coverImage") or {}).get("large") or ""


def export_anime(ref):
    """방영 목록 갱신 + 썸네일.
    - AniList(키 불필요)에서 지금 방영 중(RELEASING)인 일본 TV·ONA 작품 전부와 이번 시즌에 시작 예정인 작품을 받아 목록을 새로 만든다.
      요일·시각은 다음 화 방영 시각(JST)에서 계산하고, 방송국처럼 AniList에 없는 값은 기존 항목에서 이어받는다.
    - ANNICT_TOKEN이 있으면 Annict 정보(공식 사이트·X·시청자 수)를 덧붙인다.
    - 썸네일은 ① AniList 표지 ② 공식 사이트 og:image ③ 공식 PV(YouTube) 대표 이미지 순서로 찾는다."""
    path = os.path.join(DATA, "anime.json")
    doc = load_json(path, {"season": "", "name": "", "src": "", "list": []})
    m = ref.month
    season = f"{ref.year}-" + ("winter" if m <= 3 else "spring" if m <= 6 else "summer" if m <= 9 else "autumn")
    names = {"winter": "겨울", "spring": "봄", "summer": "여름", "autumn": "가을"}
    if doc.get("season") != season:  # 시즌이 바뀌면 새 목록으로
        doc = {"season": season, "name": f"{ref.year}년 {names[season.split('-')[1]]} 애니", "src": "Annict", "list": []}
    by = {tkey(a["t"]): a for a in doc["list"]}
    extra = {}  # title -> 표지 이미지
    try:
        # ① 방영 중 전부 ② 앞으로 75일 안에 시작하는 예정작(시즌 분류가 어긋난 작품도 날짜로 잡는다)
        # ③ 최근 30일 안에 시작해 이미 '완결'인 작품(넷플릭스처럼 전편을 한 번에 공개한 것은 AniList 에서 바로 FINISHED 가 된다)
        lo, hi = ref - timedelta(days=30), ref + timedelta(days=75)
        media = anilist({"status": "RELEASING"}, pages=5) \
            + anilist({"status": "NOT_YET_RELEASED", "startBefore": int(hi.strftime("%Y%m%d"))}, pages=2) \
            + anilist({"status": "FINISHED", "startAfter": int(lo.strftime("%Y%m%d"))}, pages=1)
        fresh, seen, skipped = {}, set(), {}
        for m in media:
            why = anilist_skip(m)
            if not why and m.get("status") != "RELEASING":
                sd = anilist_start(m)
                if not sd or not (lo <= sd <= hi):
                    why = "기간 밖·날짜 미정"
            if why:
                skipped[why] = skipped.get(why, 0) + 1
                continue
            a, cover = anilist_entry(m, by.get(tkey((m.get("title") or {}).get("native") or (m.get("title") or {}).get("romaji") or ""), {}))
            k = tkey(a["t"])
            if not a["t"] or k in seen:
                continue
            seen.add(k); fresh[k] = a
            if cover:
                extra[a["t"]] = cover
        if fresh:
            by = fresh  # AniList 결과로 목록을 새로 만든다(방영이 끝난 작품은 자연히 빠진다)
            for i, a in enumerate(sorted(by.values(), key=lambda a: -(a.get("w") or 0)), 1):
                a["r"] = i if a.get("w") else None
            doc["src"] = f"AniList 방영 정보 ({ref.month}/{ref.day} 기준)"
            print(f"AniList: 방영 중·예정 {len(fresh)}편" + (f", 제외 {skipped}" if skipped else ""))
    except Exception as e:
        print(f"AniList 실패: {e} (기존 목록 유지)", file=sys.stderr)
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
    doc["list"] = list(by.values())
    save_json(path, doc)
    thumbs = load_json(os.path.join(DATA, "thumbs.json"), {})
    got = 0
    for a in doc["list"][:300]:
        t = a["t"]
        if t in thumbs and os.path.exists(os.path.join(ROOT, thumbs[t])):
            continue
        cands = [lambda: extra.get(t, ""), lambda: og_image(a.get("site", ""))]  # 표지 → 공식 사이트 og:image → PV (필요할 때만 연다)
        pv = re.search(r"[?&]v=([\w-]{11})", a.get("pv", "") or "")
        if pv:
            cands.append(lambda pv=pv: f"https://i.ytimg.com/vi/{pv.group(1)}/hqdefault.jpg")
        for get in cands:
            u = get()
            if u and save_thumb(t, u, thumbs):
                got += 1
                break
    save_json(os.path.join(DATA, "thumbs.json"), thumbs)
    print(f"→ data/anime.json {len(doc['list'])}편, 썸네일 새로 {got}개 (전체 {len(thumbs)}개)")


# ── 연재 만화(만갤 탭): 운영자가 지정한 디시 만화갤러리 연재작만 1화부터 색인 ─────────────────
# 그림은 저장하지 않고 원문 글 번호와 제목만 모은다. 작품 목록은 data/comics_follow.json(사람이 고침).
# 회차는 지정한 글의 [시리즈] 상자(dc_series)와 '링크 모음' 글, 개념글, 제목 검색에서 찾는다.
DC_GALL = "comic_new6"
DC_PAGES = 5          # 새 화를 찾으려 읽을 개념글 목록 쪽수(쪽당 약 25건)
DC_POST_MAX = 40      # 한 번 실행에서 새로 열어 볼 글 수
DC_FOLLOW_SEARCH = 60 # 작품마다 새 화를 찾으려 읽을 검색 블록 수 상한(처음 한 번만 많이 읽는다)
DC_SEARCH_SLACK = 60000  # 검색 블록 위치(s_pos)는 삭제된 글을 빼고 세어 글 번호보다 작다. floor 아래로 이만큼 더 읽어 빈틈을 막는다
DC_UA = {"User-Agent": "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36",
         "Accept-Language": "ko", "Referer": "https://m.dcinside.com/"}
COMICS = os.path.join(DATA, "comics.json")
COMICS_FOLLOW = os.path.join(DATA, "comics_follow.json")
EP_RE = re.compile(r"(\d+(?:[-~]\d+)?)\s*화|第\s*\d+\s*話|\b(?:ep|EP|Ep)\.?\s*\d+|#\d+|(?:^|\s)\d{1,4}(?:\s*,\s*\d{1,4})*\s*$")
EP_NUM_RE = re.compile(r"(\d{1,4})\s*화?\s*(?:[\(\[（【][^)\]）】]*[\)\]）】]\s*)?$")  # 제목 끝의 회차 번호
LINKS_RE = re.compile(r"링크\s*모음")  # 회차 링크만 모아 둔 글. 열어서 그 안의 상자·본문 링크를 회차로 쓴다
TRANS_RE = re.compile(r"^\s*(번역|재업|재번역)\s*\)")  # 새 화로 받는 글의 말머리('방본만)' 같은 감상·추천 글은 거른다)
# 연재작 제목을 달고 엉뚱한 그림(니세코이 짤)을 올리는 낚시글. 대표 이미지의 dHash(9×8 흑백, 64비트)가 가까우면 회차에 넣지 않는다.
# 새 낚시 그림은 data/blocklist.json 의 "comic_images" 에 16진수 해시를 더한다.
BAIT_HASHES = ["fce6666664b033d1"]
BAIT_DIST = 10
DC_LINK_RE = re.compile(r'<a\s[^>]*?href="(?:https?:)?//(?:m\.dcinside\.com/board/(\w+)/(\d+)|gall\.dcinside\.com/(?:mgallery/)?board/view/?\?id=(\w+)(?:&amp;|&)no=(\d+))[^"]*"[^>]*>(.*?)</a>', re.S)

def dc_fetch(url):
    b = fetch(url, DC_UA)
    return b.decode("utf-8", "replace")


def dc_allowed():
    """robots.txt 의 'User-agent: *' 묶음이 /board/ 를 막고 있으면 수집하지 않는다."""
    try:
        txt = dc_fetch("https://m.dcinside.com/robots.txt")
    except Exception as e:
        print(f"연재 만화: robots.txt 를 못 읽음({e}) → 건너뜀", file=sys.stderr)
        return False
    agents, rules, groups = [], [], []
    for line in txt.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        k, v = [x.strip() for x in line.split(":", 1)]
        if k.lower() == "user-agent":
            if rules:
                groups.append((agents, rules)); agents, rules = [], []
            agents.append(v)
        elif k.lower() in ("allow", "disallow"):
            rules.append((k.lower(), v))
    groups.append((agents, rules))
    star = [r for a, r in groups if "*" in a]
    for rules in star:
        best = max(((len(v), kind) for kind, v in rules if v and "/board/comic_new6".startswith(v)), default=None)
        if best and best[1] == "disallow":
            print("연재 만화: robots.txt 가 /board/ 수집을 막음 → 건너뜀", file=sys.stderr)
            return False
    return True


def span_text(t, start):
    """start 위치의 <span ...> 안쪽 글자(안에 든 <span> 강조 표시까지 포함해 짝을 맞춰 자른다)"""
    depth = 0
    for m in re.compile(r"<(/?)span\b[^>]*>", re.I).finditer(t, start):
        depth += -1 if m.group(1) else 1
        if depth == 0:
            return re.sub(r"\s+", " ", clean(t[t.find(">", start) + 1:m.start()]))
    return ""


def dc_rows(t, g=DC_GALL):
    """목록·검색 결과 페이지 → [{no, title, nick, uid, views, rec}]. 미니 갤러리(/mini/{g}/)도 같은 틀이다"""
    out = []
    for li in t.split('<div class="gall-detail-lnktb">')[1:]:  # 항목마다 이 div 로 시작한다(안쪽 <li> 때문에 </li> 로는 못 자른다)
        li = li[:6000]
        m = re.search(rf"/(?:board|mini)/{g}/(\d+)", li)
        i = li.find('<span class="subjectin"')
        if not m or i < 0:
            continue
        nick = re.search(r'<li class="list-nick">(.*?)<', li, re.S)
        uid = re.search(r'data-info="([^"]*)"', li)
        num = lambda pat: int((re.search(pat, li) or [0, "0"])[1] or 0)
        out.append({"no": int(m.group(1)), "title": span_text(li, i), "nick": clean(nick.group(1)) if nick else "",
                    "uid": uid.group(1) if uid else "", "views": num(r"조회 (\d+)"), "rec": num(r"추천 <span>(\d+)")})
    return out


def dc_list(page):
    """개념글 목록 한 쪽"""
    return dc_rows(dc_fetch(f"https://m.dcinside.com/board/{DC_GALL}?recommend=1&page={page}"))


def dc_search(q, blocks, budget, floor=0):
    """제목 검색. 첫 결과는 최근 글 1만 건 범위이고 '다음 검색'으로 더 오래된 범위를 읽는다. budget=[남은 블록 수].
    floor 를 주면 그 글 번호 아래 범위로는 내려가지 않는다(다 읽었으면 budget 이 남는다)."""
    u, rows = f"https://m.dcinside.com/board/{DC_GALL}?s_type=subject_m&serval={urllib.parse.quote(q)}", []
    for _ in range(blocks):
        if budget[0] <= 0:
            break
        budget[0] -= 1
        try:
            t = dc_fetch(u)
        except Exception as e:
            print(f"연재 만화: 검색 '{q}' 실패 ({e})", file=sys.stderr); break
        time.sleep(1)
        rows += dc_rows(t)
        nxt = re.search(r'href="([^"]*s_pos=-?(\d+)[^"]*)"[^>]*class="next"', t)
        if not nxt or int(nxt.group(2)) < floor - DC_SEARCH_SLACK:
            return rows
        u = urllib.parse.urljoin("https://m.dcinside.com/", html.unescape(nxt.group(1)))
    budget[0] = min(budget[0], -1) if floor else budget[0]  # floor 까지 못 내려감
    return rows


def dc_links(seg):
    """HTML 조각 안의 디시 글 링크 → [(갤러리, 글번호, 링크 글자)]"""
    return [(m.group(1) or m.group(3), int(m.group(2) or m.group(4)), clean(m.group(5)).lstrip("·").strip())
            for m in DC_LINK_RE.finditer(seg)]


def dc_post(no, g=DC_GALL):
    """글 하나 → (시리즈 이름, [(갤러리, 글번호, 제목)], 게시 시각, 대표 이미지)"""
    return parse_post(dc_fetch(f"https://m.dcinside.com/board/{g}/{no}"))


def parse_post(t):
    name, eps = "", []
    i = t.find('class="dc_series"')
    h = re.compile(r"\[시리즈\]\s*(.*?)\s*</div>", re.S).search(t, i, i + 3000) if i >= 0 else None
    if h:  # 상자 = 굵은 제목 div 다음에 링크가 <br> 로 이어지다 </div> 로 닫힌다
        name = clean(h.group(1))
        end = t.find("</div>", h.end())
        eps = dc_links(t[h.end():end if end > 0 else h.end() + 100000])
    when = re.search(r'"datePublished":"([^"]+)"', t)
    og = re.search(r'<meta property="og:image" content="([^"]+)"', t)
    return name, eps, (when.group(1) if when else ""), (html.unescape(og.group(1)) if og else "")


def read_series(g, no, depth=1):
    """글 하나를 열어 회차 목록을 만든다 → ([(갤러리, 글번호, 제목)], 게시 시각, 대표 이미지).
    [시리즈] 상자의 회차를 순서대로 쓰고, 상자 안 '링크 모음' 글은 열어서 그 회차로 바꿔 끼운다(depth 단계까지).
    링크 모음 글이면 상자(50개까지만 보임) 밖 본문 링크 중 같은 작품 이름인 것도 읽는다."""
    t = dc_fetch(f"https://m.dcinside.com/board/{g}/{no}")
    time.sleep(1)
    _, box, when, cover = parse_post(t)
    out = []
    for e in box:
        if not LINKS_RE.search(e[2]):
            out.append(e)
        elif depth > 0:
            try:
                out += read_series(e[0], e[1], depth - 1)[0]
            except Exception as ex:
                print(f"연재 만화: 링크 모음 {e[0]}/{e[1]} 실패 ({ex})", file=sys.stderr)
    head = re.search(r'"headline":"([^"]*)"', t)
    if head and LINKS_RE.search(head.group(1)):  # 보통 글의 본문·옆 목록 링크는 낚시글이 섞일 수 있어 읽지 않는다
        bases = {series_base(x[2]) for x in out if ep_num(x[2])}
        seen = {(x[0], x[1]) for x in out}
        out += [e for e in dc_links(t) if series_base(e[2]) in bases and (e[0], e[1]) not in seen and not seen.add((e[0], e[1]))]
    return out, when, cover


def expand_box(box):
    """상자 회차 중 '링크 모음' 글을 열어 그 회차로 바꿔 끼운다."""
    out = []
    for e in box:
        if not LINKS_RE.search(e[2]):
            out.append(e); continue
        try:
            out += read_series(e[0], e[1], 0)[0]
        except Exception as ex:
            print(f"연재 만화: 링크 모음 {e[0]}/{e[1]} 실패 ({ex})", file=sys.stderr)
    return out


def img_hash(url):
    """대표 이미지의 dHash(16진수). Pillow 가 없거나 못 받으면 None"""
    if not url.startswith("http"):
        return None
    try:
        from PIL import Image
        import io
        im = Image.open(io.BytesIO(fetch(url, DC_UA))).convert("L").resize((9, 8), Image.LANCZOS)
    except Exception:
        return None
    px, b = im.tobytes(), 0
    for y in range(8):
        for x in range(8):
            b = (b << 1) | (px[y * 9 + x] > px[y * 9 + x + 1])
    return f"{b:016x}"


def is_bait(h, baits):
    return bool(h) and any(bin(int(h, 16) ^ int(k, 16)).count("1") <= BAIT_DIST for k in baits)


def series_key(name, author):
    return re.sub(r"[\s　・·:：!！?？~〜\-_.,()（）\[\]【】「」『』]", "", (name or "").lower()) + "|" + (author or "").lower()


def strip_ep(title):
    """'번역) 나니와 금융도 32화(파멸)' → '나니와 금융도'"""
    t = re.sub(r"^\s*(번역|창작|단편|연재|공식|웹툰|재업|재번역)\s*\)\s*", "", title)
    t = re.sub(r"\s*[\(\[（【][^)\]）】]*[\)\]）】]\s*$", "", t)
    m = EP_RE.search(t)
    return (t[:m.start()] if m else t).strip(" -~:：·") or t.strip()


def ep_num(title):
    m = EP_NUM_RE.search(title or "")
    return int(m.group(1)) if m else None


def ep_ref(e):
    return f"{e.get('g') or DC_GALL}/{e['no']}"


def series_base(title):
    """제목 → 회차·말머리를 뗀 비교용 이름. 오타가 잦아 너그럽게 뗀다('번엽) … 모음62' → '…모음')"""
    t = re.sub(r"^\s*[^\s()]{1,5}\)\s*", "", title or "")
    return series_key(re.sub(r"\d+\s*화?\s*$", "", strip_ep(t)), "")


def merge_order(old, new):
    """new 순서를 기본으로, 거기 없는 old 항목은 old 에서 바로 앞이던 항목 뒤에 끼운다."""
    out = list(dict.fromkeys(new))
    prev = None
    for r in old:
        if r not in out:
            out.insert(out.index(prev) + 1 if prev in out else 0, r)
        prev = r
    return out


def merge_canon(old, new):
    """회차 목록 두 개 [(갤러리, 글번호, 제목)]를 합친다. new(더 최신 상자) 순서가 기본이고 old 에만 있는 화는 앞 화 뒤에 끼운다."""
    t = {(g, no): x for g, no, x in old + new}
    return [(r.split("/")[0], int(r.split("/")[1]), t[(r.split("/")[0], int(r.split("/")[1]))])
            for r in merge_order([f"{g}/{no}" for g, no, _ in old], [f"{g}/{no}" for g, no, _ in new])]


def order_eps(canon, eps):
    """회차 순서: 지정 글의 상자·링크 모음 순서(canon)를 그대로 쓰고, 거기 없는 화는 같은 갤러리에서
    글 번호가 바로 앞인 canon 화 뒤에 글 번호 순으로 둔다. 회차 번호는 오타가 잦아 정렬에 쓰지 않는다."""
    pos = {r: i for i, r in enumerate(dict.fromkeys(canon))}
    anchors = [(r.split("/")[0], int(r.split("/")[1]), i) for r, i in pos.items()]

    def key(e):
        r = ep_ref(e)
        if r in pos:
            return (pos[r], 0, 0)
        g = e.get("g") or DC_GALL
        return (max((i for gg, no, i in anchors if gg == g and no < e["no"]), default=-1), 1, e["no"])
    return sorted(eps, key=key)


# ── 색인 글형 작품(닌자 슬레이어): 운영자가 정리해 둔 '코믹스 정리' 글을 부(◆…◆)·권(제N권)·에피소드(「…」)·회차(#n 링크)로 읽는다 ──
IDX_LINK_RE = re.compile(r"(?:m\.dcinside\.com/(mini|board)/(\w+)/(\d+)|gall\.dcinside\.com/(mini/)?board/view/?\?id=(\w+)(?:&amp;|&)no=(\d+))")
IDX_SKIP_RE = re.compile(r"미번역|원본|미식질|노번역|영문|질문|어디서|언제|없냐|있냐|어째서|\?|브금|재업|화질|식질|개인용|곰익스|번역본|망가|로스트|삭제|복구|썰|폭발|링크가|시급|추천")  # 번역이 아닌 글·재업·잡담 제목


def dc_link(href):
    """디시 글 주소 → (갤러리, 글번호, 미니갤 여부) 또는 None"""
    m = IDX_LINK_RE.search(html.unescape(href))
    if not m:
        return None
    return (m.group(2) or m.group(5), int(m.group(3) or m.group(6)), bool(m.group(1) == "mini" or m.group(4)))


def dc_post_url(g, no, mini=False):
    return f"https://m.dcinside.com/{'mini' if mini else 'board'}/{g}/{no}"


def parse_index(url, part="", depth=1):
    """정리 글 → [{part, vol, arc, label, u, g, no}] 본문 순서대로. 본문 안의 다른 정리 글(제1권~제5권 같은 링크)은 depth 만큼 따라 들어간다."""
    t = dc_fetch(url)
    time.sleep(1)
    i = t.find('class="thum-txtin"')
    j = t.find('class="gall-detail-lst', i)
    body = t[i:j] if i >= 0 else ""
    body = re.sub(r"<(?!a\s|/a>)[^>]+>", " ", body)  # <a> 만 남기고 다른 태그는 공백으로(「」가 글꼴 태그로 쪼개져 있어서)
    out, vol, arc = [], "", ""
    for href, atext, text in re.findall(r'<a [^>]*href="([^"]+)"[^>]*>(.*?)</a>|([^<]+)', body, re.S):
        if href:
            if href.startswith(("javascript", "#", "/pum/")):
                break  # 본문이 끝나고 추천·공유 버튼이 시작됨
            lab = clean(atext)
            if not lab:
                continue
            link = dc_link(href)
            if link and depth > 0 and re.search(r"권|정리|모음", lab) and not re.match(r"#", lab):  # 하위 정리 글
                try:
                    sub = parse_index(dc_post_url(*link), part, depth - 1)
                except Exception as e:
                    print(f"연재 만화: 하위 정리 글 {lab} 실패 ({e})", file=sys.stderr); sub = []
                if sub:
                    out += sub; continue
            u = dc_post_url(*link) if link else html.unescape(href)
            if not u.startswith("http"):
                continue
            out.append({"part": part, "vol": vol, "arc": arc, "label": lab, "u": u, "g": link[0] if link else "", "no": link[1] if link else 0})
        else:
            x = clean(text)
            for mm in re.finditer(r"◆([^◆]+)◆|제\s*(\d+)\s*권|「\s*([^」]+?)\s*」", x):
                if mm.group(1):
                    part, vol, arc = mm.group(1).strip(), "", ""
                elif mm.group(2):
                    vol = mm.group(2)
                else:
                    arc = mm.group(3).strip()
            rest = re.sub(r"◆[^◆]+◆|제\s*\d+\s*권|[／/,，]|KILLs\s*\w+|완결|※.*", " ", x).strip()
            if "「" not in x and 2 <= len(rest) <= 20:  # 「」 없이 적힌 이름(예고편, 단행본 권말 부록 모음 …)도 에피소드로 본다
                arc = rest
    return out


def arc_key(name):
    return re.sub(r"[\s　・·ㆍ:：!！?？~〜\-_.,()（）\[\]【】「」『』]", "", name or "").lower()


def guess_arc(title, known, aliases):
    """갤러리 글 제목 → (에피소드 이름, 회차 라벨). 이름은 색인에 있는 에피소드와 맞춰 본다(별칭 → 그대로 → 앞 4글자)."""
    t = re.sub(r"^\s*(?:번역|닌슬|직결중점|킬즈|킬러즈)\s*[\)\-:]\s*|^\s*\[[^\]]*\]\s*", "", title)
    NUM = r"#\s*(\d+)(?:\s*[,/]\s*#?\s*(\d+))?|(\d+)\s*(?:화|#)|(?<=[가-힣A-Za-z\s])(\d{1,3})(?=\s*(?:번역|$|\(|입니다|직결|배달|의\s))"
    m = re.search(NUM, t)
    if not m:
        return None, ""
    label = "#" + m.group(1) + (", #" + m.group(2) if m.group(2) else "") if m.group(1) else "#" + (m.group(3) or m.group(4))
    name = clean(re.sub(NUM + r"|\(완\)|\(.*?\)|번역|입니다|이와요|이사와요|배달|직결\s*(?:포탈|링크|중점)\S*|의\s*$|및.*$", " ", t)).strip(" -:·,")
    k = arc_key(name)
    for a, full in aliases.items():
        if k.startswith(arc_key(a)):
            return full, label
    for kk, full in known.items():
        if k == kk or (len(k) >= 4 and (kk.startswith(k) or k.startswith(kk[:4]))):
            return full, label
    return name, label


LINK_CHECK_MAX = 70   # 한 번 실행에서 열어 보는 회차 링크 수(처음엔 몇 번에 나눠 다 확인하고, 그 뒤로는 새 회차만)
LINK_RECHECK_DAYS = 7 # 깨진 링크는 이 간격으로 다시 확인한다(디시가 일시적으로 403을 낼 수 있어서)


def resolve_link(url):
    """회차 글을 한 번 열어 본다 → ("dead", None) 글이 없음(403/404) / ("link", 주소) 본문이 그림 없이 다른 글로 안내하는 '직결' 글 / ("ok", None).
    직결 글은 그림이 2장 이하이고 본문에 다른 디시 글이나 바깥 사이트 링크가 있다."""
    try:
        t = dc_fetch(url)
    except urllib.error.HTTPError as e:
        if e.code in (403, 404, 410):
            return "dead", None
        raise
    i = t.find('class="thum-txtin"')
    j = t.find('class="gall-detail-lst', i)
    body = t[i:j] if i >= 0 else ""
    imgs = body.count("viewimage.php")
    if imgs > 2:
        return "ok", None
    for href, _ in re.findall(r'<a [^>]*href="([^"]+)"[^>]*>(.*?)</a>', body, re.S):
        href = html.unescape(href)
        if href.startswith(("javascript", "#", "/")):
            break  # 본문이 끝나고 추천·공유 버튼이 시작됨
        link = dc_link(href)
        if link:
            return "link", dc_post_url(*link)
        if href.startswith("http") and not re.search(r"dcinside\.com|youtu\.?be|youtube\.com|x\.com|twitter\.com", href):
            return "link", href
    return ("empty" if imgs == 0 and i >= 0 else "ok"), None  # 그림도 링크도 없는 글 = 그림이 지워진 글


def check_links(eps, cache, today):
    """회차 링크를 확인해 cache({원래 주소: {u, ok, n, t}})를 채우고, 각 회차에 u(최종 주소)·dead 를 적는다. 한 번에 LINK_CHECK_MAX 개까지."""
    budget = LINK_CHECK_MAX
    for e in eps:
        if not e.get("g"):
            continue  # 디시 밖 링크(아카라이브)는 Actions 에서 못 열어 그대로 둔다
        c = cache.get(e["u"])
        ago = lambda d: (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=d)).strftime("%Y-%m-%d")
        # 한 번 없었던 글(n=1)은 다음 날 다시, 깨진 걸로 굳힌 글은 LINK_RECHECK_DAYS 마다 다시 본다
        stale = c and c.get("n", 0) > 0 and c.get("t", "") <= (ago(1) if c.get("ok") else ago(LINK_RECHECK_DAYS))
        if (c is None or stale) and budget > 0:
            budget -= 1
            try:
                kind, to = resolve_link(e["u"])
            except Exception as ex:
                print(f"연재 만화: 링크 확인 실패 {e['u']} ({ex})", file=sys.stderr); continue
            time.sleep(0.8)
            if kind in ("dead", "empty"):
                n = (c or {}).get("n", 0) + (2 if kind == "empty" else 1)
                cache[e["u"]] = {"u": e["u"], "ok": n < 2, "n": n, "t": today}  # 403/404는 두 번 연속 없어야 깨진 것으로, 그림이 하나도 없는 글은 바로 깨진 것으로
            else:
                cache[e["u"]] = {"u": to or e["u"], "ok": True, "n": 0, "t": today}
            c = cache[e["u"]]
        if c:
            e["o"] = e["u"]
            if c["u"] != e["u"]:
                e["u"] = c["u"]
            if not c.get("ok"):
                e["dead"] = True
    return budget


def build_index_series(f, s, scanned):
    """색인 글형 작품 하나를 만든다. 정리 글의 순서를 그대로 쓰고, 갤러리에서 새로 올라온 번역 글(색인에 없는 회차)을 뒤에 더한다."""
    eps = []
    for u in f["index"]:
        try:
            eps += parse_index(u)
        except Exception as e:
            print(f"연재 만화: {f['title']} 정리 글 {u} 실패 ({e})", file=sys.stderr)
    if not eps:
        return None
    nums = lambda lab: set(re.findall(r"\d+", lab))
    have = {}
    for e in eps:
        have.setdefault((e["part"], arc_key(e["arc"])), set()).update(nums(e["label"]))
    known = {arc_key(e["arc"]): e["arc"] for e in eps if e["arc"]}
    arc_parts = {}
    for e in eps:
        arc_parts.setdefault(arc_key(e["arc"]), set()).add(e["part"])
    extra = []
    g, mini = f.get("gallery", ""), f.get("mini", True)
    if g:
        rows, last = [], None
        for pg in range(1, 40):  # 미니 갤러리는 글이 적어 전부 읽는다(쪽당 ~25건)
            try:
                r = dc_rows(dc_fetch(f"https://m.dcinside.com/{'mini' if mini else 'board'}/{g}?page={pg}"), g)
            except Exception as e:
                print(f"연재 만화: {f['title']} 목록 {pg}쪽 실패 ({e})", file=sys.stderr); break
            time.sleep(0.7)
            if not r or r[0]["no"] == last:
                break
            rows += r; last = r[0]["no"]
        in_index = {(e["g"], e["no"]) for e in eps}
        for row in sorted(rows, key=lambda r: r["no"]):
            if (g, row["no"]) in in_index or IDX_SKIP_RE.search(row["title"]) or any(row["nick"].startswith(n) for n in f.get("raw_nicks", [])):
                continue
            name, label = guess_arc(row["title"], known, f.get("aliases", {}))
            if not name or len(arc_key(name)) < 2:
                continue
            parts = arc_parts.get(arc_key(name), set())
            part = next(iter(parts)) if len(parts) == 1 else ""
            if "[킬즈]" in row["title"] or "킬즈)" in row["title"]:
                part = next((p for p in parts if "킬즈" in p and "킬러즈" not in p), part)
            if "[킬러즈]" in row["title"]:
                part = next((p for p in parts if "킬러즈" in p), part)
            if not nums(label) or any(nums(label) <= have.get((p, arc_key(name)), set()) for p in (parts or {part})):
                continue  # 색인에 이미 있는 회차의 재업·중복
            if not part:
                part = "색인에 아직 없는 번역"
            e = {"part": part, "vol": "", "arc": name, "label": label, "u": dc_post_url(g, row["no"], mini), "g": g, "no": row["no"], "title": row["title"]}
            have.setdefault((part, arc_key(name)), set()).update(nums(label))
            extra.append(e)
    # 색인에 없는 회차는 같은 에피소드의 마지막 회차 뒤에(권도 이어받아) 끼우고, 에피소드 자체가 새로우면 '색인에 아직 없는 번역' 부에 둔다
    # 그 부는 extra_before 로 지정한 부 앞에(없으면 맨 뒤) 들어간다
    before = f.get("extra_before", "")
    at_part = next((i for i, x in enumerate(eps) if before and before in x["part"]), len(eps))
    for e in extra:
        at = max((i + 1 for i, x in enumerate(eps) if x["part"] == e["part"] and arc_key(x["arc"]) == arc_key(e["arc"])), default=None)
        if at is None:
            at = at_part if e["part"] == "색인에 아직 없는 번역" else len(eps)
            eps.insert(at, e)
            if at <= at_part:
                at_part += 1
        else:
            e["vol"] = eps[at - 1]["vol"]
            eps.insert(at, e)
            if at <= at_part:
                at_part += 1
    # 회차 링크 확인: 없는 글은 dead, '직결' 글은 가리키는 주소로 바꾼다(결과는 links 에 남겨 다시 열지 않는다)
    cache = s.get("links") or {}
    left = check_links(eps, cache, datetime.now(JST).strftime("%Y-%m-%d"))
    s["links"] = {k: v for k, v in cache.items() if any(e.get("o") == k or e["u"] == k for e in eps)}
    parts = []
    for e in eps:
        p = next((p for p in parts if p["name"] == e["part"]), None)
        if not p:
            p = {"name": e["part"], "arcs": []}; parts.append(p)
        a = p["arcs"][-1] if p["arcs"] and p["arcs"][-1]["name"] == e["arc"] and p["arcs"][-1]["vol"] == e["vol"] else None
        if not a:
            a = {"name": e["arc"], "vol": e["vol"], "eps": []}; p["arcs"].append(a)
        a["eps"].append({k: e[k] for k in ("label", "u", "g", "no", "dead") if e.get(k) or k == "label"})
    dead = sum(1 for e in eps if e.get("dead"))
    s.update({"name": f["title"], "title": f["title"], "author": f.get("author", ""), "kind": "index", "parts": parts,
              "episodes": [{"no": e["no"], "g": e["g"], "title": f"{e['arc']} {e['label']}".strip(), "u": e["u"]} for e in eps if not e.get("dead")],
              "updatedAt": max([s.get("updatedAt", "")] + [datetime.now(JST).strftime("%Y-%m-%dT%H:%M") if extra else ""])})
    print(f"연재 만화: {f['title']} 색인 {len(eps) - len(extra)}회차 + 갤러리 추가 {len(extra)}회차, 링크 확인 {LINK_CHECK_MAX - left}건(깨짐 {dead}, 직결 {sum(1 for e in eps if e.get('o') and e['o'] != e['u'])}, 미확인 {sum(1 for e in eps if e.get('g') and not e.get('o'))})", file=sys.stderr)
    return s


def comic_follows():
    """data/comics_follow.json → [{title, author, posts:[(갤러리, 글번호)]}]. posts 는 디시 글 주소나 '갤러리/글번호'.
    색인 글형은 {title, index:[정리 글 주소], gallery, mini, aliases, raw_nicks}."""
    out = []
    for f in load_json(COMICS_FOLLOW, {}).get("follow", []):
        posts = []
        for u in f.get("posts", []):
            m = re.search(r"(?:board/|^)(\w+)/(\d+)", str(u)) or re.search(r"id=(\w+)(?:&amp;|&)no=(\d+)", str(u))
            if m:
                posts.append((m.group(1), int(m.group(2))))
        if f.get("title"):
            out.append({"title": f["title"], "author": f.get("author", ""), "posts": posts, "index": [u for u in f.get("index", []) if str(u).startswith("http")],
                        "gallery": f.get("gallery", ""), "mini": f.get("mini", True), "aliases": f.get("aliases", {}), "raw_nicks": f.get("raw_nicks", []), "extra_before": f.get("extra_before", "")})
    return out


def export_comics(ref):
    """지정한 연재작(data/comics_follow.json)의 회차를 1화부터 data/comics.json 에 쌓는다. 실패해도 다른 수집에 영향이 없게 예외를 삼킨다."""
    doc = load_json(COMICS, {"updated": "", "gallery": DC_GALL, "series": [], "scanned": []})
    if not dc_allowed():
        return
    blk = load_json(os.path.join(DATA, "blocklist.json"), {})
    baits = BAIT_HASHES + [k for k in blk.get("comic_images", []) if re.fullmatch(r"[0-9a-fA-F]{16}", str(k))]
    follows = comic_follows()
    by = {s["id"]: s for s in doc.get("series", [])}
    scanned = set(doc.get("scanned", []))
    bad = set(doc.get("bad", []))
    stats = {"opened": 0, "bait": 0, "new": 0}

    def open_post(no, g=DC_GALL):
        """글을 열어 낚시글이면 bad 에 넣고 None, 아니면 (이름, 회차, 시각, 표지)"""
        stats["opened"] += 1
        r = dc_post(no, g)
        time.sleep(1)
        if is_bait(img_hash(r[3]), baits):
            bad.add(f"{g}/{no}"); stats["bait"] += 1
            print(f"연재 만화: 낚시글 제외 {g}/{no}", file=sys.stderr)
            return None
        return r

    posts = []
    for page in range(1, DC_PAGES + 1):
        try:
            posts += dc_list(page)
        except Exception as e:
            print(f"연재 만화: 목록 {page}쪽 실패 ({e})", file=sys.stderr); break
        time.sleep(1)
    newest = max((p["no"] for p in posts), default=0)  # 지금 갤러리의 대략 최신 글 번호

    series = []
    for f in follows:
        key = series_key(f["title"], "")
        s = by.get(key) or {"id": key, "episodes": [], "rec": 0, "cover": ""}
        if f["index"]:  # 색인 글형(닌자 슬레이어): 정리 글 + 갤러리 새 번역 글
            try:
                r = build_index_series(f, s, scanned)
            except Exception as e:
                r = None; print(f"연재 만화: {f['title']} 실패 ({e})", file=sys.stderr)
            if r:
                series.append(r)
            elif s.get("parts"):
                series.append(s)  # 이번에 못 읽었으면 예전 것을 유지
            continue
        s.update({"name": f["title"], "title": f["title"], "author": f["author"]})
        canon = []  # 지정 글의 상자·링크 모음 순서 = 작가가 정한 회차 순서
        for g, no in f["posts"]:
            try:
                canon += read_series(g, no)[0]
            except Exception as e:
                print(f"연재 만화: {f['title']} 글 {g}/{no} 실패 ({e})", file=sys.stderr)
        # [시리즈] 상자는 그 글을 쓸 때까지의 목록이라 빠진 화가 있을 수 있다 → 아는 최신 화의 상자도 읽어 합친다(최신 상자 순서 우선)
        last_known = max((e["no"] for e in s["episodes"] if not e.get("g")), default=0)
        if last_known and (DC_GALL, last_known) not in f["posts"]:
            try:
                canon = merge_canon(canon, read_series(DC_GALL, last_known)[0])
            except Exception as e:
                print(f"연재 만화: {f['title']} 최신 화 상자 실패 ({e})", file=sys.stderr)
        if doc.get("v", 0) < 6 and canon:  # 순서·중복 규칙을 바꿔서 한 번 처음부터 다시 모은다(지정 글을 못 읽었으면 예전 목록 유지)
            s["episodes"], s["seenTo"] = [], 0
        known = {ep_ref(e): e for e in s["episodes"]}
        for g, no, t in canon:
            e = {"no": no, "title": t} | ({"g": g} if g != DC_GALL else {})
            known.setdefault(ep_ref(e), e)
        # 새 화: 지금 아는 마지막 화·이미 훑은 범위(seenTo)보다 뒤에 올라온 같은 작품의 번역 글만 받는다
        # (다른 사람이 예전 화를 다시 올린 글, '방본만)' 같은 감상 글, 터무니없는 회차 번호는 거른다).
        # 개념글에서 먼저 찾고 제목 검색으로 채운다. 같은 번호가 둘 걸리면 먼저 올라온 글만.
        floor = max([s.get("seenTo", 0)] + [e["no"] for e in known.values() if not e.get("g")])
        top = max([ep_num(e["title"]) or 0 for e in known.values()] + [0])
        cands = {p["no"]: p for p in posts if p["no"] > floor and p["no"] not in scanned and series_base(p["title"]) == key}
        scanned.update(cands)
        b = [DC_FOLLOW_SEARCH]
        for row in dc_search(f["title"], DC_FOLLOW_SEARCH, b, floor):
            cands.setdefault(row["no"], row)
        new = set()
        for no in sorted(cands):
            row = cands[no]
            ref_, n = f"{DC_GALL}/{no}", ep_num(row["title"])
            if no <= floor or ref_ in known or ref_ in bad or not n or n in new or (top and n > top + 3) \
                    or not TRANS_RE.search(row["title"]) or series_base(row["title"]) != key:
                continue
            if stats["opened"] >= DC_POST_MAX:
                break
            try:
                r = open_post(no)
            except Exception as e:
                print(f"연재 만화: 글 {no} 실패 ({e})", file=sys.stderr); continue
            if r:
                known[ref_] = {"no": no, "title": row["title"], "date": r[2][:16]}
                canon = merge_canon(canon, expand_box(r[1]) + [(DC_GALL, no, row["title"])])  # 새 화의 상자가 가장 최신 목록
                for g, no2, t in canon:
                    e = {"no": no2, "title": t} | ({"g": g} if g != DC_GALL else {})
                    known.setdefault(ep_ref(e), e)
                new.add(n); top = max(top, n); stats["new"] += 1
                s["rec"] = max(s.get("rec", 0), row.get("rec", 0))
        if b[0] >= 0 and newest:
            s["seenTo"] = newest
        s["episodes"] = order_eps([f"{g}/{no}" for g, no, _ in canon], [e for r, e in known.items() if r not in bad])
        if not s["episodes"]:
            continue
        last = s["episodes"][-1]
        if not last.get("date") or s.get("coverNo") != ep_ref(last):  # 최신 화를 열어 날짜·표지를 얻는다
            try:
                r = open_post(last["no"], last.get("g") or DC_GALL)
            except Exception as e:
                r = None; print(f"연재 만화: {f['title']} 최신 화 실패 ({e})", file=sys.stderr)
            if r:
                last["date"] = r[2][:16]
                s["cover"], s["coverNo"] = r[3] or s.get("cover", ""), ep_ref(last)
            elif ep_ref(last) in bad:  # 최신 화가 낚시글이었으면 빼고 다음 실행에서 표지를 다시 찾는다
                s["episodes"].pop()
        s["updatedAt"] = max(s.get("updatedAt", ""), (s["episodes"][-1].get("date") or "") if s["episodes"] else "")
        series.append(s)
    doc = {"v": 6, "updated": ref.isoformat(), "gallery": DC_GALL, "series": series,
           "scanned": sorted(scanned)[-3000:], "bad": sorted(bad)[-500:]}
    save_json(COMICS, doc)
    print(f"→ data/comics.json: 지정 연재작 {len(series)}편, 회차 {sum(len(s['episodes']) for s in series)}개 "
          f"(이번에 글 {stats['opened']}건 확인, 새 화 {stats['new']}건, 낚시글 {stats['bait']}건 제외)")


def dump_page(src):
    """--check 와 환경변수 DUMP=출처 이름: 그 출처 주소의 원본 앞부분과 링크 주변을 로그로 보여 준다(html 출처의 item 정규식을 고칠 때).
    클라우드 세션에서는 외부 사이트가 막혀 있어 Actions 의 '소스 점검'(입력 dump)으로 본다."""
    url = src.get("url", "").replace("{ym}", datetime.now(JST).strftime("%Y%m"))
    page = fetch(url, src.get("headers")).decode("utf-8", "replace")
    print(f"--- DUMP {src.get('name')}: {url} ({len(page)}자)")
    body = page.find("<body")
    print(page[max(0, body):max(0, body) + 1500] if body >= 0 else page[:1500])
    seen = 0
    start = max(0, body)  # <head> 의 canonical·alternate 링크는 건너뛰고 본문 링크만
    for m in re.finditer(r'href="[^"]*/(news|article|topics|info)[^"]*/[^"/]+/?"', page[start:]):
        m = re.compile(re.escape(m.group(0))).search(page, start + m.start())
        if seen >= 4: break
        print(f"--- 링크 주변 {seen + 1} (위치 {m.start()})")
        print(page[max(0, m.start() - 300):m.start() + 900]); seen += 1
    links = sorted({html.unescape(m.group(1)) for m in re.finditer(r'href="([^"]*(?:rss|feed|atom|/cat|categor|/tag/|ranking|hot)[^"]*)"', page, re.I)})
    print(f"--- RSS·카테고리·순위 링크 {len(links)}개"); print("\n".join(links[:60]))
    print("--- DUMP 끝")


def check():
    """소스마다 가져오기만 해 보고 결과를 출력한다. 파일은 쓰지 않는다. 실패가 있으면 종료 코드 1."""
    ref = datetime.now(JST)
    bad = 0
    for src in SOURCES:
        name = src.get("name", src["type"])
        if os.environ.get("DUMP") and os.environ["DUMP"] == name:
            for d in [src] + ([{**src, **src["fallback"]}] if src.get("fallback") else []):
                try: dump_page(d)
                except Exception as e: print(f"--- DUMP 실패: {e}")
        try:
            got = collect(src, ref)
            print(f"OK   {name}: 원본 {RAW.get(name, len(got))}건 중 {len(got)}건 통과 (그림 {sum(1 for g in got if g.get('image'))}건)"
                  + (f" · 피드 {_cache.get(src['url'])}" if src["type"] == "site" else ""))
            for g in got[:4]:
                print(f"       + {g['title'][:70]}")
            for ti in DROPPED.get(name, [])[:3]:
                print(f"       - {ti[:70]}")
        except Exception as e:
            bad += 1
            print(f"FAIL {name}: {e}")
    for kind, url in BUZZ_FEEDS:  # X 화제(Togetter)도 같이 본다
        try:
            es = parse_feed(fetch(url))
            print(f"OK   {BUZZ_NAME} {kind}: {len(es)}건 (그림 {sum(1 for e in es if e[4])}건, 요약 {sum(1 for e in es if clean(e[1]))}건, 오타쿠 {sum(1 for e in es if OTAKU_RE.search(e[0] + e[1]))}건)")
            for e in es[:3]:
                print(f"       + {clean(e[0])[:60]} | {clean(e[1])[:50]} | {e[4][:60]}")
        except Exception as e:
            bad += 1; print(f"FAIL {BUZZ_NAME} {kind}: {e}")
    try:  # 제보의 X 글 읽기(oEmbed)가 키 없이 되는지: X 개발자 문서의 예시 글
        body, who = tip_x("https://twitter.com/Interior/status/507185938620219395")
        print(f"OK   X oEmbed(제보): {who}: {body[:60]!r}" if body else "FAIL X oEmbed(제보): 본문이 비었음")
        bad += 0 if body else 1
    except Exception as e:
        bad += 1; print(f"FAIL X oEmbed(제보): {e}")
    print(f"→ 실패 {bad}/{len(SOURCES) + len(BUZZ_FEEDS) + 1}")
    return 1 if bad else 0


if __name__ == "__main__":
    os.makedirs(os.path.join(DATA, "thumbs"), exist_ok=True)
    if "--check" in sys.argv:
        sys.exit(check())
    if "--translate-test" in sys.argv:
        t = "「薬屋のひとりごと」原画展が池袋で10月31日より開催、前売券はe+で発売中"
        print(translate_ja_ko(t)); print(translate_ja_ko(gloss_pre(t)), "(용어집)")
        sys.exit(0)
    if "--anime" in sys.argv:
        export_anime(datetime.now(JST))
    elif "--alert-broken" in sys.argv:
        call = gh_api()
        if call:
            srv, repo, rid = (os.environ.get(k, "") for k in ("GITHUB_SERVER_URL", "GITHUB_REPOSITORY", "GITHUB_RUN_ID"))
            broken_run(call, load_json(BROKEN_FILE, None), f"{srv}/{repo}/actions/runs/{rid}")
    elif "--alert" in sys.argv:
        try:
            source_alert()
        except Exception as e:  # 알림이 실패해도 워크플로는 이어 간다
            print(f"출처 알림 실패: {e}", file=sys.stderr)
    elif "--weekly-draft" in sys.argv:
        try:
            weekly_draft(datetime.now(JST))
            write_feed(datetime.now(JST))  # 초안이 생겼으면 RSS 에도
        except Exception as e:  # 실패해도 워크플로는 이어 간다
            print(f"주간 요약 초안 실패: {e}", file=sys.stderr)
    elif "--comics" in sys.argv:
        try:
            export_comics(datetime.now(JST))
        except Exception as e:  # 연재 만화 수집이 실패해도 워크플로는 이어 간다
            print(f"연재 만화 수집 실패: {e}", file=sys.stderr)
    else:
        main()
