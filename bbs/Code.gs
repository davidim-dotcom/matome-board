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
  sheet_(); scoreSheet_();
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
