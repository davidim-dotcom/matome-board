# CLAUDE.md — 마토메 보드 작업 안내

일본 게임·애니·버튜버·만화의 공연/이벤트 소식을 모아 친구들에게 공개하는 **GitHub Pages 정적 보드**다.
서버·빌드·패키지 매니저가 없다. 저장소 루트가 그대로 사이트이고, GitHub Actions가 `data/`를 하루 4번 갱신한다.
README.md는 운영자(사람)용 설명이고, 이 문서는 코드를 고치는 쪽을 위한 정리다.

## 파일 구조

| 경로 | 역할 | 누가 고치나 |
|---|---|---|
| `index.html` | 공개 페이지. HTML+CSS+JS 단일 파일(약 480줄). `data/*.json`을 fetch해서 그린다. 외부 의존성은 Google Fonts만. | 사람 |
| `collector.py` | 수집기. 표준 라이브러리만 사용(`--anime`의 썸네일만 Pillow 선택 사용). | 사람 |
| `.github/workflows/update.yml` | 하루 4번(JST 06/12/18/24시, UTC `0 21,3,9,15`) + 수동 실행. `collector.py` → `collector.py --anime` → `data/` 변경분을 `main`에 커밋·푸시 | 사람 |
| `.github/workflows/check.yml` | 수동 실행 전용 "소스 점검". `collector.py --check`를 돌려 소스별 OK/FAIL만 출력하고 `data/`는 건드리지 않는다. 소스를 고친 뒤 확인용. | 사람 |
| `data/manual.json` | 직접 추가하는 소식 배열. 자동 수집보다 먼저 읽혀 같은 id면 우선. | 사람 |
| `data/blocklist.json` | `{"urls":[], "titles":[], "ids":[]}`. 수집기와 페이지 양쪽에서 제외. `titles`는 소문자 부분일치. | 사람 |
| `data/anime.json` | 이번 시즌 방영 목록. 요일·시각 등은 사람이 고치고, `--anime`가 Annict 정보를 덧붙인다. | 사람 + 봇 |
| `data/items.json` | 수집된 소식(최대 `KEEP`=600건). | 봇만 |
| `data/meta.json` | `{updated, trends(상위 20), count}`. 페이지 상단 "n/n hh:mm 업데이트" 표기용. | 봇만 |
| `data/trends.json` | 유행 감지 기록 `{history:{날짜:{작품명:횟수}}, top:[...], updated}`. 최근 14일. | 봇만 |
| `data/thumbs.json`, `data/thumbs/*.jpg` | 작품 제목 → 208×117 JPEG 썸네일 경로. 파일명은 `sha1(공백 제거·소문자 제목)[:16].jpg`. | 봇만 |
| `data/.feedcache.json` | `site` 타입 소스의 RSS 자동 탐색 결과 캐시(사이트 URL → 피드 URL). 소스 RSS 주소가 바뀌면 해당 항목을 지워야 다시 찾는다. | 봇만 |
| `assets/og.png`, `assets/icon-512.png`, `assets/apple-touch-icon.png` | 링크 공유 미리보기 이미지(1200×630)와 파비콘·홈 화면 아이콘. `index.html` head의 og/twitter 메타와 `<link rel=icon>`이 가리킨다. 사이트 글꼴(Black Han Sans, IBM Plex Sans KR)로 Chromium에서 렌더한 PNG이며 원본 HTML은 저장소에 없다. 바꾸려면 같은 크기로 교체. | 사람 |
| `CHANGELOG.md` | 릴리즈별 변경 기록. 태그(`v1.0.0` …)와 함께 갱신한다. | 사람 |
| `bbs/Code.gs` | 게시판 백엔드(Apps Script). 저장소에서는 실행되지 않고, 운영자가 스프레드시트에 붙여 넣어 배포하는 원본. | 사람 |
| `.nojekyll` | GitHub Pages가 Jekyll로 처리하지 않게 함(`.feedcache.json` 같은 점 파일 유지). | — |

`data/items.json`에는 현재 `SOURCES`에 없는 출처(e+, オレンジ工房 등)의 항목도 있다. 이전 보드에서 가져온 초기 데이터이므로 "소스 목록과 안 맞는다"고 지우지 말 것. 정리 규칙에 따라 자연히 빠진다.

## 데이터 형식

### 소식 항목 (`items.json`, `manual.json` 공통)

```json
{"title":"", "category":"live", "source":"출처", "platform":"site|rss|wpjson|json|youtube|holodex",
 "works":["작품명"], "eventDate":"2026-12-19T18:00", "endDate":"", "ticketOpen":"", "deadline":"",
 "venue":"", "ticketUrl":"", "ticketUrls":["예매처별 링크(선택)"], "url":"원문", "summary":"", "image":"대표 이미지 주소(선택)",
 "title_ko":"한국어 제목(선택)", "summary_ko":"한국어 요약(선택)", "addedAt":"ISO"}
```

- 날짜는 **JST**이며 시간대 표기가 없으면 페이지가 `+09:00`을 붙여 해석한다.
- `category`는 `live event official doujin collab popup exhibit manga goods stream campaign other` 중 하나. 모르는 값은 페이지에서 `other`로 떨어진다.
- `id`는 저장하지 않고 페이지가 `hashId(url|title|eventDate)`로 만든다. 따라서 **title·url·eventDate가 바뀌면 다른 항목**이 되어 각자의 "관심 있어요/숨김" 기록과 끊어진다.
- 수집기 쪽 중복 판정은 `(url, title)` 쌍이다.
- `image`는 **주소만** 둔다(파일은 저장하지 않음). 수집기가 피드의 enclosure/media/본문 `<img>`, WP 대표 이미지, JSON의 image 키에서 뽑는다. 페이지는 https 주소만 받아 84px 썸네일로 보여 주고, 못 불러오면 조용히 지운다(`onerror`). 방영 목록 썸네일(`data/thumbs/`)과는 다른 경로다.
- `ticketUrls`는 예매처(e+, ローチケ, ぴあ …)별로 하나씩 모은 링크 목록이고 `ticketUrl`은 그 첫 번째(옛 데이터 호환). 페이지는 둘을 합쳐 예매처마다 버튼을 하나씩 그린다(최대 4개).
- 한국어 번역(`translate_items`): 아직 `title_ko` 키가 없는 소식의 제목·요약을 Google 번역(키 없는 `translate.googleapis.com/translate_a/single?client=gtx`)으로 일본어→한국어 번역해 `title_ko`/`summary_ko`에 넣는다(실행당 `TRANSLATE_MAX`=150건, 요청 사이 0.2초). 일본어 글자가 없는 글은 `""`(원문 그대로 표시). 요청이 실패하면 키를 남기지 않고 그 실행의 번역을 멈춰 다음 실행에 다시 시도한다. 비공식 엔드포인트라 막히면 번역만 비고 수집은 영향 없다. `python3 collector.py --translate-test`로 경로를 점검한다(클라우드 세션에서는 막힘).
- 기사 보강(`enrich`): 소식마다 기사 페이지를 **한 번만** 열어(실행당 `ENRICH_MAX`=120건, 새 소식부터) 빠진 `image`(og:image)와 아직 없는 예매처의 링크(`<article>`/`<main>` 안의 첫 e+·ぴあ·ローチケ 등 `TICKET_DOMAINS` 링크, 사이트 첫 화면 링크와 그 사이트 첫 화면에 걸린 배너 링크(`site_ticket_links`)는 제외, 같은 출처에서 3개 이상 기사에 똑같이 나오는 링크도 배너로 보고 버림)을 채우고 `scanned: true`로 표시한다. 방송 항목(holodex/youtube)은 열지 않는다. e+ 자체(eplus.jp, spice.eplus.jp)는 GitHub Actions에서 503/403으로 막혀 소스로 쓸 수 없다(2026-10).

### 방영 목록 (`anime.json`)

`{"season":"2026-autumn", "name":"2026년 가을 애니", "src":"출처", "list":[...]}`. 항목 필드:

| 키 | 뜻 |
|---|---|
| `t` | 제목(썸네일·보는 중 목록의 키) |
| `d` | 요일. 0=일 … 6=토, 7=스트리밍(배신), 8=요일 미정 |
| `tm` | 방송 시각 `"HH:MM"`(JST, `26:00`처럼 24시 넘는 표기 허용) |
| `st` | 방송국 문자열 |
| `s` | 첫 방송일 `YYYY-MM-DD` |
| `r` | 평가 순위(숫자 또는 null) |
| `pv`, `site`, `x`, `w` | PV URL, 공식 사이트, X 아이디, Annict 시청자 수 |

시즌은 월로 결정된다(1–3 winter, 4–6 spring, 7–9 summer, 10–12 autumn). `--anime` 실행 시 `season`이 달라지면 목록을 **통째로 새로 만든다**. 같은 시즌이면 기존 항목을 유지하고 `site/x/w`만 덧쓴다.

## 동작 흐름

### 수집 (`python3 collector.py`)

1. `SOURCES`를 순서대로 돈다. 타입: `site`(RSS 자동 탐색) · `rss`(RSS/Atom, Google 뉴스 사이트맵도 읽음) · `wpjson`(WordPress REST API 글 목록, RSS가 비어 있는 WP 사이트용) · `json`(임의 JSON API, `items`/`title`/`date` 필드명과 `link` 틀 지정) · `ldjson`(페이지의 schema.org Event JSON-LD 목록, `{ym}`에 YYYYMM, `months`달치. 날짜·장소가 구조화돼 있어 본문 날짜 추출과 `MUST_HAVE_ANY`를 거치지 않음) · `youtube`(채널 RSS) · `holodex`(`HOLODEX_API_KEY` 필요, 없으면 건너뜀). 소스 공통 옵션: `works`(모든 소식에 붙일 작품 태그), `extra_words`(`MUST_HAVE_ANY`에 더할 통과 단어), `headers`(요청 헤더). 게시일이 있는 글은 `FRESH_DAYS`(60일)보다 오래되면 무시한다. 한 소스가 실패해도 `stderr`에 `이름: 실패 (...)`만 찍고 계속한다. **종료 코드는 항상 0**이므로 Actions에서 실패가 보이지 않는다. 소스 상태는 Actions 로그 stderr나 "소스 점검" 워크플로(`--check`)로 확인.
2. `build()`: 제목+본문에 `MUST_HAVE_ANY` 단어가 하나도 없으면 버림(youtube의 `stream`은 예외). 날짜는 `DATE_RE`로 뽑아 기간(`A〜B`) → 마감(`END_WORDS` 문맥) → 판매 시작(`OPEN_WORDS`) → 행사일 순으로 배정. 연도가 없고 60일 이상 과거면 내년으로 본다.
3. `classify()`: `CAT_RULES`를 위에서부터 검사해 **첫 매치**를 쓴다. 순서가 곧 우선순위(doujin > official > live > exhibit > popup > collab > event > …).
4. 작품 태그: `WORKS_SEED` + `trends.json`의 `top`을 합친 `WATCH` 목록으로 본문을 검사(대소문자 무시, 최대 5개).
5. 유행 감지: 모든 기사 제목·본문의 『』「」 안 이름을 세어 `trends.json` 갱신. `TREND_MIN`=3회 이상이면 `top`에 올라 다음 실행부터 작품 태그로 쓰인다.
6. 정리: 블록리스트 해당, 종료 후 30일 초과, 날짜 없이 추가 후 45일 초과 항목을 버리고 새 항목을 앞에 둔 채 600건까지 저장. `meta.json` 갱신.

### 방영 목록·썸네일 (`python3 collector.py --anime`)

`ANNICT_TOKEN`이 있으면 Annict API로 이번 시즌 작품(최대 6페이지×50)을 받아 합치고, 없으면 기존 목록으로 썸네일만 갱신한다. 썸네일 후보는 ① 공식 사이트 `og:image`/`twitter:image` ② Annict 추천 이미지 ③ `pv`의 YouTube `hqdefault.jpg` 순. 이미 파일이 있으면 다시 받지 않는다.

### 페이지 (`index.html`)

- 로드 순서: localStorage 복원 → 렌더 → `data/` 6개 파일 병렬 fetch(10분 단위 캐시 버스터, `cache:"no-store"`) → 다시 렌더.
- `normalize()`가 모든 입력 필드를 화이트리스트·길이 제한·`safeUrl()`로 걸러 들어온다. 새 필드를 쓰려면 여기 반드시 추가.
- 출력은 전부 `esc()`를 거친다. 템플릿 문자열에 데이터 넣을 때 `esc()` 빠뜨리지 말 것(XSS).
- 개인 설정은 없다(공개 보드). 브라우저에 남는 것은 '보는 중' 목록뿐이며 localStorage 키 `matome-public-v1`에 `{S:{watching:[]}}`로 저장된다(예전 구조의 `S.watching`만 읽어 호환). 소식을 빼려면 `data/blocklist.json`을 쓴다. 예전의 관심 있어요/끄기/학습 기능은 2026-10에 제거했다.
- 표시 언어: 맨 위 `原文 / 한국어` 전환(`lang`, localStorage `matome-lang`, 기본 한국어). `tx(it,"title")`/`tx(it,"summary")`가 번역이 있으면 `*_ko`, 없으면 원문을 돌려준다. 카드 제목·요약과 상단 띠 제목에만 적용하고 장소·작품명·방영 목록은 원문 그대로.
- 탭: 피드 · 캘린더 · 방영중 · 사이트 개요. 분류별 탭(행사·콜라보·만화)은 피드의 분류 칩과 겹쳐서 없앴다.
- 사이트 개요: 안내문 + 익명 게시판(게시 후 수정·삭제 불가). 게시판 백엔드는 Google 스프레드시트에 붙인 Apps Script 웹 앱(`bbs/Code.gs`: GET `?limit=` → `{posts}`, POST JSON `{name,text}` → 행 추가)이고 `index.html` 위쪽 `BBS.api`에 웹 앱 URL을 적는다(비어 있으면 '준비 중'). POST는 Content-Type 없이 보내 preflight를 피한다. 설정 절차는 README의 "게시판 설정". 글은 500자, 같은 브라우저 30초에 1건, 최신 200건 표시. 외부 스크립트 없이 fetch 만 쓴다.
- 캘린더(`renderCalendar`, section id는 예전 그대로 `sched`): 월 격자(일요일 시작, JST 날짜 문자열 `YYYY-MM-DD`로만 계산). 칸에는 그날 `eventDate`로 시작하는 소식의 분류색 점(최대 3개 + `+N`), `ticketOpen`/`deadline`이 있는 날은 호박색 테두리 점, 오른쪽 위 숫자는 진행 중인 기간 소식 수(시작일 < 날 ≤ `endDate`). 날을 누르면 아래에 시작·개최 / 예매·마감 / 진행 중 목록, 안 고르면 이달 시작 목록. 지난 날짜 칸(`.past`)과 끝난 행사 카드(`.row.over`, 제목 뒤 "· 종료")는 흐리게. 상태는 `calYM`, `calDay`.
- 피드 상단 칩: 장르(전부 · 버튜버 · 버튜버 제외) + 정렬(최신순, 날짜순) 한 줄, 그 아래 분류 칩. 버튜버 판별은 `isVtuber()`: 전용 소스(`VT_SOURCES`)·`platform=="holodex"`·`VT_RE`(그룹명·용어 정규식) 중 하나. 새 버튜버 그룹을 다루게 되면 `VT_RE`에 더한다.
- 상단 "티켓 마감 임박"은 아직 오지 않은 시각만 보여준다: 3주 안의 `ticketOpen`/`deadline`, 기간형 분류는 5일 안의 `endDate`, 최대 10개. 지난 것은 바로 빠진다.

## 작업 규칙

- **봇이 쓰는 파일은 손으로 커밋하지 않는다** (`items.json`, `meta.json`, `trends.json`, `thumbs.json`, `thumbs/`, `.feedcache.json`). 봇이 `main`에 직접 푸시하므로 브랜치에서 이 파일을 건드리면 머지 충돌이 난다. 데이터를 고치고 싶으면 `manual.json`/`blocklist.json`/`anime.json`/`collector.py`를 고치고 봇 실행을 기다린다(또는 Actions에서 *Run workflow*).
- **로컬에서 수집기를 돌리면 `data/`가 바뀐다.** 테스트는 저장소를 다른 곳에 복사해서 돌리거나, 끝나고 `git checkout -- data`로 되돌린다. Pillow 외 의존성은 없고 Python 3.12 기준(Actions)이다.
- 이 저장소를 다루는 Claude Code 클라우드 세션에서는 외부 사이트 접근이 프록시에서 403으로 막혀 **모든 `site` 소스가 실패한다.** 수집기 실제 동작은 GitHub Actions 로그(`소식 자동 업데이트` 워크플로의 `소식 수집` 스텝 stderr)로 확인한다. 샌드박스에서의 403은 소스 장애가 아니다.
- 소스를 추가·삭제할 때는 `collector.py`의 `SOURCES`만 고친다. `site` 타입은 RSS를 못 찾으면 `rss` 타입으로 피드 주소를 직접 적는다. 사이트 RSS 주소가 바뀌었으면 `.feedcache.json`의 해당 키를 지운다(봇이 다음 실행에서 다시 찾는다). 고친 뒤에는 Actions의 "소스 점검"을 돌려 OK/FAIL을 본다.
- 꺼 둔 소스(주석)는 사유를 함께 적는다. 2026-10 기준: natalie.mu는 GitHub Actions의 요청을 405로 거부(해외 IP 차단으로 추정), アニメイトタイムズ·コミックマーケット·同人イベントNAVI는 RSS 자체가 없다. コラボカフェ는 RSS가 빈 응답이라 WP REST(`events` 글 타입)를, 電撃オンライン은 뉴스 사이트맵을, にじさんじ公式은 JSON API를 읽는다.
- 공연·이벤트·전시의 날짜·장소는 アニメハック 이벤트 캘린더(`ldjson`)에서 오고, e+ 등 예매 링크는 그 상세 페이지를 `enrich`가 열어 찾는다.
- 버튜버 소식은 PANORA·KAI-YOU(일반 뉴스)와 ホロライブ·にじさんじ·ぶいすぽっ 공식 뉴스에서 온다. 공식 소스에는 그룹명을 `works`로 붙여 두었으므로 페이지에서 작품 단위로 끄거나 점수를 줄 수 있다.
- 분류를 추가하면 세 곳을 함께 고친다: `collector.py`의 `CAT_RULES`, `index.html`의 `CATS`(필요하면 `PERIOD_CATS`/`EVENT_CATS`와 탭 렌더 함수), `README.md`의 category 설명. 소식 필드를 추가하면 `build()`와 `normalize()`를 함께 고친다.
- `index.html`은 한 파일을 유지한다. 빌드 도구·프레임워크·npm을 들이지 않는다. 외부 리소스는 Google Fonts와 방문자 집계용 GoatCounter 스크립트(`gc.zgo.at/count.js`, 대시보드 teraee.goatcounter.com) 둘뿐이며 더 늘리지 않는다.
- 다크 모드는 `prefers-color-scheme` + `:root[data-theme]` 토큰으로 동작한다. 색은 `:root` 변수로만 추가한다.
- 커밋 메시지는 기존대로 한국어 한 줄로 쓴다.

## 확인 방법 (자동 테스트 없음)

```bash
python3 -m py_compile collector.py                       # 문법
python3 collector.py --check                             # 소스별 OK/FAIL (파일은 쓰지 않음; 클라우드 세션에서는 전부 FAIL)
python3 -c "import json,glob;[json.load(open(f)) for f in glob.glob('data/*.json')]"   # JSON 유효성
python3 -m http.server 8000                              # 페이지는 file://에서 fetch가 막히므로 서버로 열어 확인
```

워크플로 전체 확인은 Actions → "소식 자동 업데이트" → *Run workflow*. 비밀값 `ANNICT_TOKEN`, `HOLODEX_API_KEY`는 선택이며 없어도 뉴스 수집은 동작한다.
