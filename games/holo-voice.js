/* 홀로 모바일 합체 보이스 (matome-board)
   games/holo2048.html 맨 끝(</body> 앞)에 <script src="holo-voice.js"></script> 한 줄로 붙는다. 게임 파일을 새로 받으면 games/merge.html 이 그 한 줄을 넣어 준다.
   게임 코드는 고치지 않고 전역 함수 playPopMergeSound(값)·playVictoryFanfare() 를 감싸서 합체를 알아챈다:
   - 수박: 방금 생긴 구슬(orbs 끝에서 같은 값), 2048: 이번에 합쳐진 타일(grid 의 merged) 의 charKey 로 멤버를 고르고 그 자리에 말풍선.
   - 멤버별 레트로 징글(게임의 AudioContext, ensureAudio) + 기기 음성으로 대사(Web Speech) + 한국어 말풍선.
   - games/voices/{값}_{멤버}.mp3 (예: 2_sora.mp3, 2_mumei.mp3) 가 있으면 징글·합성 음성 대신 그 파일.
   - 게임의 🔊 끄기(soundEnabled)를 따른다. 도감(📖)에 대사·말풍선 켜기/끄기, 16명 징글 WAV 받기 버튼을 붙이고, 도감 카드를 누르면 그 멤버 목소리를 미리 들려준다.
   필요한 게임 이름: playPopMergeSound, playVictoryFanfare, soundEnabled, ensureAudio, orbs, grid, activeGameMode, activeRoster, CHARACTER_LIBRARY, LOGICAL_WIDTH/HEIGHT,
   #suikaCanvas, #boardContainer, #soundToggleBtn, #dexGrid, #altDexGrid, #themeRandomBtn. 없는 것은 조용히 건너뛴다. */
(() => {
  'use strict';
  if (window.HoloVoice) return; // 두 번 붙어도 한 번만

  // 멤버별 대사(일본어/영어)·한국어 말풍선·음성 높이/속도·징글(파형·음·한 음 길이)
  const DB = {
    sora:   { line: 'ぬんぬん！そらとも！', ko: '눈누~! 소라토모!', lang: 'ja-JP', pitch: 1.38, rate: 1.15, wave: 'sine', notes: [523.25, 659.25, 783.99, 1046.50], dur: 0.08 },
    mumei:  { line: 'Oh hi!', ko: '오하이~!', lang: 'en-US', pitch: 1.42, rate: 1.20, wave: 'triangle', notes: [523.25, 659.25, 880.00, 1046.50], dur: 0.08 },
    suisei: { line: 'すいちゃんはー！今日もかわいい！', ko: '스이쨩은~! 오늘도 카와이!', lang: 'ja-JP', pitch: 1.25, rate: 1.22, wave: 'triangle', notes: [587.33, 739.99, 880.00, 1174.66], dur: 0.08 },
    irys:   { line: 'HiRyS! It is IRyS!', ko: '하이리스~!', lang: 'en-US', pitch: 1.32, rate: 1.15, wave: 'sine', notes: [587.33, 880.00, 1174.66, 1479.98], dur: 0.08 },
    pekora: { line: 'こんぺこ！こんぺこ！ぺこー！', ko: '콘페코~! 페코!', lang: 'ja-JP', pitch: 1.52, rate: 1.35, wave: 'square', notes: [659.25, 659.25, 783.99, 659.25, 987.77], dur: 0.07 },
    ollie:  { line: 'Zombanwa!', ko: '좀반와~!', lang: 'en-US', pitch: 1.48, rate: 1.32, wave: 'sawtooth', notes: [659.25, 830.61, 987.77, 1318.51], dur: 0.07 },
    aqua:   { line: 'こんあくあー！ねぇー！', ko: '콘아쿠아~! 네에~!', lang: 'ja-JP', pitch: 1.58, rate: 1.22, wave: 'sine', notes: [493.88, 739.99, 987.77, 1479.98], dur: 0.08 },
    fauna:  { line: 'Konfauna! Uuuu~', ko: '콘파우나! 우우우~', lang: 'en-US', pitch: 1.25, rate: 1.02, wave: 'sine', notes: [440.00, 554.37, 659.25, 880.00], dur: 0.09 },
    marine: { line: 'アホーイ！宝鐘マリンです！', ko: '아호이~! 마린입니다!', lang: 'ja-JP', pitch: 1.12, rate: 1.15, wave: 'sawtooth', notes: [440.00, 554.37, 659.25, 880.00, 1108.73], dur: 0.08 },
    kronii: { line: 'Kroniichiwa!', ko: '크로니찌와~!', lang: 'en-US', pitch: 0.92, rate: 1.05, wave: 'triangle', notes: [392.00, 493.88, 587.33, 783.99], dur: 0.09 },
    fubuki: { line: 'こんこんきーつね！', ko: '콘콘키츠네~!', lang: 'ja-JP', pitch: 1.45, rate: 1.28, wave: 'triangle', notes: [783.99, 987.77, 1174.66, 1567.98], dur: 0.07 },
    subaru: { line: 'ちわーす！シュバッ！', ko: '치와스! 슈바슈바~!', lang: 'ja-JP', pitch: 1.30, rate: 1.35, wave: 'square', notes: [587.33, 783.99, 587.33, 880.00, 1174.66], dur: 0.07 },
    korone: { line: 'ゆびゆびー！おーらよ！', ko: '유비유비~! 오라요!', lang: 'ja-JP', pitch: 1.55, rate: 1.28, wave: 'square', notes: [659.25, 880.00, 1046.50, 1318.51], dur: 0.07 },
    okayu:  { line: 'もぐもぐ〜おかゆ〜！', ko: '모구모구~ 오카유~!', lang: 'ja-JP', pitch: 0.96, rate: 1.00, wave: 'sine', notes: [392.00, 493.88, 587.33, 739.99], dur: 0.10 },
    miko:   { line: 'にゃっはろー！エリートみこ！', ko: '냐하로~! 엘리트 미코!', lang: 'ja-JP', pitch: 1.50, rate: 1.18, wave: 'triangle', notes: [523.25, 659.25, 783.99, 1046.50, 1318.51], dur: 0.08 },
    calli:  { line: 'Guh! Dead Beats!', ko: '구하~! 데드비츠!', lang: 'en-US', pitch: 0.85, rate: 1.10, wave: 'sawtooth', notes: [261.63, 392.00, 523.25, 783.99, 1046.50], dur: 0.10 }
  };
  const VALUE_OF = { sora: 2, mumei: 2, suisei: 4, irys: 4, pekora: 8, ollie: 8, aqua: 16, fauna: 16, marine: 32, kronii: 32, fubuki: 64, subaru: 128, korone: 256, okayu: 512, miko: 1024, calli: 2048 };
  const MAIN_OF = { 2: 'sora', 4: 'suisei', 8: 'pekora', 16: 'aqua', 32: 'marine', 64: 'fubuki', 128: 'subaru', 256: 'korone', 512: 'okayu', 1024: 'miko', 2048: 'calli' };

  // ---- 설정(이 기기에만 저장) ----
  const load = (k, d) => { try { const v = localStorage.getItem(k); return v == null ? d : v !== 'off'; } catch (e) { return d; } };
  const store = (k, on) => { try { localStorage.setItem(k, on ? 'on' : 'off'); } catch (e) {} };
  let voiceOn = load('holoMergeVoice', true), bubbleOn = load('holoMergeBubble', true);
  const muted = () => typeof soundEnabled !== 'undefined' && !soundEnabled; // eslint-disable-line no-undef
  const valueOf = key => VALUE_OF[key] || (typeof CHARACTER_LIBRARY !== 'undefined' && CHARACTER_LIBRARY[key] && CHARACTER_LIBRARY[key].value) || 2; // eslint-disable-line no-undef
  const rosterKey = val => (typeof activeRoster !== 'undefined' && activeRoster[val]) || MAIN_OF[val] || 'sora'; // eslint-disable-line no-undef

  // ---- 징글: 게임과 같은 AudioContext 로 음을 낸다(iOS 에서 물리 틱 중 HTMLAudio 재생이 막히는 것을 피함) ----
  function ctx() {
    try { if (typeof ensureAudio === 'function') return ensureAudio(); } catch (e) {} // eslint-disable-line no-undef
    return null;
  }
  function jingle(v) {
    const c = ctx(); if (!c) return;
    try {
      const now = c.currentTime + 0.01;
      v.notes.forEach((f, i) => {
        const t = now + i * v.dur, o = c.createOscillator(), g = c.createGain();
        o.type = v.wave;
        if (i === 0) { o.frequency.setValueAtTime(f * 0.85, t); o.frequency.linearRampToValueAtTime(f * 1.1, t + 0.04); } else o.frequency.setValueAtTime(f, t);
        g.gain.setValueAtTime(0.0001, t);
        g.gain.linearRampToValueAtTime(v.wave === 'sine' ? 0.2 : 0.13, t + 0.008);
        g.gain.exponentialRampToValueAtTime(0.001, t + v.dur + 0.07);
        o.connect(g); g.connect(c.destination); o.start(t); o.stop(t + v.dur + 0.08);
      });
    } catch (e) {}
  }

  // ---- 음성: 기기에 있는 일본어/영어 목소리를 고른다. 낮은 값이 0.35초 안에 연달아 합쳐지면 대사는 건너뛴다 ----
  let voices = [], lastSpeak = 0, lastVal = 0;
  const loadVoices = () => { try { voices = speechSynthesis.getVoices() || []; } catch (e) {} };
  if ('speechSynthesis' in window) { loadVoices(); try { speechSynthesis.addEventListener('voiceschanged', loadVoices); } catch (e) {} }
  function speak(v, value, force) {
    if (!('speechSynthesis' in window)) return;
    const now = performance.now();
    if (!force && now - lastSpeak < 350 && value <= lastVal) return;
    lastSpeak = now; lastVal = value;
    try {
      speechSynthesis.cancel();
      const u = new SpeechSynthesisUtterance(v.line);
      u.lang = v.lang;
      const pick = voices.find(x => (x.lang || '').replace('_', '-').toLowerCase().startsWith(v.lang.slice(0, 2).toLowerCase()));
      if (pick) u.voice = pick;
      u.pitch = Math.min(2, v.pitch); u.rate = v.rate; u.volume = 0.9;
      speechSynthesis.speak(u);
    } catch (e) {}
  }
  const stop = () => { try { if ('speechSynthesis' in window) speechSynthesis.cancel(); } catch (e) {} };

  // ---- 실제 목소리 MP3: 파일마다 처음 한 번만 HEAD 로 있는지 보고 기억(없는 파일을 합칠 때마다 요청하지 않게) ----
  const fileOK = {};
  function probe(f) {
    fileOK[f] = 'probe';
    fetch(f, { method: 'HEAD', cache: 'no-store' })
      .then(r => { fileOK[f] = r.ok && !/text\/html/.test(r.headers.get('content-type') || ''); })
      .catch(() => { fileOK[f] = false; });
  }

  // ---- 말풍선 ----
  const css = document.createElement('style');
  css.textContent = `.holo-voice-bubble{position:fixed;z-index:65;pointer-events:none;transform:translate(-50%,-100%);padding:5px 12px;border-radius:999px;font-family:'Jua','Pretendard',sans-serif;font-size:13px;font-weight:800;color:#fff;white-space:nowrap;max-width:92vw;overflow:hidden;text-overflow:ellipsis;box-shadow:0 6px 18px rgba(15,23,42,.35);border:2px solid #fff;animation:holoVoiceFloat 1.05s cubic-bezier(.22,1,.36,1) forwards}
@keyframes holoVoiceFloat{0%{opacity:0;transform:translate(-50%,-40%) scale(.6)}20%{opacity:1;transform:translate(-50%,-110%) scale(1.08)}40%{opacity:1;transform:translate(-50%,-125%) scale(1)}100%{opacity:0;transform:translate(-50%,-175%) scale(.92)}}
@media (prefers-reduced-motion:reduce){.holo-voice-bubble{animation-duration:.01s;animation-delay:1s}}`;
  document.head.appendChild(css);
  function bubble(key, x, y) {
    const char = (typeof CHARACTER_LIBRARY !== 'undefined' && CHARACTER_LIBRARY[key]) || {}; // eslint-disable-line no-undef
    const v = DB[key] || DB.sora, b = document.createElement('div');
    b.className = 'holo-voice-bubble';
    b.style.background = 'linear-gradient(135deg,' + (char.color || '#0ea5e9') + ',#1e293b)';
    b.textContent = '🗣️ ' + (char.name || key) + ': "' + v.ko + '"';
    document.body.appendChild(b);
    const w = b.offsetWidth, W = window.innerWidth; // 화면 밖으로 나가지 않게 가로 위치를 맞춘다
    b.style.left = Math.max(w / 2 + 6, Math.min(W - w / 2 - 6, x)) + 'px';
    b.style.top = Math.max(b.offsetHeight + 8, y) + 'px';
    setTimeout(() => b.remove(), 1100);
  }

  // ---- 재생: MP3 가 있으면 그 파일, 없으면 징글 + 대사 ----
  function play(key, value, pos, preview) {
    if (muted()) return;
    const v = DB[key] || DB[MAIN_OF[value]] || DB.sora;
    value = value || valueOf(key);
    const f = 'voices/' + value + '_' + key + '.mp3';
    if (fileOK[f] === true) {
      const a = new Audio(f); a.volume = 0.85;
      a.play().catch(() => { fileOK[f] = false; jingle(v); if (voiceOn || preview) speak(v, value, preview); });
    } else {
      if (fileOK[f] === undefined) probe(f);
      jingle(v);
      if (voiceOn || preview) speak(v, value, preview);
    }
    if (bubbleOn && pos) bubble(key, pos.x, pos.y);
  }

  // ---- 합쳐진 멤버와 화면 위치 찾기 ----
  function who(val) {
    const mode = typeof activeGameMode !== 'undefined' ? activeGameMode : ''; // eslint-disable-line no-undef
    if (mode !== '2048' && typeof orbs !== 'undefined' && Array.isArray(orbs)) { // eslint-disable-line no-undef
      for (let i = orbs.length - 1; i >= 0; i--) { // eslint-disable-line no-undef
        const o = orbs[i]; // eslint-disable-line no-undef
        if (o.value !== val) continue;
        const cv = document.getElementById('suikaCanvas'); let pos = null;
        if (cv) {
          const r = cv.getBoundingClientRect();
          const LW = typeof LOGICAL_WIDTH !== 'undefined' ? LOGICAL_WIDTH : cv.width, LH = typeof LOGICAL_HEIGHT !== 'undefined' ? LOGICAL_HEIGHT : cv.height; // eslint-disable-line no-undef
          pos = { x: r.left + (o.x / LW) * r.width, y: r.top + ((o.y - (o.radius || 20)) / LH) * r.height };
        }
        return { key: o.charKey || rosterKey(val), pos };
      }
    }
    if (mode === '2048' && typeof grid !== 'undefined' && Array.isArray(grid)) { // eslint-disable-line no-undef
      const n = grid.length || 4; // eslint-disable-line no-undef
      for (let r = 0; r < n; r++) for (let c = 0; c < n; c++) {
        const t = grid[r] && grid[r][c]; // eslint-disable-line no-undef
        if (!t || !t.merged || t.value !== val) continue;
        const bd = document.getElementById('boardContainer'); let pos = null;
        if (bd) { const R = bd.getBoundingClientRect(); pos = { x: R.left + ((c + 0.5) / n) * R.width, y: R.top + (r / n) * R.height + 10 }; }
        return { key: t.charKey || rosterKey(val), pos };
      }
    }
    return { key: rosterKey(val), pos: null };
  }

  // ---- 게임 함수 감싸기(전역 함수 선언이라 window 속성을 바꾸면 게임 안의 호출도 바뀐다) ----
  const hooked = [];
  if (typeof window.playPopMergeSound === 'function') {
    const orig = window.playPopMergeSound;
    window.playPopMergeSound = function (val) { const r = orig.apply(this, arguments); try { const m = who(val); play(m.key, val, m.pos); } catch (e) {} return r; };
    hooked.push('playPopMergeSound');
  }
  if (typeof window.playVictoryFanfare === 'function') { // 2048 달성·수박 2048 빅뱅
    const orig = window.playVictoryFanfare;
    window.playVictoryFanfare = function () { const r = orig.apply(this, arguments); try { play(rosterKey(2048), 2048, { x: window.innerWidth / 2, y: window.innerHeight * 0.38 }); } catch (e) {} return r; };
    hooked.push('playVictoryFanfare');
  }
  const sb = document.getElementById('soundToggleBtn');
  if (sb) sb.addEventListener('click', () => { if (muted()) stop(); });

  // ---- 도감 카드를 누르면 그 멤버 목소리 미리 듣기(게임이 카드 처리를 끝낸 뒤) ----
  const dg = document.getElementById('dexGrid');
  if (dg) dg.addEventListener('click', e => { const c = e.target.closest('[data-dex-val]'); if (!c) return; const val = parseInt(c.dataset.dexVal, 10); setTimeout(() => play(rosterKey(val), val, null, true), 0); });
  const ag = document.getElementById('altDexGrid');
  if (ag) ag.addEventListener('click', e => { const c = e.target.closest('[data-alt-key]'); if (!c) return; const k = c.dataset.altKey; setTimeout(() => play(k, valueOf(k), null, true), 0); });

  // ---- WAV 만들기·받기 ----
  function wavBlob(key) {
    const v = DB[key] || DB.sora, sr = 44100, nd = v.dur || 0.08, total = v.notes.length * nd + 0.08, n = Math.floor(sr * total);
    const buf = new ArrayBuffer(44 + n * 2), dv = new DataView(buf);
    const ws = (o, s) => { for (let i = 0; i < s.length; i++) dv.setUint8(o + i, s.charCodeAt(i)); };
    ws(0, 'RIFF'); dv.setUint32(4, 36 + n * 2, true); ws(8, 'WAVE'); ws(12, 'fmt ');
    dv.setUint32(16, 16, true); dv.setUint16(20, 1, true); dv.setUint16(22, 1, true); dv.setUint32(24, sr, true); dv.setUint32(28, sr * 2, true);
    dv.setUint16(32, 2, true); dv.setUint16(34, 16, true); ws(36, 'data'); dv.setUint32(40, n * 2, true);
    for (let i = 0; i < n; i++) {
      const t = i / sr, idx = Math.min(v.notes.length - 1, Math.floor(t / nd)), lt = t - idx * nd, f0 = v.notes[idx];
      const f = idx === 0 ? f0 * (0.85 + 0.25 * Math.min(1, lt / 0.04)) : f0, ph = 2 * Math.PI * f * lt;
      const raw = v.wave === 'square' ? (Math.sin(ph) >= 0 ? 0.65 : -0.65)
        : v.wave === 'sawtooth' ? 2 * (f * lt - Math.floor(0.5 + f * lt)) * 0.65
        : v.wave === 'triangle' ? (2 / Math.PI) * Math.asin(Math.sin(ph)) * 0.8
        : Math.sin(ph) * 0.75;
      const s = Math.max(-1, Math.min(1, raw * Math.min(1, lt / 0.008) * Math.exp(-lt * 10.5) * 0.42));
      dv.setInt16(44 + i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
    }
    return new Blob([buf], { type: 'audio/wav' });
  }
  function downloadAllWav() {
    Object.keys(DB).forEach((key, i) => setTimeout(() => {
      const a = document.createElement('a'), url = URL.createObjectURL(wavBlob(key));
      a.href = url; a.download = valueOf(key) + '_' + key + '_merge.wav';
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 4000);
    }, i * 250));
  }

  // ---- 도감 시트에 설정 칸 붙이기(테마 로스터 칸 바로 아래) ----
  function addPanel() {
    const anchor = document.getElementById('themeRandomBtn');
    const box = anchor && anchor.closest('.rounded-2xl');
    if (!box || document.getElementById('holoVoicePanel')) return;
    box.insertAdjacentHTML('afterend', `<div id="holoVoicePanel" class="bg-slate-950/80 border border-slate-800 rounded-2xl p-2.5">
  <div class="text-[11px] font-bold text-cyan-300 mb-1.5">🔊 합체 보이스 · 징글</div>
  <div class="grid grid-cols-3 gap-1.5">
    <button id="hvVoice" type="button"></button><button id="hvBubble" type="button"></button>
    <button id="hvWav" type="button" class="py-1.5 px-1 rounded-xl text-[11px] font-black bg-slate-800 text-slate-300 border border-slate-700">⬇️ WAV 16개</button>
  </div>
  <p class="text-[10px] text-slate-500 mt-1.5 leading-snug">합체하면 멤버별 징글과 기기의 음성으로 대사가 나오고 말풍선이 떠요. 카드를 누르면 그 멤버 목소리를 미리 들려줘요. 🔊 를 끄면 모두 꺼져요.</p>
</div>`);
    const paint = () => {
      const pill = on => 'py-1.5 px-1 rounded-xl text-[11px] font-black border ' + (on ? 'bg-cyan-500/25 text-cyan-200 border-cyan-400/60' : 'bg-slate-800 text-slate-400 border-slate-700');
      const bv = document.getElementById('hvVoice'), bb = document.getElementById('hvBubble');
      bv.className = pill(voiceOn); bv.textContent = voiceOn ? '🗣️ 대사 ON' : '🔇 대사 OFF';
      bb.className = pill(bubbleOn); bb.textContent = bubbleOn ? '💬 말풍선 ON' : '💬 말풍선 OFF';
    };
    paint();
    document.getElementById('hvVoice').addEventListener('click', () => { voiceOn = !voiceOn; store('holoMergeVoice', voiceOn); if (!voiceOn) stop(); else play(rosterKey(2), 2, null, true); paint(); });
    document.getElementById('hvBubble').addEventListener('click', () => { bubbleOn = !bubbleOn; store('holoMergeBubble', bubbleOn); paint(); });
    document.getElementById('hvWav').addEventListener('click', downloadAllWav);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', addPanel); else addPanel();

  window.HoloVoice = { play, downloadAllWav, DB, hooked, setVoice: on => { voiceOn = !!on; store('holoMergeVoice', voiceOn); if (!voiceOn) stop(); }, setBubble: on => { bubbleOn = !!on; store('holoMergeBubble', bubbleOn); } };
  // 운영자가 처음 준 코드의 이름도 그대로 쓸 수 있게
  window.HoloMergeAudio = { playMerge: (val, useAlt) => play(useAlt && ALT[val] ? ALT[val] : MAIN_OF[val] || 'sora', val, null), downloadAllWav, ROSTER: DB };
  const ALT = { 2: 'mumei', 4: 'irys', 8: 'ollie', 16: 'fauna', 32: 'kronii' };
})();
