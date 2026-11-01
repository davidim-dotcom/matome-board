#!/usr/bin/env node
// 티켓 트래커 백엔드 점검 — bbs/Code.gs 의 tk API(공연·기록 추가, 같은 id 덮어쓰기, 토큰 숨김, 지우기, 개인 달력 ics)를
// 가짜 Apps Script 서비스(시트는 배열, sha1 은 node crypto)로 돌려 본다. node tests/tkcheck.js
const fs = require("fs"), crypto = require("crypto"), path = require("path");
const code = fs.readFileSync(path.join(path.dirname(__dirname), "bbs", "Code.gs"), "utf-8");
const bad = [], check = (ok, msg) => { console.log((ok ? "OK   " : "FAIL ") + msg); if (!ok) bad.push(msg); };
const sheets = {};
const mkSheet = name => ({ rows: [], getLastRow() { return this.rows.length }, appendRow(r) { this.rows.push(r) },
  getRange(r0, c0, n, cols) { const rows = this.rows.slice(r0 - 1, r0 - 1 + n).map(r => r.slice(c0 - 1, c0 - 1 + cols)); return { getValues: () => rows } } });
const SpreadsheetApp = { getActiveSpreadsheet: () => ({ getSheetByName: n => sheets[n] || null, insertSheet: n => { sheets[n] = mkSheet(n); return sheets[n] }, getUrl: () => "x" }), openById: () => null };
const PropertiesService = { getScriptProperties: () => ({ getProperty: () => "1", setProperty() {} }) };
const LockService = { getScriptLock: () => ({ waitLock() {}, releaseLock() {} }) };
const Utilities = { DigestAlgorithm: { SHA_1: 1 }, Charset: { UTF_8: 1 },
  computeDigest: (a, s) => [...crypto.createHash("sha1").update(s, "utf8").digest()].map(b => b > 127 ? b - 256 : b),
  formatDate: (d, tz, fmt) => { const p = new Intl.DateTimeFormat("en-CA", { timeZone: tz, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false }).formatToParts(d), g = t => p.find(x => x.type === t).value;
    return fmt.includes("'T'") ? `${g("year")}${g("month")}${g("day")}T${g("hour")}${g("minute")}${g("second")}Z` : `${g("year")}-${g("month")}-${g("day")} ${g("hour")}:${g("minute")}` } };
const ContentService = { MimeType: { JSON: "json", ICAL: "ical" }, createTextOutput: t => ({ t, setMimeType(m) { this.m = m; return this } }) };
const UrlFetchApp = { fetch: () => { throw new Error("no net") } };
const api = new Function("SpreadsheetApp", "PropertiesService", "LockService", "Utilities", "ContentService", "UrlFetchApp", code + "\nreturn {doGet, doPost, tkKey_};")(SpreadsheetApp, PropertiesService, LockService, Utilities, ContentService, UrlFetchApp);
const post = d => JSON.parse(api.doPost({ postData: { contents: JSON.stringify(d) } }).t), get = p => api.doGet({ parameter: p });
let r = post({ type: "tk_show", show: { id: "i1abc2", title: "테스트 공연", date: "2026-12-19T18:00", venue: "東京ドーム", url: "https://example.com/x", boardId: "i1abc2",
  phases: [{ n: "FC先行抽選", kind: "lottery", s: "2026-11-05T12:00", e: "2026-11-10T23:59", r: "2026-11-14T18:00", p: "2026-11-17T23:59", site: "e+", url: "https://eplus.jp/x" }, { n: "一般発売", kind: "general", s: "2026-11-29T10:00" }, { n: "bad", kind: "zzz", s: "nope" }], by: "테라" } });
check(r.ok && r.show.phases.length === 3 && r.show.phases[2].kind === "lottery" && r.show.phases[2].s === "", "공연 추가: 단계 종류·날짜 형식 검사");
check(post({ type: "tk_show", show: { id: "a b", title: "x" } }).error === "id", "공연 추가: 잘못된 id 거절");
r = post({ type: "tk_entry", entry: { showId: "i1abc2", phase: 0, tok: "token-abcdefgh-1234", who: "테라", st: "applied", n: 2, note: "친구랑" } });
check(r.ok && r.entry.id === "i1abc2.0." + api.tkKey_("token-abcdefgh-1234"), "기록 추가: id = 공연.단계.key");
post({ type: "tk_entry", entry: { showId: "i1abc2", phase: 0, tok: "token-abcdefgh-1234", who: "테라", st: "won", n: 2 } }); // 같은 칸 갱신
post({ type: "tk_entry", entry: { showId: "i1abc2", phase: 0, tok: "other-token-xyz", who: "친구", st: "lost" } });
post({ type: "tk_entry", entry: { showId: "i1abc2", phase: 1, tok: "other-token-xyz", who: "친구", st: "plan", del: true } });
const all = JSON.parse(get({ tk: "1" }).t);
check(all.shows.length === 1 && all.entries.length === 2 && all.entries.find(e => e.who === "테라").st === "won", "전체 읽기: 같은 칸은 마지막 행, 지운 기록은 빠짐");
check(!JSON.stringify(all).includes("token-"), "전체 읽기: 토큰이 새지 않음");
const ics = get({ tk: "ics", tok: "token-abcdefgh-1234" });
check(ics.m === "ical" && (ics.t.match(/BEGIN:VEVENT/g) || []).length === 1 && /SUMMARY:\[결제 기한\]/.test(ics.t) && /DTSTART:20261117T145900Z/.test(ics.t), "개인 달력: 당첨 → 결제 기한 일정(JST → UTC)");
post({ type: "tk_show", show: { id: "i1abc2", title: "테스트 공연", del: true } });
check(JSON.parse(get({ tk: "1" }).t).shows.length === 0, "공연 지우기");
console.log(bad.length ? `→ 실패 ${bad.length}건` : "→ 티켓 트래커 백엔드 통과"); process.exit(bad.length ? 1 : 0);
