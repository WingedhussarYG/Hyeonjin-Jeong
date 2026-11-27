'use strict';
const $=id=>document.getElementById(id),rts=id=>['world-of-realms','galactic-realms'].includes(id);
const mobile=()=>/Android|iPhone|iPad|iPod|Mobile/i.test(navigator.userAgent)||(navigator.platform==='MacIntel'&&navigator.maxTouchPoints>1);
const shelves=[
 {id:'sport',title:'스포츠 엠파이어 계열',games:['sports-empire','touchline-manager','dugout-manager','gridiron-manager','pit-manager','e-champion-manager']},
 {id:'adventure',title:'항해 및 우주개척 계열',games:['azure-voyage','chronica-divina','bluewater-command']},
 {id:'strategy',title:'전략 시뮬레이션 계열',games:['world-of-realms','galactic-realms']}
];
function gameLocale(id,lang){
 const region={ko:'ko-KR',en:'en-GB',es:'es-ES',ja:'ja-JP',zh:'zh-CN',de:'de-DE',fr:'fr-FR'};
 if(rts(id))return lang;
 if(id==='chronica-divina')return ['en','es','zh'].includes(lang)?region[lang]:lang;
 return region[lang]||'en-GB';
}
const parentOrigin=location.origin, origins=new Map(),waiters=new Map();
let catalog=[],platforms={},filter='all',me={},locale='ko',dict={},working=false,timer;
const t=(k,f)=>dict[locale]?.[k]||dict.en?.[k]||f||k;
const fmt=(key,args)=>t(key).replace(/\{(\w+)\}/g,(m,k)=>Object.hasOwn(args,k)?String(args[k]):m);
const name=g=>locale==='ko'?g.title:t(g.id,g.title);
const notice=msg=>{clearTimeout(timer);$('notice').textContent=msg;$('notice').hidden=!msg;if(msg)timer=setTimeout(()=>$('notice').hidden=true,10000);};
async function result(r){if(!r.ok)throw Error(r.status===401?t('needLogin'):t('failed')+' ('+r.status+')');return r.json();}
function resolveLanguage(value){return Object.hasOwn(dict,value)?value:null;}
function browserLanguage(){return (navigator.languages||[navigator.language]).map(x=>resolveLanguage(x.toLowerCase().split('-')[0])).find(Boolean)||'en';}
function localize(){document.title=t('pageTitle');const appLink=$('languageApp');appLink.hidden=!mobile();appLink.href='lucidgames://language?lang='+locale;document.querySelector('.wiki').search='?lang='+locale;
 for(const el of document.querySelectorAll('[data-label]'))el.setAttribute('aria-label',t(el.dataset.label));
 for(const option of $('linkgame').options){const game=catalog.find(x=>x.id===option.value);if(game)option.textContent=name(game);}document.documentElement.lang=locale;for(const n of document.querySelectorAll('[data-t]'))n.textContent=t(n.dataset.t,n.textContent);if(me.signedIn)$('account').textContent=t('signout');render();renderPlatforms();}
function render(){
 const grid=$('grid');grid.replaceChildren();
 for(const shelf of shelves){
  if(filter!=='all'&&filter!==shelf.id)continue;
  const games=shelf.games.map(id=>catalog.find(g=>g.id===id)).filter(Boolean);
  if(!games.length)continue;
  const section=document.createElement('section'),title=document.createElement('h2'),cards=document.createElement('div');
  title.textContent=t('shelf'+shelf.id[0].toUpperCase()+shelf.id.slice(1));title.id='shelf-'+shelf.id;section.setAttribute('aria-labelledby',title.id);
  cards.className='grid';section.append(title,cards);
  for(const g of games){
   const card=document.createElement('article'),icon=new Image(),heading=document.createElement('h3'),play=document.createElement('button');
   card.className='tile';icon.src='/assets/'+g.id+'.svg';icon.alt='';heading.textContent=name(g);
   const blocked=mobile()&&rts(g.id),ready=me.ready?.includes(g.id);
   play.textContent=blocked?t('desktopOnly'):ready?t('play'):t('preparing');play.disabled=blocked||!ready;
   play.onclick=()=>run(async()=>{if(!me.signedIn){location.assign('/signin-with-chatgpt?return_to=%2F');return;}await startGame(g);});
   card.append(icon,heading,play);cards.append(card);
  }
  grid.append(section);
 }
}
function renderPlatforms(){
 const w=$('platforms');w.replaceChildren();
 const labels={'windows-x64':'Windows x64','macos-arm64':'macOS · Apple Silicon','macos-x64':'macOS · Intel','linux-x64':'Linux x64','android':'Android','ios':'iPhone · iPad'};
 for(const [key,label] of Object.entries(labels)){
  const available=platforms[key],a=document.createElement(available?'a':'button');
  a.textContent=label+(available?' '+t('download'):' · '+t('unreleased'))+(key==='ios'&&available?.name?.includes('requires-personal-signing')?' · '+t('personalSigning'):'');
  if(available)a.href=typeof available==='string'?available:'/download/'+key+'?lang='+locale;else a.disabled=true;
  w.append(a);
 }
}
async function run(fn){if(working)return;working=true;try{await fn();}catch(e){notice(e.message||t('failed'));}finally{working=false;}}
function random(){return crypto.randomUUID();}
window.addEventListener('message',e=>{const w=waiters.get(e.data?.requestId);if(!w||w.win!==e.source||w.origin!==e.origin)return;if(e.data.error)w.reject(Error(e.data.error));else w.resolve(e.data.value);});
function waitFor(id,win,origin,ms=90000){return new Promise((resolve,reject)=>{const tm=setTimeout(()=>{waiters.delete(id);reject(Error(t('timeout')));},ms);const finish=fn=>x=>{clearTimeout(tm);waiters.delete(id);fn(x);};waiters.set(id,{win,origin,resolve:finish(resolve),reject:finish(reject)});});}
async function bridge(g,action,extra={}){const origin=origins.get(g.id),{ticket}=await fetch('/api/launcher/ticket',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({game:g.id,desktopMode:!mobile(),action})}).then(result);
 const frame=document.createElement('iframe'),handshake=random();frame.name='lucid-'+handshake;frame.title=name(g);frame.allowFullscreen=true;(action==='play'?$('stage'):$('bridges')).append(frame);
 const ready=waitFor(handshake,frame.contentWindow,origin,35000),form=document.createElement('form');form.method='POST';form.action=origin+'/__launcher/open';form.target=frame.name;
 for(const [key,value] of Object.entries({ticket,handshake,action,lang:locale,...extra})){const input=document.createElement('input');input.name=key;input.value=value;input.type='hidden';form.append(input);}document.body.append(form);form.submit();form.remove();
 let hello;try{hello=await ready;}catch(e){frame.remove();throw Error(name(g)+' · '+e.message);}
 return {frame,profile:hello?.profile,rpc(type,data={}){const requestId=random(),p=waitFor(requestId,frame.contentWindow,origin);frame.contentWindow.postMessage({type,data,requestId},origin);return p;}};}
async function eachGame(action,data){const games={};for(const g of catalog){if(data&&!Object.hasOwn(data,g.id))continue;if(!me.ready?.includes(g.id))throw Error(name(g)+' · '+t('savingNotReady'));

 notice(name(g)+' …');const b=await bridge(g,'save');try{games[g.id]=await b.rpc(action,data?.[g.id]);}finally{b.frame.remove();}}return games;}
function mustLogin(){if(!me.signedIn)throw Error(t('needLogin'));}
$('export').onclick=()=>run(async()=>{mustLogin();const failed=await scanAll();if(failed.length&&!confirm(t('recheckGames')+' · '+failed.join(', ')+'\n'+t('downloadLast')))return;const a=document.createElement('a');a.href='/api/account-save';a.download='lucid-games-save.json';a.click();});
$('import').onclick=()=>{if(!me.signedIn){notice(t('needLogin'));return;}$('savefile').value='';$('savefile').click();};
$('savefile').onchange=()=>run(async()=>{const f=$('savefile').files[0];if(!f)return;if(f.size>512*1024*1024)throw Error(t('badSave'));const obj=JSON.parse(await f.text());if(obj?.format!=='lucid-games-save'||obj.version!==1||!obj.games||typeof obj.games!=='object'||Array.isArray(obj.games)||Object.keys(obj.games).some(id=>!origins.has(id)))throw Error(t('badSave'));
 const branches=normalizePortableSlots(obj);const picked=await pickArchive(obj);if(!picked)return;const only=Object.fromEntries(Object.entries(picked).filter(([id,g])=>rts(id)?Object.keys(g.files||{}).length:g.saves?.length));if(!Object.keys(only).length)throw Error(t('empty'));const plans=await eachGame('inspect',only);if(!confirm(t('overwrite')+'\n'+Object.keys(only).map(id=>name(catalog.find(g=>g.id===id))).join(', '))){notice('');return;}
 for(const {game,data} of branches){
  const g=catalog.find(x=>x.id===game);const key=await fingerprint(['portable-profile',game,rowsFor(g,data).map(x=>x.state)]);
  await storeCollection(g,key,data,true);
 }
 const done=[];try{for(const g of catalog.filter(g=>only[g.id])){const b=await bridge(g,'save');try{await b.rpc('import',{data:only[g.id],plan:plans[g.id]});done.push(name(g));await capture(g,b);}finally{b.frame.remove();}}}catch(e){throw Error(e.message+'\n'+t('completed')+' '+done.join(', '));}notice(t('imported'));});
$('filters').onclick=e=>{if(!e.target.dataset.filter)return;filter=e.target.dataset.filter;for(const n of $('filters').children)n.setAttribute('aria-pressed',String(n===e.target));render();};
const gameScreen=$('gameScreen');
function inGameFullscreen(){
 return (document.fullscreenElement||document.webkitFullscreenElement)===gameScreen;
}
async function changeGameFullscreen(enter){
 try{
  $('screenError').textContent='';
  if(enter)await (gameScreen.requestFullscreen||gameScreen.webkitRequestFullscreen).call(gameScreen);
  else if(inGameFullscreen())await (document.exitFullscreen||document.webkitExitFullscreen).call(document);
 }catch{
  $('screenError').textContent=t('screenFailed');
 }
}
$('enterScreen').onclick=()=>changeGameFullscreen(true);
$('exitScreen').onclick=()=>changeGameFullscreen(false);
function restoreGameFocus(){
 if(!$('player').open)return;
 if(inGameFullscreen())$('stage').querySelector('iframe')?.focus();
 else if(!$('enterScreen').hidden)$('enterScreen').focus();
}
document.addEventListener('fullscreenchange',restoreGameFocus);
document.addEventListener('webkitfullscreenchange',restoreGameFocus);
$('close').onclick=()=>{if(confirm(t('leave'))){$('player').close();$('stage').replaceChildren();clearInterval(periodic);const g=currentGame;currentGame=null;if(g)capture(g).catch(()=>notice(name(g)+' · '+t('recheckSave')));}};$('player').oncancel=e=>{e.preventDefault();if(inGameFullscreen())void changeGameFullscreen(false);else $('close').click();};
$('language').onchange=e=>{const choice=e.target.value;localStorage.setItem('lucid.launcher.language',choice);locale=resolveLanguage(choice)||browserLanguage();const url=new URL(location.href);url.searchParams.delete('lang');history.replaceState(null,'',url);localize();showRecovery();};
$('account').onclick=async e=>{if(me.signedIn){e.preventDefault();try{await fetch('/api/logout',{method:'POST'}).then(result);location.assign('/signout-with-chatgpt?return_to=%2F');}catch(err){notice(err.message);}}};
const recoveryKey='lucid.sports.recovery.v1';
function recovery(){
 try{const v=JSON.parse(sessionStorage.getItem(recoveryKey));if(v&&me.signedIn&&v.account===me.email&&Array.isArray(v.ids)&&[6,catalog.length].includes(v.ids.length)&&new Set(v.ids).size===v.ids.length&&v.ids.every(id=>origins.has(id))&&Number.isInteger(v.index)&&v.index>=0&&v.index<v.ids.length)return v;}catch{}
 return null;
}
function saveRecovery(v){sessionStorage.setItem(recoveryKey,JSON.stringify(v));}
function openOriginal(id){const url=origins.get(id);if(url)location.assign(url+'/__launcher/connect');}
function recoveryLine(g,row){
 return name(g)+' · '+(rts(g.id)?fmt('fileCount',{n:row.files}):fmt('slotCounts',{p:row.player,s:row.sandbox}));
}
function showRecovery(msg){
 const v=recovery();$('allSports').hidden=!!v;$('resumeLinks').hidden=!v;$('stopLinks').hidden=!v;
 $('linkStatus').textContent=msg||(v?fmt('recoveryStep',{i:v.index,n:v.ids.length,game:name(catalog.find(g=>g.id===v.ids[v.index]))}):'');
}
(async()=>{const [i,c,s,p]=await Promise.all([fetch('/languages.json').then(result),fetch('/api/launcher/modules').then(result),fetch('/api/session').then(result),fetch('/api/launcher/installers').then(result)]);dict=i;catalog=c.games;catalog.forEach(g=>origins.set(g.id,'https://'+g.id+'.maxfaine.chatgpt.site'));me=s;platforms=p;for(const game of catalog){const option=document.createElement('option');option.value=game.id;option.textContent=name(game);$('linkgame').append(option);}
 $('linkold').onclick=()=>run(async()=>{mustLogin();sessionStorage.removeItem(recoveryKey);await beforeLink($('linkgame').value);});
 $('unlink').onclick=()=>run(async()=>{mustLogin();const g=catalog.find(g=>g.id===$('linkgame').value);await capture(g);const b=await bridge(g,'save',{reset:'1'});try{await capture(g,b);}finally{b.frame.remove();}$('linkStatus').textContent=name(g)+' · '+t('initialSlots');});
 $('allSports').onclick=()=>run(async()=>{if(!me.signedIn){location.assign('/signin-with-chatgpt?return_to=%2F%23recover');return;}const state={account:me.email,ids:catalog.map(g=>g.id),index:0};saveRecovery(state);await beforeLink(state.ids[0]);});
 $('resumeLinks').onclick=()=>{const state=recovery();if(state&&state.index<state.ids.length)run(()=>beforeLink(state.ids[state.index]));};
 $('stopLinks').onclick=()=>{sessionStorage.removeItem(recoveryKey);showRecovery(t('stopped'));};
 const incoming=resolveLanguage(new URLSearchParams(location.search).get('lang'));const saved=resolveLanguage(localStorage.getItem('lucid.launcher.language'));locale=incoming||saved||browserLanguage();$('language').value=incoming||saved||'auto';localize();showRecovery();if(await openDevicePrompt(me))return;
 const linked=/^#link=([a-z-]+):([a-f0-9-]{36})$/.exec(location.hash);
 if(linked){
  const g=catalog.find(g=>g.id===linked[1]);
  history.replaceState(null,'','/#recover');$('recover').scrollIntoView();
  if(!g||!me.signedIn){showRecovery(t('sameAccount'));return;}
  try{
   const b=await bridge(g,'save',{proof:linked[2]});let row;try{await restoreMissing(g,b);row=await capture(g,b);}finally{b.frame.remove();}
   const state=recovery();
   if(state&&state.ids[state.index]===g.id){state.counts={...state.counts,[g.id]:row};state.index++;saveRecovery(state);
    if(state.index<state.ids.length){await beforeLink(state.ids[state.index]);return;}
    sessionStorage.removeItem(recoveryKey);showRecovery(t('verifiedRecords')+'\n'+catalog.filter(x=>state.counts[x.id]).map(x=>recoveryLine(x,state.counts[x.id])).join('\n'));
   }else{showRecovery(t('linked')+' · '+recoveryLine(g,row));}
  }catch(e){showRecovery(name(g)+' · '+t('linkFailure')+' '+e.message+' '+t('retryLink'));}
 }else if(me.signedIn&&!recovery()){scanAll().catch(()=>notice(t('checkAccount')));}
})().catch(e=>notice(e.message));
