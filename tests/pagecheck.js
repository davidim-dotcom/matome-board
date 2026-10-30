#!/usr/bin/env node
// 페이지 점검 — 실제 브라우저(Chromium, 폰 크기)로 index.html 을 열어 탭마다 스크립트 오류·화면 가로 넘침·빈 화면을 본다.
// .github/workflows/test.yml 이 PR 마다 돌리고, 로컬에서는  node tests/pagecheck.js  (playwright 필요. 브라우저 경로는 PW_CHROMIUM 으로 지정 가능)
// 저장소 루트를 정적 서버(python3 -m http.server)로 띄워 data/ 를 그대로 읽는다. 바깥 사이트(글꼴·그림·게시판)는 못 불러와도 실패로 치지 않는다.
const { spawn } = require("child_process");
const path = require("path");
const { chromium, devices } = require("playwright");

const ROOT = path.dirname(__dirname);
const PORT = 8799;
const TABS = ["feed", "sched", "weekly", "works", "buzz", "anime", "comics", "about", "game", "g2048", "derby"];
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
    let a = e.parentElement, clip = false;
    while (a && a !== document.body) { if (getComputedStyle(a).overflowX !== "visible") { clip = true; break; } a = a.parentElement; }
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
    await page.evaluate((t) => document.querySelector(`nav.tabs [data-tab="${t}"]`).click(), t);
    await page.waitForTimeout(900);
    const shown = await page.evaluate((t) => { const s = document.getElementById(t); return !!s && s.offsetHeight > 40 && getComputedStyle(s).display !== "none"; }, t);
    if (!shown) bad.push(`${dev} ${t}: 탭 내용이 안 보임`);
    const ov = await page.evaluate(OVERFLOW);
    if (ov.length) bad.push(`${dev} ${t}: 화면(${W}px) 밖으로 넘침 → ${ov.join(" | ")}`);
    for (const e of errs.slice(n0)) bad.push(`${dev} ${t}: ${e}`);
    console.log(`${bad.some((b) => b.startsWith(`${dev} ${t}`)) ? "FAIL" : "OK  "} ${dev} ${t}`);
  }
  // 작품 허브 주소로 바로 들어오는 길(#work=)
  await page.goto(`http://127.0.0.1:${PORT}/#work=${encodeURIComponent("ホロライブ")}`, { waitUntil: "load" });
  await page.waitForTimeout(2000);
  const hub = await page.evaluate(() => !!document.querySelector("#works .wh-title"));
  if (!hub) bad.push(`${dev}: #work= 주소로 작품 허브가 안 열림`);
  const ov = await page.evaluate(OVERFLOW);
  if (ov.length) bad.push(`${dev} 작품 허브: 화면 밖으로 넘침 → ${ov.join(" | ")}`);
  console.log(`${hub && !ov.length ? "OK  " : "FAIL"} ${dev} 작품 허브`);
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
