'use strict';
let DB = [], OCC = [], UNLINKED = [], tab = 'donors', flt = '', q = '', plaque = null, GLAST = 6, pyMonth = null, pyDay = null, HEBYEAR = '', donSort = 'last';
function curSym(d){ return (d && d.region==='il') ? '₪' : '$'; }
const GMON=['','ינואר','פברואר','מרץ','אפריל','מאי','יוני','יולי','אוגוסט','ספטמבר','אוקטובר','נובמבר','דצמבר'];
const GREGYEAR=String(new Date().getFullYear());
// תצוגת חודש לועזי לפי תאריך ("2026-07" → "יולי 2026") — התרומות הקבועות נגבות לפי חודש לועזי
function gregLabel(dateStr){if(!dateStr)return '';const m=String(dateStr).match(/^(\d{4})-(\d{1,2})/);if(!m)return String(dateStr);return GMON[+m[2]]+' '+m[1];}
function donorTotals(d){
  let all=0,year=0;
  (d.donations||[]).forEach(x=>{const a=amtNum(x.amount);all+=a;if((x.date||'').slice(0,4)===GREGYEAR)year+=a;});
  (d.parnes||[]).forEach(x=>{const a=amtNum(x.amount);all+=a;});
  return {all,year};
}
// חישוב יששכר־זבולון: התחייבות חודשית (סך האברכים) מול מה ששולם בפועל בחודשים שכבר שילם = החוב
function izSummary(d){
  const parts=(d.partners||[]).filter(p=>p.active!=0);
  const monthly=parts.reduce((s,p)=>s+amtNum(p.amount),0);
  const izdon=(d.donations||[]).filter(x=>/יששכר|זבולון/.test(x.category||''));
  const paid=izdon.reduce((s,x)=>s+amtNum(x.amount),0);
  const codes=izdon.map(x=>{const m=(x.date||'').match(/^(\d{4})-(\d{2})/);return m?(+m[1])*12+(+m[2]):null;}).filter(v=>v!=null);
  const hasPay=codes.length>0;
  const span=hasPay?(Math.max(...codes)-Math.min(...codes)+1):0;
  const expected=monthly*span;
  const debt=expected-paid;
  return {parts,monthly,paid,span,expected,debt,hasPay};
}
function izSummaryHTML(d){
  const act=(d.partners||[]).filter(p=>p.active!=0);
  if(d.tier!=='יששכר_זבולון'&&!act.length)return '';
  const s=izSummary(d),cur=curSym(d);
  const rows=s.parts.map(p=>`<div class="izrow"><span>👨‍🎓 ${esc(p.avreich||'—')}${p.method?(' <small>'+chBadgeRaw(p.method)+'</small>'):''}</span><b>${cur}${amtNum(p.amount)}</b></div>`).join('')||'<div class="hintxt">לא הוזנו אברכים</div>';
  let debtLine;
  if(!s.hasPay) debtLine='<div class="hintxt">אין עדיין תשלומי יש"ז רשומים לחישוב חוב</div>';
  else if(s.debt>0.5) debtLine=`<div class="izdebt owe">🔴 חוב מוערך: ${cur}${Math.round(s.debt)}</div>`;
  else if(s.debt<-0.5) debtLine=`<div class="izdebt ok">🟢 מקדמה / עודף: ${cur}${Math.round(-s.debt)}</div>`;
  else debtLine=`<div class="izdebt ok">🟢 מעודכן — אין חוב</div>`;
  return `<div class="izsum"><div class="izsum-t">🤝 יששכר־זבולון — סיכום</div>
    ${rows}
    <div class="izrow tot"><span>התחייבות חודשית</span><b>${cur}${s.monthly}</b></div>
    ${s.hasPay?`<div class="izrow"><span>שולם ב-2026 (${s.span} ${s.span===1?'חודש':'חודשים'})</span><b>${cur}${s.paid}</b></div>
    <div class="izrow"><span>צפוי לתקופה (${s.span}×${cur}${s.monthly})</span><b>${cur}${s.expected}</b></div>`:''}
    ${debtLine}
    ${d.iz_note?`<div class="iznote">📝 ${esc(d.iz_note)}</div>`:''}</div>`;
}
const HMORD = ['תשרי','חשון','כסלו','טבת','שבט','אדר','ניסן','אייר','סיון','תמוז','אב','אלול'];
function heDay(n){const ones=['','א','ב','ג','ד','ה','ו','ז','ח','ט'],tens=['','י','כ','ל'];let s;if(n===15)s='טו';else if(n===16)s='טז';else s=(tens[Math.floor(n/10)]||'')+(ones[n%10]||'');return s.length<=1?s+"'":s.slice(0,-1)+'"'+s.slice(-1);}
const view = document.getElementById('view'), chips = document.getElementById('chips'),
      ov = document.getElementById('ov'), sheet = document.getElementById('sheet'),
      toastEl = document.getElementById('toast');
const TIERS = {'יששכר_זבולון':['יששכר־זבולון','ishz'],'קוויטל_101':['כל לילה','k101'],'קוויטל_כללי':['כללי','klali']};
const CATS = ['', 'קבוע', 'מזדמן', 'פרנס יום', 'בניין/הקדשה', 'מזדמן/חד-פעמי'];
const MON = ['ינ','פב','מר','אפ','מא','יו','יול','אג','ספ','אק','נו','דצ'];
const KIND = {charge:'💳 לחייב',parnes:'🌙 פרנס יום',prayer:'🙏 להתפלל',followup:'📞 לחזור',other:'🔔 תזכורת'};
function todayStr(){return new Date().toISOString().slice(0,10);}
function addDay(ymd8){const y=+ymd8.slice(0,4),m=+ymd8.slice(4,6)-1,d=+ymd8.slice(6,8);return new Date(Date.UTC(y,m,d+1)).toISOString().slice(0,10).replace(/-/g,'');}
function gcalLink(t,donor){const d=(t.due_date||'').replace(/-/g,'');if(d.length!==8)return '';const title=encodeURIComponent((KIND[t.kind]||'תזכורת')+' — '+donor+(t.note?': '+t.note:''));return `https://calendar.google.com/calendar/render?action=TEMPLATE&text=${title}&dates=${d}/${addDay(d)}`;}
function dueTasks(){const td=todayStr(),out=[];DB.forEach(d=>(d.tasks||[]).forEach(t=>{if((!t.done||t.done==0)&&t.due_date&&t.due_date<=td)out.push({...t,donor:(d.last+' '+d.first).trim(),dref:d});}));return out.sort((a,b)=>(a.due_date||'').localeCompare(b.due_date||''));}
function checkReminders(){
  const due=dueTasks(),ban=document.getElementById('rembanner');
  if(!due.length){ban.classList.remove('show');ban.textContent='';return;}
  ban.textContent=`🔔 ${due.length} תזכורות ממתינות — לחץ לטיפול`;ban.classList.add('show');
  ban.onclick=()=>openRemPopup();
  if(!sessionStorage.getItem('remseen')){openRemPopup();sessionStorage.setItem('remseen','1');}
}
function openRemPopup(){
  const due=dueTasks(),remov=document.getElementById('remov'),rs=document.getElementById('remsheet');
  if(!due.length){remov.classList.remove('show');return;}
  rs.innerHTML=`<button class="x" id="rx">✕</button><h2>🔔 תזכורות שהגיע זמנן (${due.length})</h2>
    <div class="hintxt">סמן בוצע, או דחה למחר.</div>
    ${due.map((t,i)=>`<div class="remitem over"><div class="ri"><b>${KIND[t.kind]||'🔔'} ${esc(t.donor)}</b><br><small>${esc(t.due_date)} ${esc(t.note||'')}</small></div>
      <button class="btn sm rdone" data-i="${i}">בוצע ✓</button><button class="no rsnooze" data-i="${i}">דחה מחר</button></div>`).join('')}`;
  remov.classList.add('show');
  document.getElementById('rx').onclick=()=>remov.classList.remove('show');
  rs.querySelectorAll('.rdone').forEach(b=>b.onclick=async()=>{const t=due[b.dataset.i];if(t.id)await api('PUT','/api/task/'+t.id,{done:1});const lt=(t.dref.tasks||[]).find(x=>x.id===t.id);if(lt)lt.done=1;checkReminders();openRemPopup();render();toast('בוצע ✓');});
  rs.querySelectorAll('.rsnooze').forEach(b=>b.onclick=async()=>{const t=due[b.dataset.i],nd=addDay(todayStr().replace(/-/g,'')),nds=nd.slice(0,4)+'-'+nd.slice(4,6)+'-'+nd.slice(6,8);if(t.id)await api('PUT','/api/task/'+t.id,{due_date:nds});const lt=(t.dref.tasks||[]).find(x=>x.id===t.id);if(lt)lt.due_date=nds;checkReminders();openRemPopup();render();toast('נדחה למחר');});
}

function esc(s){return (s==null?'':String(s)).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));}
function norm(s){return (s||'').replace(/["'`]/g,'').replace(/\s+/g,' ').trim();}
function dupKey(d){return norm((d.last||'')+' '+(d.first||'')).replace(/[-־]/g,'');}
function findDupes(){const g={};DB.forEach(d=>{const k=dupKey(d);if(!k)return;(g[k]=g[k]||[]).push(d);});return Object.values(g).filter(a=>a.length>1);}
// פרנס "פתוח" = הלילה עדיין לא עבר, או שעבר אך טרם שולם. הירח נעלם רק כשהלילה עבר וגם שולם.
function hasOpenParnes(d){const t=todayStr();return (d.parnes||[]).some(p=>!(p.night_date&&p.night_date<t&&+p.paid));}
function toast(t){toastEl.textContent=t;toastEl.classList.add('show');setTimeout(()=>toastEl.classList.remove('show'),1300);}
function pill(t){if(!TIERS[t])return '';const[l,c]=TIERS[t];return `<span class="pill ${c}">${l}</span>`;}
function catPill(c){if(c==='קבוע')return '<span class="pill reg">קבוע</span>';if(c==='מזדמן')return '<span class="pill occ">מזדמן</span>';return '';}
// ערוצי חיוב — תג צבעוני מובחן לכל ערוץ (בצבעי המותג)
const CHANNELS={
  'בנק_ווסט':{i:'🏦',l:'בנק ווסט',c:'#0b6e61'},
  'אותורייז':{i:'💳',l:'Authorize',c:'#1a5fb4'},
  'צק':{i:'🧾',l:"צ'ק",c:'#8a6d00'},
  'Zelle':{i:'Ⓩ',l:'Zelle',c:'#6d1ed4'},
  'העברה_בנקאית':{i:'🏦',l:'העברה בנקאית',c:'#4a5568'},
  'דונורס_פאנד':{i:'💼',l:'Donors Fund',c:'#9a4a12'},
  'נדרים':{i:'📱',l:'נדרים',c:'#c2410c'},
  'OJC':{i:'🏛️',l:'OJC',c:'#3b4252'},
  'Pledger':{i:'📲',l:'Pledger',c:'#3b4252'},
};
const CHAN_ORDER=['בנק_ווסט','אותורייז','צק','Zelle','העברה_בנקאית','דונורס_פאנד','נדרים','OJC','Pledger'];
function chBadgeRaw(ch){const cfg=CHANNELS[(ch||'').trim()];if(!cfg)return '';return `<span class="chbadge" style="background:${cfg.c}" title="${esc(cfg.l)}">${cfg.i} ${esc(cfg.l)}</span>`;}
function chLabel(ch){const cfg=CHANNELS[(ch||'').trim()];return cfg?cfg.l:(ch||'');}
function channelBadge(d){return chBadgeRaw(d.channel);}
function channelOpts(cur){cur=(cur||'').trim();let o='<option value="">— ללא —</option>';CHAN_ORDER.forEach(k=>{o+=`<option value="${k}" ${k===cur?'selected':''}>${CHANNELS[k].i} ${CHANNELS[k].l}</option>`;});if(cur&&!CHANNELS[cur])o+=`<option value="${esc(cur)}" selected>${esc(cur)}</option>`;return o;}
// הסכום הקבוע (חודשי) — לתורם קבוע לפי השדה, וליששכר־זבולון סכום האברכים הפעילים
function fixedAmt(d){
  if(d.tier==='יששכר_זבולון'){const s=(d.partners||[]).filter(p=>p.active!=0).reduce((a,p)=>a+amtNum(p.amount),0);if(s)return curSym(d)+s;}
  if(d.category==='קבוע'&&amtNum(d.amount))return curSym(d)+amtNum(d.amount);
  return '';}
function matchQ(s){return !q?true:norm(s).includes(norm(q));}

async function api(m,u,b){const r=await fetch(u,{method:m,headers:{'Content-Type':'application/json'},body:b?JSON.stringify(b):undefined});return r.json();}
function fileChip(f){const ic=(f.mime||'').indexOf('pdf')>=0?'📄':((f.mime||'').indexOf('image')>=0?'🖼️':'📎');return `<span class="fchip"><a href="/api/file/${f.id}" target="_blank" rel="noopener">${ic} ${esc(f.name||'קובץ')}</a><button class="fdel" data-fid="${f.id}">🗑</button></span>`;}
function uploadFile(kind,refId,inputEl,cb){const f=inputEl.files[0];if(!f)return;if(f.size>15*1024*1024){toast('קובץ גדול מדי (מקס 15MB)');return;}toast('מעלה…');const rd=new FileReader();rd.onload=async()=>{const data=rd.result.split(',')[1];await api('POST','/api/file',{kind,ref_id:refId,name:f.name,mime:f.type,data});toast('הועלה ✓');cb&&cb();};rd.readAsDataURL(f);}
async function load(){
  const d = await api('GET','/api/data');
  DB = d.donors; UNLINKED = d.unlinked_prayers || []; HEBYEAR = d.heb_year || '';
  GLAST = (function(){const c=[...Array(12)].map((_,i)=>DB.filter(x=>x.months&&x.months[i]==='p').length);const mx=Math.max(1,...c);let l=0;for(let i=0;i<12;i++)if(c[i]>=0.3*mx)l=i;return l;})();
  document.getElementById('stat').textContent = DB.length + ' תורמים';
  render();
  checkReminders();
  // פתיחת כרטיס לפי פרמטר בכתובת (קישור מדף ההתאמה) — פעם אחת
  try{const pd=new URLSearchParams(location.search).get('donor');if(pd){const dd=DB.find(x=>x.id==+pd);if(dd){openDonor(dd);}history.replaceState(null,'',location.pathname);}}catch(e){}
}

document.querySelectorAll('.tab').forEach(b=>b.onclick=()=>{tab=b.dataset.tab;document.querySelectorAll('.tab').forEach(x=>x.classList.toggle('on',x===b));flt='';plaque=null;pyMonth=null;pyDay=null;pyKind='parnes';kvSub=null;render();});
document.getElementById('q').oninput=e=>{q=e.target.value.trim();render();};
ov.onclick=e=>{if(e.target===ov)ov.classList.remove('show');};
document.getElementById('remov').onclick=e=>{if(e.target.id==='remov')e.currentTarget.classList.remove('show');};

function render(){
  chips.innerHTML='';
  if(tab==='donors') return flt==='addrfix'?renderAddrFix():renderDonors();
  if(tab==='tasks') return renderTasksTab();
  if(tab==='kvittel') return renderKvittel();
  if(tab==='parnes') return renderParnes();
  if(tab==='charges') return renderCharges();
  if(tab==='avreich') return renderAvreich();
  if(tab==='missed') return renderMissed();
  if(tab==='camp') return renderCamp();
}

/* ---------- תורמים ---------- */
function amtNum(a){const n=parseFloat(String(a||'').replace(/[^0-9.]/g,''));return isNaN(n)?0:n;}
const DFILTERS={
  'iz':{label:'יששכר־זבולון', fn:d=>d.tier==='יששכר_זבולון'},
  'k101':{label:'כל לילה', fn:d=>d.tier==='קוויטל_101'},
  'reg':{label:'💵 קבוע', fn:d=>d.category==='קבוע'},
  'reglow':{label:'שבועי', fn:d=>d.category==='קבוע' && amtNum(d.amount)>0 && amtNum(d.amount)<101},
  'occ':{label:'מזדמנים', fn:d=>d.category==='מזדמן' && !d.tier},
  'klali':{label:'כללי', fn:d=>d.tier==='קוויטל_כללי'},
  'il':{label:'🇮🇱 ארץ ישראל', fn:d=>d.region==='il'},
  'building':{label:'🏛️ בניין', fn:d=>(d.building||[]).length>0},
  'new':{label:'🆕 נוספו', fn:d=>!!d.created},
  '':{label:'הכל', fn:d=>true}
};
const DFORDER=['il','iz','k101','reg','reglow','occ','klali','building','new',''];
function renderDonors(){
  chips.innerHTML=DFORDER.map(k=>{const cnt=DB.filter(DFILTERS[k].fn).length;return `<button class="chip ${flt===k?'on':''}" data-k="${k}">${DFILTERS[k].label} <b>${cnt}</b></button>`;}).join('');
  chips.querySelectorAll('.chip').forEach(c=>c.onclick=()=>{flt=c.dataset.k;render();});
  const ff=(DFILTERS[flt]||DFILTERS['']).fn;
  let list=DB.filter(d=>ff(d)&&matchQ(d.last+' '+d.first+' '+d.phone+' '+d.business+' '+d.english+' '+(d.building||[]).map(x=>x.object).join(' ')));
  if(donSort==='new'||flt==='new') list=list.slice().sort((a,b)=>String(b.created||'').localeCompare(String(a.created||'')));
  else if(donSort==='amt') list=list.slice().sort((a,b)=>donorTotals(b).all-donorTotals(a).all);
  else list=list.slice().sort((a,b)=>(a.last||'').localeCompare(b.last||'','he'));
  const ndup=findDupes().length;
  const nafix=DB.filter(addrIssue).length;
  view.innerHTML=`<button class="btn addbig" id="newDonorBtn">➕ הוסף תורם חדש</button>
    ${ndup?`<button class="btn dupbtn" id="dupBtn">🔀 מיזוג כרטיסים כפולים (${ndup})</button>`:''}
    ${nafix?`<button class="btn kvmissbtn" id="addrFixBtn">🔴 כתובות לתיקון — ${nafix}</button>`:''}
    <div class="avbar"><select id="donsort" class="avsortsel">
      <option value="last">מיון: שם (א-ב)</option>
      <option value="amt">מיון: סכום תרומות (גבוה→נמוך)</option>
      <option value="new">מיון: נוספו לאחרונה</option>
    </select></div>
    <div class="cnt">${list.length} תורמים</div><div class="list">${list.map(d=>`
    <div class="rowc" data-id="${d.id}">
      <div><div class="nm">${esc(d.last)} <small>${esc(d.first)}</small><span class="rownum">#${d.id}</span>${fixedAmt(d)?`<span class="fixamt">💵 ${esc(fixedAmt(d))} קבוע</span>`:''}</div>
      ${d.english?`<div class="en" dir="ltr">${esc(d.english)}</div>`:''}
      ${d.purpose?`<div class="purp">🎯 ${esc(d.purpose)}</div>`:''}
      ${d.created?`<div class="newp">🆕 נוסף ${esc(d.created)}${d.source?(' · '+esc(d.source)):''}</div>`:''}</div>
      <div class="meta">${hasOpenParnes(d)?'<span class="pill py">🌙</span>':''}${channelBadge(d)}${catPill(d.category)}${pill(d.tier)}${d.phone?`<span class="ph">${esc(d.phone)}</span>`:''}</div>
    </div>`).join('')||'<div class="empty">אין תוצאות</div>'}</div>`;
  const ds=document.getElementById('donsort'); if(ds){ds.value=donSort;ds.onchange=()=>{donSort=ds.value;render();};}
  const db2=document.getElementById('dupBtn'); if(db2)db2.onclick=openDupes;
  const afb=document.getElementById('addrFixBtn'); if(afb)afb.onclick=()=>{flt='addrfix';render();};
  view.querySelectorAll('.rowc').forEach(r=>r.onclick=()=>openDonor(DB.find(x=>x.id==r.dataset.id)));
  document.getElementById('newDonorBtn').onclick=openNewDonor;
}
// זיהוי כתובת בעייתית (מילים דבוקות / מספר דבוק / מדינה כפולה / כתובת ישראלית שמתחילה במספר)
function addrIssue(d){
  const a=(d.addr||'').trim(); if(!a||+d.addr_ok)return null;
  if(/[a-z][A-Z]/.test(a)||/\d[A-Z][a-z]/.test(a))return 'מילים דבוקות';
  if(/[\u0590-\u05FF]\d/.test(a))return 'מספר דבוק לרחוב';
  if(/\b([A-Z]{2}),\s*\1\b/.test(a))return 'מדינה כפולה';
  const street=(a.split(',')[0]||'');
  if(d.region==='il'&&/^\s*[\d]/.test(a))return 'מתחיל במספר (אולי הפוך)';
  if(d.region==='il'&&/\d[ ]*[\u0590-\u05FF]/.test(street))return 'מספר לפני שם הרחוב — לבדוק';
  return null;
}
function renderAddrFix(){
  chips.innerHTML='';
  let list=DB.filter(d=>addrIssue(d)).filter(d=>matchQ(d.last+' '+d.first+' '+d.addr));
  list.sort((a,b)=>(a.last||'').localeCompare(b.last||'','he'));
  view.innerHTML=`<button class="back" id="afback">→ חזרה לתורמים</button>
    <div class="cnt">🔴 כתובות לתיקון: ${list.length}</div>
    <div class="hintxt">ערוך את הכתובת ולחץ 💾 שמור, או ✓ תקין אם הכתובת בסדר כמו שהיא (תוסר מהרשימה).</div>
    <div class="list">${list.map(d=>`<div class="afrow" data-id="${d.id}">
      <div class="afname"><b class="avnamelink" data-id="${d.id}">${esc((d.last+' '+d.first).trim())}</b> <span class="rownum">#${d.id}</span> <span class="kvtag">${esc(addrIssue(d))}</span></div>
      <input class="afaddr" data-id="${d.id}" value="${esc(d.addr||'')}" dir="${d.region==='il'?'rtl':'ltr'}">
      <div class="afact"><button class="btn sm afsave" data-id="${d.id}">💾 שמור</button><button class="kvskip afok" data-id="${d.id}">✓ תקין</button></div>
    </div>`).join('')||'<div class="empty">🎉 אין כתובות לתיקון</div>'}</div>`;
  document.getElementById('afback').onclick=()=>{flt='';render();};
  view.querySelectorAll('.avnamelink').forEach(b=>b.onclick=()=>openDonor(DB.find(x=>x.id==b.dataset.id)));
  view.querySelectorAll('.afsave').forEach(b=>b.onclick=async()=>{const d=DB.find(x=>x.id==b.dataset.id);const inp=view.querySelector('.afaddr[data-id="'+b.dataset.id+'"]');d.addr=inp.value;await api('PUT','/api/donor/'+d.id,{addr:inp.value});toast('נשמר ✓');renderAddrFix();});
  view.querySelectorAll('.afok').forEach(b=>b.onclick=async()=>{const d=DB.find(x=>x.id==b.dataset.id);d.addr_ok=1;await api('PUT','/api/donor/'+d.id,{addr_ok:1});toast('סומן תקין ✓');renderAddrFix();});
}
function openDupes(){
  const paint=()=>{
    const gs=findDupes();
    const score=d=>((d.donations||[]).length*3+(d.partners||[]).length*3+(d.parnes||[]).length*2+(d.phone?1:0)+(d.email?1:0)+(amtNum(d.amount)?1:0)+(d.category?1:0)+(d.english?1:0));
    sheet.innerHTML=`<button class="x" id="cx">✕</button>
      <h2>🔀 מיזוג כרטיסים כפולים</h2>
      <div class="hintxt">${gs.length?'בחר את הכרטיס להשאיר (מסומן אוטומטית המלא ביותר) — כל התרומות, הפרנס והאברכים יעברו אליו, והכפול יימחק.':'לא נמצאו כפולים 🎉'}</div>
      <div id="dupwrap">${gs.map((grp,gi)=>{const best=grp.slice().sort((a,b)=>score(b)-score(a))[0];
        return `<div class="dupgrp"><div class="dupname">${esc(grp[0].last+' '+grp[0].first)}</div>${grp.map(d=>{
          const nd=(d.donations||[]).length,np=(d.partners||[]).length,npar=(d.parnes||[]).length;
          return `<label class="dupcard"><input type="radio" name="keep${gi}" value="${d.id}" ${d.id===best.id?'checked':''}>
            <div class="dupinfo"><b>כרטיס #${d.id}</b> ${catPill(d.category)} ${pill(d.tier)}${d.id===best.id?' <span class="dupkeep">מומלץ להשאיר</span>':''}
            <div class="dupmeta">${d.phone?('📞 '+esc(d.phone)+' '):''}${d.email?('✉️ '+esc(d.email)+' '):''}${amtNum(d.amount)?('💵 '+esc(d.amount)+' '):''}${d.english?('· '+esc(d.english)):''}</div>
            <div class="dupmeta">${nd} תרומות · ${npar} פרנס · ${np} אברכים</div></div></label>`;
        }).join('')}<button class="btn sm dupmerge" data-gi="${gi}">מזג ✓</button></div>`;
      }).join('')||'<div class="empty">אין כפולים</div>'}</div>`;
    sheet.querySelectorAll('.dupmerge').forEach(b=>b.onclick=async()=>{
      const gi=b.dataset.gi,grp=findDupes()[gi];if(!grp)return;
      const sel=sheet.querySelector(`input[name="keep${gi}"]:checked`);if(!sel){toast('בחר כרטיס להשאיר');return;}
      const keep=+sel.value,drops=grp.filter(d=>d.id!==keep);
      for(const dr of drops){await api('POST','/api/merge',{keep,drop:dr.id});}
      toast('מוזג ✓');await load();paint();});
    document.getElementById('cx').onclick=()=>ov.classList.remove('show');
  };
  paint(); ov.classList.add('show');
}
function openNewDonor(onCreate){
  cardTab='details';
  sheet.innerHTML=`<button class="x" id="cx">✕</button>
    <h2>➕ תורם חדש</h2>
    <div class="two"><label class="fld"><span>שם משפחה *</span><input id="nd_last" placeholder="שם משפחה"></label>
      <label class="fld"><span>שם פרטי</span><input id="nd_first" placeholder="שם פרטי"></label></div>
    <label class="fld"><span>שם באנגלית</span><input id="nd_english" dir="ltr" placeholder="English name"></label>
    <label class="fld"><span>אזור / מטבע</span><select id="nd_region"><option value="">🇺🇸 חו"ל ($)</option><option value="il">🇮🇱 ארץ ישראל (₪)</option></select></label>
    <label class="fld"><span>טלפון</span><input id="nd_phone" dir="ltr" inputmode="tel" placeholder="+1 ..."></label>
    <label class="fld"><span>כתובת (רחוב ומספר)</span><input id="nd_addr" dir="auto" placeholder="רחוב ומספר"></label>
    <div class="two"><label class="fld"><span>עיר</span><input id="nd_city" dir="auto" placeholder="עיר"></label>
      <label class="fld"><span>מדינה</span><input id="nd_country" dir="auto" placeholder="מדינה"></label></div>
    <label class="fld"><span>מיקוד</span><input id="nd_zip" dir="ltr" placeholder="מיקוד"></label>
    <div class="sec"><h3 style="color:var(--gold);font-size:1rem">💵 תרומה ראשונה (לא חובה)</h3>
      <label class="fld"><span>תאריך קבלת התרומה (לועזי)</span><input id="nd_date" type="date"></label>
      <div id="nd_purposes"></div>
      <button class="btn sm ghost" type="button" id="nd_addpurp" style="margin-top:8px">➕ עוד מטרה (לאותה תרומה)</button>
      <div class="hintxt" style="font-size:.78rem">אפשר לרשום כמה מטרות לאותה תרומה — למשל פרנס קפה + ארוחת בוקר. רק בפרנס יום צריך לבחור יום; בתרומה רגילה מספיק התאריך הלועזי.</div></div>
    <div class="sec"><button class="btn" id="nd_save" style="width:100%">✔ צור כרטיס תורם</button></div>`;
  ov.classList.add('show');
  document.getElementById('cx').onclick=()=>ov.classList.remove('show');
  const g=id=>document.getElementById(id).value.trim();
  // בחירת ארץ ישראל → מילוי אוטומטי: מדינה, קידומת +972, פלייסהולדר מיקוד
  document.getElementById('nd_region').onchange=e=>{
    const ph=document.getElementById('nd_phone'), co=document.getElementById('nd_country'), zp=document.getElementById('nd_zip');
    if(e.target.value==='il'){
      if(!co.value.trim())co.value='ישראל';
      let v=ph.value.trim(); if(!v){ph.value='+972 ';} else if(v[0]==='0'){ph.value='+972 '+v.slice(1);}
      ph.placeholder='+972 ...'; zp.placeholder='מיקוד (7 ספרות)';
    }else{ ph.placeholder='+1 ...'; }
  };
  document.getElementById('nd_date').value=todayStr();  // ברירת מחדל: היום
  const purpBox=document.getElementById('nd_purposes');
  function wirePurp(row){
    const cat=row.querySelector('.p_cat');
    cat.onchange=()=>{const day=cat.options[cat.selectedIndex].dataset.day;
      row.querySelector('.p_daybox').style.display=day?'block':'none';
      row.querySelector('.p_free').style.display=(cat.value==='אחר'||cat.value==='קמפיין')?'block':'none';};
    const rm=row.querySelector('.rmpurp'); if(rm)rm.onclick=()=>row.remove();
  }
  function addPurp(first){purpBox.insertAdjacentHTML('beforeend',purpRowHTML(first));wirePurp(purpBox.lastElementChild);}
  addPurp(true);
  document.getElementById('nd_addpurp').onclick=()=>addPurp(false);
  document.getElementById('nd_last').focus();
  document.getElementById('nd_save').onclick=async()=>{
    const last=g('nd_last'); if(!last){toast('מלא שם משפחה');return;}
    const body={last,first:g('nd_first'),english:g('nd_english'),phone:g('nd_phone'),addr:g('nd_addr'),city:g('nd_city'),country:g('nd_country'),zip:g('nd_zip'),region:document.getElementById('nd_region').value};
    const r=await api('POST','/api/donor',body);
    const nd={id:r.id,...body,category:'',amount:'',prayers:[],parnes:[],donations:[],contacts:[],tasks:[],partners:[],transactions:[],pledges:[],files:[],created:todayStr(),source:'ידני'};
    DB.push(nd);
    const date=g('nd_date'); let anyDon=false;
    for(const row of purpBox.querySelectorAll('.purprow')){
      const amt=row.querySelector('.p_amt').value.trim();
      const cs=row.querySelector('.p_cat'); let cat=cs.value; if(cat==='אחר'||cat==='קמפיין')cat=row.querySelector('.p_catfree').value.trim()||cat;
      const dayKind=cs.options[cs.selectedIndex].dataset.day;
      if(dayKind){
        // יום פרנס — נוצר גם בלי סכום (יש שתרמו באופן אחר). הסכום נשאר ריק למילוי ידני
        const hm=row.querySelector('.p_hm').value,hd=+row.querySelector('.p_hd').value,hy=row.querySelector('.p_hy').value,dtext=heDay(hd)+" "+hm;
        const pr=await api('POST','/api/parnes',{donor_id:nd.id,day:hd,month:hm,date_text:dtext,dedication:'',amount:amt,kind:dayKind,hyear:hy});
        nd.parnes.push({id:pr.id,donor_id:nd.id,day:hd,month:hm,date_text:dtext,dedication:'',amount:amt,kind:dayKind,hyear:hy});
        anyDon=true;
      }else if(amt||cat){
        // תרומה רגילה — רק אם יש סכום או קטגוריה
        const dr=await api('POST','/api/donation',{donor_id:nd.id,amount:amt,category:cat,date});
        nd.donations.unshift({id:dr.id,donor_id:nd.id,amount:amt,category:cat,date,hmonth:dr.hmonth});
        anyDon=true;
      }
    }
    toast('נוצר כרטיס ✓');
    if(onCreate){ ov.classList.remove('show'); onCreate(nd); }
    else openDonor(nd, anyDon?'donations':'details');
  };
}
function heYearOpts(sel){sel=sel||HEBYEAR;let ys=['תשפ"ד','תשפ"ה','תשפ"ו','תשפ"ז','תשפ"ח','תשפ"ט','תש"צ'];if(sel&&!ys.includes(sel))ys.unshift(sel);return ys.map(y=>`<option ${y===sel?'selected':''}>${y}</option>`).join('');}
function purpRowHTML(first){
  return `<div class="purprow" style="border-top:1px solid var(--line);padding-top:8px;margin-top:8px;position:relative">
    ${first?'':'<button type="button" class="rmpurp" style="position:absolute;left:0;top:6px;background:none;border:none;color:var(--no);font-size:1.05rem;cursor:pointer">✕</button>'}
    <div class="two"><label class="fld"><span>סכום</span><input class="p_amt" placeholder="0"></label>
      <label class="fld"><span>עבור מה</span><select class="p_cat">
        <option value="">— בחר —</option><option>קבוע</option><option>יששכר־זבולון</option>
        <option value="פרנס לילה" data-day="parnes">🌙 פרנס לילה</option>
        <option value="חדר קפה" data-day="coffee">☕ פרנס קפה</option>
        <option value="ארוחת בוקר" data-day="breakfast">🍳 ארוחת בוקר</option>
        <option value="קמפיין">🎊 קמפיין</option><option>נר למאור</option><option>חד-פעמי</option><option>אחר</option></select></label></div>
    <div class="p_daybox" style="display:none"><div class="two"><label class="fld"><span>חודש עברי</span><select class="p_hm">${HMORD.map(m=>`<option>${m}</option>`).join('')}</select></label>
      <label class="fld"><span>יום</span><select class="p_hd">${[...Array(30)].map((_,i)=>`<option value="${i+1}">${heDay(i+1)}</option>`).join('')}</select></label></div>
      <label class="fld"><span>שנה עברית</span><select class="p_hy">${heYearOpts()}</select></label></div>
    <label class="fld p_free" style="display:none"><span>שם הקמפיין / הקטגוריה</span><input class="p_catfree" placeholder="למשל: קמפיין סוכות"></label>
  </div>`;
}

function gaps(m){if(!m)return [];const f=m.indexOf('p');if(f<0)return[];const g=[];for(let i=f;i<=GLAST;i++)if(m[i]!=='p')g.push(i);return g;}
function monthGrid(m){if(!m)return '';const f=m.indexOf('p');return `<div class="mgrid">${MON.map((l,i)=>{let c;if(m[i]==='p')c='gp';else if(f>=0&&i>=f&&i<=GLAST)c='gx';else c='gn';return `<div class="mc ${c}"><span>${l}</span></div>`;}).join('')}</div>`;}

let cardTab='details';
function tierOpts(cur){return ['','יששכר_זבולון','קוויטל_101','קוויטל_כללי'].map(t=>`<option value="${t}" ${t===cur?'selected':''}>${t?({'יששכר_זבולון':'יששכר־זבולון','קוויטל_101':'כל לילה','קוויטל_כללי':'כללי'}[t]):'— ללא —'}</option>`).join('');}
function wireFields(d,flds){flds.forEach(fld=>{const el=document.getElementById('f_'+fld);if(!el)return;el.onchange=async e=>{d[fld]=e.target.value;await api('PUT','/api/donor/'+d.id,{[fld]:e.target.value});toast('נשמר ✓');if(fld==='last'||fld==='first'){document.getElementById('cardTitle').textContent=(d.last+' '+d.first).trim();}if(['last','first','tier','category','region','channel'].includes(fld)&&tab==='donors')renderDonors();};});}

function openDonor(d,startTab){
  cardTab=startTab||'details';
  const nopen=(d.tasks||[]).filter(t=>!t.done||t.done==0).length;
  sheet.innerHTML=`<button class="x" id="cx">✕</button>
    <h2 id="cardTitle">${esc(d.last)} ${esc(d.first)}</h2>
    <div class="cardsub"><span class="cardnum">כרטיס #${d.id}</span> ${catPill(d.category)} ${pill(d.tier)} ${d.english?`<span class="ensm" dir="ltr">${esc(d.english)}</span>`:''}</div>
    <div class="ctabs">
      <button class="ctab" data-c="details">פרטים</button>
      <button class="ctab" data-c="kvittel">🕯️ קוויטל</button>
      <button class="ctab" data-c="donations">💳 תרומות</button>
      <button class="ctab" data-c="building">🏛️ בניין${(d.building||[]).length?` <b class="badge">${(d.building||[]).length}</b>`:''}</button>
      <button class="ctab" data-c="contact">📞 קשר${nopen?` <b class="badge">${nopen}</b>`:''}</button>
    </div>
    <div id="cardBody"></div>`;
  ov.classList.add('show');
  document.getElementById('cx').onclick=()=>ov.classList.remove('show');
  sheet.querySelectorAll('.ctab').forEach(b=>b.onclick=()=>{cardTab=b.dataset.c;renderCard(d);});
  renderCard(d);
}
function renderCard(d){
  sheet.querySelectorAll('.ctab').forEach(b=>b.classList.toggle('on',b.dataset.c===cardTab));
  const body=document.getElementById('cardBody');
  if(cardTab==='details') return cardDetails(d,body);
  if(cardTab==='kvittel') return cardKvittel(d,body);
  if(cardTab==='donations') return cardDonations(d,body);
  if(cardTab==='building') return cardBuilding(d,body);
  if(cardTab==='contact') return cardContact(d,body);
}
function buildTotals(d){let price=0,paid=0;(d.building||[]).forEach(x=>{price+=amtNum(x.amount);paid+=amtNum(x.paid);});return {price,paid,owed:price-paid};}
function cardBuilding(d,body){
  const t=buildTotals(d),cur=curSym(d);
  body.innerHTML=`<div class="totals"><div class="tot"><span>סה"כ הקדשות</span><b>${cur}${t.price}</b></div><div class="tot"><span>שולם</span><b>${cur}${t.paid}</b></div><div class="tot ${t.owed>0?'year':''}"><span>נשאר חייב</span><b>${cur}${t.owed}</b></div></div>
    <div id="bldlist"></div>
    <div class="sec"><h3>➕ הוסף הקדשה בבניין</h3>
      <label class="fld"><span>מה ההקדשה (אובייקט)</span><input id="bl_obj" placeholder="למשל: עמוד, ספר תורה, חדר…"></label>
      <div class="two"><label class="fld"><span>מחיר (בכמה קנה)</span><input id="bl_amt" placeholder="סכום"></label>
        <label class="fld"><span>שולם עד כה</span><input id="bl_paid" placeholder="סכום"></label></div>
      <button class="btn" id="bl_add">הוסף הקדשה</button></div>`;
  renderBuilding(d);
  document.getElementById('bl_add').onclick=async()=>{const obj=document.getElementById('bl_obj').value.trim(),amt=document.getElementById('bl_amt').value.trim(),paid=document.getElementById('bl_paid').value.trim();if(!obj&&!amt){toast('הכנס אובייקט וסכום');return;}const r=await api('POST','/api/building',{donor_id:d.id,object:obj,amount:amt,paid:paid});d.building=d.building||[];d.building.push({id:r.id,donor_id:d.id,object:obj,amount:amt,paid:paid,note:'',date:todayStr()});cardBuilding(d,body);toast('נוסף ✓');if(tab==='donors')renderDonors();};
}
function renderBuilding(d){
  const el=document.getElementById('bldlist');if(!el)return;const cur=curSym(d);
  el.innerHTML=(d.building||[]).map(x=>{const owed=amtNum(x.amount)-amtNum(x.paid);return `<div class="plwrap"><div class="pledge ${owed>0?'pending':'given'}"><div class="pi"><b>🏛️ ${esc(x.object||'—')}</b><br><small>מחיר: ${cur}${esc(String(amtNum(x.amount)))} · שולם: ${cur}${esc(String(amtNum(x.paid)))} · <b style="color:${owed>0?'var(--no)':'var(--yes)'}">${owed>0?('נשאר חייב '+cur+owed):'שולם במלואו ✓'}</b></small>${x.note?('<br><small>'+esc(x.note)+'</small>'):''}</div><button class="del" data-del="${x.id}">🗑</button></div>
    <div class="bldedit"><input class="blf" data-k="object" data-id="${x.id}" value="${esc(x.object||'')}" placeholder="אובייקט"><input class="blf" data-k="amount" data-id="${x.id}" value="${esc(x.amount||'')}" placeholder="מחיר" inputmode="decimal"><input class="blf" data-k="paid" data-id="${x.id}" value="${esc(x.paid||'')}" placeholder="שולם" inputmode="decimal"></div></div>`;}).join('')||'<div class="hintxt">אין עדיין הקדשות בבניין. הוסף למטה, או שלח לי את אקסל הבניין ואמזג הכל.</div>';
  el.querySelectorAll('.del').forEach(b=>b.onclick=async()=>{await api('DELETE','/api/building/'+b.dataset.del);d.building=d.building.filter(x=>x.id!=b.dataset.del);cardBuilding(d,document.getElementById('cardBody'));toast('נמחק');if(tab==='donors')renderDonors();});
  el.querySelectorAll('.blf').forEach(inp=>inp.onchange=async()=>{const x=d.building.find(y=>y.id==inp.dataset.id);if(!x)return;x[inp.dataset.k]=inp.value;await api('PUT','/api/building/'+x.id,{[inp.dataset.k]:inp.value});cardBuilding(d,document.getElementById('cardBody'));toast('נשמר ✓');});
}
function cardDetails(d,body){
  const sel=CATS.map(c=>`<option ${c===d.category?'selected':''} value="${c}">${c||'— ללא —'}</option>`).join('');
  const f=(k,v,dir)=>v?`<div class="rf"><div class="k">${k}</div><div class="v" ${dir?'dir="ltr"':''}>${esc(v)}</div></div>`:'';
  const gc=gaps(d.months).length, pend=(d.pledges||[]).filter(p=>p.status!=='נתן').length;
  const dt=donorTotals(d), curd=curSym(d);
  // פירוט מה תרם ועבור מה — ישירות במסך הראשי
  const gitems=[];
  (d.parnes||[]).forEach(p=>gitems.push({amt:amtNum(p.amount),what:(DAYKIND[p.kind]||'🌙 פרנס')+(p.date_text?(' · '+p.date_text):'')+(p.hyear?(' '+p.hyear):''),ded:p.dedication||''}));
  (d.donations||[]).forEach(x=>gitems.push({amt:amtNum(x.amount),what:(x.category||'תרומה')+(x.date?(' · '+gregLabel(x.date)):''),ded:''}));
  (d.partners||[]).filter(p=>p.active!=0).forEach(p=>gitems.push({amt:amtNum(p.amount),what:'🤝 יש"ז — '+(p.avreich||'')+(p.method?(' · '+chLabel(p.method)):''),ded:''}));
  const give=gitems.length?`<div class="givelist"><div class="givehd">💵 מה תרם ועבור מה</div>${gitems.map(g=>`<div class="giverow"><span class="giveamt">${g.amt?(curd+g.amt):'—'}</span><span class="givewhat">${esc(g.what)}${g.ded?`<small> · ${esc(g.ded)}</small>`:''}</span></div>`).join('')}</div>`:'';
  body.innerHTML=`${(gc||pend)?`<div class="notpassed">🔴 לא עבר: ${gc?gc+' חודשים':''}${gc&&pend?' · ':''}${pend?pend+' התחייבויות':''}</div>`:''}
    ${d.purpose?`<div class="purpose">🎯 עבור: ${esc(d.purpose)}</div>`:''}
    <div class="two"><label class="fld"><span>שם משפחה</span><input id="f_last" value="${esc(d.last)}"></label>
      <label class="fld"><span>שם פרטי</span><input id="f_first" value="${esc(d.first)}"></label></div>
    <label class="fld"><span>שם באנגלית</span><input id="f_english" value="${esc(d.english)}" dir="ltr"></label>
    <div class="two"><label class="fld"><span>דרגת קוויטל</span><select id="f_tier">${tierOpts(d.tier)}</select></label>
      <label class="fld"><span>קטגוריה</span><select id="f_category">${sel}</select></label></div>
    <label class="fld"><span>עבור מה (מטרה)</span><input id="f_purpose" value="${esc(d.purpose)}"></label>
    <div class="two"><label class="fld"><span>אזור / מטבע</span><select id="f_region"><option value="">🇺🇸 חו"ל ($)</option><option value="il" ${d.region==='il'?'selected':''}>🇮🇱 ארץ ישראל (₪)</option></select></label>
      <label class="fld"><span>סכום קבוע</span><input id="f_amount" value="${esc(d.amount)}"></label></div>
    <div class="fld"><span>טלפונים</span><div id="phones" class="phones"></div></div>
    <label class="fld"><span>אימייל</span><input id="f_email" value="${esc(d.email)}" dir="ltr"></label>
    <label class="fld"><span>כתובת (רחוב ומספר)</span><input id="f_addr" value="${esc(d.addr)}" dir="${d.region==='il'?'rtl':'ltr'}"></label>
    <div class="two"><label class="fld"><span>עיר</span><input id="f_city" value="${esc(d.city||'')}" dir="${d.region==='il'?'rtl':'ltr'}"></label>
      <label class="fld"><span>מדינה</span><input id="f_country" value="${esc(d.country||'')}" dir="${d.region==='il'?'rtl':'ltr'}"></label></div>
    <label class="fld"><span>מיקוד</span><input id="f_zip" value="${esc(d.zip||'')}" dir="ltr"></label>
    <label class="fld"><span>עסק</span><input id="f_business" value="${esc(d.business)}"></label>
    <label class="fld"><span>ערוץ חיוב</span><select id="f_channel">${channelOpts(d.channel)}</select></label>
    <button class="btn" id="f_saveall" style="width:100%;margin:6px 0">💾 שמור פרטים</button>
    ${f('סטטוס תשלום',d.pay_status)}${d.created?f('נוסף למערכת',d.created+(d.source?(' · דרך '+d.source):'')):''}
    ${d.months?`<div class="rf" style="flex-direction:column;gap:6px"><div class="k">מפת חודשים${gaps(d.months).length?' · <b style="color:var(--no)">'+gaps(d.months).length+' לא עברו</b>':''}</div>${monthGrid(d.months)}</div>`:''}
    ${izSummaryHTML(d)}
    ${give}
    ${(dt.all||dt.year)?`<div class="totals" style="cursor:pointer" id="gototot"><div class="tot"><span>סה"כ שנתרם</span><b>${curd}${dt.all}</b></div><div class="tot year"><span>השנה (${GREGYEAR})</span><b>${curd}${dt.year}</b></div></div>`:''}
    <div class="sec" style="text-align:center"><button class="tinydel" id="f_delete">מחיקת תורם לצמיתות</button></div>`;
  const gt=document.getElementById('gototot'); if(gt)gt.onclick=()=>{cardTab='donations';renderCard(d);};
  const FF=['last','first','english','tier','category','purpose','amount','email','addr','city','country','zip','business','region','channel'];
  wireFields(d,FF);
  document.getElementById('f_saveall').onclick=async()=>{const body={};FF.forEach(k=>{const el=document.getElementById('f_'+k);if(el){body[k]=el.value;d[k]=el.value;}});await api('PUT','/api/donor/'+d.id,body);toast('נשמר ✓');if(tab==='donors')renderDonors();};
  renderPhones(d);
  document.getElementById('f_delete').onclick=async()=>{
    if(!confirm('למחוק את "'+(d.last+' '+d.first).trim()+'" לצמיתות?\n\nיימחקו גם כל התרומות, הקוויטל, האברכים והשטרות שלו. אי אפשר לבטל.'))return;
    if(!confirm('בטוח? זו פעולה שאי אפשר לבטל.'))return;
    await api('DELETE','/api/donor/'+d.id);DB=DB.filter(x=>x.id!==d.id);ov.classList.remove('show');toast('התורם נמחק');render();
  };
}
function splitPhones(s){return (s||'').split('/').map(x=>x.trim()).filter(Boolean);}
function renderPhones(d){
  const el=document.getElementById('phones'); if(!el) return;
  el.innerHTML='';
  const save=async()=>{const nums=[...el.querySelectorAll('.phin')].map(x=>x.value.trim()).filter(Boolean);d.phone=nums.join(' / ');await api('PUT','/api/donor/'+d.id,{phone:d.phone});toast('נשמר ✓');if(tab==='donors')renderDonors();};
  const addRow=(val)=>{const row=document.createElement('div');row.className='phrow';
    row.innerHTML=`<input class="phin" dir="ltr" inputmode="tel" value="${esc(val||'')}" placeholder="+1 ..."><button class="del phdel" title="מחק">🗑</button>`;
    row.querySelector('.phin').onchange=save;
    row.querySelector('.phdel').onclick=()=>{row.remove();save();};
    el.insertBefore(row, el.lastChild); return row;};
  const addBtn=document.createElement('button');addBtn.className='btn sm phadd';addBtn.textContent='➕ טלפון נוסף';
  addBtn.onclick=()=>{const r=addRow('');r.querySelector('.phin').focus();};
  el.appendChild(addBtn);
  const list=splitPhones(d.phone); if(!list.length) list.push('');
  list.forEach(addRow);
}
const KVTIER={'קוויטל_101':'כל לילה','קוויטל_כללי':'כללי','יששכר_זבולון':'יששכר־זבולון'};
function cardKvittel(d,body){
  const inKv=KVTIER[d.tier];
  const empty=!(d.prayers&&d.prayers.length);
  const sugg=(empty&&inKv)?((d.first||'')+' '+(d.last||'')).trim():'';
  body.innerHTML=`${inKv?`<div class="hintxt">✡️ מסומן בקוויטל <b>${KVTIER[d.tier]}</b>.${empty?' עדיין לא הוזנו שמות לתפילה — הוסף למטה (בדרך כלל שם התורם: "פלוני בן אמו").':''}</div>`:''}
    <div id="prayers"></div>
    <div class="addrow"><input id="pr_new" placeholder="שם לתפילה (למשל: יעקב בן שרה לרפואה שלמה)" value="${esc(sugg)}"><button class="btn sm" id="pr_add">הוסף</button></div>`;
  renderPrayers(d);
  document.getElementById('pr_add').onclick=async()=>{const t=document.getElementById('pr_new').value.trim();if(!t)return;const r=await api('POST','/api/prayer',{donor_id:d.id,text:t,tier:d.tier||''});d.prayers=d.prayers||[];d.prayers.push({id:r.id,text:t,tier:d.tier||''});document.getElementById('pr_new').value='';renderPrayers(d);toast('נוסף ✓');};
}
function cardDonations(d,body){
  const isIZ=d.tier==='יששכר_זבולון';
  const cur=curSym(d);
  const tot=donorTotals(d);
  body.innerHTML=`
    ${izSummaryHTML(d)}
    <div class="sec onlinebox"><h3>💳 גבייה אונליין</h3>
      <div class="hintxt">דף תרומה מאובטח — פתחו אותו מהמשרד למילוי פרטי אשראי, או שלחו לתורם קישור אישי.</div>
      <div class="obtns"><button class="btn" id="on_open">🌐 פתח דף גבייה</button>
        <button class="btn ghost" id="on_share">📤 שלח / העתק קישור אישי</button></div></div>
    <div class="sec"><h3>💳 חיובים ותשלומים</h3><div id="transactions"></div>
      <div class="addrow"><input id="tx_amt" placeholder="סכום ${cur}" style="max-width:92px"><input id="tx_cat" placeholder="עבור מה"><button class="btn sm" id="tx_add">רשום חיוב</button></div>
      <div class="hintxt">חיובים מהדף המקוון נכנסים כ"ממתין". עדכן סטטוס: אושר / סורב / נגבה, וסמן תשלומים ששולמו.</div></div>
    ${isIZ?`<div class="sec"><h3>🤝 יששכר־זבולון — האברך שהוא מחזיק</h3><div id="partners"></div>
      <div class="addrow"><input id="pa_name" placeholder="שם האברך"><button class="btn sm" id="pa_add">הוסף</button></div></div>`:''}
    <div class="sec"><h3>💵 רישום תרומה חדשה</h3>
      <div class="two"><label class="fld"><span>סכום (${cur})</span><input id="dn_amt" placeholder="480"></label>
        <label class="fld"><span>אמצעי</span><select id="dn_method"><option>אשראי</option><option>אונליין</option><option>המחאה</option><option>מזומן</option><option>העברה בנקאית</option><option>Banquest</option></select></label></div>
      <label class="fld"><span>סוג / עבור מה</span><select id="dn_cat">
        <option value="">— בחר —</option><option>קבוע</option><option>יששכר־זבולון</option>
        <option value="פרנס לילה" data-day="parnes">🌙 פרנס לילה (בחר יום)</option>
        <option value="חדר קפה" data-day="coffee">☕ חדר קפה / שתייה חמה (בחר יום)</option>
        <option value="ארוחת בוקר" data-day="breakfast">🍳 ארוחת בוקר (בחר יום)</option>
        <option value="קמפיין">🎊 קמפיין (חג/מבצע)</option><option>נר למאור</option><option>חד-פעמי</option><option>אחר</option></select></label>
      <div id="dn_daybox" style="display:none"><div class="two"><label class="fld"><span>חודש עברי</span><select id="dn_hm">${HMORD.map(m=>`<option>${m}</option>`).join('')}</select></label>
        <label class="fld"><span>יום</span><select id="dn_hd">${[...Array(30)].map((_,i)=>`<option value="${i+1}">${heDay(i+1)}</option>`).join('')}</select></label></div>
        <label class="fld"><span>שנה עברית</span><select id="dn_hy">${heYearOpts()}</select></label></div>
      <label class="fld" id="dn_catfree_l" style="display:none"><span>שם הקטגוריה / הקמפיין</span><input id="dn_catfree" placeholder="למשל: קמפיין סוכות ${esc(HEBYEAR||'תשפ״ז')}"></label>
      <label class="fld"><span>תאריך (לועזי)</span><input id="dn_date" type="date"></label>
      <label class="fld"><span>🕯️ שם לתפילה (לקוויטל)</span><textarea id="dn_pray" rows="2" placeholder="למשל: יעקב בן שרה לרפואה שלמה"></textarea></label>
      <label class="fld"><span>שייך לקוויטל</span><select id="dn_tier"><option value="">— לפי הכרטיס —</option><option value="יששכר_זבולון">יששכר־זבולון</option><option value="קוויטל_101">כל לילה</option><option value="שבועי">שבועי</option><option value="קוויטל_כללי">כללי</option></select></label>
      <button class="btn" id="dn_add">➕ רשום תרומה</button>
      ${d.channel?`<div class="hintxt">ערוץ קבוע בתיק: ${esc(d.channel)}</div>`:''}</div>
    <div class="sec"><h3>🗓️ ימים משובצים (פרנס / קפה / בוקר)</h3><div id="parnes"></div>
      <div class="hintxt">שיבוץ ימים חדשים דרך "רישום תרומה" למעלה (בחר סוג עם יום), או בלוח פרנס יום.</div></div>
    <div class="sec"><h3>🎯 התחייבויות / קמפיינים</h3><div id="pledges"></div>
      <div class="addrow"><input id="pl_cat" placeholder="קטגוריה (למשל חגי סוכות)"><input id="pl_amt" placeholder="סכום" style="max-width:80px"><button class="btn sm" id="pl_add">הוסף</button></div></div>
    <div class="sec dnhist"><div class="dntot"><span>סה"כ שנתרם: <b>${cur}${tot.all}</b></span><span>השנה (${GREGYEAR}): <b>${cur}${tot.year}</b></span></div>
      <div class="dnhead">📜 היסטוריית תרומות</div><div id="donations"></div></div>`;
  if(isIZ){renderPartners(d);document.getElementById('pa_add').onclick=async()=>{const n=document.getElementById('pa_name').value.trim();if(!n)return;const r=await api('POST','/api/partner',{donor_id:d.id,avreich:n});d.partners=d.partners||[];d.partners.push({id:r.id,avreich:n});document.getElementById('pa_name').value='';renderPartners(d);toast('נוסף ✓');};}
  renderDonations(d); renderTransactions(d); renderParnesEdit(d); renderPledges(d);
  document.getElementById('dn_date').value=todayStr();  // ברירת מחדל: היום
  document.getElementById('tx_add').onclick=async()=>{
    const amt=document.getElementById('tx_amt').value.trim(),cat=document.getElementById('tx_cat').value.trim();
    if(!amt){toast('מלא סכום');return;}
    const r=await api('POST','/api/transaction',{donor_id:d.id,amount:amt,category:cat,method:'ידני',status:'pending',date:todayStr()});
    d.transactions=d.transactions||[];d.transactions.unshift({id:r.id,donor_id:d.id,amount:amt,category:cat,method:'ידני',status:'pending',inst_total:1,inst_paid:0,recurring:0,date:todayStr()});
    document.getElementById('tx_amt').value='';document.getElementById('tx_cat').value='';renderTransactions(d);toast('נרשם ✓');};
  const dlink=location.origin+'/donate?d='+d.id;
  document.getElementById('on_open').onclick=()=>window.open(dlink+'&office=1','_blank');
  document.getElementById('on_share').onclick=async()=>{
    const nm=(d.last+' '+d.first).trim();const msg='תרומה לכולל חצות'+(nm?(' — '+nm):'')+':\n'+dlink;
    try{if(navigator.share){await navigator.share({title:'תרומה לכולל חצות',text:msg,url:dlink});return;}}catch(e){}
    try{await navigator.clipboard.writeText(dlink);toast('הקישור הועתק ✓');}catch(e){prompt('העתק את הקישור:',dlink);}
  };
  const catSel=document.getElementById('dn_cat');
  catSel.onchange=()=>{const day=catSel.options[catSel.selectedIndex].dataset.day;document.getElementById('dn_daybox').style.display=day?'block':'none';document.getElementById('dn_catfree_l').style.display=(catSel.value==='אחר'||catSel.value==='קמפיין')?'block':'none';};
  document.getElementById('dn_add').onclick=async()=>{
    let cat=catSel.value;if(cat==='אחר'||cat==='קמפיין')cat=document.getElementById('dn_catfree').value.trim()||cat;
    const amt=document.getElementById('dn_amt').value.trim(),method=document.getElementById('dn_method').value,
      date=document.getElementById('dn_date').value,pray=document.getElementById('dn_pray').value.trim(),tier=document.getElementById('dn_tier').value,
      dayKind=catSel.options[catSel.selectedIndex].dataset.day;
    if(!amt&&!pray){toast('מלא סכום או שם לתפילה');return;}
    if(amt&&!dayKind){const r=await api('POST','/api/donation',{donor_id:d.id,amount:amt,category:cat,method,date});d.donations=d.donations||[];d.donations.unshift({id:r.id,donor_id:d.id,amount:amt,category:cat,method,date,hmonth:r.hmonth});}
    if(dayKind){const hm=document.getElementById('dn_hm').value,hd=+document.getElementById('dn_hd').value,hy=document.getElementById('dn_hy').value,dtext=heDay(hd)+" "+hm;const r=await api('POST','/api/parnes',{donor_id:d.id,day:hd,month:hm,date_text:dtext,dedication:pray||'',amount:amt,kind:dayKind,hyear:hy});d.parnes=d.parnes||[];d.parnes.push({id:r.id,donor_id:d.id,day:hd,month:hm,date_text:dtext,dedication:pray||'',amount:amt,kind:dayKind,hyear:hy});}
    // שם לתפילה יוצר קוויטל רק כשזו תרומה רגילה (לא יום פרנס) — בפרנס השם נשמר בהקדשת התעודה בלבד
    if(pray&&!dayKind){const tr=tier||d.tier||'';const r=await api('POST','/api/prayer',{donor_id:d.id,text:pray,tier:tr});d.prayers=d.prayers||[];d.prayers.push({id:r.id,text:pray,tier:tr});}
    document.getElementById('dn_amt').value='';document.getElementById('dn_pray').value='';
    renderDonations(d);renderParnesEdit(d);toast('נרשם ✓'+(dayKind?' + יום נתפס':'')+(pray?' + שם לקוויטל':''));};
  document.getElementById('pl_add').onclick=async()=>{const cat=document.getElementById('pl_cat').value.trim(),amt=document.getElementById('pl_amt').value.trim();if(!cat)return;const r=await api('POST','/api/pledge',{donor_id:d.id,category:cat,amount:amt,status:'טרם'});d.pledges=d.pledges||[];d.pledges.push({id:r.id,donor_id:d.id,category:cat,amount:amt,status:'טרם'});document.getElementById('pl_cat').value='';document.getElementById('pl_amt').value='';renderPledges(d);toast('נוסף ✓');};
}
function cardContact(d,body){
  body.innerHTML=`
    <div class="sec"><h3>📞 תיעוד קשר</h3><div id="clog"></div>
      <div class="addrow"><select id="cl_ch"><option>טלפון</option><option>אימייל</option><option>וואטסאפ</option><option>פגישה</option></select><input id="cl_date" type="date"></div>
      <textarea id="cl_sum" rows="2" placeholder="מה סוכם / תוכן השיחה" style="margin-top:6px"></textarea>
      <div class="addrow"><input id="cl_next" type="date" title="מתי לחזור"><button class="btn sm" id="cl_add">שמור</button></div>
      <div class="hintxt">התאריך התחתון = מתי לחזור אליו (נכנס ל"משימות")</div></div>
    <div class="sec"><h3>🔔 תזכורות</h3><div id="tlist"></div>
      <div class="addrow"><select id="tk_kind"><option value="charge">💳 לחייב</option><option value="parnes">🌙 פרנס יום</option><option value="prayer">🙏 להתפלל</option><option value="followup">📞 לחזור</option><option value="other">🔔 אחר</option></select><input id="tk_date" type="date"></div>
      <div class="addrow"><input id="tk_note" placeholder="פרטים (על מה)"><button class="btn sm" id="tk_add">➕ קבע תזכורת</button></div>
      <div class="hintxt">כל תזכורת נכנסת ללשונית "משימות", ואפשר להוסיף אותה ליומן Google.</div></div>`;
  renderContacts(d); renderReminders(d);
  document.getElementById('cl_add').onclick=async()=>{const ch=document.getElementById('cl_ch').value,date=document.getElementById('cl_date').value,sum=document.getElementById('cl_sum').value.trim(),next=document.getElementById('cl_next').value;if(!sum&&!date)return;const r=await api('POST','/api/contact',{donor_id:d.id,channel:ch,date:date,summary:sum,next_date:next});d.contacts=d.contacts||[];d.contacts.unshift({id:r.id,channel:ch,date:date,summary:sum,next_date:next});if(next){d.tasks=d.tasks||[];d.tasks.push({id:r.task_id,donor_id:d.id,due_date:next,kind:'followup',note:sum.slice(0,80),done:0});}document.getElementById('cl_sum').value='';renderContacts(d);renderReminders(d);toast('נשמר ✓');};
  document.getElementById('tk_add').onclick=async()=>{const kind=document.getElementById('tk_kind').value,note=document.getElementById('tk_note').value.trim(),date=document.getElementById('tk_date').value;if(!date){toast('בחר תאריך');return;}const r=await api('POST','/api/task',{donor_id:d.id,due_date:date,kind:kind,note:note});d.tasks=d.tasks||[];d.tasks.push({id:r.id,donor_id:d.id,due_date:date,kind:kind,note:note,done:0});document.getElementById('tk_note').value='';renderReminders(d);toast('נקבעה תזכורת ✓');};
}
function renderReminders(d){
  const el=document.getElementById('tlist');if(!el)return;
  const td=todayStr(),donor=(d.last+' '+d.first).trim();
  const list=(d.tasks||[]).filter(t=>!t.done||t.done==0).sort((a,b)=>(a.due_date||'9999').localeCompare(b.due_date||'9999'));
  el.innerHTML=list.map(t=>{const over=t.due_date&&t.due_date<=td,g=gcalLink(t,donor);
    return `<div class="remitem ${over?'over':''}"><div class="ri"><b>${KIND[t.kind]||'🔔'}</b> ${esc(t.due_date||'')} ${t.note?('· '+esc(t.note)):''}</div>
      ${g?`<a class="gcal" href="${g}" target="_blank" rel="noopener">➕ ליומן</a>`:''}
      <button class="stbtn" style="background:var(--yes);color:#fff" data-done="${t.id}">✓</button><button class="del" data-del="${t.id}">🗑</button></div>`;}).join('')||'<div class="hintxt">אין תזכורות. הוסף למטה.</div>';
  el.querySelectorAll('[data-done]').forEach(b=>b.onclick=async()=>{const t=d.tasks.find(x=>x.id==b.dataset.done);if(t){t.done=1;await api('PUT','/api/task/'+t.id,{done:1});}renderReminders(d);toast('בוצע ✓');});
  el.querySelectorAll('.del').forEach(b=>b.onclick=async()=>{await api('DELETE','/api/task/'+b.dataset.del);d.tasks=d.tasks.filter(x=>x.id!=b.dataset.del);renderReminders(d);});
}
const FBCH={'תודה':'🙏 תודה','הקדשה':'🖼️ הקדשה','אימייל':'📧 אימייל','וואטסאפ':'💬 וואטסאפ','טלפון':'📞 טלפון'};
const FBOPTS=[['','— איך יצרנו קשר? —'],['תודה','🙏 אמרנו תודה'],['הקדשה','🖼️ שלחנו תמונת הקדשה'],['אימייל','📧 אימייל'],['וואטסאפ','💬 וואטסאפ'],['טלפון','📞 טלפון']];
function fbChip(x){
  if(!x.fb_channel) return '';
  return `<span class="fbchip on">✓ פידבק · ${FBCH[x.fb_channel]||esc(x.fb_channel)}${x.fb_date?(' · '+esc(x.fb_date)):''}${x.fb_followup?(' · 🔁 לחזור '+esc(x.fb_followup)):''}</span>`;
}
function dnRow(x,cur){cur=cur||'$';
  return `<div class="dncrow"><div class="dnci"><b>${cur}${esc(x.amount)}</b>${x.category?(' · '+esc(x.category)):''} <span class="dnmeta">${x.date?esc(gregLabel(x.date)):''}${x.method?(' · '+esc(x.method)):''}</span>${x.fb_channel?`<span class="fbmini">✓ ${FBCH[x.fb_channel]||esc(x.fb_channel)}${x.fb_followup?(' · 🔁'+esc(x.fb_followup)):''}</span>`:''}</div>`+
    `<div class="dncact"><button class="dnpaid ${+x.paid?'yes':'no'}" data-paid="${x.id}">${+x.paid?'שולם ✓':'לא שולם'}</button><button class="dnrcpt" data-id="${x.id}" title="קבלה">🧾</button><button class="dnfb" data-id="${x.id}" title="פידבק">${x.fb_channel?'✏️':'💬'}</button><button class="del" data-del="${x.id}" title="מחק">🗑</button></div></div>`+
    `<div class="fbedit hidden" data-fb="${x.id}">
      <div class="fbrow"><select class="fb_ch">${FBOPTS.map(([v,l])=>`<option value="${v}" ${v===(x.fb_channel||'')?'selected':''}>${l}</option>`).join('')}</select><input type="date" class="fb_date" value="${esc(x.fb_date||'')}"></div>
      <input class="fb_note" placeholder="תוכן קצר (לא חובה)" value="${esc(x.fb_note||'')}">
      <label class="fbfollow">🔁 מתי לחזור אליו: <input type="date" class="fb_follow" value="${esc(x.fb_followup||'')}"></label>
      <button class="btn sm fb_save" data-id="${x.id}">שמור פידבק</button>
    </div>`;
}
function renderDonations(d){
  const el=document.getElementById('donations');if(!el)return;const list=(d.donations||[]);const cur=curSym(d);
  const tot=list.reduce((s,x)=>s+(amtNum(x.amount)),0);
  el.innerHTML=(list.length?`<div class="dncount">${list.length} תרומות · ${cur}${tot}</div>`:'')+(list.map(x=>dnRow(x,cur)).join('')||'<div class="hintxt">עדיין אין תרומות.</div>');
  el.querySelectorAll('.dnpaid').forEach(b=>b.onclick=async()=>{const x=d.donations.find(y=>y.id==b.dataset.paid);x.paid=+x.paid?0:1;await api('PUT','/api/donation/'+x.id,{paid:x.paid});renderDonations(d);});
  el.querySelectorAll('.dnrcpt').forEach(b=>b.onclick=()=>{const x=d.donations.find(y=>y.id==b.dataset.id);openReceipt(d,x);});
  el.querySelectorAll('.dnfb').forEach(b=>b.onclick=()=>{el.querySelector('.fbedit[data-fb="'+b.dataset.id+'"]').classList.toggle('hidden');});
  el.querySelectorAll('.fb_save').forEach(b=>b.onclick=async()=>{
    const box=el.querySelector('.fbedit[data-fb="'+b.dataset.id+'"]');
    const ch=box.querySelector('.fb_ch').value, fd=box.querySelector('.fb_date').value, nt=box.querySelector('.fb_note').value.trim(), fu=box.querySelector('.fb_follow').value;
    if(!ch){toast('בחר איך יצרנו קשר');return;}
    const x=d.donations.find(y=>y.id==b.dataset.id);
    x.fb_channel=ch; x.fb_date=fd||todayStr(); x.fb_note=nt; x.fb_followup=fu;
    await api('PUT','/api/donation/'+x.id,{fb_channel:x.fb_channel,fb_date:x.fb_date,fb_note:x.fb_note,fb_followup:x.fb_followup});
    if(fu){const note='פידבק — לחזור ל'+(d.last+' '+d.first).trim()+(x.category?(' ('+x.category+')'):'');const r=await api('POST','/api/task',{donor_id:d.id,due_date:fu,kind:'followup',note});d.tasks=d.tasks||[];d.tasks.push({id:r.id,donor_id:d.id,due_date:fu,kind:'followup',note,done:0});}
    renderDonations(d);toast('פידבק נשמר ✓'+(fu?' + תזכורת לחזור':''));
  });
  el.querySelectorAll('.del').forEach(b=>b.onclick=async()=>{await api('DELETE','/api/donation/'+b.dataset.del);d.donations=d.donations.filter(x=>x.id!=b.dataset.del);renderDonations(d);});
}
/* ---------- קבלה אמריקאית (501c3) ---------- */
function openReceipt(d,x){
  const name=(d.english&&d.english.trim())||((d.last||'')+' '+(d.first||'')).trim();
  const p=new URLSearchParams({n:name,a:x.amount||'',p:x.category||'',d:x.date||todayStr(),r:'KC-'+(x.id||'')});
  window.open('/receipt?'+p.toString(),'_blank');
}

/* ---------- חיובים ותשלומים ---------- */
const TXST={pending:{t:'🕒 ממתין',c:'pending'},approved:{t:'✅ אושר',c:'given'},settled:{t:'💰 נגבה',c:'given'},declined:{t:'🔴 סורב',c:'pending'},refunded:{t:'↩️ זוכה',c:''}};
const TXORDER=['pending','approved','settled','declined','refunded'];
function txStatusOpts(cur){return TXORDER.map(s=>`<option value="${s}" ${s===cur?'selected':''}>${TXST[s].t}</option>`).join('');}
function txMoney(t){
  const rec=+t.recurring, tot=+t.inst_total||1, paid=+t.inst_paid||0, amt=amtNum(t.amount);
  const per = rec? amt : (tot>1? amt/tot : amt);
  const remaining = tot>0? Math.max(0, per*(tot-paid)) : 0;
  return {per, paid, tot, remaining, rec};
}
function txInst(t,cur){cur=cur||'$';
  if(+t.inst_total===1 && !+t.recurring) return '';
  const m=txMoney(t);
  if(m.tot===0) return ` · הוראת קבע · שולמו ${m.paid} תשלומים`;
  return ` · שולם ${m.paid}/${m.tot}${m.remaining>0?(' · נותרו '+cur+Math.round(m.remaining)):' · הושלם ✓'}`;
}
function txAddMonths(iso,n){const d=new Date(iso);if(isNaN(d))return null;d.setMonth(d.getMonth()+n);return d;}
function txUntil(t){
  if(!+t.recurring && +t.inst_total<=1) return '';
  if(+t.inst_total===0) return ' · עד ביטול';
  if(t.date){const e=txAddMonths(t.date,+t.inst_total);if(e)return ' · עד '+((e.getMonth()+1)+'/'+e.getFullYear());}
  return '';
}
function txRow(t,cur){cur=cur||'$';
  const st=TXST[t.status]||TXST.pending;
  return `<div class="plwrap"><div class="pledge ${st.c}"><div class="pi"><b>${cur}${esc(t.amount)}</b> ${t.category?('· '+esc(t.category)):''} <span class="txbadge">${st.t}</span>`+
    `<br><small>${t.date?esc(gregLabel(t.date)):''}${t.method?(' · '+esc(t.method)):''}${txInst(t,cur)}${txUntil(t)}</small></div>`+
    `<button class="del" data-del="${t.id}">🗑</button></div>`+
    `<div class="txctl"><select class="txst" data-id="${t.id}">${txStatusOpts(t.status)}</select>`+
    ((+t.inst_total!==1||+t.recurring)?`<button class="btn sm txpay" data-id="${t.id}">＋ תשלום שולם</button>`:'')+
    `<button class="btn sm ghost txrcpt" data-id="${t.id}">🧾 קבלה</button>`+
    `</div></div>`;
}
function wireTx(el,d,after){
  el.querySelectorAll('.txst').forEach(s=>s.onchange=async()=>{const t=d.transactions.find(x=>x.id==s.dataset.id);t.status=s.value;await api('PUT','/api/transaction/'+t.id,{status:t.value});after();toast('עודכן ✓');});
  el.querySelectorAll('.txpay').forEach(b=>b.onclick=async()=>{const t=d.transactions.find(x=>x.id==b.dataset.id);t.inst_paid=(+t.inst_paid||0)+1;const upd={inst_paid:t.inst_paid};if(+t.inst_total>0&&t.inst_paid>=+t.inst_total){t.status='settled';upd.status='settled';}await api('PUT','/api/transaction/'+t.id,upd);after();toast('תשלום נרשם ✓');});
  el.querySelectorAll('.txrcpt').forEach(b=>b.onclick=()=>{const t=d.transactions.find(x=>x.id==b.dataset.id);openReceipt(d,t);});
  el.querySelectorAll('.del').forEach(b=>b.onclick=async()=>{await api('DELETE','/api/transaction/'+b.dataset.del);d.transactions=d.transactions.filter(x=>x.id!=b.dataset.del);after();});
}
function renderTransactions(d){
  const el=document.getElementById('transactions');if(!el)return;
  const list=(d.transactions||[]);const cur=curSym(d);
  el.innerHTML=list.map(t=>txRow(t,cur)).join('')||'<div class="hintxt">אין חיובים עדיין. תרומות מהדף המקוון וכל חיוב ידני יופיעו כאן.</div>';
  wireTx(el,d,()=>renderTransactions(d));
}
let chFilter='';
function renderCharges(){
  const all=[];
  DB.forEach(d=>(d.transactions||[]).forEach(t=>all.push({t,d})));
  all.sort((a,b)=>String(b.t.date||'').localeCompare(String(a.t.date||''))||b.t.id-a.t.id);
  const cnt=s=>all.filter(x=>x.t.status===s).length;
  const CF=[['','הכל',all.length],['pending','🕒 ממתין',cnt('pending')],['approved','✅ אושרו',cnt('approved')],['settled','💰 נגבו',cnt('settled')],['declined','🔴 סורבו',cnt('declined')]];
  chips.innerHTML=CF.map(([k,l,n])=>`<button class="chip ${chFilter===k?'on':''}" data-k="${k}">${l} <b>${n}</b></button>`).join('');
  chips.querySelectorAll('.chip').forEach(c=>c.onclick=()=>{chFilter=c.dataset.k;renderCharges();});
  let rows=chFilter?all.filter(x=>x.t.status===chFilter):all;
  rows=rows.filter(x=>matchQ((x.d.last||'')+' '+(x.d.first||'')+' '+(x.t.category||'')));
  const paid=all.filter(x=>x.t.status==='settled'||x.t.status==='approved').reduce((s,x)=>s+amtNum(x.t.amount),0);
  const pend=all.filter(x=>x.t.status==='pending').reduce((s,x)=>s+amtNum(x.t.amount),0);
  view.innerHTML=`<a class="btn addbig" href="/reconcile" target="_blank" style="text-decoration:none;display:block;text-align:center">💳 טיפול בתרומות Authorize (יולי 2026)</a>
    <div class="totals"><div class="tot"><span>נגבה / אושר</span><b>$${Math.round(paid)}</b></div><div class="tot year"><span>ממתין לגבייה</span><b>$${Math.round(pend)}</b></div></div>`+
    `<div class="cnt">${rows.length} חיובים</div><div class="list">`+
    (rows.map(({t,d})=>{const st=TXST[t.status]||TXST.pending;const rc=curSym(d);return `<div class="rowc" data-id="${d.id}"><div><div class="nm">${esc(d.last)} <small>${esc(d.first)}</small></div><div class="purp">${rc}${esc(t.amount)} ${t.category?('· '+esc(t.category)):''}${txInst(t,rc)}${txUntil(t)}</div></div><div class="meta"><span class="txbadge ${st.c}">${st.t}</span><span class="ph">${esc(t.date||'')}${t.method?(' · '+esc(t.method)):''}</span></div></div>`;}).join('')||'<div class="empty">אין חיובים</div>')+`</div>`;
  view.querySelectorAll('.rowc').forEach(r=>r.onclick=()=>openDonor(DB.find(x=>x.id==r.dataset.id)));
}
function renderPartners(d){
  const el=document.getElementById('partners');if(!el)return;
  const act=(d.partners||[]).filter(p=>p.active!=0);
  const izfiles=(d.files||[]).filter(f=>f.kind==='iz'||!f.kind);
  const cur=curSym(d);
  el.innerHTML=act.map(p=>`<div class="pledge" style="flex-direction:column;align-items:stretch;gap:4px">
    <div style="display:flex;justify-content:space-between;align-items:center"><b>👨‍🎓 אברך שהוא מחזיק</b><button class="del" data-del="${p.id}">🗑</button></div>
    <input class="pfield" data-id="${p.id}" data-k="avreich" value="${esc(p.avreich||'')}" placeholder="שם האברך" style="font-weight:700">
    <div class="two"><label class="fld"><span>סכום (${cur})</span><input class="pfield" data-id="${p.id}" data-k="amount" value="${esc(p.amount||'')}" inputmode="decimal" placeholder="0"></label>
      <label class="fld"><span>איך משולם</span><select class="pfield" data-id="${p.id}" data-k="method">${channelOpts(p.method)}</select></label></div>
    <div class="two"><label class="fld"><span>מתאריך (עברי)</span><input class="pfield" data-id="${p.id}" data-k="start_date" value="${esc(p.start_date||'')}" placeholder="א' אייר תשפ״ו"></label>
      <label class="fld"><span>הערות</span><input class="pfield" data-id="${p.id}" data-k="note" value="${esc(p.note||'')}" placeholder="הערה (רשות)"></label></div>
  </div>`).join('')||'<div class="hintxt">עדיין לא הוזן. הוסף אברך למטה.</div>';
  el.innerHTML+=`<div class="izshtar"><div class="izshtar-t">📝 מעקב חוב יששכר־זבולון</div>
      <textarea id="iz_note" rows="2" placeholder="למשל: השלים חוב עד חודש תמוז · חייב 3 חודשים · שילם $4500 ב-13/7">${esc(d.iz_note||'')}</textarea>
      <button class="btn sm" id="iz_note_save" style="margin-top:4px">💾 שמור הערת חוב</button></div>
    <div class="izshtar"><div class="izshtar-t">📄 שטר שותפות:</div><div class="avfiles">${izfiles.map(fileChip).join('')||'<span class="hintxt">אין שטר עדיין</span>'}<label class="filebtn">📎 העלה שטר הסכם<input type="file" accept="application/pdf,image/*" class="pshtar" hidden></label></div></div>`;
  const izn=el.querySelector('#iz_note');
  const iznSave=async()=>{d.iz_note=izn.value;await api('PUT','/api/donor/'+d.id,{iz_note:izn.value});toast('נשמר ✓');};
  if(izn){izn.onblur=()=>{if((d.iz_note||'')!==izn.value)iznSave();};el.querySelector('#iz_note_save').onclick=iznSave;}
  el.querySelectorAll('.pfield').forEach(inp=>inp.onchange=async()=>{const p=(d.partners||[]).find(x=>x.id==inp.dataset.id);if(!p)return;p[inp.dataset.k]=inp.value;await api('PUT','/api/partner/'+p.id,{[inp.dataset.k]:inp.value});toast('נשמר ✓');if(inp.dataset.k==='amount'&&tab==='donors')renderDonors();});
  el.querySelectorAll('.del').forEach(b=>b.onclick=async()=>{await api('DELETE','/api/partner/'+b.dataset.del);d.partners=d.partners.filter(x=>x.id!=b.dataset.del);renderPartners(d);});
  el.querySelectorAll('.fdel').forEach(b=>b.onclick=async()=>{await api('DELETE','/api/file/'+b.dataset.fid);d.files=(d.files||[]).filter(x=>x.id!=b.dataset.fid);renderPartners(d);toast('נמחק');});
  const up=el.querySelector('.pshtar');if(up)up.onchange=()=>uploadFile('iz',d.id,up,load);
}
function renderContacts(d){
  const el=document.getElementById('clog');if(!el)return;
  el.innerHTML=(d.contacts||[]).map(c=>`<div class="logrow"><div class="pi"><b>${esc(c.channel)}</b> <small>${esc(c.date||'')}</small>${c.next_date?(' · <span style="color:var(--no)">חזור: '+esc(c.next_date)+'</span>'):''}<br>${esc(c.summary||'')}</div><button class="del" data-del="${c.id}">🗑</button></div>`).join('')||'<div class="hintxt">אין עדיין תיעוד.</div>';
  el.querySelectorAll('.del').forEach(b=>b.onclick=async()=>{await api('DELETE','/api/contact/'+b.dataset.del);d.contacts=d.contacts.filter(x=>x.id!=b.dataset.del);renderContacts(d);});
}
function renderPledges(d){
  const el=document.getElementById('pledges');
  el.innerHTML=(d.pledges||[]).map(p=>{const g=p.status==='נתן';return `<div class="plwrap"><div class="pledge ${g?'given':'pending'}"><div class="pi"><b>${esc(p.category)}</b> ${p.amount?('· $'+esc(p.amount)):''}<br><small>${g?'נתן ✓':'טרם נתן'}</small></div><button class="stbtn" data-id="${p.id}">${g?'נתן':'טרם'}</button><button class="del" data-del="${p.id}">🗑</button></div><label class="remset">🔔 תזכורת לחיוב: <input type="date" class="plrem" data-cat="${esc(p.category)}" data-amt="${esc(p.amount)}"></label></div>`;}).join('')||'<div class="hintxt">אין עדיין. הוסף למטה.</div>';
  el.querySelectorAll('.stbtn').forEach(b=>b.onclick=async()=>{const p=d.pledges.find(x=>x.id==b.dataset.id);p.status=p.status==='נתן'?'טרם':'נתן';await api('PUT','/api/pledge/'+p.id,p);renderPledges(d);toast('עודכן ✓');});
  el.querySelectorAll('.del').forEach(b=>b.onclick=async()=>{await api('DELETE','/api/pledge/'+b.dataset.del);d.pledges=d.pledges.filter(x=>x.id!=b.dataset.del);renderPledges(d);});
  el.querySelectorAll('.plrem').forEach(x=>x.onchange=async()=>{if(!x.value)return;const note='חייב: '+x.dataset.cat+(x.dataset.amt?(' $'+x.dataset.amt):'');const r=await api('POST','/api/task',{donor_id:d.id,due_date:x.value,kind:'charge',note});d.tasks=d.tasks||[];d.tasks.push({id:r.id,donor_id:d.id,due_date:x.value,kind:'charge',note,done:0});toast('תזכורת לחיוב נקבעה ✓');});
}
function autoGrow(t){t.style.height='auto';t.style.height=(t.scrollHeight+6)+'px';}
function renderPrayers(d){
  const el=document.getElementById('prayers');
  el.innerHTML=(d.prayers||[]).map(p=>`<div class="prow"><textarea class="prtx" data-id="${p.id}">${esc(p.text)}</textarea><button class="del" data-del="${p.id}">🗑</button></div>`).join('')||'<div class="hintxt">אין שמות עדיין. הוסף למטה.</div>';
  el.querySelectorAll('.prtx').forEach(t=>{autoGrow(t);t.addEventListener('input',()=>autoGrow(t));t.onblur=async()=>{const p=d.prayers.find(x=>x.id==t.dataset.id);if(!p||p.text===t.value)return;p.text=t.value;await api('PUT','/api/prayer/'+p.id,{text:t.value});toast('נשמר ✓');};});
  el.querySelectorAll('.del').forEach(b=>b.onclick=async()=>{await api('DELETE','/api/prayer/'+b.dataset.del);d.prayers=d.prayers.filter(x=>x.id!=b.dataset.del);renderPrayers(d);toast('נמחק');});
}
const DAYKIND={parnes:'🌙 פרנס',coffee:'☕ קפה',breakfast:'🍳 בוקר'};
function openParnesCert(d,p){
  if(!p)return;
  const dtext=(p.day&&p.month)?(heDay(+p.day)+" "+p.month):(p.date_text||'');
  const yr=p.hyear||HEBYEAR;
  const date=dtext+(yr?(' '+yr):'');
  // השמות/הנוסח פעם אחת בגדול — עדיפות לשמות שנרשמו ליום זה, אחרת לשם התפילה בכרטיס
  const names=(p.dedication&&p.dedication.trim())||(d.prayers&&d.prayers[0]&&d.prayers[0].text)||'';
  const params=new URLSearchParams({kind:p.kind||'parnes',date,names});
  window.open('/parnes-cert?'+params.toString(),'_blank');
}
function renderParnesEdit(d){
  const el=document.getElementById('parnes');
  const tdy=todayStr(), cur=curSym(d);
  const ptot=(d.parnes||[]).reduce((s,p)=>s+amtNum(p.amount),0);
  const head=(d.parnes&&d.parnes.length)?`<div class="dncount">${d.parnes.length} ימי פרנס · סה"כ ${cur}${ptot}</div>`:'';
  el.innerHTML=head+((d.parnes||[]).map(p=>{const passed=p.night_date&&p.night_date<tdy;return `<div class="plwrap"><div class="pledge ${p.status==='suggested'?'pending':'given'}"><div class="pi"><b>${p.status==='suggested'?'🔵 הצעה':'🟢'} ${DAYKIND[p.kind]||'🌙'} · ${esc(p.date_text)}${p.hyear?(' '+esc(p.hyear)):''}</b> ${p.amount?('· <b style="color:var(--yes)">'+cur+esc(p.amount)+'</b>'):''}${passed&&+p.paid?' <span class="fbchip on">🌙 הסתיים</span>':''}</div><button class="del" data-del="${p.id}">🗑</button></div>
    <div class="two" style="margin:6px 0 0"><label class="fld"><span>סכום</span><input class="pyamt" data-id="${p.id}" value="${esc(p.amount||'')}" inputmode="decimal" placeholder="0"></label>
      <label class="fld"><span>סוג</span><select class="pykind" data-id="${p.id}"><option value="parnes" ${p.kind==='parnes'?'selected':''}>🌙 פרנס לילה</option><option value="coffee" ${p.kind==='coffee'?'selected':''}>☕ פרנס קפה</option><option value="breakfast" ${p.kind==='breakfast'?'selected':''}>🍳 ארוחת בוקר</option></select></label></div>
    <div class="two"><label class="fld"><span>חודש</span><select class="pymon" data-id="${p.id}">${HMORD.map(m=>`<option ${m===p.month?'selected':''}>${m}</option>`).join('')}</select></label>
      <label class="fld"><span>יום</span><select class="pyday" data-id="${p.id}">${[...Array(30)].map((_,i)=>`<option value="${i+1}" ${(i+1)==+p.day?'selected':''}>${heDay(i+1)}</option>`).join('')}</select></label>
      <label class="fld"><span>שנה</span><select class="pyyr" data-id="${p.id}">${heYearOpts(p.hyear)}</select></label></div>
    <label class="fld" style="margin:4px 0"><span>🕯️ שמות ובקשות לתעודת הפרנס</span><textarea class="pyded" data-id="${p.id}" rows="2" placeholder="השמות שיוזכרו והבקשות (למשל: יעקב בן שרה לרפואה שלמה)">${esc(p.dedication||'')}</textarea></label>
    <button class="btn sm pydsave" data-id="${p.id}" style="margin:-2px 0 4px">💾 שמור שמות</button>
    <div class="txctl"><button class="dnpaid ${+p.paid?'yes':'no'} pypaid" data-id="${p.id}">${+p.paid?'שולם ✓':'לא שולם'}</button><button class="btn sm ghost pycert" data-id="${p.id}">🖨️ תעודת פרנס</button><button class="btn sm ghost pypic" data-id="${p.id}">${p.photo==='sent'?'📷 תמונת הקדשה נשלחה ✓':'📷 סמן: תמונת הקדשה נשלחה'}</button>${p.photo==='sent'?'<span class="fbchip on">✓ נשלחה תמונת הקדשה</span>':''}</div><label class="remset">🔔 תזכורת: <input type="date" class="pyrem" data-txt="${esc(p.date_text)}"></label></div>`;}).join('')||'<div class="hintxt">אין עדיין.</div>');
  el.querySelectorAll('.pyded').forEach(t=>{autoGrow(t);t.addEventListener('input',()=>autoGrow(t));t.onblur=async()=>{const p=d.parnes.find(x=>x.id==t.dataset.id);if(!p||(p.dedication||'')===t.value)return;p.dedication=t.value;await api('PUT','/api/parnes/'+p.id,{dedication:t.value});toast('נשמר ✓');};});
  el.querySelectorAll('.pydsave').forEach(b=>b.onclick=async()=>{const p=d.parnes.find(x=>x.id==b.dataset.id);const t=el.querySelector('.pyded[data-id="'+b.dataset.id+'"]');if(!p||!t)return;p.dedication=t.value;await api('PUT','/api/parnes/'+p.id,{dedication:t.value});toast('נשמר ✓');});
  el.querySelectorAll('.pyamt').forEach(inp=>inp.onchange=async()=>{const p=d.parnes.find(x=>x.id==inp.dataset.id);if(!p)return;p.amount=inp.value.trim();await api('PUT','/api/parnes/'+p.id,{amount:p.amount});renderParnesEdit(d);toast('סכום עודכן ✓');});
  el.querySelectorAll('.pykind').forEach(sel=>sel.onchange=async()=>{const p=d.parnes.find(x=>x.id==sel.dataset.id);if(!p)return;p.kind=sel.value;await api('PUT','/api/parnes/'+p.id,{kind:p.kind});renderParnesEdit(d);toast('סוג עודכן ✓');});
  const pySaveDate=async(p)=>{p.date_text=heDay(+p.day)+" "+p.month;await api('PUT','/api/parnes/'+p.id,{day:+p.day,month:p.month,date_text:p.date_text,hyear:p.hyear});renderParnesEdit(d);toast('יום עודכן ✓');};
  el.querySelectorAll('.pymon').forEach(sel=>sel.onchange=async()=>{const p=d.parnes.find(x=>x.id==sel.dataset.id);if(!p)return;p.month=sel.value;await pySaveDate(p);});
  el.querySelectorAll('.pyday').forEach(sel=>sel.onchange=async()=>{const p=d.parnes.find(x=>x.id==sel.dataset.id);if(!p)return;p.day=+sel.value;await pySaveDate(p);});
  el.querySelectorAll('.pyyr').forEach(sel=>sel.onchange=async()=>{const p=d.parnes.find(x=>x.id==sel.dataset.id);if(!p)return;p.hyear=sel.value;await api('PUT','/api/parnes/'+p.id,{hyear:p.hyear});renderParnesEdit(d);toast('שנה עודכנה ✓');});
  el.querySelectorAll('.pypaid').forEach(b=>b.onclick=async()=>{const p=d.parnes.find(x=>x.id==b.dataset.id);p.paid=+p.paid?0:1;await api('PUT','/api/parnes/'+p.id,{paid:p.paid});renderParnesEdit(d);toast(+p.paid?'סומן כשולם ✓':'בוטל הסימון');});
  el.querySelectorAll('.pycert').forEach(b=>b.onclick=()=>{const p=d.parnes.find(x=>x.id==b.dataset.id);openParnesCert(d,p);});
  el.querySelectorAll('.pypic').forEach(b=>b.onclick=async()=>{const p=d.parnes.find(x=>x.id==b.dataset.id);p.photo=p.photo==='sent'?'':'sent';await api('PUT','/api/parnes/'+p.id,{photo:p.photo});renderParnesEdit(d);toast(p.photo==='sent'?'סומן — תמונת הקדשה נשלחה ✓':'בוטל הסימון');});
  el.querySelectorAll('.del').forEach(b=>b.onclick=async()=>{const p=d.parnes.find(x=>x.id==b.dataset.del);await api('DELETE','/api/parnes/'+b.dataset.del);d.parnes=d.parnes.filter(x=>x.id!=b.dataset.del);if(p){const note='פרנס יום '+(p.date_text||'')+' — הכן הדפסה וצור קשר';d.tasks=(d.tasks||[]).filter(x=>!(x.kind==='parnes'&&x.note===note));}checkReminders();renderParnesEdit(d);});
  el.querySelectorAll('.pyrem').forEach(x=>x.onchange=async()=>{if(!x.value)return;const r=await api('POST','/api/task',{donor_id:d.id,due_date:x.value,kind:'parnes',note:x.dataset.txt});d.tasks=d.tasks||[];d.tasks.push({id:r.id,donor_id:d.id,due_date:x.value,kind:'parnes',note:x.dataset.txt,done:0});toast('תזכורת פרנס נקבעה ✓');});
}

/* ---------- קוויטל (5 סוגים) ---------- */
const KVTYPES=[
  ['iz','קוויטל יששכר־זבולון','שותפי יששכר־זבולון'],
  ['101','קוויטל כל לילה','תורמי כל לילה (101)'],
  ['weekly','קוויטל שבועי','קבועים פחות מ-101'],
  ['occ','קוויטל מזדמן','לפי חודשים — נשמר לכל השנים'],
  ['klali','קוויטל כללי','הכל יחד להדפסה (בלי מזדמן)']
];
let kvSub=null;
function kvTypeLabel(t){return ({iz:'יש"ז','101':'כל לילה',weekly:'שבועי',occ:'מזדמן',klali:'כללי'})[t]||'כללי';}
// לאיזה קוויטל שייך התורם (לפי דרגה/קטגוריה) — למי שאמור להיות לו שם לתפילה
function kvMemberType(d){
  if(d.tier==='יששכר_זבולון')return 'iz';
  if(d.tier==='קוויטל_101')return '101';
  if(d.tier==='קוויטל_כללי')return 'klali';
  if(d.category==='קבוע'&&amtNum(d.amount)>0&&amtNum(d.amount)<101)return 'weekly';
  return null;
}
// מסומן בקוויטל אך אין לו עדיין שם לתפילה, ולא סומן "לא צריך"
function kvMissingList(){return DB.filter(d=>kvMemberType(d)&&!(d.prayers&&d.prayers.length)&&!(+d.kv_skip));}
// חיפוש שם על פני כל סוגי הקוויטל — בלי לבחור קטגוריה קודם
function renderKvSearch(){
  let entries=[];
  DB.forEach(d=>{(d.prayers||[]).forEach(p=>{entries.push({id:p.id,text:p.text,donor:(d.last+' '+d.first).trim(),last:d.last,did:d.id,kt:prayerKvType(p.tier,d)});});});
  UNLINKED.forEach(p=>{entries.push({id:p.id,text:p.text,donor:p.name||'—',last:(p.name||'').split(' ').slice(-1)[0],loose:true,kt:prayerKvType(p.tier,null)});});
  entries=entries.filter(e=>matchQ(e.donor+' '+e.text));
  entries.sort((a,b)=>(a.last||'').localeCompare(b.last||'','he'));
  view.innerHTML=`<div class="kbar"><button class="back" id="kvback">→ סוגי קוויטל</button><b>🔎 חיפוש בכל הקוויטל</b><span class="cnt2">(${entries.length})</span></div>
    <div class="hintxt" style="margin:0 2px 8px">מציג שמות מכל סוגי הקוויטל התואמים לחיפוש. לחץ על שם לעריכה — נשמר גם בכרטיס.</div>
    ${entries.map(e=>`<div class="kblock"><div class="who${e.did?' wholink':''}"${e.did?` data-did="${e.did}"`:''}>${esc(e.donor)} <span class="kvtag">${kvTypeLabel(e.kt)}</span>${e.did?' <span class="opencard">↗ כרטיס</span>':''}${e.loose?' <span class="loose">· לא משויך</span>':''}</div><div class="names" contenteditable="true" data-id="${e.id}">${esc(e.text)}</div></div>`).join('')||'<div class="empty">לא נמצאו שמות בקוויטל התואמים לחיפוש</div>'}`;
  const bk=document.getElementById('kvback');if(bk)bk.onclick=()=>{const qi=document.getElementById('q');if(qi)qi.value='';q='';render();};
  view.querySelectorAll('.who[data-did]').forEach(w=>w.onclick=()=>openDonor(DB.find(x=>x.id==w.dataset.did),'kvittel'));
  bindKvEdit();
}
function renderKvittel(){
  chips.innerHTML='';
  if(!kvSub){
    if(q) return renderKvSearch();   // יש חיפוש — הצג תוצאות מכל הסוגים ישירות
    const miss=kvMissingList().length;
    view.innerHTML=`<div class="cnt">בחר סוג קוויטל <small style="color:var(--muted)">· או חפש שם למעלה כדי לדלג ישר לתוצאות</small></div>
      ${miss?`<button class="btn kvmissbtn" id="kvMissBtn">🔴 חסרים שמות קוויטל — ${miss} לטיפול</button>`:''}
      <div class="kvmenu">${KVTYPES.map(([k,t,s])=>`<button class="kvbtn" data-k="${k}"><b>${t}</b><small>${s}</small></button>`).join('')}</div>`;
    view.querySelectorAll('.kvbtn').forEach(b=>b.onclick=()=>{kvSub=b.dataset.k;render();});
    const mb=document.getElementById('kvMissBtn');if(mb)mb.onclick=()=>{kvSub='missing';render();};
    return;
  }
  if(kvSub==='missing') return renderKvMissing();
  if(kvSub==='occ') return renderKvOcc();
  renderKvList(kvSub);
}
function renderKvMissing(){
  let list=kvMissingList().filter(d=>matchQ(d.last+' '+d.first+' '+d.english));
  list.sort((a,b)=>(a.last||'').localeCompare(b.last||'','he'));
  view.innerHTML=`<div class="kbar"><button class="back" id="kvback">→ סוגי קוויטל</button><b>🔴 חסרים שמות קוויטל</b><span class="cnt2">(${list.length})</span></div>
    <div class="hintxt" style="margin:0 2px 8px">מסומנים בקוויטל אך אין להם עדיין שם לתפילה. הקלד שם לתפילה — או לחץ ✓ אם התורם לא ביקש קוויטל (יוסר מהרשימה).</div>
    ${list.map(d=>`<div class="kblock kvmiss" data-id="${d.id}"><div class="who wholink" data-did="${d.id}">${esc((d.last+' '+d.first).trim())} <span class="kvtag">${kvTypeLabel(kvMemberType(d))}</span> <span class="opencard">↗ כרטיס</span></div>
      <div class="kvmissrow"><div class="names" contenteditable="true" data-newdid="${d.id}" data-ph="שם לתפילה — הקלד כאן"></div><button class="kvskip" data-skip="${d.id}" title="לא ביקש קוויטל">✓ לא ביקש</button></div></div>`).join('')||'<div class="empty">🎉 אין חסרים — לכל המסומנים בקוויטל יש שם</div>'}`;
  document.getElementById('kvback').onclick=()=>{kvSub=null;render();};
  view.querySelectorAll('.who[data-did]').forEach(w=>w.onclick=()=>openDonor(DB.find(x=>x.id==w.dataset.did),'kvittel'));
  view.querySelectorAll('.kvskip').forEach(b=>b.onclick=async()=>{const d=DB.find(x=>x.id==b.dataset.skip);if(!d)return;d.kv_skip=1;await api('PUT','/api/donor/'+d.id,{kv_skip:1});toast('סומן — לא צריך קוויטל ✓');renderKvMissing();});
  bindKvEdit();
}
function bindKvEdit(){
  view.querySelectorAll('.names[contenteditable]').forEach(n=>{n.onblur=async()=>{
    const id=n.dataset.id,newdid=n.dataset.newdid,nt=n.innerText.replace(/\s+$/,'');
    if(id){
      let ref=null;DB.forEach(d=>(d.prayers||[]).forEach(p=>{if(p.id==id)ref=p;}));if(!ref)ref=UNLINKED.find(p=>p.id==id);if(!ref||ref.text===nt)return;ref.text=nt;await api('PUT','/api/prayer/'+id,{text:nt});toast('נשמר ✓ (גם בכרטיס)');
    }else if(newdid&&nt){
      const d=DB.find(x=>x.id==newdid);if(!d)return;const r=await api('POST','/api/prayer',{donor_id:+newdid,text:nt,tier:d.tier||''});d.prayers=d.prayers||[];d.prayers.push({id:r.id,text:nt,tier:d.tier||''});n.dataset.id=r.id;delete n.dataset.newdid;toast('נוסף לקוויטל ✓ (גם בכרטיס)');if(kvSub==='missing')renderKvMissing();
    }
  };});
}
function prayerKvType(pt,d){
  d=d||{};
  if(pt==='יששכר_זבולון'||(!pt&&d.tier==='יששכר_זבולון'))return 'iz';
  if(pt==='קוויטל_101'||(!pt&&d.tier==='קוויטל_101'))return '101';
  if(pt==='שבועי'||(!pt&&d.category==='קבוע'&&amtNum(d.amount)>0&&amtNum(d.amount)<101))return 'weekly';
  if(d.category==='מזדמן'&&!d.tier)return 'occ';
  return 'other';
}
function renderKvList(type){
  let entries=[];
  DB.forEach(d=>{
    const prs=(d.prayers||[]);
    prs.forEach(p=>{const t=prayerKvType(p.tier,d);const inc=type==='klali'?(t!=='occ'):(t===type);if(inc)entries.push({id:p.id,text:p.text,donor:(d.last+' '+d.first).trim(),last:d.last,did:d.id});});
    // מסומן בקוויטל לפי דרגה אך בלי שם עדיין — הצג עם שמו כדי שלא ייעלם מהרשימה (אלא אם סומן "לא צריך")
    if(!prs.length&&!(+d.kv_skip)){const t=kvMemberType(d);const inc=t&&(type==='klali'?true:(t===type));if(inc)entries.push({id:null,newdid:d.id,text:'',donor:(d.last+' '+d.first).trim(),last:d.last,did:d.id,needname:true});}
  });
  UNLINKED.forEach(p=>{const t=prayerKvType(p.tier,null);const inc=type==='klali'?(t!=='occ'):(t===type);if(inc)entries.push({id:p.id,text:p.text,donor:p.name||'—',last:(p.name||'').split(' ').slice(-1)[0],loose:true});});
  entries=entries.filter(e=>matchQ(e.donor+' '+e.text));
  entries.sort((a,b)=>(a.last||'').localeCompare(b.last||'','he'));
  const title=KVTYPES.find(x=>x[0]===type)[1];
  view.innerHTML=`<div class="kbar"><button class="back" id="kvback">→ סוגי קוויטל</button><b>${title}</b><span class="cnt2">(${entries.length})</span><button class="print" onclick="window.print()">הדפס 🖨️</button></div>
    <div class="hintxt" style="margin:0 2px 8px">לתיקון: לחץ על השם, ערוך, ולחץ מחוץ לו — נשמר גם בכרטיס.</div>
    ${entries.map(e=>`<div class="kblock"><div class="who${e.did?' wholink':''}"${e.did?` data-did="${e.did}"`:''}>${esc(e.donor)}${e.did?' <span class="opencard">↗ כרטיס</span>':''}${e.needname?' <span class="kvtag">אין שם — הקלד כאן</span>':''}${e.loose?' <span class="loose">· לא משויך</span>':''}</div><div class="names" contenteditable="true" ${e.id?`data-id="${e.id}"`:`data-newdid="${e.newdid}"`}>${esc(e.text)}</div></div>`).join('')||'<div class="empty">אין שמות בקוויטל זה</div>'}`;
  document.getElementById('kvback').onclick=()=>{kvSub=null;render();};
  view.querySelectorAll('.who[data-did]').forEach(w=>w.onclick=()=>openDonor(DB.find(x=>x.id==w.dataset.did),'kvittel'));
  bindKvEdit();
}
function renderKvOcc(){
  const groups={},mdate={};
  DB.forEach(d=>{if(!(d.category==='מזדמן'&&!d.tier))return;(d.donations||[]).forEach(dn=>{const hm=dn.hmonth||'ללא תאריך';groups[hm]=groups[hm]||{};const pid=(d.prayers&&d.prayers[0])?d.prayers[0].id:null;groups[hm][d.id]={d,pid,text:(d.prayers&&d.prayers[0])?d.prayers[0].text:''};if(!mdate[hm]||(dn.date||'')>mdate[hm])mdate[hm]=dn.date||'';});});
  let months=Object.keys(groups).sort((a,b)=>(mdate[b]||'').localeCompare(mdate[a]||''));
  months=months.filter(hm=>matchQ(hm)||Object.values(groups[hm]).some(x=>matchQ(x.d.last+' '+x.d.first+' '+x.text)));
  view.innerHTML=`<div class="kbar"><button class="back" id="kvback">→ סוגי קוויטל</button><b>קוויטל מזדמן — לפי חודשים</b><button class="print" onclick="window.print()">הדפס 🖨️</button></div>
    ${months.map(hm=>{const list=Object.values(groups[hm]);return `<div class="kvmonth"><h3>🗓️ ${esc(hm)} <small>(${list.length})</small></h3>${list.map(x=>`<div class="kblock"><div class="who wholink" data-did="${x.d.id}">${esc((x.d.last+' '+x.d.first).trim())} <span class="opencard">↗ כרטיס</span></div>${x.pid?`<div class="names" contenteditable="true" data-id="${x.pid}">${esc(x.text)}</div>`:'<div class="hintxt">אין שם לתפילה — הוסף בכרטיס התורם</div>'}</div>`).join('')}</div>`;}).join('')||'<div class="empty">אין תרומות מזדמנות</div>'}`;
  document.getElementById('kvback').onclick=()=>{kvSub=null;render();};
  view.querySelectorAll('.who[data-did]').forEach(w=>w.onclick=()=>openDonor(DB.find(x=>x.id==w.dataset.did),'kvittel'));
  bindKvEdit();
}

/* ---------- פרנס יום + שלט ---------- */
let pyKind='parnes';
const PKINDS=[['parnes','🌙 פרנס לילה'],['coffee','☕ חדר קפה'],['breakfast','🍳 ארוחת בוקר']];
function parnesTaken(kind){const taken={};DB.forEach(d=>(d.parnes||[]).forEach(p=>{if((p.kind||'parnes')!==kind)return;if(p.month&&p.day)taken[p.month+'|'+p.day]={...p,donor:(d.last+' '+d.first).trim(),dref:d};}));return taken;}
function kindToggle(){return `<div class="ktoggle">${PKINDS.map(([k,l])=>`<button class="ktog ${pyKind===k?'on':''}" data-k="${k}">${l}</button>`).join('')}</div>`;}
function bindKindToggle(){view.querySelectorAll('.ktog').forEach(b=>b.onclick=()=>{pyKind=b.dataset.k;pyDay=null;render();});}
function renderParnes(){
  chips.innerHTML='';
  const taken=parnesTaken(pyKind);
  if(!pyMonth){
    view.innerHTML=kindToggle()+`<div class="cnt">בחר חודש לראות ולשבץ את 30 הימים</div>
      <div class="hmgrid">${HMORD.map(m=>{const cnt=Object.keys(taken).filter(k=>k.startsWith(m+'|')).length;return `<button class="hmbtn" data-m="${m}"><span>${m}</span>${cnt?`<span class="hmc">${cnt}</span>`:''}</button>`;}).join('')}</div>`;
    bindKindToggle();
    view.querySelectorAll('.hmbtn').forEach(b=>b.onclick=()=>{pyMonth=b.dataset.m;pyDay=null;render();});
    return;
  }
  const days=[];for(let i=1;i<=30;i++)days.push(i);
  view.innerHTML=kindToggle()+`<div class="pbar"><button class="back" id="pmback">→ כל החודשים</button><b style="margin-inline-start:10px;font-size:1.15rem">חודש ${pyMonth}</b></div>
    <div class="dlegend"><span class="lg full"></span>מאושר <span class="lg sugg"></span>הצעה <span class="lg free"></span>פנוי</div>
    <div class="daygrid">${days.map(n=>{const t=taken[pyMonth+'|'+n];const cls=t?(t.status==='suggested'?'sugg':'full'):'free';return `<button class="daycell ${cls} ${pyDay===n?'sel':''}" data-d="${n}"><span class="dn">${heDay(n)}</span>${t?`<span class="dnm">${esc(t.donor.split(' ')[0])}</span>`:'<span class="dplus">+</span>'}</button>`;}).join('')}</div>
    <div id="daypanel"></div>`;
  bindKindToggle();
  document.getElementById('pmback').onclick=()=>{pyMonth=null;pyDay=null;render();};
  view.querySelectorAll('.daycell').forEach(b=>b.onclick=()=>{pyDay=+b.dataset.d;render();});
  if(pyDay)renderDayPanel(taken);
}
function renderDayPanel(taken){
  const panel=document.getElementById('daypanel');if(!panel)return;
  const t=taken[pyMonth+'|'+pyDay],dtext=heDay(pyDay)+" "+pyMonth;
  if(t){
    const sugg=t.status==='suggested';
    const dpcur=curSym(t.dref||{});
    panel.innerHTML=`<div class="sec"><h3>${sugg?'🔵 הצעה':'🟢 מאושר'} · ${esc(dtext)}</h3>
      <div class="remitem ${sugg?'':'given'}"><div class="ri"><b>${esc(t.donor)}</b>${t.amount?(' <b style="color:var(--yes)">· '+dpcur+esc(t.amount)+'</b>'):''}</div></div>
      ${sugg?'<div class="hintxt">הצעה — פנה אליו האם לעשות לו גם השנה. אם הסכים, אשר.</div>':''}
      <label class="fld" style="margin:6px 0"><span>🕯️ שמות ובקשות לתעודה</span><textarea id="dp_ded_edit" rows="2" placeholder="השמות שיוזכרו והבקשות">${esc(t.dedication||'')}</textarea></label>
      <button class="btn sm" id="dp_ded_save" style="margin-bottom:6px">💾 שמור שמות</button>
      <div class="hintxt" style="font-size:.78rem">לשינוי היום — מחק כאן ושבץ ליום אחר.</div>
      <div class="avfiles">${(t.files||[]).map(fileChip).join('')}<label class="filebtn">📷 העלה תמונת הקדשה<input type="file" accept="image/*,application/pdf" class="pyupload" hidden></label></div>
      <div class="addrow">${sugg?'<button class="btn sm" id="dpconfirm" style="background:var(--yes)">✅ אישר — עבור למאושר</button>':''}<button class="btn sm" id="dpopen">📋 כרטיס</button><button class="btn sm ghost" id="dpkv">🕯️ קוויטל</button><button class="btn sm" id="dpprint">🖨️ תעודה</button><button class="del" id="dpdel">מחק</button></div></div>`;
    const dded=document.getElementById('dp_ded_edit');
    const ddedSave=async()=>{t.dedication=dded.value;const p=(t.dref&&t.dref.parnes||[]).find(x=>x.id==t.id);if(p)p.dedication=dded.value;await api('PUT','/api/parnes/'+t.id,{dedication:dded.value});toast('נשמר ✓');};
    dded.onblur=()=>{if((t.dedication||'')!==dded.value)ddedSave();};
    document.getElementById('dp_ded_save').onclick=ddedSave;
    if(sugg)document.getElementById('dpconfirm').onclick=async()=>{await api('PUT','/api/parnes/'+t.id,{status:'confirmed'});const p=(t.dref.parnes||[]).find(x=>x.id==t.id);if(p)p.status='confirmed';toast('אושר ✓ עבר למאושר');render();};
    panel.querySelector('.pyupload').onchange=e=>uploadFile('parnes',t.id,e.target,load);
    panel.querySelectorAll('.fdel').forEach(b=>b.onclick=async()=>{await api('DELETE','/api/file/'+b.dataset.fid);load();});
    document.getElementById('dpopen').onclick=()=>openDonor(t.dref);
    document.getElementById('dpkv').onclick=()=>openDonor(t.dref,'kvittel');
    document.getElementById('dpprint').onclick=()=>openParnesCert(t.dref,{...t,date_text:t.date_text||dtext});
    document.getElementById('dpdel').onclick=async()=>{await api('DELETE','/api/parnes/'+t.id);t.dref.parnes=(t.dref.parnes||[]).filter(x=>x.id!=t.id);const note='פרנס יום '+(t.date_text||dtext)+' — הכן הדפסה וצור קשר';t.dref.tasks=(t.dref.tasks||[]).filter(x=>!(x.kind==='parnes'&&x.note===note));checkReminders();render();toast('נמחק');};
  }else{
    panel.innerHTML=`<div class="sec"><h3>➕ שבץ ${PKINDS.find(k=>k[0]===pyKind)[1]} — ${esc(dtext)}</h3>
      <input id="dp_q" placeholder="חפש תורם לשיבוץ…" autocomplete="off">
      <button class="btn sm ghost" id="dp_new" style="margin-top:6px">➕ תורם חדש (אם לא קיים)</button>
      <div id="dp_res" class="dpres"></div>
      <div id="dp_form" style="display:none">
        <div class="chosen" id="dp_chosen"></div>
        <div class="addrow"><button type="button" class="btn sm ghost" id="dp_open">📋 פתח כרטיס</button><button type="button" class="btn sm ghost" id="dp_kv">🕯️ פתח קוויטל</button></div>
        <div class="hintxt">כדאי לבדוק את שם הקוויטל שלו — בדרך כלל רוצים שיזכירו אותו באותו לילה.</div>
        <label class="fld"><span>בקשה ללימוד הלילה / הקדשה</span><textarea id="dp_ded" rows="2"></textarea></label>
        <div class="two"><label class="fld"><span>סכום (רשות)</span><input id="dp_amt"></label>
          <label class="fld"><span>סוג</span><select id="dp_status"><option value="confirmed">🟢 מאושר</option><option value="suggested">🔵 הצעה</option></select></label></div>
        <button class="btn" id="dp_save">שבץ ללילה זה</button></div></div>`;
    const qi=document.getElementById('dp_q'),res=document.getElementById('dp_res');let chosen=null;
    const pickChosen=nd=>{chosen=nd;document.getElementById('dp_chosen').textContent='נבחר: '+(nd.last+' '+(nd.first||'')).trim();document.getElementById('dp_form').style.display='block';res.innerHTML='';qi.value=(nd.last+' '+(nd.first||'')).trim();};
    document.getElementById('dp_new').onclick=()=>openNewDonor(nd=>pickChosen(nd));
    qi.oninput=()=>{const s=norm(qi.value);if(!s){res.innerHTML='';return;}const m=DB.filter(d=>norm(d.last+' '+d.first+' '+d.english).includes(s)).slice(0,8);
      res.innerHTML=m.map(d=>`<div class="dpr" data-id="${d.id}">${esc(d.last)} ${esc(d.first)} ${d.tier==='יששכר_זבולון'?'· יש"ז':''}</div>`).join('');
      res.querySelectorAll('.dpr').forEach(x=>x.onclick=()=>{chosen=DB.find(y=>y.id==x.dataset.id);document.getElementById('dp_chosen').textContent='נבחר: '+chosen.last+' '+chosen.first;document.getElementById('dp_form').style.display='block';res.innerHTML='';qi.value=chosen.last+' '+chosen.first;});};
    document.getElementById('dp_open').onclick=()=>{if(chosen)openDonor(chosen);};
    document.getElementById('dp_kv').onclick=()=>{if(chosen)openDonor(chosen,'kvittel');};
    document.getElementById('dp_save').onclick=async()=>{if(!chosen){toast('בחר תורם');return;}const ded=document.getElementById('dp_ded').value.trim(),amt=document.getElementById('dp_amt').value.trim(),status=document.getElementById('dp_status').value;const r=await api('POST','/api/parnes',{donor_id:chosen.id,day:pyDay,month:pyMonth,date_text:dtext,dedication:ded,amount:amt,kind:pyKind,status});chosen.parnes=chosen.parnes||[];chosen.parnes.push({id:r.id,donor_id:chosen.id,day:pyDay,month:pyMonth,date_text:dtext,dedication:ded,amount:amt,kind:pyKind,status});toast('שובץ ✓');render();};
  }
}
function renderPlaque(){
  const p=plaque;
  view.innerHTML=`<div class="pbar"><button class="back" id="pback">→ חזרה</button><button class="print" onclick="window.print()">הדפס 🖨️</button></div>
    <div class="plaque"><div class="bsd">בס"ד</div>
      <div class="ptop">יהי רצון שזכות הלימודים והתפילות הנעשים כאן בכולל חצות בעת רצון הגדול של חצות הלילה עד הבוקר</div>
      <div class="pdate2">~ ${esc(p.date_text)} ~</div><div class="pyz">יהיו ויעמדו לזכות</div>
      <div class="pded2">${esc(p.dedication)}</div><div class="pfoot">כולל חצות · ${esc(p.donor)}</div></div>`;
  document.getElementById('pback').onclick=()=>{plaque=null;render();};
}

/* ---------- לא עבר ---------- */
function renderMissed(){
  const q1=DB.filter(d=>matchQ(d.last+' '+d.first+' '+d.english));
  const missed=q1.filter(d=>gaps(d.months).length>0).sort((a,b)=>gaps(b.months).length-gaps(a.months).length);
  const debts=[];q1.forEach(d=>(d.pledges||[]).forEach(p=>{if(p.status!=='נתן')debts.push({d,p});}));
  view.innerHTML=`
    <div class="misshead">🔴 חובות והתחייבויות שטרם שולמו (${debts.length})</div>
    <div class="list">${debts.map(({d,p})=>`<div class="rowc" data-id="${d.id}"><div><div class="nm">${esc(d.last)} <small>${esc(d.first)}</small></div><div class="miss">${esc(p.category)} ${p.amount?('· $'+esc(p.amount)):''} — טרם שולם</div></div><div class="meta"><span class="pill" style="background:var(--no-soft);color:var(--no)">חוב</span></div></div>`).join('')||'<div class="hintxt">אין חובות פתוחים 🎉</div>'}</div>
    <div class="misshead" style="margin-top:16px">🔴 חודשים שלא עברו (${missed.length})</div>
    <div class="list">${missed.map(d=>{const g=gaps(d.months);return `<div class="rowc" data-id="${d.id}"><div><div class="nm">${esc(d.last)} <small>${esc(d.first)}</small></div><div class="miss">לא עבר: ${g.map(i=>MON[i]).join(', ')}</div></div><div class="meta">${monthGrid(d.months)}</div></div>`;}).join('')||'<div class="hintxt">אין פספוסים 🎉</div>'}</div>`;
  view.querySelectorAll('.rowc').forEach(r=>r.onclick=()=>openDonor(DB.find(x=>x.id==r.dataset.id)));
}

/* ---------- אברכים (יששכר־זבולון) ---------- */
let avView='cards', avSort='last', avSearch='';
function avFirstAvreich(d){return ((d.partners||[]).filter(p=>p.active!=0)[0]||{}).avreich||'';}
function avSumAmt(d){return (d.partners||[]).filter(p=>p.active!=0).reduce((s,p)=>s+amtNum(p.amount),0);}
function sortIZ(list){const s=list.slice();
  if(avSort==='av') s.sort((a,b)=>(avFirstAvreich(a)||'תתת').localeCompare(avFirstAvreich(b)||'תתת','he'));
  else if(avSort==='amt') s.sort((a,b)=>avSumAmt(b)-avSumAmt(a));
  else s.sort((a,b)=>(a.last||'').localeCompare(b.last||'','he'));
  return s;}
function filterIZ(){const nq=norm(avSearch);
  return sortIZ(DB.filter(d=>d.tier==='יששכר_זבולון')
    .filter(d=>matchQ(d.last+' '+d.first+' '+(d.partners||[]).map(p=>p.avreich).join(' ')))
    .filter(d=>!nq||norm(d.last+' '+d.first+' '+(d.partners||[]).map(p=>p.avreich).join(' ')).includes(nq)));}
function renderAvTable(){
  view.innerHTML=`<div class="avbar noprint">
      <button class="back" id="avcards">→ חזרה לעריכה</button>
      <input id="avtsearch" class="avsearch" placeholder="🔍 חפש תורם או אברך…" value="${esc(avSearch)}" autocomplete="off">
      <select id="avtsort" class="avsortsel">
        <option value="last">מיון: תורם (א-ב)</option>
        <option value="av">מיון: אברך (א-ב)</option>
        <option value="amt">מיון: סכום (גבוה→נמוך)</option>
      </select>
      <button class="print" onclick="window.print()">הדפס 🖨️</button></div>
    <div class="avtabtitle"><b id="avttl"></b></div>
    <div style="overflow-x:auto"><table class="avtable"><thead><tr>
      <th class="avsort-th" data-s="last">תורם (זבולון)</th><th class="avsort-th" data-s="av">אברך</th>
      <th>תאריך התחלה</th><th class="avsort-th" data-s="amt">סכום</th><th>איך משולם</th><th>שטר</th><th>הערות</th></tr></thead>
    <tbody id="avtbody"></tbody></table></div>`;
  const sortSel=document.getElementById('avtsort'); sortSel.value=avSort;
  function paintRows(){
    const izd=filterIZ();const rows=[];izd.forEach(d=>{const act=(d.partners||[]).filter(p=>p.active!=0);if(act.length)act.forEach(p=>rows.push({d,p}));else rows.push({d,p:null});});
    document.getElementById('avttl').textContent=`טבלת יששכר־זבולון (${rows.length})`;
    document.getElementById('avtbody').innerHTML=rows.map(({d,p})=>{const izf=(d.files||[]).filter(f=>f.kind==='iz'||!f.kind);const shtar=izf.length?`<a href="/api/file/${izf[0].id}" target="_blank" rel="noopener">📄 צפה</a>`:'';return `<tr><td><span class="avnamelink" data-id="${d.id}">${esc(d.last+' '+d.first)}</span></td><td>${esc(p?p.avreich:'—')}</td><td>${esc(p?(p.start_date||''):'')}</td><td>${esc(p?(p.amount||''):'')}</td><td>${esc(p?chLabel(p.method):'')}</td><td>${shtar}</td><td>${esc(p?(p.note||''):'')}</td></tr>`;}).join('');
    view.querySelectorAll('.avnamelink').forEach(b=>b.onclick=()=>openDonor(DB.find(x=>x.id==b.dataset.id)));
    view.querySelectorAll('.avsort-th').forEach(th=>th.classList.toggle('on',th.dataset.s===avSort));
  }
  document.getElementById('avcards').onclick=()=>{avView='cards';render();};
  document.getElementById('avtsearch').oninput=e=>{avSearch=e.target.value;paintRows();};
  sortSel.onchange=()=>{avSort=sortSel.value;paintRows();};
  view.querySelectorAll('.avsort-th').forEach(th=>th.onclick=()=>{avSort=th.dataset.s;sortSel.value=avSort;paintRows();});
  paintRows();
}
function renderAvreich(){
  chips.innerHTML='';
  if(avView==='table') return renderAvTable();
  const totalAv=DB.reduce((s,d)=>s+(d.partners||[]).filter(p=>p.active!=0).length,0);
  view.innerHTML=`<div class="avbar">
      <input id="avsearch" class="avsearch" placeholder="🔍 חפש תורם או אברך…" value="${esc(avSearch)}" autocomplete="off">
      <select id="avsort" class="avsortsel">
        <option value="last">מיון: תורם (א-ב)</option>
        <option value="av">מיון: אברך (א-ב)</option>
        <option value="amt">מיון: סכום (גבוה→נמוך)</option>
      </select>
      <button class="btn sm" id="avtablebtn">🖨️ טבלה</button></div>
    <div class="cnt" id="avcnt"></div>
    <div class="avlist" id="avlistwrap"></div>`;
  const sortSel=document.getElementById('avsort'); sortSel.value=avSort;
  const searchEl=document.getElementById('avsearch');
  function paintList(){
    const izd=filterIZ();
    document.getElementById('avcnt').innerHTML=`${izd.length} תורמי יששכר־זבולון · ${totalAv} אברכים פעילים · טור אברך / תאריך / סכום / הערות`;
    document.getElementById('avlistwrap').innerHTML=izd.map(d=>{const act=(d.partners||[]).filter(p=>p.active!=0),hist=(d.partners||[]).filter(p=>p.active==0);
      return `<div class="avrow"><div class="avtop"><b class="avnamelink" data-id="${d.id}" title="פתח כרטיס">${esc(d.last)} ${esc(d.first)}</b>${act.length>1?`<span class="avcount">${act.length} אברכים</span>`:''}<span class="avsp"></span><button class="chip avpay" data-id="${d.id}">💰 תשלומים</button><button class="chip avhist" data-id="${d.id}">🕘 היסטוריה${hist.length?' ('+hist.length+')':''}</button><button class="chip avopen" data-id="${d.id}">כרטיס</button></div>
        <div class="avps">${act.length?act.map(p=>avPartnerRow(p)).join(''):'<div class="hintxt">אין אברך פעיל כרגע</div>'}</div>
        <button class="btn sm avadd" data-id="${d.id}">➕ הוסף אברך</button>
        <div class="avfiles">${(d.files||[]).map(fileChip).join('')}<label class="filebtn">📎 העלה שטר הסכם (PDF)<input type="file" accept="application/pdf,image/*" class="izupload" data-id="${d.id}" hidden></label></div></div>`;}).join('')||'<div class="empty">אין תוצאות</div>';
    view.querySelectorAll('.izupload').forEach(inp=>inp.onchange=()=>uploadFile('iz',+inp.dataset.id,inp,load));
    view.querySelectorAll('.fdel').forEach(b=>b.onclick=async()=>{await api('DELETE','/api/file/'+b.dataset.fid);load();});
    view.querySelectorAll('.avopen').forEach(b=>b.onclick=()=>openDonor(DB.find(x=>x.id==b.dataset.id)));
    view.querySelectorAll('.avnamelink').forEach(b=>b.onclick=()=>openDonor(DB.find(x=>x.id==b.dataset.id)));
    view.querySelectorAll('.avpay').forEach(b=>b.onclick=()=>showPayments(DB.find(x=>x.id==b.dataset.id)));
    view.querySelectorAll('.avhist').forEach(b=>b.onclick=()=>showAvHist(DB.find(x=>x.id==b.dataset.id)));
    view.querySelectorAll('.avadd').forEach(b=>b.onclick=async()=>{const d=DB.find(x=>x.id==b.dataset.id),today=todayStr();const r=await api('POST','/api/partner',{donor_id:d.id,avreich:'',start_date:today});d.partners=d.partners||[];d.partners.push({id:r.id,donor_id:d.id,avreich:'',start_date:today,amount:'',note:'',active:1});renderAvreich();});
    bindAvFields();
  }
  document.getElementById('avtablebtn').onclick=()=>{avView='table';render();};
  searchEl.oninput=()=>{avSearch=searchEl.value;paintList();};
  sortSel.onchange=()=>{avSort=sortSel.value;paintList();};
  paintList();
}
function avPartnerRow(p){
  return `<div class="avp" data-pid="${p.id}">
    <div class="avmain"><input class="avf avname" data-k="avreich" value="${esc(p.avreich||'')}" placeholder="שם האברך">
      <div class="avamt"><span>$</span><input class="avf" data-k="amount" value="${esc(p.amount||'')}" placeholder="סכום"></div>
      <button class="avend" title="החלפת אברך — הקודם יישמר בהיסטוריה">🔄 החלפה</button></div>
    <div class="avsub"><select class="avf avmethod" data-k="method">${channelOpts(p.method)}</select>
      <input class="avf" data-k="start_date" value="${esc(p.start_date||'')}" placeholder="מתאריך (עברי)">
      <input class="avf" data-k="note" value="${esc(p.note||'')}" placeholder="הערות"></div></div>`;
}
function bindAvFields(){
  view.querySelectorAll('.avp').forEach(row=>{const pid=row.dataset.pid;
    row.querySelectorAll('.avf').forEach(inp=>inp.onchange=async()=>{const body={};body[inp.dataset.k]=inp.value;await api('PUT','/api/partner/'+pid,body);DB.forEach(d=>(d.partners||[]).forEach(p=>{if(p.id==pid)p[inp.dataset.k]=inp.value;}));toast('נשמר ✓');});
    row.querySelector('.avend').onclick=async()=>{const today=todayStr();await api('PUT','/api/partner/'+pid,{active:0,ended_date:today});DB.forEach(d=>(d.partners||[]).forEach(p=>{if(p.id==pid){p.active=0;p.ended_date=today;}}));renderAvreich();toast('הסתיים — עבר להיסטוריה');};});
}
function showPayments(d){
  const list=(d.donations||[]).slice().sort((a,b)=>(b.date||'').localeCompare(a.date||''));
  const tot=list.reduce((s,x)=>s+(amtNum(x.amount)),0);
  const rs=document.getElementById('remsheet'),remov=document.getElementById('remov');
  rs.innerHTML=`<button class="x" id="rx">✕</button><h2>💰 תשלומים — ${esc(d.last)} ${esc(d.first)}</h2>
    <div class="hintxt">סה"כ ${list.length} תשלומים · $${tot}</div>
    ${list.map(x=>`<div class="remitem"><div class="ri"><b style="color:var(--yes)">$${esc(x.amount)}</b> ${x.category?('· '+esc(x.category)):''}<br><small>${esc(x.date||'')}${x.hmonth?(' · '+esc(x.hmonth)):''}${x.method?(' · '+esc(x.method)):''}</small></div></div>`).join('')||'<div class="hintxt">עדיין אין תשלומים רשומים. נכנסים דרך "רישום תרומה" בכרטיס.</div>'}`;
  remov.classList.add('show');document.getElementById('rx').onclick=()=>remov.classList.remove('show');
}
function showAvHist(d){
  const hist=(d.partners||[]).filter(p=>p.active==0).sort((a,b)=>(b.start_date||'').localeCompare(a.start_date||''));
  const rs=document.getElementById('remsheet'),remov=document.getElementById('remov');
  rs.innerHTML=`<button class="x" id="rx">✕</button><h2>🕘 היסטוריית אברכים — ${esc(d.last)} ${esc(d.first)}</h2>
    ${hist.map(p=>`<div class="remitem"><div class="ri"><b>${esc(p.avreich||'—')}</b><br><small>התחיל: ${esc(p.start_date||'?')} · הסתיים: ${esc(p.ended_date||'?')} ${p.amount?('· $'+esc(p.amount)):''}${p.note?(' · '+esc(p.note)):''}</small></div></div>`).join('')||'<div class="hintxt">אין היסטוריה.</div>'}`;
  remov.classList.add('show');document.getElementById('rx').onclick=()=>remov.classList.remove('show');
}

/* ---------- קמפיינים ---------- */
function renderCamp(){
  const camps={};
  DB.forEach(d=>(d.pledges||[]).forEach(p=>{const k=p.category||'ללא';camps[k]=camps[k]||{given:0,pending:0,gsum:0,psum:0,rows:[]};const a=amtNum(p.amount),g=p.status==='נתן';if(g){camps[k].given++;camps[k].gsum+=a;}else{camps[k].pending++;camps[k].psum+=a;}camps[k].rows.push({name:(d.last+' '+d.first).trim(),amt:p.amount,given:g});}));
  const keys=Object.keys(camps).filter(k=>matchQ(k));
  view.innerHTML=`<div class="cnt">${keys.length} קמפיינים</div>`+(keys.map(k=>{const c=camps[k],t=c.given+c.pending,pct=t?Math.round(100*c.given/t):0;return `<div class="campc"><h3>${esc(k)}</h3><div class="csub">נתנו ${c.given} · טרם ${c.pending} · התקבל $${c.gsum} · צפוי $${c.psum}</div><div class="campbar"><i style="width:${pct}%"></i></div>${c.rows.sort((a,b)=>a.given-b.given).map(r=>`<div class="camprow ${r.given?'given':'pending'}"><span>${esc(r.name)}</span><span>$${esc(r.amt)} · ${r.given?'נתן ✓':'טרם ✗'}</span></div>`).join('')}</div>`;}).join('')||'<div class="empty">אין עדיין קמפיינים. הוסף התחייבות בכרטיס תורם.</div>');
}

/* ---------- משימות ---------- */
function renderTasksTab(){
  const today=todayStr();
  const opts=[['','הכל'],['charge','💳 לחייב'],['parnes','🌙 פרנס'],['prayer','🙏 תפילה'],['followup','📞 לחזור']];
  chips.innerHTML=opts.map(([k,l])=>`<button class="chip ${flt===k?'on':''}" data-k="${k}">${l}</button>`).join('');
  chips.querySelectorAll('.chip').forEach(c=>c.onclick=()=>{flt=c.dataset.k;render();});
  let all=[];
  DB.forEach(d=>(d.tasks||[]).forEach(t=>{if(t.done&&t.done!=0)return;all.push({...t,donor:(d.last+' '+d.first).trim(),dref:d});}));
  if(flt) all=all.filter(t=>t.kind===flt);
  all=all.filter(t=>matchQ(t.donor+' '+(t.note||'')));
  all.sort((a,b)=>(a.due_date||'9999').localeCompare(b.due_date||'9999'));
  const ics=location.origin+'/calendar.ics';
  view.innerHTML=`<div class="icsbox"><b>📅 חיבור אוטומטי ליומן Google</b><br>הוסף פעם אחת את הכתובת (Google Calendar → יומנים אחרים → מכתובת URL), וכל התזכורות ייכנסו ליומן אוטומטית:<span class="u" id="icsurl">${ics}</span><button class="btn sm" id="icscopy" style="margin-top:6px">העתק כתובת</button></div>
    <div class="cnt">${all.length} משימות · לפי תאריך קרוב</div><div class="list">${all.map((t,i)=>{
    const over=t.due_date&&t.due_date<today, icon=(KIND[t.kind]||'🔔').split(' ')[0], g=gcalLink(t,t.donor);
    return `<div class="rowc taskrow" data-i="${i}"><button class="tdone" data-done="${i}" title="בוצע">✓</button>
      <div><div class="nm">${icon} ${esc(t.donor)}</div><div class="miss2">${esc(t.note||'')}</div></div>
      <div class="meta"><span class="tdate ${over?'over':''}">${esc(t.due_date||'—')}</span>${g?`<a class="gcal" href="${g}" target="_blank" rel="noopener" onclick="event.stopPropagation()">ליומן</a>`:''}</div></div>`;
  }).join('')||'<div class="empty">אין משימות פתוחות 🎉</div>'}</div>`;
  document.getElementById('icscopy').onclick=()=>{navigator.clipboard&&navigator.clipboard.writeText(ics);toast('הכתובת הועתקה ✓');};
  view.querySelectorAll('.taskrow').forEach(r=>r.onclick=e=>{if(e.target.classList.contains('tdone')||e.target.classList.contains('gcal'))return;openDonor(all[r.dataset.i].dref);});
  view.querySelectorAll('.tdone').forEach(b=>b.onclick=async e=>{e.stopPropagation();const t=all[b.dataset.done];if(t.id){await api('PUT','/api/task/'+t.id,{done:1});}t.done=1;const d=t.dref;const lt=(d.tasks||[]).find(x=>x.id===t.id);if(lt)lt.done=1;toast('בוצע ✓');render();checkReminders();});
}

/* ---------- מזדמנים ---------- */
function renderOcc(){
  const list=OCC.filter(o=>matchQ(o.name+' '+o.detail));
  view.innerHTML=`<div class="cnt">${list.length} מזדמנים</div><div class="list">${list.map(o=>`<div class="rowc" style="cursor:default"><div><div class="nm">${esc(o.name)}</div><div class="en">${esc(o.detail)}</div></div><div class="meta"><span class="ph">${o.total?('$'+esc(o.total)):''}</span></div></div>`).join('')||'<div class="empty">אין תוצאות</div>'}</div>`;
}

load();
