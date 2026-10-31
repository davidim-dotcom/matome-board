/*
===== VN 엔진 (데이터 구동) =====
필요: window.VN_SCRIPT (vn-script) / 선택: window.VN_ASSETS (vn-assets)
  VN_ASSETS = { bg:{id:url}, ch:{id:url | {face:url}}, cg:{id:url} }
  리소스가 없는 항목은 색 배경·이니셜 실루엣으로 대체되므로 일부만 넣어도 동작함.
  마운트 위치: <section id="vn">
*/
(function(){
'use strict';
const root=document.getElementById('vn');const SC=window.VN_SCRIPT;if(!root||!SC)return;
const AS=window.VN_ASSETS||{bg:{},ch:{},cg:{}};AS.bg=AS.bg||{};AS.ch=AS.ch||{};AS.cg=AS.cg||{};
const KEY='vn-'+(SC.meta&&SC.meta.title||'game');
const BGCOL={classroom:['#bfe4f2','#f3efe6'],physlab:['#cfe0d8','#f0efe8'],myroom:['#3b3550','#6b5f88'],street:['#ffe2b8','#bfe4f2'],bingsu:['#ffd6e0','#fff4ee'],hallway:['#2b3248','#4a5470'],stairs:['#f2b48a','#5a4a6a'],festival:['#ffe9a8','#ffc6d8'],station:['#f0b48a','#4a5a7a'],hall:['#d8d8e8','#f6f6fa'],library:['#e8dcc4','#f6f1e6'],riverside:['#1c2448','#3a2f5a'],park:['#f4b98a','#6a5a8a'],hanaroom:['#2f3a5a','#5a6a8a'],karaoke:['#3a1f5a','#c04a8a'],arcade:['#1a1a3a','#4a2a8a'],entrance:['#d9a88a','#6a6a8a'],train:['#cfe6c8','#9fc4e0']};
const BGNAME={classroom:'교실',physlab:'물리실',myroom:'방',street:'거리',bingsu:'빙수 가게',hallway:'복도',stairs:'옥상 계단',festival:'문화제 전시실',station:'역 플랫폼',hall:'대학 강당',library:'도서관',riverside:'강변 (밤)',park:'공원 (밤)',hanaroom:'하나의 방',karaoke:'노래방',arcade:'오락실',entrance:'관사 아파트 현관',train:'기차 안'};
const CGNAME={earphone:'이어폰 한쪽',rhythm:'리듬게임 대결',bingsu3:'셋이서 빙수',fireworks:'강변 불꽃놀이',karaoke:'노래방 98점',classphoto:'문화제 단체 사진',servertree:'서버 크리스마스 트리',craft:'옆집 두 채',bully:'복도',stairs:'옥상 계단',festival:'진자 파동 아트',farewell:'플랫폼',empty:'빈 플랫폼'};
// ---------- persistent store ----------
let P;try{P=JSON.parse(localStorage.getItem(KEY)||'null')||{}}catch(e){P={}}
P.slots=P.slots||[null,null,null];P.endings=P.endings||[];P.cgs=P.cgs||[];
const persist=()=>{try{localStorage.setItem(KEY,JSON.stringify(P))}catch(e){}};
// ---------- markup ----------
root.innerHTML=`<div class="panel" style="padding:10px">
<div class="vn-box" id="vnBox">
 <div class="vn-bg" id="vnBg"><span class="lab" id="vnBgLab"></span></div>
 <div class="vn-chars" id="vnChars"></div><div class="vn-cap" id="vnCap"></div>
 <div class="vn-cg" id="vnCg"></div>
 <div class="vn-text" id="vnText"><span class="vn-name" id="vnName"></span><span id="vnLine"></span><span class="vn-next" id="vnNext">▼</span></div>
 <div class="vn-choice" id="vnChoice"></div>
 <div class="vn-card" id="vnCard"><div class="n" id="vnCardN"></div><div class="t" id="vnCardT"></div></div>
 <div class="vn-panel" id="vnPanel"><button class="x" id="vnPX">×</button><div id="vnPB"></div></div>
 <div class="vn-title" id="vnTitle"><h2>${SC.meta.title}</h2><p>${SC.meta.sub||''}</p>
  <button id="vnNew">처음부터</button><button id="vnCont">이어하기</button><button id="vnLoadT">불러오기</button><button id="vnGalT">갤러리</button></div>
</div>
<div class="vn-bar"><button id="vnLog">로그</button><button id="vnAuto" aria-pressed="false">자동</button><button id="vnSkip" aria-pressed="false">스킵</button><button id="vnSave">저장</button><button id="vnStat">상태</button><button id="vnMenu">타이틀</button></div>
</div>`;
const $=id=>document.getElementById(id);
// ---------- state ----------
let G=null,typing=null,full='',auto=false,skip=false,timer=null,log=[];
const fresh=name=>({scene:SC.start,idx:0,vars:Object.assign({},SC.vars),flags:{},chars:{},bg:null,cg:null,bgm:'',name});
const fill=s=>String(s).replace(/\{p\}/g,G?G.name:'나');
// ---------- render ----------
function setBg(id){if(G)G.bg=id;const u=AS.bg[id];const el=$('vnBg');if(u){el.style.backgroundImage=`url("${u}")`;$('vnBgLab').textContent=''}else{const c=BGCOL[id]||['#666','#999'];el.style.backgroundImage=`linear-gradient(180deg,${c[0]},${c[1]})`;$('vnBgLab').textContent=BGNAME[id]||id||''}}
function setCg(id){if(G)G.cg=id;const el=$('vnCg');if(!id){el.classList.remove('on');return}
  if(!P.cgs.includes(id)){P.cgs.push(id);persist()}
  const u=AS.cg[id];el.style.backgroundImage=u?`url("${u}")`:'';el.innerHTML=u?'':`<div class="lab">[이벤트 그림] ${CGNAME[id]||id}<br><small style="opacity:.6">일러스트 준비 중</small></div>`;el.classList.add('on')}
const POS={l:22,c:50,r:78};
function drawChars(speaker){const box=$('vnChars');box.innerHTML='';for(const [ch,o] of Object.entries(G.chars)){const d=document.createElement('div');d.className='vn-ch'+(speaker&&speaker!==ch?' dim':'');d.style.left=POS[o.at||'c']+'%';
  const a=AS.ch[ch];const u=a&&(typeof a==='string'?a:(a[o.face||'normal']||a.normal||Object.values(a)[0]));const info=SC.chars[ch]||{name:ch,color:'#888'};
  d.innerHTML=u?`<img src="${u}" alt="">`:`<div class="sil" style="background:${info.color}">${fill(info.name).slice(0,1)}</div>`;box.appendChild(d)}}
function card(n,t,cb){$('vnCardN').textContent=n?`제${n}장`:'';$('vnCardT').textContent=t;const c=$('vnCard');c.classList.add('on');setTimeout(()=>{c.classList.remove('on');cb()},skip?300:1800)}
function show(who,text){const info=who?SC.chars[who]:null;const nm=$('vnName');nm.textContent=info?fill(info.name):'';nm.style.background=info?info.color:'';
  $('vnText').classList.toggle('nar',!who);full=fill(text);log.push((info?fill(info.name)+': ':'')+full);if(log.length>200)log.shift();
  drawChars(who);const line=$('vnLine');line.textContent='';$('vnNext').style.display='none';let i=0;clearInterval(typing);
  if(skip){line.textContent=full;typing=null;$('vnNext').style.display='';schedule();return}
  typing=setInterval(()=>{i+=2;line.textContent=full.slice(0,i);if(i>=full.length){clearInterval(typing);typing=null;$('vnNext').style.display='';schedule()}},28)}
function schedule(){clearTimeout(timer);if(skip)timer=setTimeout(advance,60);else if(auto)timer=setTimeout(advance,1200+full.length*45)}
// ---------- ops ----------
function applyEff(eff,flag){if(eff)for(const [k,v] of Object.entries(eff))G.vars[k]=(G.vars[k]||0)+v;
  if(flag&&!G.flags[flag]){G.flags[flag]=true;if((SC.wallFlags||[]).includes(flag))G.vars.WALL=Math.max(0,(G.vars.WALL||0)-1)}
  G.vars.TRUST=Math.max(0,Math.min(100,G.vars.TRUST||0))}
function go(scene){G.scene=scene;G.idx=0}
function run(){for(let guard=0;guard<500;guard++){const ops=SC.scenes[G.scene];if(!ops){console.warn('no scene',G.scene);return toTitle()}
  const op=ops[G.idx];if(!op){return toTitle()}G.idx++;
  if(op.when&&!G.flags[op.when])continue;if(op.unless&&G.flags[op.unless])continue;if(op.whenVar&&!((G.vars[op.whenVar[0]]||0)>=op.whenVar[1]))continue;
  switch(op.t){
   case 'bg':setBg(op.id);break;
   case 'bgm':G.bgm=op.id;break;
   case 'caption':G.cap=op.text;$('vnCap').textContent=op.text||'';break;
   case 'show':G.chars[op.ch]={at:op.at||'c',face:op.face};drawChars();break;
   case 'hide':if(op.ch==='*')G.chars={};else delete G.chars[op.ch];drawChars();break;
   case 'cg':setCg(op.id);break;
   case 'cgoff':setCg(null);break;
   case 'set':applyEff(op.eff,op.flag);break;
   case 'jump':go(op.go);break;
   case 'if':go(G.flags[op.flag]?op.go:(op.else||op.go));break;
   case 'ending':{const e=SC.endings.find(x=>x.cond(G.vars));G.ending=e.id;if(!P.endings.includes(e.id)){P.endings.push(e.id);persist()}go(e.go);break}
   case 'chapter':autosave();return card(op.n,op.title,run);
   case 'say':if(op.face&&G.chars[op.who])G.chars[op.who].face=op.face;return show(op.who,op.text);
   case 'nar':return show(null,op.text);
   case 'choice':return choose(op);
   case 'end':skip=false;$('vnSkip').setAttribute('aria-pressed','false');return card(0,`엔딩 ${G.ending||''} 「${(SC.endings.find(x=>x.id===G.ending)||{}).name||''}」`,toTitle);
  }}}
function choose(op){clearTimeout(timer);if(skip){skip=false;$('vnSkip').setAttribute('aria-pressed','false')}
  const box=$('vnChoice');box.innerHTML='';op.opts.filter(o=>!o.need||G.flags[o.need]).forEach(o=>{const b=document.createElement('button');b.textContent=fill(o.text);
   b.addEventListener('click',e=>{e.stopPropagation();box.classList.remove('on');log.push('▶ '+fill(o.text));applyEff(o.eff,o.flag);if(o.go)go(o.go);run()});box.appendChild(b)});box.classList.add('on')}
function advance(){if(!G||$('vnChoice').classList.contains('on')||$('vnCard').classList.contains('on')||$('vnPanel').classList.contains('on'))return;
  if(typing){clearInterval(typing);typing=null;$('vnLine').textContent=full;$('vnNext').style.display='';schedule();return}run()}
// ---------- save/load ----------
const snap=()=>JSON.parse(JSON.stringify(Object.assign({},G,{idx:Math.max(0,G.idx-1),t:Date.now()})));
function autosave(){if(!G)return;P.auto=snap();persist()}
function restore(s){G=JSON.parse(JSON.stringify(s));log=[];$('vnTitle').style.display='none';$('vnCap').textContent=G.cap||'';setBg(G.bg||'classroom');setCg(G.cg);drawChars();run()}
function toTitle(){clearTimeout(timer);clearInterval(typing);typing=null;auto=skip=false;['vnAuto','vnSkip'].forEach(id=>$(id).setAttribute('aria-pressed','false'));
  $('vnCont').disabled=!P.auto;$('vnTitle').style.display='flex'}
function panel(html){$('vnPB').innerHTML=html;$('vnPanel').classList.add('on')}
$('vnPX').addEventListener('click',e=>{e.stopPropagation();$('vnPanel').classList.remove('on')});
const fmtT=t=>t?new Date(t).toLocaleString('ko-KR',{month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'}):'';
function slotsPanel(mode){const rows=P.slots.map((s,i)=>`<div class="vn-slot"><div><b>슬롯 ${i+1}</b><br>${s?`${s.scene} · 신뢰 ${s.vars.TRUST} · ${fmtT(s.t)}`:'비어 있음'}</div>${mode==='save'&&G?`<button data-s="${i}">저장</button>`:''}${s?`<button class="ld" data-l="${i}">불러오기</button>`:''}</div>`).join('');
  panel(`<h3>${mode==='save'?'저장':'불러오기'}</h3>${rows}`);
  $('vnPB').querySelectorAll('[data-s]').forEach(b=>b.addEventListener('click',()=>{P.slots[+b.dataset.s]=snap();persist();slotsPanel(mode)}));
  $('vnPB').querySelectorAll('[data-l]').forEach(b=>b.addEventListener('click',()=>{$('vnPanel').classList.remove('on');restore(P.slots[+b.dataset.l])}))}
function galPanel(){const cg=Object.keys(CGNAME).map(id=>{const got=P.cgs.includes(id),u=AS.cg[id];return `<div style="${got&&u?`background-image:url('${u}')`:''}">${got?(u?'':CGNAME[id]):'？'}</div>`}).join('');
  const en=SC.endings.map(e=>`<div class="row">${P.endings.includes(e.id)?`<b>${e.id}</b> ${e.name}`:`${e.id} ？？？`}</div>`).join('');
  panel(`<h3>갤러리</h3><div class="vn-gal">${cg}</div><h3 style="margin-top:16px">엔딩</h3>${en}`)}
// ---------- controls ----------
$('vnBox').addEventListener('click',advance);
document.addEventListener('keydown',e=>{if(root.closest('[hidden]')||root.hidden)return;if(e.key===' '||e.key==='Enter'){e.preventDefault();advance()}});
$('vnNew').addEventListener('click',e=>{e.stopPropagation();const n=(prompt('주인공 이름',(P.lastName||'유진'))||'유진').trim().slice(0,8)||'유진';P.lastName=n;persist();G=fresh(n);log=[];$('vnCap').textContent='';$('vnTitle').style.display='none';setBg('classroom');setCg(null);drawChars();run()});
$('vnCont').addEventListener('click',e=>{e.stopPropagation();if(P.auto)restore(P.auto)});
$('vnLoadT').addEventListener('click',e=>{e.stopPropagation();slotsPanel('load')});
$('vnGalT').addEventListener('click',e=>{e.stopPropagation();galPanel()});
$('vnLog').addEventListener('click',()=>panel(`<h3>로그</h3>${log.slice(-60).map(l=>`<div class="row">${l.replace(/</g,'&lt;')}</div>`).join('')||'<div class="row">아직 없음</div>'}`));
$('vnAuto').addEventListener('click',e=>{auto=!auto;e.currentTarget.setAttribute('aria-pressed',String(auto));if(auto&&!typing)schedule()});
$('vnSkip').addEventListener('click',e=>{skip=!skip;e.currentTarget.setAttribute('aria-pressed',String(skip));if(skip&&!typing)schedule()});
$('vnSave').addEventListener('click',()=>{if(G)slotsPanel('save')});
$('vnStat').addEventListener('click',()=>{if(!G)return;const v=G.vars;const fl=Object.keys(G.flags);
  panel(`<h3>상태</h3><div>신뢰 ${v.TRUST}/100</div><div class="vn-meter"><i style="width:${v.TRUST}%"></i></div><div>마음의 벽 ${v.WALL}/5</div><div class="vn-meter"><i style="width:${v.WALL*20}%;background:#6aa9ff"></i></div><div class="row">플래그: ${fl.length?fl.join(', '):'없음'}</div><div class="row">현재 장면: ${G.scene}</div><div class="row" style="opacity:.7">엔딩 A 조건: 신뢰 85 이상 · 벽 1 이하</div>`)});
$('vnMenu').addEventListener('click',()=>{autosave();toTitle()});
window.addEventListener('pagehide',autosave);
setBg('classroom');toTitle();
})();
