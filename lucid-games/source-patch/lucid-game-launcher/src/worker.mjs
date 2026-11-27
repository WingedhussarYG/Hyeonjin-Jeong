const origin='https://lucid-game-launcher.maxfaine.chatgpt.site';
const noStore={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer'};
const json=(v,s=200)=>Response.json(v,{status:s,headers:noStore});
const deny=(s)=>json({error:s===401?'로그인이 필요합니다.':'요청을 처리할 수 없습니다.'},s);
const hex=b=>Array.from(new Uint8Array(b),x=>x.toString(16).padStart(2,'0')).join('');
const hash=async b=>hex(await crypto.subtle.digest('SHA-256',typeof b==='string'?new TextEncoder().encode(b):b));
const random=()=>hex(crypto.getRandomValues(new Uint8Array(32)));
const byGame=id=>CATALOG.find(g=>g.id===id);
const desk=id=>['galactic-realms','world-of-realms'].includes(id);
const mobile=r=>/Android|iPhone|iPad|iPod|Mobile/i.test(r.headers.get('user-agent')||'')||r.headers.get('sec-ch-ua-mobile')==='?1';
const same=r=>r.headers.get('origin')===new URL(r.url).origin;
async function metadata(bucket,k){const obj=await bucket.get(k);return obj?obj.json():null;}
async function set(bucket,k,v){return bucket.put(k,JSON.stringify(v));}
function identity(r){const sub=r.headers.get('oai-authenticated-user-id'),email=r.headers.get('oai-authenticated-user-email');return sub&&email?{sub,email}:null;}
async function auth(r,env,u){
 const b=env.BUCKET,me=identity(r),p=u.pathname;
 if(p==='/api/session'&&r.method==='GET')return json({signedIn:!!me,email:me?.email,ready:(env.LUCID_READY_GAMES||'').split(',').filter(Boolean)});
 if(p==='/api/launcher/ticket'&&r.method==='POST'){
  if(!me||!same(r))return deny(me?403:401);
  const {game,desktopMode,action}=await r.json();if(!byGame(game)||desk(game)&&action!=='save'&&(mobile(r)||desktopMode===false))return deny(403);
  const userKey=await hash(me.sub), key=random(), now=Date.now();
  await set(b,'ticket/'+await hash(key),{...me,game,userKey,until:now+90000,issued:now});
  return json({ticket:key});
 }
 if(p==='/api/launcher/exchange'&&r.method==='POST'){
  const {game,ticket}=await r.json();if(!byGame(game)||! /^[a-f0-9]{64}$/.test(ticket||''))return deny(401);
  const key='ticket/'+await hash(ticket), ob=await b.get(key);if(!ob)return deny(401);
  const data=await ob.json();if(data.until<Date.now()||data.game!==game)return deny(401);
  const claim=await b.put(key,'{}',{onlyIf:{etagMatches:ob.etag}});if(!claim)return deny(401);
  const token=random();data.until=Date.now()+12*3600*1000;await set(b,'session/'+await hash(token),data);await b.delete(key);
  return json({token,...data});
 }
 if(p==='/api/launcher/identity'&&r.method==='POST'){
  const token=(r.headers.get('authorization')||'').replace(/^Bearer /,'');
  if(!/^[a-f0-9]{64}$/.test(token))return deny(401);
  const data=await metadata(b,'session/'+await hash(token));if(!data||data.until<Date.now()||data.game!==(await r.json()).game)return deny(401);
  const expired=await metadata(b,'revoked/'+data.userKey);
  return Number(expired)>=data.issued?deny(401):json({sub:data.sub,email:data.email});
 }
 if(p==='/api/logout'&&r.method==='POST'){if(!me||!same(r))return deny(403);await set(b,'revoked/'+await hash(me.sub),Date.now());return json({ok:true});}
 return null;
}
async function fileResponse(r,b,file,language,packagedLanguage=null){
 if(!file)return deny(404);
 const headers={'Content-Type':'application/octet-stream','Content-Length':String(file.bytes),'ETag':'"'+file.sha256+'"','X-Content-Type-Options':'nosniff','Content-Disposition':'attachment; filename="'+file.name+'"','Cache-Control':'private,no-transform'};
 if(packagedLanguage)headers['Content-Language']=packagedLanguage;
 const localeSet=DESKTOP_LOCALES[file.sha256],variant=localeSet?.hashes[language];
 if(variant){
  headers.ETag='"'+variant+'"';
  headers['Content-Language']=language;
  headers['Content-Disposition']='attachment; filename="'+file.name.replace(/\.zip$/,'-'+language+'.zip')+'"';
 }
 if(file.object)return sourceDownload(r,b,file,headers);
 if(r.method==='HEAD')return new Response(null,{headers});if(r.method!=='GET')return deny(405);
 let index=0,reader,cursor=0;
 const stream=new ReadableStream({async pull(controller){try{
  while(true){if(!reader){if(index===file.parts.length){controller.close();return;}const part=await b.get('chunk/'+file.parts[index++].sha256);if(!part)throw Error('Missing release chunk');reader=part.body.getReader();}
  const {value,done}=await reader.read();if(!done){let output=value;
   if(variant){
    for(const offset of localeSet.offsets)for(let i=0;i<2;i++){
     const pos=offset+i-cursor;if(pos<0||pos>=value.length)continue;
     if(output===value)output=value.slice();output[pos]=language.charCodeAt(i);
    }
    cursor+=value.length;
   }
   controller.enqueue(output);return;}reader.releaseLock();reader=null;}
 }catch(e){controller.error(e);}},async cancel(){if(reader)await reader.cancel();}});
 return new Response(stream,{headers});
}
async function releases(r,env,u){
 const b=env.BUCKET,p=u.pathname;
 if(p.startsWith('/internal/release/')){
  const token=r.headers.get('authorization');
  if(!env.LUCID_RELEASE_KEY||!token||await hash(token)!==await hash('Bearer '+env.LUCID_RELEASE_KEY))return deny(403);
  const key=p.slice('/internal/release/'.length);
  if(key.startsWith('source/'))return sourceRelease(r,b,key);
  if(/^[0-9a-f]{64}$/.test(key)){
   if(r.method==='HEAD'){const x=await b.head('chunk/'+key);return new Response(null,{status:x?200:404,headers:x?{'Content-Length':String(x.size)}:{}});}
   if(r.method!=='PUT'||Number(r.headers.get('content-length'))>8388608)return deny(400);
   const bytes=await r.arrayBuffer();if(bytes.byteLength>8388608||await hash(bytes)!==key)return deny(422);
   await b.put('chunk/'+key,bytes);return json({sha256:key,bytes:bytes.byteLength});
  }
  if(key!=='publish'||r.method!=='POST')return deny(404);
  const f=await r.json();if(!Array.isArray(f.parts)||!f.parts.length||f.parts.length>750||!/^[a-zA-Z0-9._-]+$/.test(f.name)||!/^[a-f0-9]{64}$/.test(f.sha256)||!Number.isSafeInteger(f.bytes))return deny(400);
  const id=f.id;
  if(!byGame(id)&&!['windows-x64','linux-x64','macos-x64','macos-arm64','android','ios','source'].includes(id)&&!/^(android|ios)-(ko|en|es|ja|zh|de|fr)$/.test(id))return deny(400);
  if(byGame(id)&&(byGame(id).version!==f.version||byGame(id).sha256!==f.sha256||byGame(id).bytes!==f.bytes))return deny(409);
  let size=0;for(const part of f.parts){if(!/^[a-f0-9]{64}$/.test(part.sha256))return deny(400);const x=await b.head('chunk/'+part.sha256);if(!x||x.size!==part.bytes)return deny(409);size+=x.size;}if(size!==f.bytes)return deny(422);
  await set(b,'release/'+id+'/'+f.version,f);await set(b,'current/'+id,{version:f.version,bytes:f.bytes,sha256:f.sha256,name:f.name});return json({ok:true,id,bytes:size});
 }
 if(p==='/api/launcher/modules')return json({schema:1,games:CATALOG});
 if(p==='/download/source' && ['GET','HEAD'].includes(r.method))return Response.redirect('https://github.com/WingedhussarYG/Hyeonjin-Jeong/tree/main/lucid-games',302);
 if(p==='/api/launcher/installers'){const ids=['windows-x64','macos-arm64','macos-x64','linux-x64','android','ios'];const data=await Promise.all(ids.map(async id=>[id,await metadata(b,'current/'+id)]));return json(Object.fromEntries(data.filter(x=>x[1])));}
 let m=/^\/api\/launcher\/modules\/([\w-]+)\/([\w.-]+)$/.exec(p);
 if(m){const g=byGame(m[1]);if(!g||g.version!==m[2]||r.headers.get('x-lucid-install')!=='1'||desk(g.id)&&mobile(r))return deny(403);return fileResponse(r,b,await metadata(b,'release/'+g.id+'/'+g.version));}
 m=/^\/download\/(windows-x64|macos-arm64|macos-x64|linux-x64|android|ios)$/.exec(p);
 if(m){
  const id=m[1],language=u.searchParams.get('lang'),current=await metadata(b,'current/'+id);
  if(current && (id==='android'||id==='ios') && /^(ko|en|es|ja|zh|de|fr)$/.test(language)){
   const localized=await metadata(b,'release/'+id+'-'+language+'/'+current.version);
   if(localized)return fileResponse(r,b,localized,null,language);
  }
  return fileResponse(r,b,current&&await metadata(b,'release/'+id+'/'+current.version),language);
 }
 return null;
}
export default {async fetch(r,env,ctx){try{const u=new URL(r.url);const dv=await devicePair(r,env,u);if(dv)return dv;const archive=await accountSave(r,env,u,ctx);if(archive)return archive;const a=await auth(r,env,u);if(a)return a;const f=await releases(r,env,u);if(f)return f;
 const asset=ASSETS[u.pathname];if(!asset||!['GET','HEAD'].includes(r.method))return deny(404);
 return new Response(r.method==='HEAD'?null:Uint8Array.from(atob(asset[1]),c=>c.charCodeAt(0)),{headers:{'Content-Type':asset[0],'Cache-Control':'no-cache','X-Content-Type-Options':'nosniff','Referrer-Policy':'strict-origin','Content-Security-Policy':"default-src 'self'; img-src 'self' data:; script-src 'self'; style-src 'self'; connect-src 'self'; frame-src "+CATALOG.map(g=>'https://'+g.id+'.maxfaine.chatgpt.site').join(' ')+"; form-action 'self' "+CATALOG.map(g=>'https://'+g.id+'.maxfaine.chatgpt.site').join(' ')+"; frame-ancestors 'none'; base-uri 'none'"}});
 }catch(e){console.error('Launcher request',new URL(r.url).pathname,e.name);return deny(500);}}};
