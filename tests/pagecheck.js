#!/usr/bin/env node
// 페이지 점검 — 실제 브라우저(Chromium, 폰 크기)로 index.html 을 열어 탭마다 스크립트 오류·화면 가로 넘침·빈 화면을 본다.
// .github/workflows/test.yml 이 PR 마다 돌리고, 로컬에서는  node tests/pagecheck.js  (playwright 필요. 브라우저 경로는 PW_CHROMIUM 으로 지정 가능)
// 저장소 루트를 정적 서버(python3 -m http.server)로 띄워 data/ 를 그대로 읽는다. 바깥 사이트(글꼴·그림·게시판)는 못 불러와도 실패로 치지 않는다.
const { spawn } = require("child_process");
const path = require("path");
const { chromium, devices } = require("playwright");

const ROOT = path.dirname(__dirname);
const PORT = 8799;
const TABS = ["feed", "sched", "weekly", "works", "buzz", "anime", "comics", "about", "game", "g2048", "derby", "pen", "ensei"];
const DEVS = ["Pixel 7", "iPhone SE"];  // 보통 폰(412px)과 좁은 폰(320px)
const bad = [];

function serve() {
  const p = spawn("python3", ["-m", "http.server", String(PORT), "--bind", "127.0.0.1"], { cwd: ROOT, stdio: "ignore" });
  return new Promise((ok) => setTimeout(() => ok(p), 800));
}

// 화면 오른쪽 밖으로 나간 요소(고정 요소와 overflow 로 잘리는 부모 안은 제외) — 2026-10 폰에서 페이지가 옆으로 밀린 문제
const OVERFLOW = () => {
  const W = document.documentElement.clientWidth, out = [];
  for (const e of document.querySelectorAll("body *")) {
    const r = e.getBoundingClientRect();
    if (!r.width || r.right <= W + 1 || !e.offsetParent || getComputedStyle(e).position === "fixed") continue;
    let a = e.parentElement, clip = false;  // overflow 로 잘리는 부모 안, 고정 요소(마스코트 등) 안은 페이지를 밀지 않는다
    while (a && a !== document.body) { const cs = getComputedStyle(a); if (cs.overflowX !== "visible" || cs.position === "fixed") { clip = true; break; } a = a.parentElement; }
    if (!clip) out.push(`${e.tagName.toLowerCase()}${e.id ? "#" + e.id : ""}.${e.className} right=${Math.round(r.right)}>${W}`);
  }
  return out.slice(0, 5);
};

async function run(dev) {
  const browser = await chromium.launch(process.env.PW_CHROMIUM
    ? { executablePath: process.env.PW_CHROMIUM, ignoreDefaultArgs: ["--headless=old"], args: ["--headless=new"] } : {});
  const ctx = await browser.newContext({ ...devices[dev] });
  await ctx.addInitScript(() => {  // 지난 방문·내 작품이 있을 때의 화면(새 소식 띠·내 작품 칩)도 그려 보게
    try { localStorage.setItem("matome-visit", JSON.stringify({ prev: Date.now() - 36e5, cur: Date.now() - 36e5 }));
          localStorage.setItem("matome-follow", JSON.stringify(["ホロライブ"])); } catch (e) {}
  });
  const page = await ctx.newPage();
  const errs = [];
  page.on("pageerror", (e) => errs.push("예외: " + String(e.message || e).slice(0, 200)));
  page.on("console", (m) => { if (m.type() === "error" && !/Failed to load resource|net::ERR_|ERR_NAME_NOT_RESOLVED/.test(m.text())) errs.push("콘솔: " + m.text().slice(0, 200)); });
  await page.goto(`http://127.0.0.1:${PORT}/`, { waitUntil: "load" });
  await page.waitForTimeout(2500);  // data/ fetch 와 첫 렌더
  const W = await page.evaluate(() => document.documentElement.clientWidth);
  const rows = await page.$$eval("#feedBody .row", (a) => a.length);
  if (!rows) bad.push(`${dev}: 피드에 소식 카드가 없음`);
  for (const t of TABS) {
    const n0 = errs.length;
    await page.evaluate((t) => (document.querySelector(`nav.tabs [data-tab="${t}"]`) || document.querySelector(`#gpick [data-game="${t}"]`)).click(), t);  // 게임은 게임 탭 안의 고르는 칸
    await page.waitForTimeout(900);
    const shown = await page.evaluate((t) => { const s = document.getElementById(t); return !!s && s.offsetHeight > 40 && getComputedStyle(s).display !== "none"; }, t);
    if (!shown) bad.push(`${dev} ${t}: 탭 내용이 안 보임`);
    const gp = await page.evaluate(() => { const g = document.getElementById("gpick"); return !!g && g.offsetHeight > 0; });
    if (gp !== ["game", "g2048", "derby", "pen", "ensei"].includes(t)) bad.push(`${dev} ${t}: 게임 고르는 칸이 ${gp ? "게임 밖에서 보임" : "게임 탭에서 안 보임"}`);  // 2026-10 모든 탭 밑에 보이던 문제
    const ov = await page.evaluate(OVERFLOW);
    if (ov.length) bad.push(`${dev} ${t}: 화면(${W}px) 밖으로 넘침 → ${ov.join(" | ")}`);
    for (const e of errs.slice(n0)) bad.push(`${dev} ${t}: ${e}`);
    console.log(`${bad.some((b) => b.startsWith(`${dev} ${t}`)) ? "FAIL" : "OK  "} ${dev} ${t}`);
  }
  // 피드 '그림으로 보기'(격자)와 카드 상자
  await page.evaluate(() => document.querySelector('nav.tabs [data-tab="feed"]').click());
  await page.evaluate(() => document.querySelector('[data-fview="grid"]')?.click());
  await page.waitForTimeout(700);
  const tiles = await page.$$eval(".ptile", (a) => a.length), ovg = await page.evaluate(OVERFLOW);
  await page.evaluate(() => { const t = document.querySelector(".ptile"); if (t) t.click(); });
  const modal = await page.evaluate(() => !!document.querySelector(".pmodal .row"));
  if (!tiles || !modal) bad.push(`${dev} 그림 보기: 타일 ${tiles}개, 카드 상자 ${modal ? "열림" : "안 열림"}`);
  if (ovg.length) bad.push(`${dev} 그림 보기: 화면 밖으로 넘침 → ${ovg.join(" | ")}`);
  await page.evaluate(() => { document.querySelector(".pmodal")?.remove(); document.querySelector('[data-fview="list"]')?.click(); });  // 목록으로 되돌림
  console.log(`${tiles && modal && !ovg.length ? "OK  " : "FAIL"} ${dev} 그림 보기`);
  // 도쿄 지도의 '⛩ 성지'(data/seichi.json): 켜면 ⛩ 표시가 찍히고, 누르면 설명이 나온다
  await page.evaluate(() => { const d = document.querySelector(".mapbox"); if (d) d.open = true; document.querySelector("[data-mapseichi]")?.click(); });
  await page.waitForSelector(".tmap .seichi", { timeout: 6000 }).catch(() => {});  // seichi.json 을 처음 켤 때 읽는다(CI 에서 900ms 로는 모자랐다)
  const sj = await page.$$eval(".tmap .seichi", (a) => a.length);
  await page.evaluate(() => document.querySelector(".tmap .seichi")?.dispatchEvent(new MouseEvent("click", { bubbles: true })));
  const sji = await page.evaluate(() => !!document.querySelector("#mapinfo .sj")), ovs = await page.evaluate(OVERFLOW);
  if (!sj || !sji) bad.push(`${dev} 성지 지도: ⛩ ${sj}개, 설명 ${sji ? "나옴" : "안 나옴"}`);
  if (ovs.length) bad.push(`${dev} 성지 지도: 화면 밖으로 넘침 → ${ovs.join(" | ")}`);
  await page.evaluate(() => document.querySelector("[data-mapseichi]")?.click());
  console.log(`${sj && sji && !ovs.length ? "OK  " : "FAIL"} ${dev} 성지 지도`);
  // 캘린더 도구: 기간 행사 막대 · 콜라보 카페
  for (const k of ["bars", "cafe"]) {
    await page.evaluate((k) => { document.querySelector('nav.tabs [data-tab="sched"]').click(); document.querySelector(`[data-calnav="${k}"]`)?.click(); }, k);
    await page.waitForTimeout(400);
    const ok = await page.evaluate((k) => !!document.querySelector(k === "bars" ? "#sched .gb-row, #sched .empty" : "#sched .cafe-sum"), k), ovc = await page.evaluate(OVERFLOW);
    if (!ok) bad.push(`${dev} 캘린더 ${k}: 내용이 안 나옴`);
    if (ovc.length) bad.push(`${dev} 캘린더 ${k}: 화면 밖으로 넘침 → ${ovc.join(" | ")}`);
    console.log(`${ok && !ovc.length ? "OK  " : "FAIL"} ${dev} 캘린더 ${k}`);
  }
  // 폰 아래 탭 막대: 보이는지, 더보기 시트로 만갤을 열 수 있는지, 그때 '더보기' 칸이 '만갤'로 바뀌는지
  {
    const r = await page.evaluate(async () => {
      const nav = document.querySelector(".bnav"); if (!nav || !nav.offsetHeight) return "막대가 안 보임";
      if (nav.getBoundingClientRect().bottom > innerHeight + 1) return "막대가 화면 아래로 나감";
      document.getElementById("bnMore").click(); const sh = document.getElementById("bsheet");
      if (sh.hidden || !sh.querySelector(".bsheet-in").offsetHeight) return "더보기 시트가 안 열림";
      sh.querySelector('[data-tab="comics"]').click(); await new Promise((f) => setTimeout(f, 300));
      if (!sh.hidden) return "탭을 골라도 시트가 안 닫힘";
      if (document.getElementById("comics").hidden) return "만갤이 안 열림";
      if (!/보드 v\d/.test(document.getElementById("bVer").textContent)) return "더보기에 보드 버전 줄이 없음";
      const m = document.getElementById("bnMore"); if (m.getAttribute("aria-current") !== "page" || !/만갤/.test(m.textContent)) return "더보기 칸이 만갤 선택을 안 보여 줌";
      return "";
    });
    if (r) bad.push(`${dev} 아래 탭 막대: ${r}`);
    console.log(`${r ? "FAIL" : "OK  "} ${dev} 아래 탭 막대`);
  }
  // 작품 허브 주소로 바로 들어오는 길(#work=)
  await page.goto(`http://127.0.0.1:${PORT}/#work=${encodeURIComponent("ホロライブ")}`, { waitUntil: "load" });
  await page.waitForTimeout(2000);
  const hub = await page.evaluate(() => !!document.querySelector("#works .wh-title"));
  if (!hub) bad.push(`${dev}: #work= 주소로 작품 허브가 안 열림`);
  const ov = await page.evaluate(OVERFLOW);
  if (ov.length) bad.push(`${dev} 작품 허브: 화면 밖으로 넘침 → ${ov.join(" | ")}`);
  console.log(`${hub && !ov.length ? "OK  " : "FAIL"} ${dev} 작품 허브`);
  // 여행 플래너 주소(#trip=)로 바로 들어오는 길
  const d0 = new Date(Date.now() + 9 * 36e5 + 7 * 864e5).toISOString().slice(0, 10), d1 = new Date(Date.now() + 9 * 36e5 + 10 * 864e5).toISOString().slice(0, 10);
  await page.goto(`http://127.0.0.1:${PORT}/#trip=${d0}~${d1},kanto`, { waitUntil: "load" });
  await page.waitForTimeout(2000);
  const trip = await page.evaluate(() => !!document.querySelector("#sched .trip-sum") && !document.getElementById("sched").hidden);
  if (!trip) bad.push(`${dev}: #trip= 주소로 여행 플래너가 안 열림`);
  const ov2 = await page.evaluate(OVERFLOW);
  if (ov2.length) bad.push(`${dev} 여행 플래너: 화면 밖으로 넘침 → ${ov2.join(" | ")}`);
  console.log(`${trip && !ov2.length ? "OK  " : "FAIL"} ${dev} 여행 플래너`);
  await browser.close();
}

(async () => {
  const srv = await serve();
  try {
    for (const d of DEVS) await run(d);
  } catch (e) {
    bad.push("점검 자체가 실패: " + (e.stack || e));
  } finally {
    srv.kill();
  }
  if (bad.length) { console.log("\n" + bad.join("\n")); console.log(`→ 실패 ${bad.length}건`); process.exit(1); }
  console.log("→ 페이지 점검 통과");
})();
