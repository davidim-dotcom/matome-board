// 마토메 보드 게시판 백엔드 (Google Apps Script 웹 앱)
// 스프레드시트의 확장 프로그램 → Apps Script 에 이 파일을 붙여 넣고,
// 배포 → 새 배포 → 유형 "웹 앱" → 실행 사용자 "나" → 액세스 권한 "모든 사용자" 로 배포한다.
// 나온 웹 앱 URL(https://script.google.com/macros/s/…/exec)을 index.html 의 BBS.api 에 적는다.
// 글은 'posts' 시트에 [시각, 이름, 내용] 으로 쌓이고, 지우려면 그 행을 지우면 된다.

const SHEET = 'posts';
const MAX_TEXT = 500, MAX_NAME = 20, PAGE = 200;

function sheet_() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sh = ss.getSheetByName(SHEET);
  if (!sh) { sh = ss.insertSheet(SHEET); sh.appendRow(['시각', '이름', '내용']); }
  return sh;
}

// GET ?limit=200 → {posts:[{at,name,text}]} 최신 글부터
function doGet(e) {
  const sh = sheet_();
  const n = Math.min(Number((e && e.parameter && e.parameter.limit) || PAGE), 500);
  const last = sh.getLastRow();
  const rows = last > 1 ? sh.getRange(Math.max(2, last - n + 1), 1, Math.min(n, last - 1), 3).getValues() : [];
  const posts = rows.reverse().map(r => ({ at: fmt_(r[0]), name: String(r[1] || '익명'), text: String(r[2] || '') }));
  return out_({ posts });
}

// POST 본문 {"name":"…","text":"…"} → 한 행 추가. 수정·삭제 API 는 없다(게시 후 변경 불가).
function doPost(e) {
  let d = {};
  try { d = JSON.parse((e && e.postData && e.postData.contents) || '{}'); } catch (err) {}
  const name = String(d.name || '익명').trim().slice(0, MAX_NAME) || '익명';
  const text = String(d.text || '').trim().slice(0, MAX_TEXT);
  if (!text) return out_({ ok: false, error: 'empty' });
  const lock = LockService.getScriptLock();
  lock.waitLock(5000);
  try { sheet_().appendRow([new Date(), name, text]); } finally { lock.releaseLock(); }
  return out_({ ok: true });
}

function fmt_(d) { return Utilities.formatDate(new Date(d), 'Asia/Tokyo', 'yyyy-MM-dd HH:mm'); }
function out_(obj) { return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON); }
