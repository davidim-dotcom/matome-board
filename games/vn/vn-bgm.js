/*
  VN BGM — 「2년짜리 마을」 장면 음악(2026-10-31, 이 게임용 오리지널 곡). 소리 파일 없이 Web Audio 로 그 자리에서 연주한다.
  시나리오의 {t:'bgm',id:'곡 이름'} → 엔진이 window.VN_BGM.play(id) 를 부른다(import.py 의 ENGINE 고침이 엔진에 넣는다).
  곡: 메인 테마 · 방과 후 · 이어폰 한쪽 · 진해의 여름 · 소문 · 진자 · 전출 안내 · 타이틀(메인 테마를 느리고 조용하게).
  모르는 이름은 메인 테마, 빈 이름('')은 멈춤. 곡을 더하려면 TRACKS 에 같은 꼴로 한 칸 더한다:
    bpm, ch(마디마다 코드: C·Dm·F#m7·Bbmaj7·E7·Asus4·Bdim), mel(마디마다 '음:8분 길이', '-' 는 쉼표, 한 마디 8칸),
    lead(piano·epiano·pluck·bell), acc(arp·pad·block·pulse), bass(whole·bounce·pulse·null), drums(pop·lofi·shaker·tick·null),
    swing(0~.3), phase(진자처럼 3칸·5칸 주기로 도는 오르골 아르페지오), vol, verb(잔향 양).
  브라우저는 사람이 한 번 누르기 전에는 소리를 못 내서, 첫 터치·키 입력에 시작한다. 아래 버튼 줄의 「음악」(localStorage vn-bgm)으로 끄고,
  화면이 숨거나(visibilitychange) 보드의 '테스트 중' 칸을 접어 iframe 이 안 보이면 멈춘다.
*/
(function(){
'use strict';
const NOTE={C:0,D:2,E:4,F:5,G:7,A:9,B:11};
function midi(n){const m=/^([A-G])([#b]?)(-?\d)$/.exec(n);if(!m)throw new Error('음 이름 '+n);return 12*(+m[3]+1)+NOTE[m[1]]+(m[2]==='#'?1:m[2]==='b'?-1:0)}
const hz=m=>440*Math.pow(2,(m-69)/12);
const Q={'':[0,4,7],m:[0,3,7],m7:[0,3,7,10],maj7:[0,4,7,11],'7':[0,4,7,10],sus4:[0,5,7],dim:[0,3,6],add9:[0,4,7,14]};
function chord(name){const m=/^([A-G][#b]?)(.*)$/.exec(name);const r=midi(m[1]+'3');return (Q[m[2]]||Q['']).map(i=>r+i)}
function bar(s){const out=[];let p=0;for(const t of s.trim().split(/\s+/)){const[n,l]=t.split(':');if(n!=='-')out.push([p,midi(n),+l]);p+=+l}return out}

// ---------- 곡 ----------
const MAIN={bpm:80,lead:'piano',acc:'arp',bass:'whole',drums:null,vol:.9,verb:.38,
 ch:['D','A','Bm','G','D','A','G','A','Bm','G','D','A','G','A','D','D'],
 mel:['F#5:3 E5:1 D5:2 A4:2','C#5:3 D5:1 E5:4','D5:3 C#5:1 B4:2 F#4:2','G4:2 A4:2 B4:4',
      'A5:3 F#5:1 D5:2 E5:2','F#5:2 E5:2 C#5:4','B4:2 D5:2 G5:2 F#5:2','E5:6 -:2',
      'F#5:2 B5:2 A5:2 F#5:2','G5:3 F#5:1 E5:4','F#5:2 A5:2 D6:2 C#6:2','B5:2 A5:2 E5:4',
      'D5:2 E5:2 F#5:2 G5:2','A5:3 G5:1 E5:2 C#5:2','D5:8','-:8']};
const TRACKS={
 '메인 테마':MAIN,
 '타이틀':Object.assign({},MAIN,{bpm:70,bass:null,acc:'pad',vol:.75,verb:.5,ch:MAIN.ch.slice(0,8),mel:MAIN.mel.slice(0,8)}),
 '방과 후':{bpm:108,lead:'pluck',acc:'block',bass:'bounce',drums:'pop',vol:.8,verb:.22,
  ch:['F','Dm','Bb','C','F','Am','Bb','C7'],
  mel:['A4:1 C5:1 F5:2 E5:1 F5:1 G5:2','A5:2 F5:2 D5:3 -:1','D5:1 F5:1 Bb5:2 A5:1 G5:1 F5:2','G5:3 E5:1 C5:3 -:1',
       'A4:1 C5:1 F5:2 G5:1 A5:1 C6:2','C6:2 A5:2 E5:3 -:1','F5:1 G5:1 A5:2 Bb5:1 A5:1 G5:2','E5:2 G5:2 C5:2 -:2']},
 '이어폰 한쪽':{bpm:86,lead:'bell',acc:'pad',bass:'whole',drums:'lofi',swing:.18,vol:.85,verb:.42,
  ch:['Fmaj7','Em7','Dm7','Am7','Fmaj7','Em7','Dm7','E7'],
  mel:['-:2 E5:1 G5:1 A5:2 C6:2','B5:3 G5:1 E5:4','-:2 F5:1 A5:1 C6:2 D6:2','C6:2 B5:1 A5:1 E5:4',
       '-:2 A5:1 C6:1 E6:2 D6:1 C6:1','B5:2 G5:2 E5:2 G5:2','A5:2 F5:2 D5:2 C5:1 D5:1','E5:6 -:2']},
 '진해의 여름':{bpm:116,lead:'pluck',acc:'arp',bass:'bounce',drums:'shaker',vol:.8,verb:.3,
  ch:['G','C','G','D','Em','C','D','G'],
  mel:['B4:1 D5:1 G5:2 F#5:1 G5:1 A5:2','G5:2 E5:2 C5:2 E5:2','D5:1 E5:1 G5:2 B5:2 A5:2','F#5:3 E5:1 D5:4',
       'E5:1 G5:1 B5:2 A5:1 G5:1 E5:2','C6:2 B5:2 G5:2 E5:2','A5:2 B5:1 C6:1 D6:2 F#5:2','G5:6 -:2']},
 '소문':{bpm:72,lead:'bell',acc:'pad',bass:'pulse',drums:'tick',vol:.8,verb:.45,
  ch:['Em','Em','C','B','Em','Am','C','B7'],
  mel:['-:4 B5:2 C6:2','B5:6 -:2','-:4 G5:2 A5:2','F#5:6 -:2','-:4 E6:2 D#6:2','E6:4 C6:4','-:2 B5:2 G5:2 E5:2','D#5:8']},
 '진자':{bpm:96,lead:'bell',acc:'pad',bass:'whole',drums:null,phase:true,vol:.8,verb:.45,
  ch:['Cmaj7','Fmaj7','Am7','G','Cmaj7','Fmaj7','Dm7','G'],
  mel:['E5:4 G5:4','A5:4 C6:4','B5:4 A5:2 E5:2','D5:8','E5:2 G5:2 C6:2 B5:2','A5:4 F5:4','F5:2 E5:2 D5:2 A5:2','G5:8']},
 '전출 안내':{bpm:64,lead:'piano',acc:'arp',bass:'whole',drums:null,vol:.85,verb:.5,
  ch:['Gm','Eb','Bb','F','Gm','Eb','Cm','D7'],
  mel:['D5:3 C5:1 Bb4:2 G4:2','G4:2 Bb4:2 Eb5:4','D5:2 C5:2 Bb4:2 D5:2','C5:6 -:2',
       'Bb4:2 D5:2 G5:3 F5:1','Eb5:2 D5:2 Bb4:4','C5:2 Eb5:2 G5:2 F5:1 Eb5:1','D5:6 -:2']},
};
for(const k in TRACKS){const t=TRACKS[k];t.bars=t.mel.map(bar);t.chords=t.ch.map(chord);t.n=t.ch.length}

// ---------- 악기 ----------
function env(ctx,g,t,a,peak,dec){g.gain.setValueAtTime(0,t);g.gain.linearRampToValueAtTime(peak,t+a);g.gain.exponentialRampToValueAtTime(.0008,t+a+dec)}
function osc(ctx,type,f,t,end,dest,det){const o=ctx.createOscillator();o.type=type;o.frequency.value=f;if(det)o.detune.value=det;o.connect(dest);o.start(t);o.stop(end);return o}
let NOISE=null;
function noise(ctx){if(NOISE&&NOISE.sampleRate===ctx.sampleRate)return NOISE;const b=ctx.createBuffer(1,ctx.sampleRate,ctx.sampleRate),d=b.getChannelData(0);let s=7;for(let i=0;i<d.length;i++){s=(s*16807)%2147483647;d[i]=s/1073741824-1}return NOISE=b}
const INST={
 piano(ctx,o,t,m,dur,v){const f=hz(m),g=ctx.createGain();g.connect(o);const dec=Math.min(2.6,.9+dur*.6);env(ctx,g,t,.006,.32*v,dec);
   osc(ctx,'triangle',f,t,t+dec+.1,g);const g2=ctx.createGain();g2.gain.value=.35;g2.connect(g);osc(ctx,'sine',f*2,t,t+dec+.1,g2,3);
   const g3=ctx.createGain();g3.gain.value=.12;g3.connect(g);osc(ctx,'sine',f*3,t,t+.6,g3)},
 epiano(ctx,o,t,m,dur,v){const f=hz(m),g=ctx.createGain();g.connect(o);const dec=Math.min(2.2,.8+dur*.5);env(ctx,g,t,.01,.26*v,dec);
   osc(ctx,'sine',f,t,t+dec+.1,g);const g2=ctx.createGain();g2.gain.value=.22;g2.connect(g);osc(ctx,'sine',f*2,t,t+dec+.1,g2,-4)},
 pluck(ctx,o,t,m,dur,v){const f=hz(m),g=ctx.createGain();g.connect(o);env(ctx,g,t,.004,.3*v,.32+dur*.08);
   osc(ctx,'triangle',f,t,t+.6,g);const g2=ctx.createGain();g2.gain.value=.18;g2.connect(g);osc(ctx,'square',f*2,t,t+.12,g2)},
 bell(ctx,o,t,m,dur,v){const f=hz(m),g=ctx.createGain();g.connect(o);env(ctx,g,t,.004,.24*v,1.1+dur*.2);
   osc(ctx,'sine',f,t,t+1.6,g);const g2=ctx.createGain();g2.gain.value=.22;g2.connect(g);osc(ctx,'sine',f*2.76,t,t+.9,g2);
   const g3=ctx.createGain();g3.gain.value=.07;g3.connect(g);osc(ctx,'sine',f*5.4,t,t+.4,g3)},
 pad(ctx,o,t,ms,dur,v){const lp=ctx.createBiquadFilter();lp.type='lowpass';lp.frequency.value=1000;lp.Q.value=.3;const g=ctx.createGain();lp.connect(g);g.connect(o);
   g.gain.setValueAtTime(0,t);g.gain.linearRampToValueAtTime(.05*v,t+.5);g.gain.setValueAtTime(.05*v,t+dur);g.gain.linearRampToValueAtTime(0,t+dur+.7);
   for(const m of ms){osc(ctx,'sawtooth',hz(m),t,t+dur+.8,lp,-7);osc(ctx,'sawtooth',hz(m),t,t+dur+.8,lp,7)}},
 bass(ctx,o,t,m,dur,v){const f=hz(m),g=ctx.createGain();g.connect(o);g.gain.setValueAtTime(0,t);g.gain.linearRampToValueAtTime(.3*v,t+.012);
   g.gain.exponentialRampToValueAtTime(.12*v,t+Math.min(.4,dur));g.gain.exponentialRampToValueAtTime(.0008,t+dur+.08);
   osc(ctx,'triangle',f,t,t+dur+.1,g);const g2=ctx.createGain();g2.gain.value=.5;g2.connect(g);osc(ctx,'sine',f,t,t+dur+.1,g2)},
 kick(ctx,o,t,v){const g=ctx.createGain();g.connect(o);env(ctx,g,t,.002,.55*v,.22);const k=ctx.createOscillator();k.frequency.setValueAtTime(120,t);k.frequency.exponentialRampToValueAtTime(45,t+.12);k.connect(g);k.start(t);k.stop(t+.3)},
 nz(ctx,o,t,v,type,freq,len,q){const s=ctx.createBufferSource();s.buffer=noise(ctx);const f=ctx.createBiquadFilter();f.type=type;f.frequency.value=freq;f.Q.value=q||.8;const g=ctx.createGain();
   s.connect(f);f.connect(g);g.connect(o);env(ctx,g,t,.002,v,len);s.start(t,Math.random()*.5);s.stop(t+len+.05)},
};
const DRUM={ // 두 마디 번갈아, 한 마디 8칸: k 킥, h 하이햇, s 브러시, z 셰이커, t 틱, - 쉼
 pop:['k-h-s-h-','k-hks-h-'],
 lofi:['k-h-s-h-','k-hkh-s-'],
 shaker:['kzzzhzzz','kzzzhzzk'],
 tick:['k-t-t-t-','t-t-t-t-'],
};
function hit(ctx,o,c,t,v){if(c==='k')INST.kick(ctx,o,t,v);else if(c==='h')INST.nz(ctx,o,t,.05*v,'highpass',7000,.04);else if(c==='s')INST.nz(ctx,o,t,.09*v,'bandpass',1900,.11,.7);
  else if(c==='z')INST.nz(ctx,o,t,.035*v,'bandpass',5200,.06,1.2);else if(c==='t')INST.nz(ctx,o,t,.03*v,'highpass',9000,.025)}

// 한 칸(8분음표) 예약: 곡 t, 전체 칸 번호 s, 시각 at, 출력 o(드라이)·r(잔향 보냄)
function step(ctx,t,s,at,o,r){const b=Math.floor(s/8)%t.n,p=s%8,e=60/t.bpm/2,c=t.chords[b];
  const both=(fn)=>{fn(o);if(r)fn(r)};
  for(const[np,m,l]of t.bars[b])if(np===p)both(d=>INST[t.lead](ctx,d,at,m,l*e,d===r?.6:1));
  if(t.acc==='arp'){const tones=[c[0],c[1],c[2],c[3]||c[0]+12],pat=[0,2,1,2,3,2,1,2];both(d=>INST.epiano(ctx,d,at,tones[pat[p]]+12,e,(d===r?.3:.5)))}
  else if(t.acc==='block'&&(p===0||p===3||p===6))both(d=>c.forEach(m=>INST.pluck(ctx,d,at,m+12,e,d===r?.25:.35)));
  else if(t.acc==='pulse'&&p%2===0)both(d=>c.forEach(m=>INST.epiano(ctx,d,at,m+12,e,.3)));
  if(p===0&&(t.acc==='pad'||t.lead==='piano'&&t.acc!=='arp'))both(d=>INST.pad(ctx,d,at,c.map(m=>m+12),8*e,d===r?1.2:1));
  if(t.phase){const tones=[c[0]+24,c[1]+24,c[2]+24,(c[3]||c[0]+12)+24];if(s%3===0)both(d=>INST.bell(ctx,d,at,tones[(s/3|0)%4],e,.35));if(s%5===0)both(d=>INST.bell(ctx,d,at,tones[3-(s/5|0)%4]-12,e,.3))}
  const root=c[0]-12;
  if(t.bass==='whole'&&p===0)INST.bass(ctx,o,at,root,8*e*.95,1);
  else if(t.bass==='bounce'&&[0,3,4,6].includes(p))INST.bass(ctx,o,at,p===4?root+7:root,e*.9,.9);
  else if(t.bass==='pulse')INST.bass(ctx,o,at,root,e*.55,p===0?1:.6);
  if(t.drums){const pat=DRUM[t.drums][Math.floor(s/8)%2];hit(ctx,o,pat[p],at,1)}}
function swingAt(t,s,at){return at+(s%2?(t.swing||0)*60/t.bpm/2:0)}
function reverb(ctx){const len=ctx.sampleRate*2.4,b=ctx.createBuffer(2,len,ctx.sampleRate);for(let ch=0;ch<2;ch++){const d=b.getChannelData(ch);for(let i=0;i<len;i++)d[i]=(Math.random()*2-1)*Math.pow(1-i/len,2.6)}
  const c=ctx.createConvolver();c.buffer=b;return c}

// ---------- 재생 ----------
const KEY='vn-bgm';let on=true;try{on=localStorage.getItem(KEY)!=='off'}catch(e){}
let ctx=null,master=null,verb=null,cur=null,want='',timer=null,started=false;
function setup(){if(ctx)return;const AC=window.AudioContext||window.webkitAudioContext;if(!AC)return;ctx=new AC();
  const comp=ctx.createDynamicsCompressor();comp.threshold.value=-18;comp.ratio.value=3;master=ctx.createGain();master.gain.value=.55;comp.connect(master);master.connect(ctx.destination);
  verb=reverb(ctx);verb.connect(comp);setup.comp=comp}
function hidden(){if(document.hidden)return true;try{return !!(window.frameElement&&!window.frameElement.getClientRects().length)}catch(e){return false}}
function start(id){if(!ctx)return;const t=TRACKS[id]||(id?TRACKS['메인 테마']:null);
  if(cur){const old=cur;old.g.gain.cancelScheduledValues(ctx.currentTime);old.g.gain.setValueAtTime(old.g.gain.value,ctx.currentTime);old.g.gain.linearRampToValueAtTime(0,ctx.currentTime+1.2);
    setTimeout(()=>{try{old.g.disconnect();old.r.disconnect()}catch(e){}},1600);cur=null}
  if(!t||!on)return;const g=ctx.createGain(),r=ctx.createGain();g.gain.setValueAtTime(0,ctx.currentTime);g.gain.linearRampToValueAtTime(t.vol,ctx.currentTime+1.5);
  r.gain.value=t.verb;g.connect(setup.comp);r.connect(verb);cur={id,t,g,r,s:0,next:ctx.currentTime+.08};label(id)}
function tick(){if(!ctx||!cur)return;if(hidden()){if(ctx.state==='running')ctx.suspend();return}if(ctx.state==='suspended'){ctx.resume();cur.next=Math.max(cur.next,ctx.currentTime+.05)}
  const e=60/cur.t.bpm/2;if(cur.next<ctx.currentTime-.5)cur.next=ctx.currentTime+.05; // 오래 멈췄다 돌아오면 밀린 음을 한꺼번에 내지 않게
  while(cur.next<ctx.currentTime+.25){step(ctx,cur.t,cur.s,swingAt(cur.t,cur.s,cur.next),cur.g,cur.r);cur.s++;cur.next+=e}}
function play(id){want=id||'';if(!started||!ctx)return;if(cur&&cur.id===want)return;start(want)}
function kick(){if(started)return;setup();if(!ctx)return;started=true;ctx.resume();timer=setInterval(tick,40);start(want)}
['pointerdown','keydown','touchstart'].forEach(ev=>document.addEventListener(ev,kick,{capture:true,passive:true}));
document.addEventListener('visibilitychange',tick);
// 곡 이름 표시(곡이 바뀔 때 잠깐)
let labT=0;function label(id){const box=document.querySelector('#vn .vn-box');if(!box||id==='타이틀')return;let el=box.querySelector('.vn-bgmlab');
  if(!el){el=document.createElement('div');el.className='vn-bgmlab';el.style.cssText='position:absolute;left:12px;top:10px;z-index:5;font-size:11px;color:#fff;background:#0007;border-radius:20px;padding:3px 10px;pointer-events:none;transition:opacity .6s;opacity:0';box.appendChild(el)}
  el.textContent='♪ '+id;el.style.opacity='1';clearTimeout(labT);labT=setTimeout(()=>{el.style.opacity='0'},2600)}
// 아래 버튼 줄에 「음악」 켜고 끄기
function addButton(){const bar=document.querySelector('#vn .vn-bar');if(!bar||bar.querySelector('#vnMusic'))return;const b=document.createElement('button');b.id='vnMusic';b.textContent='음악';
  b.setAttribute('aria-pressed',String(on));b.addEventListener('click',e=>{e.stopPropagation();on=!on;b.setAttribute('aria-pressed',String(on));try{localStorage.setItem(KEY,on?'on':'off')}catch(_){}
    if(!started)kick();else if(on){const w=want;cur=null;start(w)}else start('')});bar.insertBefore(b,bar.firstChild)}
document.addEventListener('DOMContentLoaded',addButton);setTimeout(addButton,0);
// 미리 듣기용: OfflineAudioContext 에 곡을 loops 번 그려 넣는다(점검·견본 파일 만들 때)
function render(octx,id,loops){const t=TRACKS[id];const comp=octx.createDynamicsCompressor();comp.threshold.value=-18;comp.ratio.value=3;const m=octx.createGain();m.gain.value=.55;comp.connect(m);m.connect(octx.destination);
  const v=reverb(octx);v.connect(comp);const g=octx.createGain();g.gain.value=t.vol;g.connect(comp);const r=octx.createGain();r.gain.value=t.verb;r.connect(v);
  const e=60/t.bpm/2,N=t.n*8*(loops||1);for(let s=0;s<N;s++)step(octx,t,s,swingAt(t,s,.05+s*e),g,r);return N*e+.05}
window.VN_BGM={play,TRACKS,render,get on(){return on},get now(){return cur&&cur.id||''},get state(){return ctx?ctx.state:''}};
})();
