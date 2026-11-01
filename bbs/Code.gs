// 마토메 보드 게시판 백엔드 (Google Apps Script 웹 앱)
// 보통은 이 파일 대신 bbs/Loader.gs(이 파일을 GitHub 에서 읽어 실행하는 로더)를 붙여 넣는다. 그러면 이 파일을 고쳐도 다시 붙여 넣거나 배포할 필요가 없다.
// 직접 쓰려면 스프레드시트의 확장 프로그램 → Apps Script 에 이 파일을 붙여 넣고,
// 배포 → 새 배포 → 유형 "웹 앱" → 실행 사용자 "나" → 액세스 권한 "모든 사용자" 로 배포한다.
// 나온 웹 앱 URL(https://script.google.com/macros/s/…/exec)을 index.html 의 BBS.api 에 적는다.
// 글은 'posts' 시트에 [시각, 이름, 내용] 으로 쌓이고, 지우려면 그 행을 지우면 된다.
// 弾幕 스코어 보드도 같은 웹 앱을 쓴다: 'scores' 시트에 [시각, 이름, 점수, 스테이지, 스킨, 클리어] 로 쌓인다.
// 이 파일을 고친 뒤에는 배포 → 배포 관리 → 수정(연필) → 버전 "새 버전" → 배포 로 다시 배포해야 반영된다(주소는 그대로).
//
// 어느 스프레드시트에 쓰나: ① 아래 SHEET_ID 에 적은 시트(주소 /d/ 와 /edit 사이의 긴 글자)
//   ② 비어 있으면 이 스크립트가 붙은 스프레드시트(확장 프로그램 → Apps Script 로 만든 경우)
//   ③ 그것도 없으면(script.google.com 에서 따로 만든 프로젝트) 처음 실행할 때 '마토메 보드 게시판' 스프레드시트를 새로 만들어 쓴다.
// 편집기에서 setup 함수를 한 번 실행하면 권한 승인과 함께 실행 로그에 쓰는 스프레드시트 주소가 찍힌다.
// 웹 앱 주소를 브라우저로 열었을 때 {"error":"…"} 가 나오면 그 내용이 실패 원인이다.
const SHEET_ID = '';
// 예전 게시판 웹 앱(2026-10 처음 배포한 스프레드시트). 지금 시트의 posts 가 비어 있으면 처음 한 번 여기서 글(최신 500건)과
// 스코어 보드 기록(TOP 50)을 가져와 채운다(migrate_). 같은 스프레드시트를 그대로 쓰는 경우엔 글이 이미 있어 건너뛴다.
const OLD_API = 'https://script.google.com/macros/s/AKfycbzsQ78kMCaXtkS5lIWpCC_dCnI3mn0GDLmqmUmQ7OYh7cW4kG-FYW1UsoTEASmgkVdt/exec';

const SHEET = 'posts';
const MAX_TEXT = 500, MAX_NAME = 20, PAGE = 200;
const SCORES = 'scores', SCORE_NAME = 12, SCORE_MAX = 99999999, SCORE_TOP = 50, SCORE_SCAN = 3000;

function book_() {
  if (SHEET_ID) return SpreadsheetApp.openById(SHEET_ID);
  const own = SpreadsheetApp.getActiveSpreadsheet();
  if (own) return own;
  const props = PropertiesService.getScriptProperties();
  const id = props.getProperty('SHEET_ID');
  if (id) return SpreadsheetApp.openById(id);
  const ss = SpreadsheetApp.create('마토메 보드 게시판');
  props.setProperty('SHEET_ID', ss.getId());
  return ss;
}

function setup() {
  const ss = book_();
  sheet_(); scoreSheet_(); tkShowSheet_(); tkEntrySheet_();
  migrate_(true);
  Logger.log('스프레드시트: ' + ss.getUrl());
}

function sheet_(name, head) {
  const ss = book_();
  let sh = ss.getSheetByName(name || SHEET);
  if (!sh) { sh = ss.insertSheet(name || SHEET); sh.appendRow(head || ['시각', '이름', '내용']); }
  return sh;
}
// 게임별 기록 시트. dm=弾幕 NORMAL·dm_l=弾幕 LUNATIC(stage 1~5), suika·2048=Holo Mobile(stage 칸에 최고 구슬·최고 타일 값 2~, clear=2048 달성)
const GAMES = {
  dm: { sheet: SCORES, stage: 5, head: ['시각', '이름', '점수', '스테이지', '스킨', '클리어'] },
  dm_l: { sheet: 'scores_lunatic', stage: 5, head: ['시각', '이름', '점수', '스테이지', '스킨', '클리어'] }, // 弾幕 LUNATIC
  suika: { sheet: 'scores_suika', stage: 131072, head: ['시각', '이름', '점수', '최고 구슬', '', '2048 달성'] },
  '2048': { sheet: 'scores_2048', stage: 131072, head: ['시각', '이름', '점수', '최고 타일', '', '2048 달성'] },
  derby: { sheet: 'scores_derby', stage: 7, head: ['시각', '이름', '점수', '레이스', '선수', 'URA 제패'] }, // まとめダービー
  run: { sheet: 'scores_run', stage: 99, head: ['시각', '이름', '점수', '스테이지', '선수', ''] }, // まとめラン(2026-10 ダービー를 대체)
  pen: { sheet: 'scores_pen', stage: 4, head: ['시각', '이름', '점수', '난이도', '곡:난이도', '풀콤보'] }, // ペンライト・オンステージ(skin 으로 곡·난이도별 순위)
  ensei: { sheet: 'scores_ensei', stage: 30, head: ['시각', '이름', '점수', '방문', '원정 날짜', ''] }, // 도쿄 원정 대작전(skin = 그 주 원정 날짜, 주마다 순위)
};
const game_ = g => GAMES[g] ? g : 'dm';
function scoreSheet_(g) { const G = GAMES[game_(g)]; return sheet_(G.sheet, G.head); }

// GET ?limit=200 → {posts:[{at,name,text}]} 최신 글부터
// GET ?scores=1&limit=30[&game=suika|2048|pen|ensei][&skin=…] → {scores:[{at,name,score,stage,skin,clear}]} 점수 높은 순(같은 점수는 먼저 올린 기록이 위)
function doGet(e) { return safe_(() => get_(e)); }
function doPost(e) { return safe_(() => post_(e)); }
// 실패하면 구글의 HTML 오류 화면 대신 {"error":"…"} JSON 을 돌려줘 페이지와 브라우저에서 원인이 보이게 한다
function safe_(f) { try { return f(); } catch (err) { return out_({ ok: false, error: String(err && err.message || err) }); } }

function get_(e) {
  migrate_(false);
  const p = (e && e.parameter) || {};
  if (p.scores) return out_({ scores: topScores_(Math.min(Number(p.limit || 30) || 30, SCORE_TOP), p.game, p.skin) });
  if (p.tips) return out_({ tips: tips_() });
  if (p.tk === 'ics') return tkIcs_(p.tok);  // 티켓 트래커 개인 달력(구독용)
  if (p.tk) return out_(tkAll_());            // 티켓 트래커 공연·기록 전부
  const sh = sheet_();
  const n = Math.min(Number((e && e.parameter && e.parameter.limit) || PAGE), 500);
  const last = sh.getLastRow();
  const rows = last > 1 ? sh.getRange(Math.max(2, last - n + 1), 1, Math.min(n, last - 1), 3).getValues() : [];
  const posts = rows.reverse().map(r => ({ at: fmt_(r[0]), name: String(r[1] || '익명'), text: String(r[2] || '') }));
  return out_({ posts });
}

// POST 본문 {"name":"…","text":"…"} → 한 행 추가. 수정·삭제 API 는 없다(게시 후 변경 불가).
function post_(e) {
  let d = {};
  try { d = JSON.parse((e && e.postData && e.postData.contents) || '{}'); } catch (err) {}
  if (d.type === 'score') return addScore_(d);
  if (d.type === 'tip') return addTip_(d);
  if (d.type === 'tk_show') return tkShow_(d.show || {});
  if (d.type === 'tk_entry') return tkEntry_(d.entry || {});
  const name = String(d.name || '익명').trim().slice(0, MAX_NAME) || '익명';
  const text = String(d.text || '').trim().slice(0, MAX_TEXT);
  if (!text) return out_({ ok: false, error: 'empty' });
  const lock = LockService.getScriptLock();
  lock.waitLock(5000);
  try { sheet_().appendRow([new Date(), noFormula_(name), noFormula_(text)]); } finally { lock.releaseLock(); }
  return out_({ ok: true });
}

// 최근 SCORE_SCAN 행만 읽어 정렬한다(시트가 아주 커져도 느려지지 않게). 지우려면 그 행을 지우면 된다.
function topScores_(n, g, skin) { // skin 을 주면 그 값인 기록만(펜라이트 곡·난이도, 도쿄 원정 주)
  const sh = scoreSheet_(g);
  const last = sh.getLastRow();
  if (last < 2) return [];
  const k = Math.min(SCORE_SCAN, last - 1);
  const rows = sh.getRange(last - k + 1, 1, k, 7).getValues(); // 7번째 칸 = 칭호(예전 기록은 빈 칸)
  return rows.map((r, i) => ({ i, at: r[0], name: String(r[1] || '익명'), score: Number(r[2]) || 0, stage: Number(r[3]) || 1, skin: String(r[4] || ''), clear: r[5] === true || r[5] === 'TRUE' || r[5] === 1, title: String(r[6] || '').slice(0, 12) }))
    .filter(r => r.score > 0 && (!skin || r.skin === String(skin).slice(0, 12)))
    .sort((a, b) => b.score - a.score || a.i - b.i)
    .slice(0, n)
    .map(r => ({ at: fmt_(r.at).slice(0, 10), name: r.name, score: r.score, stage: r.stage, skin: r.skin, clear: r.clear, title: r.title }));
}

// POST {"type":"score","game":"dm|suika|2048","name":"…","score":123,"stage":3,"skin":"릴리","clear":false,"title":"칭호(선택)"}
function addScore_(d) {
  const g = game_(d.game);
  const name = String(d.name || '').replace(/\s+/g, ' ').trim().slice(0, SCORE_NAME);
  const score = Math.floor(Number(d.score));
  const stage = Math.max(1, Math.min(GAMES[g].stage, Math.floor(Number(d.stage)) || 1));
  const skin = String(d.skin || '').trim().slice(0, 12);
  const title = String(d.title || '').replace(/\s+/g, ' ').trim().slice(0, 12); // 칭호(2026-10 말 업적): 7번째 칸
  if (!name) return out_({ ok: false, error: 'name' });
  if (!(score > 0 && score <= SCORE_MAX)) return out_({ ok: false, error: 'score' });
  const lock = LockService.getScriptLock();
  lock.waitLock(5000);
  try { scoreSheet_(g).appendRow([new Date(), noFormula_(name), score, stage, noFormula_(skin), d.clear === true, noFormula_(title)]); } finally { lock.releaseLock(); }
  return out_({ ok: true });
}

// 소식 제보(2026-10 말): 보드 사이트 개요의 '소식 제보'가 POST {"type":"tip","url":"https://…","note":"메모"}.
// tips 시트에 [시각, 주소, 메모, 상태]. 상태 칸에 no 를 적으면 숨김(수집기에 안 감). 수집기(collector.py)가 GET ?tips=1 로 최근 60일 것을 읽어
// X 글은 본문을, 그 밖은 페이지 제목을 읽어 소식으로 만든다.
const TIPS = 'tips';
function tipSheet_() { return sheet_(TIPS, ['시각', '주소', '메모', '상태(no=숨김)']); }
function addTip_(d) {
  const url = String(d.url || '').trim().slice(0, 300);
  const note = String(d.note || '').replace(/\s+$/, '').slice(0, 300);
  if (!/^https?:\/\/[^\s]+$/.test(url)) return out_({ ok: false, error: 'url' });
  const lock = LockService.getScriptLock();
  lock.waitLock(5000);
  try { tipSheet_().appendRow([new Date(), noFormula_(url), noFormula_(note), '']); } finally { lock.releaseLock(); }
  return out_({ ok: true });
}
function tips_() {
  const sh = tipSheet_();
  const last = sh.getLastRow();
  if (last < 2) return [];
  const k = Math.min(300, last - 1), since = Date.now() - 60 * 864e5;
  return sh.getRange(last - k + 1, 1, k, 4).getValues()
    .filter(r => String(r[3] || '').trim().toLowerCase() !== 'no' && new Date(r[0]).getTime() > since && String(r[1] || ''))
    .reverse().map(r => ({ at: fmt_(r[0]), url: String(r[1]), note: String(r[2] || '') }));
}

// ---- 티켓 트래커(tickets/, 2026-11) ----
// 공연(tk_shows)과 친구별 응모 기록(tk_entries). 두 시트 다 행을 '추가만' 하고(게시판과 같은 방식) 같은 id 의 마지막 행이 지금 값이다(지우기도 del 행 추가).
// 기록 id = 공연id.단계번호.key, key = sha1(그 브라우저의 토큰)[:8]. 토큰은 시트에만 두고 GET 으로는 key 만 내보내 남의 칸을 못 고친다.
// GET ?tk=1 → {shows:[…], entries:[…]}(공연 날짜가 150일 넘게 지난 것은 뺌)  /  GET ?tk=ics&tok=… → 그 토큰의 기한 달력(ics, 구독용)
// POST {type:'tk_show', show:{id,title,date,venue,url,boardId,phases:[{n,kind,s,e,r,p,site,url}],by,del}}  — 공연은 친구 누구나 고친다
// POST {type:'tk_entry', entry:{showId,phase,tok,who,st,n,area,note,del}}   — 자기 토큰의 칸만
const TK_SHOWS = 'tk_shows', TK_ENTRIES = 'tk_entries', TK_SCAN = 4000, TK_DAYS = 150, TK_PH = 8;
const TK_KIND = ['lottery', 'first', 'general', 'resale'], TK_ST = ['plan', 'applied', 'won', 'lost', 'paid', 'want', 'give', 'drop'];
function tkShowSheet_() { return sheet_(TK_SHOWS, ['시각', '공연 id', '제목', 'JSON']); }
function tkEntrySheet_() { return sheet_(TK_ENTRIES, ['시각', '기록 id', '공연 id', '이름', '토큰', 'JSON']); }
function tkKey_(tok) {
  const b = Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_1, String(tok || ''), Utilities.Charset.UTF_8);
  return b.slice(0, 4).map(x => ('0' + ((x + 256) % 256).toString(16)).slice(-2)).join('');
}
const tkStr_ = (v, n) => String(v == null ? '' : v).replace(/\s+/g, ' ').trim().slice(0, n);
const tkDate_ = v => /^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2})?$/.test(String(v || '')) ? String(v) : '';
const tkUrl_ = v => /^https?:\/\/\S{1,300}$/.test(String(v || '')) ? String(v) : '';
function tkPhase_(p) {
  if (!p || typeof p !== 'object') return null;
  const n = tkStr_(p.n, 30); if (!n) return null;
  return { n, kind: TK_KIND.includes(p.kind) ? p.kind : 'lottery', s: tkDate_(p.s), e: tkDate_(p.e), r: tkDate_(p.r), p: tkDate_(p.p), site: tkStr_(p.site, 20), url: tkUrl_(p.url) };
}
function tkShow_(x) {
  const id = tkStr_(x.id, 24); if (!/^[\w-]{4,24}$/.test(id)) return out_({ ok: false, error: 'id' });
  const show = { id, title: tkStr_(x.title, 120), date: tkDate_(x.date), end: tkDate_(x.end), venue: tkStr_(x.venue, 80), url: tkUrl_(x.url), boardId: tkStr_(x.boardId, 20),
    phases: (Array.isArray(x.phases) ? x.phases : []).map(tkPhase_).filter(Boolean).slice(0, TK_PH), by: tkStr_(x.by, 12), del: x.del === true, at: fmt_(new Date()) };
  if (!show.title && !show.del) return out_({ ok: false, error: 'title' });
  const lock = LockService.getScriptLock(); lock.waitLock(5000);
  try { tkShowSheet_().appendRow([new Date(), id, noFormula_(show.title), JSON.stringify(show)]); } finally { lock.releaseLock(); }
  return out_({ ok: true, show });
}
function tkEntry_(x) {
  const showId = tkStr_(x.showId, 24), tok = tkStr_(x.tok, 48), phase = Math.floor(Number(x.phase));
  if (!/^[\w-]{4,24}$/.test(showId)) return out_({ ok: false, error: 'showId' });
  if (tok.length < 8) return out_({ ok: false, error: 'tok' });
  if (!(phase >= 0 && phase < TK_PH)) return out_({ ok: false, error: 'phase' });
  const key = tkKey_(tok), id = showId + '.' + phase + '.' + key;
  const e = { id, showId, phase, key, who: tkStr_(x.who, 12) || '익명', st: TK_ST.includes(x.st) ? x.st : 'plan', n: Math.max(1, Math.min(8, Math.floor(Number(x.n)) || 1)),
    area: tkStr_(x.area, 16), note: tkStr_(x.note, 80), del: x.del === true, at: fmt_(new Date()) };
  const lock = LockService.getScriptLock(); lock.waitLock(5000);
  try { tkEntrySheet_().appendRow([new Date(), id, showId, noFormula_(e.who), tok, JSON.stringify(e)]); } finally { lock.releaseLock(); }
  return out_({ ok: true, entry: e });
}
function tkRows_(sh, col) { // 최근 TK_SCAN 행을 읽어 같은 id 의 마지막 행만
  const last = sh.getLastRow(); if (last < 2) return [];
  const k = Math.min(TK_SCAN, last - 1), m = {};
  sh.getRange(last - k + 1, 1, k, col).getValues().forEach(r => { try { const o = JSON.parse(r[col - 1]); if (o && o.id) m[o.id] = o; } catch (err) {} });
  return Object.values(m);
}
function tkAll_() {
  const since = Date.now() - TK_DAYS * 864e5;
  const shows = tkRows_(tkShowSheet_(), 4).filter(s => !s.del && (!s.date || new Date((s.end || s.date) + (s.date.length > 10 ? '' : 'T23:59') + '+09:00').getTime() > since));
  const ids = new Set(shows.map(s => s.id));
  const entries = tkRows_(tkEntrySheet_(), 6).filter(e => !e.del && ids.has(e.showId)).map(e => ({ id: e.id, showId: e.showId, phase: e.phase, key: e.key, who: e.who, st: e.st, n: e.n, area: e.area, note: e.note, at: e.at }));
  return { shows, entries, at: fmt_(new Date()) };
}
// 개인 달력: 그 토큰의 기록이 있는 단계의 접수 마감·결과 발표·결제 기한·리세일 오픈을 일정으로(1시간 전·하루 전 알림). 폰 달력에 구독하면 알림이 온다.
function tkIcs_(tok) {
  const key = tkKey_(String(tok || '')), all = tkAll_(), byId = {}; all.shows.forEach(s => byId[s.id] = s);
  const esc = t => String(t || '').replace(/\\/g, '\\\\').replace(/;/g, '\\;').replace(/,/g, '\\,').replace(/\n/g, '\\n');
  const ts = v => { const d = new Date(v + (v.length > 10 ? '' : 'T00:00') + '+09:00'); return Utilities.formatDate(d, 'UTC', "yyyyMMdd'T'HHmmss'Z'"); };
  const stKo = { plan: '예정', applied: '응모함', won: '당첨', lost: '낙선', paid: '결제 완료', want: '양도 구함', give: '양도 가능', drop: '포기' };
  const L = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//matome-board//tickets//KO', 'CALSCALE:GREGORIAN', 'X-WR-CALNAME:마토메 티켓 기한', 'X-WR-TIMEZONE:Asia/Tokyo', 'REFRESH-INTERVAL;VALUE=DURATION:PT3H'];
  all.entries.filter(e => e.key === key && !['lost', 'drop'].includes(e.st)).forEach(e => {
    const s = byId[e.showId], ph = s && s.phases[e.phase]; if (!ph) return;
    const evs = [];
    if (ph.e && ['plan', 'applied', 'want', 'give'].includes(e.st)) evs.push(['e', ph.e, '접수 마감']);
    if (ph.s && ['plan', 'want', 'give'].includes(e.st)) evs.push(['s', ph.s, ph.kind === 'resale' ? '리세일 오픈' : '접수 시작']);
    if (ph.r && ['applied', 'plan'].includes(e.st)) evs.push(['r', ph.r, '결과 발표']);
    if (ph.p && ['won', 'applied'].includes(e.st)) evs.push(['p', ph.p, '결제 기한']);
    evs.forEach(([k, v, lab]) => {
      L.push('BEGIN:VEVENT', 'UID:' + e.id + '-' + k + '@matome-tickets', 'DTSTAMP:' + ts(all.at.replace(' ', 'T')), 'DTSTART:' + ts(v),
        'SUMMARY:' + esc('[' + lab + '] ' + s.title + ' · ' + ph.n), 'DESCRIPTION:' + esc('내 상태: ' + (stKo[e.st] || e.st) + (e.n ? ' · ' + e.n + '매' : '') + (ph.url ? '\n' + ph.url : '')),
        'BEGIN:VALARM', 'ACTION:DISPLAY', 'TRIGGER:-PT1H', 'DESCRIPTION:' + esc(lab + ' 1시간 전'), 'END:VALARM',
        'BEGIN:VALARM', 'ACTION:DISPLAY', 'TRIGGER:-P1D', 'DESCRIPTION:' + esc(lab + ' 하루 전'), 'END:VALARM', 'END:VEVENT');
    });
  });
  L.push('END:VCALENDAR');
  return ContentService.createTextOutput(L.join('\r\n') + '\r\n').setMimeType(ContentService.MimeType.ICAL);
}

// = + - @ 로 시작하는 글자는 시트가 수식으로 읽으므로 ' 를 붙여 글자로 둔다(읽을 때는 ' 없이 나온다)
function noFormula_(v) { return /^[=+\-@]/.test(v) ? "'" + v : v; }
// 예전 웹 앱의 글·기록을 한 번만 옮긴다. 지금 시트에 이미 있는 글과 겹치는 것(같은 분·이름·내용)은 빼고 합쳐 시각 순으로 다시 쓴다.
// 끝나면 스크립트 속성 MIGRATED=1, 실패하면 1시간 뒤 다시 시도(MIGRATE_TRY).
function migrate_(force) {
  const props = PropertiesService.getScriptProperties();
  if (!OLD_API || props.getProperty('MIGRATED')) return;
  if (!force && Date.now() - Number(props.getProperty('MIGRATE_TRY') || 0) < 3600e3) return;
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(10000)) return;
  try {
    if (props.getProperty('MIGRATED')) return;
    props.setProperty('MIGRATE_TRY', String(Date.now()));
    const get = q => { const r = UrlFetchApp.fetch(OLD_API + q, { muteHttpExceptions: true, followRedirects: true });
      if (r.getResponseCode() !== 200) throw new Error('예전 웹 앱 응답 ' + r.getResponseCode()); return JSON.parse(r.getContentText()); };
    const when = at => { const d = new Date(String(at || '').replace(' ', 'T') + ':00+09:00'); return isNaN(d) ? new Date() : d; };
    const posts = (get('?limit=500').posts || [])
      .map(p => [when(p.at), String(p.name || '익명').slice(0, MAX_NAME), String(p.text || '').slice(0, MAX_TEXT)]).filter(r => r[2]);
    const np = merge_(sheet_(), 3, posts, r => fmt_(r[0]) + '|' + r[1] + '|' + r[2]);
    let scores = [];
    try { scores = get('?scores=1&limit=50').scores || []; } catch (err) {} // 예전 웹 앱에 스코어 보드가 없으면 건너뜀
    const rows = (Array.isArray(scores) ? scores : []).map(v => [when(String(v.at || '').slice(0, 10) + ' 00:00'), String(v.name || '').slice(0, SCORE_NAME),
      Math.floor(Number(v.score)) || 0, Math.max(1, Math.min(5, Number(v.stage) || 1)), String(v.skin || '').slice(0, 12), v.clear === true])
      .filter(r => r[1] && r[2] > 0 && r[2] <= SCORE_MAX);
    const ns = merge_(scoreSheet_(), 6, rows, r => r[1] + '|' + r[2] + '|' + r[3]);
    props.setProperty('MIGRATED', '1');
    Logger.log('예전 게시판에서 글 ' + np + '건, 기록 ' + ns + '건을 옮겼습니다.');
  } catch (err) {
    Logger.log('옮기기 실패: ' + err); // 다음 시도까지 게시판은 평소처럼 동작
  } finally { lock.releaseLock(); }
}
// 시트의 기존 행과 새 행을 key 로 겹침을 빼고 합쳐 첫 칸(시각) 순으로 다시 쓴다. 더한 행 수를 돌려준다.
function merge_(sh, cols, add, key) {
  const last = sh.getLastRow();
  const cur = last > 1 ? sh.getRange(2, 1, last - 1, cols).getValues() : [];
  const seen = {};
  cur.forEach(r => { seen[key(r)] = 1; });
  const fresh = add.filter(r => { const k = key(r); if (seen[k]) return false; seen[k] = 1; return true; });
  if (!fresh.length) return 0;
  const all = cur.concat(fresh).sort((a, b) => new Date(a[0]) - new Date(b[0]))
    .map(r => r.map(v => typeof v === 'string' ? noFormula_(v) : v)); // 다시 쓸 때 = 로 시작하는 글이 수식이 되지 않게
  sh.getRange(2, 1, all.length, cols).setValues(all);
  return fresh.length;
}

function fmt_(d) { return Utilities.formatDate(new Date(d), 'Asia/Tokyo', 'yyyy-MM-dd HH:mm'); }
function out_(obj) { return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON); }
