'use strict';
let DB = [], OCC = [], UNLINKED = [], GTASKS = [], CAMPAIGNS = [], BUILDING_ITEMS = [], TASKKINDS_C = [], tab = 'donors', flt = '', q = '', plaque = null, GLAST = 6, pyMonth = null, pyDay = null, HEBYEAR = '', donSort = 'last', taskWho = '', showDone = false;
// מאיר (אני, ריק) ואהרן — הקצאת משימות
function assigneeOpts(cur){return [['','מאיר'],['אהרן','אהרן']].map(([v,l])=>`<option value="${v}" ${v===(cur||'')?'selected':''}>${l}</option>`).join('');}
function curSym(d){ return (d && d.region==='il') ? '₪' : '$'; }
const GMON=['','ינואר','פברואר','מרץ','אפריל','מאי','יוני','יולי','אוגוסט','ספטמבר','אוקטובר','נובמבר','דצמבר'];
const GREGYEAR=String(new Date().getFullYear());
// תצוגת חודש לועזי לפי תאריך ("2026-07" → "יולי 2026") — התרומות הקבועות נגבות לפי חודש לועזי
// תאריך לתצוגה: יום מדויק אם יש ("16 ביוני 2026"), אחרת חודש בלבד
function gregLabel(dateStr){if(!dateStr)return '';const m=String(dateStr).match(/^(\d{4})-(\d{1,2})(?:-(\d{1,2}))?/);
  if(!m)return String(dateStr);
  return (m[3]?(+m[3]+' ב'):'')+GMON[+m[2]]+' '+m[1];}
function donorTotals(d){
  let all=0,year=0,pending=0;
  (d.donations||[]).forEach(x=>{const a=amtNum(x.amount);all+=a;if((x.date||'').slice(0,4)===GREGYEAR)year+=a;});
  (d.parnes||[]).forEach(x=>{const a=amtNum(x.amount);if(+x.paid)all+=a;else if(x.status!=='suggested')pending+=a;});   // נגבה→all · התחייבות→pending · הצעה עתידית→לא נספרת
  return {all,year,pending};
}
// חישוב יששכר־זבולון: התחייבות חודשית (סך האברכים) מול מה ששולם בפועל בחודשים שכבר שילם = החוב
// אברך שמוחזק "ביחד" — הסכום הרשום הוא הסכום המשותף לכל המחזיקים.
// חלקו של תורם אחד הוא הסכום חלקי מספר המחזיקים.
// כל המחזיקים של אותו אברך משותף
function jointGroup(p){
  const av=norm(p.avreich||''); const out=[]; if(!av)return out;
  (DB||[]).forEach(o=>(o.partners||[]).forEach(q=>{
    if(q.active!=0&&+q.joint&&norm(q.avreich||'')===av)out.push({d:o,p:q});}));
  return out;
}
function jointHolders(p){return Math.max(1,jointGroup(p).length);}
// חלקו של תורם באברך משותף:
// אם נקבע מי משלם בפועל (עסק אחד / כרטיס אחד) — כל הסכום נזקף למשלם, ולשאר 0.
// אם לא נקבע — כל אחד נושא חלק שווה.
function jointPayerId(p){const v=+(p.joint_payer||0);return v>0?v:0;}
function partnerMonthly(p){
  if(!+p.joint)return amtNum(p.amount);
  const pay=jointPayerId(p);
  if(pay)return (+p.donor_id===pay)?amtNum(p.amount):0;
  return amtNum(p.amount)/jointHolders(p);
}
function jointPayerName(p){const id=jointPayerId(p);const o=(DB||[]).find(x=>x.id===id);
  return o?((o.business||'').trim()||((o.last||'')+' '+(o.first||'')).trim()):'';}
function izSummary(d){
  const parts=(d.partners||[]).filter(p=>p.active!=0);
  // ההתחייבות החודשית = סכום האברכים. אם לא הוזן סכום לאברך — הסכום הקבוע שבכרטיס.
  const byav=parts.reduce((s,p)=>s+partnerMonthly(p),0);
  const fromCard=!byav&&d.tier==='יששכר_זבולון'&&amtNum(d.amount)>0;
  const monthly=byav||(fromCard?amtNum(d.amount):0);
  // אברך משותף: לכל מחזיק נספר חלקו בהתחייבות (ראה partnerMonthly), ולכן
  // גם התשלומים נספרים לכל אחד בנפרד — בלי לצרף את תשלומי השותפים.
  const izdon=(d.donations||[]).filter(x=>/יששכר|זבולון/.test(x.category||''));
  const paid=izdon.reduce((s,x)=>s+amtNum(x.amount),0);
  const codes=izdon.map(x=>{const m=(x.date||'').match(/^(\d{4})-(\d{2})/);return m?(+m[1])*12+(+m[2]):null;}).filter(v=>v!=null);
  const hasPay=codes.length>0;
  const span=hasPay?(Math.max(...codes)-Math.min(...codes)+1):0;
  const expected=monthly*span;
  const debt=expected-paid;
  // תשלומים שלא עוברים במערכת (מזומן / צ'ק ביד): מסמנים "שילם עד חודש X"
  // והחוב מחושב מאותו חודש ועד היום, לפי הסכום החודשי של אותו אברך.
  const nw=new Date(), nowCode=nw.getFullYear()*12+(nw.getMonth()+1);
  const thru=[]; let thruDebt=0;
  parts.forEach(p=>{const m=String(p.paid_thru||'').match(/^(\d{4})-(\d{2})/); if(!m)return;
    const months=Math.max(0,nowCode-((+m[1])*12+(+m[2]))), amt=amtNum(p.amount);
    thruDebt+=months*amt; thru.push({av:p.avreich||'אברך',thru:p.paid_thru,months:months,amt:amt,owe:months*amt});});
  const manual=String(d.iz_debt||'').trim()?amtNum(d.iz_debt):null;
  return {parts,monthly,paid,span,expected,debt,hasPay,fromCard,thru,thruDebt,manual};
}
const MONFULL=['ינואר','פברואר','מרץ','אפריל','מאי','יוני','יולי','אוגוסט','ספטמבר','אוקטובר','נובמבר','דצמבר'];
function fmtMonth(ym){const m=String(ym||'').match(/^(\d{4})-(\d{2})/);return m?(MONFULL[+m[2]-1]+' '+m[1]):'';}
// פירוק רשימת שותפים (תומך בכמה שותפים מופרדים בפסיק)
function pwList(p){const names=(p.partner_with||'').split(',').map(s=>s.trim()).filter(Boolean);const ids=(String(p.partner_with_id||'')).split(',').map(s=>s.trim());return names.map((nm,i)=>({name:nm,id:ids[i]||''}));}
// HTML של שמות השותפים — זיהוי אוטומטי (אותו אברך) + קישור ידני. כל אחד לחיץ אם מקושר לכרטיס
function coHolderNamesHtml(p){const l=avCoHolders(p);if(!l.length)return '';return ' <small class="cosp">🤝 בשותפות עם '+l.map(x=>x.id?`<span class="cosp2" data-did="${x.id}">${esc(x.name)} ↗</span>`:esc(x.name)).join(', ')+'</small>';}
// סכום כולל לאברך. "ביחד" (joint) = נותנים סכום אחד משותף → לא מחברים. אחרת = חלקים נפרדים → מחברים
function coHolderTotal(p){
  if(+p.joint)return amtNum(p.amount);   // סכום משותף — הוא כבר הסה"כ
  const av=norm(p.avreich||'');let total=amtNum(p.amount);
  (DB||[]).forEach(o=>{if(o.id==p.donor_id)return;(o.partners||[]).forEach(q=>{if(q.active==0)return;if(norm(q.avreich||'')===av&&!+q.joint)total+=amtNum(q.amount);});});
  return total;
}
// שותפויות הפוכות — כרטיסים אחרים שרשמו את התורם הזה כשותף מחזיק (לפי קישור או לפי שם שהוקלד)
function coHeldWith(d){
  const out=[];const dn=norm((d.last||'')+' '+(d.first||''));const dt=dn.split(' ').filter(t=>t.length>=2);
  (DB||[]).forEach(o=>{if(o.id===d.id)return;(o.partners||[]).forEach(p=>{if(p.active==0)return;
    const idlist=(String(p.partner_with_id||'')).split(',').map(s=>s.trim()).filter(Boolean);
    const linked=idlist.includes(String(d.id));
    const byname=!idlist.length&&p.partner_with&&dt.length&&dt.every(t=>norm(p.partner_with).includes(t));
    if(linked||byname)out.push({name:(o.last+' '+o.first).trim(),did:o.id,avreich:p.avreich,amount:p.amount,method:p.method});});});
  return out;
}
// חידוש שותפות יש"ז — מחזיר את החידוש הקרוב ביותר (בטווח התרעה) מבין האברכים הפעילים
function renewInfo(d){
  const today=new Date();today.setHours(0,0,0,0);let best=null;
  (d.partners||[]).filter(p=>p.active!=0&&p.renew_date).forEach(p=>{
    const rd=new Date(p.renew_date+'T00:00:00');const days=Math.round((rd-today)/86400000);
    if(days<=45){if(!best||days<best.days)best={days,date:p.renew_date,avreich:p.avreich};}});
  return best;
}
function fmtGreg(iso){if(!iso)return '';const p=iso.split('-');return p[2]+'/'+p[1]+'/'+p[0];}
function renewBanner(d){const r=renewInfo(d);if(!r)return '';
  const txt=r.days<0?`עברה שנה מתחילת השותפות (${fmtGreg(r.date)}) — לחדש וליצור תעודה חדשה`:`מתקרב סיום שנת שותפות (${fmtGreg(r.date)}${r.days>=0?' · בעוד '+r.days+' ימים':''}) — ליצור קשר לחידוש + תעודה`;
  return `<div class="renewbanner">🔴 חידוש יש"ז: ${esc(txt)}${r.avreich?(' · '+esc(r.avreich)):''}</div>`;
}
function izSummaryHTML(d){
  const act=(d.partners||[]).filter(p=>p.active!=0);
  const recip=coHeldWith(d);
  if(d.tier!=='יששכר_זבולון'&&!act.length&&!recip.length)return '';
  const s=izSummary(d),cur=curSym(d);
  const recipHtml=recip.length?('<div class="izrow-h">🤝 שותף ביש"ז (מחזיק יחד עם):</div>'+recip.map(r=>`<div class="izrow"><span class="cosp2" data-did="${r.did}">👥 ${esc(r.name)} — ${esc(r.avreich||'אברך')}</span><b>${cur}${amtNum(r.amount)}</b></div>`).join('')):'';
  const rows=s.parts.map(p=>{const tot=avCoHolders(p).length?coHolderTotal(p):0;const totHtml=(tot>amtNum(p.amount))?` <small class="cosptot">= סה"כ ${cur}${tot}</small>`:'';return `<div class="izrow"><span>👨‍🎓 ${esc(p.avreich||'—')}${p.method?(' <small>'+chBadgeRaw(p.method)+'</small>'):''}${coHolderNamesHtml(p)}${+p.joint?' <small class="jointbadge">🤝 משותף</small>':''}${totHtml}${p.paid_note?(' <small class="paidnote">💰 '+esc(p.paid_note)+'</small>'):''}${p.start_date?(' <small class="izstart">📅 '+esc(p.start_date)+'</small>'):''}${+p.joint&&jointHolders(p)>1?(' <small class="cosptot">'+(jointPayerId(p)?(jointPayerId(p)===d.id?('💳 אתה משלם את כל ה'+cur+amtNum(p.amount)):('💳 משלם: '+esc(jointPayerName(p)))):('חלקו מתוך '+cur+amtNum(p.amount)+' ל־'+jointHolders(p)+' מחזיקים'))+'</small>'):''}</span><b>${cur}${Math.round(partnerMonthly(p))}</b></div>`;}).join('')||'<div class="hintxt">לא הוזנו אברכים</div>';
  let debtLine;
  const thruHtml=s.thru.length?s.thru.map(t=>`<div class="izrow"><span>💵 ${esc(t.av)} — שולם עד ${esc(fmtMonth(t.thru))}${t.months?(' · חייב '+t.months+' '+(t.months===1?'חודש':'חודשים')):' · מעודכן'}</span><b>${t.owe?(cur+t.owe):'—'}</b></div>`).join(''):'';
  if(s.manual!=null) debtLine=(s.manual>0.5
      ?`<div class="izdebt owe">🔴 חוב שעודכן ידנית: ${cur}${Math.round(s.manual)}</div>`
      :`<div class="izdebt ok">🟢 עודכן ידנית — אין חוב</div>`);
  else if(s.thru.length) debtLine=(s.thruDebt>0.5
      ?`<div class="izdebt owe">🔴 חוב לפי "שולם עד": ${cur}${Math.round(s.thruDebt)}</div>`
      :`<div class="izdebt ok">🟢 מעודכן — אין חוב</div>`);
  else if(!s.hasPay) debtLine='<div class="hintxt">אין עדיין תשלומי יש"ז רשומים לחישוב חוב. אם הוא משלם במזומן — עדכן "שולם עד חודש" אצל האברך</div>';
  else if(s.debt>0.5) debtLine=`<div class="izdebt owe">🔴 חוב מוערך: ${cur}${Math.round(s.debt)}</div>`;
  else if(s.debt<-0.5) debtLine=`<div class="izdebt ok">🟢 מקדמה / עודף: ${cur}${Math.round(-s.debt)}</div>`;
  else debtLine=`<div class="izdebt ok">🟢 מעודכן — אין חוב</div>`;
  const mainHtml=(act.length||s.monthly)?`${rows}
    <div class="izrow tot"><span>התחייבות חודשית${s.fromCard?' <small class="izfromcard">לפי הסכום הקבוע בכרטיס</small>':''}</span><b>${cur}${Math.round(s.monthly)}</b></div>
    ${s.hasPay?`<div class="izrow"><span>שולם ב-2026 (${s.span} ${s.span===1?'חודש':'חודשים'})</span><b>${cur}${Math.round(s.paid)}</b></div>
    <div class="izrow"><span>צפוי לתקופה (${s.span}×${cur}${Math.round(s.monthly)})</span><b>${cur}${Math.round(s.expected)}</b></div>`:''}
    ${thruHtml}
    ${debtLine}`:'';
  return `<div class="izsum"><div class="izsum-t">🤝 יששכר־זבולון — סיכום</div>
    ${renewBanner(d)}
    ${mainHtml}
    ${recipHtml}
    ${d.iz_note?`<div class="iznote">📝 ${esc(d.iz_note)}</div>`:''}</div>`;
}
const HMORD = ['תשרי','חשון','כסלו','טבת','שבט','אדר','ניסן','אייר','סיון','תמוז','אב','אלול'];
function heDay(n){const ones=['','א','ב','ג','ד','ה','ו','ז','ח','ט'],tens=['','י','כ','ל'];let s;if(n===15)s='טו';else if(n===16)s='טז';else s=(tens[Math.floor(n/10)]||'')+(ones[n%10]||'');return s.length<=1?s+"'":s.slice(0,-1)+'"'+s.slice(-1);}
const view = document.getElementById('view'), chips = document.getElementById('chips'),
      ov = document.getElementById('ov'), sheet = document.getElementById('sheet'),
      toastEl = document.getElementById('toast');
const TIERS = {'יששכר_זבולון':['יששכר־זבולון','ishz'],'קוויטל_101':['כל לילה','k101'],'קוויטל_שבועי':['שבועי','wkly'],'קוויטל_כללי':['כללי','klali']};
const CATS = ['', 'קבוע', 'מזדמן', 'פרנס יום', 'בניין/הקדשה'];
// התווית שמוצגת לכל סוג התחייבות. הערך עצמו נשאר כפי שהוא בבסיס הנתונים
const CATLBL = {'':'— ללא —','מזדמן':'מזדמן / חד־פעמי'};
const catLabel=c=>CATLBL[c]||c;
// תדירות רלוונטית רק למי שיש לו התחייבות קבועה
const hasFreq=d=>!!(d&&['קבוע','פרנס יום','בניין/הקדשה'].includes(d.category||''));
// תדירות תרומה — לקבוע שאינו בהכרח חודשי
const FREQ = [['','חודשי'],['x2m','פעמיים בחודש'],['2m','כל חודשיים'],['3m','כל 3 חודשים (רבעוני)'],['4m','כל 4 חודשים'],['6m','פעמיים בשנה'],['1y','פעם בשנה'],['חגים','לחגים בלבד'],['משתנה','משתנה / לפי הצורך']];
function freqOpts(cur){return FREQ.map(([v,l])=>`<option value="${v}" ${v===(cur||'')?'selected':''}>${l}</option>`).join('');}
function freqLabel(v){const f=FREQ.find(x=>x[0]===v);return f&&f[0]?f[1]:'';}
const MON = ['ינ','פב','מר','אפ','מא','יו','יול','אג','ספ','אק','נו','דצ'];
const KIND = {charge:'🧾 לחייב',parnes:'🌙 פרנס יום',prayer:'🙏 לבקש שמות',followup:'📞 להתקשר',email:'📧 אימייל/וואטסאפ',verify:'💰 לבדוק שנגבה',card:'💳 לבדוק כרטיס',other:'🔔 אחר'};
// רשימת סוגי המשימה — משמשת בכל מקום שבו קובעים משימה
const TASKKINDS=[['followup','📞 להתקשר אליו'],['email','📧 לשלוח אימייל / וואטסאפ'],['verify','💰 לבדוק שנגבה'],['card','💳 לבדוק כרטיס'],['charge','🧾 לחייב'],['prayer','🙏 לבקש שמות לקוויטל'],['parnes','🌙 פרנס יום'],['other','🔔 אחר']];
// סוגי משימה שמאיר מגדיר בעצמו נשמרים כ־"c:שם הסוג"
const isCustKind=k=>String(k||'').slice(0,2)==='c:';
const custKind=k=>isCustKind(k)?String(k).slice(2):'';
function taskKindList(){return TASKKINDS.concat((TASKKINDS_C||[]).map(n=>['c:'+n,'📌 '+n]));}
function kindLabel(k){return KIND[k]||(isCustKind(k)?('📌 '+custKind(k)):'🔔');}
const taskKindOpts=sel=>taskKindList().map(([v,l])=>`<option value="${v}" ${v===sel?'selected':''}>${esc(l)}</option>`).join('')
  +'<option value="__new__">➕ סוג משימה חדש…</option>';
// כל תיבת סוג־משימה בדף מקבלת שדה טקסט להוספת סוג משלך + כפתור מחיקה לסוג אישי
function wireKindSel(sel){
  if(!sel||sel._kbox)return;
  const box=document.createElement('div'); box.className='tkindbox';
  box.innerHTML='<input class="tkindnew" placeholder="שם הסוג החדש… (למשל: לבדוק יששכר זבולון שלו)" style="display:none"><button type="button" class="btn sm tkinddel" title="מחק סוג זה" style="display:none">🗑</button>';
  const row=sel.closest('.two,.addrow,.fbrow')||sel;
  row.parentNode.insertBefore(box,row.nextSibling);
  sel._kbox=box;
  const inp=box.querySelector('.tkindnew'),del=box.querySelector('.tkinddel');
  const shw=()=>{const isnew=sel.value==='__new__',cust=isCustKind(sel.value);
    inp.style.display=isnew?'':'none'; del.style.display=cust?'':'none';
    box.style.display=(isnew||cust)?'flex':'none';};
  sel._kshw=shw;
  sel.addEventListener('change',()=>{shw();if(sel.value==='__new__')inp.focus();});
  inp.addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();kindValue(sel);}});
  inp.addEventListener('blur',()=>{if(inp.value.trim())kindValue(sel);});
  del.onclick=async()=>{const nm=custKind(sel.value); if(!nm)return;
    if(!confirm('למחוק את סוג המשימה "'+nm+'"? משימות קיימות לא ישתנו.'))return;
    await api('POST','/api/taskkinds',{name:nm,delete:1});
    TASKKINDS_C=(TASKKINDS_C||[]).filter(x=>x!==nm); refreshKindSels(); toast('הסוג נמחק');};
  shw();
}
function refreshKindSels(){document.querySelectorAll('select').forEach(s=>{
  if(!s._kbox)return; const cur=s.value; s.innerHTML=taskKindOpts();
  s.value=[...s.options].some(o=>o.value===cur)?cur:'other'; if(s._kshw)s._kshw();});}
// מחזיר את הסוג שנבחר; אם נכתב סוג חדש — שומר אותו קודם
async function kindValue(sel){
  if(!sel)return 'other';
  if(sel.value!=='__new__')return sel.value;
  const inp=sel._kbox?sel._kbox.querySelector('.tkindnew'):null;
  const nm=(inp?inp.value:'').trim().replace(/\s+/g,' ').slice(0,60);
  if(!nm){if(inp){inp.style.display='';inp.focus();}toast('כתוב את שם הסוג החדש');return '';}
  if(!(TASKKINDS_C||[]).includes(nm)){await api('POST','/api/taskkinds',{name:nm});TASKKINDS_C.push(nm);}
  if(inp)inp.value='';
  refreshKindSels(); sel.value='c:'+nm; if(sel._kshw)sel._kshw();
  return 'c:'+nm;
}
// ===== הכתבה קולית בעברית =====
// משתמש במנוע הדיבור של הדפדפן (Chrome/Android, Safari) — בלי שרת חיצוני ובלי עלות.
const SPR = window.SpeechRecognition || window.webkitSpeechRecognition || null;
const SRERR = {'not-allowed':'לא ניתנה הרשאה למיקרופון — אשר אותה בהגדרות הדפדפן',
  'service-not-allowed':'הדפדפן חסם את שירות ההכתבה','no-speech':'לא נשמע דיבור','audio-capture':'לא נמצא מיקרופון',
  'network':'אין חיבור לרשת להכתבה','aborted':''};
let SRACT=null;
// מאחד קטעי תמלול. אנדרואיד מחזיר את אותו משפט כמה פעמים — פעם כשלבים
// גדלים ("עכשיו" · "עכשיו קיבלת"), ופעם כניסוח מתוקן של אותו משפט עצמו.
// שני המקרים נראים כמו קטעים "סופיים" נפרדים, ולכן משווים ומחליפים במקום לחבר.
function _wrds(t){return String(t||'').toLowerCase().replace(/[^\u0590-\u05ffa-z0-9 ]/g,' ').split(/\s+/).filter(Boolean);}
function segSim(a,b){                      // כמה מהמילים משותפות — 0 עד 1
  const A=_wrds(a),B=_wrds(b); if(!A.length||!B.length)return 0;
  const bag={}; B.forEach(w=>bag[w]=(bag[w]||0)+1);
  let hit=0; A.forEach(w=>{if(bag[w]){bag[w]--;hit++;}});
  return hit/Math.max(A.length,B.length);
}
function joinSegs(list){
  const out=[];
  (list||[]).forEach(x=>{
    const t=String(x||'').replace(/\s+/g,' ').trim(); if(!t)return;
    const last=out.length?out[out.length-1]:'';
    if(last){
      const pref=t.indexOf(last)===0||last.indexOf(t)===0;          // שלב גדל של אותו משפט
      const same=_wrds(t).length>=4&&segSim(t,last)>=0.7;           // ניסוח חוזר של אותו משפט
      if(pref||same){out[out.length-1]=t.length>=last.length?t:last;return;}
    }
    out.push(t);
  });
  // רשת ביטחון: קטע ארוך שחוזר על עצמו ברצף — נמחק
  let t=out.join(' ');
  for(let k=0;k<8;k++){
    const n=t.replace(/(\S+(?:\s+\S+){1,60})\s+\1(?=\s|$)/g,'$1');
    if(n===t)break; t=n;
  }
  return t;
}
function startDictation(btn,el){
  const C=window.SpeechRecognition||window.webkitSpeechRecognition||null;
  if(!C){toast('הדפדפן הזה לא תומך בהכתבה קולית — נסה בכרום');return;}
  if(SRACT){stopDictation();return;}                       // לחיצה שנייה עוצרת
  const r=new C(); r.lang='he-IL'; r.continuous=true; r.interimResults=true;
  const base=(el.value||'').trim()?((el.value||'').trim()+' '):''; let fin='';
  const setv=v=>{el.value=v;el.dispatchEvent(new Event('input',{bubbles:true}));};
  r.onstart=()=>{SRACT=r;btn.classList.add('rec');btn.textContent='⏹';toast('🎤 מקליט — דבר בעברית. לחץ שוב לסיום');};
  // אנדרואיד מחזיר כל שלב של המשפט כתוצאה נפרדת ו"סופית":
  // "עכשיו" · "עכשיו קיבלת" · "עכשיו קיבלת את"… חיבור פשוט שלהן יוצר את
  // הכפילות. לכן שומרים כל תוצאה לפי מקומה, ומאחדים קטע שהוא המשך של קודמו.
  const seg=[];
  r.onresult=ev=>{
    for(let i=0;i<ev.results.length;i++)seg[i]=ev.results[i][0].transcript;
    fin=joinSegs(seg);
    setv((base+fin).replace(/\s+/g,' ').trim());};
  r.onerror=ev=>{const m=SRERR[ev.error]; if(m)toast(m); else if(ev.error)toast('הכתבה נכשלה: '+ev.error);};
  r.onend=()=>{SRACT=null;btn.classList.remove('rec');btn.textContent='🎤';
    const fixed=fixNames((base+fin).replace(/\s+/g,' ').trim());
    setv(fixed.text);
    if(fixed.hits.length)toast('תוקנו שמות: '+fixed.hits.join(', '));
    el.dispatchEvent(new Event('change',{bubbles:true}));
    try{el.focus();}catch(e){}};
  try{r.start();}catch(e){toast('לא הצלחתי להפעיל את המיקרופון');}
}
// מנוע הדיבור לא מכיר שמות משפחה של תורמים. אחרי ההכתבה מתקנים כל מילה
// שנשמעת בדיוק כמו שם משפחה שקיים אצלנו (אותו מפתח דמיון), ומדווחים מה תוקן.
let _NMIDX=null;
function nameIndex(){
  if(_NMIDX)return _NMIDX;
  const cnt={};
  (DB||[]).forEach(d=>['last','first'].forEach(k=>{
    const w=String(d[k]||'').trim();
    if(w.length<4||/\s/.test(w))return;
    const key=fzHe(w); if(key.length<3)return;
    (cnt[key]=cnt[key]||{})[w]=(cnt[key][w]||0)+1;
  }));
  const m={};
  Object.keys(cnt).forEach(key=>{                       // כמה איותים לאותו צליל — בוחרים את הנפוץ
    const l=Object.keys(cnt[key]).sort((a,b)=>cnt[key][b]-cnt[key][a]);
    if(l.length===1||cnt[key][l[0]]>cnt[key][l[1]])m[key]=l[0];
  });
  _NMIDX=m; return m;
}
const _HPFX=/^[ולבכמשה]/;                                 // אותיות שימוש: לאברמוביץ, ושטטפלד…
function fixNames(txt){
  const hits=[];
  if(!txt||!(DB||[]).length)return {text:txt,hits:hits};
  const idx=nameIndex();
  const out=String(txt).split(' ').map(w=>{
    const bare=w.replace(/[^\u05d0-\u05ea]/g,'');
    if(bare.length<4)return w;
    let pre='', body=bare, cand=idx[fzHe(bare)];
    if(!cand&&bare.length>=5&&_HPFX.test(bare)){pre=bare[0];body=bare.slice(1);cand=idx[fzHe(body)];}
    if(!cand||cand===body)return w;
    hits.push(bare+' → '+pre+cand);
    return w.replace(bare,pre+cand);
  }).join(' ');
  return {text:out,hits:hits.slice(0,3)};
}
// ===== בדיקת מערכת — מה עובד, מה חסר, ומה דורש טיפול =====
async function openHealth(){
  const ov=document.getElementById('dictov'), sh=document.getElementById('dictsheet');
  sh.innerHTML='<button class="x" id="hx">✕</button><h2>🩺 בדיקת מערכת</h2><div class="hintxt">בודק…</div>';
  ov.classList.add('show');
  document.getElementById('hx').onclick=()=>ov.classList.remove('show');
  const h=await api('GET','/api/health');
  if(!h||!h.rows){sh.innerHTML='<button class="x" id="hx2">✕</button><h2>🩺 בדיקת מערכת</h2><div class="hintxt">השרת לא החזיר תשובה</div>';
    document.getElementById('hx2').onclick=()=>ov.classList.remove('show');return;}
  const ic={ok:'✅',warn:'⚠️',bad:'❌'};
  sh.innerHTML=`<button class="x" id="hx3">✕</button><h2>🩺 בדיקת מערכת</h2>
    <div class="hintxt">${esc(h.when)} · ${h.bad?('❌ '+h.bad+' תקלות'):'✅ אין תקלות'}${h.warn?(' · ⚠️ '+h.warn+' לתשומת לב'):''}</div>
    ${h.rows.map(r=>`<div class="hrow ${r.state}"><span class="hi">${ic[r.state]||''}</span>
      <span class="hn"><b>${esc(r.name)}</b><small>${esc(r.detail)}</small></span></div>`).join('')}
    <button class="btn" id="hagain" style="width:100%;margin-top:10px">🔄 בדוק שוב</button>`;
  document.getElementById('hx3').onclick=()=>ov.classList.remove('show');
  document.getElementById('hagain').onclick=openHealth;
}
// ===== פנקס ההכתבה — להכתיב הוראות ותיקונים ולהעתיק אותם במכה אחת =====
const DICTKEY='kc_dict_hist';
function dictHist(){try{return JSON.parse(localStorage.getItem(DICTKEY)||'[]');}catch(e){return [];}}
function dictSave(t){
  t=String(t||'').trim(); if(!t)return;
  const l=dictHist().filter(x=>x.t!==t); l.unshift({t:t,d:new Date().toLocaleString('he-IL')});
  try{localStorage.setItem(DICTKEY,JSON.stringify(l.slice(0,12)));}catch(e){}
}
// שליחה ישירה — פותח את חלון השיתוף של אנדרואיד; בוחרים את קלוד והטקסט נכנס לצ׳אט
async function shareTxt(t){
  if(navigator.share){
    try{await navigator.share({text:t});dictSave(t);toast('נשלח ✓');return 'sent';}
    catch(e){if(e&&e.name==='AbortError')return 'cancel';}
  }
  return (await copyTxt(t))?'copied':'fail';
}
async function copyTxt(t){
  try{await navigator.clipboard.writeText(t);toast('הועתק ✓ — הדבק לי בצ׳אט');return true;}
  catch(e){const ta=document.getElementById('dictpad');
    if(ta){ta.select();ta.setSelectionRange(0,99999);try{document.execCommand('copy');toast('הועתק ✓');return true;}catch(e2){}}
    toast('לא הצלחתי להעתיק — סמן ידנית');return false;}
}
function openDictPad(){
  const ov=document.getElementById('dictov'), sh=document.getElementById('dictsheet');
  const h=dictHist(), auto=localStorage.getItem('kc_dict_noauto')!=='1';
  sh.innerHTML=`<button class="x" id="dictx">✕</button><h2>🎤 הכתבה</h2>
    <div class="hintxt">לחץ "התחל להקליט" ודבר בעברית. בסיום הטקסט מועתק לבד — עבור לצ׳אט והדבק (לחיצה ארוכה → הדבק).</div>
    <textarea id="dictpad" class="dictpad" placeholder="כאן ייכתב מה שתאמר…"></textarea>
    <button class="btn dictbig" id="dictgo">🎤 התחל להקליט</button>
    <button class="btn dictbig" id="dictsend" style="background:var(--yes)">📋 העתק להדבקה בצ׳אט</button>
    <label class="jointchk" style="margin-top:8px"><input type="checkbox" id="dictauto" ${auto?'checked':''}> להעתיק אוטומטית ברגע שמסיימים להקליט</label>
    <div class="dictbar">
      <button class="btn sm ghost" id="dictshare">📤 שיתוף לאפליקציה אחרת</button>
      <button class="btn sm ghost" id="dictadd">➕ שורה חדשה</button>
      <button class="btn sm ghost" id="dictclr">🗑 נקה</button></div>
    ${h.length?`<div class="dicthist"><div class="hintxt">הכתבות אחרונות — לחץ לשלוח שוב</div>
      ${h.map((x,i)=>`<div class="dh"><span>${esc(x.t.slice(0,220))}${x.t.length>220?'…':''}</span>
        <button class="btn sm dhsend" data-i="${i}">📋</button><button class="del dhdel" data-i="${i}">🗑</button></div>`).join('')}</div>`:''}`;
  ov.classList.add('show');
  const pad=document.getElementById('dictpad'), go=document.getElementById('dictgo'),
        snd=document.getElementById('dictsend'), au=document.getElementById('dictauto');
  document.getElementById('dictx').onclick=()=>{stopDictation();ov.classList.remove('show');};
  au.onchange=()=>{try{localStorage.setItem('kc_dict_noauto',au.checked?'0':'1');}catch(e){}};
  // ההעתקה היא הדרך האמינה — שיתוף פותח שיחה חדשה ולא בהכרח את השיחה הנכונה
  const send=async()=>{const t=pad.value.trim(); if(!t){toast('אין מה להעתיק');return;}
    if(await copyTxt(t)){dictSave(t);toast('הועתק ✓ — עבור לצ׳אט והדבק');}};
  snd.onclick=send;
  document.getElementById('dictshare').onclick=async()=>{const t=pad.value.trim();
    if(!t){toast('אין מה לשלוח');return;} await shareTxt(t);};
  go.onclick=()=>{
    const wasRec=go.classList.contains('rec');
    startDictation(go,pad);
    if(!wasRec)go._wantSend=au.checked;               // בסיום ההקלטה נשלח מיד
    else go._wantSend=false;
  };
  // מעקב אחרי מצב ההקלטה — משנה כיתוב ומדליק את הכפתור הצף
  new MutationObserver(()=>{const on=go.classList.contains('rec');
    go.textContent=on?'⏹ סיים ושלח':'🎤 התחל להקליט';
    document.getElementById('dictfab').classList.toggle('rec',on);
    if(!on&&go._wantSend){go._wantSend=false;setTimeout(()=>{if(pad.value.trim())send();},250);}
  }).observe(go,{attributes:true,attributeFilter:['class']});
  document.getElementById('dictadd').onclick=()=>{if(pad.value.trim())pad.value=pad.value.trim()+'\n';pad.focus();};
  document.getElementById('dictclr').onclick=()=>{if(pad.value.trim())dictSave(pad.value.trim());pad.value='';pad.focus();};
  sh.querySelectorAll('.dhsend').forEach(b=>b.onclick=()=>copyTxt(dictHist()[+b.dataset.i].t));
  sh.querySelectorAll('.dhdel').forEach(b=>b.onclick=()=>{
    const l=dictHist(); l.splice(+b.dataset.i,1);
    try{localStorage.setItem(DICTKEY,JSON.stringify(l));}catch(e){} openDictPad();});
}
// מצמיד כפתור מיקרופון לשדה טקסט. נשאר בפינה ולא משנה את הפריסה
function addMic(el){
  if(!SPR||!el||el._micd)return; el._micd=1;
  const w=document.createElement('div'); w.className='micwrap';
  el.parentNode.insertBefore(w,el); w.appendChild(el);
  const b=document.createElement('button'); b.type='button'; b.className='micbtn';
  b.textContent='🎤'; b.title='הקלטה קולית — דבר בעברית';
  b.onclick=e=>{e.preventDefault();e.stopPropagation();startDictation(b,el);};
  w.appendChild(b);
}
// מצמיד מיקרופון לכל השדות שנבחרו בתוך אזור מסוים
function addMics(root,sels){
  if(!SPR||!root)return;
  sels.forEach(sl=>root.querySelectorAll(sl).forEach(addMic));
}
function todayStr(){return new Date().toISOString().slice(0,10);}
function inDaysStr(n){const d=new Date();d.setDate(d.getDate()+(n||0));return d.toISOString().slice(0,10);}
function addDay(ymd8){const y=+ymd8.slice(0,4),m=+ymd8.slice(4,6)-1,d=+ymd8.slice(6,8);return new Date(Date.UTC(y,m,d+1)).toISOString().slice(0,10).replace(/-/g,'');}
function gcalLink(t,donor){const d=(t.due_date||'').replace(/-/g,'');if(d.length!==8)return '';const title=encodeURIComponent((kindLabel(t.kind)||'תזכורת')+' — '+donor+(t.note?': '+t.note:''));return `https://calendar.google.com/calendar/render?action=TEMPLATE&text=${title}&dates=${d}/${addDay(d)}`;}
function dueTasks(){const td=todayStr(),out=[];DB.forEach(d=>(d.tasks||[]).forEach(t=>{if((!t.done||t.done==0)&&t.due_date&&t.due_date<=td)out.push({...t,donor:(d.last+' '+d.first).trim(),dref:d});}));return out.sort((a,b)=>(a.due_date||'').localeCompare(b.due_date||''));}
// מי אחראי על המשימה — מוצג בכל מקום שבו רואים משימה, וניתן להחליף בלחיצה
const whoName=t=>(((t&&t.assignee)||'')==='אהרן'?'אהרן':'מאיר');
function whoChipHTML(t,attrs){return `<button class="whoflip ${whoName(t)==='אהרן'?'ah':'me'}" ${attrs||''} title="לחץ להחליף בין מאיר לאהרן" onclick="event.stopPropagation()">👤 ${whoName(t)} ⇄</button>`;}
// מחליף את האחראי ומעדכן את הרשומה בכל מקום שבו היא מוחזקת בזיכרון
async function flipWho(id){
  let rec=GTASKS.find(x=>x.id==id);
  if(!rec)for(const d of DB){const t=(d.tasks||[]).find(x=>x.id==id);if(t){rec=t;break;}}
  const who=((rec&&rec.assignee)||'')==='אהרן'?'':'אהרן';
  await api('PUT','/api/task/'+id,{assignee:who});
  if(rec)rec.assignee=who;
  for(const d of DB){const t=(d.tasks||[]).find(x=>x.id==id);if(t)t.assignee=who;}
  toast(who==='אהרן'?'הועבר לאהרן ✓':'הועבר למאיר ✓');
  return who;
}
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
    ${due.map((t,i)=>`<div class="remitem over"><div class="ri"><b>${esc(kindLabel(t.kind))} ${esc(t.donor)}</b><br><small>${esc(t.due_date)} ${esc(t.note||'')}</small><br>${whoChipHTML(t,'data-rwho="'+t.id+'"')}</div>
      <button class="btn sm rdone" data-i="${i}">בוצע ✓</button><button class="no rsnooze" data-i="${i}">דחה מחר</button></div>`).join('')}`;
  remov.classList.add('show');
  document.getElementById('rx').onclick=()=>remov.classList.remove('show');
  rs.querySelectorAll('[data-rwho]').forEach(b=>b.onclick=async e=>{e.stopPropagation();b.disabled=true;await flipWho(b.dataset.rwho);openRemPopup();render();});
  rs.querySelectorAll('.rdone').forEach(b=>b.onclick=async()=>{const t=due[b.dataset.i];if(t.id)await api('PUT','/api/task/'+t.id,{done:1});const lt=(t.dref.tasks||[]).find(x=>x.id===t.id);if(lt)lt.done=1;checkReminders();openRemPopup();render();toast('בוצע ✓');});
  rs.querySelectorAll('.rsnooze').forEach(b=>b.onclick=async()=>{const t=due[b.dataset.i],nd=addDay(todayStr().replace(/-/g,'')),nds=nd.slice(0,4)+'-'+nd.slice(4,6)+'-'+nd.slice(6,8);if(t.id)await api('PUT','/api/task/'+t.id,{due_date:nds});const lt=(t.dref.tasks||[]).find(x=>x.id===t.id);if(lt)lt.due_date=nds;checkReminders();openRemPopup();render();toast('נדחה למחר');});
}

function esc(s){return (s==null?'':String(s)).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));}
function norm(s){return (s||'').replace(/["'`]/g,'').replace(/\s+/g,' ').trim();}
function dupKey(d){return norm((d.last||'')+' '+(d.first||'')).replace(/[-־]/g,'');}
// מפתח דמיון לשם עברי — בלי אמות קריאה ועם איחוד אותיות דומות, כדי לתפוס גם איות שונה
// (וורצברגר / ווערצבערגער, שטטפלד / סטטפלד). אותו היגיון כמו בשרת.
const FZMAP={'ך':'כ','ם':'מ','ן':'נ','ף':'פ','ץ':'צ','ש':'ס','ז':'ס','צ':'ס','ת':'ט','כ':'ק'};
function fzHe(s){
  s=String(s||'').replace(/[^א-ת]/g,'').replace(/[ךםןףץשזצתכ]/g,c=>FZMAP[c]);
  return s.replace(/[אהעוי]/g,'').replace(/(.)\1+/g,'$1');
}
function fzKey(d){const k=fzHe(d.last)+'|'+fzHe(d.first);return k==='|'?'':k;}
// זוגות שסומנו "לא אותו אדם" — נשמרים בשרת ולא חוזרים לרשימה
let NOTDUPE=new Set();
const ndKey=(a,b)=>Math.min(a,b)+'-'+Math.max(a,b);
// עשר הספרות האחרונות של מספר טלפון — השוואה בלי תלות בקידומת ובסימנים
function ph10(s){const d=String(s||'').replace(/\D/g,'');return d.length>=10?d.slice(-10):'';}
function ndClean(a){                       // מסיר מהקבוצה מי שסומן "לא אותו אדם" מול כל השאר
  const keep=a.filter(d=>a.some(x=>x.id!==d.id&&!NOTDUPE.has(ndKey(d.id,x.id))));
  return keep.length>1?keep:null;
}
function findDupes(){
  const out=[], seen=new Set();
  const add=(a,why)=>{                       // קבוצה נכנסת פעם אחת, לפי הסימן החזק ביותר שמצאנו
    if(a.length<2||a.every(d=>seen.has(d.id)))return;
    const c=ndClean(a); if(!c)return;
    c.forEach(d=>seen.add(d.id)); c.why=why; out.push(c);
  };
  const bucket=fn=>{const m={};DB.forEach(d=>{(fn(d)||[]).forEach(k=>{if(k)(m[k]=m[k]||[]).push(d);});});
    return Object.values(m).map(a=>[...new Map(a.map(d=>[d.id,d])).values()]).filter(a=>a.length>1);};
  bucket(d=>[dupKey(d)]).forEach(a=>add(a,''));                                  // אותו שם בדיוק
  bucket(d=>splitEmails(d.email).map(e=>'@'+e.toLowerCase())).forEach(a=>add(a,'📧 אותו מייל'));
  bucket(d=>splitPhones(d.phone).map(ph10)).forEach(a=>add(a,'📞 אותו טלפון — אולי בני זוג, בדוק'));
  bucket(d=>[fzKey(d)]).forEach(a=>add(a,'איות שונה — בדוק שזה באמת אותו אדם'));  // איות שונה
  // אותו שם משפחה, ולאחד מהם אין שם פרטי או שהוא קיצור של השני (יידי / יידל)
  bucket(d=>[fzHe(d.last)]).forEach(a=>{
    if(a.length>4)return;
    const fs=a.map(d=>fzHe(d.first));
    if(!fs.every((x,i)=>fs.every((y,j)=>i===j||!x||!y||x.startsWith(y)||y.startsWith(x))))return;
    add(a,'איות שונה — בדוק שזה באמת אותו אדם');
  });
  return out;
}

// פרנס "פתוח" = הלילה עדיין לא עבר, או שעבר אך טרם שולם. הירח נעלם רק כשהלילה עבר וגם שולם.
function hasOpenParnes(d){const t=todayStr();return (d.parnes||[]).some(p=>!(p.night_date&&p.night_date<t&&+p.paid));}
function toast(t){toastEl.textContent=t;toastEl.classList.add('show');setTimeout(()=>toastEl.classList.remove('show'),1300);}
let _undoTimer;
function toastUndo(msg,undoFn){
  toastEl.innerHTML=esc(msg)+' <button class="undobtn">↩️ בטל</button>';
  toastEl.classList.add('show');clearTimeout(_undoTimer);
  const b=toastEl.querySelector('.undobtn');if(b)b.onclick=async()=>{clearTimeout(_undoTimer);toastEl.classList.remove('show');await undoFn();};
  _undoTimer=setTimeout(()=>{toastEl.classList.remove('show');},6000);
}
// אישור בתוך האפליקציה — confirm() של הדפדפן חסום לעיתים באפליקציה המותקנת (PWA)
function uiConfirm(msg){
  return new Promise(res=>{
    const o=document.createElement('div');o.className='confirmov';
    o.innerHTML=`<div class="confirmbox"><div class="cm">${esc(msg).replace(/\n/g,'<br>')}</div><div class="cbtns"><button class="btn ghost cno">ביטול</button><button class="btn cyes">אישור</button></div></div>`;
    document.body.appendChild(o);
    const done=v=>{o.remove();res(v);};
    o.querySelector('.cno').onclick=()=>done(false);
    o.querySelector('.cyes').onclick=()=>done(true);
    o.onclick=e=>{if(e.target===o)done(false);};
  });
}
// בורר חודש+שנה עברית — לשיוך תורם מזדמן לחודש/שנה מסוימים בקוויטל המזדמנים
function uiPickMonth(msg,curM,curY){
  return new Promise(res=>{
    const o=document.createElement('div');o.className='confirmov';
    o.innerHTML=`<div class="confirmbox"><div class="cm">${esc(msg)}</div>
      <div class="two" style="margin:10px 0">
        <select class="pmsel" style="padding:10px;font-size:1.05rem">${HMORD.map(m=>`<option ${m===curM?'selected':''}>${m}</option>`).join('')}</select>
        <select class="pysel" style="padding:10px;font-size:1.05rem">${heYearOpts(curY||HEBYEAR)}</select></div>
      <div class="cbtns"><button class="btn ghost cno">ביטול</button><button class="btn cyes">אישור</button></div></div>`;
    document.body.appendChild(o);
    const msel=o.querySelector('.pmsel'),ysel=o.querySelector('.pysel');
    const done=v=>{o.remove();res(v);};
    o.querySelector('.cno').onclick=()=>done(null);
    o.querySelector('.cyes').onclick=()=>done({month:msel.value,year:ysel.value});
    o.onclick=e=>{if(e.target===o)done(null);};
  });
}
function pill(t){if(!TIERS[t])return '';const[l,c]=TIERS[t];return `<span class="pill ${c}">${l}</span>`;}
function catPill(c){if(c==='קבוע')return '<span class="pill reg">קבוע</span>';if(c==='מזדמן')return '<span class="pill occ">מזדמן</span>';return '';}
// ערוצי חיוב — תג צבעוני מובחן לכל ערוץ (בצבעי המותג)
const CHANNELS={
  'אשראי':{i:'💳',l:'אשראי',c:'#1a5fb4'},
  'מזומן':{i:'💵',l:'מזומן',c:'#2f7a3e'},
  'בנק_ווסט':{i:'🏦',l:'בנק ווסט',c:'#0b6e61'},
  'אותורייז':{i:'💳',l:'אוטורייז',c:'#1a5fb4'},
  'צק':{i:'🧾',l:"צ'ק",c:'#8a6d00'},
  'Zelle':{i:'Ⓩ',l:'זל',c:'#6d1ed4'},
  'העברה_בנקאית':{i:'🏦',l:'העברה בנקאית',c:'#4a5568'},
  'דונורס_פאנד':{i:'💼',l:'דונרס פאנד',c:'#9a4a12'},
  'נדרים':{i:'📱',l:'נדרים',c:'#c2410c'},
  'OJC':{i:'🏛️',l:'OJC',c:'#3b4252'},
  'Pledger':{i:'📲',l:'פלדג׳ר',c:'#3b4252'},
};
const CHAN_ORDER=['אשראי','מזומן','צק','Zelle','העברה_בנקאית','בנק_ווסט','אותורייז','דונורס_פאנד','נדרים','OJC','Pledger'];
// שמות הערוצים כפי שהם נשמרו בייבואים — כדי שיוצגו תמיד בעברית ובאותו עיצוב
const CHALIAS={'Banquest':'בנק_ווסט','banquest':'בנק_ווסט','בנק ווסט':'בנק_ווסט',
  'Authorize':'אותורייז','authorize':'אותורייז','Checks':'צק','Check':'צק',"צ'ק":'צק','צ׳ק':'צק','המחאה':'צק',
  'Donors Fund':'דונורס_פאנד','דונרס':'דונורס_פאנד','Donors':'דונורס_פאנד',
  'ACH':'העברה_בנקאית','העברה בנקאית':'העברה_בנקאית','Wire':'העברה_בנקאית','אונליין':'אשראי'};
const CHEXTRA={'Annualy':{i:'📅',l:'תשלום שנתי',c:'#4a5568'},'Pledger':{i:'📲',l:'פלדג׳ר',c:'#3b4252'}};
function chCfg(ch){ch=(ch||'').trim();return CHANNELS[ch]||CHANNELS[CHALIAS[ch]]||CHEXTRA[ch]||null;}
function chBadgeRaw(ch){const cfg=chCfg(ch);if(!cfg)return '';return `<span class="chbadge" style="background:${cfg.c}" title="${esc(cfg.l)}">${cfg.i} ${esc(cfg.l)}</span>`;}
function chLabel(ch){const cfg=chCfg(ch);return cfg?cfg.l:(ch||'');}
function channelBadge(d){return chBadgeRaw(d.channel);}
function channelOpts(cur){cur=(cur||'').trim();let o='<option value="">— ללא —</option>';CHAN_ORDER.forEach(k=>{o+=`<option value="${k}" ${k===cur?'selected':''}>${CHANNELS[k].i} ${CHANNELS[k].l}</option>`;});if(cur&&!CHANNELS[cur])o+=`<option value="${esc(cur)}" selected>${esc(cur)}</option>`;return o;}
// הסכום הקבוע (חודשי) — לתורם קבוע לפי השדה, וליששכר־זבולון סכום האברכים הפעילים
function fixedAmt(d){
  if(d.tier==='יששכר_זבולון'){const s=(d.partners||[]).filter(p=>p.active!=0).reduce((a,p)=>a+amtNum(p.amount),0);if(s)return curSym(d)+s;}
  if(d.category==='קבוע'&&amtNum(d.amount))return curSym(d)+amtNum(d.amount);
  return '';}
// חיפוש חופשי: כל מילה בשאילתה חייבת להופיע — בלי תלות בסדר,
// כך ש"אפרים מיטמן" ו"מיטמן אפרים" מוצאים אותו דבר. אם לא נמצא,
// מנסים שוב לפי צליל בעברית, כדי לתפוס איות שונה.
function matchQ(s){
  if(!q)return true;
  const h=norm(s).toLowerCase(), toks=norm(q).toLowerCase().split(' ').filter(Boolean);
  if(!toks.length)return true;
  if(toks.every(t=>h.indexOf(t)>=0))return true;
  const hf=fzHe(h);
  return hf&&toks.every(t=>{const f=fzHe(t);return f.length>=3&&hf.indexOf(f)>=0;});
}

async function api(m,u,b){const r=await fetch(u,{method:m,headers:{'Content-Type':'application/json'},body:b?JSON.stringify(b):undefined});return r.json();}
function fileChip(f){const m=(f.mime||'');
  const dl=`<a class="fdl" href="/api/file/${f.id}?dl=1" download="${esc(f.name||'file')}" title="הורד למכשיר">⬇️</a>`;
  // הודעה קולית מוואטסאפ — נגן ישירות בכרטיס
  if(m.indexOf('audio')>=0||/\.(ogg|opus|m4a|mp3|wav|aac|amr)$/i.test(f.name||''))
    return `<span class="fchip audio"><audio controls preload="none" src="/api/file/${f.id}"></audio>${dl}<button class="fdel" data-fid="${f.id}" title="מחק">🗑</button></span>`;
  // תמונה — תצוגה מקדימה קטנה שנפתחת בלחיצה
  if(m.indexOf('image')>=0)
    return `<span class="fchip img"><a href="/api/file/${f.id}" target="_blank" rel="noopener"><img src="/api/file/${f.id}" alt="${esc(f.name||'')}" loading="lazy"></a>${dl}<button class="fdel" data-fid="${f.id}" title="מחק">🗑</button></span>`;
  const ic=m.indexOf('pdf')>=0?'📄':'📎';
  return `<span class="fchip"><a href="/api/file/${f.id}" target="_blank" rel="noopener">${ic} ${esc(f.name||'קובץ')}</a>${dl}<button class="fdel" data-fid="${f.id}">🗑</button></span>`;}
function uploadBlob(kind,refId,f){return new Promise(res=>{
  if(!f){res(false);return;}
  if(f.size>15*1024*1024){toast('קובץ גדול מדי (מקס 15MB)');res(false);return;}
  const rd=new FileReader();
  rd.onload=async()=>{try{await api('POST','/api/file',{kind,ref_id:refId,name:f.name,mime:f.type,data:rd.result.split(',')[1]});res(true);}catch(e){res(false);}};
  rd.onerror=()=>res(false);
  rd.readAsDataURL(f);});}
function uploadFile(kind,refId,inputEl,cb){const f=inputEl.files[0];if(!f)return;toast('מעלה…');uploadBlob(kind,refId,f).then(ok=>{if(ok)toast('הועלה ✓');inputEl.value='';cb&&cb();});}
// ===== משיכת מיילים ותיוקם אצל התורמים — רצה ברקע בשרת, כאן עוקבים אחרי ההתקדמות =====
async function runMailSync(btn){
  const label=btn?btn.textContent:'';
  const set=t=>{if(btn)btn.textContent=t;};
  if(btn)btn.disabled=true; set('מתחיל…');
  const r=await api('POST','/api/mail/contacts_sync',{});
  if(!r||!r.ok){
    if(btn){btn.disabled=false;set(label);}
    toast(r&&r.error==='not_configured'?'המייל לא מוגדר בשרת (GMAIL_USER / GMAIL_APP_PASSWORD)':'שגיאה: '+((r&&(r.detail||r.error))||''));
    return;
  }
  let last=0;
  for(let i=0;i<900;i++){                       // עד ~30 דקות, בדיקה כל 2 שניות
    await new Promise(res=>setTimeout(res,2000));
    let s;try{s=await api('GET','/api/mail/contacts_sync/status');}catch(e){continue;}
    if(!s)continue;
    last=s.new||0;
    if(s.running){set(s.total?('מתייק… '+last+'/'+s.total):('סורק… '+(s.scanned||0)+' מיילים'));continue;}
    if(btn){btn.disabled=false;set(label);}
    if(s.error){toast('שגיאת משיכה: '+s.error);return;}
    if(last)await load();
    toast(last?('תויקו '+last+' מיילים אצל התורמים ✓'):'הכל מסונכרן — אין מיילים חדשים');
    render();return;
  }
  if(btn){btn.disabled=false;set(label);}
  toast('המשיכה עדיין רצה ברקע — בדוק שוב בעוד כמה דקות');
}
// ===== קבצים שהגיעו דרך "שיתוף" מוואטסאפ/גלריה (Web Share Target) =====
async function takeSharedFiles(){
  try{
    const c=await caches.open('kc-shared');const keys=await c.keys();
    const files=[];let text='';
    for(const k of keys){
      const res=await c.match(k);if(!res)continue;
      if(new URL(k.url).pathname==='/__shared_text__'){text=await res.text();continue;}
      const blob=await res.blob();
      const nm=decodeURIComponent(new URL(k.url).pathname.split('/').pop()||'file');
      files.push(new File([blob],nm,{type:blob.type||'application/octet-stream'}));
    }
    return {files,text,clear:async()=>{for(const k of await c.keys())await c.delete(k);}};
  }catch(e){return {files:[],text:'',clear:async()=>{}};}
}
async function shareInbox(){
  const {files,text,clear}=await takeSharedFiles();
  if(!files.length)return;
  let chosen=null;
  const o=document.createElement('div');o.className='confirmov';
  o.innerHTML=`<div class="confirmbox" style="max-width:520px;text-align:right">
    <div class="cm" style="font-weight:800;margin-bottom:6px">📥 התקבלו ${files.length} קבצים משיתוף</div>
    <div class="avfiles dnfiles" id="sh_list"></div>
    <label class="fld" style="margin-top:8px"><span>🔍 לאיזה תורם לצרף?</span><input id="sh_q" placeholder="שם / טלפון / עסק…" autocomplete="off"></label>
    <div id="sh_res" class="dpres"></div><div id="sh_pick" class="pick" style="display:none"></div>
    <label class="fld" style="margin-top:6px"><span>✍️ הערה</span><input id="sh_note" value="${esc(text||'התקבל בוואטסאפ')}"></label>
    <label class="fld" style="margin-top:6px"><span>🗓️ תאריך תזכורת (רק אם בוחרים משימה)</span><input id="sh_date" type="date" value="${esc(todayStr())}"></label>
    <div style="display:flex;flex-direction:column;gap:8px;margin-top:10px">
      <button class="btn" id="sh_contact">📞 צרף לתיעוד קשר</button>
      <button class="btn" id="sh_task">🔔 צרף כמשימה (להזכיר לחייב)</button></div>
    <div class="cbtns" style="margin-top:10px"><button class="btn ghost cno">בטל</button></div></div>`;
  document.body.appendChild(o);
  const done=async(wipe)=>{if(wipe)await clear();o.remove();};
  o.querySelector('#sh_list').innerHTML=files.map(f=>`<span class="fchip">${(f.type||'').indexOf('audio')>=0?'🎙️':((f.type||'').indexOf('image')>=0?'🖼️':'📎')} ${esc(f.name)}</span>`).join('');
  o.querySelector('.cno').onclick=()=>done(true);
  const q=o.querySelector('#sh_q'),res=o.querySelector('#sh_res'),pick=o.querySelector('#sh_pick');
  q.oninput=()=>{const s=norm(q.value);if(!s){res.innerHTML='';return;}
    const m=DB.filter(x=>norm(x.last+' '+x.first+' '+(x.english||'')+' '+(x.phone||'')).includes(s)).slice(0,6);
    res.innerHTML=m.map(x=>`<div class="dpr" data-did="${x.id}">${esc(x.last)} ${esc(x.first)} <span style="color:var(--muted)">#${x.id}</span></div>`).join('')||'<div class="dpr" style="color:var(--muted)">אין תוצאות</div>';
    res.querySelectorAll('.dpr[data-did]').forEach(el=>el.onclick=()=>{chosen=DB.find(x=>x.id==el.dataset.did);res.innerHTML='';q.value='';
      pick.style.display='';pick.textContent='✓ '+(chosen.last+' '+chosen.first).trim();});};
  const attach=async(mode)=>{
    if(!chosen){toast('בחר תורם קודם');return;}
    const note=o.querySelector('#sh_note').value.trim()||'התקבל בוואטסאפ';
    const btns=o.querySelectorAll('button');btns.forEach(b=>b.disabled=true);
    toast('מעלה…');
    let refId,kind;
    if(mode==='contact'){
      const r=await api('POST','/api/contact',{donor_id:chosen.id,channel:'וואטסאפ',date:todayStr(),summary:note});
      refId=r.id;kind='contact';
    }else{
      const r=await api('POST','/api/task',{donor_id:chosen.id,due_date:o.querySelector('#sh_date').value||todayStr(),kind:'charge',note});
      refId=r.id;kind='task';
    }
    for(const f of files)await uploadBlob(kind,refId,f);
    await done(true);await load();
    const dd=DB.find(x=>x.id===chosen.id);if(dd)openDonor(dd,mode==='contact'?'contact':'contact');
    toast('צורף ל'+(chosen.last+' '+chosen.first).trim()+' ✓');
  };
  o.querySelector('#sh_contact').onclick=()=>attach('contact');
  o.querySelector('#sh_task').onclick=()=>attach('task');
}
// בורר קבצים לטופס חדש — אוסף קבצים לפני השמירה, ומעלה אותם מיד אחריה
function pendFiles(boxId,inputId){
  const arr=[],box=document.getElementById(boxId),inp=document.getElementById(inputId);
  if(!box||!inp)return {arr,reset(){}};
  const paint=()=>{
    box.querySelectorAll('.pchip').forEach(x=>x.remove());
    arr.forEach((f,i)=>{const s=document.createElement('span');s.className='fchip pchip';
      s.innerHTML=`${(f.type||'').indexOf('audio')>=0?'🎙️':((f.type||'').indexOf('image')>=0?'🖼️':'📎')} ${esc(f.name)} <button class="fdel">✕</button>`;
      s.querySelector('.fdel').onclick=()=>{arr.splice(i,1);paint();};
      box.insertBefore(s,box.firstChild);});
  };
  inp.onchange=()=>{[...inp.files].forEach(f=>arr.push(f));inp.value='';paint();};
  return {arr,reset(){arr.length=0;paint();}};
}
async function load(){
  const d = await api('GET','/api/data');
  DB = d.donors; UNLINKED = d.unlinked_prayers || []; GTASKS = d.general_tasks || []; CAMPAIGNS = d.campaigns || []; BUILDING_ITEMS = d.building_items || []; TASKKINDS_C = d.task_kinds || []; _NMIDX = null; HEBYEAR = hq(d.heb_year) || '';
  NOTDUPE = new Set((d.not_dupes||[]).map(p=>ndKey(p[0],p[1])));
  GLAST = (function(){const c=[...Array(12)].map((_,i)=>DB.filter(x=>x.months&&(x.months[i]==='p'||x.months[i]==='c')).length);const mx=Math.max(1,...c);let l=0;for(let i=0;i<12;i++)if(c[i]>=0.3*mx)l=i;return l;})();
  document.getElementById('stat').textContent = DB.length + ' תורמים';
  // שחזור הלשונית שבה הייתי לפני הרענון
  try{const st=localStorage.getItem('kc_tab');const valid=['donors','tasks','kvittel','parnes','charges','avreich','missed','camp','mails'];if(st&&valid.includes(st)){tab=st;document.querySelectorAll('.tab').forEach(x=>x.classList.toggle('on',x.dataset.tab===st));if(st==='parnes'){const py=JSON.parse(localStorage.getItem('kc_py')||'{}');if(py.kind)pyKind=py.kind;if(py.month)pyMonth=py.month;if(py.day)pyDay=py.day;}}}catch(e){}
  render();
  checkReminders();
  // פתיחת כרטיס: לפי פרמטר בכתובת (קישור), אחרת התורם שהיה פתוח לפני הרענון
  const wasShare=(()=>{try{return new URLSearchParams(location.search).get('share')==='1';}catch(e){return false;}})();
  try{let pd=new URLSearchParams(location.search).get('donor');if(!pd&&!wasShare)pd=localStorage.getItem('kc_donor');if(pd){const dd=DB.find(x=>x.id==+pd);if(dd)openDonor(dd);}history.replaceState(null,'',location.pathname);}catch(e){}
  if(wasShare)shareInbox();       // קבצים שהגיעו משיתוף — פתח מסך שיוך לתורם
}

document.querySelectorAll('.tab').forEach(b=>b.onclick=()=>{tab=b.dataset.tab;document.querySelectorAll('.tab').forEach(x=>x.classList.toggle('on',x===b));flt='';plaque=null;pyMonth=null;pyDay=null;pyKind='parnes';kvSub=null;try{localStorage.setItem('kc_tab',tab);localStorage.removeItem('kc_donor');}catch(e){}render();});
document.getElementById('q').oninput=e=>{q=e.target.value.trim();render();};
ov.onclick=e=>{if(e.target===ov){ov.classList.remove('show');try{localStorage.removeItem('kc_donor');}catch(e){}}};
document.getElementById('remov').onclick=e=>{if(e.target.id==='remov')e.currentTarget.classList.remove('show');};

function render(){
  chips.innerHTML='';
  if(tab==='donors'){
    if(flt==='addrfix')return renderAddrFix();
    if(flt==='noaddr')return renderNoAddr();
    if(flt==='nophone')return renderNoPhone();
    return renderDonors();
  }
  if(tab==='tasks') return renderTasksTab();
  if(tab==='kvittel') return renderKvittel();
  if(tab==='parnes') return renderParnes();
  if(tab==='charges') return renderCharges();
  if(tab==='avreich') return renderAvreich();
  if(tab==='debts') return renderDebts();
  if(tab==='missed') return renderMissed();
  if(tab==='mails') return renderMails();
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
  'il':{label:'🇮🇱 ארץ ישראל', fn:d=>d.region==='il'},
  'building':{label:'🏛️ בניין', fn:d=>(d.building||[]).length>0},
  'new':{label:'🆕 נוספו', fn:d=>!!d.created},
  '':{label:'הכל', fn:d=>true}
};
const DFORDER=['il','iz','k101','reg','reglow','occ','building','new',''];
// כל הייעודים שבשימוש בפועל + כמה תרומות וכמה כסף בכל אחד — לחיפוש ולניהול
let catFlt='';
function catUsage(){
  const m={};
  DB.forEach(d=>(d.donations||[]).forEach(x=>{
    const c=String(x.category||'').trim(); if(!c)return;
    if(!m[c])m[c]=[c,0,0];
    m[c][1]++; m[c][2]+=amtNum(x.amount);
  }));
  (CAMPAIGNS||[]).forEach(c=>{c=String(c||'').trim(); if(c&&!m[c])m[c]=[c,0,0];});
  return Object.values(m).sort((a,b)=>b[2]-a[2]||a[0].localeCompare(b[0],'he'));
}
function openCatManager(){
  const rows=catUsage();
  const o=document.createElement('div');o.className='confirmov';
  o.innerHTML=`<div class="confirmbox"><div class="cm" style="font-weight:800;margin-bottom:4px">🎯 ניהול ייעודים</div>
    <div class="hintxt" style="margin-bottom:8px">לחיצה על ייעוד מציגה את התורמים שלו. 🗑 מוחק אותו מרשימת הבחירה.</div>
    <div class="catmgrlist">${rows.map(([c,n,s])=>`<div class="catmgrrow" data-c="${esc(c)}">
      <button class="catmgrgo" data-c="${esc(c)}">${esc(c)}</button>
      <span class="catmgrn">${n?(n+' · $'+s.toLocaleString('en-US')):'לא בשימוש'}</span>
      <button class="del catmgrdel" data-c="${esc(c)}" data-n="${n}" title="מחק ייעוד">🗑</button></div>`).join('')
      ||'<div class="hintxt">אין עדיין ייעודים.</div>'}</div>
    <div class="cbtns" style="margin-top:10px"><button class="btn ghost cno">סגור</button></div></div>`;
  document.body.appendChild(o);const done=()=>o.remove();
  o.querySelector('.cno').onclick=done;o.onclick=e=>{if(e.target===o)done();};
  o.querySelectorAll('.catmgrgo').forEach(b=>b.onclick=()=>{catFlt=b.dataset.c;done();tab='donors';render();});
  o.querySelectorAll('.catmgrdel').forEach(b=>b.onclick=async()=>{
    const c=b.dataset.c, n=+b.dataset.n;
    if(n&&!confirm('הייעוד "'+c+'" מסומן על '+n+' תרומות.\nלמחוק אותו? התרומות יישארו, אבל יחזרו להיות בלי ייעוד.'))return;
    b.disabled=true;
    const r=await api('POST','/api/campaigns',{name:c,delete:true,force:true});
    if(!r||!r.ok){b.disabled=false;toast('המחיקה נכשלה');return;}
    CAMPAIGNS=(CAMPAIGNS||[]).filter(x=>x!==c);
    if(catFlt===c)catFlt='';
    toast(r.freed?('נמחק · '+r.freed+' תרומות חזרו לבלי ייעוד'):'הייעוד נמחק ✓');
    done(); await load(); render();
  });
}
function renderDonors(){
  chips.innerHTML=DFORDER.map(k=>{const cnt=DB.filter(DFILTERS[k].fn).length;return `<button class="chip ${flt===k?'on':''}" data-k="${k}">${DFILTERS[k].label} <b>${cnt}</b></button>`;}).join('');
  chips.querySelectorAll('.chip').forEach(c=>c.onclick=()=>{flt=c.dataset.k;render();});
  const ff=(DFILTERS[flt]||DFILTERS['']).fn;
  let list=DB.filter(d=>ff(d)&&matchQ(d.last+' '+d.first+' '+d.phone+' '+d.business+' '+d.english+' '+(d.notes||'')+' '+(d.building||[]).map(x=>x.object).join(' ')));
  if(catFlt)list=list.filter(d=>(d.donations||[]).some(x=>String(x.category||'').trim()===catFlt));
  if(donSort==='new'||flt==='new') list=list.slice().sort((a,b)=>String(b.created||'').localeCompare(String(a.created||'')));
  else if(donSort==='amt') list=list.slice().sort((a,b)=>donorTotals(b).all-donorTotals(a).all);
  else list=list.slice().sort((a,b)=>(a.last||'').localeCompare(b.last||'','he'));
  const ndup=findDupes().length;
  const nafix=DB.filter(addrIssue).length;
  const nanone=DB.filter(d=>!(d.addr||'').trim()).length;
  view.innerHTML=`<button class="btn addbig" id="newDonorBtn">➕ הוסף תורם חדש</button>
    ${ndup?`<button class="btn dupbtn" id="dupBtn">🔀 מיזוג כרטיסים כפולים (${ndup})</button>`:''}
    ${nafix?`<button class="btn kvmissbtn" id="addrFixBtn">🔴 כתובות לתיקון — ${nafix}</button>`:''}
    ${nanone?`<button class="btn kvmissbtn" id="noAddrBtn">🏠 בלי כתובת בכלל — ${nanone}</button>`:''}
    ${DB.filter(d=>!(d.phone||'').trim()).length?`<button class="btn kvmissbtn" id="noPhoneBtn" style="background:var(--yes);border-color:var(--yes)">📞 השלמת טלפונים — ${DB.filter(d=>!(d.phone||'').trim()).length} בלי טלפון</button>`:''}
    <div class="avbar"><select id="donsort" class="avsortsel">
      <option value="last">מיון: שם (א-ב)</option>
      <option value="amt">מיון: סכום תרומות (גבוה→נמוך)</option>
      <option value="new">מיון: נוספו לאחרונה</option>
    </select></div>
    <div class="avbar"><select id="doncat" class="avsortsel">
      <option value="">🎯 חיפוש לפי ייעוד — הכל</option>
      ${catUsage().map(([c,n,s])=>`<option value="${esc(c)}"${c===catFlt?' selected':''}>${esc(c)} — ${n} תרומות · $${s.toLocaleString('en-US')}</option>`).join('')}
    </select><button class="btn sm ghost" id="catmgr" style="white-space:nowrap">🗑 ניהול ייעודים</button></div>
    ${catFlt?`<div class="cnt" style="color:var(--accent)">🎯 ${esc(catFlt)} — ${(()=>{const u=catUsage().find(x=>x[0]===catFlt);return u?(u[1]+' תרומות · $'+u[2].toLocaleString('en-US')):'';})()}</div>`:''}
    <div class="cnt">${list.length} תורמים</div><div class="list">${list.map(d=>`
    <div class="rowc" data-id="${d.id}">
      <div><div class="nm">${esc(d.last)} <small>${esc(d.first)}</small><span class="rownum">#${d.id}</span>${fixedAmt(d)?`<span class="fixamt">💵 ${esc(fixedAmt(d))} קבוע</span>`:''}</div>
      ${d.english?`<div class="en" dir="ltr">${esc(d.english)}</div>`:''}
      ${d.purpose?`<div class="purp">🎯 ${esc(d.purpose)}</div>`:''}
      ${d.notes?`<div class="dnote">📝 ${esc(String(d.notes).replace(/\s+/g,' ').slice(0,90))}</div>`:''}
      ${d.created?`<div class="newp">🆕 נוסף ${esc(d.created)}${d.source?(' · '+esc(d.source)):''}</div>`:''}</div>
      <div class="meta">${unthankedCount(d)?`<span class="pill thx">🙏 ${unthankedCount(d)}</span>`:''}${hasOpenParnes(d)?'<span class="pill py">🌙</span>':''}${channelBadge(d)}${catPill(d.category)}${freqLabel(d.frequency)?`<span class="pill freq">🔁 ${freqLabel(d.frequency)}</span>`:''}${pill(d.tier)}${d.phone?`<span class="ph">${esc(d.phone)}</span>`:''}</div>
    </div>`).join('')||'<div class="empty">אין תוצאות</div>'}</div>`;
  const ds=document.getElementById('donsort'); if(ds){ds.value=donSort;ds.onchange=()=>{donSort=ds.value;render();};}
  const dc=document.getElementById('doncat'); if(dc)dc.onchange=()=>{catFlt=dc.value;render();};
  const cm=document.getElementById('catmgr'); if(cm)cm.onclick=openCatManager;
  const db2=document.getElementById('dupBtn'); if(db2)db2.onclick=openDupes;
  const afb=document.getElementById('addrFixBtn'); if(afb)afb.onclick=()=>{flt='addrfix';render();};
  const nab=document.getElementById('noAddrBtn'); if(nab)nab.onclick=()=>{flt='noaddr';NOADDR=null;render();};
  const npb=document.getElementById('noPhoneBtn'); if(npb)npb.onclick=()=>{flt='nophone';NOPHONE=null;NPLIM=15;render();};
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
// משיכת אנשי הקשר מגוגל — ממלאת רק שדות ריקים, אף פעם לא דורסת מה שכבר יש
async function pullGContacts(btn){
  const out=document.getElementById('gcout'), lbl=btn.textContent;
  const say=h=>{if(out)out.innerHTML=h;};
  btn.disabled=true;btn.textContent='מתחבר לגוגל…';
  const r=await api('POST','/api/contacts/pull',{});
  if(!r||!r.ok){
    btn.disabled=false;btn.textContent=lbl;
    say(r&&r.error==='not_configured'?'❌ המייל לא מוגדר בשרת.':'❌ שגיאה: '+((r&&(r.detail||r.error))||''));
    return;
  }
  for(let i=0;i<450;i++){
    await new Promise(res=>setTimeout(res,2000));
    let s;try{s=await api('GET','/api/contacts/pull/status');}catch(e){continue;}
    if(!s)continue;
    if(s.running){btn.textContent=s.found?('משלים… '+(s.scanned||0)+'/'+s.found):'מוריד אנשי קשר…';continue;}
    btn.disabled=false;btn.textContent=lbl;
    if(s.error){say('❌ '+esc(s.error)+'<br>אם גוגל חוסמת — שלח לי ייצוא CSV של אנשי הקשר ואמלא ממנו.');return;}
    const z=s.result||{};const f=z.filled||{};
    say(`✅ נמצאו ${z.cards||0} אנשי קשר · עודכנו ${z.donors||0} כרטיסים —
      ${f.addr||0} כתובות, ${f.phone||0} טלפונים, ${f.email||0} מיילים.
      ${z.unmatched_total?('<br>⚠️ '+z.unmatched_total+' אנשי קשר עם כתובת שלא הצלחתי לשייך לתורם.'):''}`);
    NOADDR=null; await load(); render();
    return;
  }
  btn.disabled=false;btn.textContent=lbl;
  say('המשיכה עדיין רצה ברקע — בדוק שוב בעוד רגע.');
}
// קובץ אנשי קשר של גוגל — נקרא כאן ונשלח לשרת להשלמת שדות ריקים בלבד
async function uploadContactsCsv(inp){
  const f=inp.files&&inp.files[0]; if(!f)return;
  const out=document.getElementById('gcout'), lbl=document.getElementById('gccsvbtn');
  const say=h=>{if(out)out.innerHTML=h;};
  const t0=lbl?lbl.firstChild.nodeValue:'';
  if(lbl)lbl.firstChild.nodeValue='קורא את הקובץ…';
  let text='';
  try{ text=await f.text(); }catch(e){ say('❌ לא הצלחתי לקרוא את הקובץ'); if(lbl)lbl.firstChild.nodeValue=t0; return; }
  inp.value='';
  if(lbl)lbl.firstChild.nodeValue='משלים כתובות…';
  let r=null;
  try{ r=await api('POST','/api/contacts/csv',{text}); }catch(e){ r=null; }
  if(lbl)lbl.firstChild.nodeValue=t0;
  if(!r||!r.ok){
    const why={empty:'הקובץ ריק',no_contacts:'לא נמצאו אנשי קשר בקובץ',
               parse:'לא הצלחתי לפרק את הקובץ'}[r&&r.error]||((r&&(r.detail||r.error))||'שגיאה');
    say('❌ '+esc(why)+'<br>אפשר להעלות <b>Google CSV</b> מ-contacts.google.com, או קובץ <b>VCF</b> שייצאת מהטלפון (הגדרות אנשי קשר ← ייבוא/ייצוא).');
    return;
  }
  const fl=r.filled||{};
  say(`✅ נקראו ${r.cards||0} אנשי קשר (${r.people||0} אנשים) · עודכנו ${r.donors||0} כרטיסים —
    ${fl.addr||0} כתובות, ${fl.phone||0} טלפונים, ${fl.email||0} מיילים${r.kvittel?(', '+r.kvittel+' קוויטל'):''}${r.notes?(', '+r.notes+' הערות'):''}.
    ${r.unmatched_total?('<br>⚠️ '+r.unmatched_total+' אנשי קשר עם כתובת שלא שויכו לתורם (רובם לא תורמים).'):''}`);
  NOADDR=null; await load(); render();
}
// מי אין לו כתובת בכלל — עם הצעה מוכנה איפה שיש, ובלחיצה אחת נכנסת לכרטיס
let NOADDR=null;
let NOPHONE=null, NPLIM=15;
// מסך השלמת טלפונים — לכל תורם בלי טלפון מוצעים אנשי הקשר עם אותו שם משפחה,
// ובלחיצה אחת מאשרים או דוחים. במקום לענות על שאלות בצ׳אט.
async function renderNoPhone(){
  view.innerHTML='<div class="cnt">טוען הצעות…</div>';
  if(!NOPHONE){ try{ NOPHONE=await api('GET','/api/audit/phones'); }catch(e){ NOPHONE={ok:false}; } }
  const R=NOPHONE||{};
  if(!R.ok){view.innerHTML=`<div class="misshead">📞 השלמת טלפונים</div><div class="empty">לא הצלחתי לטעון${R.error?(' — '+esc(R.error)):''}</div><button class="btn" id="npback" style="margin:10px 2px">→ חזרה</button>`;
    document.getElementById('npback').onclick=()=>{flt='';render();};return;}
  const all=(R.rows||[]).filter(r=>matchQ(r.name));
  const rows=all.slice(0,NPLIM);        // מציגים מנה קטנה בכל פעם — קל יותר לעבור על זה בטלפון
  view.innerHTML=`<div class="misshead">📞 השלמת טלפונים</div>
    <div class="submuted">לכל תורם מוצעים אנשי קשר עם אותו שם משפחה. ✓ = זה הוא · ✕ = לא הוא.<br>
      ${R.total||0} תורמים בלי טלפון, מתוכם ${all.length} עם הצעה.</div>
    <button class="btn ghost" id="npback" style="margin:8px 2px">→ חזרה לתורמים</button>
    <div class="list">${rows.map(r=>`<div class="npcard" data-did="${r.id}">
      <div class="nm">${esc(r.name)}${r.tot?` <small style="color:var(--yes)">$${(+r.tot).toLocaleString('en-US')}</small>`:''}${r.tier==='יששכר_זבולון'?' <small>יש"ז</small>':''}</div>
      ${r.email?`<div class="miss2">${esc(r.email)}</div>`:''}
      ${r.cands.map(c=>`<div class="npcand">
        <button class="btn sm npyes" data-did="${r.id}" data-ph="${esc(c.phone)}" data-em="${esc(c.email||'')}">✓</button>
        <button class="del npno" data-did="${r.id}" data-ph="${esc(c.phone)}">✕</button>
        <span class="npi"><b dir="ltr">${esc(c.phone)}</b><br><small>${esc(c.name)}${c.sure?' · <b style="color:var(--yes)">שם פרטי תואם</b>':''}</small></span>
      </div>`).join('')}
      <button class="btn sm ghost npskip" data-did="${r.id}" style="margin-top:5px">🚫 אף אחד מהם</button>
    </div>`).join('')||'<div class="empty">אין הצעות פתוחות 🎉</div>'}</div>
    ${all.length>rows.length?`<button class="btn ghost" id="npmore" style="width:100%;margin:8px 2px">↓ עוד ${Math.min(15,all.length-rows.length)} (נשארו ${all.length-rows.length})</button>`:''}`;
  const nm2=document.getElementById('npmore'); if(nm2)nm2.onclick=()=>{NPLIM+=15;renderNoPhone();};
  document.getElementById('npback').onclick=()=>{flt='';render();};
  const drop=(did,ph)=>{const r=(NOPHONE.rows||[]).find(x=>x.id==did); if(!r)return;
    if(ph===null){NOPHONE.rows=NOPHONE.rows.filter(x=>x.id!=did);}
    else{r.cands=r.cands.filter(c=>c.phone!==ph); if(!r.cands.length)NOPHONE.rows=NOPHONE.rows.filter(x=>x.id!=did);}
    renderNoPhone();};
  view.querySelectorAll('.npyes').forEach(b=>b.onclick=async e=>{e.stopPropagation();b.disabled=true;
    await api('POST','/api/audit/phones',{donor_id:+b.dataset.did,phone:b.dataset.ph,email:b.dataset.em||''});
    const d=DB.find(x=>x.id==b.dataset.did); if(d){d.phone=b.dataset.ph; if(!d.email&&b.dataset.em)d.email=b.dataset.em;}
    toast('נשמר ✓'); drop(+b.dataset.did,null);});
  view.querySelectorAll('.npno').forEach(b=>b.onclick=async e=>{e.stopPropagation();b.disabled=true;
    await api('POST','/api/audit/phones',{donor_id:+b.dataset.did,phone:b.dataset.ph,reject:1});
    drop(+b.dataset.did,b.dataset.ph);});
  view.querySelectorAll('.npskip').forEach(b=>b.onclick=async e=>{e.stopPropagation();b.disabled=true;
    await api('POST','/api/audit/phones',{donor_id:+b.dataset.did,skip:1});
    drop(+b.dataset.did,null);});
  view.querySelectorAll('.npcard .nm').forEach(el=>el.onclick=()=>{const d=DB.find(x=>x.id==el.closest('.npcard').dataset.did);if(d)openDonor(d);});
}
async function renderNoAddr(){
  chips.innerHTML='';
  if(!NOADDR){
    view.innerHTML='<div class="hintxt">בודק מי חסר כתובת…</div>';
    try{NOADDR=await api('GET','/api/audit/noaddr');}catch(e){NOADDR={people:[],count:0,with_suggest:0};}
  }
  const all=(NOADDR.people||[]).filter(p=>matchQ(p.name+' '+p.english+' '+p.phone));
  const withS=all.filter(p=>(p.suggest||[]).length), without=all.filter(p=>!(p.suggest||[]).length);
  const card=p=>`<div class="narow" data-id="${p.id}">
    <div class="nahd"><b class="nago" data-id="${p.id}">${esc(p.name)} ↗</b>
      <span class="namoney">${p.total?('$'+p.total.toLocaleString('en-US')):''}</span></div>
    <div class="nasub">${p.phone?('📞 '+esc(p.phone)):'<span style="color:var(--no)">בלי טלפון</span>'}${p.email?(' · ✉️ '+esc(p.email)):''}</div>
    ${(p.suggest||[]).map((s,i)=>`<div class="nasug">
      <div class="nasugt">💡 ${esc(s.src)}${s.who?(' · '+esc(s.who)):''}${s.phone?(' · 📞 '+esc(s.phone)):''}</div>
      <div class="nasuga">${esc(s.addr)}</div>
      <div class="dupacts"><button class="btn sm nause" data-id="${p.id}" data-i="${i}">✔️ קבע כתובת זו</button>
        <button class="btn sm ghost nanot dupnot" data-id="${p.id}" data-i="${i}">✕ לא מתאים</button></div></div>`).join('')}
  </div>`;
  view.innerHTML=`<button class="btn ghost" id="nback" style="width:100%;margin-bottom:8px">⬅ חזרה לרשימת התורמים</button>
    <div class="rbtitle">🏠 תורמים בלי כתובת — ${NOADDR.count||0}</div>
    <button class="btn" id="gcpull" style="width:100%;background:#1a73e8;border-color:#1a73e8;margin-bottom:6px">📇 משוך אנשי קשר מגוגל והשלם כתובות</button>
    <label class="btn" id="gccsvbtn" style="width:100%;background:var(--yes);border-color:var(--yes);margin-bottom:6px;display:block;text-align:center;cursor:pointer">📄 העלה אנשי קשר — CSV מגוגל או VCF מהטלפון
      <input type="file" id="gccsv" accept=".csv,.vcf,.vcard,text/csv,text/vcard,text/x-vcard" hidden></label>
    <div id="gcout" class="hintxt" style="margin:0 2px 10px">${(NOADDR.with_suggest||0)} מהם יש לי הצעה מוכנה מייצוא אנשי הקשר או מכתובת החיוב. לשאר אין כתובת באף קובץ שקיבלתי — לחץ על הכפתור כדי למשוך ישירות מאנשי הקשר בגוגל.</div>
    ${withS.length?`<div class="misshead">💡 יש הצעה — ${withS.length}</div>${withS.map(card).join('')}`:''}
    ${without.length?`<div class="misshead">אין שום נתון — ${without.length}</div>${without.map(card).join('')}`:''}`;
  document.getElementById('nback').onclick=()=>{flt='';render();};
  const gp=document.getElementById('gcpull'); if(gp)gp.onclick=()=>pullGContacts(gp);
  const gc=document.getElementById('gccsv'); if(gc)gc.onchange=()=>uploadContactsCsv(gc);
  view.querySelectorAll('.nago').forEach(b=>b.onclick=()=>{const d=DB.find(x=>x.id==b.dataset.id);if(d)openDonor(d);});
  view.querySelectorAll('.nanot').forEach(b=>b.onclick=async()=>{
    const p=(NOADDR.people||[]).find(x=>x.id==b.dataset.id); if(!p)return;
    const s=p.suggest[+b.dataset.i]; if(!s)return;
    b.disabled=true;
    p.suggest.splice(+b.dataset.i,1);
    if(!p.suggest.length)NOADDR.with_suggest=Math.max(0,(NOADDR.with_suggest||1)-1);
    renderNoAddr(); toast('ההצעה נדחתה — לא תוצע שוב');
    try{ await api('POST','/api/addr/reject',{donor_id:p.id,addr:s.addr}); }catch(e){}
  });
  view.querySelectorAll('.nause').forEach(b=>b.onclick=async()=>{
    const p=(NOADDR.people||[]).find(x=>x.id==b.dataset.id); if(!p)return;
    const s=p.suggest[+b.dataset.i]; if(!s)return;
    b.disabled=true;b.textContent='שומר…';
    const body={addr:s.addr};
    const d=DB.find(x=>x.id==p.id);
    if(s.phone&&!(d&&(d.phone||'').trim()))body.phone=s.phone;
    await api('PUT','/api/donor/'+p.id,body);
    NOADDR.people=NOADDR.people.filter(x=>x.id!=p.id); NOADDR.count--; NOADDR.with_suggest--;
    toast('הכתובת נשמרה ✓');
    await load(); render();
  });
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
// סיכום קצר בעברית של מה עבר במיזוג — "7 תרומות · 2 שמות קוויטל"
const MOVEDHE={donations:'תרומות',prayers:'שמות קוויטל',parnes:'פרנס יום',tasks:'משימות',
  contacts_log:'רישומי קשר',partners:'אברכים',transactions:'חיובים',pledges:'התחייבויות',
  building:'בניין',recon:'שורות חיוב',intake:'בקשות מהאתר'};
function movedTxt(moved){
  const p=Object.entries(moved||{}).filter(([,v])=>v).map(([k,v])=>v+' '+(MOVEDHE[k]||k));
  return p.length?('— '+p.join(' · ')):'';
}
// מיזוג מקומי — מעביר את הרשומות על המסך מיד, באותו היגיון של השרת, כדי שלא נחכה לרענון
const MERGE_TABLES=['donations','prayers','parnes','tasks','contacts','partners','transactions','pledges','building'];
function mergeLocal(keepId,dropId,tot){
  const k=DB.find(x=>x.id===keepId), d=DB.find(x=>x.id===dropId);
  if(!k||!d)return;
  MERGE_TABLES.forEach(t=>{
    const src=d[t]||[]; if(!src.length)return;
    k[t]=(k[t]||[]).concat(src);
    if(tot)tot[t==='contacts'?'contacts_log':t]=(tot[t==='contacts'?'contacts_log':t]||0)+src.length;
  });
  ['first','english','business','addr','tier','category','purpose','amount','region','country',
   'zip','city','channel','pay_status','labels','aliases','iz_note','months','last_active']
    .forEach(c=>{ if(!String(k[c]||'').trim()&&String(d[c]||'').trim())k[c]=d[c]; });
  const ph=[...new Set(splitPhones(k.phone).concat(splitPhones(d.phone)))].filter(Boolean);
  if(ph.length)k.phone=ph.join(' / ');
  const em=[...new Set(splitEmails(k.email).concat(splitEmails(d.email)))].filter(Boolean);
  if(em.length)k.email=em.join(', ');
  const dn=String(d.notes||'').trim();
  if(dn&&!String(k.notes||'').includes(dn))k.notes=(String(k.notes||'').trim()+' · '+dn).replace(/^ · /,'');
  DB=DB.filter(x=>x.id!==dropId);
}
function openDupes(){
  const paint=()=>{
    const gs=findDupes();
    const score=d=>((d.donations||[]).length*3+(d.partners||[]).length*3+(d.parnes||[]).length*2+(d.phone?1:0)+(d.email?1:0)+(amtNum(d.amount)?1:0)+(d.category?1:0)+(d.english?1:0));
    sheet.innerHTML=`<button class="x" id="cx">✕</button>
      <h2>🔀 מיזוג כרטיסים כפולים</h2>
      <div class="hintxt">${gs.length?'בחר את הכרטיס להשאיר (מסומן אוטומטית המלא ביותר) — כל התרומות, הפרנס והאברכים יעברו אליו, והכפול יימחק.':'לא נמצאו כפולים 🎉'}</div>
      <div id="dupwrap">${gs.map((grp,gi)=>{const best=grp.slice().sort((a,b)=>score(b)-score(a))[0];
        return `<div class="dupgrp"><div class="dupname">${esc(grp[0].last+' '+grp[0].first)}${grp.why?(' <span class="dupfz'+(grp.why[0]==='📧'?' strong':'')+'">'+esc(grp.why)+'</span>'):''}</div>${grp.map(d=>{
          const nd=(d.donations||[]).length,np=(d.partners||[]).length,npar=(d.parnes||[]).length;
          return `<label class="dupcard"><input type="radio" name="keep${gi}" value="${d.id}" ${d.id===best.id?'checked':''}>
            <div class="dupinfo">
            <div class="dupwho">${esc(d.last||'')} <span>${esc(d.first||'')}</span>${d.id===best.id?' <span class="dupkeep">מומלץ להשאיר</span>':''}</div>
            <div class="dupmeta2">כרטיס #${d.id} ${catPill(d.category)} ${pill(d.tier)}${d.english?(' · <span dir="ltr">'+esc(d.english)+'</span>'):''}</div>
            <div class="dupmeta">${d.phone?('📞 '+esc(d.phone)+' '):''}${d.email?('✉️ '+esc(d.email)+' '):''}${amtNum(d.amount)?('💵 '+esc(d.amount)+' '):''}</div>
            ${d.addr?`<div class="dupmeta">🏠 ${esc(d.addr)}</div>`:''}
            <div class="dupmeta2">${nd} תרומות · ${npar} פרנס · ${np} אברכים</div></div></label>`;
        }).join('')}<div class="dupacts"><button class="btn sm dupmerge" data-gi="${gi}" data-ids="${grp.map(d=>d.id).join(',')}">מזג ✓</button>
          <button class="btn sm ghost dupnot" data-ids="${grp.map(d=>d.id).join(',')}">✕ לא אותו אדם</button></div></div>`;
      }).join('')||'<div class="empty">אין כפולים</div>'}</div>`;
    sheet.querySelectorAll('.dupmerge').forEach(b=>b.onclick=async()=>{
      const gi=b.dataset.gi;
      const ids=(b.dataset.ids||'').split(',').map(Number).filter(Boolean);
      const sel=sheet.querySelector(`input[name="keep${gi}"]:checked`);
      if(!sel){toast('בחר כרטיס להשאיר');return;}
      const keep=+sel.value, drops=ids.filter(id=>id!==keep);
      if(!drops.length){toast('אין מה למזג');return;}
      b.disabled=true;
      const tot={};
      drops.forEach(id=>mergeLocal(keep,id,tot));   // מיזוג מיידי על המסך — השרת מתעדכן ברקע
      paint(); toast('מוזג ✓ '+movedTxt(tot));
      try{
        for(const id of drops){
          const r=await api('POST','/api/merge',{keep,drop:id});
          if(!r||!r.ok)throw new Error((r&&(r.detail||r.error))||'השרת סירב');
        }
      }catch(e){
        toast('❌ המיזוג לא נשמר: '+(e&&e.message||e));
        await load(); paint(); return;
      }
      load().then(paint);                            // רענון שקט, בלי להשהות את המסך
    });
    sheet.querySelectorAll('.dupnot').forEach(b=>b.onclick=async()=>{
      const ids=(b.dataset.ids||'').split(',').map(Number).filter(Boolean);
      if(ids.length<2)return;
      b.disabled=true;
      for(let i=0;i<ids.length;i++)for(let j=i+1;j<ids.length;j++)NOTDUPE.add(ndKey(ids[i],ids[j]));
      paint(); toast('סומן: לא אותו אדם ✓');
      try{ await api('POST','/api/notdupe',{ids}); }
      catch(e){ toast('❌ לא נשמר: '+(e&&e.message||e)); }
    });
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
    else openDonor(nd,'details');
  };
}
function hq(s){return String(s||'').replace(/\u05f4/g,'"').replace(/\u05f3/g,"'");}
// ברירת המחדל היא תמיד השנה העברית הנוכחית (מהשרת) — שנה שעברה לא נבחרת לבד אף פעם
function heYearOpts(sel){sel=hq(sel)||HEBYEAR;let ys=['תשפ"ד','תשפ"ה','תשפ"ו','תשפ"ז','תשפ"ח','תשפ"ט','תש"צ'];
  if(sel&&!ys.includes(sel))ys.unshift(sel);
  if(!ys.includes(sel))sel=HEBYEAR;
  return ys.map(y=>`<option ${y===sel?'selected':''}>${y}</option>`).join('');}
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

// 'p'=עבר · 'c'=נגבה ידנית · 'h'=טופל/הוסר · '-'=חסר
function _firstPaid(m){for(let i=0;i<m.length;i++)if(m[i]==='p'||m[i]==='c')return i;return -1;}
function gaps(m){if(!m)return [];const f=_firstPaid(m);if(f<0)return[];const g=[];for(let i=f;i<=GLAST;i++)if(m[i]!=='p'&&m[i]!=='c'&&m[i]!=='h')g.push(i);return g;}
function monthGrid(m){if(!m)return '';const f=_firstPaid(m);return `<div class="mgrid">${MON.map((l,i)=>{let c;const ch=m[i];if(ch==='p'||ch==='c')c='gp';else if(ch==='h')c='gh';else if(f>=0&&i>=f&&i<=GLAST)c='gx';else c='gn';return `<div class="mc ${c}"><span>${l}</span></div>`;}).join('')}</div>`;}
function setMonthChar(m,i,ch){const a=(m||'------------').padEnd(12,'-').split('');a[i]=ch;return a.join('');}

let cardTab='details';
function tierOpts(d){
  const cur=(d&&d.tier)||'';
  const isOcc=!cur && hasOccKv(d);
  const base=['','יששכר_זבולון','קוויטל_101','קוויטל_שבועי'].map(t=>`<option value="${t}" ${(t===cur&&!isOcc)?'selected':''}>${t?({'יששכר_זבולון':'יששכר־זבולון','קוויטל_101':'כל לילה','קוויטל_שבועי':'שבועי'}[t]):'— ללא —'}</option>`).join('');
  const occLbl=isOcc?('מזדמנים'+(d.kv_month?(' · '+d.kv_month+(d.kv_year?(' '+d.kv_year):'')):'')):'מזדמנים';
  return base+`<option value="__occ" ${isOcc?'selected':''}>${occLbl}</option>`;
}
// "מזדמנים" בדרגת הקוויטל שייך רק למי שבאמת יש לו קוויטל — שמות לתפילה או חודש שנקבע.
// תורם מזדמן בלי קוויטל נשאר "— ללא —", ובלי שורת חודש/שנה.
function hasOccKv(d){return !!(d&&d.category==='מזדמן'&&!d.tier&&((d.prayers||[]).length||String(d.kv_month||'').trim()));}
// שינוי דרגת קוויטל — כולל הבחירה המיוחדת "מזדמנים" ששואלת לאיזה חודש/שנה
async function applyTierSelect(d,selId){
  const el=document.getElementById(selId||'f_tier');if(!el)return;const val=el.value;
  if(val==='__occ'){
    const pick=await uiPickMonth('לאיזה חודש ושנה עברית לשייך את הקוויטל של התורם המזדמן?',d.kv_month||'תשרי',d.kv_year||HEBYEAR);
    if(!pick){el.innerHTML=tierOpts(d);return;}   // בוטל — החזר לבחירה הקודמת
    d.category='מזדמן';d.tier='';d.kv_month=pick.month;d.kv_year=pick.year;
    await api('PUT','/api/donor/'+d.id,{category:'מזדמן',tier:'',kv_month:pick.month,kv_year:pick.year});
    toast('שויך למזדמנים · '+pick.month+' '+pick.year+' ✓');
  }else{
    d.tier=val;
    await api('PUT','/api/donor/'+d.id,{tier:val});
    toast('נשמר ✓');
  }
  renderCard(d);
  if(tab==='donors')renderDonors();
}
function wireFields(d,flds){flds.forEach(fld=>{const el=document.getElementById('f_'+fld);if(!el)return;el.onchange=async e=>{d[fld]=e.target.value;await api('PUT','/api/donor/'+d.id,{[fld]:e.target.value});toast('נשמר ✓');if(fld==='last'||fld==='first'){document.getElementById('cardTitle').textContent=(d.last+' '+d.first).trim();}if(['last','first','tier','category','region','channel'].includes(fld)&&tab==='donors')renderDonors();};});}

function openDonor(d,startTab){
  cardTab=startTab||'details';
  const nopen=(d.tasks||[]).filter(t=>!t.done||t.done==0).length;
  sheet.innerHTML=`<button class="x" id="cx">✕</button>
    <h2 id="cardTitle">${esc(d.last)} ${esc(d.first)}</h2>
    <div class="cardsub"><span class="cardnum">כרטיס #${d.id}</span> ${catPill(d.category)} ${d.tier==='יששכר_זבולון'?`<span class="izchip" id="izHeadLink" title="לחץ לראות אברך ושותף">${pill(d.tier)} 👥</span>`:pill(d.tier)} ${d.english?`<span class="ensm" dir="ltr">${esc(d.english)}</span>`:''}</div>
    <div class="ctabs">
      <button class="ctab" data-c="details">🏠 ראשי${pendCount(d)?` <b class="badge">${pendCount(d)}</b>`:''}</button>
      <button class="ctab" data-c="info">📇 פרטים</button>
      <button class="ctab" data-c="kvittel">🕯️ קוויטל${(d.intake_pending||[]).length?` <b class="badge">${(d.intake_pending||[]).length}</b>`:''}</button>
      <button class="ctab" data-c="building">🏛️ בניין${(d.building||[]).length?` <b class="badge">${(d.building||[]).length}</b>`:''}</button>
      <button class="ctab" data-c="contact">📞 קשר</button>
      <button class="ctab" data-c="tasks">📋 משימות${nopen?` <b class="badge">${nopen}</b>`:''}</button>
    </div>
    <div id="cardBody"></div>`;
  ov.classList.add('show');
  try{localStorage.setItem('kc_donor',d.id);}catch(e){}
  document.getElementById('cx').onclick=()=>{ov.classList.remove('show');try{localStorage.removeItem('kc_donor');}catch(e){}};
  sheet.querySelectorAll('.ctab').forEach(b=>b.onclick=()=>{cardTab=b.dataset.c;renderCard(d);});
  const izh=document.getElementById('izHeadLink');if(izh)izh.onclick=()=>{cardTab='details';renderCard(d);};
  renderCard(d);
}
function renderCard(d){
  sheet.querySelectorAll('.ctab').forEach(b=>b.classList.toggle('on',b.dataset.c===cardTab));
  const body=document.getElementById('cardBody');
  if(cardTab==='details') return cardDetails(d,body);
  if(cardTab==='info') return cardInfo(d,body);
  if(cardTab==='kvittel') return cardKvittel(d,body);
  if(cardTab==='building') return cardBuilding(d,body);
  if(cardTab==='contact') return cardContact(d,body);
  if(cardTab==='tasks') return cardTasks(d,body);
}
function cardTasks(d,body){
  body.innerHTML=`${contactBtns(d)?`<div class="cardcbar">${contactBtns(d)}</div>`:''}
    <div class="sec"><h3>➕ משימה חדשה</h3>
      <input id="ct_note" placeholder="✍️ מה צריך לעשות (למשל: להתפלל עליו, לתקן פרטים, לחזור)…" autocomplete="off">
      <div class="two" style="margin-top:6px"><label class="fld"><span>סוג</span><select id="ct_kind">${taskKindOpts('other')}</select></label>
        <label class="fld"><span>תאריך</span><input id="ct_date" type="date" value="${todayStr()}"></label></div>
      <div class="two" style="margin-top:6px"><label class="fld"><span>מי מבצע</span><select id="ct_who">${assigneeOpts('')}</select></label><label class="fld"><span>&nbsp;</span><button class="btn" id="ct_add" style="width:100%">➕ הוסף משימה</button></label></div>
      <div class="hintxt">כל משימה נכנסת גם ללשונית "משימות" הראשית וליומן Google.</div></div>
    <div class="sec"><h3>📋 המשימות של ${esc((d.last+' '+d.first).trim())}</h3><div id="ct_list"></div></div>`;
  renderCardTasks(d);
  addMic(document.getElementById('ct_note'));
  wireKindSel(document.getElementById('ct_kind'));
  document.getElementById('ct_add').onclick=async()=>{
    const note=document.getElementById('ct_note').value.trim(),kind=await kindValue(document.getElementById('ct_kind')),date=document.getElementById('ct_date').value,who=document.getElementById('ct_who').value;
    if(!kind){return;}if(!note){toast('כתוב מה צריך לעשות');return;}if(!date){toast('בחר תאריך');return;}
    const r=await api('POST','/api/task',{donor_id:d.id,due_date:date,kind:kind,note:note,assignee:who});
    d.tasks=d.tasks||[];d.tasks.push({id:r.id,donor_id:d.id,due_date:date,kind:kind,note:note,assignee:who,done:0});
    document.getElementById('ct_note').value='';renderCardTasks(d);toast('נוספה משימה ✓');checkReminders();};
}
function renderCardTasks(d){
  const el=document.getElementById('ct_list');if(!el)return;const td=todayStr();
  const open=(d.tasks||[]).filter(t=>!t.done||t.done==0).sort((a,b)=>(a.due_date||'9999').localeCompare(b.due_date||'9999'));
  el.innerHTML=open.map(t=>{const over=t.due_date&&t.due_date<td,icon=kindLabel(t.kind).split(' ')[0];
    return `<div class="cttask" data-id="${t.id}"><button class="tdone ctdone" data-id="${t.id}">✓</button>
      <div class="cti"><div>${icon} ${esc(t.note||'')}</div><div class="ctmeta ${over?'over':''}">${esc(t.due_date||'—')} ${whoChipHTML(t,'data-rwho="'+t.id+'"')}</div></div>
      <button class="tedit ctedit" data-id="${t.id}" title="ערוך משימה">✏️ ערוך</button><button class="del ctdel" data-id="${t.id}">🗑</button></div>
    <div class="teditpanel hidden" data-ctp="${t.id}">
      <label class="fld"><span>✏️ טקסט המשימה</span><textarea class="ctn" data-id="${t.id}" rows="3" placeholder="מה צריך לעשות">${esc(t.note||'')}</textarea></label>
      <div class="two" style="margin-top:6px"><label class="fld"><span>סוג</span><select class="ctk" data-id="${t.id}">${taskKindOpts(t.kind)}</select></label>
        <label class="fld"><span>תאריך</span><input type="date" class="ctd" data-id="${t.id}" value="${esc(t.due_date||'')}"></label></div>
      <label class="fld" style="margin-top:6px"><span>👤 מי מבצע</span><select class="ctw" data-id="${t.id}">${assigneeOpts(t.assignee)}</select></label>
      <button class="btn sm ctsave" data-id="${t.id}" style="width:100%;margin-top:8px">💾 שמור שינויים</button>
    </div>`;}).join('')||'<div class="hintxt">אין משימות פתוחות. הוסף למעלה.</div>';
  el.querySelectorAll('.ctk').forEach(wireKindSel);
  addMics(el,['.ctn']);
  el.querySelectorAll('.ctedit').forEach(b=>b.onclick=e=>{e.stopPropagation();const p=el.querySelector('.teditpanel[data-ctp="'+b.dataset.id+'"]');if(p)p.classList.toggle('hidden');});
  el.querySelectorAll('.ctsave').forEach(b=>b.onclick=async()=>{
    const t=(d.tasks||[]).find(x=>x.id==b.dataset.id);if(!t)return;
    const kind=await kindValue(el.querySelector('.ctk[data-id="'+b.dataset.id+'"]'));if(!kind)return;
    const note=el.querySelector('.ctn[data-id="'+b.dataset.id+'"]').value.trim();
    const date=el.querySelector('.ctd[data-id="'+b.dataset.id+'"]').value;
    const who=el.querySelector('.ctw[data-id="'+b.dataset.id+'"]').value;
    b.disabled=true;
    await api('PUT','/api/task/'+t.id,{note:note,kind:kind,due_date:date,assignee:who});
    t.note=note;t.kind=kind;t.due_date=date;t.assignee=who;
    renderCardTasks(d);renderReminders(d);checkReminders();toast('נשמר ✓');});
  el.querySelectorAll('[data-rwho]').forEach(b=>b.onclick=async e=>{e.stopPropagation();b.disabled=true;await flipWho(b.dataset.rwho);renderCardTasks(d);});
  el.querySelectorAll('.ctdone').forEach(b=>b.onclick=async()=>{const t=(d.tasks||[]).find(x=>x.id==b.dataset.id);if(!t)return;await api('PUT','/api/task/'+t.id,{done:1});t.done=1;renderCardTasks(d);checkReminders();toastUndo('בוצע ✓',async()=>{await api('PUT','/api/task/'+t.id,{done:0});t.done=0;renderCardTasks(d);checkReminders();});});
  el.querySelectorAll('.ctdel').forEach(b=>b.onclick=async()=>{if(!await uiConfirm('למחוק את המשימה?'))return;await api('DELETE','/api/task/'+b.dataset.id);d.tasks=(d.tasks||[]).filter(x=>x.id!=b.dataset.id);renderCardTasks(d);checkReminders();toast('נמחק');});
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
// סיכום לפי ייעוד — כמה נתרם לכל דבר, השנה ובסך הכל
// "עבור מה" שמוצג בראש הכרטיס — הייעוד שנקבע לתורם, ואם לא נקבע אז לפי התרומות בפועל
function purposeText(d){
  // תורם שנותן לכמה דברים — מציגים את כולם, לא רק אחד.
  // קודם ההתחייבויות החוזרות (יש"ז + התחייבויות חודשיות), ואז ייעוד שנקבע ידנית.
  const parts=[];
  try{const s=izSummary(d); if(s.monthly>0)parts.push('יששכר־זבולון');}catch(e){}
  (d.pledges||[]).filter(p=>+p.monthly).forEach(p=>{
    const c=String(p.category||'').trim(); if(c&&parts.indexOf(c)<0)parts.push(c);});
  const own=String(d.purpose||'').trim();
  if(own&&parts.indexOf(own)<0)parts.push(own);
  if(parts.length)return parts.join(' · ');
  const m={};
  (d.donations||[]).forEach(x=>{const c=String(x.category||'').trim();if(c)m[c]=(m[c]||0)+amtNum(x.amount);});
  (d.parnes||[]).filter(p=>p.status!=='suggested').forEach(p=>{const c=DAYKIND[p.kind]||'🌙 פרנס יום';m[c]=(m[c]||0)+amtNum(p.amount);});
  const l=Object.keys(m).sort((a,b)=>m[b]-m[a]);
  return l.length?(l.slice(0,3).join(' · ')+(l.length>3?' ועוד':'')):'';
}
// הערות חופשיות — שורה לכל הערה, אפשר להוסיף כמה שרוצים. נשמר בשדה ההערות של התורם
function noteList(d){return String(d.notes||'').split('\n').map(x=>x.trim()).filter(Boolean);}
function notesHTML(d){
  const l=noteList(d);
  return `<div class="notesbox"><div class="notesbox-t">📝 הערות</div>
    ${l.map((n,i)=>`<div class="noterow"><input class="nbtxt" data-i="${i}" value="${esc(n)}"><button class="del nbdel" data-i="${i}" title="מחק הערה">🗑</button></div>`).join('')}
    <div class="addrow"><input class="nbnew" placeholder="הוסף הערה — למשל: התחיל קדיש מא' תמוז תשפ״ו"><button class="btn sm nbadd">➕ הוסף</button></div></div>`;
}
function wireNotes(d,root){
  const box=root.querySelector('.notesbox'); if(!box)return;
  const save=async(l)=>{d.notes=l.join('\n');await api('PUT','/api/donor/'+d.id,{notes:d.notes});
    const w=document.createElement('div');w.innerHTML=notesHTML(d);box.replaceWith(w.firstElementChild);
    wireNotes(d,root);if(tab==='donors')renderDonors();};
  box.querySelectorAll('.nbtxt').forEach(inp=>inp.onchange=()=>{const l=noteList(d);
    const v=inp.value.trim(); if(v)l[+inp.dataset.i]=v; else l.splice(+inp.dataset.i,1); save(l);toast('נשמר ✓');});
  box.querySelectorAll('.nbdel').forEach(b2=>b2.onclick=async()=>{const l=noteList(d);l.splice(+b2.dataset.i,1);await save(l);toast('נמחק');});
  addMics(box,['.nbtxt','.nbnew']);
  const ni=box.querySelector('.nbnew'),na=box.querySelector('.nbadd');
  const add=async()=>{const v=ni.value.trim();if(!v){ni.focus();return;}await save(noteList(d).concat([v]));toast('נוספה הערה ✓');};
  na.onclick=add; ni.onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();add();}};
}
// כל ההתחייבויות החוזרות של התורם — הקבוע שבכרטיס, אברכי יש"ז והתחייבויות חודשיות
function monthlyHTML(d){
  const rows=[], cur=curSym(d);
  try{const s=izSummary(d); if(s.monthly>0)rows.push(['🤝 יששכר־זבולון',Math.round(s.monthly)]);}catch(e){}
  (d.pledges||[]).filter(p=>+p.monthly&&amtNum(p.amount)>0)
    .forEach(p=>rows.push(['🕯️ '+(p.category||'התחייבות'),amtNum(p.amount)]));
  if(!rows.length)return '';
  const tot=rows.reduce((s,r)=>s+r[1],0);
  const f=n=>cur+Math.round(n).toLocaleString('en-US');
  return `<div class="cattot"><div class="cattot-t">🔁 התחייבות חודשית קבועה</div>
    ${rows.map(r=>`<div class="catrow"><span>${esc(r[0])}</span><b>${f(r[1])}</b></div>`).join('')}
    ${rows.length>1?`<div class="catrow tot"><span>סה"כ לחודש</span><b>${f(tot)}</b></div>`:''}</div>`;
}
function catTotalsHTML(d){
  const cur=curSym(d), m={};
  const add=(c,amt,dt)=>{
    c=String(c||'').trim()||'ללא ייעוד';
    if(!m[c])m[c]={c,all:0,year:0};
    m[c].all+=amt;
    if(String(dt||'').slice(0,4)===String(GREGYEAR))m[c].year+=amt;
  };
  (d.donations||[]).forEach(x=>add(x.category,amtNum(x.amount),x.date));
  (d.parnes||[]).filter(p=>p.status!=='suggested'&&+p.paid).forEach(p=>
    add(DAYKIND[p.kind]||'🌙 פרנס יום',amtNum(p.amount),p.night_date));
  const rows=Object.values(m).filter(x=>x.all).sort((a,b)=>b.all-a.all);
  if(!rows.length)return '';
  const tA=rows.reduce((s,x)=>s+x.all,0), tY=rows.reduce((s,x)=>s+x.year,0);
  const f=n=>cur+Math.round(n).toLocaleString('en-US');
  return `<div class="cattot"><div class="cattot-t">🎯 כמה נתרם לכל ייעוד</div>
    <div class="catrow head"><span>ייעוד</span><b>${GREGYEAR}</b><b>הכל</b></div>
    ${rows.map(x=>`<div class="catrow"><span>${esc(x.c)}</span><b>${x.year?f(x.year):'—'}</b><b>${f(x.all)}</b></div>`).join('')}
    <div class="catrow tot"><span>סה"כ</span><b>${f(tY)}</b><b>${f(tA)}</b></div></div>`;
}
function cardDetails(d,body){
  const cl=CATS.includes(d.category||'')?CATS:CATS.concat([d.category]);
  const sel=cl.map(c=>`<option ${c===(d.category||'')?'selected':''} value="${esc(c)}">${esc(catLabel(c))}</option>`).join('');
  const f=(k,v,dir)=>v?`<div class="rf"><div class="k">${k}</div><div class="v" ${dir?'dir="ltr"':''}>${esc(v)}</div></div>`:'';
  const gc=gaps(d.months).length, pend=(d.pledges||[]).filter(p=>p.status!=='נתן').length;
  const dt=donorTotals(d), curd=curSym(d);
  // פירוט מה תרם ועבור מה — ישירות במסך הראשי
  const gitems=[];
  (d.parnes||[]).forEach(p=>gitems.push({k:p.night_date||'',amt:amtNum(p.amount),what:(DAYKIND[p.kind]||'🌙 פרנס')+(p.date_text?(' · '+p.date_text):'')+(p.hyear?(' '+p.hyear):''),ded:p.dedication||'',parnes:true,pid:p.id,paid:+p.paid,rm:p.method||d.channel||''}));
  (d.donations||[]).forEach(x=>gitems.push({k:x.date||'',amt:amtNum(x.amount),what:'',when:x.date?gregLabel(x.date):'',
    ded:giveNote(x),rm:x.method||'',don:true,did:x.id,cat:x.category||'',note:x.note||''}));
  (d.partners||[]).filter(p=>p.active!=0).forEach(p=>{const co=avCoHolders(p);gitems.push({k:'',amt:amtNum(p.amount),what:'🤝 יש"ז — '+(p.avreich||'')+(co.length?(' · בשותפות עם '+co.map(x=>x.name).join(', ')):''),ded:'',rm:p.method||''});});
  gitems.sort((a,b)=>String(b.k||'').localeCompare(String(a.k||'')));   // החדשות למעלה, לפי תאריך אמיתי
  const methChip=rm=>rm?(chBadgeRaw(rm)||`<span class="givemeth">${esc(chLabel(rm))}</span>`):'';
  const GVSHOW=8;                       // מציגים את האחרונות; השאר נפתחות בלחיצה — פחות גלילה
  const gvrow=g=>{
    const st=g.parnes?(g.paid?'<span class="pstat yes">✓ נגבה</span>':'<span class="pstat no">🔴 טרם נגבה</span>'):'';
    const tog=g.parnes?`<button class="collectbtn ${g.paid?'yes':'no'}" data-pid="${g.pid}">${g.paid?'בטל גבייה':'✓ סמן נגבה'}</button>`:'';
    const ed=g.don?`<button class="gvedit" data-did="${g.did}" title="שנה עבור מה">✏️</button>`:'';
    // חלון אחד לכל תרומה: עבור מה · פירוט · כלל קבוע לאותו סכום
    const pan=g.don?`<div class="gvpanel hidden" data-pan="${g.did}">
      <div class="gvlbl">עבור מה ${curd}${g.amt} האלה?</div>
      <div class="addrow"><select class="gvcatsel" data-did="${g.did}">${dnCatOpts(g.cat)}</select></div>
      <div class="addrow gvnewrow hidden" style="margin-top:5px">
        <input class="gvcatnew" data-did="${g.did}" placeholder="שם הייעוד החדש">
        <button class="btn sm gvcatok" data-did="${g.did}">➕ הוסף</button></div>
      <div class="addrow" style="margin-top:5px"><input class="gvnote" placeholder="פירוט (למשל: סעודת ראש חודש)" value="${esc(g.ded)}">
        <button class="btn sm gvsave" data-did="${g.did}">💾</button></div>
      <label class="gvall"><input type="checkbox" class="gvrule"> 🔁 כל ${curd}${g.amt} של התורם הזה = זה (גם בעתיד)</label></div>`:'';
    // בכל תרומה: סכום · עבור מה · תאריך · דרך מה נתרם. לחיצה על הייעוד פותחת את החלון.
    const what=g.don
      ? `<button class="gvcatbtn${g.cat?'':' need'}" data-did="${g.did}" title="לחץ כדי לשנות">${g.cat?esc(g.cat):'עבור מה?'}</button>`
      : esc(g.what);
    return `<div class="giverow"><span class="giveamt">${g.amt?(curd+g.amt):'—'}</span><div class="givewhat">${what}`
      + `${g.when?`<span class="givedate">${esc(g.when)}</span>`:''} ${methChip(g.rm)} ${st}${tog}${ed}`
      + `${g.ded?`<div class="givesub">${esc(g.ded)}</div>`:''}${pan}</div></div>`;
  };
  const give=gitems.length?`<div class="givelist"><div class="givehd">💵 מה תרם ועבור מה <span class="givecnt">${gitems.length}</span></div>`
    + gitems.slice(0,GVSHOW).map(gvrow).join('')
    + (gitems.length>GVSHOW?`<details class="gvmore"><summary>הצג עוד ${gitems.length-GVSHOW}</summary>${gitems.slice(GVSHOW).map(gvrow).join('')}</details>`:'')
    + `</div>`:'';
  const pdebts=(d.parnes||[]).filter(p=>p.status!=='suggested'&&!+p.paid);
  const pdebtsum=pdebts.reduce((s,p)=>s+amtNum(p.amount),0);
  body.innerHTML=`${contactBtns(d)?`<div class="cardcbar">${contactBtns(d)}</div>`:''}
    ${pdebts.length?`<div class="debtbanner">🔴 חוב פרנס שטרם נגבה: <b>${pdebtsum?(curd+pdebtsum):(pdebts.length+' ימים')}</b>${pdebts.map(p=>' · '+esc(DAYKIND[p.kind]||'🌙')+' '+esc(p.date_text||'')).join('')}</div>`:''}
    ${(gc||pend)?`<div class="notpassed">🔴 לא עבר: ${gc?gc+' חודשים':''}${gc&&pend?' · ':''}${pend?pend+' התחייבויות':''}</div>`:''}
    ${unthankedCount(d)?`<div class="thxbanner" id="thxgo">🙏 <b>${unthankedCount(d)}</b> תרומות בלי תודה — לחץ לסמן</div>`:''}
    ${(()=>{const pt=purposeText(d); if(!pt)return '';
      const known=String(d.purpose||'').trim()||(d.pledges||[]).some(p=>+p.monthly)||izSummary(d).monthly>0;
      return `<div class="purpose">🎯 עבור: ${esc(pt)}${known?'':' <small>(לפי התרומות)</small>'}</div>`;})()}
    <div class="two"><label class="fld"><span>שם משפחה</span><input id="f_last" value="${esc(d.last)}"></label>
      <label class="fld"><span>שם פרטי</span><input id="f_first" value="${esc(d.first)}"></label></div>
    <div class="two"><label class="fld"><span>התחייבות</span><select id="f_category">${sel}</select></label>
      <label class="fld"><span>סכום קבוע</span><input id="f_amount" value="${esc(d.amount)}" inputmode="decimal"></label></div>
    ${hasFreq(d)?`<div class="two"><label class="fld"><span>דרגת קוויטל</span><select id="f_tier">${tierOpts(d)}</select></label>
      <label class="fld"><span>תדירות</span><select id="f_frequency">${freqOpts(d.frequency)}</select></label></div>`
    :`<label class="fld"><span>דרגת קוויטל</span><select id="f_tier">${tierOpts(d)}</select></label>`}
    <label class="fld"><span>🎯 עבור מה (הייעוד שלו — מוצג למעלה)</span><select id="f_purpose">${dnCatOpts(d.purpose||'')}</select></label>
    <div class="addrow hidden" id="f_purpnew"><input id="f_purpfree" placeholder="שם הייעוד החדש"></div>
    ${hasOccKv(d)?`<div class="two"><label class="fld"><span>🗓️ חודש קוויטל (מזדמנים)</span><select id="f_kvmon">${HMORD.map(m=>`<option ${m===(d.kv_month||'')?'selected':''}>${m}</option>`).join('')}</select></label>
      <label class="fld"><span>שנה עברית</span><select id="f_kvyr">${heYearOpts(d.kv_year||HEBYEAR)}</select></label></div>`:''}
    <button class="btn" id="f_saveall" style="width:100%;margin:6px 0">💾 שמור</button>
    ${notesHTML(d)}
    ${izSummaryHTML(d)}
    ${reconPendHTML(d)}
    ${monthlyHTML(d)}
    ${catTotalsHTML(d)}
    ${give}
    <details class="dsec" id="dnbox"><summary>➕ רישום תרומה חדשה</summary>
      <div class="two"><label class="fld"><span>סכום (${curd})</span><input id="dn_amt" inputmode="decimal" placeholder="480"></label>
        <label class="fld"><span>איך נתרם</span><select id="dn_method">${DNMETH.map(x=>`<option${x===(d.channel||'')?' selected':''}>${x}</option>`).join('')}</select></label></div>
      <label class="fld"><span>עבור מה</span><select id="dn_cat">${dnCatOpts('')}
        <option value="פרנס לילה" data-day="parnes">🌙 פרנס לילה (בחר יום)</option>
        <option value="חדר קפה" data-day="coffee">☕ חדר קפה (בחר יום)</option>
        <option value="ארוחת בוקר" data-day="breakfast">🍳 ארוחת בוקר (בחר יום)</option></select></label>
      <div class="addrow hidden" id="dn_newrow"><input id="dn_catfree" placeholder="שם הייעוד החדש"></div>
      <label class="fld hidden" id="dn_bldg_l"><span>🏗️ מה תרם בבניין?</span><input id="dn_bldg" list="bldgitems2" placeholder="שולחן / עמוד / מטר…"><datalist id="bldgitems2">${(BUILDING_ITEMS||[]).map(x=>`<option value="${esc(x)}">`).join('')}</datalist></label>
      <div class="hidden" id="dn_daybox"><div class="two"><label class="fld"><span>חודש עברי</span><select id="dn_hm">${HMORD.map(m=>`<option>${m}</option>`).join('')}</select></label>
        <label class="fld"><span>יום</span><select id="dn_hd">${[...Array(30)].map((_,i)=>`<option value="${i+1}">${heDay(i+1)}</option>`).join('')}</select></label></div>
        <label class="fld"><span>שנה עברית</span><select id="dn_hy">${heYearOpts()}</select></label></div>
      <div class="two hidden" id="dn_ccbox"><label class="fld"><span>4 ספרות אחרונות</span><input id="dn_cc4" inputmode="numeric" maxlength="4" placeholder="1234"></label>
        <label class="fld"><span>תוקף</span><input id="dn_ccexp" placeholder="12/28" style="direction:ltr"></label></div>
      <div class="two"><label class="fld"><span>תאריך</span><input id="dn_date" type="date"></label>
        <label class="fld"><span>הערה</span><input id="dn_note" placeholder="פירוט קצר"></label></div>
      <label class="fld"><span>🕯️ שם לתפילה (לא חובה)</span><textarea id="dn_pray" rows="2" placeholder="יעקב בן שרה לרפואה שלמה"></textarea></label>
      <button class="btn" id="dn_add" style="width:100%">➕ רשום תרומה</button></details>
    ${(d.parnes||[]).filter(p=>p.status!=='suggested').length?`<details class="dsec"><summary>🗓️ ימים משובצים (פרנס / קפה / בוקר)</summary><div id="parnes"></div></details>`:''}
    ${d.tier==='יששכר_זבולון'?`<details class="dsec"><summary>🤝 יששכר־זבולון — האברכים שהוא מחזיק</summary><div id="partners"></div>
      <div class="addrow"><input id="pa_name" placeholder="שם האברך"><button class="btn sm" id="pa_add">הוסף</button></div></details>`:''}
    <details class="dsec"><summary>🎯 התחייבויות / קמפיינים${(d.pledges||[]).length?(' ('+(d.pledges||[]).length+')'):''}</summary><div id="pledges"></div>
      <div class="addrow"><input id="pl_cat" placeholder="עבור מה (למשל: נר למאור)"><input id="pl_amt" placeholder="סכום" style="max-width:82px"><button class="btn sm" id="pl_add">הוסף</button></div>
      <label class="jointchk"><input type="checkbox" id="pl_monthly"> 🔁 התחייבות שחוזרת <b>כל חודש</b> (לא חוב חד־פעמי)</label></details>
    ${(d.transactions||[]).length?`<details class="dsec"><summary>💳 חיובים ותשלומים (${(d.transactions||[]).length})</summary><div id="transactions"></div></details>`:''}
    ${(dt.all||dt.year||dt.pending)?`<div class="totals" style="cursor:pointer" id="gototot"><div class="tot"><span>נגבה בפועל</span><b>${curd}${dt.all}</b></div><div class="tot year"><span>השנה (${GREGYEAR})</span><b>${curd}${dt.year}</b></div>${dt.pending>0?`<div class="tot pend"><span>🔴 התחייב · טרם נגבה</span><b>${curd}${dt.pending}</b></div>`:''}</div>`:''}
    ${(d.unclassified||[]).length?(()=>{const uo=RCATS.map(c=>`<option value="${esc(c)}">${esc(c)||'— בחר עבור מה —'}</option>`).join('')
        +((CAMPAIGNS||[]).length?('<optgroup label="🎯 מגביות/ייעודים">'+CAMPAIGNS.filter(c=>!RCATS.includes(c)).map(c=>`<option value="${esc(c)}">${esc(c)}</option>`).join('')+'</optgroup>'):'')
        +'<option value="__new__">➕ עבור מה חדש… (טקסט חופשי)</option>';
      return `<datalist id="bldgitems">${(BUILDING_ITEMS||[]).map(x=>`<option value="${esc(x)}">`).join('')}</datalist><div class="unclbox"><div class="k">❓ ${d.unclassified.length} חיובים שלא ידוע עבור מה — סה"כ $${(d.unclassified.reduce((s,x)=>s+(+x.amount||0),0)).toLocaleString('en-US',{maximumFractionDigits:2})}</div>
      ${d.unclassified.map(x=>`<div class="uline" data-uid="${x.id}">
        <span class="unci">$${(+x.amount).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2})} · ${esc(gregLabel(x.date)||x.date)}</span>
        <select class="ucat1">${uo}</select><input class="unew1" placeholder="שם הייעוד החדש…" style="display:none"><input class="ubldg1" list="bldgitems" placeholder="🏗️ מה תרם בבניין? (שולחן/עמוד/מטר…)" style="display:none"><select class="uav1" style="display:none">${avOpts()}</select><input class="uavnew1" placeholder="שם האברך החדש" style="display:none"><button class="btn sm uavadd1" style="display:none">➕ הוסף</button><button class="btn sm ugo1">💾</button></div>`).join('')}
      ${d.unclassified.length>1?`<div class="addrow uall"><select id="ucl_cat">${uo}</select>
        <input id="ucl_new" placeholder="שם הייעוד החדש…" style="display:none">
        <input id="ucl_bldg" list="bldgitems" placeholder="🏗️ מה תרם בבניין?" style="display:none">
        <select id="ucl_av" style="display:none">${avOpts()}</select>
        <input id="ucl_avnew" placeholder="שם האברך החדש" style="display:none">
        <button class="btn sm" id="ucl_avadd" style="display:none">➕ הוסף</button>
        <button class="btn sm" id="ucl_save">💾 אותו דבר לכולם</button></div>`:''}</div>`;})():''}
    <div class="sec"><div class="k" style="margin-bottom:6px">📌 עבור מה כל סכום — כללים קבועים</div>
      <div class="hintxt" style="margin:0 2px 7px">כל חיוב בסכום הזה אצל התורם ייכנס אוטומטית לייעוד הזה — גם אחורה וגם בעתיד.</div>
      <div id="rules">${(d.rules||[]).map(r=>`<div class="rulerow" data-amt="${r.amount}">
        <b>$${(+r.amount).toLocaleString('en-US',{maximumFractionDigits:2})}</b>
        <span class="rulecat">${esc(r.category||'')}</span>
        ${r.note?`<span class="rulenote2">${esc(r.note)}</span>`:''}
        <button class="del ruledel" data-amt="${r.amount}" title="מחק כלל">🗑</button></div>`).join('')}</div>
      <div class="addrow" style="margin-top:6px">
        <input id="rl_amt" type="number" step="0.01" placeholder="סכום" style="max-width:110px">
        <select id="rl_cat">${dnCatOpts('')}</select></div>
      <div class="addrow hidden" id="rl_newrow" style="margin-top:6px">
        <input id="rl_new" placeholder="שם הייעוד החדש"></div>
      <div class="addrow" style="margin-top:6px">
        <input id="rl_note" placeholder="פירוט (למשל: מעקות וכיסוי רדיאטורים)">
        <button class="btn sm" id="rl_add">➕ הוסף כלל</button></div></div>
    <div class="sec"><button class="btn ghost" id="f_merge" style="width:100%">🔀 מזג עם כרטיס כפול (אותו אדם)</button>
      <div id="mergebox" class="hidden" style="margin-top:8px">
        <input id="mg_q" placeholder="🔍 חפש את הכרטיס הכפול למזג לכאן…" autocomplete="off">
        <div id="mg_res" class="dpres"></div>
        <div class="hintxt">הכרטיס הזה (${esc((d.last+' '+d.first).trim())}) יישאר, והכפול יתמזג לתוכו — כל התרומות, הקוויטל והאברכים יעברו לכאן.</div></div></div>
    <div class="sec" style="text-align:center"><button class="btn ghost delbig" id="f_delete" style="width:100%">🗑 מחיקת התורם לצמיתות</button></div>`;
  wireDelete(d, body);   // ראשון בתור: תקלה בחיווט אחר לא תשאיר את המחיקה בלי מאזין
  const gt=document.getElementById('gototot'); if(gt)gt.onclick=()=>{cardTab='details';renderCard(d);};
  body.querySelectorAll('.cosp2[data-did]').forEach(x=>x.onclick=()=>{const dd=DB.find(y=>y.id==x.dataset.did);if(dd)openDonor(dd);});
  body.querySelectorAll('.collectbtn').forEach(b=>b.onclick=async()=>{const p=(d.parnes||[]).find(x=>x.id==b.dataset.pid);if(!p)return;const np=+p.paid?0:1;p.paid=np;await api('PUT','/api/parnes/'+p.id,{paid:np});toast(np?'סומן כנגבה ✓':'סומן כטרם נגבה');cardDetails(d,body);if(tab==='donors')renderDonors();});
  body.querySelectorAll('.gvedit').forEach(b=>b.onclick=()=>{
    const p=body.querySelector('.gvpanel[data-pan="'+b.dataset.did+'"]'); if(p)p.classList.toggle('hidden');});
  // בחירת "עבור מה" ישירות על שורת התרומה — נשמר מיד
  const saveGvCat=async(did,cat)=>{
    const x=(d.donations||[]).find(y=>y.id==did); if(!x)return;
    const body2={category:cat};
    const nn=String(x.note||'').replace(/\s*·?\s*לא סווג[^·]*/,'').trim();
    if(nn!==String(x.note||'')){body2.note=nn;x.note=nn;}
    x.category=cat;
    await api('PUT','/api/donation/'+did,body2);
    cardDetails(d,body); if(tab==='donors')renderDonors();
    toast(cat?('נרשם: '+cat+' ✓'):'הייעוד נוקה');
  };
  const gvOpen=did=>{const p=body.querySelector('.gvpanel[data-pan="'+did+'"]');if(p)p.classList.toggle('hidden');};
  body.querySelectorAll('.gvcatbtn').forEach(b=>b.onclick=()=>gvOpen(b.dataset.did));
  body.querySelectorAll('.gvcatsel').forEach(s=>s.onchange=()=>{
    const pan=s.closest('.gvpanel');
    if(s.value==='__new__'){
      pan.querySelector('.gvnewrow').classList.remove('hidden');
      pan.querySelector('.gvcatnew').focus();
      return;
    }
    saveGvCat(s.dataset.did,s.value);
  });
  body.querySelectorAll('.gvcatok').forEach(b=>b.onclick=async()=>{
    const pan=b.closest('.gvpanel'), inp=pan.querySelector('.gvcatnew'), nm=inp.value.trim();
    if(nm.length<2){toast('כתוב את שם הייעוד');inp.focus();return;}
    b.disabled=true;
    await api('POST','/api/campaigns',{name:nm});
    if(!(CAMPAIGNS||[]).includes(nm))CAMPAIGNS.unshift(nm);
    await saveGvCat(b.dataset.did,nm);
  });
  body.querySelectorAll('.gvcatnew').forEach(i=>i.onkeydown=e=>{
    if(e.key==='Enter'){e.preventDefault();i.closest('.gvpanel').querySelector('.gvcatok').click();}});
  body.querySelectorAll('.gvsave').forEach(b=>b.onclick=async()=>{
    const p=body.querySelector('.gvpanel[data-pan="'+b.dataset.did+'"]'); if(!p)return;
    const sel=body.querySelector('.gvcatsel[data-did="'+b.dataset.did+'"]');
    const cat=(sel&&sel.value!=='__new__'?sel.value:'').trim(), note=p.querySelector('.gvnote').value.trim();
    const rule=p.querySelector('.gvrule').checked;
    const dn=(d.donations||[]).find(x=>x.id==b.dataset.did); if(!dn)return;
    b.disabled=true;
    if(rule){ await api('POST','/api/rule',{donor_id:d.id,amount:parseFloat(dn.amount),category:cat,note}); }
    else { await api('PUT','/api/donation/'+b.dataset.did,{category:cat,note:note?(String(dn.note||'').split(' · ')[0]+' · '+note):dn.note}); }
    toast(rule?'נשמר לכל הסכום הזה ✓':'נשמר ✓');
    await load(); const dd=DB.find(x=>x.id===d.id); if(dd)openDonor(dd,'details');});
  body.querySelectorAll('.uline[data-uid]').forEach(ln=>{
    const b=ln.querySelector('.ugo1'), sx=ln.querySelector('.ucat1'), nx=ln.querySelector('.unew1'), bx=ln.querySelector('.ubldg1');
    const isB=c=>/בנין|בניין/.test(c||'');
    const ax=ln.querySelector('.uav1'), axn=ln.querySelector('.uavnew1'), axa=ln.querySelector('.uavadd1');
    wireAvNew(ax,axn,axa);
    if(sx&&nx&&bx){ const shw=()=>{const isNew=sx.value==='__new__';nx.style.display=isNew?'block':'none';
        const c=isNew?nx.value:sx.value;
        bx.style.display=isB(c)?'block':'none';
        const iz=isIZcat(c); if(ax) ax.style.display=iz?'block':'none';
        if(!iz&&axn){axn.style.display='none';axa.style.display='none';}};
      sx.onchange=()=>{shw();if(sx.value==='__new__')nx.focus();}; nx.oninput=shw; }
    b.onclick=async()=>{
      const s1=ln.querySelector('.ucat1'), n1=ln.querySelector('.unew1');
      let cat=s1.value.trim();
      if(cat==='__new__'){ cat=n1.value.trim();
        if(!cat){toast('כתוב את שם הייעוד');n1.focus();return;}
        if(!(CAMPAIGNS||[]).includes(cat)){ await api('POST','/api/campaigns',{name:cat}); CAMPAIGNS.unshift(cat); } }
      if(!cat){toast('בחר עבור מה');return;}
      if(/בנין|בניין/.test(cat)){ const it=ln.querySelector('.ubldg1').value.trim();
        if(!it){toast('כתוב מה הוא תרם בבניין');return;}
        if(!(BUILDING_ITEMS||[]).includes(it)){ await api('POST','/api/building_items',{name:it}); BUILDING_ITEMS.unshift(it); }
        cat=cat+' — '+it; }
      let avv='';
      if(isIZcat(cat)){ avv=(ax?ax.value:'').trim();
        if(!avv||avv==='__new__'){toast('בחר אברך מהרשימה');if(ax)ax.focus();return;} }
      b.disabled=true;b.textContent='…';
      const r=await api('POST','/api/classify',{donor_id:d.id,category:cat,ids:[+ln.dataset.uid],avreich:avv});
      if(!r||!r.ok){b.disabled=false;b.textContent='💾';toast('השמירה נכשלה');return;}
      toast('נשמר ✓'); await load(); const dd=DB.find(x=>x.id===d.id); if(dd)openDonor(dd,'details');};
  });
  const uclSave=document.getElementById('ucl_save');
  const uclSel=document.getElementById('ucl_cat'), uclNew=document.getElementById('ucl_new');
  const uclBd=document.getElementById('ucl_bldg');
  const uclAv=document.getElementById('ucl_av');
  wireAvNew(uclAv,document.getElementById('ucl_avnew'),document.getElementById('ucl_avadd'));
  if(uclAv&&!AVLIST.length) loadAvList().then(()=>{document.querySelectorAll('select.uav1,#ucl_av').forEach(s2=>{s2.innerHTML=avOpts(s2.value);});});
  if(uclSel&&uclNew&&uclBd){ const shwA=()=>{const isNew=uclSel.value==='__new__';uclNew.style.display=isNew?'block':'none';
      const c=isNew?uclNew.value:uclSel.value;
      uclBd.style.display=/בנין|בניין/.test(c)?'block':'none';
      const izA=isIZcat(c); if(uclAv) uclAv.style.display=izA?'block':'none';
      const un=document.getElementById('ucl_avnew'),ua=document.getElementById('ucl_avadd');
      if(!izA&&un){un.style.display='none';ua.style.display='none';}};
    uclSel.onchange=()=>{shwA();if(uclSel.value==='__new__')uclNew.focus();}; uclNew.oninput=shwA; }
  if(uclSave)uclSave.onclick=async()=>{
    const sa=document.getElementById('ucl_cat'), na=document.getElementById('ucl_new');
    let cat=sa.value.trim();
    if(cat==='__new__'){ cat=na.value.trim();
      if(!cat){toast('כתוב את שם הייעוד');na.focus();return;}
      if(!(CAMPAIGNS||[]).includes(cat)){ await api('POST','/api/campaigns',{name:cat}); CAMPAIGNS.unshift(cat); } }
    if(!cat){toast('בחר עבור מה');return;}
    if(/בנין|בניין/.test(cat)){ const it=(uclBd?uclBd.value:'').trim();
      if(!it){toast('כתוב מה הוא תרם בבניין');return;}
      if(!(BUILDING_ITEMS||[]).includes(it)){ await api('POST','/api/building_items',{name:it}); BUILDING_ITEMS.unshift(it); }
      cat=cat+' — '+it; }
    let avv2='';
    if(isIZcat(cat)){ avv2=(uclAv?uclAv.value:'').trim();
      if(!avv2||avv2==='__new__'){toast('בחר אברך מהרשימה');if(uclAv)uclAv.focus();return;} }
    uclSave.disabled=true;uclSave.textContent='שומר…';
    const r=await api('POST','/api/classify',{donor_id:d.id,category:cat,avreich:avv2});
    if(!r||!r.ok){uclSave.disabled=false;uclSave.textContent='💾 שמור לכולם';toast('השמירה נכשלה');return;}
    toast('עודכנו '+r.updated+' תרומות ✓');
    await load(); const dd=DB.find(x=>x.id===d.id); if(dd)openDonor(dd,'details');};
  // ---- רישום תרומה חדשה, ישירות מהדף הראשי ----
  renderParnesEdit(d); renderPledges(d); renderTransactions(d);
  if(d.tier==='יששכר_זבולון'){
    renderPartners(d);
    const pab=document.getElementById('pa_add');
    if(pab)pab.onclick=async()=>{const n=document.getElementById('pa_name').value.trim();if(!n)return;
      const r=await api('POST','/api/partner',{donor_id:d.id,avreich:n});
      d.partners=(d.partners||[]).concat([{id:r.id,avreich:n}]);
      document.getElementById('pa_name').value='';renderPartners(d);toast('נוסף ✓');};
  }
  const plAdd=document.getElementById('pl_add');
  if(plAdd)plAdd.onclick=async()=>{const cat=document.getElementById('pl_cat').value.trim(),amt=document.getElementById('pl_amt').value.trim();
    const mo=document.getElementById('pl_monthly')&&document.getElementById('pl_monthly').checked?1:0;
    if(!cat)return;const st=mo?'נתן':'טרם';
    const r=await api('POST','/api/pledge',{donor_id:d.id,category:cat,amount:amt,status:st,monthly:mo});
    d.pledges=(d.pledges||[]).concat([{id:r.id,donor_id:d.id,category:cat,amount:amt,status:st,monthly:mo}]);
    document.getElementById('pl_cat').value='';document.getElementById('pl_amt').value='';
    if(document.getElementById('pl_monthly'))document.getElementById('pl_monthly').checked=false;
    renderPledges(d);refreshIzSum(d);toast(mo?'נוספה התחייבות חודשית ✓':'נוסף ✓');};
  const dnDate=document.getElementById('dn_date'); if(dnDate)dnDate.value=todayStr();
  const dnCat=document.getElementById('dn_cat'), dnMeth=document.getElementById('dn_method');
  const isBldg=c=>/בנין|בניין/.test(c||'');
  const dnShow=()=>{
    const o=dnCat.options[dnCat.selectedIndex], day=o?o.dataset.day:'';
    document.getElementById('dn_daybox').classList.toggle('hidden',!day);
    document.getElementById('dn_newrow').classList.toggle('hidden',dnCat.value!=='__new__');
    document.getElementById('dn_bldg_l').classList.toggle('hidden',!isBldg(dnCat.value));
    document.getElementById('dn_ccbox').classList.toggle('hidden',!/אשראי|אונליין/.test(dnMeth.value));
  };
  if(dnCat){dnCat.onchange=dnShow;dnMeth.onchange=dnShow;dnShow();}
  const dnAdd=document.getElementById('dn_add');
  if(dnAdd)dnAdd.onclick=async()=>{
    let cat=dnCat.value;
    const o=dnCat.options[dnCat.selectedIndex], dayKind=o?o.dataset.day:'';
    if(cat==='__new__'){
      cat=document.getElementById('dn_catfree').value.trim();
      if(cat.length<2){toast('כתוב את שם הייעוד');return;}
      if(!(CAMPAIGNS||[]).includes(cat)){await api('POST','/api/campaigns',{name:cat});CAMPAIGNS.unshift(cat);}
    }
    if(isBldg(cat)){const it=document.getElementById('dn_bldg').value.trim();
      if(it){if(!(BUILDING_ITEMS||[]).includes(it)){await api('POST','/api/building_items',{name:it});BUILDING_ITEMS.unshift(it);}cat=cat+' — '+it;}}
    const amt=document.getElementById('dn_amt').value.trim(), method=dnMeth.value,
          date=dnDate.value, pray=document.getElementById('dn_pray').value.trim();
    let note=document.getElementById('dn_note').value.trim();
    const c4=(document.getElementById('dn_cc4')||{}).value||'', cx=(document.getElementById('dn_ccexp')||{}).value||'';
    if(c4.trim()||cx.trim())note=(note?note+' · ':'')+'כרטיס ****'+c4.trim()+(cx.trim()?(' תוקף '+cx.trim()):'');
    if(!amt&&!pray){toast('מלא סכום או שם לתפילה');return;}
    dnAdd.disabled=true;
    if(amt&&!dayKind){
      const r=await api('POST','/api/donation',{donor_id:d.id,amount:amt,category:cat,method,date,note});
      d.donations=(d.donations||[]).concat([{id:r.id,donor_id:d.id,amount:amt,category:cat,method,date,note,paid:1}]);
    }
    if(dayKind){
      const hm=document.getElementById('dn_hm').value,hd=+document.getElementById('dn_hd').value,
            hy=document.getElementById('dn_hy').value,dtext=heDay(hd)+' '+hm;
      const r=await api('POST','/api/parnes',{donor_id:d.id,day:hd,month:hm,date_text:dtext,dedication:pray||'',amount:amt,kind:dayKind,hyear:hy});
      d.parnes=(d.parnes||[]).concat([{id:r.id,donor_id:d.id,day:hd,month:hm,date_text:dtext,dedication:pray||'',amount:amt,kind:dayKind,hyear:hy}]);
    }
    if(pray&&!dayKind){
      const tr=d.tier||'';
      const r=await api('POST','/api/prayer',{donor_id:d.id,text:pray,tier:tr});
      d.prayers=(d.prayers||[]).concat([{id:r.id,text:pray,tier:tr}]);
    }
    dnAdd.disabled=false;
    toast('נרשם ✓'+(dayKind?' + יום נתפס':'')+(pray?' + שם לקוויטל':''));
    cardDetails(d,body); if(tab==='donors')renderDonors();
  };
  const rlCat=document.getElementById('rl_cat'), rlNewRow=document.getElementById('rl_newrow');
  if(rlCat&&rlNewRow)rlCat.onchange=()=>{
    const on=rlCat.value==='__new__';
    rlNewRow.classList.toggle('hidden',!on);
    if(on)document.getElementById('rl_new').focus();
  };
  const rlAdd=document.getElementById('rl_add');
  if(rlAdd)rlAdd.onclick=async()=>{
    const amt=parseFloat(document.getElementById('rl_amt').value);
    let cat=document.getElementById('rl_cat').value.trim();
    const note=document.getElementById('rl_note').value.trim();
    if(cat==='__new__'){                       // ייעוד חדש שנכתב כאן — נוסף לרשימה ואז נשמר
      cat=(document.getElementById('rl_new').value||'').trim();
      if(cat.length<2){toast('כתוב את שם הייעוד');document.getElementById('rl_new').focus();return;}
      await api('POST','/api/campaigns',{name:cat});
      if(!(CAMPAIGNS||[]).includes(cat))CAMPAIGNS.unshift(cat);
    }
    if(!amt||!cat){toast('מלא סכום ועבור מה');return;}
    rlAdd.disabled=true;
    const r=await api('POST','/api/rule',{donor_id:d.id,amount:amt,category:cat,note});
    rlAdd.disabled=false;
    if(!r||!r.ok){toast('השמירה נכשלה');return;}
    toast('נשמר · עודכנו '+r.updated+' תרומות ✓');
    await load(); const dd=DB.find(x=>x.id===d.id); if(dd)openDonor(dd,'details');};
  body.querySelectorAll('.ruledel').forEach(b=>b.onclick=async()=>{
    await api('POST','/api/rule',{donor_id:d.id,amount:+b.dataset.amt,delete:true});
    toast('הכלל נמחק'); await load(); const dd=DB.find(x=>x.id===d.id); if(dd)openDonor(dd,'details');});
  document.getElementById('f_merge').onclick=()=>document.getElementById('mergebox').classList.toggle('hidden');
  const mgq=document.getElementById('mg_q'),mgres=document.getElementById('mg_res');
  mgq.oninput=()=>{const s=norm(mgq.value);if(!s){mgres.innerHTML='';return;}
    const m=DB.filter(x=>x.id!==d.id&&norm(x.last+' '+x.first+' '+x.english+' '+x.phone).includes(s)).slice(0,8);
    mgres.innerHTML=m.map(x=>`<div class="dpr" data-id="${x.id}">${esc(x.last)} ${esc(x.first)} <span style="color:var(--muted)">#${x.id}${x.phone?(' · '+esc(splitPhones(x.phone)[0])):''}</span></div>`).join('')||'<div class="dpr" style="color:var(--muted)">אין תוצאות</div>';
    mgres.querySelectorAll('.dpr[data-id]').forEach(el=>el.onclick=async()=>{
      const other=DB.find(x=>x.id==el.dataset.id);if(!other)return;
      if(!await uiConfirm('למזג את "'+(other.last+' '+other.first).trim()+'" (#'+other.id+') לתוך "'+(d.last+' '+d.first).trim()+'"?\nהכפול יימחק וכל הנתונים יעברו לכאן.'))return;
      const tot={};
      mergeLocal(d.id,other.id,tot);              // מיד על המסך; השרת מתעדכן ברקע
      toast('מוזג ✓ '+movedTxt(tot)); ov.classList.remove('show'); openDonor(d,'details');
      try{
        const r=await api('POST','/api/merge',{keep:d.id,drop:other.id});
        if(!r||!r.ok)throw new Error((r&&(r.detail||r.error))||'השרת סירב');
      }catch(e){ toast('❌ המיזוג לא נשמר: '+(e&&e.message||e)); }
      load().then(()=>{const dd=DB.find(x=>x.id===d.id); if(dd)openDonor(dd,'details');});});
  };
  const FF=['last','first','category','amount','frequency'];
  wireFields(d,FF);
  wireNotes(d,body);
  // שינוי ההתחייבות מחליף גם את מה שרלוונטי להציג (תדירות רק לקבועים)
  const catSel=document.getElementById('f_category');
  if(catSel)catSel.addEventListener('change',()=>setTimeout(()=>cardDetails(d,body),150));
  const thg=document.getElementById('thxgo');if(thg)thg.onclick=()=>{cardTab='details';renderCard(d);};
  const tierSel=document.getElementById('f_tier'); if(tierSel)tierSel.onchange=()=>applyTierSelect(d);
  const kvmon=document.getElementById('f_kvmon'),kvyr=document.getElementById('f_kvyr');
  const saveKvMY=async()=>{d.kv_month=kvmon.value;d.kv_year=kvyr.value;await api('PUT','/api/donor/'+d.id,{kv_month:d.kv_month,kv_year:d.kv_year});toast('עודכן · '+d.kv_month+' '+d.kv_year+' ✓');cardDetails(d,body);};
  if(kvmon)kvmon.onchange=saveKvMY; if(kvyr)kvyr.onchange=saveKvMY;
  addMic(document.getElementById('dn_note'));
  const psel=document.getElementById('f_purpose'),pnew=document.getElementById('f_purpnew');
  if(psel)psel.onchange=()=>{pnew.classList.toggle('hidden',psel.value!=='__new__');if(psel.value==='__new__')document.getElementById('f_purpfree').focus();};
  document.getElementById('f_saveall').onclick=async()=>{const b2={};FF.forEach(k=>{const el=document.getElementById('f_'+k);if(el){b2[k]=el.value;d[k]=el.value;}});
    if(psel){let pv=psel.value;
      if(pv==='__new__'){pv=document.getElementById('f_purpfree').value.trim();
        if(!pv){toast('כתוב את שם הייעוד החדש');document.getElementById('f_purpfree').focus();return;}
        if(!(CAMPAIGNS||[]).includes(pv)){await api('POST','/api/campaigns',{name:pv});CAMPAIGNS.unshift(pv);}}
      b2.purpose=pv;d.purpose=pv;}
    await api('PUT','/api/donor/'+d.id,b2);cardDetails(d,body);toast('נשמר ✓');if(tab==='donors')renderDonors();};
}

// מחיקת תורם — חלון אישור ברור, ודיווח אמיתי אם נכשל
async function wireDelete(d, body){
  const delBtn=document.getElementById('f_delete'); if(!delBtn) return;
  delBtn.onclick=async()=>{
    const nm=((d.last||'')+' '+(d.first||'')).trim();
    const n=(d.donations||[]).length, p=(d.parnes||[]).length, av=(d.partners||[]).length;
    const det=[n?n+' תרומות':'',p?p+' פרנס':'',av?av+' אברכים':''].filter(Boolean).join(' · ');
    if(!await uiConfirm('למחוק לצמיתות את "'+nm+'"?\n'+(det?('יימחקו גם: '+det+'\n'):'')+'אי אפשר לבטל את זה.')) return;
    delBtn.disabled=true; delBtn.textContent='מוחק…';
    let r=null; try{ r=await api('DELETE','/api/donor/'+d.id); }catch(e){ r={ok:false,detail:String(e)}; }
    if(!r||!r.ok){
      delBtn.disabled=false; delBtn.textContent='🗑 מחיקת התורם לצמיתות';
      toast('המחיקה נכשלה'+((r&&(r.detail||r.error))?': '+(r.detail||r.error):' — נסה שוב'));
      return;
    }
    DB=DB.filter(x=>x.id!==d.id); ov.classList.remove('show');
    try{localStorage.removeItem('kc_donor');}catch(e){}
    toast('התורם נמחק ✓'); render();
  };
}
function splitPhones(s){return (s||'').split('/').map(x=>x.trim()).filter(Boolean);}
// כמה אימיילים לאותו תורם — מופרדים בפסיק / קו נטוי / רווח
function splitEmails(s){return String(s||'').split(/[,;/\s]+/).map(x=>x.trim()).filter(x=>x.includes('@'));}
function renderEmails(d){
  const el=document.getElementById('emails'); if(!el) return;
  el.innerHTML='';
  const save=async()=>{const list=[...el.querySelectorAll('.emin')].map(x=>x.value.trim()).filter(Boolean);
    d.email=list.join(', ');await api('PUT','/api/donor/'+d.id,{email:d.email});toast('נשמר ✓');};
  const addRow=(val)=>{const row=document.createElement('div');row.className='phrow';
    row.innerHTML=`<input class="emin" dir="ltr" inputmode="email" value="${esc(val||'')}" placeholder="name@example.com"><button class="del emdel" title="מחק">🗑</button>`;
    row.querySelector('.emin').onchange=save;
    row.querySelector('.emdel').onclick=()=>{row.remove();save();};
    el.insertBefore(row, el.lastChild); return row;};
  const addBtn=document.createElement('button');addBtn.className='btn sm phadd';addBtn.textContent='➕ אימייל נוסף';
  addBtn.onclick=()=>{const r=addRow('');r.querySelector('.emin').focus();};
  el.appendChild(addBtn);
  const list=splitEmails(d.email); if(!list.length) list.push('');
  list.forEach(addRow);
}
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
  const isOcc=hasOccKv(d)||(d.category==='מזדמן'&&!d.tier);   // בלשונית הקוויטל תמיד אפשר לקבוע חודש
  body.innerHTML=`${(d.intake_pending||[]).length?reconPendHTML({intake_pending:d.intake_pending,recon_pending:[]}):''}
    <div class="sec">
      <label class="fld"><span>דרגת קוויטל (אפשר לשנות מכאן)</span><select id="kv_tier">${tierOpts(d)}</select></label>
      ${isOcc?`<div class="two" style="margin-top:6px"><label class="fld"><span>🗓️ חודש עברי (מזדמנים)</span><select id="kv_mon">${HMORD.map(m=>`<option ${m===(d.kv_month||'')?'selected':''}>${m}</option>`).join('')}</select></label>
        <label class="fld"><span>שנה עברית</span><select id="kv_yr">${heYearOpts(d.kv_year||HEBYEAR)}</select></label></div>
        <div class="hintxt">התורם יופיע בקוויטל מזדמן תחת <b>${esc((d.kv_month||'—')+' '+(d.kv_year||''))}</b>. שנה כאן בכל עת.</div>`:''}
    </div>
    ${inKv?`<div class="hintxt">✡️ מסומן בקוויטל <b>${KVTIER[d.tier]}</b>.${empty?' עדיין לא הוזנו שמות לתפילה — הוסף למטה (בדרך כלל שם התורם: "פלוני בן אמו").':''}</div>`:''}
    <div id="prayers"></div>
    <div class="addrow"><input id="pr_new" placeholder="שם לתפילה (למשל: יעקב בן שרה לרפואה שלמה)" value="${esc(sugg)}"><button class="btn sm" id="pr_add">הוסף</button></div>`;
  renderPrayers(d);
  // בקשות קוויטל מהאתר — אישור ישירות מכאן (מרענן לתוך לשונית הקוויטל)
  body.querySelectorAll('.kvpend').forEach(el=>{
    const ta=el.querySelector('.ipnames');
    const done=async()=>{await load();const x=DB.find(y=>y.id===d.id);
      if(x){d.intake_pending=x.intake_pending;d.prayers=x.prayers;}cardKvittel(d,body);};
    el.querySelector('.ipok').onclick=async()=>{
      const names=ta.value.trim(); if(!names){toast('אין שמות');return;}
      const b=el.querySelector('.ipok');b.disabled=true;b.textContent='מוסיף…';
      const r=await api('POST','/api/intake/'+el.dataset.iid+'/attach',{donor_id:d.id,names});
      if(!r||!r.ok){b.disabled=false;b.textContent='➕ הוסף לקוויטל';toast('לא נוסף');return;}
      await done();toast('נוסף לקוויטל ✓');
    };
    el.querySelector('.ipskip').onclick=async()=>{
      await api('PUT','/api/intake/'+el.dataset.iid,{status:'handled'});await done();toast('סומן כטופל');
    };
  });
  const kvt=document.getElementById('kv_tier'); if(kvt)kvt.onchange=()=>applyTierSelect(d,'kv_tier');
  const kvm=document.getElementById('kv_mon'),kvy=document.getElementById('kv_yr');
  const saveOcc=async()=>{d.kv_month=kvm.value;d.kv_year=kvy.value;await api('PUT','/api/donor/'+d.id,{kv_month:d.kv_month,kv_year:d.kv_year});toast('עודכן · '+d.kv_month+' '+d.kv_year+' ✓');cardKvittel(d,body);};
  if(kvm)kvm.onchange=saveOcc; if(kvy)kvy.onchange=saveOcc;
  document.getElementById('pr_add').onclick=async()=>{const t=document.getElementById('pr_new').value.trim();if(!t)return;const r=await api('POST','/api/prayer',{donor_id:d.id,text:t,tier:d.tier||''});d.prayers=d.prayers||[];d.prayers.push({id:r.id,text:t,tier:d.tier||''});document.getElementById('pr_new').value='';renderPrayers(d);toast('נוסף ✓');};
}
/* חיובים מאוטרייז/בנק ווסט שטרם אושרו — אישור ישירות מכרטיס התורם */
const RCATS=['','קבוע','יששכר־זבולון','פרנס לילה','חדר קפה','ארוחת בוקר','נר למאור','קוויטל','מזדמן','חד-פעמי','בניין'];
const RPARNES=['פרנס לילה','חדר קפה','ארוחת בוקר'];
function pendCount(d){return (d.recon_pending||[]).length+(d.intake_pending||[]).length;}
function reconPendHTML(d){
  const rp=(d.recon_pending||[]), ip=(d.intake_pending||[]);
  if(!rp.length&&!ip.length)return '';
  const opts=c=>RCATS.concat(CAMPAIGNS||[]).filter((v,i,a)=>a.indexOf(v)===i)
      .map(x=>`<option value="${esc(x)}" ${x===(c||'')?'selected':''}>${x||'— עבור מה? —'}</option>`).join('');
  const kv=ip.length?`<div class="hintxt" style="margin-top:8px"><b>🕯️ שמות לקוויטל שהגיעו מהאתר</b> — ערוך אם צריך ולחץ "הוסף לקוויטל".</div>
    ${ip.map(x=>`<div class="rpitem kvpend" data-iid="${x.id}">
      <div class="rphd">🕯️ בקשה מהאתר${x.received?(' · '+esc(x.received)):''}${x.subject?(' · <span class="ensm">'+esc(x.subject)+'</span>'):''}</div>
      <textarea class="ipnames" rows="3">${esc(x.names||'')}</textarea>
      <div class="intbtns"><button class="btn sm ipok">➕ הוסף לקוויטל</button><button class="btn sm ghost ipskip">דלג</button></div>
    </div>`).join('')}`:'';
  const ch=rp.length?`<div class="hintxt" style="margin-top:8px"><b>💳 חיובים מהאשראי</b> — בחר עבור מה ולחץ "הכנס".</div>
    ${rp.map(r=>`<div class="rpitem" data-tid="${esc(r.tid)}">
      <div class="rphd"><b>$${esc(r.amount||'')}</b> · ${esc(r.date||'')} <span class="givemeth">${esc(r.source||'')}</span>${+r.recurring?' <span class="fbchip on">🔁 הוראת קבע</span>':''}</div>
      <div class="two" style="margin-top:5px"><label class="fld"><span>עבור מה</span><select class="rpcat">${opts(r.category)}</select></label>
        <label class="fld"><span>&nbsp;</span><button class="btn sm rpok" style="width:100%">✓ הכנס לכרטיס</button></label></div>
      <label class="fld"><span>📝 הערה לתרומה (רשות) — תישמר גם בהערות התורם</span><input class="rpnote" placeholder="למשל: קרן מיוחדת שנתרמה דרך הבנק שבו היא עובדת"></label>
      <div class="two"><label class="fld"><span>✅ משימה (רשות)</span><select class="rptaskk">${taskKindOpts()}</select></label>
        <label class="fld"><span>👤 מי מטפל</span><select class="rptaskw">${assigneeOpts('')}</select></label>
        <label class="fld"><span>מתי להזכיר</span><input type="date" class="rptaskd" value="${esc(todayStr())}"></label></div>
      <input class="rptask" placeholder="פרטי המשימה — למשל: לבדוק מתי צריכה לשלם בפעם הבאה" style="width:100%;padding:9px 11px;border:1px solid var(--line);border-radius:9px;font-family:inherit;background:var(--card);color:var(--ink)">
      <div class="rpday hidden"><div class="two"><label class="fld"><span>חודש עברי</span><select class="rpmon">${HMORD.map(m=>`<option>${m}</option>`).join('')}</select></label>
        <label class="fld"><span>יום</span><select class="rpdd">${[...Array(30)].map((_,i)=>`<option value="${i+1}">${heDay(i+1)}</option>`).join('')}</select></label></div>
        <label class="fld"><span>שנה עברית</span><select class="rpyr">${heYearOpts()}</select></label>
        <label class="fld"><span>🕯️ שמות לתעודת הפרנס</span><input class="rpded" placeholder="שמות ובקשות"></label></div>
    </div>`).join('')}`:'';
  return `<div class="sec rpsec"><h3>🕒 ממתין לטיפול (${rp.length+ip.length})</h3>${kv}${ch}</div>`;
}
function wireReconPend(d,body){
  const refresh=async()=>{await load();const x=DB.find(y=>y.id===d.id);
    if(x){d.recon_pending=x.recon_pending;d.intake_pending=x.intake_pending;d.donations=x.donations;d.prayers=x.prayers;d.parnes=x.parnes;d.transactions=x.transactions;}
    cardDonations(d,body);if(tab==='donors')renderDonors();};
  // בקשות קוויטל מהאתר
  body.querySelectorAll('.kvpend').forEach(el=>{
    const ta=el.querySelector('.ipnames');
    el.querySelector('.ipok').onclick=async()=>{
      const names=ta.value.trim(); if(!names){toast('אין שמות');return;}
      const b=el.querySelector('.ipok'); b.disabled=true; b.textContent='מוסיף…';
      const r=await api('POST','/api/intake/'+el.dataset.iid+'/attach',{donor_id:d.id,names});
      if(!r||!r.ok){b.disabled=false;b.textContent='➕ הוסף לקוויטל';toast('לא נוסף');return;}
      await refresh(); toast('נוסף לקוויטל ✓');
    };
    el.querySelector('.ipskip').onclick=async()=>{
      await api('PUT','/api/intake/'+el.dataset.iid,{status:'handled'});
      await refresh(); toast('סומן כטופל');
    };
  });
  body.querySelectorAll('.rpitem[data-tid]').forEach(el=>{
    const sel=el.querySelector('.rpcat'),day=el.querySelector('.rpday');
    wireKindSel(el.querySelector('.rptaskk'));
    const upd=()=>{day.classList.toggle('hidden',!RPARNES.includes(sel.value));};
    sel.onchange=upd; upd();
    el.querySelector('.rpok').onclick=async()=>{
      if(!sel.value){toast('בחר עבור מה');return;}
      const b=el.querySelector('.rpok'); b.disabled=true; b.textContent='מכניס…';
      const payload={donor_id:d.id,category:sel.value};
      const nt=el.querySelector('.rpnote'); if(nt&&nt.value.trim()){payload.note=nt.value.trim();payload.note_to_donor=true;}
      const tk=el.querySelector('.rptask');
      if(tk&&tk.value.trim()){payload.task=tk.value.trim();payload.task_date=el.querySelector('.rptaskd').value||todayStr();
        payload.task_kind=(await kindValue(el.querySelector('.rptaskk')))||'other';
        payload.task_who=el.querySelector('.rptaskw').value;}
      if(RPARNES.includes(sel.value)){
        const mo=el.querySelector('.rpmon').value,dd=+el.querySelector('.rpdd').value;
        payload.month=mo; payload.day=dd; payload.hyear=el.querySelector('.rpyr').value;
        payload.date_text=heDay(dd)+' '+mo; payload.dedication=el.querySelector('.rpded').value.trim();
      }
      const r=await api('POST','/api/recon/'+encodeURIComponent(el.dataset.tid),payload);
      if(!r||!r.ok){b.disabled=false;b.textContent='✓ הכנס לכרטיס';toast('לא נכנס'+((r&&(r.detail||r.error))?': '+(r.detail||r.error):''));return;}
      await refresh(); toast('נכנס לכרטיס ✓');
    };
  });
}
function cardInfo(d,body){
  // כל פרטי הקשר של התורם במקום אחד — כתובת, טלפונים, מיילים, שם לועזי והערות
  const f=(k,v,dir)=>v?`<div class="rf"><div class="k">${k}</div><div class="v" ${dir?'dir="ltr"':''}>${esc(v)}</div></div>`:'';
  body.innerHTML=`${contactBtns(d)?`<div class="cardcbar">${contactBtns(d)}</div>`:''}
    <label class="fld"><span>שם באנגלית</span><input id="f_english" value="${esc(d.english)}" dir="ltr"></label>
    <label class="fld"><span>עסק</span><input id="f_business" value="${esc(d.business)}"></label>
    <div class="fld"><span>טלפונים</span><div id="phones" class="phones"></div></div>
    <div class="fld"><span>אימיילים</span><div id="emails" class="phones"></div></div>
    <div class="two"><label class="fld"><span>אזור / מטבע</span><select id="f_region"><option value="">🇺🇸 חו"ל ($)</option><option value="il" ${d.region==='il'?'selected':''}>🇮🇱 ארץ ישראל (₪)</option></select></label>
      <label class="fld"><span>ערוץ חיוב</span><select id="f_channel">${channelOpts(d.channel)}</select></label></div>
    <label class="fld"><span>כתובת (רחוב ומספר)</span><input id="f_addr" value="${esc(d.addr)}" dir="${d.region==='il'?'rtl':'ltr'}"></label>
    <div class="two"><label class="fld"><span>עיר</span><input id="f_city" value="${esc(d.city||'')}" dir="${d.region==='il'?'rtl':'ltr'}"></label>
      <label class="fld"><span>מדינה</span><input id="f_country" value="${esc(d.country||'')}" dir="${d.region==='il'?'rtl':'ltr'}"></label></div>
    <label class="fld"><span>מיקוד</span><input id="f_zip" value="${esc(d.zip||'')}" dir="ltr"></label>
    <label class="fld"><span>עבור מה (מטרה כללית)</span><input id="f_purpose" value="${esc(d.purpose)}"></label>
    <label class="fld"><span>📝 הערות (למשל: הגיע דרך אבא קלוק) — ניתן לחיפוש</span><textarea id="f_notes" rows="3" placeholder="כתוב כאן כל דבר שתרצה למצוא אחר כך בחיפוש">${esc(d.notes||'')}</textarea></label>
    ${d.notes?`<div class="hintxt" style="margin:-4px 2px 8px">🔎 <a class="notelink" href="#">חפש את כל מי שיש לו הערה דומה</a></div>`:''}
    <button class="btn" id="f_saveall" style="width:100%;margin:6px 0">💾 שמור פרטים</button>
    ${f('סטטוס תשלום',d.pay_status)}${d.created?f('נוסף למערכת',d.created+(d.source?(' · דרך '+d.source):'')):''}
    ${d.months?`<div class="rf" style="flex-direction:column;gap:6px"><div class="k">מפת חודשים${gaps(d.months).length?' · <b style="color:var(--no)">'+gaps(d.months).length+' לא עברו</b>':''}</div>${monthGrid(d.months)}</div>`:''}`;
  renderPhones(d); renderEmails(d);
  const INF=['english','business','region','channel','addr','city','country','zip','purpose','notes'];
  wireFields(d,INF);
  const sv=document.getElementById('f_saveall');
  if(sv)sv.onclick=async()=>{
    const body2={};
    INF.forEach(k=>{const el=document.getElementById('f_'+k); if(el)body2[k]=el.value;});
    await api('PUT','/api/donor/'+d.id,body2);
    Object.assign(d,body2); toast('נשמר ✓'); if(tab==='donors')renderDonors();
  };
  const nl=body.querySelector('.notelink');
  if(nl)nl.onclick=e=>{e.preventDefault();ov.classList.remove('show');
    q=(String(d.notes||'').split(/[·\n]/)[0]||'').trim().slice(0,30);
    const si=document.getElementById('q'); if(si)si.value=q;
    try{localStorage.removeItem('kc_donor');}catch(err){}
    tab='donors';document.querySelectorAll('.tab').forEach(x=>x.classList.toggle('on',x.dataset.tab==='donors'));
    flt=''; render();};
}
function cardContact(d,body){
  body.innerHTML=`
    ${contactBtns(d)?`<div class="cardcbar">${contactBtns(d)}</div>`:''}
    <div class="sec"><h3>➕ רישום קשר חדש <button class="btn sm ghost" id="cl_mailsync" style="float:left">📥 משוך מיילים</button></h3>
      <div class="addrow"><select id="cl_ch"><option>טלפון</option><option>אימייל</option><option>וואטסאפ</option><option>פגישה</option></select><input id="cl_date" type="date" value="${todayStr()}"></div>
      <textarea id="cl_sum" rows="2" placeholder="מה סוכם / תוכן השיחה" style="margin-top:6px"></textarea>
      <div class="avfiles dnfiles" id="cl_files"><label class="filebtn sm">📎 צרף כרטיס אשראי / הקלטה / צילום<input type="file" multiple accept="image/*,audio/*,application/pdf" id="cl_file" hidden></label></div>
      <div class="addrow"><input id="cl_next" type="date" title="מתי לחזור"><button class="btn sm" id="cl_add">שמור</button></div>
      <div class="hintxt">התאריך התחתון = מתי לחזור אליו (נכנס ל"משימות")</div></div>
    <details class="dsec"><summary>🔔 קביעת תזכורת</summary>
      <div class="addrow"><select id="tk_kind">${taskKindOpts()}</select><input id="tk_date" type="date"></div>
      <div class="addrow"><input id="tk_note" placeholder="פרטים (על מה)"><button class="btn sm" id="tk_add">➕ קבע תזכורת</button></div>
      <div class="avfiles dnfiles" id="tk_files"><label class="filebtn sm">📎 צרף כרטיס אשראי / הקלטה / צילום<input type="file" multiple accept="image/*,audio/*,application/pdf" id="tk_file" hidden></label></div>
      <div class="hintxt">כל תזכורת נכנסת ללשונית "משימות", ואפשר להוסיף אותה ליומן Google.</div></details>
    <div class="sec"><h3>🔔 תזכורות פתוחות</h3><div id="tlist"></div></div>
    <div class="sec"><h3>📞 תיעוד קשר</h3><div id="clog"></div></div>`;
  renderContacts(d); renderReminders(d);
  const clF=pendFiles('cl_files','cl_file'), tkF=pendFiles('tk_files','tk_file');
  const refresh=async()=>{await load();const dd=DB.find(x=>x.id===d.id);if(dd){d.contacts=dd.contacts;d.tasks=dd.tasks;}renderContacts(d);renderReminders(d);};
  const msb=document.getElementById('cl_mailsync');
  if(msb)msb.onclick=async()=>{
    if(!(d.email||'').trim()){toast('אין כתובת מייל בכרטיס — הוסף אותה כדי לתייק מיילים');return;}
    await runMailSync(msb); await refresh();
  };
  document.getElementById('cl_add').onclick=async()=>{const ch=document.getElementById('cl_ch').value,date=document.getElementById('cl_date').value,sum=document.getElementById('cl_sum').value.trim(),next=document.getElementById('cl_next').value;if(!sum&&!date)return;const r=await api('POST','/api/contact',{donor_id:d.id,channel:ch,date:date,summary:sum,next_date:next});d.contacts=d.contacts||[];d.contacts.unshift({id:r.id,channel:ch,date:date,summary:sum,next_date:next});if(next){d.tasks=d.tasks||[];d.tasks.push({id:r.task_id,donor_id:d.id,due_date:next,kind:'followup',note:sum.slice(0,80),done:0});}document.getElementById('cl_sum').value='';
    if(clF.arr.length){toast('מעלה קבצים…');for(const f of clF.arr)await uploadBlob('contact',r.id,f);clF.reset();await refresh();toast('נשמר עם האסמכתאות ✓');return;}
    renderContacts(d);renderReminders(d);toast('נשמר ✓');};
  wireKindSel(document.getElementById('tk_kind'));
  addMic(document.getElementById('cl_sum')); addMic(document.getElementById('tk_note'));
  document.getElementById('tk_add').onclick=async()=>{const kind=await kindValue(document.getElementById('tk_kind'));if(!kind)return;const note=document.getElementById('tk_note').value.trim(),date=document.getElementById('tk_date').value;if(!date){toast('בחר תאריך');return;}const r=await api('POST','/api/task',{donor_id:d.id,due_date:date,kind:kind,note:note});d.tasks=d.tasks||[];d.tasks.push({id:r.id,donor_id:d.id,due_date:date,kind:kind,note:note,done:0});document.getElementById('tk_note').value='';
    if(tkF.arr.length){toast('מעלה קבצים…');for(const f of tkF.arr)await uploadBlob('task',r.id,f);tkF.reset();await refresh();toast('נקבעה תזכורת עם האסמכתאות ✓');return;}
    renderReminders(d);toast('נקבעה תזכורת ✓');};
}
function renderReminders(d){
  const el=document.getElementById('tlist');if(!el)return;
  const td=todayStr(),donor=(d.last+' '+d.first).trim();
  const list=(d.tasks||[]).filter(t=>!t.done||t.done==0).sort((a,b)=>(a.due_date||'9999').localeCompare(b.due_date||'9999'));
  el.innerHTML=list.map(t=>{const over=t.due_date&&t.due_date<=td,g=gcalLink(t,donor);
    return `<div class="remitem ${over?'over':''}"><div class="ri"><b>${esc(kindLabel(t.kind))}</b> ${esc(t.due_date||'')} ${t.note?('· '+esc(t.note)):''}
      <div class="avfiles">${(t.files||[]).map(fileChip).join('')}<label class="filebtn">📎 צרף תמונה / הקלטה<input type="file" accept="image/*,audio/*,application/pdf" class="tkup" data-id="${t.id}" hidden></label></div></div>
      ${whoChipHTML(t,'data-rwho="'+t.id+'"')}${g?`<a class="gcal" href="${g}" target="_blank" rel="noopener">➕ ליומן</a>`:''}
      <button class="stbtn" style="background:var(--yes);color:#fff" data-done="${t.id}">✓</button><button class="del" data-del="${t.id}">🗑</button></div>`;}).join('')||'<div class="hintxt">אין תזכורות. הוסף למטה.</div>';
  el.querySelectorAll('[data-rwho]').forEach(b=>b.onclick=async e=>{e.stopPropagation();b.disabled=true;await flipWho(b.dataset.rwho);renderReminders(d);});
  el.querySelectorAll('[data-done]').forEach(b=>b.onclick=async()=>{const t=d.tasks.find(x=>x.id==b.dataset.done);if(t){t.done=1;await api('PUT','/api/task/'+t.id,{done:1});}renderReminders(d);toast('בוצע ✓');});
  el.querySelectorAll('.del').forEach(b=>b.onclick=async()=>{await api('DELETE','/api/task/'+b.dataset.del);d.tasks=d.tasks.filter(x=>x.id!=b.dataset.del);renderReminders(d);});
  el.querySelectorAll('.tkup').forEach(inp=>inp.onchange=()=>uploadFile('task',+inp.dataset.id,inp,async()=>{await load();const dd=DB.find(x=>x.id===d.id);if(dd)d.tasks=dd.tasks;renderReminders(d);}));
  el.querySelectorAll('.fdel').forEach(b=>b.onclick=async()=>{await api('DELETE','/api/file/'+b.dataset.fid);(d.tasks||[]).forEach(t=>{t.files=(t.files||[]).filter(f=>f.id!=b.dataset.fid);});renderReminders(d);toast('נמחק');});
}
const FBCH={'תודה':'🙏 תודה','הקדשה':'🖼️ הקדשה','אימייל':'📧 אימייל','וואטסאפ':'💬 וואטסאפ','טלפון':'📞 טלפון'};
const FBOPTS=[['','— איך יצרנו קשר? —'],['תודה','🙏 אמרנו תודה'],['הקדשה','🖼️ שלחנו תמונת הקדשה'],['אימייל','📧 אימייל'],['וואטסאפ','💬 וואטסאפ'],['טלפון','📞 טלפון']];
function fbChip(x){
  if(!x.fb_channel) return '';
  return `<span class="fbchip on">✓ פידבק · ${FBCH[x.fb_channel]||esc(x.fb_channel)}${x.fb_date?(' · '+esc(x.fb_date)):''}${x.fb_followup?(' · 🔁 לחזור '+esc(x.fb_followup)):''}</span>`;
}
// מעקב "הודינו?" — על תרומות מאוגוסט 2026 ואילך (וכל תרומה חדשה מכאן)
const THANKS_FROM='2026-07-01';   // כל תרומה מ-1 ביולי ואילך — מעקב "הודינו?"
function needThanks(x){let d=(x.date||'').slice(0,10);if(!d)return true;if(d.length===7)d+='-01';return d>=THANKS_FROM;}
function unthankedCount(d){return (d.donations||[]).filter(x=>needThanks(x)&&!+x.thanked).length;}
// הערה חופשית שנרשמה לתרומה (בלי סימוני הייבוא הטכניים)
// כל האברכים במערכת — לבחירה כשמסווגים יששכר־זבולון
function allAvreichim(){const s=new Set();DB.forEach(d=>(d.partners||[]).forEach(p=>{const a=(p.avreich||'').trim();if(a)s.add(a);}));
  return [...s].sort((a,b)=>a.localeCompare(b,'he'));}
const isIZcat=c=>/יששכר|יש"?ז/.test(c||'');
let AVLIST=[];
function avOpts(sel){
  const src=AVLIST.length?AVLIST:allAvreichim().map(n=>({name:n,taken:true,holders:[]}));
  return '<option value="">— בחר אברך מהרשימה —</option>'
    +src.map(a=>{const t=a.taken?(' — אצל '+((a.holders&&a.holders[0])?a.holders[0].name:'תורם')):' — פנוי';
      return `<option value="${esc(a.name)}" ${a.name===sel?'selected':''}>${esc(a.name)}${esc(t)}</option>`;}).join('')
    +'<option value="__new__">➕ אברך חדש — הוסף לרשימה…</option>';
}
async function loadAvList(){ try{AVLIST=await api('GET','/api/avreichim');}catch(e){} }
function wireAvNew(sel,inp,btn){
  if(!sel||!inp||!btn) return;
  sel.addEventListener('change',()=>{const on=sel.value==='__new__';
    inp.style.display=on?'block':'none';btn.style.display=on?'block':'none';if(on)inp.focus();});
  btn.onclick=async()=>{
    const nm=inp.value.trim(); if(nm.length<2){toast('כתוב את שם האברך');inp.focus();return;}
    btn.disabled=true;
    const r=await api('POST','/api/avreich/new',{name:nm});
    btn.disabled=false;
    if(!r||!r.ok){toast('ההוספה נכשלה');return;}
    await loadAvList();
    document.querySelectorAll('select.uav1,#ucl_av').forEach(s2=>{s2.innerHTML=avOpts(s2===sel?nm:s2.value);});
    inp.value='';inp.style.display='none';btn.style.display='none';
    toast(r.existed?'האברך כבר היה ברשימה ✓':'האברך נוסף לרשימה ✓');};
}
// ההערה שנשמרה על התרומה, כטקסט נקי — בלי "ייבוא…" ובלי הסימון "לא סווג"
function dnNoteText(x){
  let t=String(x.note||'').replace(/<[^>]*>/g,' ');
  t=t.replace(/^ייבוא[^·]*(·\s*הוראת קבע)?\s*·?\s*/,'').replace(/^ייבוא\s*2026\s*$/,'');
  t=t.replace(/\s*·?\s*לא סווג[^·]*/,'');
  return t.replace(/\s{2,}/g,' ').replace(/^[\s·]+|[\s·]+$/g,'').trim();
}
function dnNote(x){
  const t=dnNoteText(x);
  return t?`<div class="dnnote">📝 ${esc(t)}</div>`:'';
}
// במסך הראשי משאירים רק הערה אמיתית (מי תרם בשמו, דרך מי) — לא מספרי אסמכתא ולא שמות דוחות
const GVNOISE=/^(דוח הקבועים|הוראת קבע|דרגת יששכר־זבולון|קבוע|מזדמן)$/;
const GVDROP=/^(דוח הקבועים|הוראת קבע|דרגת יששכר־זבולון|אסמכתא .*)$/;
function giveNote(x){
  let t=dnNoteText(x).split('·').map(s=>s.trim()).filter(s=>s&&!GVDROP.test(s)).join(' · ');
  t=t.replace(/^[\s·]+|[\s·]+$/g,'').trim();
  if(t===String(x.category||'').trim())return '';   // חוזר על הייעוד שכבר מוצג בבורר
  return GVNOISE.test(t)?'':t;
}
// רשימת הייעודים לבחירה — הקבועים שלנו + כל המגביות, ואפשרות להוסיף חדש בלי לצאת מהשורה
const DNMETH=['אשראי','אונליין','המחאה','מזומן','העברה בנקאית','זל','קפיטל 1','בנק ווסט','אוטורייז','דונרס פאנד','OJC','נדרים'];
const DNBASE=['קבוע','יששכר־זבולון','פרנס לילה','חדר קפה','ארוחת בוקר','נר למאור','קוויטל','בניין','מזדמן','חד-פעמי'];
function dnCatList(){return DNBASE.concat((CAMPAIGNS||[]).filter(c=>c&&!DNBASE.includes(c)));}
function dnCatOpts(cur){
  const L=dnCatList();
  return `<option value="">— עבור מה? —</option>`
    +(cur&&!L.includes(cur)?`<option value="${esc(cur)}" selected>${esc(cur)}</option>`:'')
    +L.map(c=>`<option value="${esc(c)}"${c===cur?' selected':''}>${esc(c)}</option>`).join('')
    +`<option value="__new__">➕ ייעוד חדש…</option>`;
}
function dnRow(x,cur){cur=cur||'$';
  return `<div class="dncrow"><div class="dnci"><b>${cur}${esc(x.amount)}</b>${x.category?(' · '+esc(x.category)):''} <span class="dnmeta">${x.date?esc(gregLabel(x.date)):''}</span>${x.method?(' '+(chBadgeRaw(x.method)||'<span class="givemeth">'+esc(chLabel(x.method))+'</span>')):''}${x.fb_channel?`<span class="fbmini">✓ ${FBCH[x.fb_channel]||esc(x.fb_channel)}${x.fb_followup?(' · 🔁'+esc(x.fb_followup)):''}</span>`:''}${dnNote(x)}</div>`+
    `<div class="dncact"><button class="dnpaid ${+x.paid?'yes':'no'}" data-paid="${x.id}">${+x.paid?'שולם ✓':'לא שולם'}</button><button class="dnedbtn" data-id="${x.id}" title="ערוך סכום/קטגוריה">✏️ ערוך</button><button class="dnrcpt" data-id="${x.id}" title="קבלה">🧾</button><button class="dnfb" data-id="${x.id}" title="פידבק">${x.fb_channel?'✏️':'💬'}</button><button class="del" data-del="${x.id}" title="מחק">🗑</button></div></div>`+
    (needThanks(x)?`<div class="thxrow"><button class="thxbtn ${+x.thanked?'yes':'no'}" data-thx="${x.id}">${+x.thanked?'✅ הודינו':'🙏 להודות'}</button></div>`:'')+
    `<div class="avfiles dnfiles">${(x.files||[]).map(fileChip).join('')}<label class="filebtn sm">📎 אסמכתא (צ'ק / שובר / צילום)<input type="file" accept="image/*,audio/*,application/pdf" class="dnup" data-id="${x.id}" hidden></label></div>`+
    `<div class="dnedit hidden" data-de="${x.id}">
      <div class="fbrow"><label class="fld"><span>סכום (${cur})</span><input class="de_amt" value="${esc(x.amount)}"></label>
        <label class="fld"><span>🎯 עבור מה</span><select class="de_cat" data-id="${x.id}">${dnCatOpts(x.category||'')}</select></label></div>
      <div class="addrow hidden" data-denew="${x.id}"><input class="de_catnew" placeholder="שם הייעוד החדש…"></div>
      <div class="fbrow"><label class="fld"><span>אמצעי</span><input class="de_method" list="dnmeths" value="${esc(x.method||'')}"></label>
        <label class="fld"><span>סטטוס</span><select class="de_paid"><option value="1" ${+x.paid?'selected':''}>✓ שולם</option><option value="0" ${+x.paid?'':'selected'}>לא שולם</option></select></label></div>
      <label class="fld"><span>📅 תאריך מדויק${(x.date||'').length===7?' — חסר יום, אפשר להשלים':''}</span><input type="date" class="de_date" value="${esc((x.date||'').length===10?x.date:'')}"></label>
      <button class="btn sm de_save" data-id="${x.id}">שמור שינויים</button>
    </div>`+
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
  const dncats=['קבוע','מזדמן','יששכר־זבולון','פרנס לילה','חדר קפה','ארוחת בוקר','נר למאור','חד-פעמי'].concat(CAMPAIGNS||[]);
  const dmeths=['אשראי','אונליין','המחאה','מזומן','העברה בנקאית','בנק ווסט','Banquest','Authorize'];
  // פרנס יום — מוצג גם כאן בתרומות, עם סטטוס גבייה (נגבה/חוב)
  const pns=(d.parnes||[]).filter(p=>p.status!=='suggested');
  const pnsHtml=pns.length?`<div class="dncount">🌙 פרנס יום (${pns.length})</div>`+pns.map(p=>{const pc=p.currency||'$',pd=+p.paid;return `<div class="dncrow"><div class="dnci"><b>${pc}${esc(p.amount||'—')}</b> · ${esc(DAYKIND[p.kind]||'🌙 פרנס')} ${esc(p.date_text||'')}${p.hyear?(' '+esc(p.hyear)):''} <span class="pstat ${pd?'yes':'no'}">${pd?'✓ נגבה':'🔴 טרם נגבה'}</span></div><div class="dncact"><button class="collectbtn ${pd?'yes':'no'} pnspaid" data-pid="${p.id}">${pd?'בטל':'✓ נגבה'}</button></div></div>`;}).join(''):'';
  el.innerHTML=(list.length?`<div class="dncount">${list.length} תרומות · ${cur}${tot}</div>`:'')+(list.map(x=>dnRow(x,cur)).join('')||'<div class="hintxt">עדיין אין תרומות.</div>')+pnsHtml
    +`<datalist id="dncats">${dncats.map(c=>`<option value="${esc(c)}">`).join('')}</datalist><datalist id="dnmeths">${dmeths.map(c=>`<option value="${esc(c)}">`).join('')}</datalist>`;
  el.querySelectorAll('.pnspaid').forEach(b=>b.onclick=async()=>{const p=(d.parnes||[]).find(x=>x.id==b.dataset.pid);if(!p)return;p.paid=+p.paid?0:1;await api('PUT','/api/parnes/'+p.id,{paid:p.paid});toast(+p.paid?'נגבה ✓':'סומן כחוב');renderDonations(d);});
  el.querySelectorAll('.dnpaid').forEach(b=>b.onclick=async()=>{const x=d.donations.find(y=>y.id==b.dataset.paid);x.paid=+x.paid?0:1;await api('PUT','/api/donation/'+x.id,{paid:x.paid});renderDonations(d);});
  el.querySelectorAll('.dnedbtn').forEach(b=>b.onclick=()=>{el.querySelector('.dnedit[data-de="'+b.dataset.id+'"]').classList.toggle('hidden');});
  // "ייעוד חדש" בבורר פותח שדה טקסט לשם החדש
  el.querySelectorAll('.de_cat').forEach(sel=>sel.onchange=()=>{
    const nb=el.querySelector('[data-denew="'+sel.dataset.id+'"]');
    if(nb){nb.classList.toggle('hidden',sel.value!=='__new__'); if(sel.value==='__new__')nb.querySelector('.de_catnew').focus();}});
  el.querySelectorAll('.de_save').forEach(b=>b.onclick=async()=>{
    const box=el.querySelector('.dnedit[data-de="'+b.dataset.id+'"]');
    const x=d.donations.find(y=>y.id==b.dataset.id); if(!x)return;
    x.amount=box.querySelector('.de_amt').value.trim();
    let cat=box.querySelector('.de_cat').value.trim();
    if(cat==='__new__'){cat=(box.querySelector('.de_catnew')||{value:''}).value.trim();
      if(!cat){toast('כתוב את שם הייעוד החדש');return;}}
    x.category=cat;
    x.method=box.querySelector('.de_method').value.trim(); x.paid=+box.querySelector('.de_paid').value;
    const nd=box.querySelector('.de_date').value; if(nd)x.date=nd;
    await api('PUT','/api/donation/'+x.id,{amount:x.amount,category:x.category,method:x.method,paid:x.paid,date:x.date});
    if(x.category&&!(CAMPAIGNS||[]).includes(x.category)&&!['קבוע','מזדמן','יששכר־זבולון','פרנס לילה','חדר קפה','ארוחת בוקר','נר למאור','חד-פעמי'].includes(x.category)){api('POST','/api/campaigns',{name:x.category});CAMPAIGNS.unshift(x.category);}
    renderDonations(d);toast('עודכן ✓');
  });
  el.querySelectorAll('.thxbtn').forEach(b=>b.onclick=async()=>{
    const x=d.donations.find(y=>y.id==b.dataset.thx);if(!x)return;
    x.thanked=+x.thanked?0:1;await api('PUT','/api/donation/'+x.id,{thanked:x.thanked});
    renderDonations(d);if(tab==='donors')renderDonors();toast(x.thanked?'סומן: הודינו ✓':'סומן: עדיין לא הודינו');});
  el.querySelectorAll('.dnup').forEach(inp=>inp.onchange=()=>uploadFile('donation',+inp.dataset.id,inp,async()=>{await load();const dd=DB.find(y=>y.id===d.id);if(dd)d.donations=dd.donations;renderDonations(d);}));
  el.querySelectorAll('.dnfiles .fdel').forEach(b=>b.onclick=async()=>{await api('DELETE','/api/file/'+b.dataset.fid);(d.donations||[]).forEach(x=>{x.files=(x.files||[]).filter(f=>f.id!=b.dataset.fid);});renderDonations(d);toast('נמחק');});
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
    `</div>`+
    `<div class="avfiles dnfiles">${(t.files||[]).map(fileChip).join('')}<label class="filebtn sm">📎 אסמכתא<input type="file" accept="image/*,audio/*,application/pdf" class="txup" data-id="${t.id}" hidden></label></div>`+
    `</div>`;
}
function wireTx(el,d,after){
  el.querySelectorAll('.txst').forEach(s=>s.onchange=async()=>{const t=d.transactions.find(x=>x.id==s.dataset.id);t.status=s.value;await api('PUT','/api/transaction/'+t.id,{status:t.value});after();toast('עודכן ✓');});
  el.querySelectorAll('.txpay').forEach(b=>b.onclick=async()=>{const t=d.transactions.find(x=>x.id==b.dataset.id);t.inst_paid=(+t.inst_paid||0)+1;const upd={inst_paid:t.inst_paid};if(+t.inst_total>0&&t.inst_paid>=+t.inst_total){t.status='settled';upd.status='settled';}await api('PUT','/api/transaction/'+t.id,upd);after();toast('תשלום נרשם ✓');});
  el.querySelectorAll('.txrcpt').forEach(b=>b.onclick=()=>{const t=d.transactions.find(x=>x.id==b.dataset.id);openReceipt(d,t);});
  el.querySelectorAll('.del').forEach(b=>b.onclick=async()=>{await api('DELETE','/api/transaction/'+b.dataset.del);d.transactions=d.transactions.filter(x=>x.id!=b.dataset.del);after();});
  el.querySelectorAll('.txup').forEach(inp=>inp.onchange=()=>uploadFile('transaction',+inp.dataset.id,inp,async()=>{await load();const dd=DB.find(y=>y.id===d.id);if(dd)d.transactions=dd.transactions;after();}));
  el.querySelectorAll('.dnfiles .fdel').forEach(b=>b.onclick=async()=>{await api('DELETE','/api/file/'+b.dataset.fid);(d.transactions||[]).forEach(t=>{t.files=(t.files||[]).filter(f=>f.id!=b.dataset.fid);});after();toast('נמחק');});
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
  view.innerHTML=`<div class="rbtitle">💳 טיפול והתאמת תרומות — לפי שיטת תשלום (ינואר–אוגוסט 2026)</div>
    <div class="addrow" style="margin:0 2px 8px"><button class="btn sm ghost" id="ch_mailsync" style="width:100%">📥 משוך מיילים (נכנסים + ששלחנו) ותייק אצל התורמים</button></div>
    <div class="addrow" style="margin:0 2px 8px"><button class="btn sm ghost" id="ch_audit" style="width:100%">🔍 בדיקת סתירות — אקסל מול חיובים בפועל</button></div>
    <div id="auditbox"></div>
    <div id="reconboxes" class="reconboxes"></div>
    <div class="totals"><div class="tot"><span>נגבה / אושר</span><b>$${Math.round(paid)}</b></div><div class="tot year"><span>ממתין לגבייה</span><b>$${Math.round(pend)}</b></div></div>`+
    `<div class="cnt">${rows.length} חיובים</div><div class="list">`+
    (rows.map(({t,d})=>{const st=TXST[t.status]||TXST.pending;const rc=curSym(d);return `<div class="rowc" data-id="${d.id}"><div><div class="nm">${esc(d.last)} <small>${esc(d.first)}</small></div><div class="purp">${rc}${esc(t.amount)} ${t.category?('· '+esc(t.category)):''}${txInst(t,rc)}${txUntil(t)}</div></div><div class="meta"><span class="txbadge ${st.c}">${st.t}</span><span class="ph">${esc(t.date||'')}${t.method?(' · '+esc(t.method)):''}</span></div></div>`;}).join('')||'<div class="empty">אין חיובים</div>')+`</div>`;
  view.querySelectorAll('.rowc').forEach(r=>r.onclick=()=>openDonor(DB.find(x=>x.id==r.dataset.id)));
  const cms=document.getElementById('ch_mailsync');
  if(cms)cms.onclick=()=>runMailSync(cms);
  const cau=document.getElementById('ch_audit');
  if(cau)cau.onclick=async()=>{
    const box=document.getElementById('auditbox');
    if(box.innerHTML){box.innerHTML='';return;}
    cau.disabled=true;cau.textContent='בודק…';
    const r=await api('GET','/api/audit/excel');
    cau.disabled=false;cau.textContent='🔍 בדיקת סתירות — אקסל מול חיובים בפועל';
    const it=(r&&r.items)||[];
    const over=it.filter(x=>x.diff<0), under=it.filter(x=>x.diff>0);
    const sum=a=>a.reduce((s,x)=>s+Math.abs(x.diff),0);
    const row=x=>`<div class="rowc auditrow" data-id="${x.id}"><div>
        <div class="nm">${esc(x.name)} <span class="rownum">#${x.id}</span></div>
        <div class="miss2">${esc(x.method)} · אקסל: ${x.xl_n} = $${Math.round(x.xl_sum).toLocaleString()} · בפועל: ${x.rc_n} = $${Math.round(x.rc_sum).toLocaleString()}</div></div>
      <div class="meta"><b style="color:${x.diff<0?'var(--no)':'var(--yes)'}">${x.diff<0?'−':'+'}$${Math.round(Math.abs(x.diff)).toLocaleString()}</b></div></div>`;
    box.innerHTML=`<div class="hintxt" style="margin:2px">השוואה לתקופה ${esc(r.from||'')} – ${esc(r.to||'')} (מה שהאקסל מכסה). החיובים בפועל הם המקור הנכון.</div>
      <div class="misshead">🔴 רשום אצלנו יותר ממה שנגבה (${over.length}) — סה"כ $${Math.round(sum(over)).toLocaleString()}</div>
      <div class="hintxt" style="margin:0 2px 4px">כסף שרשום בכרטיס אבל אין לו חיוב מקביל — כאן כדאי לבדוק.</div>
      <div class="list">${over.map(row).join('')||'<div class="hintxt">אין 🎉</div>'}</div>
      <div class="misshead" style="color:var(--yes)">🟢 נגבה ועדיין לא הוכנס לכרטיס (${under.length}) — סה"כ $${Math.round(sum(under)).toLocaleString()}</div>
      <div class="hintxt" style="margin:0 2px 4px">ברובו פשוט חיובים שעוד לא אישרת בדף החיובים.</div>
      <div class="list">${under.map(row).join('')}</div>`;
    box.querySelectorAll('.auditrow').forEach(el=>el.onclick=()=>openDonor(DB.find(x=>x.id==el.dataset.id),'details'));
  };
  // משבצת נפרדת לכל שיטת תשלום — נטענת מסיכום ההתאמה
  api('GET','/api/recon/summary').then(gs=>{const box=document.getElementById('reconboxes');if(!box||!Array.isArray(gs))return;
    box.innerHTML=gs.map(g=>{const active=g.total>0;
      return `<a class="reconbox ${active?'act':'empty'}" ${active?`href="/reconcile?src=${g.key}" target="_blank" rel="noopener"`:''}>
        <div class="rb-t">${g.icon} ${esc(g.label)}</div>
        <div class="rb-s">${active?('<b>'+g.pending+'</b> לטיפול · '+g.done+' טופלו'):'יעלה כשתשלח את הקובץ'}</div></a>`;}).join('');
  });
}
// רענון בלוק הסיכום של יש"ז בלבד (בלי לרנדר מחדש את כל הכרטיס ולסגור חלוניות)
function refreshIzSum(d){
  const box=document.querySelector('.izsum'); if(!box)return;
  const w=document.createElement('div'); w.innerHTML=izSummaryHTML(d);
  const nb=w.firstElementChild; if(!nb)return;
  box.replaceWith(nb);
  nb.querySelectorAll('.cosp2[data-did]').forEach(x=>x.onclick=()=>{const dd=DB.find(y=>y.id==x.dataset.did);if(dd)openDonor(dd);});
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
    <label class="fld"><span>מתאריך (עברי)</span><input class="pfield" data-id="${p.id}" data-k="start_date" value="${esc(p.start_date||'')}" placeholder="א' אייר תשפ״ו"></label>
    <div class="fld"><span>🤝 מחזיקים יחד עם (אפשר כמה שותפים)</span>
      <div class="pwchips" data-id="${p.id}">${pwList(p).map((x,i)=>`<span class="pwchip">${x.id?'🔗 ':''}${esc(x.name)}<button class="pwx" data-id="${p.id}" data-idx="${i}" title="הסר">✕</button></span>`).join('')}</div>
      <input class="pwadd" data-id="${p.id}" placeholder="➕ הוסף שותף — חפש שם ובחר…" autocomplete="off"><div class="pwres dpres" data-id="${p.id}"></div></div>
    <label class="jointchk"><input type="checkbox" class="pjoint" data-id="${p.id}" ${+p.joint?'checked':''}> 🤝 מחזיקים אותו <b>ביחד</b> — הסכום למעלה הוא הסכום המשותף לכולם</label>
    ${+p.joint&&jointHolders(p)>1?`<label class="fld"><span>💳 מי משלם בפועל</span><select class="ppayer" data-id="${p.id}">
      <option value="">כל אחד את חלקו (${curSym(d)}${Math.round(amtNum(p.amount)/jointHolders(p))} לכל אחד)</option>
      ${jointGroup(p).map(g=>`<option value="${g.d.id}" ${jointPayerId(p)===g.d.id?'selected':''}>${esc(((g.d.business||'').trim()||((g.d.last||'')+' '+(g.d.first||'')).trim()))} — משלם את כל ${curSym(d)}${amtNum(p.amount)}</option>`).join('')}
    </select></label>
    <div class="hintxt" style="margin:-6px 2px 6px">כשעסק אחד או כרטיס אחד משלם על כולם — בחר אותו כאן, והסכום ייזקף רק אליו. ההגדרה חלה על כל המחזיקים.</div>`:''}
    <label class="fld"><span>💵 שילם עד סוף חודש (מזומן / צ'ק ביד — תשלום שלא נרשם במערכת)</span><input type="month" class="pfield" data-id="${p.id}" data-k="paid_thru" value="${esc(p.paid_thru||'')}"></label>
    <label class="fld"><span>💰 עדכון תשלום ידני (למשל: "שילם הכל מראש 13/7")</span><input class="pfield" data-id="${p.id}" data-k="paid_note" value="${esc(p.paid_note||'')}" placeholder="הערת תשלום — נשמר ומוצג בסיכום"></label>
    <label class="fld"><span>הערות</span><input class="pfield" data-id="${p.id}" data-k="note" value="${esc(p.note||'')}" placeholder="הערה (רשות)"></label>
    <button class="btn sm psave" data-id="${p.id}" style="width:100%;margin-top:4px">💾 שמור אברך</button>
  </div>`).join('')||'<div class="hintxt">עדיין לא הוזן. הוסף אברך למטה.</div>';
  el.innerHTML+=`<div class="izshtar"><div class="izshtar-t">📝 מעקב חוב יששכר־זבולון</div>
      <label class="fld"><span>🔴 כמה הוא חייב עכשיו (${cur}) — עדכון ידני שגובר על החישוב</span><input id="iz_debt" inputmode="decimal" value="${esc(d.iz_debt||'')}" placeholder="השאר ריק כדי לחשב אוטומטית"></label>
      <textarea id="iz_note" rows="2" placeholder="למשל: השלים חוב עד חודש תמוז · חייב 3 חודשים · שילם $4500 ב-13/7">${esc(d.iz_note||'')}</textarea>
      <button class="btn sm" id="iz_note_save" style="margin-top:4px">💾 שמור חוב והערה</button></div>
    <div class="izshtar"><div class="izshtar-t">📄 שטר שותפות:</div><div class="avfiles">${izfiles.map(fileChip).join('')||'<span class="hintxt">אין שטר עדיין</span>'}<label class="filebtn">📎 העלה שטר הסכם<input type="file" accept="application/pdf,image/*" class="pshtar" hidden></label></div></div>`;
  const izn=el.querySelector('#iz_note'),izd=el.querySelector('#iz_debt');
  const iznSave=async()=>{d.iz_note=izn.value;d.iz_debt=izd?izd.value.trim():(d.iz_debt||'');
    await api('PUT','/api/donor/'+d.id,{iz_note:izn.value,iz_debt:d.iz_debt});
    refreshIzSum(d);toast('נשמר ✓');};
  if(izn){izn.onblur=()=>{if((d.iz_note||'')!==izn.value)iznSave();};el.querySelector('#iz_note_save').onclick=iznSave;}
  if(izd)izd.onblur=()=>{if((d.iz_debt||'')!==izd.value.trim())iznSave();};
  el.querySelectorAll('.pfield').forEach(inp=>{
    const save=async()=>{const p=(d.partners||[]).find(x=>x.id==inp.dataset.id);if(!p)return;p[inp.dataset.k]=inp.value;await api('PUT','/api/partner/'+p.id,{[inp.dataset.k]:inp.value});refreshIzSum(d);if(inp.dataset.k==='amount'&&tab==='donors')renderDonors();};
    inp.onchange=save;let tmr;inp.oninput=()=>{clearTimeout(tmr);tmr=setTimeout(save,800);};
  });
  el.querySelectorAll('.psave').forEach(btn=>btn.onclick=async()=>{
    const p=(d.partners||[]).find(x=>x.id==btn.dataset.id);if(!p)return;
    const body={};el.querySelectorAll('.pfield[data-id="'+btn.dataset.id+'"]').forEach(inp=>{p[inp.dataset.k]=inp.value;body[inp.dataset.k]=inp.value;});
    await api('PUT','/api/partner/'+p.id,body);refreshIzSum(d);toast('נשמר ✓');if(tab==='donors')renderDonors();
  });
  // שדה שותפים — מספר שותפים (צ'יפים). בחירה מרשימה מקשרת לכרטיס (מופיע גם אצלו); Enter מוסיף כטקסט
  const savePw=async(p)=>{p.partner_with=pwList(p).map(x=>x.name).join(', ');p.partner_with_id=pwList(p).map(x=>x.id).join(',');await api('PUT','/api/partner/'+p.id,{partner_with:p.partner_with,partner_with_id:p.partner_with_id});renderPartners(d);if(tab==='donors')renderDonors();};
  const addPw=async(pid,name,did)=>{const p=(d.partners||[]).find(x=>x.id==pid);if(!p)return;const l=pwList(p);l.push({name:name,id:did?String(did):''});p.partner_with=l.map(x=>x.name).join(', ');p.partner_with_id=l.map(x=>x.id).join(',');await api('PUT','/api/partner/'+p.id,{partner_with:p.partner_with,partner_with_id:p.partner_with_id});toast('שותף נוסף ✓');renderPartners(d);if(tab==='donors')renderDonors();};
  const rmPw=async(pid,idx)=>{const p=(d.partners||[]).find(x=>x.id==pid);if(!p)return;const l=pwList(p);l.splice(idx,1);p.partner_with=l.map(x=>x.name).join(', ');p.partner_with_id=l.map(x=>x.id).join(',');await api('PUT','/api/partner/'+p.id,{partner_with:p.partner_with,partner_with_id:p.partner_with_id});renderPartners(d);if(tab==='donors')renderDonors();};
  el.querySelectorAll('.ppayer').forEach(sel=>sel.onchange=async()=>{
    const p=(d.partners||[]).find(x=>x.id==sel.dataset.id); if(!p)return;
    const v=sel.value?+sel.value:null;
    await api('PUT','/api/partner/'+p.id,{joint_payer:v});
    jointGroup(p).forEach(g=>{g.p.joint_payer=v;});      // חל על כל הקבוצה גם על המסך
    toast(v?'נשמר — משלם אחד ✓':'נשמר — כל אחד את חלקו ✓');
    renderPartners(d); refreshIzSum(d); if(tab==='donors')renderDonors();});
  el.querySelectorAll('.pjoint').forEach(cb=>cb.onchange=async()=>{const p=(d.partners||[]).find(x=>x.id==cb.dataset.id);if(!p)return;p.joint=cb.checked?1:0;await api('PUT','/api/partner/'+p.id,{joint:p.joint});toast(cb.checked?'סומן כמשותף ✓':'בוטל');renderPartners(d);if(tab==='donors')renderDonors();});
  el.querySelectorAll('.pwx').forEach(b=>b.onclick=()=>rmPw(b.dataset.id,+b.dataset.idx));
  el.querySelectorAll('.pwadd').forEach(inp=>{
    const pid=inp.dataset.id,res=el.querySelector('.pwres[data-id="'+pid+'"]');
    inp.oninput=()=>{const s=norm(inp.value);if(!s){res.innerHTML='';return;}
      const m=DB.filter(x=>x.id!==d.id&&norm(x.last+' '+x.first+' '+x.english+' '+x.business).includes(s)).slice(0,6);
      res.innerHTML=m.map(x=>`<div class="dpr" data-did="${x.id}" data-nm="${esc((x.last+' '+x.first).trim())}">${esc(x.last)} ${esc(x.first)}${x.tier==='יששכר_זבולון'?' · יש"ז':''} <span style="color:var(--muted)">#${x.id}</span></div>`).join('')||'<div class="dpr" style="color:var(--muted)">אין תוצאות — Enter להוסיף כטקסט</div>';
      res.querySelectorAll('.dpr[data-did]').forEach(r=>r.onmousedown=e=>{e.preventDefault();addPw(pid,r.dataset.nm,r.dataset.did);});
    };
    inp.onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();const v=inp.value.trim();if(v)addPw(pid,v,'');}};
    inp.onblur=()=>{setTimeout(()=>{if(res)res.innerHTML='';},200);};
  });
  el.querySelectorAll('.del').forEach(b=>b.onclick=async()=>{await api('DELETE','/api/partner/'+b.dataset.del);d.partners=d.partners.filter(x=>x.id!=b.dataset.del);renderPartners(d);});
  el.querySelectorAll('.fdel').forEach(b=>b.onclick=async()=>{await api('DELETE','/api/file/'+b.dataset.fid);d.files=(d.files||[]).filter(x=>x.id!=b.dataset.fid);renderPartners(d);toast('נמחק');});
  const up=el.querySelector('.pshtar');if(up)up.onchange=()=>uploadFile('iz',d.id,up,load);
}
function renderContacts(d){
  const el=document.getElementById('clog');if(!el)return;
  el.innerHTML=(d.contacts||[]).map(c=>`<div class="logrow${c.direction==='out'?' outmail':''}"><div class="pi"><b>${c.direction==='out'?'📤 שלחנו':esc(c.channel)}</b> <small>${esc(c.date||'')}</small>${c.next_date?(' · <span style="color:var(--no)">חזור: '+esc(c.next_date)+'</span>'):''}<br>${esc(c.summary||'')}${(c.body||'').trim()?`<details class="mailfull"><summary>הצג את המייל המלא${(c.body_he||'').trim()?' (בעברית)':''}</summary>
      ${(c.body_he||'').trim()?`<pre class="mhe">${esc(c.body_he)}</pre>
        <details class="morig"><summary>🔤 הצג את המקור באנגלית</summary><pre>${esc(c.body)}</pre></details>`
      :`<pre>${esc(c.body)}</pre>${/[A-Za-z]{4}/.test(c.body||'')?`<button class="btn sm ghost mtr" data-cid="${c.id}">🌐 תרגם לעברית</button>`:''}`}
    </details>`:''}
    <div class="avfiles">${(c.files||[]).map(fileChip).join('')}<label class="filebtn">📎 צרף תמונה / הקלטה<input type="file" accept="image/*,audio/*,application/pdf" class="clup" data-id="${c.id}" hidden></label>
      <button class="btn sm ghost clrem" data-id="${c.id}">🔔 קבע תזכורת${(c.files||[]).length?' + האסמכתאות':''}</button></div>
    <div class="teditpanel hidden" data-rem="${c.id}">
      <div class="fbrow"><label class="fld"><span>סוג</span><select class="cr_kind">${taskKindOpts()}</select></label>
        <label class="fld"><span>מתי להזכיר</span><input type="date" class="cr_date" value="${esc(todayStr())}"></label></div>
      <label class="fld"><span>פרטים</span><input class="cr_note" value="${esc(c.summary||'')}"></label>
      <button class="btn sm cr_save" data-id="${c.id}" style="margin-top:6px">➕ צור תזכורת</button>
    </div></div><button class="del" data-del="${c.id}">🗑</button></div>`).join('')||'<div class="hintxt">אין עדיין תיעוד.</div>';
  el.querySelectorAll('.del').forEach(b=>b.onclick=async()=>{await api('DELETE','/api/contact/'+b.dataset.del);d.contacts=d.contacts.filter(x=>x.id!=b.dataset.del);renderContacts(d);});
  el.querySelectorAll('.clup').forEach(inp=>inp.onchange=()=>uploadFile('contact',+inp.dataset.id,inp,async()=>{await load();const dd=DB.find(x=>x.id===d.id);if(dd){d.contacts=dd.contacts;}renderContacts(d);}));
  el.querySelectorAll('.mtr').forEach(b=>b.onclick=async()=>{
    const c=(d.contacts||[]).find(x=>x.id==b.dataset.cid);if(!c)return;
    b.disabled=true;b.textContent='מתרגם…';
    const r=await api('POST','/api/contact/'+b.dataset.cid+'/translate',{});
    if(r&&r.ok&&r.he){
      c.body_he=r.he;
      // החלפה במקום — כדי שהמייל הפתוח לא ייסגר
      const pre=b.parentElement?b.parentElement.querySelector('pre'):null;
      if(pre){
        const orig=pre.textContent;
        pre.className='mhe'; pre.textContent=r.he;
        const dd=document.createElement('details'); dd.className='morig';
        dd.innerHTML='<summary>🔤 הצג את המקור באנגלית</summary><pre></pre>';
        dd.querySelector('pre').textContent=orig;
        b.replaceWith(dd);
      }else{renderContacts(d);}
      toast('תורגם ✓');return;
    }
    b.disabled=false;b.textContent='🌐 תרגם לעברית';
    toast('לא הצלחתי לתרגם'+((r&&(r.detail||r.error))?': '+(r.detail||r.error):' — נסה שוב'));
  });
  el.querySelectorAll('.cr_kind').forEach(wireKindSel);
  el.querySelectorAll('.clrem').forEach(b=>b.onclick=()=>{el.querySelector('.teditpanel[data-rem="'+b.dataset.id+'"]').classList.toggle('hidden');});
  el.querySelectorAll('.cr_save').forEach(b=>b.onclick=async()=>{
    const box=el.querySelector('.teditpanel[data-rem="'+b.dataset.id+'"]');
    const due=box.querySelector('.cr_date').value;if(!due){toast('בחר תאריך');return;}
    b.disabled=true;
    const r=await api('POST','/api/contact/'+b.dataset.id+'/remind',
      {due_date:due,kind:(await kindValue(box.querySelector('.cr_kind')))||'other',note:box.querySelector('.cr_note').value.trim()});
    if(!r||!r.ok){toast('שגיאה ביצירת תזכורת');b.disabled=false;return;}
    await load();const dd=DB.find(x=>x.id===d.id);if(dd){d.contacts=dd.contacts;d.tasks=dd.tasks;}
    renderContacts(d);renderReminders(d);checkReminders();
    toast('נקבעה תזכורת ✓'+(r.files?' · '+r.files+' אסמכתאות הועתקו':''));
  });
  el.querySelectorAll('.fdel').forEach(b=>b.onclick=async()=>{await api('DELETE','/api/file/'+b.dataset.fid);(d.contacts||[]).forEach(c=>{c.files=(c.files||[]).filter(f=>f.id!=b.dataset.fid);});renderContacts(d);toast('נמחק');});
}
function renderPledges(d){
  const el=document.getElementById('pledges');if(!el)return;
  el.innerHTML=(d.pledges||[]).map(p=>{const g=p.status==='נתן',mo=+p.monthly;
    return `<div class="plwrap"><div class="pledge ${mo?'given':(g?'given':'pending')}"><div class="pi">
      <b>${esc(p.category)}</b> ${p.amount?('· $'+esc(p.amount)+(mo?' לחודש':'')):''}
      <br><small>${mo?'🔁 התחייבות חודשית קבועה':(g?'נתן ✓':'טרם נתן')}</small>${p.note?('<br><small>'+esc(p.note)+'</small>'):''}</div>
      <label class="jointchk plmo" title="התחייבות שחוזרת כל חודש"><input type="checkbox" class="plmonthly" data-id="${p.id}" ${mo?'checked':''}> 🔁 חודשי</label>
      ${mo?'':`<button class="stbtn" data-id="${p.id}">${g?'נתן':'טרם'}</button>`}
      <button class="del" data-del="${p.id}">🗑</button></div>
      ${mo?'':`<label class="remset">🔔 תזכורת לחיוב: <input type="date" class="plrem" data-cat="${esc(p.category)}" data-amt="${esc(p.amount)}"></label>`}</div>`;}).join('')||'<div class="hintxt">אין עדיין. הוסף למטה.</div>';
  el.querySelectorAll('.plmonthly').forEach(cb=>cb.onchange=async()=>{
    const p=(d.pledges||[]).find(x=>x.id==cb.dataset.id); if(!p)return;
    p.monthly=cb.checked?1:0; if(p.monthly)p.status='נתן';
    await api('PUT','/api/pledge/'+p.id,p);
    renderPledges(d); refreshIzSum(d); toast(p.monthly?'סומן כהתחייבות חודשית ✓':'סומן כחד־פעמי ✓');});
  el.querySelectorAll('.stbtn').forEach(b=>b.onclick=async()=>{const p=d.pledges.find(x=>x.id==b.dataset.id);p.status=p.status==='נתן'?'טרם':'נתן';await api('PUT','/api/pledge/'+p.id,p);renderPledges(d);toast('עודכן ✓');});
  el.querySelectorAll('.del').forEach(b=>b.onclick=async()=>{await api('DELETE','/api/pledge/'+b.dataset.del);d.pledges=d.pledges.filter(x=>x.id!=b.dataset.del);renderPledges(d);});
  el.querySelectorAll('.plrem').forEach(x=>x.onchange=async()=>{if(!x.value)return;const note='חייב: '+x.dataset.cat+(x.dataset.amt?(' $'+x.dataset.amt):'');const r=await api('POST','/api/task',{donor_id:d.id,due_date:x.value,kind:'charge',note});d.tasks=d.tasks||[];d.tasks.push({id:r.id,donor_id:d.id,due_date:x.value,kind:'charge',note,done:0});toast('תזכורת לחיוב נקבעה ✓');});
}
function autoGrow(t){t.style.height='auto';t.style.height=(t.scrollHeight+6)+'px';}
// העתקה ללוח — עם נפילה חלופה לאפליקציה מותקנת (execCommand)
async function copyToClip(txt,okMsg){
  txt=(txt||'').trim();if(!txt){toast('אין מה להעתיק');return;}
  try{await navigator.clipboard.writeText(txt);toast(okMsg||'הועתק ✓');return;}catch(e){}
  try{const ta=document.createElement('textarea');ta.value=txt;ta.style.position='fixed';ta.style.opacity='0';document.body.appendChild(ta);ta.focus();ta.select();document.execCommand('copy');ta.remove();toast(okMsg||'הועתק ✓');}
  catch(e){prompt('העתק ידנית:',txt);}
}
function renderPrayers(d){
  const el=document.getElementById('prayers');
  const prs=(d.prayers||[]);
  const allBtn=prs.length>1?`<button class="btn sm ghost" id="prcopyall" style="width:100%;margin-bottom:6px">📋 העתק את כל השמות</button>`:'';
  el.innerHTML=allBtn+(prs.map(p=>`<div class="prow"><textarea class="prtx" data-id="${p.id}">${esc(p.text)}</textarea><button class="prcopy" data-id="${p.id}" title="העתק שם">📋</button><button class="del" data-del="${p.id}">🗑</button></div>`).join('')||'<div class="hintxt">אין שמות עדיין. הוסף למטה.</div>');
  el.querySelectorAll('.prtx').forEach(t=>{autoGrow(t);t.addEventListener('input',()=>autoGrow(t));t.onblur=async()=>{const p=d.prayers.find(x=>x.id==t.dataset.id);if(!p||p.text===t.value)return;p.text=t.value;await api('PUT','/api/prayer/'+p.id,{text:t.value});toast('נשמר ✓');};});
  el.querySelectorAll('.prcopy').forEach(b=>b.onclick=()=>{const t=el.querySelector('.prtx[data-id="'+b.dataset.id+'"]');copyToClip(t?t.value:'','השם הועתק ✓');});
  const ca=document.getElementById('prcopyall');if(ca)ca.onclick=()=>{const txt=[...el.querySelectorAll('.prtx')].map(t=>t.value.trim()).filter(Boolean).join('\n');copyToClip(txt,'כל השמות הועתקו ✓');};
  el.querySelectorAll('.del').forEach(b=>b.onclick=async()=>{await api('DELETE','/api/prayer/'+b.dataset.del);d.prayers=d.prayers.filter(x=>x.id!=b.dataset.del);renderPrayers(d);toast('נמחק');});
}
const DAYKIND={parnes:'🌙 פרנס',coffee:'☕ קפה',breakfast:'🍳 בוקר'};
function parnesCertUrl(d,p){
  const dtext=(p.day&&p.month)?(heDay(+p.day)+" "+p.month):(p.date_text||'');
  const yr=p.hyear||HEBYEAR;const date=dtext+(yr?(' '+yr):'');
  const names=(p.dedication&&p.dedication.trim())||(d&&d.prayers&&d.prayers[0]&&d.prayers[0].text)||'';
  return location.origin+'/parnes-cert?'+new URLSearchParams({kind:p.kind||'parnes',date,names}).toString();
}
function openParnesCert(d,p){if(!p)return;window.open(parnesCertUrl(d,p),'_blank');}
// אותה תעודה — כתמונה (PNG) לשליחה ישירה, בלי PDF
function parnesCertPng(d,p){
  const dtext=(p.day&&p.month)?(heDay(+p.day)+" "+p.month):(p.date_text||'');
  const yr=p.hyear||HEBYEAR;const date=dtext+(yr?(' '+yr):'');
  const names=(p.dedication&&p.dedication.trim())||(d&&d.prayers&&d.prayers[0]&&d.prayers[0].text)||'';
  return {png:'/cert.png?'+new URLSearchParams({kind:p.kind||'parnes',date,names}).toString(),
          jpg:'/cert.jpg?'+new URLSearchParams({kind:p.kind||'parnes',date,names}).toString()};
}
// שיתוף תמונה מכתובת — קובץ אמיתי בטלפון, העתקה ללוח במחשב
async function sharePngUrl(url,fname,msg){
  let blob=null;
  try{ blob=await (await fetch(url)).blob(); }catch(e){ window.open(url,'_blank'); return 'opened'; }
  if(!blob||blob.size<5000||(blob.type||'').indexOf('image')<0){ toast('התמונה לא נוצרה כראוי'); return 'bad'; }
  try{ const file=new File([blob],fname||'certificate.jpg',{type:blob.type||'image/jpeg'});
    if(navigator.canShare&&navigator.canShare({files:[file]})){ await navigator.share({files:[file],text:msg||''}); return 'shared'; }
  }catch(e){ if(e&&e.name==='AbortError') return 'cancel'; }
  try{ if(window.ClipboardItem&&navigator.clipboard&&navigator.clipboard.write){
    const png=await imgToPngBlob(blob);   // הלוח מקבל רק PNG — JPEG נדחה
    await navigator.clipboard.write([new ClipboardItem({'image/png':png})]); return 'copied'; } }catch(e){}
  const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=fname||'certificate.png';a.click();
  setTimeout(()=>URL.revokeObjectURL(a.href),4000);
  return 'downloaded';
}
// שיתוף תמונה כקובץ אמיתי (מצרף בוואטסאפ/מייל דרך תפריט המכשיר), עם נפילה לפתיחת התמונה
// המרת תמונה ל-PNG — לוח ההעתקה של הדפדפן תומך רק בפורמט הזה
async function imgToPngBlob(blob){
  if((blob.type||'')==='image/png')return blob;
  const bmp=await createImageBitmap(blob);
  const c=document.createElement('canvas');c.width=bmp.width;c.height=bmp.height;
  c.getContext('2d').drawImage(bmp,0,0);
  return await new Promise(res=>c.toBlob(res,'image/png'));
}
// העתקת תמונת ההקדשה ללוח — כדי להדביק אותה ישירות בוואטסאפ ווב / במייל במחשב
async function copyImageToClip(img){
  if(!img||(img.mime||'').indexOf('image')<0)return false;
  if(!(window.ClipboardItem&&navigator.clipboard&&navigator.clipboard.write))return false;
  const getPng=async()=>await imgToPngBlob(await (await fetch('/api/file/'+img.id)).blob());
  // צורת ה-Promise נדרשת בספארי/אייפד כדי לשמור על אישור המשתמש
  try{await navigator.clipboard.write([new ClipboardItem({'image/png':getPng()})]);return true;}catch(e){}
  try{await navigator.clipboard.write([new ClipboardItem({'image/png':await getPng()})]);return true;}catch(e){return false;}
}
// שליחת התמונה עצמה: בטלפון — שיתוף קובץ אמיתי; במחשב — העתקה ללוח להדבקה בוואטסאפ ווב
async function sharePhotoFile(img,msg){
  if(!img){toast('אין תמונה מצורפת');return 'none';}
  try{const r=await fetch('/api/file/'+img.id);const blob=await r.blob();const file=new File([blob],img.name||'hakdasha.jpg',{type:blob.type||'image/jpeg'});
    if(navigator.canShare&&navigator.canShare({files:[file]})){await navigator.share({files:[file],text:msg||''});return 'shared';}}
  catch(e){if(e&&e.name==='AbortError')return 'cancel';}
  if(await copyImageToClip(img))return 'copied';
  window.open(location.origin+'/api/file/'+img.id,'_blank');   // גיבוי אחרון
  return 'opened';
}
// תפריט שליחת תעודת פרנס לתורם — וואטסאפ / מייל / שיתוף מכשיר / התמונה
function shareParnesMenu(t,d){
  d=d||{};
  const certUrl=parnesCertUrl(d,t);
  const img=(t.files||[]).find(f=>(f.mime||'').indexOf('image')>=0)||(t.files||[])[0];
  const donor=((d.last||'')+' '+(d.first||'')).trim()||t.donor||'';
  const dtext=(t.day&&t.month)?(heDay(+t.day)+' '+t.month):(t.date_text||'');
  const cap=`תעודת פרנס — כולל חצות 🕯️  עבור ${donor}${dtext?(' · '+dtext):''}`;   // כיתוב קצר לתמונה — בלי קישור למערכת
  const msgLink=`${cap}\n\nלצפייה/הדפסה: ${certUrl}`;                                   // רק לאפשרות "קישור טקסט"
  const ph=(splitPhones(d.phone)[0]||'').replace(/[^0-9]/g,'');
  const o=document.createElement('div');o.className='confirmov';
  o.innerHTML=`<div class="confirmbox"><div class="cm" style="font-weight:800;margin-bottom:8px">📤 שליחת תעודה${donor?(' ל'+esc(donor)):''}</div>
    <div style="display:flex;flex-direction:column;gap:8px">
      ${img?`<button class="btn" id="shsend" style="background:var(--yes);border-color:var(--yes)">📧 שלח עכשיו לתורם במייל (התמונה מצורפת)</button>
      ${ph?`<button class="btn" id="shwadir" style="background:#25D366;border-color:#25D366">📲 פתח וואטסאפ ישירות ל${esc(donor||'תורם')}</button>`:''}
      <button class="btn ghost" id="shph">📤 שתף את התמונה (בחירת אפליקציה)</button>
      <button class="btn ghost" id="shdl">📥 הורד / פתח את התמונה</button>`:'<div class="hintxt" style="color:var(--no)">אין תמונת הקדשה מצורפת — העלה תמונה קודם.</div>'}
      <div class="hintxt" style="margin:2px 0">— התעודה המעוצבת —</div>
      <button class="btn" id="shcimg" style="background:var(--accent);border-color:var(--accent)">🖼️ שלח את התעודה כתמונה</button>
      <button class="btn ghost" id="shccopy">📋 העתק את התעודה כתמונה</button>
      <button class="btn ghost" id="shcdl">📥 הורד את התעודה כתמונה</button>
      <button class="btn ghost" id="shwa">📲 שלח קישור לתעודה בוואטסאפ</button>
      <button class="btn ghost" id="shml">📧 מייל דרך תוכנת הדואר</button>
      <button class="btn ghost" id="shcert">👁️ פתח / הדפס תעודה</button></div>
    <div class="cbtns" style="margin-top:10px"><button class="btn ghost cno">סגור</button></div></div>`;
  document.body.appendChild(o);const done=()=>o.remove();
  o.querySelector('.cno').onclick=done;o.onclick=e=>{if(e.target===o)done();};
  const certImg=parnesCertPng(d,t), pngName='תעודת פרנס — '+(donor||'')+'.jpg';
  // מכינים את התמונה כבר עכשיו ברקע — כרום מסרב להעתיק ללוח תמונה שעדיין נטענת
  let certBlob=null;
  const prepPng=async()=>{
    if(certBlob)return certBlob;
    try{const b=await (await fetch(certImg.png)).blob();
      if(b&&b.size>5000&&(b.type||'').indexOf('image')>=0)certBlob=b;}catch(e){}
    return certBlob;
  };
  prepPng();
  const ci=o.querySelector('#shcimg');
  if(ci)ci.onclick=async()=>{ci.disabled=true;ci.textContent='מכין את התמונה…';
    const r=await sharePngUrl(certImg.jpg,pngName,cap);
    ci.disabled=false;ci.textContent='🖼️ שלח את התעודה כתמונה';
    if(r==='shared'){toast('נשלח ✓');done();}
    else if(r==='copied'){toast('התמונה הועתקה — הדבק בוואטסאפ ווב');pasteStep();}
    else if(r==='downloaded'){toast('התמונה ירדה למכשיר ✓');}};
  const cc=o.querySelector('#shccopy');
  if(cc)cc.onclick=async()=>{
    if(!(window.ClipboardItem&&navigator.clipboard&&navigator.clipboard.write)){toast('הדפדפן לא תומך בהעתקת תמונה');return;}
    cc.disabled=true;cc.textContent='מעתיק…';
    let ok=false;
    // 1) התמונה כבר בזיכרון מההכנה מראש — זו הדרך שעובדת בכרום
    if(certBlob){try{await navigator.clipboard.write([new ClipboardItem({'image/png':certBlob})]);ok=true;}catch(e){}}
    // 2) ספארי/אייפד — צורת ה-Promise שומרת על אישור המשתמש
    if(!ok){try{await navigator.clipboard.write([new ClipboardItem({'image/png':prepPng().then(x=>x||Promise.reject())})]);ok=true;}catch(e){}}
    // 3) להביא ואז לכתוב
    if(!ok){const b=await prepPng();if(b){try{await navigator.clipboard.write([new ClipboardItem({'image/png':b})]);ok=true;}catch(e){}}}
    cc.disabled=false;cc.textContent='📋 העתק את התעודה כתמונה';
    if(ok){toast('הועתק ✓');pasteStep();}else{prepPng();toast('ההעתקה נכשלה — לחץ שוב, התמונה כבר מוכנה');}};
  const cd=o.querySelector('#shcdl');
  if(cd)cd.onclick=async()=>{const a=document.createElement('a');a.href=certImg.jpg;a.download=pngName;a.click();toast('מוריד…');};
  // שלב 2 במחשב: התמונה כבר בלוח — נותר לפתוח וואטסאפ ווב ולהדביק
  const pasteStep=()=>{
    const wurl=ph?('https://web.whatsapp.com/send?phone='+ph):'https://web.whatsapp.com';
    o.querySelector('.confirmbox').innerHTML=`<div class="cm" style="font-weight:800;margin-bottom:8px">✅ התמונה הועתקה</div>
      <div class="hintxt" style="margin-bottom:10px;line-height:1.6">עכשיו פתח את וואטסאפ ווב והדבק אותה בשיחה עם <b>Ctrl+V</b> (במק: <b>⌘+V</b>) ואז Enter.<br>אפשר גם להדביק ככה במייל.</div>
      <div style="display:flex;flex-direction:column;gap:8px">
        <button class="btn" id="shwaweb" style="background:#25D366;border-color:#25D366">📲 פתח וואטסאפ ווב${donor?(' — '+esc(donor)):''}</button>
        <button class="btn ghost" id="shgml">📧 פתח גימייל לכתיבת מייל</button></div>
      <div class="cbtns" style="margin-top:10px"><button class="btn ghost cno2">סגור</button></div>`;
    o.querySelector('.cno2').onclick=done;
    o.querySelector('#shwaweb').onclick=()=>{window.open(wurl,'_blank');done();};
    o.querySelector('#shgml').onclick=()=>{window.open('https://mail.google.com/mail/?view=cm&to='+encodeURIComponent((d.email||'').trim())+'&su='+encodeURIComponent('תעודת פרנס — כולל חצות')+'&body='+encodeURIComponent(cap),'_blank');done();};
  };
  // שליחה ישירה מהשרת — התמונה מגיעה לתורם מצורפת למייל, בלי העתק/הדבק
  const shs=o.querySelector('#shsend');if(shs)shs.onclick=async()=>{
    const to=(d.email||'').trim();
    if(!to){toast('אין כתובת מייל בכרטיס התורם');return;}
    shs.disabled=true;shs.textContent='שולח…';
    const r=await api('POST','/api/parnes/'+t.id+'/sendmail',{to});
    if(r&&r.ok){toast('נשלח ל'+to+' ✓');done();return;}
    const why={not_configured:'המייל לא מוגדר בשרת',no_files:'אין תמונה מצורפת',no_recipient:'אין כתובת מייל',login_failed:'התחברות לג׳ימייל נכשלה'}[r&&r.error]||((r&&(r.detail||r.error))||'שגיאה');
    toast('לא נשלח: '+why);shs.disabled=false;shs.textContent='📧 שלח עכשיו לתורם במייל (התמונה מצורפת)';
  };
  // וואטסאפ ישיר לשיחה של התורם — בלי חלון בחירת אפליקציה. התמונה מועתקת ללוח להדבקה בשיחה.
  const shwd=o.querySelector('#shwadir');if(shwd)shwd.onclick=async()=>{
    shwd.disabled=true;shwd.textContent='מכין את התמונה…';
    const ok=await copyImageToClip(img);
    toast(ok?'התמונה בלוח — בשיחה: לחיצה ארוכה ← הדבק ← שלח 📋':'נפתחת השיחה — צרף את התמונה מהגלריה');
    location.href='https://wa.me/'+ph;
    setTimeout(done,600);
  };
  const shph=o.querySelector('#shph');if(shph)shph.onclick=async()=>{     // שולח את קובץ התמונה עצמו
    const res=await sharePhotoFile(img,cap);
    if(res==='copied'){pasteStep();return;}
    if(res==='opened')toast('שמור את התמונה ושלח אותה בוואטסאפ 📷');
    done();
  };
  const shdl=o.querySelector('#shdl');if(shdl)shdl.onclick=()=>{window.open(location.origin+'/api/file/'+img.id,'_blank');done();};
  o.querySelector('#shwa').onclick=()=>{window.open('https://wa.me/'+ph+'?text='+encodeURIComponent(msgLink),'_blank');done();};
  o.querySelector('#shml').onclick=()=>{window.location.href='mailto:'+encodeURIComponent((d.email||'').trim())+'?subject='+encodeURIComponent('תעודת פרנס — כולל חצות')+'&body='+encodeURIComponent(msgLink);done();};
  o.querySelector('#shcert').onclick=()=>{openParnesCert(d,t);done();};
}
function renderParnesEdit(d){
  const el=document.getElementById('parnes');if(!el)return;
  const tdy=todayStr(), cur=curSym(d);
  const ptot=(d.parnes||[]).reduce((s,p)=>s+amtNum(p.amount),0);
  const head=(d.parnes&&d.parnes.length)?`<div class="dncount">${d.parnes.length} ימי פרנס · סה"כ ${cur}${ptot}</div>`:'';
  el.innerHTML=head+((d.parnes||[]).map(p=>{const passed=p.night_date&&p.night_date<tdy;return `<div class="plwrap"><div class="pledge ${p.status==='suggested'?'pending':'given'}"><div class="pi"><b>${p.status==='suggested'?'🔵 הצעה':'🟢'} ${DAYKIND[p.kind]||'🌙'} · ${esc(p.date_text)}${p.hyear?(' '+esc(p.hyear)):''}</b> ${p.amount?('· <b style="color:var(--yes)">'+cur+esc(p.amount)+'</b>'):''}${passed&&+p.paid?' <span class="fbchip on">🌙 הסתיים</span>':''}</div><button class="del" data-del="${p.id}">🗑</button></div>
    <div class="two" style="margin:6px 0 0"><label class="fld"><span>סכום</span><input class="pyamt" data-id="${p.id}" value="${esc(p.amount||'')}" inputmode="decimal" placeholder="0"></label>
      <label class="fld"><span>סוג</span><select class="pykind" data-id="${p.id}"><option value="parnes" ${p.kind==='parnes'?'selected':''}>🌙 פרנס לילה</option><option value="coffee" ${p.kind==='coffee'?'selected':''}>☕ פרנס קפה</option><option value="breakfast" ${p.kind==='breakfast'?'selected':''}>🍳 ארוחת בוקר</option></select></label></div>
    <div class="two"><label class="fld"><span>חודש</span><select class="pymon" data-id="${p.id}">${HMORD.map(m=>`<option ${m===p.month?'selected':''}>${m}</option>`).join('')}</select></label>
      <label class="fld"><span>יום</span><select class="pyday" data-id="${p.id}">${[...Array(30)].map((_,i)=>`<option value="${i+1}" ${(i+1)==+p.day?'selected':''}>${heDay(i+1)}</option>`).join('')}</select></label>
      <label class="fld"><span>שנה</span><select class="pyyr" data-id="${p.id}">${heYearOpts(p.hyear)}</select></label></div>
    <label class="fld"><span>💳 דרך מה ייגבה</span><select class="pymethod" data-id="${p.id}">${channelOpts(p.method)}</select></label>
    <label class="fld" style="margin:4px 0"><span>🕯️ שמות ובקשות לתעודת הפרנס</span><textarea class="pyded" data-id="${p.id}" rows="2" placeholder="השמות שיוזכרו והבקשות (למשל: יעקב בן שרה לרפואה שלמה)">${esc(p.dedication||'')}</textarea></label>
    <button class="btn sm pydsave" data-id="${p.id}" style="margin:-2px 0 4px">💾 שמור שמות</button>
    <div class="txctl"><button class="dnpaid ${+p.paid?'yes':'no'} pypaid" data-id="${p.id}">${+p.paid?'נגבה ✓':'🔴 טרם נגבה'}</button><button class="btn sm ghost pycert" data-id="${p.id}">🖨️ תעודת פרנס</button><button class="btn sm ghost pypic" data-id="${p.id}">${p.photo==='sent'?'📷 תמונת הקדשה נשלחה ✓':'📷 סמן: תמונת הקדשה נשלחה'}</button>${p.photo==='sent'?'<span class="fbchip on">✓ נשלחה תמונת הקדשה</span>':''}</div><label class="remset">🔔 תזכורת: <input type="date" class="pyrem" data-txt="${esc(p.date_text)}"></label></div>`;}).join('')||'<div class="hintxt">אין עדיין.</div>');
  el.querySelectorAll('.pyded').forEach(t=>{autoGrow(t);t.addEventListener('input',()=>autoGrow(t));t.onblur=async()=>{const p=d.parnes.find(x=>x.id==t.dataset.id);if(!p||(p.dedication||'')===t.value)return;p.dedication=t.value;await api('PUT','/api/parnes/'+p.id,{dedication:t.value});toast('נשמר ✓');};});
  el.querySelectorAll('.pydsave').forEach(b=>b.onclick=async()=>{const p=d.parnes.find(x=>x.id==b.dataset.id);const t=el.querySelector('.pyded[data-id="'+b.dataset.id+'"]');if(!p||!t)return;p.dedication=t.value;await api('PUT','/api/parnes/'+p.id,{dedication:t.value});toast('נשמר ✓');});
  el.querySelectorAll('.pyamt').forEach(inp=>inp.onchange=async()=>{const p=d.parnes.find(x=>x.id==inp.dataset.id);if(!p)return;p.amount=inp.value.trim();await api('PUT','/api/parnes/'+p.id,{amount:p.amount});renderParnesEdit(d);toast('סכום עודכן ✓');});
  el.querySelectorAll('.pykind').forEach(sel=>sel.onchange=async()=>{const p=d.parnes.find(x=>x.id==sel.dataset.id);if(!p)return;p.kind=sel.value;await api('PUT','/api/parnes/'+p.id,{kind:p.kind});renderParnesEdit(d);toast('סוג עודכן ✓');});
  el.querySelectorAll('.pymethod').forEach(sel=>sel.onchange=async()=>{const p=d.parnes.find(x=>x.id==sel.dataset.id);if(!p)return;p.method=sel.value;await api('PUT','/api/parnes/'+p.id,{method:p.method});toast('אמצעי גבייה עודכן ✓');});
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
  if(d.tier==='קוויטל_שבועי'||d.tier==='קוויטל_כללי')return 'weekly';
  if(d.category==='קבוע'&&amtNum(d.amount)>0&&amtNum(d.amount)<101)return 'weekly';
  return null;
}
// כל תורם שאין לו שם לתפילה ולא סומן "לא צריך" — כדי להתריע על כולם
function kvMissingList(){return DB.filter(d=>!(d.prayers&&d.prayers.length)&&!(+d.kv_skip));}
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
    const miss=kvMissingList().length, unl=(UNLINKED||[]).length;
    view.innerHTML=`<div class="cnt">בחר סוג קוויטל <small style="color:var(--muted)">· או חפש שם למעלה כדי לדלג ישר לתוצאות</small></div>
      ${miss?`<button class="btn kvmissbtn" id="kvMissBtn">🔴 חסרים שמות קוויטל — ${miss} לטיפול</button>`:''}
      ${unl?`<button class="btn kvunlbtn" id="kvUnlBtn">🔗 קוויטל לא־משויכים — ${unl} להחלטה</button>`:''}
      <button class="btn kvintakebtn" id="kvIntakeBtn">📨 בקשות תפילה מהאתר (מהמייל)…</button>
      <button class="btn ghost" id="kvDedupBtn" style="width:100%;margin-top:6px">🧹 נקה שמות כפולים בקוויטל של כולם</button>
      <div class="kvmenu">${KVTYPES.map(([k,t,s])=>`<button class="kvbtn" data-k="${k}"><b>${t}</b><small>${s}</small></button>`).join('')}</div>`;
    view.querySelectorAll('.kvbtn').forEach(b=>b.onclick=()=>{kvListQ='';kvSub=b.dataset.k;render();});
    const mb=document.getElementById('kvMissBtn');if(mb)mb.onclick=()=>{kvSub='missing';render();};
    const ub=document.getElementById('kvUnlBtn');if(ub)ub.onclick=()=>{kvSub='unlinked';render();};
    const ib=document.getElementById('kvIntakeBtn');if(ib)ib.onclick=()=>{kvSub='intake';render();};
    const db2=document.getElementById('kvDedupBtn');
    if(db2)db2.onclick=async()=>{db2.disabled=true;const t0=db2.textContent;db2.textContent='בודק את כל הקוויטלים…';
      const r=await api('POST','/api/kvittel/dedup',{});
      db2.disabled=false;db2.textContent=t0;
      if(!r||!r.ok){toast('הניקוי נכשל');return;}
      toast(r.removed||r.merged?('נוקו כפילויות אצל '+r.donors+' תורמים ✓'):'לא נמצאו כפילויות 🎉');
      if(r.removed||r.merged){await load();render();}};
    return;
  }
  if(kvSub==='unlinked') return renderKvUnlinked();
  if(kvSub==='missing') return renderKvMissing();
  if(kvSub==='occ') return renderKvOcc();
  if(kvSub==='intake') return renderKvIntake();
  renderKvList(kvSub);
}
function renderKvUnlinked(){
  const list=(UNLINKED||[]).filter(p=>matchQ((p.name||'')+' '+(p.text||'')));
  view.innerHTML=`<div class="kbar"><button class="back" id="kvback">→ סוגי קוויטל</button><b>🔗 קוויטל לא־משויכים</b><span class="cnt2">(${list.length})</span></div>
    <div class="hintxt" style="margin:0 2px 8px">אלה שמות קוויטל מאנשי הקשר שלא נמצא להם כרטיס תורם תואם. לכל אחד: צור כרטיס חדש, שייך לתורם קיים, או מחק.</div>
    ${list.map(p=>`<div class="kblock unlrow" data-id="${p.id}">
      <div class="who"><b>${esc(p.name||'ללא שם')}</b> <span class="kvtag">${kvTypeLabel(prayerKvType(p.tier,null))}</span></div>
      <div class="names" style="white-space:pre-line;margin:4px 0">${esc(p.text||'')}</div>
      <div class="unlact"><button class="btn sm unlnew" data-id="${p.id}">➕ צור כרטיס</button><button class="btn sm ghost unllink" data-id="${p.id}">🔗 שייך לתורם קיים</button><button class="del unldel" data-id="${p.id}">🗑</button></div>
      <div class="unlsearch hidden" data-id="${p.id}"><input class="unlq" placeholder="🔍 חפש תורם קיים…" autocomplete="off"><div class="dpres unlres"></div></div>
    </div>`).join('')||'<div class="empty">🎉 אין לא־משויכים</div>'}`;
  document.getElementById('kvback').onclick=()=>{kvSub=null;render();};
  view.querySelectorAll('.unldel').forEach(b=>b.onclick=async()=>{if(!await uiConfirm('למחוק את השם הזה מהקוויטל?'))return;await api('DELETE','/api/prayer/'+b.dataset.id);UNLINKED=UNLINKED.filter(x=>x.id!=b.dataset.id);renderKvUnlinked();toast('נמחק');});
  view.querySelectorAll('.unlnew').forEach(b=>b.onclick=async()=>{
    const p=UNLINKED.find(x=>x.id==b.dataset.id);if(!p)return;
    const parts=(p.name||'').trim().split(/\s+/);const last=parts[0]||p.name||'—',first=parts.slice(1).join(' ');
    if(!await uiConfirm('ליצור כרטיס תורם חדש בשם "'+esc((last+' '+first).trim())+'" ולשייך אליו את השם?'))return;
    const r=await api('POST','/api/donor',{last:last,first:first,tier:p.tier||'קוויטל_שבועי'});
    await api('PUT','/api/prayer/'+p.id,{donor_id:r.id});
    toast('נוצר כרטיס ושויך ✓');await load();kvSub='unlinked';render();});
  view.querySelectorAll('.unllink').forEach(b=>b.onclick=()=>{const s=view.querySelector('.unlsearch[data-id="'+b.dataset.id+'"]');if(s)s.classList.toggle('hidden');});
  view.querySelectorAll('.unlsearch').forEach(box=>{const pid=box.dataset.id,inp=box.querySelector('.unlq'),res=box.querySelector('.unlres');
    inp.oninput=()=>{const s=norm(inp.value);if(!s){res.innerHTML='';return;}
      const m=DB.filter(x=>norm(x.last+' '+x.first+' '+x.english+' '+x.phone).includes(s)).slice(0,8);
      res.innerHTML=m.map(x=>`<div class="dpr" data-did="${x.id}">${esc(x.last)} ${esc(x.first)} <span style="color:var(--muted)">#${x.id}</span></div>`).join('')||'<div class="dpr" style="color:var(--muted)">אין תוצאות</div>';
      res.querySelectorAll('.dpr[data-did]').forEach(el=>el.onclick=async()=>{const dd=DB.find(x=>x.id==el.dataset.did);if(!dd)return;if(!await uiConfirm('לשייך את השם ל"'+(dd.last+' '+dd.first).trim()+'"?'))return;await api('PUT','/api/prayer/'+pid,{donor_id:dd.id});toast('שויך ✓');await load();kvSub='unlinked';render();});
    };});
}
function renderKvMissing(){
  let list=kvMissingList().filter(d=>matchQ(d.last+' '+d.first+' '+d.english));
  const prio=d=>kvMemberType(d)?0:1;  // מסומני קוויטל קודם, אחר כך השאר
  list.sort((a,b)=>prio(a)-prio(b)||(a.last||'').localeCompare(b.last||'','he'));
  view.innerHTML=`<div class="kbar"><button class="back" id="kvback">→ סוגי קוויטל</button><b>🔴 תורמים בלי שם לקוויטל</b><span class="cnt2">(${list.length})</span></div>
    <div class="hintxt" style="margin:0 2px 8px">כל תורם שאין לו עדיין שם לתפילה. הקלד שם — או לחץ ✓ אם הוא לא ביקש קוויטל (יוסר מהרשימה). מסומני הקוויטל למעלה.</div>
    ${list.map(d=>{const yr=donorTotals(d).year,cs=curSym(d);return `<div class="kblock kvmiss" data-id="${d.id}"><div class="who wholink" data-did="${d.id}">${esc((d.last+' '+d.first).trim())} <span class="kvtag">${kvMemberType(d)?kvTypeLabel(kvMemberType(d)):'אין קוויטל'}</span> <span class="kvyear ${yr>0?'':'zero'}">💵 השנה: ${cs}${yr}</span> <span class="opencard">↗ כרטיס</span></div>
      ${contactBtns(d)}
      <div class="kvmissrow"><div class="names" contenteditable="true" data-newdid="${d.id}" data-ph="שם לתפילה — הקלד כאן"></div><button class="kvskip" data-skip="${d.id}" title="לא ביקש קוויטל">✓ לא ביקש</button></div>
      <div style="text-align:left;margin-top:4px"><button class="tinydel kvdeldonor" data-del="${d.id}">🗑 מחק תורם לגמרי</button></div></div>`;}).join('')||'<div class="empty">🎉 אין חסרים — לכל המסומנים בקוויטל יש שם</div>'}`;
  document.getElementById('kvback').onclick=()=>{kvSub=null;render();};
  view.querySelectorAll('.who[data-did]').forEach(w=>w.onclick=()=>openDonor(DB.find(x=>x.id==w.dataset.did),'kvittel'));
  view.querySelectorAll('.kvskip').forEach(b=>b.onclick=async()=>{const d=DB.find(x=>x.id==b.dataset.skip);if(!d)return;d.kv_skip=1;await api('PUT','/api/donor/'+d.id,{kv_skip:1});toast('סומן — לא צריך קוויטל ✓');renderKvMissing();});
  view.querySelectorAll('.kvdeldonor').forEach(b=>b.onclick=async e=>{e.stopPropagation();const d=DB.find(x=>x.id==b.dataset.del);if(!d)return;if(!await uiConfirm('למחוק לצמיתות את "'+(d.last+' '+d.first).trim()+'"?\nכל הכרטיס יימחק — פעולה בלתי הפיכה.'))return;await api('DELETE','/api/donor/'+b.dataset.del);DB=DB.filter(x=>x.id!=b.dataset.del);toast('התורם נמחק ✓');renderKvMissing();});
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
  // כפתור העתקה ליד כל שם ברשימות הקוויטל
  view.querySelectorAll('.kblock').forEach(bl=>{
    const nm=bl.querySelector('.names');if(!nm||bl.querySelector('.kvcopy'))return;
    const b=document.createElement('button');b.className='kvcopy';b.textContent='📋';b.title='העתק שם';
    b.onclick=e=>{e.stopPropagation();copyToClip(nm.innerText,'השם הועתק ✓');};
    const who=bl.querySelector('.who');(who||bl).appendChild(b);
  });
}
// ===== בקשות תפילה מהאתר (מיילים) — עיון, בדיקה אם כבר בקוויטל, וצירוף =====
let INTAKE=null, INTAKE_CFG=false;
async function loadIntake(){const r=await api('GET','/api/intake');INTAKE=r.items||[];INTAKE_CFG=!!r.configured;}
async function renderKvIntake(){
  chips.innerHTML='';
  view.innerHTML='<div class="cnt">📨 טוען בקשות…</div>';
  if(INTAKE===null) await loadIntake();
  paintIntake();
}
function paintIntake(){
  const items=(INTAKE||[]).filter(x=>matchQ((x.names||'')+' '+(x.from_name||'')+' '+(x.from_email||'')+' '+(x.subject||'')));
  const nNew=(INTAKE||[]).filter(x=>x.status!=='handled').length;
  view.innerHTML=`<div class="kbar"><button class="back" id="kvback">→ סוגי קוויטל</button><b>📨 בקשות תפילה מהאתר</b><span class="cnt2">(${nNew} לטיפול)</span>
      <button class="btn sm" id="intSync">🔄 משוך מהמייל</button></div>
    ${INTAKE_CFG?'':`<div class="missbox">⚙️ חיבור המייל עדיין לא הוגדר בשרת. הגדר ב-Render את <b>GMAIL_USER</b> ו-<b>GMAIL_APP_PASSWORD</b> (וגם INTAKE_FROM לסינון לפי כתובת האתר). ראה הוראות.</div>`}
    <div class="hintxt" style="margin:2px 2px 8px">כל בקשה שהגיעה במייל מהאתר. ✅ = השמות כבר צורפו לקוויטל אצל התורם · 🔴 = עדיין לא. אפשר לערוך את השמות, לצרף לתורם, או לסמן שטופל.</div>
    <div id="intlist"></div>`;
  document.getElementById('kvback').onclick=()=>{kvSub=null;render();};
  document.getElementById('intSync').onclick=async()=>{
    const btn=document.getElementById('intSync');btn.disabled=true;btn.textContent='מושך…';
    const r=await api('POST','/api/intake/sync',{});
    if(!r.ok){toast(r.error==='not_configured'?'המייל לא מוגדר בשרת':'שגיאת משיכה: '+(r.detail||r.error||''));btn.disabled=false;btn.textContent='🔄 משוך מהמייל';return;}
    toast('נמשכו '+(r.new||0)+' בקשות'+(r.attached?' · '+r.attached+' צורפו אוטומטית לקוויטל לפי המייל':'')+' ✓');INTAKE=null;await loadIntake();paintIntake();
  };
  const list=document.getElementById('intlist');
  list.innerHTML=items.map(x=>{
    const mt=x.match;const badge=x.in_kvittel?'<span class="pstat yes">✅ כבר בקוויטל</span>':'<span class="pstat no">🔴 עדיין לא בקוויטל</span>';
    const handled=x.status==='handled';
    return `<div class="intcard ${handled?'given':''}" data-id="${x.id}">
      <div class="inthd"><b>${esc(x.from_name||x.from_email||'—')}</b> ${x.from_email?`<span class="ensm" dir="ltr">${esc(x.from_email)}</span>`:''} <span style="color:var(--muted);font-size:.8rem">${esc(x.received||'')}</span></div>
      ${mt?`<div class="intmatch">🔗 מותאם לכרטיס: <a class="wholink" data-did="${mt.id}"><b>${esc(mt.name)}</b> ↗</a> ${badge} ${mt.tier?('· '+esc(({'יששכר_זבולון':'יש"ז','קוויטל_101':'כל לילה','קוויטל_שבועי':'שבועי'})[mt.tier]||mt.tier)):''}</div>`:`<div class="intmatch">❓ לא נמצא כרטיס תואם — חפש וצרף למטה</div>`}
      <textarea class="intnames" rows="3" placeholder="שמות לתפילה">${esc(x.names||x.body||'')}</textarea>
      <div class="intact">
        <input class="intq" placeholder="🔍 חפש תורם לצרף אליו…" autocomplete="off" value="">
        <div class="intres dpres"></div>
        <div class="intbtns">
          ${mt?`<button class="btn sm intattach" data-id="${x.id}" data-did="${mt.id}">➕ צרף ל${esc(mt.name)}</button>`:`<button class="btn sm intnew" data-id="${x.id}">🆕 תורם חדש</button>`}
          <button class="btn sm intaddkv" data-id="${x.id}">🕯️ הוסף לקוויטל (בלי תורם)</button>
          <button class="btn sm ghost intsave" data-id="${x.id}">💾 שמור שמות</button>
          <button class="btn sm ${handled?'':'ghost'} inthandle" data-id="${x.id}">${handled?'↩︁ החזר לטיפול':'✓ סמן טופל'}</button>
          <button class="btn sm danger intdel" data-id="${x.id}">🗑️ מחק</button>
        </div>
      </div>
      <details class="intraw"><summary style="cursor:pointer;color:var(--muted);font-size:.8rem">הצג את המייל המלא</summary><pre style="white-space:pre-wrap;font-size:.82rem">${esc(x.body||'')}</pre></details>
    </div>`;
  }).join('')||'<div class="empty">אין בקשות. לחץ "משוך מהמייל".</div>';
  list.querySelectorAll('.wholink[data-did]').forEach(w=>w.onclick=()=>openDonor(DB.find(d=>d.id==w.dataset.did),'kvittel'));
  const getNames=id=>{const c=list.querySelector('.intcard[data-id="'+id+'"]');return c?c.querySelector('.intnames').value.trim():'';};
  list.querySelectorAll('.intsave').forEach(b=>b.onclick=async()=>{await api('PUT','/api/intake/'+b.dataset.id,{names:getNames(b.dataset.id)});const it=INTAKE.find(x=>x.id==b.dataset.id);if(it)it.names=getNames(b.dataset.id);toast('נשמר ✓');});
  list.querySelectorAll('.inthandle').forEach(b=>b.onclick=async()=>{const it=INTAKE.find(x=>x.id==b.dataset.id);const ns=it&&it.status==='handled'?'new':'handled';await api('PUT','/api/intake/'+b.dataset.id,{status:ns});if(it)it.status=ns;paintIntake();});
  list.querySelectorAll('.intdel').forEach(b=>b.onclick=async()=>{if(!confirm('למחוק את הבקשה הזו לגמרי?'))return;await api('DELETE','/api/intake/'+b.dataset.id);INTAKE=(INTAKE||[]).filter(x=>x.id!=b.dataset.id);paintIntake();toast('נמחק ✓');});
  list.querySelectorAll('.intnew').forEach(b=>b.onclick=async()=>{
    const it=INTAKE.find(x=>x.id==b.dataset.id);
    b.disabled=true;
    const r=await api('POST','/api/intake/'+b.dataset.id+'/newdonor',{names:getNames(b.dataset.id),email:it?it.from_email:'',last:it?(it.from_name||''):''});
    if(!r||!r.id){toast('שגיאה ביצירת תורם');b.disabled=false;return;}
    toast(r.from_recon?('נוצר כרטיס ל'+(r.name||'')+' — כולל כתובת מחיובי האשראי ✓'):('נוצר כרטיס ל'+(r.name||'תורם החדש')+' ✓'));
    // נשארים בדף הבקשות — הפריט יתעדכן ויראה קישור "פתח כרטיס ↗" (בלי לקפוץ ולאבד את המקום)
    await load();INTAKE=null;await loadIntake();paintIntake();
  });
  list.querySelectorAll('.intattach').forEach(b=>b.onclick=async()=>{
    const names=getNames(b.dataset.id);if(!names){toast('אין שמות לצירוף');return;}
    await api('POST','/api/intake/'+b.dataset.id+'/attach',{donor_id:+b.dataset.did,names:names});
    const dd=DB.find(x=>x.id==+b.dataset.did);if(dd){dd.prayers=dd.prayers||[];dd.prayers.push({text:names,tier:dd.tier||'קוויטל_שבועי'});}
    const it=INTAKE.find(x=>x.id==b.dataset.id);if(it){it.status='handled';it.in_kvittel=true;}
    toast('צורף לקוויטל ✓');paintIntake();
  });
  list.querySelectorAll('.intaddkv').forEach(b=>b.onclick=async()=>{
    const names=getNames(b.dataset.id);if(!names){toast('אין שמות להוספה');return;}
    await api('POST','/api/intake/'+b.dataset.id+'/attach',{names:names});   // בלי donor_id → שם לא־משויך
    const it=INTAKE.find(x=>x.id==b.dataset.id);if(it){it.status='handled';it.in_kvittel=true;}
    await load();   // רענן כדי שהשם הלא־משויך ייכנס לרשימת הקוויטל
    toast('נוסף לקוויטל (לא־משויך) ✓');kvSub='intake';INTAKE=null;await loadIntake();paintIntake();
  });
  // חיפוש תורם לצירוף ידני
  list.querySelectorAll('.intcard').forEach(card=>{
    const id=card.dataset.id,inp=card.querySelector('.intq'),res=card.querySelector('.intres');
    inp.oninput=()=>{const s=norm(inp.value);if(!s){res.innerHTML='';return;}
      const m=DB.filter(x=>norm(x.last+' '+x.first+' '+x.english+' '+x.phone).includes(s)).slice(0,6);
      res.innerHTML=m.map(x=>`<div class="dpr" data-did="${x.id}">${esc(x.last)} ${esc(x.first)} <span style="color:var(--muted)">#${x.id}</span></div>`).join('')||'<div class="dpr" style="color:var(--muted)">אין תוצאות</div>';
      res.querySelectorAll('.dpr[data-did]').forEach(el=>el.onclick=async()=>{
        const names=getNames(id);if(!names){toast('אין שמות לצירוף');return;}
        await api('POST','/api/intake/'+id+'/attach',{donor_id:+el.dataset.did,names:names});
        const dd=DB.find(x=>x.id==+el.dataset.did);if(dd){dd.prayers=dd.prayers||[];dd.prayers.push({text:names,tier:dd.tier||'קוויטל_שבועי'});}
        const it=INTAKE.find(x=>x.id==id);if(it){it.status='handled';it.in_kvittel=true;it.match={id:+el.dataset.did,name:(dd.last+' '+dd.first).trim(),tier:dd.tier||''};}
        toast('צורף לקוויטל ✓');paintIntake();
      });
    };
  });
}
function prayerKvType(pt,d){
  d=d||{};
  if(pt==='יששכר_זבולון'||(!pt&&d.tier==='יששכר_זבולון'))return 'iz';
  if(pt==='קוויטל_101'||(!pt&&d.tier==='קוויטל_101'))return '101';
  if(pt==='שבועי'||pt==='קוויטל_שבועי'||pt==='קוויטל_כללי'||(!pt&&(d.tier==='קוויטל_שבועי'||d.tier==='קוויטל_כללי'))||(!pt&&d.category==='קבוע'&&amtNum(d.amount)>0&&amtNum(d.amount)<101))return 'weekly';
  if(d.category==='מזדמן'&&!d.tier)return 'occ';
  return 'other';
}
let kvListQ='';
function renderKvList(type){
  const title=KVTYPES.find(x=>x[0]===type)[1];
  view.innerHTML=`<div class="kbar"><button class="back" id="kvback">→ סוגי קוויטל</button><b>${title}</b><span class="cnt2" id="kvcnt"></span><button class="print noprint" onclick="window.print()">הדפס 🖨️</button></div>
    <input class="avsearch noprint" id="kvsearch" placeholder="🔍 חפש שם תורם או שם שמוזכר בקוויטל…" value="${esc(kvListQ)}" autocomplete="off">
    <div class="hintxt noprint" style="margin:0 2px 8px">לתיקון: לחץ על השם, ערוך, ולחץ מחוץ לו — נשמר גם בכרטיס.</div>
    <div id="kvlistwrap"></div>`;
  document.getElementById('kvback').onclick=()=>{kvListQ='';kvSub=null;render();};
  const si=document.getElementById('kvsearch');
  function paint(){
    let entries=[];
    DB.forEach(d=>{
      const prs=(d.prayers||[]);
      prs.forEach(p=>{const t=prayerKvType(p.tier,d);const inc=type==='klali'?(t!=='occ'):(t===type);if(inc)entries.push({id:p.id,text:p.text,donor:(d.last+' '+d.first).trim(),last:d.last,did:d.id});});
      if(!prs.length&&!(+d.kv_skip)){const t=kvMemberType(d);const inc=t&&(type==='klali'?true:(t===type));if(inc)entries.push({id:null,newdid:d.id,text:'',donor:(d.last+' '+d.first).trim(),last:d.last,did:d.id,needname:true});}
    });
    UNLINKED.forEach(p=>{const t=prayerKvType(p.tier,null);const inc=type==='klali'?(t!=='occ'):(t===type);if(inc)entries.push({id:p.id,text:p.text,donor:p.name||'—',last:(p.name||'').split(' ').slice(-1)[0],loose:true});});
    const nq=norm(kvListQ);
    if(nq)entries=entries.filter(e=>norm(e.donor+' '+e.text).includes(nq));
    entries.sort((a,b)=>(a.last||'').localeCompare(b.last||'','he'));
    // תורם אחד = משבצת אחת. כמה שמות שנוספו לו לאורך הזמן יושבים יחד תחת שמו,
    // כל אחד עדיין ניתן לעריכה בנפרד; בהדפסה הם נקראים כרשימה אחת רצופה
    const groups=[],gmap={};
    entries.forEach(e=>{const k=e.did?('d'+e.did):('l'+e.id);
      if(!gmap[k]){gmap[k]={key:k,donor:e.donor,last:e.last,did:e.did,loose:e.loose,items:[]};groups.push(gmap[k]);}
      gmap[k].items.push(e);});
    document.getElementById('kvcnt').textContent='('+groups.length+(groups.length!==entries.length?(' · '+entries.length+' רשומות'):'')+')';
    document.getElementById('kvlistwrap').innerHTML=groups.map(g=>{
      const empty=!g.items.some(e=>(e.text||'').trim());
      const needname=g.items.some(e=>e.needname);
      return `<div class="kblock${empty?' kvempty':''}${g.items.length>1?' kvmulti':''}"><div class="who${g.did?' wholink':''}"${g.did?` data-did="${g.did}"`:''}>${esc(g.donor)}${g.did?' <span class="opencard">↗ כרטיס</span>':''}${needname?' <span class="kvtag">אין שם — הקלד כאן</span>':''}${g.loose?' <span class="loose">· לא משויך</span>':''}</div>`
        + g.items.map(e=>`<div class="names" contenteditable="true" ${e.id?`data-id="${e.id}"`:`data-newdid="${e.newdid}"`}>${esc(e.text)}</div>`).join('')
        + `</div>`;}).join('')||'<div class="empty">אין תוצאות</div>';
    view.querySelectorAll('.who[data-did]').forEach(w=>w.onclick=()=>openDonor(DB.find(x=>x.id==w.dataset.did),'kvittel'));
    bindKvEdit();
  }
  si.oninput=()=>{kvListQ=si.value;paint();};
  paint();
}
function renderKvOcc(){
  const groups={},mdate={};
  const place=(d,hm,dt)=>{groups[hm]=groups[hm]||{};const pid=(d.prayers&&d.prayers[0])?d.prayers[0].id:null;groups[hm][d.id]={d,pid,text:(d.prayers&&d.prayers[0])?d.prayers[0].text:''};if(!mdate[hm]||(dt||'')>mdate[hm])mdate[hm]=dt||'';};
  DB.forEach(d=>{if(!(d.category==='מזדמן'&&!d.tier))return;
    if(d.kv_month){const lastdt=(d.donations||[]).reduce((a,x)=>((x.date||'')>a?(x.date||''):a),'');place(d,d.kv_month+(d.kv_year?(' '+d.kv_year):''),lastdt);return;}  // חודש/שנה שנקבעו ידנית
    const dons=(d.donations||[]);
    if(!dons.length){place(d,'ללא תאריך','');return;}
    dons.forEach(dn=>place(d,dn.hmonth||'ללא תאריך',dn.date||''));});
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
function savePy(){try{localStorage.setItem('kc_py',JSON.stringify({kind:pyKind,month:pyMonth,day:pyDay}));}catch(e){}}
const PKINDS=[['parnes','🌙 פרנס לילה'],['coffee','☕ חדר קפה'],['breakfast','🍳 ארוחת בוקר']];
function parnesTaken(kind){const taken={};DB.forEach(d=>(d.parnes||[]).forEach(p=>{if((p.kind||'parnes')!==kind)return;if(p.month&&p.day)taken[p.month+'|'+p.day]={...p,donor:(d.last+' '+d.first).trim(),dref:d};}));return taken;}
function kindToggle(){return `<div class="ktoggle">${PKINDS.map(([k,l])=>`<button class="ktog ${pyKind===k?'on':''}" data-k="${k}">${l}</button>`).join('')}</div>`;}
function bindKindToggle(){view.querySelectorAll('.ktog').forEach(b=>b.onclick=()=>{pyKind=b.dataset.k;pyDay=null;render();});}
function renderParnes(){
  chips.innerHTML='';
  savePy();   // שמירת המקום (חודש/יום) לשחזור אחרי רענון
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
    <div class="daygrid">${days.map(n=>{const t=taken[pyMonth+'|'+n];const cls=t?(t.status==='suggested'?'sugg':'full'):'free';const unpaid=t&&t.status!=='suggested'&&!+t.paid;return `<button class="daycell ${cls} ${unpaid?'unpaid':''} ${pyDay===n?'sel':''}" data-d="${n}"><span class="dn">${heDay(n)}</span>${t?`<span class="dnm">${esc(t.donor.split(' ')[0])}</span>${unpaid?'<span class="unpaiddot">🔴</span>':''}`:'<span class="dplus">+</span>'}</button>`;}).join('')}</div>
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
    const dpcur=t.currency||'$';                       // ברירת מחדל דולר; ניתן לבחור שקל
    const paid=+t.paid, amt=t.amount||'';
    panel.innerHTML=`<div class="sec"><h3>${sugg?'🔵 הצעה':(paid?'🟢 נגבה':'🔴 חוב — טרם נגבה')} · ${esc(dtext)}</h3>
      <div class="remitem ${sugg?'':(paid?'given':'')}"><div class="ri"><b>${esc(t.donor)}</b>${amt?(' · <b style="color:'+(paid?'var(--yes)':'var(--no)')+'">'+dpcur+esc(amt)+'</b>'):''}${t.method?(' · '+esc(chLabel(t.method))):''}</div></div>
      <div class="fld" style="margin:6px 0"><span>💰 סכום — מלא ידני לכל פרנס</span>
        <div class="two" style="gap:6px;margin-top:3px"><input id="dp_amt_edit" value="${esc(amt)}" inputmode="decimal" placeholder="כמה תרם">
          <select id="dp_cur_edit" style="max-width:110px"><option value="$" ${dpcur==='$'?'selected':''}>$ דולר</option><option value="₪" ${dpcur==='₪'?'selected':''}>₪ שקל</option></select></div>
        <button class="btn sm" id="dp_amt_save" style="margin-top:6px;width:100%">💾 שמור סכום</button></div>
      <label class="fld" style="margin:6px 0"><span>💳 איך נגבה (אמצעי תשלום)</span><select id="dp_method">${channelOpts(t.method)}</select></label>
      ${sugg?'':`<button class="dnpaid ${paid?'yes':'no'}" id="dppaid" style="margin:2px 0 8px;width:100%">${paid?'✓ נגבה — לחץ לביטול':'🔴 חוב — סמן שנגבה'}</button>`}
      ${sugg?'<div class="hintxt">הצעה — פנה אליו האם לעשות לו גם השנה. אם הסכים, אשר.</div>':''}
      <label class="fld" style="margin:6px 0"><span>🕯️ שמות ובקשות לתעודה</span><textarea id="dp_ded_edit" rows="2" placeholder="השמות שיוזכרו והבקשות">${esc(t.dedication||'')}</textarea></label>
      <button class="btn sm" id="dp_ded_save" style="margin-bottom:6px">💾 שמור שמות</button>
      <div class="movebox">🔀 העבר ליום אחר:
        <select id="dpmvmon">${HMORD.map(m=>`<option ${m===pyMonth?'selected':''}>${m}</option>`).join('')}</select>
        <select id="dpmvday">${[...Array(30)].map((_,i)=>`<option value="${i+1}" ${(i+1)===pyDay?'selected':''}>${heDay(i+1)}</option>`).join('')}</select>
        <button class="btn sm" id="dpmove">העבר</button></div>
      <div class="avfiles">${(t.files||[]).map(fileChip).join('')}<label class="filebtn">📷 העלה תמונת הקדשה<input type="file" accept="image/*,application/pdf" class="pyupload" hidden></label></div>
      <div class="addrow">${sugg?'<button class="btn sm" id="dpconfirm" style="background:var(--yes)">✅ אישר — עבור למאושר</button>':''}<button class="btn sm" id="dpsend" style="background:#25D366;border-color:#25D366">📤 שלח לתורם</button><button class="btn sm" id="dpopen">📋 כרטיס</button><button class="btn sm ghost" id="dpkv">🕯️ קוויטל</button><button class="btn sm" id="dpprint">🖨️ תעודה</button><button class="del" id="dpdel">מחק</button></div></div>`;
    const dpMethSel=document.getElementById('dp_method');
    const setPMeth=v=>{t.method=v;const p=(t.dref&&t.dref.parnes||[]).find(x=>x.id==t.id);if(p)p.method=v;};
    const dpAmtSave=async()=>{const damt=document.getElementById('dp_amt_edit'),dcur=document.getElementById('dp_cur_edit');t.amount=damt.value.trim();t.currency=dcur.value;const mv=dpMethSel?dpMethSel.value:t.method;setPMeth(mv);const p=(t.dref&&t.dref.parnes||[]).find(x=>x.id==t.id);if(p){p.amount=t.amount;p.currency=t.currency;}await api('PUT','/api/parnes/'+t.id,{amount:t.amount,currency:t.currency,method:mv});toast('נשמר ✓');render();};
    const dpAmtBtn=document.getElementById('dp_amt_save'); if(dpAmtBtn)dpAmtBtn.onclick=dpAmtSave;
    if(dpMethSel)dpMethSel.onchange=async()=>{setPMeth(dpMethSel.value);await api('PUT','/api/parnes/'+t.id,{method:dpMethSel.value});toast('אמצעי נשמר ✓');render();};
    const dppaid=document.getElementById('dppaid');
    if(dppaid)dppaid.onclick=async()=>{const np=+t.paid?0:1;t.paid=np;const mv=dpMethSel?dpMethSel.value:t.method;setPMeth(mv);const p=(t.dref&&t.dref.parnes||[]).find(x=>x.id==t.id);if(p)p.paid=np;await api('PUT','/api/parnes/'+t.id,{paid:np,method:mv});toast(np?'סומן כנגבה ✓':'סומן כחוב שטרם נגבה');render();};
    const dded=document.getElementById('dp_ded_edit');
    const ddedSave=async()=>{t.dedication=dded.value;const p=(t.dref&&t.dref.parnes||[]).find(x=>x.id==t.id);if(p)p.dedication=dded.value;await api('PUT','/api/parnes/'+t.id,{dedication:dded.value});toast('נשמר ✓');};
    dded.onblur=()=>{if((t.dedication||'')!==dded.value)ddedSave();};
    document.getElementById('dp_ded_save').onclick=ddedSave;
    document.getElementById('dpmove').onclick=async()=>{
      const nm=document.getElementById('dpmvmon').value, nd=+document.getElementById('dpmvday').value;
      if(nm===pyMonth && nd===pyDay){toast('בחר יום אחר');return;}
      if(nm===pyMonth && taken[nm+'|'+nd]){toast('היום הזה כבר תפוס — בחר אחר');return;}
      const ndtext=heDay(nd)+' '+nm, p=(t.dref&&t.dref.parnes||[]).find(x=>x.id==t.id);
      await api('PUT','/api/parnes/'+t.id,{day:nd,month:nm,date_text:ndtext,hyear:t.hyear||(p&&p.hyear)||''});
      if(p){p.day=nd;p.month=nm;p.date_text=ndtext;}
      pyMonth=nm;pyDay=nd;toast('הועבר ל־'+ndtext+' ✓');render();
    };
    if(sugg)document.getElementById('dpconfirm').onclick=async()=>{await api('PUT','/api/parnes/'+t.id,{status:'confirmed'});const p=(t.dref.parnes||[]).find(x=>x.id==t.id);if(p)p.status='confirmed';toast('אושר ✓ עבר למאושר');render();};
    panel.querySelector('.pyupload').onchange=e=>uploadFile('parnes',t.id,e.target,load);
    panel.querySelectorAll('.fdel').forEach(b=>b.onclick=async()=>{await api('DELETE','/api/file/'+b.dataset.fid);load();});
    document.getElementById('dpopen').onclick=()=>openDonor(t.dref);
    document.getElementById('dpkv').onclick=()=>openDonor(t.dref,'kvittel');
    document.getElementById('dpprint').onclick=()=>openParnesCert(t.dref,{...t,date_text:t.date_text||dtext});
    const dpsend=document.getElementById('dpsend'); if(dpsend)dpsend.onclick=()=>shareParnesMenu({...t,date_text:t.date_text||dtext},t.dref);
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
    document.getElementById('dp_save').onclick=async()=>{if(!chosen){toast('בחר תורם');return;}const ded=document.getElementById('dp_ded').value.trim(),amt=document.getElementById('dp_amt').value.trim(),status=document.getElementById('dp_status').value;const r=await api('POST','/api/parnes',{donor_id:chosen.id,day:pyDay,month:pyMonth,date_text:dtext,dedication:ded,amount:amt,kind:pyKind,status});chosen.parnes=chosen.parnes||[];chosen.parnes.push({id:r.id,donor_id:chosen.id,day:pyDay,month:pyMonth,date_text:dtext,dedication:ded,amount:amt,kind:pyKind,status});if(r.suggestions&&r.suggestions.length)chosen.parnes.push(...r.suggestions);toast('שובץ ✓'+(r.suggestions&&r.suggestions.length?' + '+r.suggestions.length+' הצעות לשנים הבאות':''));render();};
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
const PKLBL={parnes:'🌙 פרנס לילה',coffee:'☕ חדר קפה',breakfast:'🍳 ארוחת בוקר'};
/* ---------- כל החובות במקום אחד ---------- */
// אוסף לכל תורם את כל מה שנשאר חייב, מכל המקורות, עם פירוט "עבור מה"
function donorDebts(d){
  const out=[];
  (d.pledges||[]).forEach(p=>{ if(p.status==='נתן'||+p.monthly)return;   // חודשית = שוטפת, לא חוב
    out.push({what:(p.category||'התחייבות'),amt:amtNum(p.amount),kind:'pledge',id:p.id,when:''}); });
  (d.parnes||[]).forEach(p=>{ if(p.status==='suggested'||+p.paid)return;
    out.push({what:(PKLBL[p.kind]||'🌙 פרנס יום'),amt:amtNum(p.amount),kind:'parnes',id:p.id,
              when:[p.date_text,p.hyear].filter(Boolean).join(' ')}); });
  // תרומה שלא סומנה כשולמה = חוב, אבל רק אם יש לה תאריך מלא. שורות עם
  // חודש בלבד הן רישומי עבר מייבוא ולא התחייבות שממתינה לגבייה.
  (d.donations||[]).forEach(x=>{ if(+x.paid)return;
    if(String(x.date||'').length<=7)return;
    out.push({what:(x.category||'תרומה'),amt:amtNum(x.amount),kind:'donation',id:x.id,
              when:gregLabel(x.date)||x.date||''}); });
  (d.building||[]).forEach(x=>{ const owed=amtNum(x.amount)-amtNum(x.paid);
    if(owed>0.5)out.push({what:'🏛️ בניין'+(x.object?(' · '+x.object):''),amt:owed,kind:'building',id:x.id,when:''}); });
  // יששכר־זבולון — רק חוב שנקבע במפורש: עדכון ידני, או "שולם עד חודש".
  // חוב שמחושב מ"צפוי פחות שולם" לא נכנס לכאן — אברך שמוחזק אצל כמה
  // תורמים רשום אצל כל אחד בסכום המלא, וזה מנפח את ההתחייבות החודשית.
  try{
    const s=izSummary(d);
    let izd=0, note='';
    if(s.manual!=null){izd=s.manual;note='עודכן ידנית';}
    else if(s.thru&&s.thru.length){izd=s.thruDebt;
      note=s.thru.filter(t=>t.months).map(t=>t.av+' — שולם עד '+fmtMonth(t.thru)).join(' · ');}
    if(izd>0.5)out.push({what:'🤝 יששכר־זבולון',amt:izd,kind:'iz',id:0,when:note});
  }catch(e){}
  return out;
}
function renderDebts(){
  const rows=[];
  DB.filter(d=>matchQ(d.last+' '+d.first+' '+d.english+' '+d.business)).forEach(d=>{
    const l=donorDebts(d); if(!l.length)return;
    rows.push({d,list:l,sum:l.reduce((s,x)=>s+x.amt,0)});
  });
  rows.sort((a,b)=>b.sum-a.sum);
  const tot=rows.reduce((s,r)=>s+r.sum,0);
  // סיכום לפי "עבור מה" — כדי לראות במה מרוכז החוב
  const byWhat={}, wlbl={};
  const wkey=w=>String(w||'').replace(/[^\u0590-\u05ffA-Za-z0-9 ]/g,'').replace(/\s+/g,' ').trim()||'אחר';
  rows.forEach(r=>r.list.forEach(x=>{const k=wkey(x.what);
    byWhat[k]=(byWhat[k]||0)+x.amt; if(!wlbl[k]||x.what.length>wlbl[k].length)wlbl[k]=x.what;}));
  const whats=Object.keys(byWhat).sort((a,b)=>byWhat[b]-byWhat[a]);
  const f=n=>'$'+Math.round(n).toLocaleString('en-US');
  view.innerHTML=`
    <div class="totals"><div class="tot pend"><span>🔴 סה"כ חוב פתוח</span><b>${f(tot)}</b></div>
      <div class="tot"><span>תורמים שחייבים</span><b>${rows.length}</b></div></div>
    ${whats.length?`<div class="cattot"><div class="cattot-t">🎯 החוב לפי ייעוד</div>
      ${whats.map(w=>`<div class="catrow"><span>${esc(wlbl[w]||w)}</span><b>${f(byWhat[w])}</b></div>`).join('')}</div>`:''}
    <div class="cnt">${rows.length} תורמים · לפי גובה החוב</div>
    <div class="hintxt" style="margin:0 2px 8px">נכנס לכאן: התחייבות שטרם ניתנה · פרנס שטרם נגבה · תרומה עם תאריך מלא שלא סומנה כשולמה · יתרה בבניין · חוב יש"ז שנקבע במפורש (ידני או "שולם עד חודש").</div>
    <div class="list">${rows.map((r,i)=>`<div class="rowc debtrow"><div class="rowmain" data-did="${r.d.id}">
      <div class="nm">${esc(r.d.last)} <small>${esc(r.d.first)}</small></div>
      ${r.list.map((x,j)=>`<div class="miss"><span class="dbw">${esc(x.what)}</span>${x.when?(' <small>'+esc(x.when)+'</small>'):''}
        — <b style="color:var(--no)">${x.amt?f(x.amt):'ללא סכום'}</b>${x.kind!=='iz'?`<button class="btn sm dbpaid" data-i="${i}" data-j="${j}" onclick="event.stopPropagation()">✓ נגבה</button>`:''}</div>`).join('')}
      ${contactBtns(r.d)}</div>
      <div class="meta"><b class="debtsum">${f(r.sum)}</b></div></div>`).join('')
      ||'<div class="empty">אין חובות פתוחים 🎉</div>'}</div>`;
  view.querySelectorAll('.rowmain').forEach(el=>el.onclick=()=>{const d=DB.find(x=>x.id==el.dataset.did);if(d)openDonor(d);});
  view.querySelectorAll('.dbpaid').forEach(b=>b.onclick=async e=>{
    e.stopPropagation();
    const r=rows[+b.dataset.i], x=r.list[+b.dataset.j]; if(!r||!x)return;
    b.disabled=true;
    if(x.kind==='parnes'){await api('PUT','/api/parnes/'+x.id,{paid:1});
      const p=(r.d.parnes||[]).find(y=>y.id==x.id); if(p)p.paid=1;}
    else if(x.kind==='donation'){await api('PUT','/api/donation/'+x.id,{paid:1});
      const p=(r.d.donations||[]).find(y=>y.id==x.id); if(p)p.paid=1;}
    else if(x.kind==='pledge'){const p=(r.d.pledges||[]).find(y=>y.id==x.id);
      if(p){p.status='נתן';await api('PUT','/api/pledge/'+p.id,p);}}
    else if(x.kind==='building'){const p=(r.d.building||[]).find(y=>y.id==x.id);
      if(p){p.paid=String(amtNum(p.amount));await api('PUT','/api/building/'+p.id,p);}}
    toast('נגבה ✓'); renderDebts();
  });
}
function renderMissed(){
  const q1=DB.filter(d=>matchQ(d.last+' '+d.first+' '+d.english));
  const missed=q1.filter(d=>gaps(d.months).length>0).sort((a,b)=>gaps(b.months).length-gaps(a.months).length);
  // חובות = התחייבויות (pledges) שטרם ניתנו + פרנס־יום שהתחייב וטרם נגבה (paid=0)
  const debts=[];
  q1.forEach(d=>{
    (d.pledges||[]).forEach(p=>{if(p.status!=='נתן')debts.push({d,label:esc(p.category||'התחייבות'),amount:p.amount,method:'',kind:'pledge',id:p.id});});
    (d.parnes||[]).forEach(p=>{if(!Number(p.paid)&&(p.status==='confirmed'||!p.status))debts.push({d,label:(PKLBL[p.kind]||'🕯️ פרנס')+(p.date_text?(' · '+esc(p.date_text)):''),amount:p.amount,method:p.method||'',kind:'parnes',id:p.id});});
  });
  view.innerHTML=`
    <div class="misshead">🔴 חובות והתחייבויות שטרם שולמו (${debts.length})</div>
    <div class="list">${debts.map((x,ix)=>`<div class="rowc"><div class="rowmain" data-id="${x.d.id}"><div class="nm">${esc(x.d.last)} <small>${esc(x.d.first)}</small></div><div class="miss">${x.label} ${x.amount?('· $'+esc(x.amount)):''}${x.method?(' · <span class="pmeth">'+esc(x.method)+'</span>'):''} — <b style="color:var(--no)">טרם נגבה</b></div></div><div class="meta"><button class="btn sm collectbtn" data-ix="${ix}">✓ נגבה</button></div></div>`).join('')||'<div class="hintxt">אין חובות פתוחים 🎉</div>'}</div>
    <div class="misshead" style="margin-top:16px">🔴 חודשים שלא עברו (${missed.length})</div>
    <div class="submuted">לחץ על חודש כדי לסמן שנגבה · "הסר שורה" מסמן שטופל</div>
    <div class="list">${missed.map(d=>{const g=gaps(d.months);return `<div class="rowc"><div class="rowmain" data-id="${d.id}"><div class="nm">${esc(d.last)} <small>${esc(d.first)}</small></div><div class="miss">לא עבר: ${g.map(i=>`<span class="gchip" data-id="${d.id}" data-m="${i}">${MON[i]} ✓</span>`).join(' ')}</div></div><div class="meta"><button class="btn sm ghost missdismiss" data-id="${d.id}">הסר שורה</button>${monthGrid(d.months)}</div></div>`;}).join('')||'<div class="hintxt">אין פספוסים 🎉</div>'}</div>`;
  view.querySelectorAll('.rowmain').forEach(r=>r.onclick=()=>openDonor(DB.find(x=>x.id==r.dataset.id)));
  // סימון חוב/התחייבות כנגבה
  view.querySelectorAll('.collectbtn').forEach(b=>b.onclick=async e=>{e.stopPropagation();const x=debts[+b.dataset.ix];
    if(x.kind==='parnes'){const p=(x.d.parnes||[]).find(y=>y.id==x.id);await api('PUT','/api/parnes/'+x.id,{paid:1});if(p)p.paid=1;
      toastUndo('נגבה ✓',async()=>{await api('PUT','/api/parnes/'+x.id,{paid:0});if(p)p.paid=0;renderMissed();});}
    else{const p=(x.d.pledges||[]).find(y=>y.id==x.id);if(p){const prev=p.status;p.status='נתן';await api('PUT','/api/pledge/'+p.id,p);
      toastUndo('נגבה ✓',async()=>{p.status=prev;await api('PUT','/api/pledge/'+p.id,p);renderMissed();});}}
    renderMissed();});
  // סימון חודש בודד כנגבה
  view.querySelectorAll('.gchip').forEach(c=>c.onclick=async e=>{e.stopPropagation();const d=DB.find(x=>x.id==c.dataset.id);const i=+c.dataset.m;const prev=d.months;d.months=setMonthChar(d.months,i,'c');await api('PUT','/api/donor/'+d.id,{months:d.months});
    toastUndo(MON[i]+' — נגבה ✓',async()=>{d.months=prev;await api('PUT','/api/donor/'+d.id,{months:prev});renderMissed();});renderMissed();});
  // הסרת שורה — סימון כל הפספוסים כ"טופל"
  view.querySelectorAll('.missdismiss').forEach(b=>b.onclick=async e=>{e.stopPropagation();const d=DB.find(x=>x.id==b.dataset.id);const prev=d.months;let nm=d.months;gaps(nm).forEach(i=>nm=setMonthChar(nm,i,'h'));d.months=nm;await api('PUT','/api/donor/'+d.id,{months:nm});
    toastUndo('הוסר ✓',async()=>{d.months=prev;await api('PUT','/api/donor/'+d.id,{months:prev});renderMissed();});renderMissed();});
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
      const s=izSummary(d),cs=curSym(d);
      return `<div class="avrow"><div class="avtop"><b class="avnamelink" data-id="${d.id}" title="פתח כרטיס">${esc(d.last)} ${esc(d.first)}</b>${act.length>1?`<span class="avcount">${act.length} אברכים</span>`:''}<span class="avpaidchip">💰 שולם ${GREGYEAR}: ${cs}${s.paid}${s.hasPay&&s.debt>0.5?(' · <b style="color:var(--no)">חוב '+cs+Math.round(s.debt)+'</b>'):''}</span><span class="avsp"></span><button class="chip avpay" data-id="${d.id}">💰 תשלומים</button><button class="chip avhist" data-id="${d.id}">🕘 היסטוריה${hist.length?' ('+hist.length+')':''}</button><button class="chip avopen" data-id="${d.id}">כרטיס</button></div>
        ${renewBanner(d)}
        <div class="avps">${act.length?act.map(p=>avPartnerRow(p)).join(''):'<div class="hintxt">אין אברך פעיל כרגע</div>'}</div>
        <button class="btn sm avadd" data-id="${d.id}">➕ הוסף אברך</button>
        <div class="avfiles">${(d.files||[]).map(fileChip).join('')}<label class="filebtn">📎 העלה שטר הסכם (PDF)<input type="file" accept="application/pdf,image/*" class="izupload" data-id="${d.id}" hidden></label></div></div>`;}).join('')||'<div class="empty">אין תוצאות</div>';
    view.querySelectorAll('.izupload').forEach(inp=>inp.onchange=()=>uploadFile('iz',+inp.dataset.id,inp,load));
    view.querySelectorAll('.fdel').forEach(b=>b.onclick=async()=>{await api('DELETE','/api/file/'+b.dataset.fid);load();});
    view.querySelectorAll('.avopen').forEach(b=>b.onclick=()=>openDonor(DB.find(x=>x.id==b.dataset.id)));
    view.querySelectorAll('.avnamelink').forEach(b=>b.onclick=()=>openDonor(DB.find(x=>x.id==b.dataset.id)));
    view.querySelectorAll('.cosp2[data-did]').forEach(x=>x.onclick=()=>openDonor(DB.find(y=>y.id==x.dataset.did)));
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
// שותפים לאותו אברך — מקישור ידני (partner_with) וגם זיהוי אוטומטי של תורמים אחרים שמחזיקים אותו אברך
function avCoHolders(p){
  const av=norm(p.avreich||'');const set=new Map();
  if(av)(DB||[]).forEach(o=>{if(o.id==p.donor_id)return;(o.partners||[]).forEach(q=>{if(q.active==0)return;if(norm(q.avreich||'')===av){const nm=(o.last+' '+o.first).trim();const k=norm(nm);if(!set.has(k))set.set(k,{name:nm,id:o.id});}});});
  pwList(p).forEach(x=>{if(x.name){const k=norm(x.name);if(!set.has(k))set.set(k,{name:x.name,id:x.id});}});
  return [...set.values()];
}
function avPartnerRow(p){
  const co=avCoHolders(p);
  const coHtml=co.length?`<div class="avco">🤝 מוחזק במשותף עם: ${co.map(x=>x.id?`<span class="cosp2" data-did="${x.id}">${esc(x.name)} ↗</span>`:esc(x.name)).join(', ')}</div>`:'';
  return `<div class="avp" data-pid="${p.id}">
    <div class="avmain"><input class="avf avname" data-k="avreich" value="${esc(p.avreich||'')}" placeholder="שם האברך">
      <div class="avamt"><span>$</span><input class="avf" data-k="amount" value="${esc(p.amount||'')}" placeholder="סכום" inputmode="decimal"></div>
      <button class="avend" title="החלפת אברך — הקודם יישמר בהיסטוריה">🔄 החלפה</button></div>
    <div class="avsub">
      <label class="avfld"><span>💳 אמצעי</span><select class="avf avmethod" data-k="method">${channelOpts(p.method)}</select></label>
      <label class="avfld"><span>📅 מתאריך ההסכם</span><input class="avf" data-k="start_date" value="${esc(p.start_date||'')}" placeholder="למשל א' אייר תשפ״ה"></label>
      <label class="avfld"><span>📝 הערות</span><input class="avf" data-k="note" value="${esc(p.note||'')}" placeholder="—"></label></div>
    <label class="avfld" style="margin-top:6px"><span>💰 עדכון תשלום ידני (למשל: שילם הכל מראש)</span><input class="avf" data-k="paid_note" value="${esc(p.paid_note||'')}" placeholder="הערת תשלום"></label>
    <label class="jointchk" style="margin-top:6px"><input type="checkbox" class="avjoint" data-pid="${p.id}" ${+p.joint?'checked':''}> 🤝 נותנים ביחד סכום אחד משותף (לא לחבר)</label>
    ${coHtml}</div>`;
}
function bindAvFields(){
  view.querySelectorAll('.avp').forEach(row=>{const pid=row.dataset.pid;
    row.querySelectorAll('.avf').forEach(inp=>{
      const save=async()=>{const body={};body[inp.dataset.k]=inp.value;await api('PUT','/api/partner/'+pid,body);DB.forEach(d=>(d.partners||[]).forEach(p=>{if(p.id==pid)p[inp.dataset.k]=inp.value;}));toast('נשמר ✓');};
      inp.onchange=save;
      let tmr; inp.oninput=()=>{clearTimeout(tmr);tmr=setTimeout(save,800);};   // שמירה גם תוך כדי הקלדה (טאבלט)
    });
    row.querySelector('.avend').onclick=async()=>{const today=todayStr();await api('PUT','/api/partner/'+pid,{active:0,ended_date:today});DB.forEach(d=>(d.partners||[]).forEach(p=>{if(p.id==pid){p.active=0;p.ended_date=today;}}));renderAvreich();toast('הסתיים — עבר להיסטוריה');};
    const jc=row.querySelector('.avjoint');if(jc)jc.onchange=async()=>{const v=jc.checked?1:0;await api('PUT','/api/partner/'+pid,{joint:v});DB.forEach(d=>(d.partners||[]).forEach(p=>{if(p.id==pid)p.joint=v;}));renderAvreich();toast(jc.checked?'סומן כמשותף ✓':'בוטל');};});
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
/* ---------- 📧 כל המיילים שנמשכו — במקום אחד ---------- */
let mailFlt='';
function renderMails(){
  const all=[];
  DB.forEach(d=>(d.contacts||[]).forEach(c=>{ if(c.channel==='אימייל') all.push({c,d}); }));
  all.sort((a,b)=>String(b.c.date||'').localeCompare(String(a.c.date||''))||b.c.id-a.c.id);
  const withFiles=all.filter(x=>(x.c.files||[]).length).length;
  const F=[['','הכל',all.length],['in','📥 מהתורם',all.filter(x=>x.c.direction!=='out').length],
           ['out','📤 ששלחנו',all.filter(x=>x.c.direction==='out').length],
           ['files','📎 עם קבצים',withFiles],
           ['kv','🕯️ שמות לקוויטל',all.filter(x=>(x.c.summary||'').includes('🕯️')).length]];
  chips.innerHTML=F.map(([k,l,n])=>`<button class="chip ${mailFlt===k?'on':''}" data-k="${k}">${l} <b>${n}</b></button>`).join('');
  chips.querySelectorAll('.chip').forEach(b=>b.onclick=()=>{mailFlt=b.dataset.k;render();});
  let list=all;
  if(mailFlt==='in')list=list.filter(x=>x.c.direction!=='out');
  if(mailFlt==='out')list=list.filter(x=>x.c.direction==='out');
  if(mailFlt==='files')list=list.filter(x=>(x.c.files||[]).length);
  if(mailFlt==='kv')list=list.filter(x=>(x.c.summary||'').includes('🕯️'));
  list=list.filter(x=>matchQ((x.d.last||'')+' '+(x.d.first||'')+' '+(x.c.summary||'')+' '+(x.c.body||'')+' '+(x.c.body_he||'')));
  view.innerHTML=`<div class="rbtitle">📧 כל המיילים עם התורמים — נכנסים וששלחנו, לפי תאריך</div>
    <div class="addrow" style="margin:0 2px 8px"><button class="btn sm ghost" id="ml_sync" style="width:100%">📥 משוך מיילים (נכנסים + ששלחנו) ותייק אצל התורמים</button></div>
    <div class="addrow" style="margin:0 2px 8px"><select id="ml_cat" style="flex:1">${['— כל התורמים —',...[...new Set(DB.map(d=>(d.category||'').trim()).filter(Boolean))].sort((a,b)=>a.localeCompare(b,'he'))].map(c=>`<option>${esc(c)}</option>`).join('')}</select>
      <a class="btn sm ghost" id="ml_csv" href="#" style="flex:1;text-align:center;text-decoration:none">📤 ייצוא רשימת תפוצה (CSV)</a></div>
    <div class="hintxt" style="margin:-4px 2px 10px">שורה לכל כתובת מייל — כולל תורמים עם כמה כתובות. מתאים לייבוא ל-Brevo / MailerLite לדיוור אישי עם שם התורם.</div>
    <div class="cnt">${list.length} מיילים</div>
    <div class="list">${list.map(({c,d},i)=>`<div class="mailrow">
      <div class="mailhd"><span class="mlwho" data-did="${d.id}">${esc((d.last||'')+' '+(d.first||''))} ↗</span>
        <span class="mldate">${c.direction==='out'?'📤 שלחנו · ':'📥 קיבלנו · '}${esc(c.date||'')}</span></div>
      <div class="mlsum">${esc(c.summary||'')}</div>
      ${(c.body_he||c.body||'').trim()?`<details class="mailfull"><summary>הצג את המייל המלא${(c.body_he||'').trim()?' (בעברית)':''}</summary>
        ${(c.body_he||'').trim()?`<pre class="mhe">${esc(c.body_he)}</pre><details class="morig"><summary>🔤 הצג את המקור באנגלית</summary><pre>${esc(c.body)}</pre></details>`:`<pre>${esc(c.body)}</pre>`}
      </details>`:''}
      ${(c.files||[]).length?`<div class="avfiles dnfiles">${(c.files||[]).map(fileChip).join('')}</div>`:''}
    </div>`).join('')||'<div class="empty">אין מיילים. לחץ "משוך מיילים".</div>'}</div>`;
  view.querySelectorAll('.mlwho').forEach(w=>w.onclick=()=>openDonor(DB.find(x=>x.id==w.dataset.did),'contact'));
  view.querySelectorAll('.mailrow .fdel').forEach(b=>b.onclick=async()=>{await api('DELETE','/api/file/'+b.dataset.fid);await load();render();toast('נמחק');});
  const ms=document.getElementById('ml_sync'); if(ms)ms.onclick=()=>runMailSync(ms);
  const mc=document.getElementById('ml_cat'),mx=document.getElementById('ml_csv');
  if(mx){const setu=()=>{const c=mc.selectedIndex>0?mc.value:'';
      mx.href='/api/donors.csv'+(c?('?cat='+encodeURIComponent(c)):'');mx.setAttribute('download','');};
    mc.onchange=setu; setu();}
}
function renderCamp(){
  const camps={};
  DB.forEach(d=>(d.pledges||[]).forEach(p=>{const k=p.category||'ללא';camps[k]=camps[k]||{given:0,pending:0,gsum:0,psum:0,rows:[]};const a=amtNum(p.amount),g=p.status==='נתן';if(g){camps[k].given++;camps[k].gsum+=a;}else{camps[k].pending++;camps[k].psum+=a;}camps[k].rows.push({name:(d.last+' '+d.first).trim(),amt:p.amount,given:g});}));
  const keys=Object.keys(camps).filter(k=>matchQ(k));
  view.innerHTML=`<div class="cnt">${keys.length} קמפיינים</div>`+(keys.map(k=>{const c=camps[k],t=c.given+c.pending,pct=t?Math.round(100*c.given/t):0;return `<div class="campc"><h3>${esc(k)}</h3><div class="csub">נתנו ${c.given} · טרם ${c.pending} · התקבל $${c.gsum} · צפוי $${c.psum}</div><div class="campbar"><i style="width:${pct}%"></i></div>${c.rows.sort((a,b)=>a.given-b.given).map(r=>`<div class="camprow ${r.given?'given':'pending'}"><span>${esc(r.name)}</span><span>$${esc(r.amt)} · ${r.given?'נתן ✓':'טרם ✗'}</span></div>`).join('')}</div>`;}).join('')||'<div class="empty">אין עדיין קמפיינים. הוסף התחייבות בכרטיס תורם.</div>');
}

/* ---------- משימות ---------- */
// כפתורי קשר מהירים — התקשרות / וואטסאפ / אימייל ישירות מהמשימה
function waNum(p){let n=(p||'').replace(/[^0-9]/g,'');if(n.length>=9&&n[0]==='0')n='972'+n.slice(1);return n;}
function contactBtns(d){
  const ph=splitPhones(d.phone)[0]||'', wa=waNum(ph), em=(d.email||'').trim();
  let h='';
  if(ph)h+=`<a class="cbtn call" href="tel:${esc(ph)}" onclick="event.stopPropagation()" title="התקשר ${esc(ph)}">📞</a>`;
  if(wa)h+=`<a class="cbtn wa" href="https://wa.me/${wa}" target="_blank" rel="noopener" onclick="event.stopPropagation()" title="וואטסאפ">💬</a>`;
  if(em)h+=`<a class="cbtn mail" href="mailto:${esc(em)}" onclick="event.stopPropagation()" title="${esc(em)}">📧</a>`;
  return h?`<span class="cbtns">${h}</span>`:'';
}
// מציאת רשומת הפרנס שאליה שייכת משימת הפרנס (לפי הטקסט/תאריך)
function taskParnes(t){
  if(t.kind!=='parnes'||!t.dref)return null;
  const ps=t.dref.parnes||[];
  return ps.find(p=>p.date_text&&(t.note||'').includes(p.date_text))||ps[0]||null;
}
function renderTasksTab(){
  const today=todayStr();
  const opts=[['','הכל'],['charge','💳 לחייב'],['parnes','🌙 פרנס'],['prayer','🙏 תפילה'],['followup','📞 לחזור']];
  chips.innerHTML=opts.map(([k,l])=>`<button class="chip ${flt===k?'on':''}" data-k="${k}">${l}</button>`).join('');
  chips.querySelectorAll('.chip').forEach(c=>c.onclick=()=>{flt=c.dataset.k;render();});
  let all=[];
  const isDone=t=>!!(t.done&&t.done!=0);
  // פרנס יום מופיע במשימות רק כשמגיע שבוע לפני הלילה (תאריך התזכורת = שבוע לפני), לא חודשים מראש
  const hideParnes=t=>t.kind==='parnes'&&!isDone(t)&&t.due_date&&t.due_date>today;
  DB.forEach(d=>(d.tasks||[]).forEach(t=>{if(isDone(t)!==showDone||hideParnes(t))return;all.push({...t,donor:(d.last+' '+d.first).trim(),dref:d});}));
  GTASKS.forEach(t=>{if(isDone(t)!==showDone||hideParnes(t))return;all.push({...t,donor:'',dref:null});});   // משימות חופשיות בלי תורם
  if(flt) all=all.filter(t=>t.kind===flt);
  if(taskWho) all=all.filter(t=>taskWho==='מאיר'?!(t.assignee||'').trim():(t.assignee||'')===taskWho);
  all=all.filter(t=>matchQ(t.donor+' '+(t.note||'')));
  all.sort((a,b)=>(a.due_date||'9999').localeCompare(b.due_date||'9999'));
  // ספירת משימות פתוחות לכל אחד (מאיר=ריק, אהרן)
  const openAll=[];DB.forEach(d=>(d.tasks||[]).forEach(t=>{if(!(t.done&&t.done!=0)&&!hideParnes(t))openAll.push(t);}));GTASKS.forEach(t=>{if(!(t.done&&t.done!=0)&&!hideParnes(t))openAll.push(t);});
  const cnt=w=>openAll.filter(t=>w===''?true:(w==='מאיר'?!(t.assignee||'').trim():(t.assignee||'')===w)).length;
  const WHO=[['','📋 הכל'],['מאיר','👤 מאיר (אני)'],['אהרן','👤 אהרן']];
  const inWho=taskWho==='אהרן'?'אהרן':(taskWho==='מאיר'?'מאיר':'');
  const ics=location.origin+'/calendar.ics';
  // חובות פרנס — כל פרנס שאושר וטרם נגבה, מופיע כאן לגבייה (וגם בכרטיס התורם)
  // פרנס יום נכנס לרשימה רק משבוע לפני הלילה (או אם כבר עבר וטרם נגבה) — לא חודשים מראש
  const wkAhead=inDaysStr(7);
  const pdebts=[]; DB.forEach(d=>(d.parnes||[]).forEach(p=>{if(p.status!=='suggested'&&!+p.paid&&(!p.night_date||p.night_date<=wkAhead)&&matchQ(d.last+' '+d.first+' '+(p.date_text||'')))pdebts.push({d,p});}));
  pdebts.sort((a,b)=>(a.p.night_date||'').localeCompare(b.p.night_date||''));
  const debtSec=pdebts.length?`<div class="misshead" style="margin-top:10px">🔴 חובות פרנס לגבייה (${pdebts.length})</div>
    <div class="list">${pdebts.map(x=>`<div class="rowc"><div class="rowmain" data-did="${x.d.id}"><div class="nm">${esc(x.d.last)} <small>${esc(x.d.first)}</small></div><div class="miss">${esc(DAYKIND[x.p.kind]||'🌙 פרנס')}${x.p.date_text?(' · '+esc(x.p.date_text)):''}${x.p.hyear?(' '+esc(x.p.hyear)):''}${x.p.amount?(' · '+curSym(x.d)+esc(x.p.amount)):''} — <b style="color:var(--no)">טרם נגבה</b></div>${contactBtns(x.d)}</div><div class="meta"><button class="btn sm pcollect" data-pid="${x.p.id}" data-did="${x.d.id}">✓ נגבה</button></div></div>`).join('')}</div>`:'';
  const renews=[]; DB.forEach(d=>{const r=renewInfo(d);if(r&&matchQ(d.last+' '+d.first))renews.push({d,r});});
  renews.sort((a,b)=>(a.r.date||'').localeCompare(b.r.date||''));
  const renewSec=renews.length?`<div class="misshead" style="margin-top:10px">🔴 חידוש שותפות יש"ז מתקרב (${renews.length})</div>
    <div class="list">${renews.map(x=>`<div class="rowc"><div class="rowmain" data-did="${x.d.id}"><div class="nm">${esc(x.d.last)} <small>${esc(x.d.first)}</small></div><div class="miss">🤝 ${x.r.avreich?esc(x.r.avreich)+' · ':''}${x.r.days<0?'עברה שנה מההתחלה':('סיום שנה '+fmtGreg(x.r.date))}${x.r.days>=0?(' · בעוד '+x.r.days+' ימים'):''} — <b style="color:var(--no)">לחדש + תעודה חדשה</b></div>${contactBtns(x.d)}</div><div class="meta"><button class="btn sm avopen2" data-did="${x.d.id}">כרטיס</button></div></div>`).join('')}</div>`:'';
  view.innerHTML=`<div class="whobar">${WHO.map(([w,l])=>`<button class="whochip ${taskWho===w?'on':''}" data-w="${w}">${l} <b>${cnt(w)}</b></button>`).join('')}</div>
    <div class="addrow" style="margin:0 2px 8px"><button class="btn sm ghost" id="tk_mailsync" style="width:100%">📥 משוך מיילים (נכנסים + ששלחנו) ותייק אצל התורמים</button></div>${renewSec}${debtSec}
    <div class="sec newtask"><h3>➕ משימה חדשה${taskWho==='אהרן'?' — לאהרן':(taskWho==='מאיר'?' — למאיר':'')}</h3>
      <input id="nt_note" placeholder="✍️ מה צריך לעשות? (משימה חופשית)" autocomplete="off">
      <input id="nt_q" placeholder="🔍 שייך לתורם (רשות) — שם / טלפון / עסק…" autocomplete="off" style="margin-top:6px">
      <div id="nt_res" class="dpres"></div>
      <div id="nt_chosen" class="pick" style="display:none"></div>
      <div class="two" style="margin-top:6px"><select id="nt_kind">${taskKindOpts()}</select><input id="nt_date" type="date" value="${today}"></div>
      <label class="fld" style="margin-top:6px"><span>👤 מי מבצע</span><select id="nt_who">${assigneeOpts(inWho)}</select></label>
      <div class="avfiles dnfiles" id="nt_files"><label class="filebtn sm">📎 צרף כרטיס אשראי / הקלטה / צילום<input type="file" multiple accept="image/*,audio/*,application/pdf" id="nt_file" hidden></label></div>
      <button class="btn" id="nt_add" style="width:100%;margin-top:6px">➕ הוסף משימה${taskWho==='אהרן'?' לאהרן':''}</button>
      <div class="hintxt">בחר מי מבצע — מאיר או אהרן. ברירת המחדל היא החלון שאתה נמצא בו. אפשר גם לשייך לתורם.</div></div>
    <details class="icsmini"><summary>📅 כתובת יומן Google (כבר חובר)</summary><span class="u" id="icsurl">${ics}</span><button class="btn sm" id="icscopy" style="margin-top:6px">העתק כתובת</button></details>
    <div class="cnt" style="display:flex;justify-content:space-between;align-items:center;gap:8px"><span>${all.length} ${showDone?'משימות שבוצעו':'משימות · לפי תאריך קרוב'}</span><button class="btn sm ghost" id="toggledone">${showDone?'🔔 חזרה לפתוחות':'✓ הצג שבוצעו'}</button></div><div class="list">${all.map((t,i)=>{
    const over=t.due_date&&t.due_date<today, icon=kindLabel(t.kind).split(' ')[0], g=gcalLink(t,t.donor||t.note||'משימה');
    const isParnes=t.kind==='parnes'&&taskParnes(t);
    return `<div class="rowc taskrow ${showDone?'donerow':''}" data-i="${i}"><button class="tdone ${showDone?'restore':''}" data-done="${i}" title="${showDone?'החזר לפתוחות':'בוצע'}">${showDone?'↩️':'✓'}</button>
      <div><div class="nm">${icon} ${esc(t.donor||t.note||'משימה')}</div>${isCustKind(t.kind)?`<div class="miss2">📌 ${esc(custKind(t.kind))}</div>`:''}${t.donor&&t.note?`<div class="miss2">${esc(t.note)}</div>`:''}${t.dref?contactBtns(t.dref):''}</div>
      <div class="meta"><span class="tdate ${over?'over':''}">${esc(t.due_date||'—')}</span>
        <button class="whoflip ${(t.assignee||'')==='אהרן'?'ah':'me'}" data-i="${i}" title="לחץ להחליף בין מאיר לאהרן" onclick="event.stopPropagation()">👤 ${(t.assignee||'')==='אהרן'?'אהרן':'מאיר'} ⇄</button>
        <button class="tedit" data-i="${i}" title="ערוך משימה" onclick="event.stopPropagation()">✏️ ערוך</button>${g?`<a class="gcal" href="${g}" target="_blank" rel="noopener" onclick="event.stopPropagation()">ליומן</a>`:''}</div></div>
    <div class="teditpanel hidden" data-panel="${i}">
      ${isParnes?`<button class="btn sm tparnes" data-i="${i}" style="background:var(--gold);width:100%;margin-bottom:8px">🌙 החלף/ערוך את הפרנס בלוח</button>`:''}
      <label class="fld"><span>✏️ טקסט המשימה</span><textarea class="tnote" data-i="${i}" rows="3" placeholder="מה צריך לעשות">${esc(t.note||'')}</textarea></label>
      <div class="two" style="margin-top:6px"><label class="fld"><span>סוג</span><select class="tkindsel" data-i="${i}">${taskKindOpts(t.kind)}</select></label>
        <label class="fld"><span>👤 מי מטפל (אפשר להעביר לאהרן)</span><select class="twho" data-i="${i}">${assigneeOpts(t.assignee)}</select></label></div>
      <div class="addrow" style="margin-top:6px"><input type="date" class="tdate2" data-i="${i}" value="${esc(t.due_date||'')}"><button class="btn sm tsave" data-i="${i}">💾 שמור</button><button class="del tdel" data-i="${i}">🗑 מחק</button></div>
      <div class="avfiles" style="margin-top:6px">${(t.files||[]).map(fileChip).join('')}<label class="filebtn">📎 צרף תמונה / הקלטה / אסמכתא<input type="file" accept="image/*,audio/*,application/pdf" class="ttup" data-id="${t.id}" hidden></label></div>
    </div>`;
  }).join('')||'<div class="empty">אין משימות פתוחות 🎉</div>'}</div>`;
  view.querySelectorAll('.whochip').forEach(b=>b.onclick=()=>{taskWho=b.dataset.w;render();});
  // חובות פרנס — פתיחת כרטיס / סימון שנגבה
  view.querySelectorAll('.rowmain[data-did]').forEach(r=>r.onclick=e=>{if(e.target.closest('.cbtns'))return;openDonor(DB.find(x=>x.id==r.dataset.did));});
  view.querySelectorAll('.avopen2').forEach(b=>b.onclick=e=>{e.stopPropagation();openDonor(DB.find(x=>x.id==b.dataset.did));});
  view.querySelectorAll('.pcollect').forEach(b=>b.onclick=async e=>{e.stopPropagation();const d=DB.find(x=>x.id==+b.dataset.did),p=(d&&d.parnes||[]).find(x=>x.id==+b.dataset.pid);if(p){p.paid=1;await api('PUT','/api/parnes/'+p.id,{paid:1});}toast('נגבה ✓');render();});
  document.getElementById('icscopy').onclick=()=>{navigator.clipboard&&navigator.clipboard.writeText(ics);toast('הכתובת הועתקה ✓');};
  // עריכת / מחיקת משימה
  // החלפה מהירה בין מאיר לאהרן, ישירות מהשורה
  view.querySelectorAll('.whoflip').forEach(b=>b.onclick=async e=>{
    e.stopPropagation();
    const t=all[b.dataset.i]; if(!t)return;
    const who=(t.assignee||'')==='אהרן'?'':'אהרן';
    b.disabled=true;
    await api('PUT','/api/task/'+t.id,{assignee:who});
    t.assignee=who;
    const rec=t.dref?(t.dref.tasks||[]).find(x=>x.id===t.id):GTASKS.find(x=>x.id===t.id);
    if(rec)rec.assignee=who;
    toast(who==='אהרן'?'הועבר לאהרן ✓':'הועבר למאיר ✓');
    render();
  });
  view.querySelectorAll('.tkindsel').forEach(wireKindSel);
  view.querySelectorAll('.tedit').forEach(b=>b.onclick=e=>{e.stopPropagation();const p=view.querySelector('.teditpanel[data-panel="'+b.dataset.i+'"]');if(p)p.classList.toggle('hidden');});
  view.querySelectorAll('.tsave').forEach(b=>b.onclick=async()=>{const t=all[b.dataset.i];const note=view.querySelector('.tnote[data-i="'+b.dataset.i+'"]').value.trim(),date=view.querySelector('.tdate2[data-i="'+b.dataset.i+'"]').value;const whoEl=view.querySelector('.twho[data-i="'+b.dataset.i+'"]');const who=whoEl?whoEl.value:(t.assignee||'');const kEl=view.querySelector('.tkindsel[data-i="'+b.dataset.i+'"]');const kind=kEl?(await kindValue(kEl)):(t.kind||'other');if(!kind)return;await api('PUT','/api/task/'+t.id,{note:note,kind:kind,due_date:date,assignee:who});t.note=note;t.kind=kind;t.due_date=date;t.assignee=who;const rec=t.dref?(t.dref.tasks||[]).find(x=>x.id===t.id):GTASKS.find(x=>x.id===t.id);if(rec){rec.note=note;rec.kind=kind;rec.due_date=date;rec.assignee=who;}toast(who==='אהרן'?'הועבר לאהרן ✓':'נשמר ✓');render();});
  view.querySelectorAll('.tdel').forEach(b=>b.onclick=async()=>{const t=all[b.dataset.i];if(!await uiConfirm('למחוק את המשימה?'))return;await api('DELETE','/api/task/'+t.id);if(t.dref)t.dref.tasks=(t.dref.tasks||[]).filter(x=>x.id!==t.id);else GTASKS=GTASKS.filter(x=>x.id!==t.id);toast('נמחק');render();checkReminders();});
  view.querySelectorAll('.tparnes').forEach(b=>b.onclick=()=>{const t=all[b.dataset.i],p=taskParnes(t);if(!p){toast('לא נמצא פרנס');return;}tab='parnes';pyKind=p.kind||'parnes';pyMonth=p.month;pyDay=+p.day;flt='';plaque=null;document.querySelectorAll('.tab').forEach(x=>x.classList.toggle('on',x.dataset.tab==='parnes'));render();});
  // משימה חדשה — חיפוש ובחירת תורם
  let ntChosen=null;
  const ntq=document.getElementById('nt_q'),ntres=document.getElementById('nt_res'),ntch=document.getElementById('nt_chosen');
  ntq.oninput=()=>{const s=norm(ntq.value);if(!s){ntres.innerHTML='';ntChosen=null;ntch.style.display='none';return;}
    const m=DB.filter(d=>norm(d.last+' '+d.first+' '+d.english+' '+d.phone+' '+d.business).includes(s)).slice(0,8);
    ntres.innerHTML=m.map(d=>`<div class="dpr" data-id="${d.id}">${esc(d.last)} ${esc(d.first)}${d.tier==='יששכר_זבולון'?' · יש"ז':''}${d.phone?(' · '+esc(splitPhones(d.phone)[0])):''}</div>`).join('')||'<div class="dpr" style="color:var(--muted)">אין תוצאות</div>';
    ntres.querySelectorAll('.dpr[data-id]').forEach(x=>x.onclick=()=>{ntChosen=DB.find(y=>y.id==x.dataset.id);ntch.style.display='block';ntch.innerHTML='✓ נבחר: <b>'+esc((ntChosen.last+' '+ntChosen.first).trim())+'</b>';ntres.innerHTML='';ntq.value=(ntChosen.last+' '+ntChosen.first).trim();});};
  const tms=document.getElementById('tk_mailsync');
  if(tms)tms.onclick=()=>runMailSync(tms);
  const ntF=pendFiles('nt_files','nt_file');
  wireKindSel(document.getElementById('nt_kind'));
  addMic(document.getElementById('nt_note'));
  addMics(view,['.tnote']);
  document.getElementById('nt_add').onclick=async()=>{
    const kind=await kindValue(document.getElementById('nt_kind'));if(!kind)return;
    const date=document.getElementById('nt_date').value,note=document.getElementById('nt_note').value.trim();
    const whoEl=document.getElementById('nt_who');
    const who=whoEl?whoEl.value:inWho;   // ברירת המחדל לפי החלון, וניתן לשנות כאן
    if(!note&&!ntChosen){toast('כתוב מה צריך לעשות');return;}
    if(!date){toast('בחר תאריך');return;}
    const body={due_date:date,kind:kind,note:note,assignee:who};
    if(ntChosen)body.donor_id=ntChosen.id;
    const r=await api('POST','/api/task',body);
    const rec={id:r.id,donor_id:ntChosen?ntChosen.id:null,due_date:date,kind:kind,note:note,assignee:who,done:0};
    if(ntChosen){ntChosen.tasks=ntChosen.tasks||[];ntChosen.tasks.push(rec);}else{GTASKS.push(rec);}
    if(ntF.arr.length){toast('מעלה קבצים…');for(const f of ntF.arr)await uploadBlob('task',r.id,f);ntF.reset();await load();}
    toast('המשימה נוספה ✓'+(who?' — '+who:''));render();checkReminders();};
  view.querySelectorAll('.ttup').forEach(inp=>inp.onchange=()=>uploadFile('task',+inp.dataset.id,inp,load));
  view.querySelectorAll('.teditpanel .fdel').forEach(b=>b.onclick=async()=>{await api('DELETE','/api/file/'+b.dataset.fid);load();});
  view.querySelectorAll('.taskrow').forEach(r=>r.onclick=e=>{if(e.target.classList.contains('tdone')||e.target.classList.contains('gcal'))return;const t=all[r.dataset.i];if(t.dref)openDonor(t.dref);});
  const setDone=async(t,v)=>{if(t.id)await api('PUT','/api/task/'+t.id,{done:v});t.done=v;const rec=t.dref?(t.dref.tasks||[]).find(x=>x.id===t.id):GTASKS.find(x=>x.id===t.id);if(rec)rec.done=v;};
  view.querySelectorAll('.tdone').forEach(b=>b.onclick=async e=>{e.stopPropagation();const t=all[b.dataset.done];
    if(showDone){await setDone(t,0);toast('הוחזר לפתוחות ✓');render();checkReminders();}
    else{await setDone(t,1);render();checkReminders();toastUndo('בוצע ✓',async()=>{await setDone(t,0);render();checkReminders();});}
  });
  const tgd=document.getElementById('toggledone');if(tgd)tgd.onclick=()=>{showDone=!showDone;render();};
}

/* ---------- מזדמנים ---------- */
function renderOcc(){
  const list=OCC.filter(o=>matchQ(o.name+' '+o.detail));
  view.innerHTML=`<div class="cnt">${list.length} מזדמנים</div><div class="list">${list.map(o=>`<div class="rowc" style="cursor:default"><div><div class="nm">${esc(o.name)}</div><div class="en">${esc(o.detail)}</div></div><div class="meta"><span class="ph">${o.total?('$'+esc(o.total)):''}</span></div></div>`).join('')||'<div class="empty">אין תוצאות</div>'}</div>`;
}

// כפתור ההכתבה הצף — זמין בכל מסך. אם הדפדפן לא תומך בהכתבה, מסתירים אותו
(function(){const h=document.getElementById('healthbtn');if(h)h.onclick=()=>openHealth();})();
(function(){const f=document.getElementById('dictfab');if(!f)return;
  if(!(window.SpeechRecognition||window.webkitSpeechRecognition)){f.style.display='none';return;}
  f.onclick=()=>openDictPad();})();
load();
