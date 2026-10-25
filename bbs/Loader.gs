// 마토메 보드 게시판·스코어 보드 로더 (Google Apps Script)
// 이 짧은 파일만 Apps Script 에 한 번 붙여 넣고 웹 앱으로 배포하면, 실제 코드는 GitHub 의 bbs/Code.gs 를 읽어 실행한다.
// 그래서 Code.gs 가 바뀌어도 다시 붙여 넣거나 다시 배포할 필요가 없다(10분 캐시 뒤 자동 반영).
const SRC = 'https://raw.githubusercontent.com/davidim-dotcom/matome-board/main/bbs/Code.gs';

function api_() {
  const cache = CacheService.getScriptCache();
  let code = cache.get('code');
  if (!code) {
    code = UrlFetchApp.fetch(SRC).getContentText();
    try { cache.put('code', code, 600); } catch (e) {}
  }
  return new Function(code + '\nreturn { doGet, doPost, setup };')();
}
function doGet(e) { return api_().doGet(e); }
function doPost(e) { return api_().doPost(e); }
function setup() { CacheService.getScriptCache().remove('code'); api_().setup(); }

// 실행하지 않는 함수. Apps Script 가 필요한 권한(스프레드시트·잠금·속성)을 알아보도록 이름만 적어 둔다.
function scopes_() { SpreadsheetApp.openById(''); SpreadsheetApp.create(''); LockService.getScriptLock(); PropertiesService.getScriptProperties(); }
