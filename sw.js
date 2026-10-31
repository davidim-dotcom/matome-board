/* 마토메 보드 서비스 워커(홈 화면 앱·오프라인).
   - 페이지(index.html)와 data/*.json 은 네트워크 먼저, 안 되면 마지막으로 받아 둔 것(그래서 온라인이면 늘 최신).
   - manifest 와 앱 아이콘(icon-*·apple-touch-icon*)도 네트워크 먼저: 캐시 먼저면 폰이 앱 아이콘을 다시 확인할 때 옛 manifest 를 받아 아이콘이 안 바뀌었다.
   - 그림·게임 등 나머지 같은 출처 파일은 캐시를 먼저 보여 주고 뒤에서 새로 받아 둔다.
   - 다른 출처(Google Fonts·GoatCounter·게시판 웹 앱)와 소리 파일(Range 요청)은 건드리지 않는다.
   캐시 구조를 바꾸면 V 를 올린다(예전 캐시는 activate 에서 지움). */
const V = "matome-v3"; // 2026-10 말 v2: 앱 아이콘·미리보기 그림을 새 릴리로 바꾸며 파일 이름을 바꿨다(옛 캐시를 지우게). v3: manifest·아이콘을 네트워크 먼저로
const SHELL = ["./", "index.html", "manifest.webmanifest", "assets/icon-lilly-192.png", "assets/mascot.png", "assets/game/player.png"];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(V).then(c => c.addAll(SHELL)).catch(() => {}).then(() => self.skipWaiting()));
});
self.addEventListener("activate", e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== V).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});

function keyOf(req) { // data/*.json 은 ?v= 캐시 버스터를 떼고 한 칸에 저장
  const u = new URL(req.url);
  return u.pathname.includes("/data/") ? u.origin + u.pathname : req;
}
async function networkFirst(req, fallbackKey) {
  const c = await caches.open(V);
  try {
    const r = await fetch(req);
    if (r.ok) c.put(keyOf(req), r.clone());
    return r;
  } catch (err) {
    const hit = await c.match(keyOf(req)) || (fallbackKey && await c.match(fallbackKey));
    if (hit) return hit;
    throw err;
  }
}
async function staleWhileRevalidate(e, req) {
  const c = await caches.open(V);
  const hit = await c.match(req);
  const net = fetch(req).then(r => { if (r.ok && r.type === "basic") c.put(req, r.clone()); return r });
  if (hit) { e.waitUntil(net.catch(() => {})); return hit }
  return net;
}

self.addEventListener("fetch", e => {
  const req = e.request, url = new URL(req.url);
  if (req.method !== "GET" || url.origin !== location.origin) return;
  if (req.headers.has("range") || /\.(mp3|mid|wav|ogg)$/i.test(url.pathname)) return;
  if (req.mode === "navigate" || url.pathname.endsWith("/") || url.pathname.endsWith("index.html")) {
    e.respondWith(networkFirst(req, req.destination === "iframe" ? null : new URL("./", self.registration.scope).href)); // 게임 iframe 이 오프라인일 때 보드 첫 화면이 안에 뜨지 않게
    return;
  }
  if (url.pathname.includes("/data/") || /\/(manifest\.webmanifest|assets\/(icon-|apple-touch-icon)[^/]*\.png)$/.test(url.pathname)) { e.respondWith(networkFirst(req)); return; }
  e.respondWith(staleWhileRevalidate(e, req));
});
