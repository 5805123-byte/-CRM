'use strict';
let DB = [], tab = 'donors', flt = '', q = '';
const view = document.getElementById('view'), chips = document.getElementById('chips'),
      ov = document.getElementById('ov'), sheet = document.getElementById('sheet'),
      toastEl = document.getElementById('toast');
const TIERS = {'יששכר_זבולון':['יששכר־זבולון','ishz'],'קוויטל_101':['קוויטל 101','k101'],'קוויטל_כללי':['כללי','klali']};
const CATS = ['', 'קבוע', 'מזדמן'];

function esc(s){return (s==null?'':String(s)).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));}
function norm(s){return (s||'').replace(/["'`]/g,'').replace(/\s+/g,' ').trim();}
function toast(t){toastEl.textContent=t;toastEl.classList.add('show');setTimeout(()=>toastEl.classList.remove('show'),1400);}
function pill(t){if(!TIERS[t])return '';const[l,c]=TIERS[t];return `<span class="pill ${c}">${l}</span>`;}
function catPill(c){if(c==='קבוע')return '<span class="pill reg">קבוע</span>';if(c==='מזדמן')return '<span class="pill occ">מזדמן</span>';return '';}

async function api(method, url, body){
  const r = await fetch(url, {method, headers:{'Content-Type':'application/json'}, body: body?JSON.stringify(body):undefined});
  return r.json();
}
async function load(){
  const d = await api('GET','/api/data');
  DB = d.donors;
  document.getElementById('stat').textContent = DB.length + ' תורמים';
  render();
}

document.querySelectorAll('.tab').forEach(b=>b.onclick=()=>{
  tab=b.dataset.tab; document.querySelectorAll('.tab').forEach(x=>x.classList.toggle('on',x===b)); flt=''; render();
});
document.getElementById('q').oninput=e=>{q=e.target.value.trim();render();};
ov.onclick=e=>{if(e.target===ov)ov.classList.remove('show');};

function matchQ(s){return !q?true:norm(s).includes(norm(q));}
function render(){
  chips.innerHTML='';
  if(tab==='donors') return renderDonors();
  if(tab==='camp') return renderCamp();
  return renderParnes();
}

function renderDonors(){
  const opts=[['','הכל'],['קבוע','קבועים'],['מזדמן','מזדמנים'],['py','פרנס יום']];
  chips.innerHTML=opts.map(([k,l])=>`<button class="chip ${flt===k?'on':''}" data-k="${k}">${l}</button>`).join('');
  chips.querySelectorAll('.chip').forEach(c=>c.onclick=()=>{flt=c.dataset.k;render();});
  let list=DB.filter(d=>matchQ(d.last+' '+d.first+' '+d.phone+' '+d.business+' '+d.english));
  if(flt==='py') list=list.filter(d=>d.parnes&&d.parnes.length);
  else if(flt) list=list.filter(d=>d.category===flt);
  view.innerHTML=`<div class="cnt">${list.length} תורמים</div><div class="list">${list.map(d=>`
    <div class="rowc" data-id="${d.id}">
      <div><div class="nm">${esc(d.last)} <small>${esc(d.first)}</small></div>
      ${d.english?`<div class="en" dir="ltr">${esc(d.english)}</div>`:''}</div>
      <div class="meta">${d.parnes&&d.parnes.length?'<span class="pill py">🌙</span>':''}${catPill(d.category)}${pill(d.tier)}${d.phone?`<span class="ph">${esc(d.phone)}</span>`:''}</div>
    </div>`).join('')||'<div class="empty">אין תוצאות</div>'}</div>`;
  view.querySelectorAll('.rowc').forEach(r=>r.onclick=()=>openDonor(DB.find(x=>x.id==r.dataset.id)));
}

function openDonor(d){
  const sel=(cur)=>CATS.map(c=>`<option ${c===cur?'selected':''} value="${c}">${c||'— ללא —'}</option>`).join('');
  sheet.innerHTML=`<button class="x" id="cx">✕</button>
    <h2>${esc(d.last)} ${esc(d.first)}</h2>
    <div>${pill(d.tier)} ${catPill(d.category)}</div>
    <label class="fld"><span>קטגוריה</span><select id="f_category">${sel(d.category)}</select></label>
    <label class="fld"><span>עבור מה (מטרה)</span><input id="f_purpose" value="${esc(d.purpose)}"></label>
    <label class="fld"><span>סכום קבוע</span><input id="f_amount" value="${esc(d.amount)}"></label>
    <label class="fld"><span>טלפון</span><input id="f_phone" value="${esc(d.phone)}" dir="ltr"></label>
    <label class="fld"><span>שם באנגלית</span><input id="f_english" value="${esc(d.english)}" dir="ltr"></label>
    <label class="fld"><span>כתובת</span><input id="f_addr" value="${esc(d.addr)}"></label>
    <div class="sec"><h3>💳 התחייבויות / קמפיינים</h3><div id="pledges"></div>
      <div class="addrow"><input id="pl_cat" placeholder="קטגוריה (למשל חגי סוכות)"><input id="pl_amt" placeholder="סכום" style="max-width:90px"><button class="btn sm" id="pl_add">הוסף</button></div>
    </div>
    <div class="sec"><h3>🌙 פרנס יום</h3><div id="parnes"></div>
      <div class="addrow"><input id="py_date" placeholder="תאריך (ג' אב)"><input id="py_ded" placeholder="הקדשה"><button class="btn sm" id="py_add">הוסף</button></div>
    </div>`;
  ov.classList.add('show');
  document.getElementById('cx').onclick=()=>ov.classList.remove('show');
  // עריכת שדות — שמירה אוטומטית
  ['category','purpose','amount','phone','english','addr'].forEach(f=>{
    document.getElementById('f_'+f).onchange=async(e)=>{
      d[f]=e.target.value; await api('PUT','/api/donor/'+d.id,{[f]:e.target.value}); toast('נשמר ✓');
      if(f==='category') renderDonorsSilently();
    };
  });
  renderPledges(d); renderParnesEdit(d);
  document.getElementById('pl_add').onclick=async()=>{
    const cat=document.getElementById('pl_cat').value.trim(), amt=document.getElementById('pl_amt').value.trim();
    if(!cat)return;
    const r=await api('POST','/api/pledge',{donor_id:d.id,category:cat,amount:amt,status:'טרם'});
    d.pledges.push({id:r.id,donor_id:d.id,category:cat,amount:amt,status:'טרם'});
    document.getElementById('pl_cat').value='';document.getElementById('pl_amt').value='';renderPledges(d);toast('נוסף ✓');
  };
  document.getElementById('py_add').onclick=async()=>{
    const date=document.getElementById('py_date').value.trim(), ded=document.getElementById('py_ded').value.trim();
    if(!date)return;
    const r=await api('POST','/api/parnes',{donor_id:d.id,date_text:date,dedication:ded});
    d.parnes.push({id:r.id,donor_id:d.id,date_text:date,dedication:ded,amount:''});
    document.getElementById('py_date').value='';document.getElementById('py_ded').value='';renderParnesEdit(d);toast('נוסף ✓');
  };
}
function renderDonorsSilently(){ if(tab==='donors') renderDonors(); }

function renderPledges(d){
  const el=document.getElementById('pledges');
  el.innerHTML=(d.pledges||[]).map(p=>{
    const given=p.status==='נתן';
    return `<div class="pledge ${given?'given':'pending'}">
      <div class="pi"><b>${esc(p.category)}</b> ${p.amount?('· $'+esc(p.amount)):''}<br><small>${given?'נתן ✓':'טרם נתן'}</small></div>
      <button class="stbtn" data-id="${p.id}">${given?'נתן':'טרם'}</button>
      <button class="del" data-del="${p.id}">🗑</button></div>`;
  }).join('')||'<div style="color:var(--muted);font-size:.85rem">אין עדיין. הוסף למטה.</div>';
  el.querySelectorAll('.stbtn').forEach(b=>b.onclick=async()=>{
    const p=d.pledges.find(x=>x.id==b.dataset.id); p.status=p.status==='נתן'?'טרם':'נתן';
    await api('PUT','/api/pledge/'+p.id,p); renderPledges(d); toast('עודכן ✓');
  });
  el.querySelectorAll('.del').forEach(b=>b.onclick=async()=>{
    await api('DELETE','/api/pledge/'+b.dataset.del); d.pledges=d.pledges.filter(x=>x.id!=b.dataset.del); renderPledges(d);
  });
}
function renderParnesEdit(d){
  const el=document.getElementById('parnes');
  el.innerHTML=(d.parnes||[]).map(p=>`<div class="pledge given"><div class="pi"><b>${esc(p.date_text)}</b> ${p.amount?('· $'+esc(p.amount)):''}<br><small>${esc(p.dedication)}</small></div><button class="del" data-del="${p.id}">🗑</button></div>`).join('')||'<div style="color:var(--muted);font-size:.85rem">אין עדיין.</div>';
  el.querySelectorAll('.del').forEach(b=>b.onclick=async()=>{await api('DELETE','/api/parnes/'+b.dataset.del);d.parnes=d.parnes.filter(x=>x.id!=b.dataset.del);renderParnesEdit(d);});
}

function renderCamp(){
  const camps={};
  DB.forEach(d=>(d.pledges||[]).forEach(p=>{
    const k=p.category||'ללא'; camps[k]=camps[k]||{given:0,pending:0,gsum:0,psum:0,rows:[]};
    const amt=parseFloat(p.amount)||0; const given=p.status==='נתן';
    if(given){camps[k].given++;camps[k].gsum+=amt;}else{camps[k].pending++;camps[k].psum+=amt;}
    camps[k].rows.push({name:d.last+' '+d.first,amt:p.amount,given});
  }));
  const keys=Object.keys(camps).filter(k=>matchQ(k));
  view.innerHTML=`<div class="cnt">${keys.length} קמפיינים</div>`+ (keys.map(k=>{
    const c=camps[k],tot=c.given+c.pending,pct=tot?Math.round(100*c.given/tot):0;
    return `<div class="campc"><h3>${esc(k)}</h3>
      <div style="font-size:.85rem;color:var(--muted)">נתנו ${c.given} · טרם ${c.pending} · התקבל $${c.gsum} · צפוי $${c.psum}</div>
      <div class="campbar"><i style="width:${pct}%"></i></div>
      ${c.rows.sort((a,b)=>a.given-b.given).map(r=>`<div class="camprow ${r.given?'given':'pending'}"><span>${esc(r.name)}</span><span>$${esc(r.amt)} · ${r.given?'נתן ✓':'טרם ✗'}</span></div>`).join('')}
    </div>`;
  }).join('')||'<div class="empty">אין עדיין קמפיינים. הוסף התחייבות בכרטיס תורם.</div>');
}

const MON=['תשרי','חשון','כסלו','טבת','שבט','אדר','ניסן','אייר','סיון','תמוז','אב','אלול'];
function renderParnes(){
  let all=[];
  DB.forEach(d=>(d.parnes||[]).forEach(p=>all.push({...p,donor:d.last+' '+d.first})));
  all=all.filter(p=>matchQ((p.date_text||'')+' '+p.donor+' '+(p.dedication||'')));
  all.sort((a,b)=>(a.ord||99)-(b.ord||99)||(a.day||0)-(b.day||0));
  view.innerHTML=`<div class="cnt">${all.length} פרנסי יום</div>`+(all.map(p=>`
    <div class="campc"><h3 style="color:var(--gold)">${esc(p.date_text)}</h3>
      <div><b>${esc(p.donor)}</b> ${p.amount?('· $'+esc(p.amount)):''}</div>
      ${p.dedication?`<div style="color:var(--accent);font-weight:600;margin-top:3px">${esc(p.dedication)}</div>`:''}
    </div>`).join('')||'<div class="empty">אין עדיין. הוסף בכרטיס תורם.</div>');
}

load();
