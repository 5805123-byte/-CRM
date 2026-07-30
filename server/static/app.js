'use strict';
let DB = [], OCC = [], UNLINKED = [], tab = 'donors', flt = '', q = '', plaque = null, GLAST = 6;
const view = document.getElementById('view'), chips = document.getElementById('chips'),
      ov = document.getElementById('ov'), sheet = document.getElementById('sheet'),
      toastEl = document.getElementById('toast');
const TIERS = {'יששכר_זבולון':['יששכר־זבולון','ishz'],'קוויטל_101':['קוויטל 101','k101'],'קוויטל_כללי':['כללי','klali']};
const CATS = ['', 'קבוע', 'מזדמן', 'פרנס יום', 'בניין/הקדשה', 'מזדמן/חד-פעמי'];
const MON = ['ינ','פב','מר','אפ','מא','יו','יול','אג','ספ','אק','נו','דצ'];

function esc(s){return (s==null?'':String(s)).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));}
function norm(s){return (s||'').replace(/["'`]/g,'').replace(/\s+/g,' ').trim();}
function toast(t){toastEl.textContent=t;toastEl.classList.add('show');setTimeout(()=>toastEl.classList.remove('show'),1300);}
function pill(t){if(!TIERS[t])return '';const[l,c]=TIERS[t];return `<span class="pill ${c}">${l}</span>`;}
function catPill(c){if(c==='קבוע')return '<span class="pill reg">קבוע</span>';if(c==='מזדמן')return '<span class="pill occ">מזדמן</span>';return '';}
function matchQ(s){return !q?true:norm(s).includes(norm(q));}

async function api(m,u,b){const r=await fetch(u,{method:m,headers:{'Content-Type':'application/json'},body:b?JSON.stringify(b):undefined});return r.json();}
async function load(){
  const d = await api('GET','/api/data');
  DB = d.donors; OCC = d.occasional || []; UNLINKED = d.unlinked_prayers || [];
  GLAST = (function(){const c=[...Array(12)].map((_,i)=>DB.filter(x=>x.months&&x.months[i]==='p').length);const mx=Math.max(1,...c);let l=0;for(let i=0;i<12;i++)if(c[i]>=0.3*mx)l=i;return l;})();
  document.getElementById('stat').textContent = DB.length + ' תורמים';
  render();
}

document.querySelectorAll('.tab').forEach(b=>b.onclick=()=>{tab=b.dataset.tab;document.querySelectorAll('.tab').forEach(x=>x.classList.toggle('on',x===b));flt='';plaque=null;render();});
document.getElementById('q').oninput=e=>{q=e.target.value.trim();render();};
ov.onclick=e=>{if(e.target===ov)ov.classList.remove('show');};

function render(){
  chips.innerHTML='';
  if(tab==='donors') return renderDonors();
  if(tab==='tasks') return renderTasksTab();
  if(tab==='kvittel') return renderKvittel();
  if(tab==='parnes') return plaque?renderPlaque():renderParnes();
  if(tab==='missed') return renderMissed();
  if(tab==='camp') return renderCamp();
  if(tab==='occ') return renderOcc();
}

/* ---------- תורמים ---------- */
function renderDonors(){
  const opts=[['','הכל'],['קבוע','קבועים'],['מזדמן','מזדמנים'],['py','פרנס יום']];
  chips.innerHTML=opts.map(([k,l])=>`<button class="chip ${flt===k?'on':''}" data-k="${k}">${l}</button>`).join('');
  chips.querySelectorAll('.chip').forEach(c=>c.onclick=()=>{flt=c.dataset.k;render();});
  let list=DB.filter(d=>matchQ(d.last+' '+d.first+' '+d.phone+' '+d.business+' '+d.english));
  if(flt==='py') list=list.filter(d=>d.parnes&&d.parnes.length); else if(flt) list=list.filter(d=>d.category===flt);
  view.innerHTML=`<div class="cnt">${list.length} תורמים</div><div class="list">${list.map(d=>`
    <div class="rowc" data-id="${d.id}">
      <div><div class="nm">${esc(d.last)} <small>${esc(d.first)}</small></div>
      ${d.english?`<div class="en" dir="ltr">${esc(d.english)}</div>`:''}
      ${d.purpose?`<div class="purp">🎯 ${esc(d.purpose)}</div>`:''}</div>
      <div class="meta">${d.parnes&&d.parnes.length?'<span class="pill py">🌙</span>':''}${catPill(d.category)}${pill(d.tier)}${d.phone?`<span class="ph">${esc(d.phone)}</span>`:''}</div>
    </div>`).join('')||'<div class="empty">אין תוצאות</div>'}</div>`;
  view.querySelectorAll('.rowc').forEach(r=>r.onclick=()=>openDonor(DB.find(x=>x.id==r.dataset.id)));
}

function gaps(m){if(!m)return [];const f=m.indexOf('p');if(f<0)return[];const g=[];for(let i=f;i<=GLAST;i++)if(m[i]!=='p')g.push(i);return g;}
function monthGrid(m){if(!m)return '';const f=m.indexOf('p');return `<div class="mgrid">${MON.map((l,i)=>{let c;if(m[i]==='p')c='gp';else if(f>=0&&i>=f&&i<=GLAST)c='gx';else c='gn';return `<div class="mc ${c}"><span>${l}</span></div>`;}).join('')}</div>`;}

let cardTab='details';
function tierOpts(cur){return ['','יששכר_זבולון','קוויטל_101','קוויטל_כללי'].map(t=>`<option value="${t}" ${t===cur?'selected':''}>${t?({'יששכר_זבולון':'יששכר־זבולון','קוויטל_101':'קוויטל 101','קוויטל_כללי':'כללי'}[t]):'— ללא —'}</option>`).join('');}
function wireFields(d,flds){flds.forEach(fld=>{const el=document.getElementById('f_'+fld);if(!el)return;el.onchange=async e=>{d[fld]=e.target.value;await api('PUT','/api/donor/'+d.id,{[fld]:e.target.value});toast('נשמר ✓');if(fld==='last'||fld==='first'){document.getElementById('cardTitle').textContent=(d.last+' '+d.first).trim();}if(['last','first','tier','category'].includes(fld)&&tab==='donors')renderDonors();};});}

function openDonor(d){
  cardTab='details';
  const nopen=(d.tasks||[]).filter(t=>!t.done||t.done==0).length;
  sheet.innerHTML=`<button class="x" id="cx">✕</button>
    <h2 id="cardTitle">${esc(d.last)} ${esc(d.first)}</h2>
    <div class="cardsub">${catPill(d.category)} ${pill(d.tier)} ${d.english?`<span class="ensm" dir="ltr">${esc(d.english)}</span>`:''}</div>
    <div class="ctabs">
      <button class="ctab" data-c="details">פרטים</button>
      <button class="ctab" data-c="kvittel">🕯️ קוויטל</button>
      <button class="ctab" data-c="donations">💳 תרומות</button>
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
  if(cardTab==='contact') return cardContact(d,body);
}
function cardDetails(d,body){
  const sel=CATS.map(c=>`<option ${c===d.category?'selected':''} value="${c}">${c||'— ללא —'}</option>`).join('');
  const f=(k,v,dir)=>v?`<div class="rf"><div class="k">${k}</div><div class="v" ${dir?'dir="ltr"':''}>${esc(v)}</div></div>`:'';
  body.innerHTML=`${d.purpose?`<div class="purpose">🎯 עבור: ${esc(d.purpose)}</div>`:''}
    <div class="two"><label class="fld"><span>שם משפחה</span><input id="f_last" value="${esc(d.last)}"></label>
      <label class="fld"><span>שם פרטי</span><input id="f_first" value="${esc(d.first)}"></label></div>
    <label class="fld"><span>שם באנגלית</span><input id="f_english" value="${esc(d.english)}" dir="ltr"></label>
    <div class="two"><label class="fld"><span>דרגת קוויטל</span><select id="f_tier">${tierOpts(d.tier)}</select></label>
      <label class="fld"><span>קטגוריה</span><select id="f_category">${sel}</select></label></div>
    <label class="fld"><span>עבור מה (מטרה)</span><input id="f_purpose" value="${esc(d.purpose)}"></label>
    <label class="fld"><span>סכום קבוע</span><input id="f_amount" value="${esc(d.amount)}"></label>
    <div class="fld"><span>טלפונים</span><div id="phones" class="phones"></div></div>
    <label class="fld"><span>אימייל</span><input id="f_email" value="${esc(d.email)}" dir="ltr"></label>
    <label class="fld"><span>כתובת</span><input id="f_addr" value="${esc(d.addr)}"></label>
    <label class="fld"><span>עסק</span><input id="f_business" value="${esc(d.business)}"></label>
    ${f('ערוץ',d.channel)}${f('סטטוס תשלום',d.pay_status)}
    ${d.months?`<div class="rf" style="flex-direction:column;gap:6px"><div class="k">מפת חודשים${gaps(d.months).length?' · <b style="color:var(--no)">'+gaps(d.months).length+' לא עברו</b>':''}</div>${monthGrid(d.months)}</div>`:''}`;
  wireFields(d,['last','first','english','tier','category','purpose','amount','email','addr','business']);
  renderPhones(d);
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
function cardKvittel(d,body){
  body.innerHTML=`<div id="prayers"></div>
    <div class="addrow"><input id="pr_new" placeholder="שם לתפילה (למשל: יעקב בן שרה לרפואה שלמה)"><button class="btn sm" id="pr_add">הוסף</button></div>`;
  renderPrayers(d);
  document.getElementById('pr_add').onclick=async()=>{const t=document.getElementById('pr_new').value.trim();if(!t)return;const r=await api('POST','/api/prayer',{donor_id:d.id,text:t,tier:d.tier||''});d.prayers=d.prayers||[];d.prayers.push({id:r.id,text:t,tier:d.tier||''});document.getElementById('pr_new').value='';renderPrayers(d);toast('נוסף ✓');};
}
function cardDonations(d,body){
  const isIZ=d.tier==='יששכר_זבולון';
  body.innerHTML=`
    ${isIZ?`<div class="sec"><h3>🤝 יששכר־זבולון — האברך שהוא מחזיק</h3><div id="partners"></div>
      <div class="addrow"><input id="pa_name" placeholder="שם האברך"><button class="btn sm" id="pa_add">הוסף</button></div></div>`:''}
    <div class="sec"><h3>💵 חיוב תרומה</h3>
      <div class="two"><label class="fld"><span>סכום ($)</span><input id="dn_amt" placeholder="480"></label>
        <label class="fld"><span>קטגוריה</span><input id="dn_cat" value="${esc(d.purpose||'')}" placeholder="עבור מה"></label></div>
      <div class="two"><label class="fld"><span>אמצעי</span><select id="dn_method"><option>אשראי</option><option>המחאה</option><option>מזומן</option><option>העברה בנקאית</option><option>Authorize</option></select></label>
        <label class="fld"><span>תאריך</span><input id="dn_date" type="date"></label></div>
      <button class="btn" id="dn_add">➕ רשום חיוב</button>
      ${d.channel?`<div class="hintxt">ערוץ קבוע בתיק: ${esc(d.channel)}</div>`:''}</div>
    <div class="sec"><h3>📜 היסטוריית תרומות</h3><div id="donations"></div></div>
    <div class="sec"><h3>🌙 פרנס יום</h3><div id="parnes"></div>
      <div class="addrow"><input id="py_date" placeholder="תאריך (ג' אב)"><input id="py_ded" placeholder="הקדשה"><button class="btn sm" id="py_add">הוסף</button></div></div>
    <div class="sec"><h3>🎯 התחייבויות / קמפיינים</h3><div id="pledges"></div>
      <div class="addrow"><input id="pl_cat" placeholder="קטגוריה (למשל חגי סוכות)"><input id="pl_amt" placeholder="סכום" style="max-width:80px"><button class="btn sm" id="pl_add">הוסף</button></div></div>`;
  if(isIZ){renderPartners(d);document.getElementById('pa_add').onclick=async()=>{const n=document.getElementById('pa_name').value.trim();if(!n)return;const r=await api('POST','/api/partner',{donor_id:d.id,avreich:n});d.partners=d.partners||[];d.partners.push({id:r.id,avreich:n});document.getElementById('pa_name').value='';renderPartners(d);toast('נוסף ✓');};}
  renderDonations(d); renderParnesEdit(d); renderPledges(d);
  document.getElementById('dn_add').onclick=async()=>{const amt=document.getElementById('dn_amt').value.trim(),cat=document.getElementById('dn_cat').value.trim(),method=document.getElementById('dn_method').value,date=document.getElementById('dn_date').value;if(!amt)return;const r=await api('POST','/api/donation',{donor_id:d.id,amount:amt,category:cat,method:method,date:date});d.donations=d.donations||[];d.donations.unshift({id:r.id,donor_id:d.id,amount:amt,category:cat,method:method,date:date});document.getElementById('dn_amt').value='';renderDonations(d);toast('נרשם ✓');};
  document.getElementById('pl_add').onclick=async()=>{const cat=document.getElementById('pl_cat').value.trim(),amt=document.getElementById('pl_amt').value.trim();if(!cat)return;const r=await api('POST','/api/pledge',{donor_id:d.id,category:cat,amount:amt,status:'טרם'});d.pledges.push({id:r.id,donor_id:d.id,category:cat,amount:amt,status:'טרם'});document.getElementById('pl_cat').value='';document.getElementById('pl_amt').value='';renderPledges(d);toast('נוסף ✓');};
  document.getElementById('py_add').onclick=async()=>{const date=document.getElementById('py_date').value.trim(),ded=document.getElementById('py_ded').value.trim();if(!date)return;const r=await api('POST','/api/parnes',{donor_id:d.id,date_text:date,dedication:ded});d.parnes.push({id:r.id,donor_id:d.id,date_text:date,dedication:ded,amount:''});document.getElementById('py_date').value='';document.getElementById('py_ded').value='';renderParnesEdit(d);toast('נוסף ✓');};
}
function cardContact(d,body){
  body.innerHTML=`
    <div class="sec"><h3>📞 תיעוד קשר</h3><div id="clog"></div>
      <div class="addrow"><select id="cl_ch"><option>טלפון</option><option>אימייל</option><option>וואטסאפ</option><option>פגישה</option></select><input id="cl_date" type="date"></div>
      <textarea id="cl_sum" rows="2" placeholder="מה סוכם / תוכן השיחה" style="margin-top:6px"></textarea>
      <div class="addrow"><input id="cl_next" type="date" title="מתי לחזור"><button class="btn sm" id="cl_add">שמור</button></div>
      <div class="hintxt">התאריך התחתון = מתי לחזור אליו (נכנס ל"משימות")</div></div>
    <div class="sec"><h3>🙏 תאריכים להתפלל עליו</h3><div id="tlist"></div>
      <div class="addrow"><input id="tk_note" placeholder="על מה (ניתוח / פגישה / רפואה)"><input id="tk_date" type="date"><button class="btn sm" id="tk_add">הוסף</button></div></div>`;
  renderContacts(d); renderTasks(d);
  document.getElementById('cl_add').onclick=async()=>{const ch=document.getElementById('cl_ch').value,date=document.getElementById('cl_date').value,sum=document.getElementById('cl_sum').value.trim(),next=document.getElementById('cl_next').value;if(!sum&&!date)return;const r=await api('POST','/api/contact',{donor_id:d.id,channel:ch,date:date,summary:sum,next_date:next});d.contacts=d.contacts||[];d.contacts.unshift({id:r.id,channel:ch,date:date,summary:sum,next_date:next});if(next){d.tasks=d.tasks||[];d.tasks.push({donor_id:d.id,due_date:next,kind:'followup',note:sum.slice(0,80),done:0});}document.getElementById('cl_sum').value='';renderContacts(d);renderTasks(d);toast('נשמר ✓');};
  document.getElementById('tk_add').onclick=async()=>{const note=document.getElementById('tk_note').value.trim(),date=document.getElementById('tk_date').value;if(!date)return;const r=await api('POST','/api/task',{donor_id:d.id,due_date:date,kind:'prayer',note:note});d.tasks=d.tasks||[];d.tasks.push({id:r.id,donor_id:d.id,due_date:date,kind:'prayer',note:note,done:0});document.getElementById('tk_note').value='';renderTasks(d);toast('נוסף ✓');};
}
function renderDonations(d){
  const el=document.getElementById('donations');if(!el)return;const list=(d.donations||[]);
  const tot=list.reduce((s,x)=>s+(parseFloat(x.amount)||0),0);
  el.innerHTML=(list.length?`<div class="hintxt">סה"כ ${list.length} תרומות · $${tot}</div>`:'')+(list.map(x=>`<div class="pledge given"><div class="pi"><b>$${esc(x.amount)}</b> ${x.category?('· '+esc(x.category)):''}<br><small>${esc(x.date||'')} ${x.method?('· '+esc(x.method)):''}</small></div><button class="del" data-del="${x.id}">🗑</button></div>`).join('')||'<div class="hintxt">עדיין אין תרומות. מתחילים להזין מתחילת 2026.</div>');
  el.querySelectorAll('.del').forEach(b=>b.onclick=async()=>{await api('DELETE','/api/donation/'+b.dataset.del);d.donations=d.donations.filter(x=>x.id!=b.dataset.del);renderDonations(d);});
}
function renderPartners(d){
  const el=document.getElementById('partners');if(!el)return;
  el.innerHTML=(d.partners||[]).map(p=>`<div class="pledge"><div class="pi">👨‍🎓 <b>${esc(p.avreich)}</b>${p.note?('<br><small>'+esc(p.note)+'</small>'):''}</div><button class="del" data-del="${p.id}">🗑</button></div>`).join('')||'<div class="hintxt">עדיין לא הוזן. יתמלא מהאקסל של האברכים.</div>';
  el.querySelectorAll('.del').forEach(b=>b.onclick=async()=>{await api('DELETE','/api/partner/'+b.dataset.del);d.partners=d.partners.filter(x=>x.id!=b.dataset.del);renderPartners(d);});
}
function renderContacts(d){
  const el=document.getElementById('clog');if(!el)return;
  el.innerHTML=(d.contacts||[]).map(c=>`<div class="logrow"><div class="pi"><b>${esc(c.channel)}</b> <small>${esc(c.date||'')}</small>${c.next_date?(' · <span style="color:var(--no)">חזור: '+esc(c.next_date)+'</span>'):''}<br>${esc(c.summary||'')}</div><button class="del" data-del="${c.id}">🗑</button></div>`).join('')||'<div class="hintxt">אין עדיין תיעוד.</div>';
  el.querySelectorAll('.del').forEach(b=>b.onclick=async()=>{await api('DELETE','/api/contact/'+b.dataset.del);d.contacts=d.contacts.filter(x=>x.id!=b.dataset.del);renderContacts(d);});
}
function renderTasks(d){
  const el=document.getElementById('tlist');if(!el)return;const t=(d.tasks||[]).filter(x=>x.kind==='prayer');
  el.innerHTML=t.map(x=>`<div class="pledge pending"><div class="pi">🙏 <b>${esc(x.due_date||'')}</b> ${esc(x.note||'')}</div><button class="del" data-del="${x.id}">🗑</button></div>`).join('')||'<div class="hintxt">אין תאריכים.</div>';
  el.querySelectorAll('.del').forEach(b=>b.onclick=async()=>{await api('DELETE','/api/task/'+b.dataset.del);d.tasks=d.tasks.filter(x=>x.id!=b.dataset.del);renderTasks(d);});
}
function renderPledges(d){
  const el=document.getElementById('pledges');
  el.innerHTML=(d.pledges||[]).map(p=>{const g=p.status==='נתן';return `<div class="pledge ${g?'given':'pending'}"><div class="pi"><b>${esc(p.category)}</b> ${p.amount?('· $'+esc(p.amount)):''}<br><small>${g?'נתן ✓':'טרם נתן'}</small></div><button class="stbtn" data-id="${p.id}">${g?'נתן':'טרם'}</button><button class="del" data-del="${p.id}">🗑</button></div>`;}).join('')||'<div class="hintxt">אין עדיין. הוסף למטה.</div>';
  el.querySelectorAll('.stbtn').forEach(b=>b.onclick=async()=>{const p=d.pledges.find(x=>x.id==b.dataset.id);p.status=p.status==='נתן'?'טרם':'נתן';await api('PUT','/api/pledge/'+p.id,p);renderPledges(d);toast('עודכן ✓');});
  el.querySelectorAll('.del').forEach(b=>b.onclick=async()=>{await api('DELETE','/api/pledge/'+b.dataset.del);d.pledges=d.pledges.filter(x=>x.id!=b.dataset.del);renderPledges(d);});
}
function autoGrow(t){t.style.height='auto';t.style.height=(t.scrollHeight+6)+'px';}
function renderPrayers(d){
  const el=document.getElementById('prayers');
  el.innerHTML=(d.prayers||[]).map(p=>`<div class="prow"><textarea class="prtx" data-id="${p.id}">${esc(p.text)}</textarea><button class="del" data-del="${p.id}">🗑</button></div>`).join('')||'<div class="hintxt">אין שמות עדיין. הוסף למטה.</div>';
  el.querySelectorAll('.prtx').forEach(t=>{autoGrow(t);t.addEventListener('input',()=>autoGrow(t));t.onblur=async()=>{const p=d.prayers.find(x=>x.id==t.dataset.id);if(!p||p.text===t.value)return;p.text=t.value;await api('PUT','/api/prayer/'+p.id,{text:t.value});toast('נשמר ✓');};});
  el.querySelectorAll('.del').forEach(b=>b.onclick=async()=>{await api('DELETE','/api/prayer/'+b.dataset.del);d.prayers=d.prayers.filter(x=>x.id!=b.dataset.del);renderPrayers(d);toast('נמחק');});
}
function renderParnesEdit(d){
  const el=document.getElementById('parnes');
  el.innerHTML=(d.parnes||[]).map(p=>`<div class="pledge given"><div class="pi"><b>${esc(p.date_text)}</b> ${p.amount?('· $'+esc(p.amount)):''}<br><small>${esc(p.dedication)}</small></div><button class="del" data-del="${p.id}">🗑</button></div>`).join('')||'<div class="hintxt">אין עדיין.</div>';
  el.querySelectorAll('.del').forEach(b=>b.onclick=async()=>{await api('DELETE','/api/parnes/'+b.dataset.del);d.parnes=d.parnes.filter(x=>x.id!=b.dataset.del);renderParnesEdit(d);});
}

/* ---------- קוויטל ---------- */
function renderKvittel(){
  const order={'יששכר_זבולון':0,'קוויטל_101':1,'קוויטל_כללי':2};
  const opts=[['','הכל']].concat(Object.keys(TIERS).map(k=>[k,TIERS[k][0]]));
  chips.innerHTML=opts.map(([k,l])=>`<button class="chip ${flt===k?'on':''}" data-k="${k}">${l}</button>`).join('');
  chips.querySelectorAll('.chip').forEach(c=>c.onclick=()=>{flt=c.dataset.k;render();});
  let all=[];
  DB.forEach(d=>(d.prayers||[]).forEach(p=>{const tier=p.tier||d.tier||'';all.push({ref:p,text:p.text,tier,donor:(d.last+' '+d.first).trim(),last:d.last});}));
  UNLINKED.forEach(p=>{all.push({ref:p,text:p.text,tier:p.tier||'',donor:(p.name||'—'),last:(p.name||'').split(' ').slice(-1)[0],loose:true});});
  all=all.filter(p=>(!flt||p.tier===flt)&&matchQ(p.donor+' '+p.text));
  all.sort((a,b)=>(order[a.tier]??9)-(order[b.tier]??9)||(a.last||'').localeCompare(b.last||'','he'));
  const title=flt&&TIERS[flt]?('קוויטל '+TIERS[flt][0]):'קוויטל — כל השמות';
  view.innerHTML=`<div class="kbar"><b>${title}</b><span class="cnt2">(${all.length})</span><button class="print" onclick="window.print()">הדפס 🖨️</button></div>
    <div class="hintxt" style="margin:0 2px 8px">לתיקון: לחץ על השם, ערוך, ולחץ מחוץ לו — נשמר לבד.</div>
    ${all.map(p=>`<div class="kblock"><div class="who">${esc(p.donor)} · ${TIERS[p.tier]?TIERS[p.tier][0]:''}${p.loose?' <span class="loose">· לא משויך לכרטיס</span>':''}</div><div class="names" contenteditable="true" data-id="${p.ref.id}">${esc(p.text)}</div></div>`).join('')||'<div class="empty">אין שמות</div>'}`;
  view.querySelectorAll('.names[contenteditable]').forEach(n=>{n.onblur=async()=>{const item=all.find(x=>x.ref.id==n.dataset.id);const nt=n.innerText.replace(/\s+$/,'');if(!item||item.ref.text===nt)return;item.ref.text=nt;item.text=nt;await api('PUT','/api/prayer/'+n.dataset.id,{text:nt});toast('נשמר ✓');};});
}

/* ---------- פרנס יום + שלט ---------- */
function renderParnes(){
  let all=[];DB.forEach(d=>(d.parnes||[]).forEach(p=>all.push({...p,donor:(d.last+' '+d.first).trim()})));
  all=all.filter(p=>matchQ((p.date_text||'')+' '+p.donor+' '+(p.dedication||'')));
  all.sort((a,b)=>(a.ord||99)-(b.ord||99)||(a.day||0)-(b.day||0));
  view.innerHTML=`<div class="cnt">${all.length} פרנסי יום · לחץ על לילה לנוסח מודפס</div>${all.map((p,i)=>`
    <div class="pyc" data-i="${i}"><div class="pdate">${esc(p.date_text)}</div>
      <div class="pbody"><div class="nm">${esc(p.donor)} ${p.amount?('· $'+esc(p.amount)):''}</div>
      ${p.dedication?`<div class="ded">${esc(p.dedication)}</div>`:''}<div class="printhint">הדפס נוסח 🖨️</div></div></div>`).join('')||'<div class="empty">אין עדיין. הוסף בכרטיס תורם.</div>'}`;
  const list=all; view.querySelectorAll('.pyc').forEach(c=>c.onclick=()=>{plaque=list[c.dataset.i];render();});
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
  const list=DB.filter(d=>gaps(d.months).length>0&&matchQ(d.last+' '+d.first+' '+d.english)).sort((a,b)=>gaps(b.months).length-gaps(a.months).length);
  view.innerHTML=`<div class="cnt">${list.length} תורמים עם חודש שלא עבר</div><div class="list">${list.map(d=>{const g=gaps(d.months);return `<div class="rowc" data-id="${d.id}"><div><div class="nm">${esc(d.last)} <small>${esc(d.first)}</small></div><div class="miss">לא עבר: ${g.map(i=>MON[i]).join(', ')}</div></div><div class="meta">${monthGrid(d.months)}</div></div>`;}).join('')||'<div class="empty">אין פספוסים 🎉</div>'}</div>`;
  view.querySelectorAll('.rowc').forEach(r=>r.onclick=()=>openDonor(DB.find(x=>x.id==r.dataset.id)));
}

/* ---------- קמפיינים ---------- */
function renderCamp(){
  const camps={};
  DB.forEach(d=>(d.pledges||[]).forEach(p=>{const k=p.category||'ללא';camps[k]=camps[k]||{given:0,pending:0,gsum:0,psum:0,rows:[]};const a=parseFloat(p.amount)||0,g=p.status==='נתן';if(g){camps[k].given++;camps[k].gsum+=a;}else{camps[k].pending++;camps[k].psum+=a;}camps[k].rows.push({name:(d.last+' '+d.first).trim(),amt:p.amount,given:g});}));
  const keys=Object.keys(camps).filter(k=>matchQ(k));
  view.innerHTML=`<div class="cnt">${keys.length} קמפיינים</div>`+(keys.map(k=>{const c=camps[k],t=c.given+c.pending,pct=t?Math.round(100*c.given/t):0;return `<div class="campc"><h3>${esc(k)}</h3><div class="csub">נתנו ${c.given} · טרם ${c.pending} · התקבל $${c.gsum} · צפוי $${c.psum}</div><div class="campbar"><i style="width:${pct}%"></i></div>${c.rows.sort((a,b)=>a.given-b.given).map(r=>`<div class="camprow ${r.given?'given':'pending'}"><span>${esc(r.name)}</span><span>$${esc(r.amt)} · ${r.given?'נתן ✓':'טרם ✗'}</span></div>`).join('')}</div>`;}).join('')||'<div class="empty">אין עדיין קמפיינים. הוסף התחייבות בכרטיס תורם.</div>');
}

/* ---------- משימות ---------- */
function renderTasksTab(){
  const today=new Date().toISOString().slice(0,10);
  const opts=[['','הכל'],['followup','📞 לחזור'],['prayer','🙏 להתפלל']];
  chips.innerHTML=opts.map(([k,l])=>`<button class="chip ${flt===k?'on':''}" data-k="${k}">${l}</button>`).join('');
  chips.querySelectorAll('.chip').forEach(c=>c.onclick=()=>{flt=c.dataset.k;render();});
  let all=[];
  DB.forEach(d=>(d.tasks||[]).forEach(t=>{if(t.done&&t.done!=0)return;all.push({...t,donor:(d.last+' '+d.first).trim(),dref:d});}));
  if(flt) all=all.filter(t=>t.kind===flt);
  all=all.filter(t=>matchQ(t.donor+' '+(t.note||'')));
  all.sort((a,b)=>(a.due_date||'9999').localeCompare(b.due_date||'9999'));
  view.innerHTML=`<div class="cnt">${all.length} משימות · לפי תאריך קרוב</div><div class="list">${all.map((t,i)=>{
    const over=t.due_date&&t.due_date<today, icon=t.kind==='prayer'?'🙏':'📞';
    return `<div class="rowc taskrow" data-i="${i}"><button class="tdone" data-done="${i}" title="בוצע">✓</button>
      <div><div class="nm">${icon} ${esc(t.donor)}</div><div class="miss2">${esc(t.note||'')}</div></div>
      <div class="meta"><span class="tdate ${over?'over':''}">${esc(t.due_date||'—')}</span></div></div>`;
  }).join('')||'<div class="empty">אין משימות פתוחות 🎉</div>'}</div>`;
  view.querySelectorAll('.taskrow').forEach(r=>r.onclick=e=>{if(e.target.classList.contains('tdone'))return;openDonor(all[r.dataset.i].dref);});
  view.querySelectorAll('.tdone').forEach(b=>b.onclick=async e=>{e.stopPropagation();const t=all[b.dataset.done];if(t.id){await api('PUT','/api/task/'+t.id,{done:1});}t.done=1;const d=t.dref;const lt=(d.tasks||[]).find(x=>x.id===t.id);if(lt)lt.done=1;toast('בוצע ✓');render();});
}

/* ---------- מזדמנים ---------- */
function renderOcc(){
  const list=OCC.filter(o=>matchQ(o.name+' '+o.detail));
  view.innerHTML=`<div class="cnt">${list.length} מזדמנים</div><div class="list">${list.map(o=>`<div class="rowc" style="cursor:default"><div><div class="nm">${esc(o.name)}</div><div class="en">${esc(o.detail)}</div></div><div class="meta"><span class="ph">${o.total?('$'+esc(o.total)):''}</span></div></div>`).join('')||'<div class="empty">אין תוצאות</div>'}</div>`;
}

load();
