/* Shared UI locale for the browser and the isolated Electron renderer origins. */
(() => {
  'use strict';
  if (window.LucidLocale) return;
  const languages = {'ko':'한국어','en-GB':'English (UK)','de':'Deutsch','fr':'Français','es':'Español','ja':'日本語','zh-CN':'简体中文'};
  const key = 'lucid.studio.interface-language';
  const assetBase = new URL('.', document.currentScript.src);
  const native = window.lucidLanguage;
  const clean = value => String(value ?? '').replace(/\s+/gu,' ').trim();
  const normalise = value => Object.keys(languages).find(id => id.toLowerCase().split('-')[0] === String(value || '').toLowerCase().split(/[-_]/)[0]);
  function saved() { try { return localStorage.getItem(key); } catch { return null; } }
  let locale = normalise(saved()) || (navigator.languages || [navigator.language]).map(normalise).find(Boolean) || 'en-GB';
  let table = Object.create(null), patterns = new Map(), revision = 0;
  const textOrigins = new WeakMap(), attributeOrigins = new WeakMap();
  const excluded = 'script,style,textarea,pre,code,svg,canvas,[contenteditable]:not([contenteditable="false"]),[translate="no"],[data-user-content],#document-name,[data-item] .meta,[data-folder] .name,.document-title,#project-name,.layer-list .name,.layers-panel .name,.library-item-name,.document-heading #document-name,.item .meta b,.filename,.model-prompt,[data-ref],.compat-slide p,.slide-thumbnail p,.compat-note-body,.job-prompt,.layer-name,[data-library-name],.filename,.file-name,.layer-name,.page-text,.pdf-text-layer,.textLayer,.monaco-editor,[role="textbox"],[role="gridcell"]';
  const attrs = ['title','placeholder','aria-label','aria-description','alt','data-tooltip','value'];
  const names = new Map();
  function matchParts(s,parts) {
    if(!s.startsWith(parts[0]) || !s.endsWith(parts.at(-1)))return null;
    let pos=parts[0].length;const values=[];
    for(let i=1;i<parts.length;i++){
      const next=i===parts.length-1?s.length-parts[i].length:s.indexOf(parts[i],pos);
      if(next<pos)return null;
      values.push(s.slice(pos,next));pos=next+parts[i].length;
    }
    return values;
  }
  function install(messages) {
    table = messages; patterns = new Map();
    for (const [from,to] of Object.entries(messages)) {
      if(!from.includes('⟦v⟧') || from === '⟦v⟧') continue;
      const parts=from.split('⟦v⟧');
      if(parts.join('').length<4 || parts.length>9 || parts.some((p,i)=>!p && i>0 && i<parts.length-1)) continue;
      const bucket=parts[0].slice(0,1);
      const list=patterns.get(bucket) || [];
      list.push([parts,to,parts.join('').length]);
      patterns.set(bucket,list);
    }
    for (const list of patterns.values()) list.sort((a,b)=>b[2]-a[2]);
  }
  function translate(value) {
    if(typeof value !== 'string' || value.length>4000) return value;
    const s=clean(value); let result=Object.hasOwn(table,s)?table[s]:undefined;
    if(result===undefined && s && s.length<1200) {
      for(const k of [s[0],'']) {
        for(const [parts,format] of patterns.get(k)||[]) {
          const match=matchParts(s,parts);
          if(match){let i=0;result=format.replace(/⟦v⟧/g,()=>match[i++]??'');break;}
        }
        if(result!==undefined)break;
      }
    }
    return result===undefined || result===s ? value : value.replace(/^(\s*)[\s\S]*?(\s*)$/u,(_,a,b)=>a+result+b);
  }
  function attributes(el) {
    if(el.closest('[translate="no"],[data-user-content]'))return;
    if(el.matches(excluded) && !el.matches('textarea,input,[role="textbox"],[contenteditable="true"]'))return;
    const mem=attributeOrigins.get(el)||{};
    for(const a of attrs) {
      if(!el.hasAttribute(a))continue;
      if(a==='value' && !el.matches('input[type="submit"],input[type="button"],input[type="reset"]'))continue;
      const v=el.getAttribute(a),old=mem[a],source=old && old.output===v?old.source:v;
      const output=translate(source);
      if(output!==v)el.setAttribute(a,output);
      mem[a]={source,output};
    }
    attributeOrigins.set(el,mem);
  }
  function nodeText(node) {
    const el=node.parentElement;
    if(!el || el.closest(excluded))return;
    const v=node.data,old=textOrigins.get(node),source=old && old.output===v?old.source:v;
    if(!source.trim())return;
    const output=translate(source);
    if(output!==v){
      if(el.tagName==='OPTION'&&!el.hasAttribute('value'))el.value=el.textContent;
      node.data=output;
    }
    textOrigins.set(node,{source,output});
  }
  function scan(root) {
    if(root.nodeType===Node.TEXT_NODE){nodeText(root);return;}
    if(root.nodeType!==Node.ELEMENT_NODE && root.nodeType!==Node.DOCUMENT_NODE)return;
    if(root.nodeType===1){attributes(root);if(root.matches(excluded))return;}
    const walker=document.createTreeWalker(root,NodeFilter.SHOW_ELEMENT|NodeFilter.SHOW_TEXT,{
      acceptNode:n=>{if(n.nodeType===1 && n.matches(excluded)){attributes(n);return NodeFilter.FILTER_REJECT;}return NodeFilter.FILTER_ACCEPT;}
    });
    while(walker.nextNode()) {
      const n=walker.currentNode;
      if(n.nodeType===3)nodeText(n);else attributes(n);
    }
  }
  const watch=new MutationObserver(records=>{
    for(const r of records){
      if(r.type==='childList')r.addedNodes.forEach(scan);
      else if(r.type==='attributes')attributes(r.target);
      else nodeText(r.target);
    }
    if(document.readyState!=='loading' && self===top && !document.getElementById('lucid-language-select')) control();
  });
  async function setLocale(value,persist=false){
    const id=normalise(value);
    if(!id)return;
    const rev=++revision;
    if(!names.has(id))names.set(id,fetch(new URL('strings-'+id.toLowerCase()+'.json',assetBase)).then(r=>{if(!r.ok)throw Error('Locale '+r.status);return r.json()}).catch(e=>{names.delete(id);throw e;}));
    const data=await names.get(id);
    if(rev!==revision)return;
    locale=id;install(data);document.documentElement.lang=id;
    if(persist || native){try{localStorage.setItem(key,id)}catch{};if(persist && native)await native.set(id);}
    const selector=document.getElementById('lucid-language-select');if(selector)selector.value=id;
    scan(document);
    document.dispatchEvent(new CustomEvent('lucid-language-change',{detail:id}));
  }
  function control(){
    if(self!==top || document.getElementById('lucid-language-select') || !document.body)return;
    const holder=document.createElement('label');holder.setAttribute('translate','no');holder.className='lucid-language-control';
    const label=document.createElement('span');label.textContent='Language';
    const select=document.createElement('select');select.id='lucid-language-select';select.setAttribute('aria-label','Language');
    for(const [value,name] of Object.entries(languages)){const opt=new Option(name,value);select.add(opt);}
    select.value=locale;select.addEventListener('change',()=>setLocale(select.value,true).catch(console.error));
    holder.append(label,select);
    const bar=document.querySelector('.tab-tools,.topbar nav,.topbar,.app-header,.app-topbar,.menubar,header nav,header');
    if(bar)bar.append(holder);else {holder.classList.add('lucid-language-floating');document.body.append(holder);}
    const labels={ko:'언어','en-GB':'Language',de:'Sprache',fr:'Langue',es:'Idioma',ja:'言語','zh-CN':'语言'};
    const changed=()=>{label.textContent=labels[locale];select.setAttribute('aria-label',labels[locale]);select.value=locale;};
    document.addEventListener('lucid-language-change',changed);changed();
  }
  window.LucidLocale={get current(){return locale},languages,set:setLocale,t:translate};
  for(const name of ['alert','confirm','prompt']){
    const original=window[name].bind(window);window[name]=(message,...args)=>original(translate(message),...args);
  }
  const ready=(async()=>{
    if(native)locale=normalise(await native.get())||locale;
    else if(self!==top){try{await parent.LucidLocale?.ready;locale=normalise(parent.LucidLocale?.current)||locale;parent.document.addEventListener('lucid-language-change',e=>setLocale(e.detail).catch(console.error));}catch{}}
    await setLocale(locale);
    watch.observe(document.documentElement,{subtree:true,childList:true,characterData:true,attributes:true,attributeFilter:attrs});
    if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',control,{once:true});else control();
  })();
  window.LucidLocale.ready=ready;
  addEventListener('storage',e=>{if(e.key===key&&normalise(e.newValue))setLocale(e.newValue).catch(console.error)});
  native?.onChange(id=>{if(id!==locale)setLocale(id).catch(console.error)});
})();
