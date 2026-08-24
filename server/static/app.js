'use strict';
let HEBTODAY = '';
let DB = [], OCC = [], UNLINKED = [], GTASKS = [], CAMPAIGNS = [], BUILDING_ITEMS = [], TASKKINDS_C = [], CHAN_C = [], CLK_C = [], tab = 'donors', flt = '', q = '', plaque = null, GLAST = 6, pyMonth = null, pyDay = null, HEBYEAR = '', donSort = 'last', taskWho = '', showDone = false;
// מאיר (אני, ריק) ואהרן — הקצאת משימות
function assigneeOpts(cur){return [['','מאיר'],['אהרן','אהרן']].map(([v,l])=>`<option value="${v}" ${v===(cur||'')?'selected':''}>${l}</option>`).join('');}
function curSym(d){ return (d && d.region==='il') ? '₪' : '$'; }
// מטבע של יום פרנס: מה שנבחר לאותו יום, ואם לא נבחר — לפי האזור של התורם
function pCur(p,d){ return (p&&String(p.currency||'').trim())||curSym(d); }
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
// מאיר: "הוא נותן אלף שקל והוא נותן 400 דולר וביחד יששכר־זבולון" —
// לכל שורת אברך מטבע משלה, כך ששני שותפים באותו אברך יכולים לשלם
// כל אחד במטבע שלו. ברירת המחדל היא מטבע הכרטיס.
function pCur(p,d){const c=String((p&&p.cur)||'').trim();
  return c==='₪'?'₪':(c==='$'?'$':curSym(d));}
function curOpts(cur){return ['$','₪'].map(x=>`<option value="${x}" ${x===cur?'selected':''}>${x}</option>`).join('');}
function jointPayerId(p){const v=+(p.joint_payer||0);return v>0?v:0;}
function partnerMonthly(p){
  // חלוקה לא שווה: אצל כל מחזיק נרשם כמה הוא בעצמו משלם מהכרטיס שלו.
  // זה גובר על כל חישוב אחר — כולל 0 למי שמחזיק אך אינו משלם.
  if(String(p.share||'').trim()!=='')return amtNum(p.share);
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
  // כשיש אברכים בשני מטבעות — לא מחברים שקלים לדולרים. שומרים פירוט
  // לפי מטבע, וזה מה שמוצג בשורת ההתחייבות החודשית (מאיר).
  const byCur={};
  parts.forEach(p=>{const c=pCur(p,d);byCur[c]=(byCur[c]||0)+partnerMonthly(p);});
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
  return {parts,monthly,paid,span,expected,debt,hasPay,fromCard,thru,thruDebt,manual,byCur};
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
// סך התרומות לאברך אחד לפי מטבע — כשמחזיק אחד משלם בשקלים והשני
// בדולרים, אין מספר אחד שמייצג את שניהם (מאיר).
function coHolderByCur(p,d){
  const av=norm(p.avreich||''),m={};
  m[pCur(p,d)]=amtNum(p.amount);
  if(av)(DB||[]).forEach(o=>{if(o.id==p.donor_id)return;(o.partners||[]).forEach(q=>{
    if(q.active==0||norm(q.avreich||'')!==av||+q.joint)return;
    const c=pCur(q,o);m[c]=(m[c]||0)+amtNum(q.amount);});});
  return m;
}
function coHolderTotalTxt(p,d){
  const m=coHolderByCur(p,d),ks=Object.keys(m).filter(k=>Math.round(m[k])>0);
  return ks.map(k=>k+Math.round(m[k]).toLocaleString('en-US')).join(' + ');
}
// שותפויות הפוכות — כרטיסים אחרים שרשמו את התורם הזה כשותף מחזיק (לפי קישור או לפי שם שהוקלד)
// מאיר: "למה לא רואים אצל יואל שטטפלד שהוא שותף עם בנימין ומחזיק את חבה?
// התשלום יוצא רק מבנימין אבל שניהם שותפים". השותפות שלהם רשומה כחלוקת
// תשלום ולא בשדה "מחזיקים יחד עם", ולכן היא נקראת גם משם.
function coHeldWith(d){
  const out=[],seen=new Set();
  const dn=norm((d.last||'')+' '+(d.first||''));const dt=dn.split(' ').filter(t=>t.length>=2);
  const add=(o,p,split)=>{
    if(!String(p.avreich||'').trim())return;
    const k=o.id+'|'+norm(p.avreich); if(seen.has(k))return; seen.add(k);
    out.push({name:(o.last+' '+o.first).trim(),did:o.id,avreich:p.avreich,
              amount:(String(p.share||'').trim()!==''?p.share:p.amount),
              cur:pCur(p,o),method:p.method,split:split?1:0});};
  (DB||[]).forEach(o=>{if(o.id===d.id)return;(o.partners||[]).forEach(p=>{if(p.active==0)return;
    const idlist=(String(p.partner_with_id||'')).split(',').map(s=>s.trim()).filter(Boolean);
    const linked=idlist.includes(String(d.id));
    const byname=!idlist.length&&p.partner_with&&dt.length&&dt.every(t=>norm(p.partner_with).includes(t));
    if(linked||byname)add(o,p,0);});});
  // שותף בחלוקת התשלום מחזיק יחד גם את האברכים — הכסף יוצא מאחד מהם,
  // והשני עדיין שותף. הסכום נשאר רשום אצל מי שהשורה רשומה אצלו.
  // מאיר: "אדלין ודהאן — כל אחד נותן 1000 ליששכר־זבולון שלו, וזה יוצא
  // מהעסק בתשלום אחד של 2000". למי שיש אברך משלו — החלוקה כספית בלבד,
  // והוא אינו מחזיק גם את האברך של השני.
  const ownAv=(d.partners||[]).some(p=>p.active!=0&&String(p.avreich||'').trim());
  if(!ownAv)(d.paysplit||[]).forEach(s=>{
    const o=(DB||[]).find(x=>x.id===s.with_id); if(!o||o.id===d.id)return;
    (o.partners||[]).forEach(p=>{if(p.active==0)return; add(o,p,1);});});
  return out;
}
// מאיר: "כשאני מעדכן שבנימין שטטפלד מחזיק ביחד עם יואל שטטפלד את יחזקאל
// חבה — כשאני נכנס לחלון של יששכר־זבולון זה אמור להראות שהם שותפים, וגם
// ברשימה לפי אברכים או לפי תורמים זה אמור להיות מסונכרן".
// השותפות נרשמת על שורה אחת בלבד, ולכן אצל השותף לא הייתה לה שום עדות.
// כאן היא נקראת מהצד השני: כל אברך שמישהו אחר רשם שהתורם הזה מחזיק איתו,
// ושאין לו שורה משלו אצל התורם.
function izLinkedRows(d){
  const own=new Set((d.partners||[]).filter(p=>p.active!=0).map(p=>norm(p.avreich||'')));
  return coHeldWith(d).filter(x=>x.avreich&&!own.has(norm(x.avreich)));
}
function izLinkedHTML(d,cur){
  const l=izLinkedRows(d); if(!l.length)return '';
  return l.map(x=>`<div class="izrow izlink"><span>👨‍🎓 ${esc(x.avreich)}`
    + ` <small class="cosp">🤝 בשותפות עם <span class="cosp2" data-did="${x.did}">${esc(x.name)} ↗</span></small>`
    + `${x.amount?` <small class="cosptot">${x.split?'התשלום יוצא ממנו — ':'רשום שם '}${x.cur||cur}${Math.round(amtNum(x.amount)).toLocaleString('en-US')}</small>`:''}`
    + `</span><b class="izlinkb">—</b></div>`).join('');
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
// תשלומים שנכנסו לכרטיס בלי לציין עבור מה. אצל תורם שכל ההתחייבות שלו היא
// יששכר־זבולון, כמעט תמיד זה בדיוק זה — אבל לא מניחים, שואלים.
function unclassifiedIz(d){
  const rows=(d.donations||[]).filter(x=>{
    const c=String(x.category||'').trim();
    return !/יששכר|זבולון/.test(c) &&
      (!c || c==='קבוע' || /לא סווג/.test(String(x.note||'')));
  });
  return {n:rows.length, sum:rows.reduce((s2,x)=>s2+amtNum(x.amount),0), rows};
}
// ההתחייבות החודשית כטקסט — במטבע אחד סכום אחד, ובשני מטבעות שניהם
// זה לצד זה ("₪1,000 + $400"), בלי לחבר ביניהם.
function izMonthlyTxt(s,cur){
  const ks=Object.keys(s.byCur||{}).filter(k=>Math.round(s.byCur[k])>0);
  if(ks.length>1)return ks.map(k=>k+Math.round(s.byCur[k]).toLocaleString('en-US')).join(' + ');
  return (ks[0]||cur)+Math.round(s.monthly).toLocaleString('en-US');
}
// סכום אברך שמוחזק "ביחד" כפי שהוא נראה לכל המחזיקים. אם כולם באותו
// מטבע — מספר אחד; אם אחד בשקלים והשני בדולרים — שני החלקים זה לצד זה.
function jointTotalTxt(p,d){
  const m={};
  jointGroup(p).forEach(x=>{const c=pCur(x.p,x.d);m[c]=(m[c]||0)+partnerMonthly(x.p);});
  const ks=Object.keys(m).filter(k=>Math.round(m[k])>0);
  if(ks.length>1)return ks.map(k=>k+Math.round(m[k]).toLocaleString('en-US')).join(' + ');
  return pCur(p,d)+amtNum(p.amount).toLocaleString('en-US');
}
function izSummaryHTML(d){
  const act=(d.partners||[]).filter(p=>p.active!=0);
  const recip=coHeldWith(d);
  if(d.tier!=='יששכר_זבולון'&&!act.length&&!recip.length)return '';
  const s=izSummary(d),cur=curSym(d);
  // אברך שהוא מחזיק בשותפות, אבל השורה עצמה רשומה אצל השותף. הכסף נספר
  // שם ולכן אין כאן סכום — רק העובדה שהם שותפים, ולחיצה לכרטיס שלו.
  const recipHtml=izLinkedHTML(d,cur);
  const rows=s.parts.map(p=>{const cur=pCur(p,d);const tot=avCoHolders(p).length?coHolderTotal(p):0;const totHtml=(tot>amtNum(p.amount))?` <small class="cosptot">= סה"כ ${coHolderTotalTxt(p,d)}</small>`:'';return `<div class="izrow${avOpenSlot(p)?' izgap':''}"><span>${avOpenSlot(p)
    ?`🚪 מקום פתוח — ${esc(p.prev_avreich)} יצא מהכולל${p.prev_ended?(' ב'+esc(p.prev_ended)):''} <small class="izgaps">חפש אברך חדש למקום הזה</small>`
    :`👨‍🎓 ${esc(p.avreich||'—')}`}${p.method?(' <small>'+chBadgeRaw(p.method)+'</small>'):''}${coHolderNamesHtml(p)}${+p.joint?' <small class="jointbadge">🤝 משותף</small>':''}${totHtml}${p.paid_note?(' <small class="paidnote">💰 '+esc(p.paid_note)+'</small>'):''}${p.start_date?(' <small class="izstart">📅 '+esc(p.start_date)+'</small>'):''}${+p.joint&&jointHolders(p)>1?(' <small class="cosptot">'+(
  String(p.share||'').trim()!==''?('💳 חלקו מתוך '+jointTotalTxt(p,d)+' — לפי החלוקה שנקבעה'
    +(amtNum(p.share)?'':', אינו משלם'))
  :jointPayerId(p)?(jointPayerId(p)===d.id?('💳 אתה משלם את כל ה'+cur+amtNum(p.amount)):('💳 משלם: '+esc(jointPayerName(p))))
  :('חלקו מתוך '+cur+amtNum(p.amount)+' ל־'+jointHolders(p)+' מחזיקים'))+'</small>'):''}</span><b>${cur}${Math.round(partnerMonthly(p))}</b></div>`;}).join('')||'<div class="hintxt">לא הוזנו אברכים</div>';
  let debtLine;
  const thruHtml=s.thru.length?s.thru.map(t=>`<div class="izrow"><span>💵 ${esc(t.av)} — שולם עד ${esc(fmtMonth(t.thru))}${t.months?(' · חסרים '+t.months+' '+(t.months===1?'חודש':'חודשים')):' · מעודכן'}</span><b>${t.owe?(cur+t.owe):'—'}</b></div>`).join(''):'';
  if(s.manual!=null) debtLine=(s.manual>0.5
      ?`<div class="izdebt owe">🔴 חוב שעודכן ידנית: ${cur}${Math.round(s.manual)}</div>`
      :`<div class="izdebt ok">🟢 עודכן ידנית — אין חוב</div>`);
  else if(s.thru.length) debtLine=(s.thruDebt>0.5
      ?`<div class="izdebt owe">🔴 חוב לפי "שולם עד": ${cur}${Math.round(s.thruDebt)}</div>`
      :`<div class="izdebt ok">🟢 מעודכן — אין חוב</div>`);
  else if(false){
    // הכסף נכנס, אבל לא נרשם עבור מה — ולכן הסיכום לא מוצא תשלומים.
    // מראים בדיוק כמה נכנס ומציעים לסמן בלחיצה אחת.
    const un=unclassifiedIz(d);
    debtLine=un.n
      ? `<div class="izunc"><div class="izunc-t">💰 נכנסו ${cur}${Math.round(un.sum)} ב-${un.n} ${un.n===1?'תשלום':'תשלומים'} שעדיין לא נרשם עבור מה</div>
          <div class="izunc-l">${un.rows.slice(0,6).map(x=>`${esc(gregLabel(x.date))} · ${cur}${Math.round(amtNum(x.amount))}${x.method?(' · '+esc(chLabel(x.method))):''}`).join('<br>')}${un.n>6?('<br>ועוד '+(un.n-6)):''}</div>
          <button class="btn sm" id="izclaim">🤝 כן — לסמן הכל כיששכר־זבולון</button>
          <div class="hintxt">אחרי הסימון החוב יחושב לבד.</div></div>`
      : '<div class="hintxt">אין עדיין תשלומי יש"ז רשומים לחישוב חוב. אם הוא משלם במזומן — עדכן "שולם עד חודש" אצל האברך</div>';
  }
  else if(s.debt>0.5) debtLine=`<div class="izdebt owe">🔴 חוב מוערך: ${cur}${Math.round(s.debt)}</div>`;
  else if(s.debt<-0.5) debtLine=`<div class="izdebt ok">🟢 מקדמה / עודף: ${cur}${Math.round(-s.debt)}</div>`;
  else debtLine='';
  if(s.debt<=0.5&&s.manual==null&&!s.thru.length)debtLine='';   // חוב מוצג רק בחלון החוב
  const mainHtml=(act.length||s.monthly)?`${rows}
    <div class="izrow tot"><span>התחייבות חודשית${s.fromCard?' <small class="izfromcard">לפי הסכום הקבוע בכרטיס</small>':''}</span><b>${izMonthlyTxt(s,cur)}</b></div>
    ${s.hasPay?(()=>{
      // רק החלק של יששכר־זבולון. אצל פינטער נכנסים 12,800 בחודש והם
      // מסומנים כולם יששכר־זבולון, בעוד שההתחייבות ליש"ז היא 800 בלבד.
      const al=purposeAlloc(d), izr=al&&al.rows.find(r=>/יששכר/.test(r.what));
      const pd=izr?izr.got:Math.round(s.paid), ex=izr?izr.exp:Math.round(s.expected);
      return `<div class="izrow"><span>שולם ליששכר־זבולון ב-${GREGYEAR} (${s.span} ${s.span===1?'חודש':'חודשים'})</span><b>${cur}${pd}</b></div>
        <div class="izrow"><span>צפוי לתקופה (${s.span}×${cur}${Math.round(s.monthly)})</span><b>${cur}${ex}</b></div>`;})():''}
    ${thruHtml}
    ${debtLine}`:'';
  return `<div class="izsum"><div class="izsum-t">🤝 יששכר־זבולון — סיכום</div>
    ${renewBanner(d)}
    ${mainHtml}
    ${recipHtml}
    ${izHistHTML(d)}
    ${splitHTML(d)}</div>`;
}
// מאיר: "שיהיה היסטוריה בדף היששכר־זבולון של התורם — איזה אברך היה ומתי
// יצא ומי נכנס במקומו". היומן כבר נשמר בדף הקשר תחת הערוץ הזה, ולכן אין
// צורך בפנייה נוספת לשרת — רק בהצגה במקום שבו מאיר מחפש אותה.
function izHistHTML(d){
  const rows=(d.contacts||[]).filter(c=>String(c.channel||'')==='יששכר־זבולון'
    &&String(c.summary||'').trim());
  const past=(d.partners||[]).filter(p=>p.active==0&&String(p.avreich||'').trim());
  if(!rows.length&&!past.length)return '';
  const line=t=>`<div class="izhline">${t}</div>`;
  return `<details class="izhist"><summary>🕘 היסטוריית האברכים (${rows.length+past.length})</summary>
    ${past.map(p=>line(`<b>${esc(p.avreich)}</b> — ${esc(p.start_date||'?')}`
      +` עד ${esc(p.ended_date?gregLabel(p.ended_date):'?')}${p.amount?(' · '+curSym(d)+esc(p.amount)):''}`)).join('')}
    ${rows.slice(0,40).map(c=>line(esc(c.summary))).join('')}</details>`;
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
const TASKKINDS=[['followup','📞 להתקשר אליו'],['email','📧 לשלוח אימייל / וואטסאפ'],['verify','💰 לבדוק שנגבה'],['card','💳 לבדוק כרטיס'],['charge','🧾 לחייב'],['prayer','🙏 לבקש שמות לקוויטל'],['parnes','🌙 פרנס יום'],['cert','📜 תעודת יששכר־זבולון'],['other','🔔 אחר']];
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
// עצירה בטוחה: גם אם המנוע לא מדווח שהוא נגמר, המצב מתאפס אחרי רגע
// אחרת הכפתור נשאר "מקליט" לנצח ואי אפשר להתחיל הקלטה חדשה.
let SRSTOP=null;
function stopDictation(){
  if(SRSTOP){const f=SRSTOP; SRSTOP=null; f(); return;}
  const r=SRACT; if(!r)return;
  try{r.stop();}catch(e){}
  setTimeout(()=>{ if(SRACT===r){ try{r.abort&&r.abort();}catch(e){} SRACT=null; } },1200);
}
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
// הבדיקה מוצגת בתוך החלון ונשארת שם — לא הודעה חולפת שאי אפשר לקרוא
async function runMicDiag(){
  const box=document.getElementById('dictdiagbox'); if(!box)return;
  const g=micDiag();
  box.innerHTML='<div class="dgbox"><div class="hintxt">בודק…</div></div>';
  let perm='לא ידוע';
  try{ const st=await navigator.permissions.query({name:'microphone'});
    perm={granted:'✅ מאושר',denied:'❌ נחסם',prompt:'❓ עדיין לא נשאלת'}[st.state]||st.state; }catch(e){}
  let mic='לא נבדק';
  try{ const st=await navigator.mediaDevices.getUserMedia({audio:true});
    st.getTracks().forEach(t=>t.stop()); mic='✅ המיקרופון נפתח'; }
  catch(e){ mic='❌ '+((e&&e.name)||'נכשל'); }
  const line=(k,v)=>`<div class="dgrow"><span>${k}</span><b>${v}</b></div>`;
  const advice = !g.api ? 'הדפדפן הזה לא כולל מנוע הכתבה. פתח בכרום.'
    : mic.indexOf('❌')===0||perm==='❌ נחסם' ? 'המיקרופון חסום לאתר. פתח את הגדרות האתר בדפדפן ואשר מיקרופון.'
    : g.pwa ? 'זו האפליקציה שהתקנת למסך הבית — באנדרואיד ההכתבה שלה לרוב חסומה. פתח את המערכת בכרום רגיל.'
    : 'הכל נראה תקין מהצד שלנו. ייתכן שאין חיבור לשרת ההכתבה של גוגל, או שאפליקציה אחרת תופסת את המיקרופון.';
  box.innerHTML=`<div class="dgbox">
    ${line('מנוע ההכתבה בדפדפן', g.api?'✅ קיים':'❌ חסר')}
    ${line('חיבור מאובטח', g.secure?'✅':'❌')}
    ${line('הרשאת מיקרופון', perm)}
    ${line('פתיחת מיקרופון בפועל', mic)}
    ${line('מכשיר', g.ua)}
    ${line('אפליקציה מותקנת', g.pwa?'⚠️ כן':'לא (דפדפן רגיל)')}
    <div class="hintxt" style="margin-top:6px"><b>${advice}</b></div>
    <div class="hintxt">בכל מקרה — הקש על תיבת הטקסט ואז על 🎤 שבמקלדת. זה עובד תמיד.</div></div>`;
}
function micDiag(){
  const C=window.SpeechRecognition||window.webkitSpeechRecognition||null;
  const pwa=window.matchMedia&&window.matchMedia('(display-mode: standalone)').matches;
  return {api:!!C, pwa:!!pwa, secure:window.isSecureContext!==false,
          md:!!(navigator.mediaDevices&&navigator.mediaDevices.getUserMedia),
          ua:/Android/i.test(navigator.userAgent)?'Android':(/iPhone|iPad/i.test(navigator.userAgent)?'iOS':'מחשב')};
}
// באנדרואיד המנוע לא באמת תומך בהאזנה רציפה: הוא נסגר אחרי כל משפט, ואם
// מבקשים ממנו continuous הוא לפעמים לא מחזיר כלום בכלל. לכן שם עובדים
// במקטעים — כל משפט בנפרד, והמערכת מפעילה אותו שוב מיד, עד שלוחצים עצור.
function startDictation(btn,el){
  const C=window.SpeechRecognition||window.webkitSpeechRecognition||null;
  if(!C){toast('הדפדפן הזה לא תומך בהכתבה קולית — נסה בכרום');return;}
  if(SRACT){stopDictation();return;}                       // לחיצה שנייה עוצרת
  const ANDROID=/Android/i.test(navigator.userAgent);
  const setv=v=>{el.value=v;el.dispatchEvent(new Event('input',{bubbles:true}));};
  const base=(el.value||'').trim()?((el.value||'').trim()+' '):'';
  let done='', userStop=false, gotAny=false, rounds=0, cur=null;
  const paint=live=>setv((base+joinSegs([done,live||''])).replace(/\s+/g,' ').trim());
  const finish=()=>{
    if(finish._d)return; finish._d=1;
    SRACT=null; btn.classList.remove('rec'); btn.textContent='🎤';
    const fixed=fixNames((base+done).replace(/\s+/g,' ').trim());
    setv(fixed.text);
    if(fixed.hits.length)toast('תוקנו שמות: '+fixed.hits.join(', '));
    if(!gotAny){
      toast('לא נקלט דיבור — הנה מה שנמצא',5000);
      try{ runMicDiag(); }catch(e){}      // ההסבר נשאר על המסך, לא חולף
    }
    el.dispatchEvent(new Event('change',{bubbles:true}));
    try{el.focus();}catch(e){}
  };
  const round=()=>{
    if(userStop){finish();return;}
    if(++rounds>60){finish();return;}
    const r=new C(); cur=r; SRACT=r;
    r.lang='he-IL'; r.interimResults=true; r.continuous=!ANDROID;
    let seg=[];
    r.onstart=()=>{btn.classList.add('rec');btn.textContent='⏹';
      if(rounds===1)toast('🎤 מקליט — דבר בעברית. לחץ שוב לסיום');};
    r.onspeechstart=()=>{gotAny=true;};
    r.onresult=ev=>{ gotAny=true;
      for(let i=0;i<ev.results.length;i++)seg[i]=ev.results[i][0].transcript;
      paint(joinSegs(seg)); };
    r.onerror=ev=>{
      if(ev.error==='no-speech'||ev.error==='aborted')return;      // רגיל — נמשיך בסבב הבא
      const m=SRERR[ev.error];
      if(m||ev.error){toast(m||('הכתבה נכשלה: '+ev.error)); userStop=true;}
    };
    r.onend=()=>{
      const t=joinSegs(seg);
      if(t)done=joinSegs([done,t]);
      paint('');
      if(userStop)finish(); else setTimeout(round,120);           // מפעילים שוב מיד
    };
    try{ r.start(); }
    catch(e){ setTimeout(()=>{try{r.start();}catch(e2){userStop=true;finish();}},250); }
  };
  round();
  SRSTOP=()=>{ userStop=true; try{cur&&cur.stop();}catch(e){} setTimeout(finish,900); };
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
// ----- עדכון גרסה: אפליקציה שנשארת פתוחה ברקע לא טוענת מחדש את הקוד,
// ולכן תיקון שעלה לשרת לא מגיע עד שסוגרים ופותחים. כאן בודקים את הגרסה
// בכל חזרה למסך, ומרעננים לבד כשאין מה לאבד -----
let _VER=null;
async function liveVer(){
  try{
    const t=await (await fetch('/sw.js',{cache:'no-store'})).text();
    const m=/kc-crm-(v\d+)/.exec(t); return m?m[1]:null;
  }catch(e){ return null; }
}
function verBanner(v){
  if(document.getElementById('verbar'))return;
  const b=document.createElement('button');
  b.id='verbar'; b.textContent='🔄 יש גרסה חדשה ('+v+') — לחץ לעדכון';
  b.onclick=()=>location.reload();
  document.body.appendChild(b);
}
async function verCheck(){
  const v=await liveVer(); if(!v)return;
  if(!_VER){_VER=v;return;}
  if(v===_VER)return;
  const busy=document.querySelector('.ov.show,.confirmov')
    ||/^(INPUT|TEXTAREA|SELECT)$/.test((document.activeElement||{}).tagName||'')
    ||(document.activeElement&&document.activeElement.isContentEditable);
  if(busy){ verBanner(v); return; }
  _VER=v; location.reload();
}
document.addEventListener('visibilitychange',()=>{ if(!document.hidden)verCheck(); });
setInterval(verCheck, 4*60*1000);
verCheck();

async function openHealth(){
  const ov=document.getElementById('dictov'), sh=document.getElementById('dictsheet');
  sh.innerHTML='<button class="x" id="hx">✕</button><h2>🩺 בדיקת מערכת</h2><div class="hintxt">בודק…</div>';
  ov.classList.add('show');
  document.getElementById('hx').onclick=()=>ov.classList.remove('show');
  const h=await api('GET','/api/health');
  if(!h||!h.rows){sh.innerHTML='<button class="x" id="hx2">✕</button><h2>🩺 בדיקת מערכת</h2><div class="hintxt">השרת לא החזיר תשובה</div>';
    document.getElementById('hx2').onclick=()=>ov.classList.remove('show');return;}
  const ic={ok:'✅',warn:'⚠️',bad:'❌'};
  // גרסת הקבצים שהדפדפן באמת מחזיק — כדי לדעת אם הרענון תפס
  const showVer=()=>{const e=document.getElementById('appver'); if(!e)return;
    fetch('/sw.js',{cache:'no-store'}).then(r=>r.text()).then(t=>{
      const m=/kc-crm-(v\d+)/.exec(t)||[]; const live=m[1]||'?';
      caches.keys().then(ks=>{
        const mine=(ks.find(k=>/kc-crm-v\d+/.test(k))||'').replace('kc-crm-','')||'?';
        e.textContent=mine+(live&&mine!==live?(' · בשרת כבר '+live+' — סגור ופתח את האפליקציה'):' ✓ מעודכן');
      }).catch(()=>{e.textContent='בשרת: '+live;});
    }).catch(()=>{e.textContent='לא זמין';});};
  sh.innerHTML=`<button class="x" id="hx3">✕</button><h2>🩺 בדיקת מערכת</h2>
    <div class="hintxt">📱 גרסת האפליקציה אצלך: <b id="appver">בודק…</b></div>
    <div class="hintxt">${esc(h.when)} · ${h.bad?('❌ '+h.bad+' תקלות'):'✅ אין תקלות'}${h.warn?(' · ⚠️ '+h.warn+' לתשומת לב'):''}</div>
    ${h.rows.map(r=>`<div class="hrow ${r.state}"><span class="hi">${ic[r.state]||''}</span>
      <span class="hn"><b>${esc(r.name)}</b><small>${esc(r.detail)}</small></span></div>`).join('')}
    <button class="btn" id="hagain" style="width:100%;margin-top:10px">🔄 בדוק שוב</button>
    <a class="btn" id="hbackup" href="/api/backup" download style="width:100%;margin-top:8px;display:block;text-align:center;text-decoration:none">💾 גיבוי מלא — לשמור אצלך</a>
    <div class="hintxt">כל הנתונים כולל התעודות והקבצים (כ-34MB). שמור אותו מדי פעם — זה הביטוח שלך.</div>
    <a class="btn" id="hbacklite" href="/api/backup?light=1" download style="width:100%;margin-top:8px;display:block;text-align:center;text-decoration:none;background:var(--yes)">📤 קובץ קטן — לשלוח לקלוד</a>
    <div class="hintxt">אותם נתונים בדיוק בלי גוף הקבצים — כ-200KB בלבד, נשלח בקלות בצ׳אט.</div>`;
  document.getElementById('hx3').onclick=()=>ov.classList.remove('show');
  showVer();
  document.getElementById('hagain').onclick=openHealth;
  const hb=document.getElementById('hbackup');
  if(hb)hb.onclick=()=>toast('מכין גיבוי מלא… ההורדה תתחיל בעוד רגע');
  const hl=document.getElementById('hbacklite');
  if(hl)hl.onclick=()=>toast('מכין קובץ קטן לשליחה…');
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
    <div class="micalt">🎤 <b>לא עובד?</b> הקש על תיבת הטקסט ואז על המיקרופון שבמקלדת — זה עובד תמיד, בכל מכשיר.</div>
    <textarea id="dictpad" class="dictpad" placeholder="כאן ייכתב מה שתאמר…"></textarea>
    <button class="btn dictbig" id="dictgo">🎤 התחל להקליט</button>
    <button class="btn dictbig" id="dictsend" style="background:var(--yes)">📋 העתק להדבקה בצ׳אט</button>
    <label class="jointchk" style="margin-top:8px"><input type="checkbox" id="dictauto" ${auto?'checked':''}> להעתיק אוטומטית ברגע שמסיימים להקליט</label>
    <div class="dictbar">
      <button class="btn sm ghost" id="dictshare">📤 שיתוף לאפליקציה אחרת</button>
      <button class="btn sm ghost" id="dictadd">➕ שורה חדשה</button>
      <button class="btn sm ghost" id="dictclr">🗑 נקה</button>
      <button class="btn sm ghost" id="dictdiag">🩺 בדיקת מיקרופון</button></div>
    <div id="dictdiagbox"></div>
    ${h.length?`<div class="dicthist"><div class="hintxt">הכתבות אחרונות — לחץ לשלוח שוב</div>
      ${h.map((x,i)=>`<div class="dh"><span>${esc(x.t.slice(0,220))}${x.t.length>220?'…':''}</span>
        <button class="btn sm dhsend" data-i="${i}">📋</button><button class="del dhdel" data-i="${i}">🗑</button></div>`).join('')}</div>`:''}`;
  ov.classList.add('show');
  const pad=document.getElementById('dictpad'), go=document.getElementById('dictgo'),
        snd=document.getElementById('dictsend'), au=document.getElementById('dictauto');
  const closePad=()=>{try{stopDictation();}catch(e){}
    SRACT=null; ov.classList.remove('show');
    const f=document.getElementById('dictfab'); if(f)f.classList.remove('rec');};
  document.getElementById('dictx').onclick=closePad;
  ov.onclick=e=>{if(e.target===ov)closePad();};      // לחיצה מחוץ לחלון סוגרת
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
  // בדיקה שמראה בדיוק מה חוסם את ההכתבה, במקום לנחש
  document.getElementById('dictdiag').onclick=()=>runMicDiag();
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
// חותמת זמן לפי השעון של המכשיר — 'YYYY-MM-DD HH:MM'. השרת רץ בשעון אחר,
// ולכן שעת הביצוע נקבעת כאן ונשלחת אליו.
function nowStamp(){const d=new Date(),z=n=>String(n).padStart(2,'0');
  return d.getFullYear()+'-'+z(d.getMonth()+1)+'-'+z(d.getDate())+' '+z(d.getHours())+':'+z(d.getMinutes());}
const hhmm=s=>{const m=/\d{4}-\d{2}-\d{2}[ T](\d{2}:\d{2})/.exec(s||'');return m?m[1]:'';};
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
// סימון וי על משימה. השרת רושם את זה גם בדף הקשר של התורם — מה נעשה, באיזה
// תאריך, ובידי מי. ביטול הווי מוחק את אותה שורה. כל מקום שבו יש וי עובר כאן,
// כדי שהתיעוד ייווצר בין אם סימנו מהתזכורות, מהכרטיס, או מרשימת המשימות.
async function setTaskDone(t,v,dref){
  const on=v?1:0, at=nowStamp();
  let r=null;
  if(t.id)r=await api('PUT','/api/task/'+t.id,{done:on,done_by:whoName(t),done_at:at});
  const stamp=x=>{x.done=on;x.done_by=on?whoName(t):'';x.done_at=on?at:'';x.done_date=on?at.slice(0,10):'';};
  stamp(t);
  const g=GTASKS.find(x=>x.id===t.id);if(g)stamp(g);
  const d=dref||t.dref||DB.find(x=>x.id===t.donor_id);
  if(d){
    const lt=(d.tasks||[]).find(x=>x.id===t.id);if(lt)stamp(lt);
    d.contacts=d.contacts||[];
    if(!on)d.contacts=d.contacts.filter(c=>c.task_id!=t.id);
    if(on&&r&&r.contact)d.contacts.unshift(r.contact);
    if(CURD&&CURD.id===d.id&&document.getElementById('clog'))renderContacts(d);
  }
  return r;
}
// עריכת משימה שכבר בוצעה — השרת מחזיר את הרישום המעודכן, ומחליפים אותו במקום
function putLog(d,c){
  if(!d||!c)return;
  d.contacts=d.contacts||[];
  const ix=d.contacts.findIndex(x=>x.id===c.id);
  if(ix>=0)d.contacts[ix]=c; else d.contacts.unshift(c);
  if(CURD&&CURD.id===d.id&&document.getElementById('clog'))renderContacts(d);
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
    <div class="hintxt">לחיצה על שם התורם פותחת את הכרטיס שלו.</div>
    ${due.map((t,i)=>`<div class="remitem over"><div class="ri"><b>${esc(kindLabel(t.kind))} ${t.dref?`<a class="remname" data-i="${i}">${esc(t.donor)} ↗</a>`:esc(t.donor)}</b><br><small>${esc(t.due_date)} ${esc(t.note||'')}</small><br>${whoChipHTML(t,'data-rwho="'+t.id+'"')}</div>
      <button class="btn sm rdone" data-i="${i}">בוצע ✓</button><button class="no rsnooze" data-i="${i}">דחה מחר</button></div>`).join('')}`;
  remov.classList.add('show');
  document.getElementById('rx').onclick=()=>remov.classList.remove('show');
  // שם התורם פותח את הכרטיס שלו — כדי לטפל בתזכורת מול כל המידע שלפניך
  rs.querySelectorAll('.remname').forEach(a=>a.onclick=e=>{e.stopPropagation();
    const t=due[a.dataset.i]; if(!t.dref)return;
    remov.classList.remove('show'); openDonor(t.dref);});
  rs.querySelectorAll('[data-rwho]').forEach(b=>b.onclick=async e=>{e.stopPropagation();b.disabled=true;await flipWho(b.dataset.rwho);openRemPopup();render();});
  rs.querySelectorAll('.rdone').forEach(b=>b.onclick=async()=>{const t=due[b.dataset.i];await setTaskDone(t,1,t.dref);checkReminders();openRemPopup();render();toast('בוצע ✓ · נרשם בכרטיס');});
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
// שאלה עם תשובה בכתב — למשל התאריך העברי שבו אברך יצא מהכולל.
// מחזיר null כשמבטלים, כדי להבדיל בין ביטול לבין תשובה ריקה.
function uiPrompt(msg,def){
  return new Promise(res=>{
    const o=document.createElement('div');o.className='confirmov';
    o.innerHTML=`<div class="confirmbox"><div class="cm">${esc(msg)}</div>
      <input class="cinp" value="${esc(def||'')}">
      <div class="cbtns"><button class="btn ghost cno">ביטול</button><button class="btn cyes">אישור</button></div></div>`;
    document.body.appendChild(o);
    const inp=o.querySelector('.cinp');
    const done=v=>{o.remove();res(v);};
    o.querySelector('.cno').onclick=()=>done(null);
    o.querySelector('.cyes').onclick=()=>done(inp.value.trim());
    inp.onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();done(inp.value.trim());}};
    o.onclick=e=>{if(e.target===o)done(null);};
    setTimeout(()=>{inp.focus();inp.select();},30);
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
/* מאיר: "כשאני משבץ לאברך את התורם אמור להיות לוח שנה שאבחר מאיזה תאריך".
   תאריך עברי בשלוש בחירות — יום, חודש, שנה — במקום הקלדה חופשית. הפורמט
   שנשמר הוא בדיוק אותו פורמט שכבר קיים בשדות: א' אייר תשפ"ו */
const HEDAYS=[...Array(30)].map((_,i)=>heDay(i+1));
// כתיב מלא וחסר מעורבים בנתונים — "כסליו"/"כסלו", "סיוון"/"סיון". משמיטים
// אימות קריאה כדי ששתי הצורות יזוהו כאותו חודש.
const _hm=x=>String(x||'').replace(/[וי]/g,'');
function parseHeDate(s){
  s=String(s||'').replace(/[״"]/g,'"').replace(/\s+/g,' ').trim();
  const body=_hm(s.split(' ').slice(1).join(' '));
  const mo=HMORD.slice().sort((a,b)=>_hm(b).length-_hm(a).length)
    .find(m=>_hm(m)&&body.indexOf(_hm(m))>=0)||'';
  const yr=(s.match(/תש[^\s]*\s*$/)||[''])[0].trim();
  const day=HEDAYS.find(d=>s.indexOf(d+' ')===0)||'';
  return {day,mo,yr};
}
function hebDateSel(cls,val){
  const p=parseHeDate(val);
  return `<div class="hedate ${cls}">
    <select class="hd_d">${HEDAYS.map(d=>`<option ${d===p.day?'selected':''}>${d}</option>`).join('')}</select>
    <select class="hd_m">${HMORD.map(m=>`<option ${m===p.mo?'selected':''}>${m}</option>`).join('')}</select>
    <select class="hd_y">${heYearOpts(p.yr||HEBYEAR)}</select></div>`;
}
function hebDateGet(el){
  if(!el)return '';
  const g=c=>{const x=el.querySelector(c);return x?x.value:'';};
  return [g('.hd_d'),g('.hd_m'),g('.hd_y')].filter(Boolean).join(' ');
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
// דרך תשלום שמאיר הוסיף בעצמו — מקבלת עיצוב אחיד ומוצגת ככל השאר
function chCfg(ch){ch=(ch||'').trim();
  return CHANNELS[ch]||CHANNELS[CHALIAS[ch]]||CHEXTRA[ch]
    ||((CHAN_C||[]).includes(ch)?{i:'💰',l:ch,c:'#5b5470'}:null);}
function chBadgeRaw(ch){const cfg=chCfg(ch);if(!cfg)return '';return `<span class="chbadge" style="background:${cfg.c}" title="${esc(cfg.l)}">${cfg.i} ${esc(cfg.l)}</span>`;}
function chLabel(ch){const cfg=chCfg(ch);return cfg?cfg.l:(ch||'');}
function channelBadge(d){return chBadgeRaw(d.channel);}
function channelOpts(cur){cur=(cur||'').trim();
  if(cur==='__new__')cur='';                 // ערך שנשמר בטעות ע"י הכפתור הישן
  let o='<option value="">— ללא —</option>';
  CHAN_ORDER.forEach(k=>{o+=`<option value="${k}" ${k===cur?'selected':''}>${CHANNELS[k].i} ${CHANNELS[k].l}</option>`;});
  (CHAN_C||[]).forEach(k=>{o+=`<option value="${esc(k)}" ${k===cur?'selected':''}>💰 ${esc(k)}</option>`;});
  if(cur&&!CHANNELS[cur]&&!(CHAN_C||[]).includes(cur))o+=`<option value="${esc(cur)}" selected>${esc(cur)}</option>`;
  return o+'<option value="__new__">➕ דרך תשלום חדשה…</option>';}
// הוספת דרך תשלום מתוך תיבת הבחירה עצמה — נשמרת ומופיעה מכאן והלאה בכל מקום
function wireChanSel(sel){
  if(!sel||sel._cbox)return;
  const box=document.createElement('div'); box.className='chanbox';
  box.innerHTML='<input class="channew" placeholder="שם דרך התשלום (למשל: קופת גמ&quot;ח)" style="display:none">'
    +'<button type="button" class="btn sm chandel" title="מחק דרך זו" style="display:none">🗑</button>';
  (sel.closest('.fld')||sel).parentNode.insertBefore(box,(sel.closest('.fld')||sel).nextSibling);
  sel._cbox=box;
  const inp=box.querySelector('.channew'), del=box.querySelector('.chandel');
  const refresh=()=>{const v=sel.value;document.querySelectorAll('select#f_channel,select.chansel')
    .forEach(s=>{const c=s===sel?v:s.value;s.innerHTML=channelOpts(c);});};
  const showDel=()=>{del.style.display=(CHAN_C||[]).includes(sel.value)?'':'none';};
  sel.addEventListener('change',()=>{
    if(sel.value==='__new__'){inp.style.display='';inp.focus();del.style.display='none';return;}
    inp.style.display='none';showDel();});
  const add=async()=>{const nm=inp.value.trim(); if(!nm){inp.focus();return;}
    if(!(CHAN_C||[]).includes(nm)){const r=await api('POST','/api/paychannels',{name:nm});CHAN_C=(r&&r.channels)||CHAN_C.concat([nm]);}
    inp.value='';inp.style.display='none';sel.value=nm;refresh();sel.value=nm;showDel();toast('נוספה דרך תשלום ✓');};
  inp.onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();add();}};
  // יציאה מהשדה: שם שנכתב נשמר, שדה ריק פשוט נסגר. אחרי הוספה מוצלחת
  // השדה כבר מוסתר — ואסור שהיציאה ממנו תאפס את הבחירה החדשה.
  inp.onblur=()=>{if(inp.style.display==='none')return;
    if(inp.value.trim())add(); else{inp.style.display='none'; if(sel.value==='__new__')sel.value='';}};
  del.onclick=async()=>{const nm=sel.value; if(!nm||!(CHAN_C||[]).includes(nm))return;
    if(!await uiConfirm('למחוק את דרך התשלום "'+nm+'" מהרשימה?\nתורמים שכבר סומנו בה יישארו כפי שהם.'))return;
    const r=await api('POST','/api/paychannels',{name:nm,delete:1});CHAN_C=(r&&r.channels)||CHAN_C.filter(x=>x!==nm);
    sel.value='';refresh();showDel();toast('נמחקה');};
  showDel();
}
// כל תיבת "דרך תשלום" בדף — גם כאלו שנוצרו הרגע ברענון של חלון — מקבלת
// את שדה ההוספה. מאיר: "אי אפשר כאן להוסיף דרך חדשה איך שהוא נותן"; קודם
// זה עבד רק בתיבה שבפרטי הכרטיס, ולא בחלון היששכר־זבולון.
async function addPayChannel(sel,prev){
  const nm=((await uiPrompt('שם דרך התשלום החדשה — למשל: בנק ישראלי','')) ||'').trim();
  if(!nm){sel.value=prev;return;}
  if(!(CHAN_C||[]).includes(nm)){
    const r=await api('POST','/api/paychannels',{name:nm});
    CHAN_C=(r&&r.channels)||(CHAN_C||[]).concat([nm]);
  }
  // כל תיבות הבחירה בדף מקבלות את הדרך החדשה, וזו שנלחצה נבחרת בה
  document.querySelectorAll('select.chansel').forEach(x=>{
    const c=(x===sel)?nm:x.value; x.innerHTML=channelOpts(c); x.value=c;});
  sel.value=nm; sel.dispatchEvent(new Event('change',{bubbles:true}));
  toast('נוספה דרך תשלום ✓');
}
// מאזין אחד לכל הדף: שורד כל רענון של חלון, ולא תלוי בשדה מוזרק.
// תיבת "ערוץ חיוב" שבפרטי הכרטיס ממשיכה בדרך הישנה (יש לה גם מחיקה).
document.addEventListener('change',e=>{
  const sel=e.target;
  if(!sel||!sel.matches||!sel.matches('select.chansel'))return;
  if(sel.id==='f_channel'||sel._cbox)return;
  if(sel.value!=='__new__')return;
  addPayChannel(sel,sel._prevch||'');
},true);
document.addEventListener('focus',e=>{
  const sel=e.target;
  if(sel&&sel.matches&&sel.matches('select.chansel'))sel._prevch=sel.value;
},true);

// הסכום הקבוע (חודשי) — לתורם קבוע לפי השדה, וליששכר־זבולון סכום האברכים הפעילים
// מה התורם נתן מתחילת השנה הלועזית ועד היום — מוצג בשורה ברשימת התורמים,
// כדי שגם מי שאינו "קבוע" יראה מיד כמה הוא כבר תרם השנה (מאיר).
function yearAmt(d){
  const t=donorTotals(d);
  return t.year>0 ? (curSym(d)+Math.round(t.year).toLocaleString('en-US')) : '';
}
function fixedAmt(d){
  // הסכום החודשי האמיתי: הקבוע המפוצל לייעודים ואברכי יששכר־זבולון,
  // כשייעוד יששכר־זבולון נספר פעם אחת ולא פעמיים
  const fx=monthlyTotal(d);
  if(fx)return curSym(d)+Math.round(fx);
  if(d.tier==='יששכר_זבולון'){
    const m={};(d.partners||[]).filter(p=>p.active!=0).forEach(p=>{const c=pCur(p,d);m[c]=(m[c]||0)+amtNum(p.amount);});
    const ks=Object.keys(m).filter(k=>m[k]>0);
    if(ks.length)return ks.map(k=>k+m[k].toLocaleString('en-US')).join(' + ');
  }
  if(d.category==='קבוע'&&amtNum(d.amount))return curSym(d)+amtNum(d.amount);
  return '';}
// חיפוש חופשי: כל מילה בשאילתה חייבת להופיע — בלי תלות בסדר,
// כך ש"אפרים מיטמן" ו"מיטמן אפרים" מוצאים אותו דבר. אם לא נמצא,
// מנסים שוב לפי צליל בעברית, כדי לתפוס איות שונה.
// חיפוש חופשי: כל סדר של מילים, וגם איות קרוב. משמש גם בתורמים וגם באברכים
function matchStr(s,query){
  if(!query)return true;
  const h=norm(s).toLowerCase(), toks=norm(query).toLowerCase().split(' ').filter(Boolean);
  if(!toks.length)return true;
  if(toks.every(t=>h.indexOf(t)>=0))return true;
  const hf=fzHe(h);
  return hf&&toks.every(t=>{const f=fzHe(t);return f.length>=3&&hf.indexOf(f)>=0;});
}
function matchQ(s){return matchStr(s,q);}

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
// משיכת תשלומי PayPal מהמייל — הודעות "קיבלת תשלום", כולל תיקיית הספאם
async function runPaypalSync(btn){
  const label=btn?btn.textContent:'';
  const set=t=>{if(btn)btn.textContent=t;};
  if(btn)btn.disabled=true; set('מתחיל…');
  const r=await api('POST','/api/mail/paypal_sync',{});
  if(!r||!r.ok){
    if(btn){btn.disabled=false;set(label);}
    toast(r&&r.error==='not_configured'?'המייל לא מוגדר בשרת (GMAIL_USER / GMAIL_APP_PASSWORD)':'שגיאה: '+((r&&(r.detail||r.error))||''));
    return;
  }
  for(let i=0;i<900;i++){
    await new Promise(res=>setTimeout(res,2000));
    let st;try{st=await api('GET','/api/mail/paypal_sync/status');}catch(e){continue;}
    if(!st)continue;
    if(st.running){set((st.phase?st.phase+' — ':'')+(st.total?('קורא… '+(st.done||st.new||0)+'/'+st.total):'סורק את המייל…'));continue;}
    if(btn){btn.disabled=false;set(label);}
    if(st.error){toast('שגיאת משיכה: '+st.error);return;}
    LEDGER=null; await load();
    toast(st.new?('נקלטו '+st.new+' תשלומים וקבלות ✓'+(st.dup?(' · '+st.dup+' כבר היו'):'')):'אין תשלומים חדשים במייל');
    render();return;
  }
  if(btn){btn.disabled=false;set(label);}
  toast('המשיכה עדיין רצה ברקע — בדוק שוב בעוד כמה דקות');
}
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
// חתימת הנתונים האחרונים. אם השרת עונה "לא השתנה כלום" — לא מורידים שוב
// מגה של נתונים ולא מפענחים אותם מחדש, וזה חוסך את רוב זמן ההמתנה.
let _ETAG='', _LASTDATA=null;
async function load(){
  let d;
  try{
    const h={};
    if(_ETAG&&_LASTDATA)h['If-None-Match']=_ETAG;
    const r=await fetch('/api/data',{headers:h});
    if(r.status===304&&_LASTDATA){ d=_LASTDATA; }
    else { d=await r.json(); _LASTDATA=d; _ETAG=r.headers.get('ETag')||''; }
  }catch(e){ d = await api('GET','/api/data'); }
  DB = d.donors; UNLINKED = d.unlinked_prayers || []; GTASKS = d.general_tasks || []; CAMPAIGNS = d.campaigns || []; BUILDING_ITEMS = d.building_items || []; TASKKINDS_C = d.task_kinds || []; CHAN_C = d.pay_channels || []; CLK_C = d.contact_kinds || []; _NMIDX = null; HEBYEAR = hq(d.heb_year) || ''; HEBTODAY = hq(d.heb_today) || '';
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

document.querySelectorAll('.tab').forEach(b=>b.onclick=()=>{tab=b.dataset.tab;DLIM=60;document.querySelectorAll('.tab').forEach(x=>x.classList.toggle('on',x===b));flt='';plaque=null;pyMonth=null;pyDay=null;pyKind='parnes';kvSub=null;try{localStorage.setItem('kc_tab',tab);localStorage.removeItem('kc_donor');}catch(e){}render();});
document.getElementById('q').oninput=e=>{q=e.target.value.trim();DLIM=60;render();};
ov.onclick=e=>{if(e.target===ov){ov.classList.remove('show');try{localStorage.removeItem('kc_donor');}catch(e){}
  if(typeof restoreScroll==='function')restoreScroll();}};
document.getElementById('remov').onclick=e=>{if(e.target.id==='remov')e.currentTarget.classList.remove('show');};

function render(){
  chips.innerHTML='';
  if(tab==='donors'){
    if(flt==='addrfix')return renderAddrFix();
    if(flt==='noaddr')return renderNoAddr();
    if(flt==='noeng')return renderNoEng();
    if(flt==='nophone')return renderNoPhone();
    if(flt==='deposits')return renderDeposits();
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
  if(tab==='old') return renderOld();
  if(tab==='dups') return renderDups();
  if(tab==='unlinked') return renderUnlinked();
  if(tab==='review') return renderReview();
}

/* ---------- תורמים ---------- */
function amtNum(a){const n=parseFloat(String(a||'').replace(/[^0-9.]/g,''));return isNaN(n)?0:n;}
// כמו amtNum אבל שומר על מינוס — ליתרת פתיחה של תורם ששילם מראש
function amtSigned(a){const t=String(a==null?'':a).trim();
  return /^[-–—−]/.test(t)?-amtNum(t):amtNum(t);}
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
let FIXOPEN=false;      // האם חלון "בדיקות ותיקונים" פתוח — נשמר בין ציורים
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
let DLIM = 60;      // כמה שורות תורמים מוצגות עכשיו; גדל מאליו בגלילה
// כשמגיעים לתחתית הרשימה מוסיפים עוד חבילה, בלי כפתור ובלי המתנה
function wireMoreDonors(list){
  const el=document.getElementById('moredon'); if(!el)return;
  const grow=()=>{DLIM+=60;renderDonors();};
  try{
    const io2=new IntersectionObserver(es=>{if(es.some(e=>e.isIntersecting)){io2.disconnect();grow();}},
      {rootMargin:'400px'});
    io2.observe(el);
  }catch(e){ el.onclick=grow; }
  el.onclick=grow;
}
function renderDonors(){
  chips.innerHTML=DFORDER.map(k=>{const cnt=DB.filter(DFILTERS[k].fn).length;return `<button class="chip ${flt===k?'on':''}" data-k="${k}">${DFILTERS[k].label} <b>${cnt}</b></button>`;}).join('');
  chips.querySelectorAll('.chip').forEach(c=>c.onclick=()=>{flt=c.dataset.k;DLIM=60;render();});
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
    ${(()=>{
      const nph=DB.filter(d=>!(d.phone||'').trim()).length;
      const items=[
        {id:'dupBtn',   n:ndup,   t:'🔀 כרטיסים כפולים למיזוג'},
        {id:'addrFixBtn',n:nafix, t:'🏠 כתובות לתיקון'},
        {id:'noAddrBtn', n:nanone,t:'🏠 בלי כתובת בכלל'},
        {id:'noPhoneBtn',n:nph,   t:'📞 בלי טלפון'},
        {id:'noEngBtn',  n:DB.filter(d=>!(d.english||'').trim()).length, t:'🔤 בלי שם באנגלית'},
      ].filter(x=>x.n);
      // מאיר: "כל אלו יהיו תחת חלון אחד, לא בדף הראשי משבצת לכל אחד"
      const tabs=[{k:'review',t:'📋 לבדיקה'},{k:'dups',t:'🧾 תשלומים כפולים'},
                  {k:'unlinked',t:'💳 חיובים בלי תורם'},{k:'old',t:'🧹 תורמים ישנים'},
                  {k:'mails',t:'📧 מיילים'}];
      const tot=items.reduce((a,x)=>a+x.n,0);
      return `<details class="fixbox"${FIXOPEN?' open':''} id="fixbox">
        <summary>🧰 בדיקות ותיקונים${tot?` <b class="fixcnt">${tot}</b>`:''}</summary>
        ${items.map(x=>`<button class="btn fixrow" id="${x.id}">${x.t}<b>${x.n}</b></button>`).join('')}
        ${tabs.map(x=>`<button class="btn fixrow fixtab" data-t="${x.k}">${x.t}</button>`).join('')}
      </details>`;
    })()}
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
    <div class="cnt">${list.length} תורמים</div><div class="list" id="donlist">${list.slice(0,DLIM).map(d=>`
    <div class="rowc" data-id="${d.id}">
      <div><div class="nm">${esc(d.last)} <small>${esc(d.first)}</small><span class="rownum">#${d.id}</span>${fixedAmt(d)?`<span class="fixamt">💵 ${esc(fixedAmt(d))} קבוע</span>`:''}${yearAmt(d)?`<span class="yramt" title="מתחילת ${GREGYEAR} ועד היום · סך הכל אי פעם: ${esc(curSym(d)+Math.round(donorTotals(d).all).toLocaleString('en-US'))}">💰 תרם השנה <bdi>${esc(yearAmt(d))}</bdi></span>`:''}</div>
      ${d.english?`<div class="en" dir="ltr">${esc(d.english)}</div>`:''}
      ${d.purpose?`<div class="purp">🎯 ${esc(d.purpose)}</div>`:''}
      ${d.notes?`<div class="dnote">📝 ${esc(String(d.notes).replace(/\s+/g,' ').slice(0,90))}</div>`:''}
      ${d.created?`<div class="newp">🆕 נוסף ${esc(d.created)}${d.source?(' · '+esc(d.source)):''}</div>`:''}</div>
      <div class="meta">${unthankedCount(d)?`<span class="pill thx">🙏 ${unthankedCount(d)}</span>`:''}${hasOpenParnes(d)?'<span class="pill py">🌙</span>':''}${channelBadge(d)}${catPill(d.category)}${freqLabel(d.frequency)?`<span class="pill freq">🔁 ${freqLabel(d.frequency)}</span>`:''}${pill(d.tier)}${d.phone?`<span class="ph">${esc(d.phone)}</span>`:''}</div>
    </div>`).join('')||'<div class="empty">אין תוצאות</div>'}</div>
    ${list.length>DLIM?`<div class="moredon" id="moredon">מציג ${DLIM} מתוך ${list.length} — גלול להמשך…</div>`:''}`;
  wireMoreDonors(list);
  const ds=document.getElementById('donsort'); if(ds){ds.value=donSort;ds.onchange=()=>{donSort=ds.value;DLIM=60;render();};}
  const dc=document.getElementById('doncat'); if(dc)dc.onchange=()=>{catFlt=dc.value;DLIM=60;render();};
  const cm=document.getElementById('catmgr'); if(cm)cm.onclick=openCatManager;
  const fx=document.getElementById('fixbox');
  if(fx)fx.addEventListener('toggle',()=>{FIXOPEN=fx.open;});
  view.querySelectorAll('.fixtab').forEach(b=>b.onclick=()=>{
    const t=b.dataset.t;
    const btn=document.querySelector('.tab[data-tab="'+t+'"]');
    if(btn){btn.click();return;}
    tab=t;flt='';render();});
  const db2=document.getElementById('dupBtn'); if(db2)db2.onclick=openDupes;
  const afb=document.getElementById('addrFixBtn'); if(afb)afb.onclick=()=>{flt='addrfix';render();};
  const nab=document.getElementById('noAddrBtn'); if(nab)nab.onclick=()=>{flt='noaddr';NOADDR=null;render();};
  const npb=document.getElementById('noPhoneBtn'); if(npb)npb.onclick=()=>{flt='nophone';NOPHONE=null;NPLIM=15;render();};
  const neb=document.getElementById('noEngBtn'); if(neb)neb.onclick=()=>{flt='noeng';NELIM=25;render();};
  view.querySelectorAll('.rowc').forEach(r=>r.onclick=()=>openDonor(DB.find(x=>x.id==r.dataset.id)));
  document.getElementById('newDonorBtn').onclick=openNewDonor;
}
// זיהוי כתובת בעייתית (מילים דבוקות / מספר דבוק / מדינה כפולה / כתובת ישראלית שמתחילה במספר)
// המספר התלוש בסוף הרחוב, אם יש — "1241 E 28th St 4626" → "4626"
const TAILRX=/^(.*?(?:st|ave|avenue|rd|road|blvd|dr|drive|ln|lane|ct|court|pl|place|way|ter|terrace|pkwy|hwy)\.?)\s+(\d{3,})\s*$/i;
function tailNum(a){const m=TAILRX.exec(String(a||'').split(',')[0].trim());return m?m[2]:'';}
function stripTail(a){
  const parts=String(a||'').split(',');
  const m=TAILRX.exec((parts[0]||'').trim());
  if(m)parts[0]=m[1];
  return parts.join(',').trim();
}
function addrIssue(d){
  const a=(d.addr||'').trim(); if(!a||+d.addr_ok)return null;
  if(/[a-z][A-Z]/.test(a)||/\d[A-Z][a-z]/.test(a))return 'מילים דבוקות';
  if(/[\u0590-\u05FF]\d/.test(a))return 'מספר דבוק לרחוב';
  if(/\b([A-Z]{2}),\s*\1\b/.test(a))return 'מדינה כפולה';
  const street=(a.split(',')[0]||'');
  if(d.region==='il'&&/^\s*[\d]/.test(a))return 'מתחיל במספר (אולי הפוך)';
  if(d.region==='il'&&/\d[ ]*[\u0590-\u05FF]/.test(street))return 'מספר לפני שם הרחוב — לבדוק';
  // "1241 E 28th St 4626" — מספר תלוש בסוף הרחוב. בדרך כלל דירה או מיקוד
  // שנדבק בטעות בייבוא, ואי אפשר לשלוח לשם דואר.
  if(/(st|ave|avenue|rd|road|blvd|dr|drive|ln|lane|ct|court|pl|place|way|ter|terrace|pkwy|hwy)\.?\s+\d{3,}\s*$/i.test(street.trim()))
    return 'מספר מיותר בסוף — דירה? מיקוד?';
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
let NELIM=25;
// מאיר: "צריך כפתור תורמים בלי שם באנגלית". לצד כל אחד מוצעת הצעה מתוך
// כתובת המייל שלו, וכל שם נשמר בלחיצה אחת — או שמקלידים ידנית.
function engGuess(d){
  const em=splitEmails(d.email||'')[0]||'';
  const loc=em.split('@')[0].toLowerCase().trim();
  if(!loc||/\d/.test(loc))return '';
  const parts=loc.split(/[._\-]+/).filter(Boolean);
  if(parts.length<2||parts.length>3)return '';
  const stop=['info','office','mail','email','admin','sales','support','contact',
    'accounts','accounting','billing','service','help','team','the','and','inc','llc',
    'corp','group','realty','law','cpa','md','me','my','new','usa','ny','nj'];
  if(parts.some(p=>p.length<3||!/^[a-z]+$/.test(p)||stop.includes(p)))return '';
  return parts.map(p=>p[0].toUpperCase()+p.slice(1)).join(' ');
}
function renderNoEng(){
  chips.innerHTML='';
  const all=DB.filter(d=>!(d.english||'').trim())
              .filter(d=>matchQ(d.last+' '+d.first+' '+(d.email||'')+' '+(d.phone||'')));
  const withG=all.filter(d=>engGuess(d)).length;
  const rows=all.slice(0,NELIM);
  view.innerHTML=`<div class="misshead">🔤 תורמים בלי שם באנגלית</div>
    <div class="submuted">${all.length} תורמים${withG?(' · '+withG+' מהם עם הצעה מכתובת המייל'):''}.
      השם באנגלית משמש לקבלות, לדיוור, ולזיהוי החיובים מהבנק.</div>
    <button class="btn ghost" id="neback" style="margin:8px 2px">→ חזרה לתורמים</button>
    <button class="btn" id="nescan" style="width:100%;margin:0 2px 8px">📥 סרוק את הג'ימייל והשלם שמות</button>
    <div class="hintxt" id="nescanst" style="margin:-4px 2px 8px">עובר על כל המיילים שקיבלנו ושלחנו — משנת 2015 — ולוקח את השם הלועזי
      שמופיע ליד כתובת המייל של התורם. נכנס רק שם שמתאים לשם העברי שבכרטיס.</div>
    ${rows.map(d=>{const g=engGuess(d);
      return `<div class="npcard" data-did="${d.id}">
        <div class="nm"><b class="avnamelink" data-id="${d.id}">${esc((d.last+' '+(d.first||'')).trim())}</b>
          <span class="rownum">#${d.id}</span></div>
        ${d.email?`<div class="nemail" dir="ltr">${esc(splitEmails(d.email).join(' · '))}</div>`:''}
        ${d.phone?`<div class="nemail" dir="ltr">${esc(splitPhones(d.phone)[0]||'')}</div>`:''}
        <div class="addrow"><input class="neinp" data-did="${d.id}" dir="ltr"
            placeholder="שם באנגלית — שם פרטי ואז שם משפחה" value="${esc(g)}">
          <button class="btn sm nesave" data-did="${d.id}">💾 שמור</button></div>
        ${g?'<div class="hintxt" style="margin:-2px 2px 0">💡 ההצעה מגיעה מכתובת המייל — בדוק ותקן אם צריך</div>':''}
      </div>`;}).join('')||'<div class="empty">כל התורמים כבר עם שם באנגלית ✓</div>'}
    ${all.length>rows.length?`<button class="btn" id="nemore" style="width:100%;margin:8px 2px">הצג עוד ${Math.min(25,all.length-rows.length)}</button>`:''}`;
  document.getElementById('neback').onclick=()=>{flt='';render();};
  const mb=document.getElementById('nemore'); if(mb)mb.onclick=()=>{NELIM+=25;renderNoEng();};
  // סריקת הג'ימייל לשמות לועזיים — רצה בשרת, וכאן רק עוקבים אחריה
  const sb=document.getElementById('nescan'), sst=document.getElementById('nescanst');
  if(sb)sb.onclick=async()=>{
    sb.disabled=true; sst.textContent='מתחיל לסרוק את הג׳ימייל…';
    const r=await api('POST','/api/mail/engscan',{});
    if(!r||!r.ok){
      sb.disabled=false;
      sst.textContent=(r&&r.error==='not_configured')
        ? 'הג׳ימייל לא מחובר בשרת — בדוק ב-🩺 בדיקת מערכת'
        : 'הסריקה לא התחילה'+((r&&r.detail)?(' — '+r.detail):'');
      return;}
    for(;;){
      await new Promise(z=>setTimeout(z,2500));
      let s; try{s=await api('GET','/api/mail/engscan/status');}catch(e){continue;}
      if(!s)continue;
      if(s.error){sb.disabled=false;sst.textContent='שגיאה: '+s.error;return;}
      if(s.done){
        sb.disabled=false;
        sst.textContent='הסריקה הסתיימה — '+(s.new||0)+' כתובות נבדקו, '
          +(s.filled||0)+' שמות נכנסו לכרטיסים.';
        if(s.filled){await load();renderNoEng();}
        return;}
      sst.textContent='סורק'+(s.box?(' '+s.box):'')+'… '+(s.scanned||0)
        +(s.total?(' מתוך '+s.total):'')+' מיילים';
    }};
  view.querySelectorAll('.avnamelink').forEach(b=>b.onclick=()=>openDonor(DB.find(x=>x.id==b.dataset.id)));
  const save=async b=>{
    const d=DB.find(x=>x.id==b.dataset.did); if(!d)return;
    const inp=view.querySelector('.neinp[data-did="'+b.dataset.did+'"]');
    const v=(inp?inp.value:'').trim();
    if(!v){if(inp)inp.focus();return;}
    b.disabled=true; d.english=v;
    await api('PUT','/api/donor/'+d.id,{english:v});
    toast('נשמר ✓'); renderNoEng();
  };
  view.querySelectorAll('.nesave').forEach(b=>b.onclick=()=>save(b));
  view.querySelectorAll('.neinp').forEach(i=>i.onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();
    save(view.querySelector('.nesave[data-did="'+i.dataset.did+'"]'));}});
}
async function renderNoPhone(){
  view.innerHTML='<div class="cnt">טוען הצעות…</div>';
  if(!NOPHONE){ try{ NOPHONE=await api('GET','/api/audit/phones'); }catch(e){ NOPHONE={ok:false}; } }
  const R=NOPHONE||{};
  if(!R.ok){view.innerHTML=`<div class="misshead">📞 השלמת טלפונים</div><div class="empty">לא הצלחתי לטעון${R.error?(' — '+esc(R.error)):''}</div><button class="btn" id="npback" style="margin:10px 2px">→ חזרה</button>`;
    document.getElementById('npback').onclick=()=>{flt='';render();};return;}
  const all=(R.rows||[]).filter(r=>matchQ(r.name));
  const rows=all.slice(0,NPLIM);        // מציגים מנה קטנה בכל פעם — קל יותר לעבור על זה בטלפון
  const nc=all.filter(r=>r.cands.length).length;
  view.innerHTML=`<div class="misshead">📞 השלמת טלפונים</div>
    <div class="submuted">${R.total||0} תורמים בלי טלפון${nc?(', מתוכם '+nc+' עם הצעה מאנשי הקשר'):''}.<br>
      ✓ = זה הוא · ✕ = לא הוא. למי שאין הצעה — אפשר להקליד את המספר ישירות.</div>
    <button class="btn ghost" id="npback" style="margin:8px 2px">→ חזרה לתורמים</button>
    <div class="list">${rows.map(r=>`<div class="npcard" data-did="${r.id}">
      <div class="nm">${esc(r.name)}${r.tot?` <small style="color:var(--yes)">$${(+r.tot).toLocaleString('en-US')}</small>`:''}${r.tier==='יששכר_זבולון'?' <small>יש"ז</small>':''}</div>
      ${r.email?`<div class="miss2">${esc(r.email)}</div>`:''}
      ${r.cands.map(c=>`<div class="npcand">
        <button class="btn sm npyes" data-did="${r.id}" data-ph="${esc(c.phone)}" data-em="${esc(c.email||'')}">✓</button>
        <button class="del npno" data-did="${r.id}" data-ph="${esc(c.phone)}">✕</button>
        <span class="npi"><b dir="ltr">${esc(c.phone)}</b><br><small>${esc(c.name)}${c.sure?' · <b style="color:var(--yes)">שם פרטי תואם</b>':''}</small></span>
      </div>`).join('')}
      <div class="npman"><input class="npph" data-did="${r.id}" dir="ltr" inputmode="tel" placeholder="${r.cands.length?'או הקלד מספר אחר…':'הקלד את המספר שלו…'}">
        <button class="btn sm npsave" data-did="${r.id}">💾 שמור</button></div>
      <button class="btn sm ghost npskip" data-did="${r.id}" style="margin-top:5px">🚫 ${r.cands.length?'אף אחד מהם':'אין לו טלפון'}</button>
    </div>`).join('')||'<div class="empty">כל התורמים עם טלפון 🎉</div>'}</div>
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
  // הקלדה ידנית — למי שאין לו הצעה מאנשי הקשר, או כשמאיר יודע מספר אחר
  const saveMan=async b=>{const did=+b.dataset.did,inp=view.querySelector('.npph[data-did="'+did+'"]');
    const ph=(inp?inp.value:'').trim(); if(!ph){if(inp)inp.focus();return;}
    b.disabled=true;
    await api('POST','/api/audit/phones',{donor_id:did,phone:ph});
    const d=DB.find(x=>x.id===did); if(d)d.phone=ph;
    toast('נשמר ✓'); drop(did,null);};
  view.querySelectorAll('.npsave').forEach(b=>b.onclick=e=>{e.stopPropagation();saveMan(b);});
  view.querySelectorAll('.npph').forEach(inp=>inp.onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();
    saveMan(view.querySelector('.npsave[data-did="'+inp.dataset.did+'"]'));}});
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
      <div class="nasuga" dir="auto">${esc(s.addr)}</div>
      <div class="dupacts"><button class="btn sm nause" data-id="${p.id}" data-i="${i}">✔️ קבע כתובת זו</button>
        <button class="btn sm ghost nanot dupnot" data-id="${p.id}" data-i="${i}">✕ לא מתאים</button></div></div>`).join('')}
  </div>`;
  view.innerHTML=`<button class="btn ghost" id="nback" style="width:100%;margin-bottom:8px">⬅ חזרה לרשימת התורמים</button>
    <div class="rbtitle">🏠 תורמים בלי כתובת — ${NOADDR.count||0}</div>
    <button class="btn" id="gcpull" style="width:100%;background:#1a73e8;border-color:#1a73e8;margin-bottom:6px">📇 משוך אנשי קשר מגוגל והשלם כתובות</button>
    <label class="btn" id="gccsvbtn" style="width:100%;background:var(--yes);border-color:var(--yes);margin-bottom:6px;display:block;text-align:center;cursor:pointer">📄 העלה אנשי קשר — CSV מגוגל או VCF מהטלפון
      <input type="file" id="gccsv" accept=".csv,.vcf,.vcard,text/csv,text/vcard,text/x-vcard" hidden></label>
    <div id="gcout" class="hintxt" style="margin:0 2px 10px">${(NOADDR.with_suggest||0)} מהם יש הצעה מוכנה — מהמייל שהתורם עצמו שלח (בדרך כלל מהחתימה שבתחתית), מייצוא אנשי הקשר, או מכתובת החיוב. כל הצעה מחכה לאישור שלך, ומסומן ליד כל אחת מאיפה היא הגיעה. לשאר אין כתובת באף מקור — לחץ על הכפתור כדי למשוך ישירות מאנשי הקשר בגוגל.</div>
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
/* ---------- 🎯 טיפול: תרומות שנכנסו בלי "עבור מה" ---------- */
// הכסף כבר בכרטיס התורם; כאן רק משלימים את הייעוד, במקום אחד מרוכז.
let WFLIM=40;
function noCatList(){
  const out=[];
  DB.forEach(d=>(d.donations||[]).forEach(x=>{
    if(!String(x.category||'').trim())out.push({d,x});}));
  out.sort((a,b)=>String(b.x.date||'').localeCompare(String(a.x.date||'')));
  return out;
}
// נפתח מתוך מסך החיובים (כפתור "🎯 בלי ייעוד") — לא חלון נפרד.
// ייעוד שהוא יום (פרנס לילה / חדר קפה / ארוחת בוקר) לא מסתפק בשם הייעוד —
// צריך לדעת איזה יום נתפס, אחרת הכסף מסווג אבל הלילה לא משובץ לאף אחד.
const WFDAY={'פרנס לילה':'parnes','חדר קפה':'coffee','ארוחת בוקר':'breakfast'};
// "בניין" לבד לא אומר כלום — צריך לדעת מה נתרם בו. בכל מקום שבוחרים
// בניין נפתח שדה חופשי, והייעוד נשמר כ"בניין — שולחן"
function isBldgCat(c){return /בנין|בניין/.test(String(c||''));}
function bldgList(id){return `<datalist id="${id}">${(BUILDING_ITEMS||[]).map(x=>`<option value="${esc(x)}">`).join('')}</datalist>`;}
async function bldgRemember(it){
  if(it&&!(BUILDING_ITEMS||[]).includes(it)){await api('POST','/api/building_items',{name:it});BUILDING_ITEMS.unshift(it);}
}
// תרומה שממתינה לשיבוץ בלוח. כל עוד היא פתוחה — הלוח מציג פס עליון,
// והיום שנבחר נרשם על התורם הזה, מסומן כנגבה, והייעוד נכנס לתרומה
let PYPICK=null;
function openParnesPick(o,cat,note){
  PYPICK={id:o.x.id,donor_id:o.d.id,name:(o.d.last+' '+o.d.first).trim(),
          amount:o.x.amount,cur:curSym(o.d),cat,kind:WFDAY[cat],
          note:wfNoteBody(o.x,(note||'').trim()),ded:(note||'').trim()};
  pyKind=PYPICK.kind; pyMonth=null; pyDay=null; flt=''; plaque=null; tab='parnes';
  document.querySelectorAll('.tab').forEach(x=>x.classList.toggle('on',x.dataset.tab==='parnes'));
  try{localStorage.setItem('kc_tab','parnes');}catch(e){}
  render(); toast('בחר את הלילה של '+PYPICK.name);
}
function pyPickBar(){
  if(!PYPICK)return '';
  return `<div class="pypick"><span>🎯 משבץ עכשיו: <b>${esc(PYPICK.name)}</b> · ${PYPICK.cur}${esc(PYPICK.amount)} — לחץ על היום שהוא תפס</span>
    <button class="btn sm ghost" id="pypx">✕ ביטול</button></div>`;
}
function wirePyPick(){
  const b=document.getElementById('pypx');
  if(b)b.onclick=()=>{PYPICK=null;render();toast('בוטל');};
}
// היום נבחר: התרומה מקבלת את הייעוד, והלילה מסומן כנגבה
async function pyPickDone(pid){
  const P=PYPICK; if(!P)return;
  if(pid)await api('PUT','/api/parnes/'+pid,{paid:1});
  await api('PUT','/api/donation/'+P.id,{category:P.cat,note:P.note});
  PYPICK=null;
  await load(); toast('✓ '+P.name+' — הלילה נתפס ונרשם כנגבה');
}
function wfYear(x){const m=/(ת[שק]["׳']?[א-ת]{0,3})\s*$/.exec(String((x&&x.hmonth)||''));return m?m[1]:'';}
// ההערה החופשית בלבד. החלק הראשון ("נכנס מצ'ייס זל") נכתב על ידינו
// ונשמר כמו שהוא; מה שמאיר מוסיף נשמר אחריו
function wfNote(x){
  const p=String(x.note||'').split(' · ').slice(1)
    .filter(t=>t&&!/^לא סווג/.test(t));
  return p.join(' · ');
}
function wfNoteBody(x,txt){
  const head=String(x.note||'').split(' · ')[0];
  return txt?(head?head+' · '+txt:txt):head;
}
function whatForBox(el){
  let list=noCatList().filter(o=>matchQ(o.d.last+' '+o.d.first+' '+(o.d.english||'')+' '+(o.x.amount||'')));
  const tot=list.reduce((s,o)=>s+amtNum(o.x.amount),0);
  el.innerHTML=`<div class="cnt"><span id="wfcnt">🎯 בלי ייעוד — ${list.length} תרומות · $${Math.round(tot).toLocaleString('en-US')}</span>
      <button class="btn sm ghost" id="wfclose">✕ סגור</button></div>
    <div class="hintxt" style="margin:0 2px 6px">הכסף כבר רשום אצל התורם. כאן רק בוחרים עבור מה, ולוחצים 💾 שמור.</div>
    ${bldgList('wfbldgitems')}
    <div class="list">${list.slice(0,WFLIM).map(o=>`<div class="wfrow" data-id="${o.x.id}">
      <div class="wfhead"><b class="avnamelink" data-id="${o.d.id}">${esc((o.d.last+' '+o.d.first).trim())}</b>
        <span class="wfamt">${curSym(o.d)}${esc(o.x.amount)}</span>
        <span class="dnmeta">${o.x.date?esc(gregLabel(o.x.date)):''}${o.x.method?(' · '+esc(chLabel(o.x.method))):''}</span></div>
      <div class="wfact"><select class="wfcat" data-id="${o.x.id}">${dnCatOpts('')}</select>
        <button class="btn sm wfsave" data-id="${o.x.id}">💾 שמור</button></div>
      <div class="addrow"><input class="wfnote" data-id="${o.x.id}" placeholder="📝 הערה (למשל: עבור חודשיים יששכר־זבולון)" value="${esc(wfNote(o.x))}"></div>
      <div class="addrow hidden" data-wfnew="${o.x.id}"><input class="wfnew" placeholder="שם הייעוד החדש…"></div>
      <div class="addrow hidden" data-wfbldg="${o.x.id}"><input class="wfbldg" list="wfbldgitems" placeholder="🏗️ מה תרם בבניין? (שולחן / עמוד / מטר…)"></div>
      <div class="wfday hidden" data-wfday="${o.x.id}">
        <div class="hintxt">🗓️ איזה לילה הוא תפס? בלוח רואים מה פנוי, מי כבר לקח, ומה עוד לא נגבה.</div>
        <button class="btn sm wfopen" data-id="${o.x.id}">🗓️ פתח את הלוח ובחר יום</button>
      </div>
    </div>`).join('')||'<div class="empty">🎉 לכל התרומות יש ייעוד</div>'}</div>
    ${list.length>WFLIM?`<button class="btn ghost" id="wfmore" style="width:100%;margin:8px 2px">עוד — מציג ${WFLIM} מתוך ${list.length}</button>`:''}`;
  const mb=document.getElementById('wfmore'); if(mb)mb.onclick=()=>{WFLIM+=40;whatForBox(el);};
  const cb=document.getElementById('wfclose'); if(cb)cb.onclick=()=>{ledNoCat=false;renderLedger();};
  el.querySelectorAll('.avnamelink').forEach(b=>b.onclick=()=>openDonor(DB.find(x=>x.id==b.dataset.id)));
  el.querySelectorAll('.wfcat').forEach(s=>s.onchange=()=>{
    const nb=el.querySelector('[data-wfnew="'+s.dataset.id+'"]');
    if(nb){nb.classList.toggle('hidden',s.value!=='__new__'); if(s.value==='__new__')nb.querySelector('.wfnew').focus();}
    const db2=el.querySelector('[data-wfday="'+s.dataset.id+'"]');
    if(db2)db2.classList.toggle('hidden',!WFDAY[s.value]);
    const bb=el.querySelector('[data-wfbldg="'+s.dataset.id+'"]');
    if(bb){bb.classList.toggle('hidden',!isBldgCat(s.value));
      if(isBldgCat(s.value))bb.querySelector('.wfbldg').focus();}});
  el.querySelectorAll('.wfopen').forEach(b=>b.onclick=()=>{
    const row=el.querySelector('.wfrow[data-id="'+b.dataset.id+'"]');
    const cat=row.querySelector('.wfcat').value.trim();
    const o=noCatList().find(z=>String(z.x.id)===String(b.dataset.id)); if(!o)return;
    openParnesPick(o,cat,(row.querySelector('.wfnote')||{value:''}).value.trim());});
  el.querySelectorAll('.wfsave').forEach(b=>b.onclick=async()=>{
    const id=b.dataset.id, row=el.querySelector('.wfrow[data-id="'+id+'"]');
    let cat=row.querySelector('.wfcat').value.trim();
    if(cat==='__new__')cat=(row.querySelector('.wfnew')||{value:''}).value.trim();
    if(!cat){toast('בחר עבור מה');return;}
    const o=noCatList().find(z=>String(z.x.id)===String(id)); if(!o)return;
    // ייעוד של יום נסגר בלוח עצמו — שם רואים מה תפוס ומי כבר לקח
    if(WFDAY[cat]){ openParnesPick(o,cat,(row.querySelector('.wfnote')||{value:''}).value.trim()); return; }
    if(isBldgCat(cat)){
      const it=(row.querySelector('.wfbldg')||{value:''}).value.trim();
      if(!it){toast('כתוב מה הוא תרם בבניין');return;}
      await bldgRemember(it); cat=cat+' — '+it;
    }
    o.x.category=cat;
    const nt=(row.querySelector('.wfnote')||{value:''}).value.trim();
    const body={category:cat}; body.note=wfNoteBody(o.x,nt); o.x.note=body.note;
    await api('PUT','/api/donation/'+id,body);
    if(!(CAMPAIGNS||[]).includes(cat)&&!DNBASE.includes(cat)){api('POST','/api/campaigns',{name:cat});CAMPAIGNS.unshift(cat);}
    // מסירים רק את השורה הזו. רענון של כל הרשימה מזיז את הכפתורים מתחת
    // לאצבע, ואז לחיצה שנייה נופלת על תורם אחר
    toast('✓ '+(o.d.last+' '+o.d.first).trim()+' '+curSym(o.d)+o.x.amount+' → '+cat);
    row.remove(); wfCount();});
}
// עדכון המונים בלי לרנדר מחדש את הרשימה
function wfCount(){
  const nc=noCatList(), s2=nc.reduce((a,o)=>a+amtNum(o.x.amount),0);
  const t='$'+Math.round(s2).toLocaleString('en-US');
  const c=document.getElementById('wfcnt');
  if(c)c.textContent='🎯 בלי ייעוד — '+nc.length+' תרומות · '+t;
  const b=document.querySelector('#lednocat b'), sm=document.querySelector('#lednocat small');
  if(b)b.textContent=t;
  if(sm)sm.textContent=nc.length+' תרומות — להשלים עבור מה';
}
function renderAddrFix(){
  chips.innerHTML='';
  let list=DB.filter(d=>addrIssue(d)).filter(d=>matchQ(d.last+' '+d.first+' '+d.addr));
  list.sort((a,b)=>(a.last||'').localeCompare(b.last||'','he'));
  view.innerHTML=`<button class="back" id="afback">→ חזרה לתורמים</button>
    <div class="cnt">🔴 כתובות לתיקון: ${list.length}</div>
    <div class="hintxt">ערוך את הכתובת ולחץ 💾 שמור, או ✓ תקין אם הכתובת בסדר כמו שהיא (תוסר מהרשימה).</div>
    ${list.filter(d=>tailNum(d.addr)).length>1?`<button class="btn" id="afstripall" style="width:100%;margin:6px 2px">✂️ הסר את כל המספרים התלושים (${list.filter(d=>tailNum(d.addr)).length})</button>
      <div class="hintxt">מספר בן 4 ספרות שנדבק בסוף הרחוב בייבוא. בדוק שורה־שתיים לפני שאתה מאשר לכולם.</div>`:''}
    <div class="list">${list.map(d=>`<div class="afrow" data-id="${d.id}">
      <div class="afname"><b class="avnamelink" data-id="${d.id}">${esc((d.last+' '+d.first).trim())}</b> <span class="rownum">#${d.id}</span> <span class="kvtag">${esc(addrIssue(d))}</span></div>
      <input class="afaddr" data-id="${d.id}" value="${esc(d.addr||'')}" dir="${d.region==='il'?'rtl':'ltr'}">
      <div class="afact"><button class="btn sm afsave" data-id="${d.id}">💾 שמור</button>${tailNum(d.addr)?`<button class="btn sm ghost afstrip" data-id="${d.id}">✂️ הסר ${esc(tailNum(d.addr))}</button>`:''}<button class="kvskip afok" data-id="${d.id}">✓ תקין</button></div>
    </div>`).join('')||'<div class="empty">🎉 אין כתובות לתיקון</div>'}</div>`;
  document.getElementById('afback').onclick=()=>{flt='';render();};
  const asa=document.getElementById('afstripall');
  if(asa)asa.onclick=async()=>{
    const hits=list.filter(d=>tailNum(d.addr));
    if(!await uiConfirm('להסיר את המספר התלוש מ-'+hits.length+' כתובות?\nלמשל: "1241 E 28th St 4626" ← "1241 E 28th St"'))return;
    asa.disabled=true; asa.textContent='מנקה…';
    for(const d of hits){ const nw=stripTail(d.addr); d.addr=nw; d.addr_ok=1;
      await api('PUT','/api/donor/'+d.id,{addr:nw,addr_ok:1}); }
    toast('נוקו '+hits.length+' כתובות ✓'); renderAddrFix();};
  view.querySelectorAll('.avnamelink').forEach(b=>b.onclick=()=>openDonor(DB.find(x=>x.id==b.dataset.id)));
  view.querySelectorAll('.afsave').forEach(b=>b.onclick=async()=>{const d=DB.find(x=>x.id==b.dataset.id);const inp=view.querySelector('.afaddr[data-id="'+b.dataset.id+'"]');d.addr=inp.value;await api('PUT','/api/donor/'+d.id,{addr:inp.value});toast('נשמר ✓');renderAddrFix();});
  // ניקוי המספר התלוש בלחיצה — 38 כתובות נפגעו מאותו ייבוא
  view.querySelectorAll('.afstrip').forEach(b=>b.onclick=async()=>{
    const d=DB.find(x=>x.id==b.dataset.id); if(!d)return;
    const nw=stripTail(d.addr); d.addr=nw; d.addr_ok=1;
    await api('PUT','/api/donor/'+d.id,{addr:nw,addr_ok:1});
    toast('נוקה ✓ '+nw); renderAddrFix();});
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
            ${d.addr?`<div class="dupmeta" dir="auto">🏠 ${esc(d.addr)}</div>`:''}
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
function openNewDonor(onCreate,pre){
  cardTab='details'; pre=pre||{};
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
  ['english','phone','email','addr','city','country','zip','last','first'].forEach(k=>{
    const el=document.getElementById('nd_'+k); if(el&&pre[k])el.value=pre[k];});
  const g=id=>document.getElementById(id).value.trim();
  // בחירת ארץ ישראל → מילוי אוטומטי: מדינה, קידומת +972, פלייסהולדר מיקוד
  // בכרטיס חדש בלבד: טלפון או כתובת ישראליים בוחרים ₪ מראש — ותמיד אפשר לשנות
  (()=>{
    const rg=document.getElementById('nd_region'), ph=document.getElementById('nd_phone'),
          ad=document.getElementById('nd_addr'), ct=document.getElementById('nd_city');
    if(!rg||!ph)return;
    const IL=/ירושלים|ביתר|בית שמש|בני ברק|אלעד|מודיעין|אשדוד|צפת|טבריה|רכסים|חיפה|ישראל|israel|jerusalem|bnei ?brak|beitar|ashdod/i;
    const sniff=()=>{
      if(rg._touched)return;                       // מרגע שבחרת ידנית — לא נוגעים
      const p2=String(ph.value||'').replace(/[^\d+]/g,'');
      const t=[ad&&ad.value,ct&&ct.value].join(' ');
      rg.value=(p2.startsWith('+972')||p2.startsWith('972')||IL.test(t))?'il':'';
    };
    [ph,ad,ct].forEach(x=>x&&x.addEventListener('input',sniff));
    rg.addEventListener('change',()=>{rg._touched=1;});
  })();
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
// היום בחודש שבו התורם משלם בדרך כלל — חציון הימים מההיסטוריה שלו
function payDay(d){
  const ds=((d&&d.donations)||[]).map(x=>{const m=/^\d{4}-\d{2}-(\d{2})$/.exec(x.date||'');return m?+m[1]:0;}).filter(Boolean);
  if(!ds.length)return 0;
  ds.sort((a,b)=>a-b); return ds[Math.floor(ds.length/2)];
}
// עד איזה חודש בודקים. החודש הנוכחי נספר רק אחרי שעבר יום החיוב הרגיל של
// התורם (עם שלושה ימי חסד), כדי לא לצבוע באדום מישהו שעוד לא הגיע זמנו.
function lastMonthToCheck(d){
  // החודש הנוכחי אינו חוב. גם אם יום החיוב עבר, ייתכן שהכסף עוד בדרך —
  // חוב נספר רק על חודשים שכבר הסתיימו.
  return new Date().getMonth() - 1;
}
// שלושה חודשים רצופים ששולמו — התנהגות של הוראת קבע, גם בלי שסומן כך בכרטיס
function _run3(m){let r=0;for(let i=0;i<(m||'').length;i++){r=(m[i]==='p'||m[i]==='c')?r+1:0;if(r>=3)return true;}return false;}
// האם מצפים מהתורם לתשלום כל חודש. רק אצלו יש טעם לדבר על "חודש שלא עבר":
// מי שתרם פעם אחת אינו חייב כלום בחודש שאחרי, ואסור לצבוע אותו באדום.
function isMonthly(d){
  if(!d)return false;
  const cat=(d.category||'').trim();
  if(cat==='מזדמן')return false;                              // סומן במפורש כתרומה חד־פעמית
  if(cat==='קבוע')return true;                                // סומן כקבוע חודשי
  if((d.pledges||[]).some(p=>+p.monthly===1))return true;      // התחייבות חודשית מפורשת
  return _run3(d.months||'');
}
function gaps(m,d){
  if(!m)return [];
  if(d&&!isMonthly(d))return [];
  const f=_firstPaid(m); if(f<0)return [];
  const last=d?lastMonthToCheck(d):GLAST;
  const g=[]; for(let i=f;i<=last;i++)if(m[i]!=='p'&&m[i]!=='c'&&m[i]!=='h')g.push(i);
  return g;
}
// כמה כסף נכנס בפועל בכל חודש — לפי התרומות עצמן, לא לפי הסימון במפה
function monthPaid(d){const s={};(d&&d.donations||[]).forEach(x=>{
  const k=String(x.date||'').slice(0,7); if(k.length===7&&amtNum(x.amount)>0)s[k]=(s[k]||0)+amtNum(x.amount);});
  return s;}
// חודש שמסומן "נגבה" אבל אין לו שום תשלום רשום — לא הופכים אותו לחוב לבד,
// רק מסמנים אותו כדי שאפשר יהיה לבדוק. אצל ברוך אמזל זה אפריל.
function monthUnbacked(d){
  if(!d||!d.months||!isMonthly(d)||amtNum(fixedAmt(d))<=0)return [];
  const s=monthPaid(d), last=lastMonthToCheck(d), out=[];
  for(let i=0;i<12&&i<=last;i++)
    if(d.months[i]==='p'&&!s[GREGYEAR+'-'+String(i+1).padStart(2,'0')])out.push(i);
  return out;
}
function monthGrid(m,d){if(!m)return '';const f=_firstPaid(m);const last=d?lastMonthToCheck(d):GLAST;
  const mo=d?isMonthly(d):true;   // אצל מזדמן אין "חודש חסר" — החודשים שלא שילם בהם אפורים
  const q=d?monthUnbacked(d):[];
  return `<div class="mgrid">${MON.map((l,i)=>{let c;const ch=m[i];if(ch==='p'||ch==='c')c=q.includes(i)?'gq':'gp';else if(ch==='h')c='gh';else if(mo&&f>=0&&i>=f&&i<=last)c='gx';else c='gn';return `<div class="mc ${c}"><span>${l}</span></div>`;}).join('')}</div>`
    + (q.length?`<div class="hintxt munb">❓ ${q.map(i=>MON[i]).join(', ')} — מסומן שנגבה, אבל אין תשלום רשום בחודש הזה. שווה לבדוק בדוח.</div>`:'');}
function setMonthChar(m,i,ch){const a=(m||'------------').padEnd(12,'-').split('');a[i]=ch;return a.join('');}

let cardTab='details';
let CURD=null;          // התורם שכרטיסו פתוח כרגע
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

// מאיר: "כשאני לוחץ על שם תורם בקוויטל נפתח הכרטיס, ואז אני רוצה לחזור
// לקוויטל איפה שאני אוחז וזה לא מחזיר אותי לאותו מקום". שומרים את מיקום
// הגלילה ברגע שהכרטיס נפתח, ומחזירים אותו כשהוא נסגר.
let SCROLLBACK=null;
function keepScroll(){SCROLLBACK=window.scrollY||document.documentElement.scrollTop||0;}
function restoreScroll(){
  if(SCROLLBACK==null)return; const y=SCROLLBACK; SCROLLBACK=null;
  // אחרי הסגירה הרשימה מצוירת מחדש — מחזירים אחרי שהציור הסתיים
  requestAnimationFrame(()=>requestAnimationFrame(()=>window.scrollTo(0,y)));
}
function openDonor(d,startTab){
  keepScroll();
  cardTab=startTab||'details';CURD=d;
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
  document.getElementById('cx').onclick=async()=>{await flushPrayers();
    ov.classList.remove('show');try{localStorage.removeItem('kc_donor');}catch(e){}
    restoreScroll();};
  sheet.querySelectorAll('.ctab').forEach(b=>b.onclick=async()=>{await flushPrayers();cardTab=b.dataset.c;renderCard(d);});
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
      <div class="avfiles dnfiles" id="ct_files"><label class="filebtn sm">📎 צרף תמונה / הקלטה / צילום<input type="file" multiple accept="image/*,audio/*,application/pdf" id="ct_file" hidden></label></div>
      <div class="hintxt">כל משימה נכנסת גם ללשונית "משימות" הראשית וליומן Google.</div></div>
    <div class="sec"><h3>📋 המשימות של ${esc((d.last+' '+d.first).trim())}</h3><div id="ct_list"></div></div>`;
  renderCardTasks(d);
  addMic(document.getElementById('ct_note'));
  wireKindSel(document.getElementById('ct_kind'));
  const ctF=pendFiles('ct_files','ct_file');
  document.getElementById('ct_add').onclick=async ev=>{
    const btn=ev.currentTarget; if(btn.disabled)return;
    const note=document.getElementById('ct_note').value.trim(),kind=await kindValue(document.getElementById('ct_kind')),date=document.getElementById('ct_date').value,who=document.getElementById('ct_who').value;
    if(!kind){return;}if(!note){toast('כתוב מה צריך לעשות');return;}if(!date){toast('בחר תאריך');return;}
    btn.disabled=true;                 // הגנה מלחיצה כפולה — אחרת נוצרות שתי משימות
    const r=await api('POST','/api/task',{donor_id:d.id,due_date:date,kind:kind,note:note,assignee:who});
    btn.disabled=false;
    if(r&&r.existing){toast('המשימה כבר קיימת');return;}
    d.tasks=d.tasks||[];d.tasks.push({id:r.id,donor_id:d.id,due_date:date,kind:kind,note:note,assignee:who,done:0});
    document.getElementById('ct_note').value='';
    if(ctF.arr.length){toast('מעלה קבצים…');for(const f of ctF.arr)await uploadBlob('task',r.id,f);ctF.reset();
      await load();const dd=DB.find(x=>x.id===d.id);if(dd)d.tasks=dd.tasks;
      renderCardTasks(d);toast('נוספה משימה עם האסמכתאות ✓');checkReminders();return;}
    renderCardTasks(d);toast('נוספה משימה ✓');checkReminders();};
}
function renderCardTasks(d){
  const el=document.getElementById('ct_list');if(!el)return;const td=todayStr();
  const open=(d.tasks||[]).filter(t=>!t.done||t.done==0).sort((a,b)=>(a.due_date||'9999').localeCompare(b.due_date||'9999'));
  el.innerHTML=open.map(t=>{const over=t.due_date&&t.due_date<td,icon=kindLabel(t.kind).split(' ')[0];
    return `<div class="cttask" data-id="${t.id}"><button class="tdone ctdone" data-id="${t.id}">✓</button>
      <div class="cti"><div>${icon} ${esc(t.note||'')}</div><div class="ctmeta ${over?'over':''}">${esc(t.due_date||'—')} ${whoChipHTML(t,'data-rwho="'+t.id+'"')}</div>
        <div class="avfiles">${(t.files||[]).map(fileChip).join('')}<label class="filebtn sm">📎 צרף<input type="file" accept="image/*,audio/*,application/pdf" class="ctup" data-id="${t.id}" hidden></label></div></div>
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
  el.querySelectorAll('.ctup').forEach(inp=>inp.onchange=()=>uploadFile('task',+inp.dataset.id,inp,async()=>{
    await load();const dd=DB.find(x=>x.id===d.id);if(dd)d.tasks=dd.tasks;renderCardTasks(d);}));
  el.querySelectorAll('.ctedit').forEach(b=>b.onclick=e=>{e.stopPropagation();const p=el.querySelector('.teditpanel[data-ctp="'+b.dataset.id+'"]');if(p)p.classList.toggle('hidden');});
  el.querySelectorAll('.ctsave').forEach(b=>b.onclick=async()=>{
    const t=(d.tasks||[]).find(x=>x.id==b.dataset.id);if(!t)return;
    const kind=await kindValue(el.querySelector('.ctk[data-id="'+b.dataset.id+'"]'));if(!kind)return;
    const note=el.querySelector('.ctn[data-id="'+b.dataset.id+'"]').value.trim();
    const date=el.querySelector('.ctd[data-id="'+b.dataset.id+'"]').value;
    const who=el.querySelector('.ctw[data-id="'+b.dataset.id+'"]').value;
    b.disabled=true;
    const rsp=await api('PUT','/api/task/'+t.id,{note:note,kind:kind,due_date:date,assignee:who});
    t.note=note;t.kind=kind;t.due_date=date;t.assignee=who;
    if(rsp&&rsp.contact)putLog(d,rsp.contact);
    renderCardTasks(d);renderReminders(d);checkReminders();toast('נשמר ✓');});
  el.querySelectorAll('[data-rwho]').forEach(b=>b.onclick=async e=>{e.stopPropagation();b.disabled=true;await flipWho(b.dataset.rwho);renderCardTasks(d);});
  el.querySelectorAll('.ctdone').forEach(b=>b.onclick=async()=>{const t=(d.tasks||[]).find(x=>x.id==b.dataset.id);if(!t)return;await setTaskDone(t,1,d);renderCardTasks(d);checkReminders();toastUndo('בוצע ✓ · נרשם בקשר',async()=>{await setTaskDone(t,0,d);renderCardTasks(d);checkReminders();});});
  el.querySelectorAll('.ctdel').forEach(b=>b.onclick=async()=>{if(!await uiConfirm('למחוק את המשימה?'))return;await api('DELETE','/api/task/'+b.dataset.id);d.tasks=(d.tasks||[]).filter(x=>x.id!=b.dataset.id);renderCardTasks(d);checkReminders();toast('נמחק');});
}
function buildTotals(d){let price=0,paid=0;(d.building||[]).forEach(x=>{price+=amtNum(x.amount);paid+=amtNum(x.paid);});return {price,paid,owed:price-paid};}
function cardBuilding(d,body){
  const t=buildTotals(d),cur=curSym(d);
  body.innerHTML=`<div class="totals"><div class="tot"><span>סה"כ הקדשות</span><b>${cur}${t.price}</b></div><div class="tot"><span>שולם</span><b>${cur}${t.paid}</b></div><div class="tot ${t.owed>0?'year':''}"><span>נשאר לתשלום</span><b>${cur}${t.owed}</b></div></div>
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
  el.innerHTML=(d.building||[]).map(x=>{const owed=amtNum(x.amount)-amtNum(x.paid);return `<div class="plwrap"><div class="pledge ${owed>0?'pending':'given'}"><div class="pi"><b>🏛️ ${esc(x.object||'—')}</b><br><small>מחיר: ${cur}${esc(String(amtNum(x.amount)))} · שולם: ${cur}${esc(String(amtNum(x.paid)))} · <b style="color:${owed>0?'var(--no)':'var(--yes)'}">${owed>0?('נשאר לתשלום '+cur+owed):'שולם במלואו ✓'}</b></small>${x.note?('<br><small>'+esc(x.note)+'</small>'):''}</div><button class="del" data-del="${x.id}">🗑</button></div>
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
  purposeList(d).forEach(c=>{if(parts.indexOf(c)<0)parts.push(c);});
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
// כמה מההתחייבות החודשית שייך ליששכר־זבולון, בלי לספור את אותו כסף פעמיים.
// אצל אברמוביץ 1350 הופיע פעם אחת כאברך ופעם כסכום קבוע — והסתכם ב-2700.
// כמה באמת נגבה כל חודש עבור יששכר־זבולון — לפי החודשים האחרונים בפועל.
// זו הראיה החזקה ביותר: הסכום שחוזר על עצמו בבנק. פחות משני חודשים זהים
// זו לא הוראת קבע ולכן לא נחשב.
function izRealMonthly(d){
  const mm={};
  (d.donations||[]).forEach(x=>{
    if(!/יששכר|זבולון/.test(String(x.category||'')))return;
    const m=String(x.date||'').slice(0,7);
    if(m.length<7||m.slice(0,4)!==GREGYEAR)return;
    mm[m]=(mm[m]||0)+amtNum(x.amount);});
  const ks=Object.keys(mm).sort().slice(-4);
  if(ks.length<2)return 0;
  const cnt={}; ks.forEach(k=>{const v=Math.round(mm[k]);cnt[v]=(cnt[v]||0)+1;});
  let best=0,bn=0;
  Object.keys(cnt).forEach(v=>{if(cnt[v]>bn){best=+v;bn=cnt[v];}});
  // רוב ברור בלבד. סכומים משתנים אינם הוראת קבע, ועדיף לשתוק מלטעות
  return (bn>=2&&bn*2>ks.length)?best:0;
}
function izOther(d){
  return (d.pledges||[]).filter(p=>+p.monthly&&amtNum(p.amount)>0&&plReal(p)
      &&!/יששכר/.test(String(p.category||''))).reduce((a,p)=>a+amtNum(p.amount),0);
}
// מה שיוצא מהתורם כל חודש בפועל: הקבועים + התשלום החודשי של התחייבות
// בתשלומים. אחרי שמאיר רושם את התשלומים, האזהרה נסגרת מעצמה.
function instPerMonth(d){
  return (d.pledges||[]).filter(p=>!+p.monthly&&amtNum(p.permo)>0&&plReal(p)
      &&plLeft(d,p)>0.5).reduce((a,p)=>a+amtNum(p.permo),0);
}
// להשוואה מול הגבייה של יששכר־זבולון סופרים רק התחייבויות שהכסף שלהן
// עדיין יושב בתוך אותו זרם. התחייבות שהתשלומים שלה כבר משויכים אליה
// (כמו הבניין אצל אברמוביץ) נגבית בנפרד ואין להוסיף אותה שוב.
function izStreamOther(d){
  return (d.pledges||[]).filter(p=>!/יששכר/.test(String(p.category||''))&&plReal(p)
      &&plCollected(d,p)<=0.5)
    .reduce((a,p)=>a+(+p.monthly?amtNum(p.amount)
      :(amtNum(p.permo)>0&&plLeft(d,p)>0.5?amtNum(p.permo):0)),0);
}
/* מאיר: "אם כתבתי 4,000 על יששכר־זבולון למה יש פה שוב התחייבות? ברגע
   שיש לו רשום שהוא נותן על יששכר־זבולון זה מספיק". שורה חודשית בלי ייעוד
   אמיתי ("התחייבות" / "קבוע") אצל תורם יששכר־זבולון היא אותו כסף עצמו,
   ולכן היא נבלעת בשורת היששכר־זבולון ואינה נספרת פעם שנייה. */
const NOPURP=c=>{const t=String(c||'').trim(); return !t||t==='התחייבות'||t==='קבוע';};
// שורות חודשיות שהן כפילות של שורת היששכר־זבולון — בלי ייעוד אמיתי
// ובאותו סכום בדיוק. הן לא מוצגות ולא נספרות בשום מקום.
function izDupPledges(d){
  if(String(d.tier||'')!=='יששכר_זבולון')return [];
  const pl=(d.pledges||[]).filter(p=>+p.monthly&&plReal(p));
  const iz=pl.filter(p=>isIZcat(p.category));
  let byav=0; try{byav=Math.round(izSummary(d).monthly||0);}catch(e){}
  const izAmt=iz.reduce((a,p)=>a+amtNum(p.amount),0)||byav;
  if(izAmt<0.5)return [];
  return pl.filter(p=>iz.indexOf(p)<0&&NOPURP(p.category)
    &&Math.abs(amtNum(p.amount)-izAmt)<1);
}
function izRowAmt(d){
  let s; try{s=izSummary(d);}catch(e){return 0;}
  const pl=(d.pledges||[]).filter(p=>+p.monthly&&amtNum(p.amount)>0);
  const izPl=pl.filter(p=>isIZcat(p.category));
  const izSum=izPl.reduce((a,p)=>a+amtNum(p.amount),0);
  if(izSum>0.5)return Math.round(izSum);            // הייעוד נרשם במפורש
  const other=izOther(d);
  // הסכום שבכרטיס והגבייה בפועל מסכימים ביניהם — זו האמת, גם אם ברשימת
  // האברכים נרשמו פחות. אצל פינטער נגבים 12,800 בחודש ורשום אברך אחד.
  // מאיר על ג'ייקובס: "יש לו קבוע 1700, והשאר זה תשלומים על קמחא דפסחא".
  // לכן מעלים רק כשהפער גדול וברור — תוספת קטנה היא לרוב משהו אחר,
  // ובמקרה כזה רק מציגים אזהרה ומאיר רושם לה שורה משלה.
  const real=izRealMonthly(d), card=amtNum(d.amount), byav=Math.round(s.monthly||0);
  if(real>0.5&&card>0.5&&Math.abs(real-card)<1&&real-other>byav
     &&real-other-byav>=500&&real-other>=byav*1.5)
    return Math.max(0,Math.round(real-other));
  if(!s.fromCard)return Math.round(s.monthly||0);   // לפי האברכים עצמם
  // "לפי הסכום הקבוע בכרטיס" — מה שנשאר מהסכום אחרי שאר השורות הקבועות
  return Math.max(0,Math.round((s.monthly||0)-other));
}
/* ---------- 📊 סיכום לפי ייעוד ----------
   מאיר על פינטער: "בסיכום של יששכר־זבולון מופיע עדיין הסכום של כולל יום
   ביחד עם היששכר־זבולון". הכסף נכנס מהבנק בשני חיובים (9,000 ו-3,800)
   וכולם מסומנים יששכר־זבולון, ולכן אי אפשר לפצל אותם לפי הסימון עצמו.
   הפיצול נעשה לפי החלוקה שמאיר רשם: כל ייעוד מקבל עד מה שהוא אמור היה
   לקבל בתקופה, לפי הסדר, ומה שנשאר מעבר לזה מוצג בשורה משלו. */
// עד איזה חודש הנתונים במערכת מלאים. חודש שהקובץ שלו טרם נקלט אינו
// נחשב חוב — אחרת כל תורם ייראה חסר עד שיגיע הקובץ הבא.
let DATATHRU=null;
function dataThru(){
  if(DATATHRU)return DATATHRU;
  // כמה תרומות יש בכל חודש. חודש שהקובץ שלו רק התחיל להיקלט מכיל חלק
  // קטן מהרגיל, ואם סופרים אותו כמעט כל תורם נראה כאילו חסר לו חודש.
  const cnt={};
  (DB||[]).forEach(d=>(d.donations||[]).forEach(x=>{
    const m=String(x.date||'').slice(0,7);
    if(m.length===7)cnt[m]=(cnt[m]||0)+1;}));
  const ms=Object.keys(cnt).sort();
  if(!ms.length){DATATHRU=todayStr().slice(0,7);return DATATHRU;}
  let i=ms.length-1;
  while(i>0){
    const prev=ms.slice(Math.max(0,i-3),i).map(m=>cnt[m]).sort((a,b)=>a-b);
    const med=prev.length?prev[Math.floor(prev.length/2)]:0;
    if(med&&cnt[ms[i]]<med*0.5){i--; continue;}   // חודש חלקי — לא נספר
    break;
  }
  DATATHRU=ms[i];
  return DATATHRU;
}
function monthsTo(fromYM,toYM){
  const a=String(fromYM||'').match(/^(\d{4})-(\d{2})/), b=String(toYM||'').match(/^(\d{4})-(\d{2})/);
  if(!a||!b)return 0;
  return Math.max(0, ((+b[1])*12+(+b[2])) - ((+a[1])*12+(+a[2])) + 1);
}
function prevMonth(ym){
  const m=String(ym||'').match(/^(\d{4})-(\d{2})/); if(!m)return '';
  const n=(+m[1])*12+(+m[2])-1;
  return Math.floor((n-1)/12)+'-'+String(((n-1)%12)+1).padStart(2,'0');
}
/* ---------- 📊 האם הגיע לסכום שהתחייב ----------
   מאיר: "תכל'ס אתה צריך שזה יעשה חשבון אם הוא הגיע לסכום שהתחייב או לא".
   לכל התחייבות: כמה הוא היה אמור לתת עד היום, כמה נגבה בפועל, ומה ההפרש.
   הכסף מחולק בין ההתחייבויות לפי החלוקה שנרשמה, כי בבנק הוא נכנס
   בחיוב אחד בלי פירוט. */
// מאיר: "אני צריך שתמיד יהיה חשבון כמה נכנס תכליס וכמה הוא חייב".
// שורת חשבון אחת מעל ההתחייבויות: כמה היה אמור להיכנס עד היום לפי מה
// שרשום, כמה באמת נכנס, וכמה חסר. החישוב עצמו הוא purposeAlloc — אותו
// חישוב שמסך "לבדיקה" נשען עליו, כדי שלא יהיו שני מספרים סותרים.
function acctLine(d){
  let a=null; try{a=purposeAlloc(d);}catch(e){return '';}
  if(!a||!a.rows.length)return '';
  const cur=curSym(d), f=n=>cur+Math.round(n).toLocaleString('en-US');
  const gap=Math.round(a.exp-a.got);
  const from=fmtMonth(a.first), to=fmtMonth(a.thru);
  // פירוט רק על מה שחסר — שורה שנסגרה במלואה אינה מוסיפה מידע
  const short=a.rows.filter(r=>r.gap>0.5)
    .map(r=>`${r.icon||''} ${esc(r.what)} ${f(r.gap)}`).join(' · ');
  return `<div class="acct ${gap>0.5?'owes':'ok'}">
    <div class="acct-r"><span>📅 ${esc(from)} – ${esc(to)}</span>
      <span>אמור היה להיכנס <b>${f(a.exp)}</b></span>
      <span>נכנס בפועל <b>${f(a.got)}</b></span>
      <span class="acct-g">${gap>0.5?('🔴 חייב <b>'+f(gap)+'</b>')
        :(a.extra>0.5?('🟢 שילם מראש <b>'+f(a.extra)+'</b>'):'✅ מסודר')}</span></div>
    ${short?`<div class="acct-d">${short}</div>`:''}
    ${a.steady?`<div class="acct-d">⚠️ בפועל נכנס ${f(a.steady)} בכל חודש —
      אם זה הסכום הנכון, עדכן את השורה כדי שלא ייצבר חוב מדומה</div>`:''}
  </div>`;
}
function purposeAlloc(d){
  // רק התחייבות שמאיר רשם ושעדיין בתוקף נכנסת לחשבון. סכום שהמערכת הסיקה
  // מהגבייה אינו התחייבות, ואסור שייצור חוב.
  const rows=commitRows(d).filter(r=>(r.mo||r.inst)&&r.amt>0.5&&r.conf>0&&!r.ended);
  if(!rows.length)return null;
  const thru=dataThru(), yr=thru.slice(0,4);
  // תחילת הספירה: החודש הראשון שנכנס בו כסף השנה, ולא לפני תחילת השנה
  let first='';
  (d.donations||[]).forEach(x=>{const m=String(x.date||'').slice(0,7);
    if(m.length===7&&m.slice(0,4)===yr&&(!first||m<first))first=m;});
  if(!first)first=yr+'-01';
  // כסף שנכנס השנה אבל סגר חוב של שנה קודמת אינו שייך לחשבון השנה.
  // מאיר: "הוא נתן 33,300 וחלק מזה על 2025 סכום מסוים".
  let pool=(d.donations||[]).filter(x=>String(x.date||'').slice(0,4)===yr)
    .reduce((a,x)=>a+amtNum(x.amount)-amtNum(x.prev_year),0);
  (d.parnes||[]).forEach(p=>{ if(+p.paid&&String(p.night_date||'').slice(0,4)===yr)
    pool+=amtNum(p.amount); });
  const base=rows.map(r=>{
    const per=r.inst?r.plan.per:r.amt;
    // מאיר: "בלי שתצבור חוב או זכות" — סכום שהשתנה באמצע השנה נספר רק
    // מהחודש שנרשם לו, ולא אחורה על חודשים ששולמו לפי הסכום הקודם
    let start=(r.inst&&r.plan.from)?(r.plan.from>first?r.plan.from:first):first;
    // החודשים שלפני השינוי אינם נעלמים — הם נספרים לפי הסכום שהיה נהוג
    // בהם. כך תורם שהוריד מ-1,000 ל-500 באמצע השנה אינו נראה כמי שנשאר
    // חייב על העבר, וגם לא כמי ששילם מראש.
    let head=0, hn=0;
    if(r.since&&r.since>start){
      hn=monthsTo(start, prevMonth(r.since));
      if(hn>0&&r.prev>0.5)head=r.prev*hn;
      start=r.since;
    }
    const n=monthsTo(start, thru);
    let exp=per*n+head;
    if(r.inst)exp=Math.min(exp, r.amt);          // תשלומים — לא מעבר לסכום הכולל
    return {what:r.what, icon:r.icon, per, n:n+hn, exp};
  });
  // החלוקה יחסית ולא לפי הסדר: כשחסר כסף, החוסר מתחלק בין ההתחייבויות
  // ולא נופל כולו על האחרונה. אחרת ייעוד אחד היה נראה "מלא ✓" בזמן
  // שהתורם בכלל לא הגיע לסכום.
  const sumExp=base.reduce((a,r)=>a+r.exp,0);
  const share=sumExp>0.5?Math.min(1, Math.max(0,pool)/sumExp):0;
  const out=base.map(r=>{
    const got=Math.min(r.exp, r.exp*share);
    pool-=got;
    return {what:r.what, icon:r.icon, per:r.per, n:r.n, exp:Math.round(r.exp),
            got:Math.round(got), gap:Math.round(r.exp-got)};
  });
  // תורם שמשלם בקביעות בכל חודש, רק פחות ממה שרשום בכרטיס — זה לא חוב
  // אלא סכום שגוי אצלנו. אצל אדלין יצחק נכנסים 100 בכל חודש והכרטיס
  // אומר 1,000.
  const by={};
  (d.donations||[]).forEach(x=>{const m=String(x.date||'').slice(0,7);
    if(m>=first&&m<=thru)by[m]=(by[m]||0)+amtNum(x.amount);});
  const need=[];
  for(let i=1;i<=12;i++){const m=yr+'-'+String(i).padStart(2,'0');
    if(m>=first&&m<=thru)need.push(m);}
  let steady=0;
  if(need.length>1&&need.every(m=>by[m]>0.5)){
    const cnt={};need.forEach(m=>{const v=Math.round(by[m]);cnt[v]=(cnt[v]||0)+1;});
    let best=0,bn=0;Object.keys(cnt).forEach(v=>{if(cnt[v]>bn){best=+v;bn=cnt[v];}});
    const per=base.reduce((a,r)=>a+r.per,0);
    if(bn>=need.length*0.6&&best<per-0.5)steady=best;
  }
  const prevPaid=(d.donations||[]).filter(x=>String(x.date||'').slice(0,4)===yr)
    .reduce((a,x)=>a+amtNum(x.prev_year),0);
  return {thru, first, rows:out, extra:Math.round(Math.max(0,pool)), steady, prevPaid,
          per:base.reduce((a,r)=>a+r.per,0),
          exp:out.reduce((a,r)=>a+r.exp,0), got:out.reduce((a,r)=>a+r.got,0)};
}
// מאיר: "תוריד את זה, זה מיותר. אם כתוב חוב מסוים אז מה הענין שיהיה
// עוד שורה". הריבוע "האם הגיע לסכום שהתחייב" ירד מדף התורם — החוב כבר
// מופיע בראש הכרטיס ובשורת ההתחייבות עצמה. החישוב (purposeAlloc) נשאר,
// כי מסך "לבדיקה" נשען עליו.
// אזהרה קצרה כשמה שנגבה בפועל אינו מה שרשום, ושתי דרכים לסגור אותה.
// מאיר: "אם סידרתי את זה איך אני מוחק את השורה האדומה? אם תורם העלה או
// הוריד את הסכום איך אני מעדכן בלי שתצבור חוב או זכות?"
//   "עדכן ל-X מהחודש" — הסכום מתעדכן, ונרשם מאיזה חודש הוא תקף, כך
//                       שהחודשים שלפניו אינם נספרים ואין חוב/זכות מדומים.
//   "זה בסדר"          — הסכום נשאר, וההערה נסגרת. היא תחזור רק אם
//                       הסכום שנגבה בפועל ישתנה שוב.
function izGapNote(d){
  const real=izRealMonthly(d); if(real<=0.5)return '';
  const shown=izRowAmt(d)+izStreamOther(d);
  if(Math.abs(real-shown)<1.5)return '';
  if(String(d.gap_ok||'')===String(Math.round(real)))return '';
  const cur=curSym(d), f=n=>cur+Math.round(n).toLocaleString('en-US');
  return `<div class="cmgap">⚠️ בפועל נגבה <b>${f(real)}</b> כל חודש, וכאן רשום ${f(shown)}`
    +(real>shown?' — כנראה חסרים אברכים ברשימה':' — כנראה נשאר חוב או שההתחייבות ירדה')
    +`<div class="cmgap-b noprint">`
    +`<button class="btn sm gapfix" data-amt="${Math.round(real)}">🔄 עדכן ל-${f(real)}</button>`
    +`<label class="gapfrom-l">החל מ<select class="gapfrom">${gapMonthOpts()}</select></label>`
    +`<button class="btn sm ghost gapok" data-amt="${Math.round(real)}">✓ זה בסדר</button></div></div>`;
}
/* מאיר: "ואז יהיה אפשרות בחירה מהחודש או מההתחלה שאבחר תאריך למשל ינואר,
   ואז הכל יסתדר גם אצל שאר תורמים שיש לי את הבעיה הזו איתם".
   טעפפער וסלקוביץ שותפים ביששכר־זבולון ונותנים 500 כל אחד מינואר, אבל
   רשום 1,000 לכל אחד. בחירת "מינואר" מתקנת את כל השנה בבת אחת, ולא רק
   מהחודש הזה והלאה. */
function gapMonthOpts(){
  const now=todayStr().slice(0,7), yr=GREGYEAR;
  const out=[`<option value="${now}">החודש (${fmtMonth(now)})</option>`];
  for(let m=12;m>=1;m--){
    const k=yr+'-'+String(m).padStart(2,'0');
    if(k>=now)continue;
    out.push(`<option value="${k}">${fmtMonth(k)}${m===1?' — מתחילת השנה':''}</option>`);
  }
  return out.join('');
}
function monthlyRows(d){
  const dupm=izDupPledges(d);
  const rows=[], pl=(d.pledges||[]).filter(p=>+p.monthly&&amtNum(p.amount)>0&&plReal(p)
    &&dupm.indexOf(p)<0);
  const izPl=pl.filter(p=>/יששכר/.test(String(p.category||'')));
  const iza=izRowAmt(d);
  if(iza>0)rows.push(['🤝 יששכר־זבולון',iza]);
  pl.filter(p=>izPl.indexOf(p)<0)
    .forEach(p=>rows.push(['🕯️ '+(p.category||'התחייבות'),amtNum(p.amount)]));
  return rows;
}
function monthlyTotal(d){return monthlyRows(d).reduce((s,r)=>s+r[1],0);}
/* ---------- 📋 ההתחייבויות של התורם — בלוק אחד בתחתית דף התורם ----------
   במקום הערות מפוזרות בכמה חלונות: שורה אחת לכל התחייבות — עבור מה ·
   כמה · קבוע או חד־פעמי — ולידה שורת הערה ידנית קצרה ("שילם מראש 4,500
   ב-13/7, מכסה עד אלול"). כאן גם האברכים שהוא מחזיק ודרגת הקוויטל,
   כדי שהכל ייקרא במקום אחד. */
// הכותרת של שורת התחייבות: הייעוד מהרשימה, ואחריו הפירוט של התורם עצמו
function plWhat(p){
  const c=String(p.category||'').trim()||'התחייבות', t=String(p.detail||'').trim();
  return t?(c+' — '+t):c;
}
/* ---------- מה מאיר רשם, ומה המערכת רק ראתה ----------
   מאיר: "אל תכתוב לי סתם סכומים בקבוע שהוא התחייב כזה סכום כי לעולם הוא
   לא התחייב כזה סכום". השדה הקבוע שבכרטיס הגיע מהייבוא — אצל חלק הוא
   החיוב החודשי ואצל חלק סך התרומות — ולכן שום סכום שלא נרשם ביד אינו
   התחייבות ואינו יוצר חוב. שלושה מצבים לשורה:
     1  — מאיר רשם. זו התחייבות, ורק היא נכנסת לחשבון.
     0  — המערכת הסיקה מהגבייה. הצעה שממתינה לאישור.
    -1  — נקבע שאין סכום התחייבות (תורם שמכניס מדי פעם לאתר).           */
const plConf=p=>(p&&p.confirmed!=null)?+p.confirmed:1;
const plEnded=p=>String((p&&p.status)||'')==='הסתיים';
// רק שורה שנרשמה ביד ועדיין בתוקף נחשבת התחייבות לכל חישוב
const plReal=p=>plConf(p)>0&&!plEnded(p);
function monthlyPledgesReal(d){return (d.pledges||[]).filter(p=>+p.monthly&&plReal(p));}
// מה שנכנס מהתורם בשנה הנוכחית — המספר שמוצג במקום סכום שהומצא
function obsYear(d){
  const by={};
  (d.donations||[]).forEach(x=>{const m=String(x.date||'').slice(0,7);
    if(m.length===7&&m.slice(0,4)===GREGYEAR)by[m]=(by[m]||0)+amtNum(x.amount);});
  const ms=Object.keys(by).sort(), sum=ms.reduce((a,m)=>a+by[m],0);
  return {sum, n:ms.length, first:ms[0]||'', last:ms[ms.length-1]||'',
          per:ms.length?sum/ms.length:0};
}
const isNightCat=c=>/פרנס|חדר קפה|ארוחת בוקר/.test(String(c||''));
function commitRows(d){
  const rows=[], dup=izDupPledges(d);
  // שורה כפולה של אותו כסף לא מוצגת כלל — מאיר: "זה מספיק, בלי הרבה
  // רישומים שאינם נצרכים ומסרבלים"
  const pl=(d.pledges||[]).filter(p=>dup.indexOf(p)<0);
  const izPl=pl.filter(p=>+p.monthly&&/יששכר/.test(String(p.category||'')));
  // יששכר־זבולון הוא אותו כסף של האברכים — שורה אחת בלבד, לא פעמיים
  const iza=izRowAmt(d);
  if(iza>0.5||izPl.length){
    // יששכר־זבולון נחשב רשום כשיש לו שורה מפורשת או אברכים עם סכום —
    // ואם הסכום רק הוסק מהגבייה, זו הצעה ולא התחייבות.
    let byav=0; try{byav=izSummary(d).monthly*( (d.partners||[]).some(p=>p.active!=0)?1:0 );}catch(e){}
    const izReal=izPl.some(p=>plConf(p)>0)||byav>0.5;
    // החודש שממנו הסכום תקף, והסכום שהיה נהוג לפניו — נלקחים מהשורה
    // עצמה, אחרת עדכון של יששכר־זבולון היה נספר על כל השנה אחורה
    const izOne=izPl.length===1?izPl[0]:null;
    rows.push({iz:1,what:'יששכר־זבולון',icon:'🤝',mo:1,amt:iza,
      pid:(izOne?izOne.id:''),
      conf:izReal?1:0, ended:!!izOne&&plEnded(izOne),
      since:izOne?String(izOne.since||''):'',
      prev:izOne?amtNum(izOne.prev_amount):0,
      guess:!izPl.length,
      praw:'',note:String(d.iz_note||'')});
  }
  pl.filter(p=>izPl.indexOf(p)<0).forEach(p=>{
    const plan=plPlan(d,p);
    const viaD=viaDonorOf(p);
    rows.push({pid:p.id,what:plWhat(p),
      icon:plEnded(p)?'🏁':(plConf(p)<0?'🔁':(+p.monthly?'🔁':(plan?'📆':'🎯'))),
      mo:+p.monthly?1:0, inst:plan?1:0, plan,
      conf:plConf(p), ended:plEnded(p), since:String(p.since||''),
      prev:amtNum(p.prev_amount),
      amt:amtNum(p.amount),praw:String(p.paid||''),
      got:plCollected(d,p), left:plLeft(d,p),
      via:viaD?{id:viaD.id,name:(viaD.last+' '+viaD.first).trim(),
        total:amtNum(p.via_total),note:String(p.via_note||'')}:null,
      avreich:String(p.avreich||''), note:String(p.note||'')});});
  // סכום קבוע שנשאר בשדה הישן בלי שורה משלו — מוצג כהצעה בלבד, כי גם
  // הוא הגיע מהייבוא ולא ממאיר
  if(!rows.length&&amtNum(d.amount)>0)
    rows.push({legacy:1,what:(purposeList(d)[0]||'קבוע'),icon:'🔁',mo:1,conf:0,
      amt:amtNum(d.amount),praw:'',note:''});
  return rows;
}
function commitHTML(d){
  const cur=curSym(d), f=n=>cur+Math.round(n).toLocaleString('en-US');
  const rows=commitRows(d), av=(d.partners||[]).filter(p=>p.active!=0);
  const tier=TIERS[d.tier]?(d.tier==='יששכר_זבולון'?'יששכר־זבולון':('קוויטל '+TIERS[d.tier][0])):'';
  // בסיכום למעלה נספר רק מה שנרשם ביד ועדיין בתוקף
  const real=rows.filter(r=>r.conf>0&&!r.ended);
  const mo=real.filter(r=>r.mo).reduce((s,r)=>s+r.amt,0);
  const inst=real.filter(r=>r.inst).reduce((s,r)=>s+r.plan.per,0);
  const ob=obsYear(d);
  // שורה שהסכום שלה הוסק מהגבייה, או שנקבע שאין בה סכום — אין ממנה חוב,
  // ורואים בה רק מה שבאמת נכנס. מכאן מאיר מאשר או מבטל בלחיצה אחת.
  const askLine=r=>{
    const btns=`<div class="cmask-b noprint">`
      +(r.amt>0.5?`<button class="btn sm cmyes" data-pid="${r.pid||''}" ${r.iz?'data-iz="1"':''}>✓ כן — ${f(r.amt)} לחודש</button>`:'')
      +`<button class="btn sm ghost cmno" data-pid="${r.pid||''}" ${r.iz?'data-iz="1"':''}>✕ לא התחייב סכום</button></div>`;
    if(r.conf<0)
      return `<div class="cmask off">🔁 נותן מדי פעם, בלי סכום קבוע — אין כאן חוב.`
        +(ob.sum>0.5?` נכנס ממנו השנה <b>${f(ob.sum)}</b> ב-${ob.n} ${ob.n===1?'חודש':'חודשים'}.`:'')
        +`<div class="cmask-b noprint"><button class="btn sm ghost cmset" data-pid="${r.pid||''}">✎ בעצם כן התחייב סכום</button></div></div>`;
    return `<div class="cmask">❔ לא רשום שהוא התחייב סכום. ${r.legacy?'הסכום':'הסכום שכאן'} הגיע מהייבוא, לא ממך.`
      +(ob.sum>0.5?` בפועל נכנס ממנו השנה <b>${f(ob.sum)}</b> ב-${ob.n} ${ob.n===1?'חודש':'חודשים'} — ${f(ob.per)} בממוצע לחודש.`:' ולא נכנס ממנו כסף השנה.')
      +` אפשר לאשר, לתקן את הסכום למעלה, או לקבוע שאין התחייבות.${btns}</div>`;
  };
  const line=r=>{
    // גם שורת יששכר־זבולון ניתנת לתיקון ידני. מאיר על פינטער: "הוא התחייב
    // 12,000 לכולל הוראה ועוד 800 ליששכר־זבולון עם המלי" — הסכום שהמערכת
    // הסיקה מהגבייה הוא הצעה בלבד, ומה שנכתב כאן גובר עליו.
    const ask=r.conf<=0;                       // סכום שלא נרשם ביד — לא חוב
    const amt=(r.pid||r.iz)
      ? `<input class="cmamt" ${r.iz?'data-iz="1"':''} data-pid="${r.pid||''}" value="${esc(r.amt||'')}" inputmode="decimal" placeholder="0">`
        + `<button class="btn sm cmsave noprint" ${r.iz?'data-iz="1"':''} data-pid="${r.pid||''}" title="שמור את השורה">💾</button>`
      : `<b class="cmfix">${r.amt?f(r.amt):'—'}</b>`;
    const tag=r.ended?'הסתיים':(ask?(r.conf<0?'בלי סכום':'לא אושר')
                                   :(r.mo?'קבוע':(r.inst?'בתשלומים':'חד־פעמי')));
    // התחייבות בתשלומים מתעדכנת לבד לפי מה שנגבה בייעוד הזה
    const pn=r.plan||{};
    const prog=(r.inst&&!ask&&!r.ended)
      ? `<div class="cminst">📆 ${f(pn.per)} לחודש${pn.from?(' · החל מ'+esc(monthPlus(pn.from,0))):''}`
        +` · שולם ${f(r.amt-r.left)} מתוך ${f(r.amt)}`
        +(r.left>0.5?` · <b class="cmleft no">נשאר ${f(r.left)}</b> · עוד ${pn.n} ${pn.n===1?'תשלום':'תשלומים'}`
                    +(pn.end?` (עד ${esc(pn.end)})`:'')
                   :' · <b class="cmleft ok">הושלם ✓</b>')
        +`</div>`
        +(pn.from&&pn.due>pn.done
          ? `<div class="cmdue">📅 לפי הלוח כבר אמורים לעבור ${pn.due} תשלומים, ורשומים ${pn.done}`
            +` — כנראה עדיין לא נקלט קובץ הבנק האחרון</div>` : '')
        +(r.got>0.5
          ? `<span class="cmpaid"><small>המספרים כאן לפי מה שנקלט במערכת — כשייכנס קובץ הבנק הבא זה יתעדכן לבד</small></span>`
          : `<span class="cmpaid">שולם עד היום <input class="cmpd" data-pid="${r.pid}" value="${esc(r.praw)}" inputmode="decimal" placeholder="0">`
            +`<small>${pn.done?(pn.done+' מתוך '+pn.all+' תשלומים'):'עדיין לא שולם'}</small></span>`)
      : '';
    // תשלום אחד: ירוק כשנגבה, אדום עם "לא נגבה" כשעדיין לא
    const done=r.amt>0.5&&r.left<=0.5;
    const paid=(!r.mo&&!r.inst&&r.pid&&!ask&&!r.ended)
      ? `<span class="cmpaid ${r.amt?(done?'ok':'no'):''}">שילם <input class="cmpd" data-pid="${r.pid}" value="${esc(r.praw)}" inputmode="decimal" placeholder="0">`
        +(r.amt?(done?'<b class="cmleft ok">✓ נגבה במלואו</b>'
                     :`<b class="cmleft no">נשאר ${f(r.left)}</b><small class="cmnog">לא נגבה</small>`):'')
        +(r.got>0.5?`<small>נגבו ${f(r.got)} במערכת</small>`:'')+`</span>`
      : '';
    const note=(r.iz||r.pid)
      ? `<input class="cmnote" ${r.iz?'data-iz="1"':`data-pid="${r.pid}"`} value="${esc(r.note)}"`
        +` placeholder="${r.iz?('הערה: שילם מראש '+cur+'4,500, מכסה עד אלול'):'הערה'}">`
      : '<div class="hintxt">בחר עבור מה למטה כדי לקבוע לו שורה משלו</div>';
    const st=r.ended?' ended':(ask?' ask'
             :((!r.mo&&r.amt>0.5)?(r.left<=0.5?' done':' owe'):''));
    // מאיר על קייזרי: "הוא התחייב בהתחלה את הסכומים שהוא נתן וזה נגמר לו,
    // זה לא אומר שכל חודש עכשיו הוא צריך לשלוח" — התחייבות שהסתיימה
    // נשארת לתיעוד, מסומנת, ואינה נכנסת לשום חשבון.
    const endBtn=(r.pid&&!ask)
      ? `<button class="cmendb noprint" data-pid="${r.pid}" data-on="${r.ended?1:0}"
           title="${r.ended?'החזר לפעילה':'סמן שההתחייבות הסתיימה'}">${r.ended?'↩':'🏁'}</button>` : '';
    // שותפות תשלום: הכסף שלו נכנס דרך כרטיס של תורם אחר. מאיר: "שולחים
    // 2000 ביחד, אז אלף זה של לאקס — ושלא יצבור חוב". זמין לכל שורה,
    // לא רק ליששכר־זבולון.
    const viaBtn=(r.pid&&!ask&&!r.ended&&!r.iz)
      ? `<button class="cmviab noprint" data-pid="${r.pid}" title="משולם ביחד עם תורם אחר">🤝</button>` : '';
    const viaInfo=r.via
      ? `<div class="cmvia">🤝 משולם ביחד עם <span class="cosp2" data-did="${r.via.id}">${esc(r.via.name)} ↗</span>`
        +(r.via.total>0.5?(' — '+f(r.via.total)+' ביחד, '+f(r.amt)+' שלו'):'')
        +(r.via.note?(' · '+esc(r.via.note)):'')+`</div>` : '';
    const viaEdit=(r.pid&&!ask&&!r.ended&&!r.iz)
      ? `<div class="cmviaed hidden" data-pid="${r.pid}">
          <input class="rvia_q" placeholder="חפש את שם התורם שדרכו זה נכנס…">
          <div class="rvia_res"></div>
          <div class="rvia_sel hidden"></div>
          <div class="cmrow2"><input class="rvia_tot" inputmode="decimal" placeholder="הסכום הכולל שנשלח ביחד" value="${r.via?esc(r.via.total||''):''}">
          <input class="rvia_note" placeholder="הערה — למשל: דרך המשרד" value="${r.via?esc(r.via.note):''}"></div>
          <div class="cmask-b"><button class="btn sm rvia_save" data-pid="${r.pid}">💾 שמור</button>
          ${r.via?`<button class="btn sm ghost rvia_clear" data-pid="${r.pid}">✕ בטל שותפות</button>`:''}
          <button class="btn sm ghost rvia_close">סגור</button></div></div>` : '';
    return `<div class="cmrow${st}">
      <div class="cmhead"><span class="cmwhat">${r.icon} ${esc(r.what)}</span>
        ${amt}<span class="cmtag ${r.ended?'end':(ask?'ask':(r.mo?'mo':(r.inst?'inst':'one')))}">${tag}</span>
        ${viaBtn}${endBtn}${r.pid?`<button class="del cmdel" data-pid="${r.pid}" title="מחק שורה">🗑</button>`:'<span class="cmpad"></span>'}</div>
      ${ask?askLine(r):''}
      ${r.ended?'<div class="cmask off">🏁 ההתחייבות הזו הסתיימה — היא לא נספרת יותר ואין ממנה חוב.</div>':''}
      ${r.avreich?`<div class="cmav">👨‍🎓 ${esc(r.avreich)}</div>`:''}
      ${viaInfo}${viaEdit}
      ${prog}${paid}
      ${note}
      ${(r.mo&&(r.pid||r.iz)&&!ask&&!r.ended)
        ? `<label class="cmsince">📅 מאז <input type="month" class="cmsincei" data-pid="${r.pid||''}"
             ${r.iz?'data-iz="1"':''} value="${esc((r.since||'').slice(0,7))}"><small>מכאן נספרים החודשים והחוב</small></label>` : ''}
      ${r.iz&&!ask&&!r.ended?izGapNote(d):''}
      ${r.iz?av.map(p=>`<div class="cmav${avOpenSlot(p)?' cmavgap':''}">${avOpenSlot(p)
        ?('🚪 מקום פתוח — '+esc(p.prev_avreich)+' יצא'+(p.prev_ended?(' ב'+esc(p.prev_ended)):''))
        :('👨‍🎓 '+esc(p.avreich||'—'))}${amtNum(p.amount)?(' · '+f(amtNum(p.amount))):''}${coHolderNamesHtml(p)}${+p.joint?' <small class="jointbadge">🤝 ביחד</small>':''}${p.paid_thru?(' <small class="izstart">💵 שולם עד '+esc(fmtMonth(p.paid_thru))+'</small>'):''}</div>`).join(''):''}
    </div>`;
  };
  // מי משלם דרך הכרטיס הזה עבור התחייבות של תורם אחר — מידע בלבד,
  // כדי שיראה שחלק ממה שהוא שולח לא באמת שלו
  const viaIn=viaLinkedIn(d);
  const viaInHTML=viaIn.length
    ? `<div class="cmviain">${viaIn.map(({from,p})=>{
        const nm=(from.last+' '+from.first).trim(), sh=amtNum(p.amount);
        return `<div>📥 <span class="cosp2" data-did="${from.id}">${esc(nm)} ↗</span> — ${sh?(f(sh)+' מתוך מה שנכנס כאן שייך ל'+esc(plWhat(p))+' שלו'):('חלק ממה שנכנס כאן שייך ל'+esc(plWhat(p))+' שלו')}</div>`;
      }).join('')}</div>` : '';
  // טופס ההוספה: ייעוד מהרשימה, פירוט חופשי שנשאר אצל התורם בלבד,
  // ולפי הייעוד — בחירת לילה או בחירת אברך.
  const add=`<div class="cmadd">
      <select class="cm_cat">${dnCatOpts('')}</select>
      <div class="addrow hidden cm_newrow"><input class="cm_new" placeholder="שם הייעוד החדש…"></div>
      <input class="cm_det" placeholder="פירוט אצל התורם הזה בלבד — למשל: כיסוי רדיאטורים ומעקות">
      <div class="cmpick hidden cm_avbox"><label class="cmlbl">👨‍🎓 איזה אברך?</label>
        <select class="cm_av">${avOpts('')}</select>
        <div class="addrow hidden cm_avnewrow"><input class="cm_avnew" placeholder="שם האברך החדש">
          <button class="btn sm cm_avadd">➕ הוסף</button></div></div>
      <div class="cmpick hidden cm_nightbox"><label class="cmlbl">🌙 איזה לילה?</label>
        <div class="cmthree"><select class="cm_hm">${HMORD.map(m=>`<option>${m}</option>`).join('')}</select>
          <select class="cm_hd">${[...Array(30)].map((_,i)=>`<option value="${i+1}">${heDay(i+1)}</option>`).join('')}</select>
          <select class="cm_hy">${heYearOpts()}</select></div></div>
      <button type="button" class="opnlink cm_via_tgl">🤝 משולם ביחד עם תורם אחר? (לא נכנס בכרטיס שלו)</button>
      <div class="opnbox hidden cm_viabox">
        <div class="hintxt" style="margin:0 0 5px">כשהכסף נכנס בפועל בכרטיס של מישהו אחר — למשל שניהם שולחים יחד דרך אותו משרד — כתוב כאן מי זה וכמה מתוך הסכום המשותף שייך לתורם הזה.</div>
        <input class="cm_via_q" placeholder="חפש את שם התורם שדרכו זה נכנס…">
        <div class="cm_via_res"></div>
        <div class="cm_via_sel hidden"></div>
        <div class="cmrow2"><input class="cm_via_tot" inputmode="decimal" placeholder="הסכום הכולל שנשלח ביחד">
        <input class="cm_via_note" placeholder="הערה — למשל: דרך המשרד"></div></div>
      <div class="cmrow2">
        <input class="cm_amt" inputmode="decimal" placeholder="כמה">
        <select class="cm_plan">
          <option value="mo">🔁 קבוע כל חודש</option>
          <option value="inst">📆 בתשלומים</option>
          <option value="one">🎯 חד־פעמי</option></select>
        <input class="cm_n hidden" inputmode="numeric" placeholder="לכמה תשלומים?">
        <button class="btn sm cm_add">➕ הוסף</button></div>
      <div class="cmstart hidden">
        <label class="cmlbl cmstartl">התחייבות שכבר רצה? מלא מאיזה חודש התחילה וכמה תשלומים כבר עברו</label>
        <div class="cmthree"><input type="month" class="cm_from">
          <input class="cm_done" inputmode="numeric" placeholder="כמה תשלומים כבר שולמו"></div>
        <label class="cmmerge hidden"><input type="checkbox" class="cm_merge" checked>
          <span class="cm_mergetxt"></span></label></div>
      <div class="hintxt cm_calc"></div></div>`;
  return `<div class="cmbox"><div class="cmbox-t">📋 ההתחייבויות שלו
      ${mo?`<span class="cmtot">${f(mo)} לחודש</span>`:''}
      ${inst?`<span class="cmtot inst">+${f(inst)} בתשלומים</span>`:''}</div>
    ${viaInHTML}
    ${rows.map(line).join('')||'<div class="hintxt">אין עדיין התחייבות רשומה. הוסף שורה למטה.</div>'}
    <details class="dsec cmsub"><summary>➕ הוספת התחייבות / הוראת קבע</summary>
    ${add}</details>
    <details class="dsec cmsub" id="dnbox"><summary>💵 רישום תרומה שנכנסה</summary>
    <div class="hintxt" style="margin:2px 2px 7px">שלושה שדות וזהו — כמה, מתי, ואיך. כל השאר לא חובה.</div>
    <div class="two"><label class="fld"><span>💲 כמה</span><div class="curwrap"><select id="dn_cur" class="curpick">${curOpts(cur)}</select><input id="dn_amt" inputmode="decimal" placeholder="480"></div></label>
    <label class="fld"><span>📅 מתי</span><input id="dn_date" type="date"></label></div>
    <div class="two"><label class="fld"><span>איך נתרם</span><select id="dn_method">${dnMethList().map(x=>`<option${x===chLabel(d.channel||'')?' selected':''}>${esc(x)}</option>`).join('')}</select></label>
    <label class="fld"><span>עבור מה</span><select id="dn_cat">${dnCatOpts('')}
    <option value="פרנס לילה" data-day="parnes">🌙 פרנס לילה (בחר יום)</option>
    <option value="חדר קפה" data-day="coffee">☕ חדר קפה (בחר יום)</option>
    <option value="ארוחת בוקר" data-day="breakfast">🍳 ארוחת בוקר (בחר יום)</option></select></label></div>
    <div class="addrow hidden" id="dn_newrow"><input id="dn_catfree" placeholder="שם הייעוד החדש"></div>
    <label class="fld hidden" id="dn_bldg_l"><span>🏗️ מה תרם בבניין?</span><input id="dn_bldg" list="bldgitems2" placeholder="שולחן / עמוד / מטר…"><datalist id="bldgitems2">${(BUILDING_ITEMS||[]).map(x=>`<option value="${esc(x)}">`).join('')}</datalist></label>
    <div class="hidden" id="dn_daybox"><div class="two"><label class="fld"><span>חודש עברי</span><select id="dn_hm">${HMORD.map(m=>`<option>${m}</option>`).join('')}</select></label>
    <label class="fld"><span>יום</span><select id="dn_hd">${[...Array(30)].map((_,i)=>`<option value="${i+1}">${heDay(i+1)}</option>`).join('')}</select></label></div>
    <label class="fld"><span>שנה עברית</span><select id="dn_hy">${heYearOpts()}</select></label></div>
    <div class="two hidden" id="dn_ccbox"><label class="fld"><span>4 ספרות אחרונות</span><input id="dn_cc4" inputmode="numeric" maxlength="4" placeholder="1234"></label>
    <label class="fld"><span>תוקף</span><input id="dn_ccexp" placeholder="12/28" style="direction:ltr"></label></div>
    <label class="jointchk"><input type="checkbox" id="dn_rep"> 🔁 העביר את הסכום הזה <b>כל חודש</b> — רשום שורה לכל חודש</label>
    <div class="two hidden" id="dn_repbox"><label class="fld"><span>מחודש</span><input type="month" id="dn_from"></label>
      <label class="fld"><span>עד חודש</span><input type="month" id="dn_to"></label></div>
    <div class="hintxt hidden" id="dn_rephint"></div>
    <button type="button" class="opnlink" id="dn_more">➕ הערה ושם לתפילה (לא חובה)</button>
    <div class="opnbox hidden" id="dn_morebox">
      <label class="fld"><span>הערה</span><input id="dn_note" placeholder="פירוט קצר"></label>
      <label class="fld"><span>📌 מזה על שנה קודמת (${GREGYEAR-1} ואחורה)</span>
        <div class="curwrap"><span class="curpick curfix">${cur}</span>
          <input id="dn_prev" inputmode="decimal" placeholder="כמה"></div></label>
      <label class="fld"><span>עבור מה החלק הזה</span>
        <input id="dn_prevn" placeholder="למשל: יששכר־זבולון ${GREGYEAR-1}"></label>
      <div class="hintxt" style="margin:-6px 2px 6px">כשתשלום אחד סוגר גם חוב ישן — רשום כאן כמה מתוכו הלך לשנה שעברה.
        הסכום הזה יוצא מחשבון ${GREGYEAR} ונזקף כנגד ההתחייבות הקודמת.</div>
      <label class="fld"><span>🕯️ שם לתפילה</span><textarea id="dn_pray" rows="2" placeholder="יעקב בן שרה לרפואה שלמה"></textarea></label></div>
    <button class="btn" id="dn_add" style="width:100%;margin-top:8px">💾 שמור תרומה</button></details>
    <div class="cmopen"><button type="button" class="opnlink" id="f_opn">📌 התחייבות קודמת (לפני 2026)${amtSigned(d.debt_open)?(' · '+cur+Math.round(amtSigned(d.debt_open))):''}</button>
      <div class="opnbox hidden" id="f_opnbox">
        <div class="hintxt" style="margin:0 0 5px">התרומות במערכת מתחילות מינואר 2026. כאן רושמים מה הוא התחייב ולא נתן לפני כן — או מינוס, אם שילם מראש. הסכום נכנס לשורת החוב שבראש הכרטיס.</div>
        <div class="two"><input id="f_debt_open" value="${esc(d.debt_open||'')}" inputmode="decimal" placeholder="0">
          <input id="f_debt_open_note" value="${esc(d.debt_open_note||'')}" placeholder="עבור מה — למשל: קמחא דפסחא תשפ\"ה"></div></div></div>
  </div>`;
}
function wireCommit(d,body){
  const box=body.querySelector('.cmbox'); if(!box)return;
  const redraw=()=>{cardDetails(d,body);if(tab==='donors')renderDonors();};
  // הסכום הקבוע בכרטיס מסונכרן לשורות רק אצל מי שאין לו אברכים. אצל תורם
  // עם אברכים הסכום שבכרטיס הוא עדות היסטורית (אצל פינטער 12,800 שנגבים
  // בפועל), ואסור שהוספת שורה אחרת תדרוס אותו.
  const syncAmt=async()=>{
    if((d.partners||[]).some(p=>p.active!=0))return;
    d.amount=String(fixTotal(d)||'');
    await api('PUT','/api/donor/'+d.id,{amount:d.amount});};
  const putPl=async(p,fields)=>{Object.assign(p,fields);
    await api('PUT','/api/pledge/'+p.id,{category:p.category||'',amount:p.amount||'',
      status:p.status||'',note:p.note||'',monthly:+p.monthly?1:0,paid:p.paid||'',
      detail:p.detail||'',permo:p.permo||'',avreich:p.avreich||'',
      confirmed:(p.confirmed!=null?+p.confirmed:1),
      via_donor_id:p.via_donor_id||'',via_total:p.via_total||'',via_note:p.via_note||'',
      since:p.since||'',prev_amount:p.prev_amount||''});};
  const pOf=pid=>(d.pledges||[]).find(x=>String(x.id)===String(pid));
  // סכום ידני שנשאר לצד תשלומים שנקלטו במערכת יוצר שני מספרים סותרים
  // על אותה שורה. מה שנקלט הוא הקובע, ולכן הידני נמחק פעם אחת.
  (d.pledges||[]).forEach(p=>{
    if(amtNum(p.paid)>0.5&&plCollected(d,p)>0.5){
      p.paid=''; api('PUT','/api/pledge/'+p.id,{category:p.category||'',
        amount:p.amount||'',status:p.status||'',note:p.note||'',
        monthly:+p.monthly?1:0,paid:'',detail:p.detail||'',
        permo:p.permo||'',avreich:p.avreich||''});
    }});
  box.querySelectorAll('.cmamt').forEach(inp=>inp.onchange=async()=>{
    if(inp.dataset.busy)return; inp.dataset.busy='1';
    try{ await saveAmt(inp); } finally{ delete inp.dataset.busy; }});
  const saveAmt=async inp=>{
    const v=inp.value.trim();
    let p=pOf(inp.dataset.pid);
    // תיקון שורת יששכר־זבולון שאין לה עדיין שורה משלה — נפתחת אחת,
    // ומאותו רגע הסכום שנכתב הוא הקובע ולא ההערכה מהגבייה.
    // אם כבר יש שורת יש"ז — מעדכנים אותה, ולא פותחים עוד אחת.
    if(!p&&inp.dataset.iz)
      p=(d.pledges||[]).find(x=>+x.monthly&&isIZcat(x.category));
    if(!p&&inp.dataset.iz){
      const r=await api('POST','/api/pledge',{donor_id:d.id,category:'יששכר־זבולון',
        amount:v,status:'נתן',monthly:1,paid:''});
      if(!r||!r.id){toast('לא נשמר');return;}
      p={id:r.id,donor_id:d.id,category:'יששכר־זבולון',amount:v,status:'נתן',
         monthly:1,paid:'',note:'',detail:'',permo:'',avreich:'',date:todayStr()};
      d.pledges=(d.pledges||[]).concat([p]);
    }
    if(!p)return;
    // סכום שנכתב כאן ביד הוא התחייבות מאושרת — מאותו רגע זו האמת ולא הצעה
    await putPl(p,{amount:v,confirmed:1});
    // אברך יחיד — הסכום שלו הולך יחד עם ההתחייבות, שלא יישארו שני מספרים
    if(inp.dataset.iz!==undefined||isIZcat(p.category)){
      const act=(d.partners||[]).filter(x=>x.active!=0);
      if(act.length===1&&amtNum(act[0].amount)!==amtNum(v)){
        act[0].amount=v; await api('PUT','/api/partner/'+act[0].id,{amount:v});
      }
    }
    await syncAmt(); toast('נשמר ✓'); redraw();};
  box.querySelectorAll('.cmsave').forEach(btn=>btn.onclick=async()=>{
    if(btn.dataset.busy)return; btn.dataset.busy='1';
    const row=btn.closest('.cmrow');
    try{
      const nt=row&&row.querySelector('.cmnote');
      if(nt){
        if(nt.dataset.iz){d.iz_note=nt.value.trim();
          await api('PUT','/api/donor/'+d.id,{iz_note:d.iz_note});}
        else{const q=pOf(nt.dataset.pid); if(q)await putPl(q,{note:nt.value.trim()});}
      }
      const pd=row&&row.querySelector('.cmpd');
      if(pd){const q=pOf(pd.dataset.pid);
        if(q){const paid=pd.value.trim();
          await putPl(q,{paid,status:(amtNum(q.amount)&&amtNum(paid)>=amtNum(q.amount))?'נתן':'טרם'});}}
      const ai=row&&row.querySelector('.cmamt');
      if(ai)await saveAmt(ai);            // שומר, מודיע ומצייר מחדש
      else{toast('נשמר ✓'); redraw();}
    } finally{ delete btn.dataset.busy; }});
  // מאיר: "איך אני מוסיף ממתי ההתחייבות שלו?" — על שורה שכבר קיימת,
  // ולא רק בטופס ההוספה. מכאן נספרים החודשים והחוב.
  box.querySelectorAll('.cmsincei').forEach(inp=>inp.onchange=async()=>{
    if(inp.dataset.busy)return; inp.dataset.busy='1';
    try{ await saveSince(inp); } finally{ delete inp.dataset.busy; }});
  const saveSince=async inp=>{
    let p=pOf(inp.dataset.pid);
    // שורת יששכר־זבולון שנגזרת מהאברכים ואין לה עדיין שורה משלה —
    // נפתחת אחת ברגע שנקבע לה חודש התחלה, כדי שיהיה איפה לשמור
    if(!p&&inp.dataset.iz){
      p=(d.pledges||[]).find(x=>+x.monthly&&isIZcat(x.category));
      if(!p){
        const amt=String(izRowAmt(d)||'');
        const r=await api('POST','/api/pledge',{donor_id:d.id,category:'יששכר־זבולון',
          amount:amt,status:'נתן',monthly:1,paid:'',since:inp.value||''});
        if(!r||!r.id){toast('לא נשמר');return;}
        p={id:r.id,donor_id:d.id,category:'יששכר־זבולון',amount:amt,status:'נתן',
           monthly:1,paid:'',note:'',detail:'',permo:'',avreich:'',
           since:inp.value||'',date:todayStr()};
        d.pledges=(d.pledges||[]).concat([p]);
        toast(inp.value?('נספר מ'+fmtMonth(inp.value)+' ✓'):'נשמר ✓');
        redraw(); return;
      }
    }
    if(!p)return;
    await putPl(p,{since:inp.value||''});
    toast(inp.value?('נספר מ'+fmtMonth(inp.value)+' ✓'):'בוטל — נספר מהחודש הראשון שנכנס בו כסף');
    redraw();};
  box.querySelectorAll('.cmpd').forEach(inp=>inp.onchange=async()=>{
    const p=pOf(inp.dataset.pid); if(!p)return;
    const paid=inp.value.trim();
    await putPl(p,{paid,status:(amtNum(p.amount)&&amtNum(paid)>=amtNum(p.amount))?'נתן':'טרם'});
    toast('עודכן ✓'); redraw();});
  // שורת ההערה — היא הלב של הסידור. אצל יששכר־זבולון נשמרת בהערת היש"ז
  box.querySelectorAll('.cmnote').forEach(inp=>inp.onchange=async()=>{
    if(inp.dataset.iz){d.iz_note=inp.value.trim();
      await api('PUT','/api/donor/'+d.id,{iz_note:d.iz_note});toast('נשמר ✓');return;}
    const p=pOf(inp.dataset.pid); if(!p)return;
    await putPl(p,{note:inp.value.trim()}); toast('נשמר ✓');});
  // ----- אישור סכום שהמערכת הסיקה, או קביעה שאין התחייבות בכלל -----
  // שורה שאין לה עדיין רשומה משלה (יששכר־זבולון מוסק, או הסכום הישן
  // שבכרטיס) נפתחת כאן פעם אחת, כדי שההחלטה תישמר ולא תחזור בכל טעינה.
  const rowPledge=async b=>{
    let p=pOf(b.dataset.pid);
    if(p)return p;
    const iz=!!b.dataset.iz;
    const cat=iz?'יששכר־זבולון':((purposeList(d)[0]||'קבוע'));
    if(iz)p=(d.pledges||[]).find(x=>+x.monthly&&isIZcat(x.category));
    if(p)return p;
    const r=await api('POST','/api/pledge',{donor_id:d.id,category:cat,
      amount:'',status:'נתן',monthly:1,paid:'',confirmed:0});
    if(!r||!r.id){toast('לא נשמר');return null;}
    p={id:r.id,donor_id:d.id,category:cat,amount:'',status:'נתן',monthly:1,
       paid:'',note:'',detail:'',permo:'',avreich:'',confirmed:0,date:todayStr()};
    d.pledges=(d.pledges||[]).concat([p]);
    return p;};
  box.querySelectorAll('.cmyes').forEach(b=>b.onclick=async()=>{
    if(b.dataset.busy)return; b.dataset.busy='1';
    try{
      const p=await rowPledge(b); if(!p)return;
      const row=b.closest('.cmrow'), inp=row&&row.querySelector('.cmamt');
      const v=(inp&&inp.value.trim())||p.amount||'';
      await putPl(p,{amount:v,confirmed:1});
      await syncAmt(); toast('נרשם כהתחייבות ✓'); redraw();
    } finally{ delete b.dataset.busy; }});
  box.querySelectorAll('.cmno').forEach(b=>b.onclick=async()=>{
    if(b.dataset.busy)return; b.dataset.busy='1';
    try{
      const p=await rowPledge(b); if(!p)return;
      await putPl(p,{amount:'',confirmed:-1});
      await syncAmt(); toast('נקבע: אין סכום התחייבות'); redraw();
    } finally{ delete b.dataset.busy; }});
  box.querySelectorAll('.cmset').forEach(b=>b.onclick=async()=>{
    const p=pOf(b.dataset.pid); if(!p)return;
    await putPl(p,{confirmed:0}); toast('אפשר לכתוב את הסכום למעלה'); redraw();});
  // התחייבות שנגמרה — נשארת לתיעוד ולא נספרת יותר
  box.querySelectorAll('.cmendb').forEach(b=>b.onclick=async()=>{
    const p=pOf(b.dataset.pid); if(!p)return;
    const on=b.dataset.on==='1';
    await putPl(p,{status:on?'נתן':'הסתיים'});
    await syncAmt(); toast(on?'חזרה לפעילה':'סומן כהסתיים'); redraw();});
  // ----- סגירת ההערה האדומה על הפער -----
  // "עדכן מהחודש": הסכום החדש נרשם יחד עם החודש שממנו הוא תקף, ולכן
  // החודשים שלפניו נספרים לפי הסכום הקודם ולא נוצר חוב או זכות מדומים.
  box.querySelectorAll('.gapfix').forEach(b=>b.onclick=async()=>{
    if(b.dataset.busy)return; b.dataset.busy='1';
    try{
      const v=b.dataset.amt;
      const sel=b.closest('.cmgap-b')&&b.closest('.cmgap-b').querySelector('.gapfrom');
      const mo=(sel&&sel.value)||todayStr().slice(0,7);
      let p=(d.pledges||[]).find(x=>+x.monthly&&isIZcat(x.category));
      // הסכום שהיה עד עכשיו נשמר, כדי שהחודשים שלפני החודש שנבחר
      // ייספרו לפיו ולא ייעלמו מהחשבון
      const old=String(Math.round(izRowAmt(d))||'');
      if(!p){
        const r=await api('POST','/api/pledge',{donor_id:d.id,category:'יששכר־זבולון',
          amount:v,status:'נתן',monthly:1,paid:'',confirmed:1,since:mo,prev_amount:old});
        if(!r||!r.id){toast('לא נשמר');return;}
        p={id:r.id,donor_id:d.id,category:'יששכר־זבולון',amount:v,status:'נתן',monthly:1,
           paid:'',note:'',detail:'',permo:'',avreich:'',confirmed:1,since:mo,prev_amount:old};
        d.pledges=(d.pledges||[]).concat([p]);
      } else await putPl(p,{amount:v,confirmed:1,since:mo,prev_amount:old});
      const act=(d.partners||[]).filter(x=>x.active!=0);
      if(act.length===1){act[0].amount=v;await api('PUT','/api/partner/'+act[0].id,{amount:v});}
      // הסכום הקבוע שבראש הכרטיס מתעדכן גם הוא, אחרת היה נשאר מוצג
      // הסכום הישן ליד השורה המתוקנת. יש כאן התחייבות חיה, ולכן הסכום
      // לעולם אינו מתאפס — גם אצל תורם שיש לו אברכים פעילים.
      const tot=fixTotal(d);
      d.gap_ok=String(v);
      await api('PUT','/api/donor/'+d.id,
        tot>0.5?{gap_ok:d.gap_ok,amount:String(Math.round(tot))}:{gap_ok:d.gap_ok});
      if(tot>0.5)d.amount=String(Math.round(tot));
      toast('עודכן ל-'+v+' החל מ'+fmtMonth(mo)+' ✓'); redraw();
    } finally{ delete b.dataset.busy; }});
  // "זה בסדר": הסכום נשאר, ההערה נסגרת, והיא תחזור רק אם הגבייה תשתנה שוב
  box.querySelectorAll('.gapok').forEach(b=>b.onclick=async()=>{
    d.gap_ok=String(b.dataset.amt);
    await api('PUT','/api/donor/'+d.id,{gap_ok:d.gap_ok});
    toast('נסגר ✓'); redraw();});
  box.querySelectorAll('.cmdel').forEach(b=>b.onclick=async()=>{
    const p=pOf(b.dataset.pid); if(!p)return;
    if(!await uiConfirm('למחוק את השורה "'+plWhat(p)+'"?'))return;
    await api('DELETE','/api/pledge/'+p.id);
    d.pledges=(d.pledges||[]).filter(x=>String(x.id)!==String(p.id));
    await syncAmt(); toast('נמחק'); redraw();});
  // שותפות תשלום על שורה קיימת — עריכה/ביטול, אותו רעיון כמו בטופס ההוספה
  box.querySelectorAll('.cmviab').forEach(b=>b.onclick=()=>{
    const ed=box.querySelector('.cmviaed[data-pid="'+b.dataset.pid+'"]'); if(!ed)return;
    ed.classList.toggle('hidden');
    if(ed.classList.contains('hidden')||ed.dataset.wired)return;
    ed.dataset.wired='1';
    const p=pOf(b.dataset.pid); if(!p)return;
    const q=ed.querySelector('.rvia_q'), res=ed.querySelector('.rvia_res'), selD=ed.querySelector('.rvia_sel'),
          tot=ed.querySelector('.rvia_tot'), noteI=ed.querySelector('.rvia_note');
    let rid=+(p.via_donor_id||0);
    if(rid){const dd=DB.find(x=>x.id===rid); if(dd){
      selD.classList.remove('hidden');
      selD.innerHTML=`נבחר: 🤝 ${esc((dd.last+' '+dd.first).trim())} <button type="button" class="viax">✕</button>`;
      selD.querySelector('.viax').onclick=()=>{rid=0;selD.classList.add('hidden');selD.innerHTML='';};}}
    wireDonorSearch(q,res,dd=>{rid=dd.id;
      selD.classList.remove('hidden');
      selD.innerHTML=`נבחר: 🤝 ${esc((dd.last+' '+dd.first).trim())} <button type="button" class="viax">✕</button>`;
      selD.querySelector('.viax').onclick=()=>{rid=0;selD.classList.add('hidden');selD.innerHTML='';};
    },d.id);
    const save=ed.querySelector('.rvia_save');
    if(save)save.onclick=async()=>{
      if(!rid){toast('בחר תורם מהרשימה');return;}
      await putPl(p,{via_donor_id:rid,via_total:tot.value.trim(),via_note:noteI.value.trim()});
      toast('נשמר ✓'); redraw();};
    const clr=ed.querySelector('.rvia_clear');
    if(clr)clr.onclick=async()=>{
      await putPl(p,{via_donor_id:'',via_total:'',via_note:''});
      toast('בוטל ✓'); redraw();};
    const closeB=ed.querySelector('.rvia_close');
    if(closeB)closeB.onclick=()=>ed.classList.add('hidden');
  });

  // ----- טופס ההוספה -----
  const sel=box.querySelector('.cm_cat'), nrow=box.querySelector('.cm_newrow'),
        det=box.querySelector('.cm_det'), avbox=box.querySelector('.cm_avbox'),
        avsel=box.querySelector('.cm_av'), nightbox=box.querySelector('.cm_nightbox'),
        amt=box.querySelector('.cm_amt'), plan=box.querySelector('.cm_plan'),
        nfld=box.querySelector('.cm_n'), calc=box.querySelector('.cm_calc'),
        startb=box.querySelector('.cmstart'), fromf=box.querySelector('.cm_from'),
        donef=box.querySelector('.cm_done'), mergeL=box.querySelector('.cmmerge'),
        mergec=box.querySelector('.cm_merge');
  let MATCH=[];
  const curS=curSym(d);
  const catNow=()=>sel.value==='__new__'
    ? (nrow.querySelector('.cm_new').value.trim()) : sel.value.trim();
  const show=()=>{
    const c=catNow();
    nrow.classList.toggle('hidden', sel.value!=='__new__');
    avbox.classList.toggle('hidden', !isIZcat(c));
    nightbox.classList.toggle('hidden', !isNightCat(c));
    det.placeholder=isBldgCat(c)
      ? 'מה בדיוק תרם בבניין? — למשל: כיסוי רדיאטורים ומעקות'
      : (/כולל/.test(c)?'איזה כולל? — למשל: כולל הוראה (נשאר אצלו בלבד)'
        :'פירוט אצל התורם הזה בלבד (לא נשמר ברשימת הייעודים)');
    nfld.classList.toggle('hidden', plan.value!=='inst');
    // מאיר: "כאן במקום שסימנתי אמור להיות שדה עם לוח שנה ממתי הוא
    // התחייב את ההתחייבות הזו". בהוראת קבע השדה הזה היה מוסתר, ולכן
    // המערכת לא ידעה מאיזה חודש לספור — ולא הראתה חוב.
    const isMo=plan.value==='mo';
    startb.classList.toggle('hidden', plan.value!=='inst'&&!isMo);
    donef.classList.toggle('hidden', isMo);
    box.querySelector('.cmstartl').textContent=isMo
      ? '📅 מאיזה חודש הוא התחייב? — מכאן נספרים החודשים והחוב'
      : 'התחייבות שכבר רצה? מלא מאיזה חודש התחילה וכמה תשלומים כבר עברו';
    const a=amtNum(amt.value), n=parseInt(nfld.value,10)||0;
    const done=Math.min(n, parseInt(donef.value,10)||0);
    if(plan.value==='inst'&&a>0&&n>0){
      const per=Math.round(a/n);
      const f=x=>curS+Math.round(x).toLocaleString('en-US');
      // תשלומים שכבר רשומים בכרטיס — מציעים לצרף אותם במקום להקליד שוב
      MATCH=instMatches(d,a/n,fromf.value,c).slice(0,n);
      const useM=MATCH.length&&mergec.checked;
      mergeL.classList.toggle('hidden', !MATCH.length);
      if(MATCH.length)
        box.querySelector('.cm_mergetxt').textContent=
          '🔗 צרף '+MATCH.length+' תשלומים של '+f(per)+' שכבר רשומים בכרטיס'
          +(MATCH[0].date?(' מ'+monthPlus(String(MATCH[0].date).slice(0,7),0)):'')
          +' — במקום לרשום אותם שוב';
      const dn=useM?MATCH.length:done;
      const left=Math.max(0,a-per*dn);
      calc.textContent='כל תשלום '+f(per)+' — '+n+' תשלומים'
        +(dn?(' · כבר שולמו '+dn+' ('+f(per*dn)+') · נשאר '+f(left)
                +' ב-'+(n-dn)+' תשלומים'):'')
        +(fromf.value?(' · '+(dn?'התשלום האחרון ':'עד ')
                +monthPlus(fromf.value,n-1)):'');
    } else { MATCH=[]; mergeL.classList.add('hidden');
      calc.textContent=(isIZcat(c)?'בחירת אברך כאן תיצור לו שורת אברך בלשונית יששכר־זבולון'
        :(isNightCat(c)?'בחירת לילה כאן תשריין את היום אצל התורם':'')); }
  };
  [sel,plan].forEach(e=>e.addEventListener('change',show));
  [amt,nfld,donef].forEach(e=>e.addEventListener('input',show));
  [fromf,mergec].forEach(e=>e.addEventListener('change',show));
  if(sel.value==='__new__')nrow.querySelector('.cm_new').addEventListener('input',show);
  show();
  if(!AVLIST.length)loadAvList().then(()=>{avsel.innerHTML=avOpts('');});
  wireAvNew(avsel, box.querySelector('.cm_avnew'), box.querySelector('.cm_avadd'));
  addMics(box,['.cmnote','.cm_det']);

  // שותפות תשלום בטופס ההוספה — הכסף נכנס בכרטיס של תורם אחר
  let VIAID=0;
  const viaTgl=box.querySelector('.cm_via_tgl'), viaBoxEl=box.querySelector('.cm_viabox'),
        viaQ=box.querySelector('.cm_via_q'), viaRes=box.querySelector('.cm_via_res'),
        viaSelD=box.querySelector('.cm_via_sel'), viaTot=box.querySelector('.cm_via_tot'),
        viaNoteI=box.querySelector('.cm_via_note');
  const pickVia=(dd,selEl,setId)=>{setId(dd.id);
    selEl.classList.remove('hidden');
    selEl.innerHTML=`נבחר: 🤝 ${esc((dd.last+' '+dd.first).trim())} <button type="button" class="viax">✕</button>`;
    selEl.querySelector('.viax').onclick=()=>{setId(0);selEl.classList.add('hidden');selEl.innerHTML='';};};
  if(viaTgl)viaTgl.onclick=()=>viaBoxEl.classList.toggle('hidden');
  if(viaQ)wireDonorSearch(viaQ,viaRes,dd=>pickVia(dd,viaSelD,v=>VIAID=v),d.id);

  box.querySelector('.cm_add').onclick=async()=>{
    let cat=sel.value.trim();
    if(cat==='__new__'){cat=nrow.querySelector('.cm_new').value.trim();
      if(!cat){toast('כתוב את שם הייעוד');return;}
      if(!(CAMPAIGNS||[]).includes(cat)){await api('POST','/api/campaigns',{name:cat});CAMPAIGNS.unshift(cat);}}
    if(!cat){toast('בחר עבור מה');return;}
    const total=amt.value.trim(), a=amtNum(total);
    const mode=plan.value;
    let permo='', already='', from='';
    if(mode==='inst'){
      const n=parseInt(nfld.value,10)||0;
      if(!a||!n){toast('מלא סכום ומספר תשלומים');return;}
      permo=String(Math.round(a/n*100)/100);
      // התחייבות שכבר רצה: מה ששולם עד היום נרשם כסכום, וחודש ההתחלה
      // קובע מתי היא נגמרת — כדי שזה ייראה עדכון ולא התחייבות חדשה.
      // אם יש תשלומים שכבר רשומים בכרטיס, מצרפים אותם עצמם ולא רושמים
      // סכום ידני — אחרת אותו כסף היה נספר פעמיים.
      const useM=MATCH.length&&mergec.checked;
      const dn=useM?MATCH.length:Math.min(n, parseInt(donef.value,10)||0);
      if(dn&&!useM)already=String(Math.round(a/n*dn*100)/100);
      from=fromf.value?(fromf.value+'-01'):
        (useM&&MATCH[0].date?(String(MATCH[0].date).slice(0,7)+'-01'):'');
    }
    const mo=mode==='mo'?1:0;
    // הוראת קבע — החודש שנבחר הוא החודש שממנו נספרת ההתחייבות. בלי זה
    // הספירה מתחילה מהחודש הראשון שנכנס בו כסף, וחודשים שלא שולמו
    // בכלל נעלמים מהחשבון.
    const sinceMo=mo?(fromf.value||'') : '';
    // הפירוט נשמר על השורה של התורם בלבד — לא נכנס לרשימת הייעודים
    const detail=det.value.trim();
    const avn=(!avbox.classList.contains('hidden')&&avsel.value&&avsel.value!=='__new__')
      ? avsel.value : '';
    const viaTotV=VIAID?viaTot.value.trim():'', viaNoteV=VIAID?viaNoteI.value.trim():'';
    const r=await api('POST','/api/pledge',{donor_id:d.id,category:cat,amount:total,
      status:mo?'נתן':'טרם',monthly:mo,paid:already,detail,permo,avreich:avn,date:from,
      since:sinceMo,
      via_donor_id:VIAID||'',via_total:viaTotV,via_note:viaNoteV});
    if(!r||!r.id){toast('לא נשמר');return;}
    d.pledges=(d.pledges||[]).concat([{id:r.id,donor_id:d.id,category:cat,amount:total,
      status:mo?'נתן':'טרם',monthly:mo,paid:already,note:'',detail,permo,avreich:avn,
      since:sinceMo,
      date:from||todayStr(),via_donor_id:VIAID||null,via_total:viaTotV,via_note:viaNoteV}]);
    // צירוף התשלומים הקיימים: הייעוד שלהם משתנה לייעוד ההתחייבות, וכך
    // המערכת מזהה אותם לבד כתשלומים על החשבון — בלי כפילות
    if(mode==='inst'&&MATCH.length&&mergec.checked){
      for(const x of MATCH){
        x.category=cat;
        await api('PUT','/api/donation/'+x.id,{category:cat});
      }
      toast('צורפו '+MATCH.length+' תשלומים קיימים ✓');
    }
    // אברך יששכר־זבולון — נפתחת לו שורת אברך אמיתית, כדי שהכל מחובר
    if(avn&&!(d.partners||[]).some(x=>x.active!=0&&(x.avreich||'').trim()===avn)){
      const pr=await api('POST','/api/partner',{donor_id:d.id,avreich:avn,amount:total});
      if(pr&&pr.id)d.partners=(d.partners||[]).concat([{id:pr.id,donor_id:d.id,avreich:avn,
        amount:total,active:1}]);
      if(d.tier!=='יששכר_זבולון'){d.tier='יששכר_זבולון';
        await api('PUT','/api/donor/'+d.id,{tier:d.tier});}
    }
    // לילה שנבחר — נרשם כיום משובץ אצל התורם
    if(!nightbox.classList.contains('hidden')){
      const hm=box.querySelector('.cm_hm').value, hd=+box.querySelector('.cm_hd').value,
            hy=box.querySelector('.cm_hy').value;
      const kind=/קפה/.test(cat)?'coffee':(/בוקר/.test(cat)?'breakfast':'parnes');
      const pr=await api('POST','/api/parnes',{donor_id:d.id,kind,day:hd,month:hm,
        date_text:heDay(hd)+' '+hm,hyear:hy,amount:total,dedication:detail});
      if(pr&&pr.id)d.parnes=(d.parnes||[]).concat([{id:pr.id,donor_id:d.id,kind,day:hd,
        month:hm,date_text:heDay(hd)+' '+hm,hyear:hy,amount:total,dedication:detail,
        status:'confirmed',paid:0}]);
    }
    await syncAmt();
    toast(mo?'נוסף קבוע ✓':(mode==='inst'?'נוספה התחייבות בתשלומים ✓':'נוספה התחייבות ✓'));
    redraw();};
  // מאיר: "יש שם מידי הרבה סיבוך כשמכניסים תורם" — הערה ושם לתפילה
  // יורדים לשורה מתקפלת, ובחוץ נשארים רק כמה / מתי / איך / עבור מה.
  const dnm=box.querySelector('#dn_more');
  if(dnm)dnm.onclick=()=>{const bx=box.querySelector('#dn_morebox');
    bx.classList.toggle('hidden');
    if(!bx.classList.contains('hidden'))bx.querySelector('input').focus();};
  // יתרת פתיחה — עברה לכאן מלשונית "פרטים", כדי שכל הכסף יהיה במקום אחד
  const opnb=box.querySelector('#f_opn');
  if(opnb)opnb.onclick=()=>{const bx=box.querySelector('#f_opnbox');
    bx.classList.toggle('hidden');
    if(!bx.classList.contains('hidden'))bx.querySelector('input').focus();};
  ['debt_open','debt_open_note'].forEach(k=>{
    const el=box.querySelector('#f_'+k); if(!el)return;
    el.onchange=async()=>{d[k]=el.value;
      await api('PUT','/api/donor/'+d.id,{[k]:el.value});
      toast('נשמר ✓'); redraw();};});
  box.querySelectorAll('.cosp2[data-did]').forEach(x=>x.onclick=()=>{
    const dd=DB.find(y=>y.id==x.dataset.did); if(dd)openDonor(dd);});
}
// "קבוע" לבד לא אומר על מה — על מה בדיוק הוא קבוע: יששכר־זבולון,
// קוויטל כל לילה, קוויטל שבועי, או ההתחייבות החודשית שרשומה אצלו.
function steadyFor(d){
  const parts=[], put=s=>{s=String(s||'').trim();if(s&&parts.indexOf(s)<0)parts.push(s);};
  try{const s=izSummary(d); if(s.monthly>0)put('יששכר־זבולון');}catch(e){}
  (d.pledges||[]).filter(p=>+p.monthly).forEach(p=>put(p.category));
  purposeList(d).forEach(put);
  const t=TIERS[d.tier];
  if(t)put(d.tier==='יששכר_זבולון'?t[0]:('קוויטל '+t[0]));
  return parts.join(' · ');
}
/* ---------- שניים ששולחים לבנק סכום אחד ומתחלקים בו ---------- */
// הכסף מגיע על שם אחד מהם. המערכת זוכרת, וכל סכום שנכנס נחתך מיד לשני הכרטיסים.
/* ---------- חיובים שלא עברו אצל התורם הזה ---------- */
// כרטיס שנדחה, חיוב שנכשל — הכי חשוב לראות את זה דווקא בכרטיס שלו,
// כדי לדעת למי להתקשר ולבקש כרטיס חדש.
// שבעה ניסיונות באותו חודש ובאותו סכום הם שורה אחת, לא שבע
function declinedGroups(d){
  const seen={}, out=[];
  (d.declined||[]).filter(x=>!+x.covered).forEach(x=>{
    const iso=String(x.date_iso||x.date||''), a=amtNum(x.amount);
    if(a<=0.5||iso.length<7)return;
    const k=iso.slice(0,7)+'|'+a.toFixed(2), h=seen[k];
    if(h){h.tries++; h.tids.push(x.tid); if(+x.is_debt)h.debt=1; if(iso<h.iso)h.iso=iso; return;}
    seen[k]={iso,a,tries:1,tids:[x.tid],debt:+x.is_debt?1:0}; out.push(seen[k]);
  });
  return out.sort((a2,b2)=>a2.iso<b2.iso?-1:1);
}
/* מאיר: "כאן בשורה המסומנת שיהיה כתוב כמה חוב אמיתי, לא כמה חיובים לא
   עברו — כי יש לפעמים שבסוף כן עבר — אלא תכליס כמה הוא חייב, ואז להיכנס
   לזה ולראות איך נוצר לו החוב הזה".
   השורה האדומה בראש הכרטיס מציגה עכשיו את החוב עצמו: מה היה אמור
   להיכנס לפי ההתחייבויות מול מה שבאמת נכנס. הפתיחה מראה את הפירוט —
   שורה לכל ייעוד, וכמה חסר בכל אחד. החיובים שלא עברו ירדו לסוף,
   כרמז לבדיקה בלבד, כי חיוב שנוסה שוב ועבר אינו חוב. */
// חשבון חודש־בחודש: כמה הוא היה אמור לתת באותו חודש, כמה באמת נכנס,
// וכמה נשאר לא מכוסה. עודף של חודש אחד מכסה חוסר של חודש אחר, ולכן
// חיוב שנכשל ובסוף שולם בדרך אחרת אינו יוצר חוב — הוא רק היסטוריה.
function monthLedger(d){
  const rows=commitRows(d).filter(r=>(r.mo||r.inst)&&r.amt>0.5&&r.conf>0&&!r.ended);
  if(!rows.length)return null;
  const thru=dataThru(), yr=thru.slice(0,4);
  // מאיזה חודש סופרים: החודש שנרשם על ההתחייבות, ואם לא נרשם — החודש
  // הראשון שנכנס בו כסף השנה
  // כשנקבע במפורש "מאז" — הוא הקובע, וכסף שנכנס לפניו שייך לתקופה
  // הקודמת ואינו בחשבון הזה. אם לא נקבע — סופרים מהחודש הראשון שנכנס
  // בו כסף השנה.
  let first='';
  rows.forEach(r=>{const s=r.since||(r.inst&&r.plan&&r.plan.from)||'';
    if(s&&s.length>=7&&(!first||s.slice(0,7)<first))first=s.slice(0,7);});
  if(!first)
    (d.donations||[]).forEach(x=>{const m=String(x.date||'').slice(0,7);
      if(m.length===7&&m.slice(0,4)===yr&&(!first||m<first))first=m;});
  if(!first)first=yr+'-01';
  // מה נכנס בכל חודש — בלי החלק שסגר חוב של שנה קודמת
  const got={};
  (d.donations||[]).forEach(x=>{const m=String(x.date||'').slice(0,7);
    if(m.length===7)got[m]=(got[m]||0)+amtNum(x.amount)-amtNum(x.prev_year);});
  const dec={};
  declinedGroups(d).forEach(r=>{const m=r.iso.slice(0,7);dec[m]=(dec[m]||0)+r.a;});
  const due1=m=>rows.reduce((s,r)=>{
    const per=r.inst?r.plan.per:r.amt;
    const st=(r.since&&r.since.length>=7)?r.since.slice(0,7)
      :((r.inst&&r.plan&&r.plan.from)?String(r.plan.from).slice(0,7):first);
    if(m<st)return s+((r.since&&r.prev>0.5)?r.prev:0);
    if(r.inst&&r.plan&&r.plan.n&&monthsTo(st,m)>r.plan.n)return s;
    return s+per;},0);
  const out=[]; let bal=0;
  for(let m=first;m<=thru;m=nextMonth(m)){
    const due=due1(m), g=got[m]||0;
    bal+=g-due;
    out.push({m,due,got:g,dec:dec[m]||0,bal});
    if(out.length>36)break;
  }
  const totDue=out.reduce((s,r)=>s+r.due,0), totGot=out.reduce((s,r)=>s+r.got,0);
  // "לא כוסה" של החודשים החסרים לחוד, והעודף של החודשים הטובים לחוד —
  // כדי שיהיה ברור למה החוב קטן מסכום החודשים שכתוב עליהם "לא כוסה"
  const miss=out.reduce((s,r)=>s+Math.max(0,r.due-r.got),0);
  const over=out.reduce((s,r)=>s+Math.max(0,r.got-r.due),0);
  return {rows:out, first, thru, due:Math.round(totDue), got:Math.round(totGot),
          miss:Math.round(miss), over:Math.round(over),
          debt:Math.max(0,Math.round(totDue-totGot)),
          ahead:Math.max(0,Math.round(totGot-totDue)),
          per:due1(thru)};
}
function nextMonth(ym){
  const a=String(ym).split('-'); let y=+a[0], m=+a[1]+1;
  if(m>12){m=1;y++;}
  return y+'-'+String(m).padStart(2,'0');
}
function debtBarHTML(d){
  let L=null; try{L=monthLedger(d);}catch(e){}
  const cur=curSym(d), f=n=>cur+Math.round(n).toLocaleString('en-US');
  const man=amtSigned(d.debt_open);           // התחייבות שנשארה מלפני 2026
  let prevPaid=0;
  (d.donations||[]).forEach(x=>{ if(String(x.date||'').slice(0,4)===GREGYEAR+'')
    prevPaid+=amtNum(x.prev_year); });
  const openPrev=Math.round(man-prevPaid);
  const tot=(L?L.debt:0)+Math.max(0,openPrev);
  const dec=declinedGroups(d).filter(r=>!r.debt);
  const decSum=dec.reduce((s,r)=>s+r.a,0);
  if(tot<=0.5)return '';        // אין חוב — ולא מציקים עם חיובים שנכשלו
  // מאיר: "אל תסתכל על כל חודש אלא בכללי מה היה מאז שהתחייב — כמה נכנס
  // וכמה חסר". שלוש שורות וזהו: מאז מתי, הסיכום, וכפתור לחיובים שחזרו.
  return `<details class="decbox debtbox"><summary>🔴 חייב ${f(tot)}</summary>
    ${L?`<div class="dbtot"><span>מאז ${esc(fmtMonth(L.first))}</span>
      <span>התחייב <b>${f(L.due)}</b></span>
      <span>נתן <b>${f(L.got)}</b></span>
      <span>חסר <b class="dbno">${f(L.debt)}</b></span></div>`:''}
    ${openPrev>0.5?`<div class="dbtot"><span>📌 מלפני ${GREGYEAR}${d.debt_open_note?(' · '+esc(d.debt_open_note)):''}</span>
      ${prevPaid>0.5?`<span>שולם <b>${f(prevPaid)}</b></span>`:''}
      <span>חסר <b class="dbno">${f(openPrev)}</b></span></div>`:''}
    ${dec.length?`<details class="decsub"><summary>💳 חיובי אשראי שחזרו (${dec.length}) · ${f(decSum)}</summary>
      <div class="hintxt" style="margin:2px 0 5px">היסטוריה בלבד — מה שחזר ובסוף נכנס בדרך אחרת כבר מקוזז בחשבון שלמעלה.</div>
      ${dec.map(r=>`<div class="decrow"><span class="decamt">${f(r.a)}</span>
        <span class="decd">${esc(gregLabel(r.iso))}${r.tries>1?(' · '+r.tries+' ניסיונות'):''}</span>
        <button class="dechide" data-tids="${esc(r.tids.join(','))}" title="הסתר">✕</button></div>`).join('')}</details>`:''}
  </details>`;
}
function declinedHTML(d){
  // חיוב שנדחה אינו חוב מעצמו: לרוב ניסו שוב וזה עבר, או שהתורם שילם
  // באותו חודש בדרך אחרת. לכן זו רשימה לבדיקה, ורק "זה חוב" מכניס לחוב.
  const g=declinedGroups(d).filter(r=>!r.debt); if(!g.length)return '';
  const cur=curSym(d), f=n=>cur+Math.round(n).toLocaleString('en-US');
  return `<details class="decbox"><summary>🔴 ${g.length} ${g.length===1?'חיוב שלא עבר':'חיובים שלא עברו'} · ${f(g.reduce((s2,r)=>s2+r.a,0))}</summary>
    ${g.map(r=>`<div class="decrow"><span class="decamt">${f(r.a)}</span>
      <span class="decd">${esc(gregLabel(r.iso))}${r.tries>1?(' · '+r.tries+' ניסיונות'):''}</span>
      <button class="dsok decdebt" data-tids="${esc(r.tids.join(','))}" data-undo="0">זה חוב</button>
      <button class="dechide" data-tids="${esc(r.tids.join(','))}" title="לא רלוונטי — הסתר">✕</button></div>`).join('')}
    <div class="hintxt">לא נספר בחוב. סמן "זה חוב" רק אם הכסף הזה באמת חסר — חיוב שנוסה שוב ועבר, או שהתורם שילם באותו חודש בדרך אחרת, אינו חוב. ✕ מסתיר שורה שאינה רלוונטית.</div></details>`;
}
function splitHTML(d){
  const rows=(d.paysplit||[]);
  const hasIz=(d.partners||[]).some(p=>p.active!=0)||d.tier==='יששכר_זבולון';
  if(!rows.length&&!hasIz)return '';       // בלי יששכר־זבולון — לא מציקים עם זה
  const body=rows.map(s=>{
    const pct=Math.round(s.pct), mine=100-pct;
    const t=s.role==='payer'
      ? `הכסף מגיע לבנק על שמו, ומתחלק עם <b class="splgo" data-id="${s.with_id}">${esc(s.with)}</b> — ${mine}% אצלו, ${pct}% אצל השותף.`
      : `הכסף שלו מגיע דרך <b class="splgo" data-id="${s.with_id}">${esc(s.with)}</b> — ${pct}% מכל סכום שנכנס על שמו נרשם כאן.`;
    return `<div class="splrow">🤝 ${t}${s.note?`<div class="splnote">${esc(s.note)}</div>`:''}
      <button class="del splx" data-id="${s.id}" title="בטל את החלוקה">🗑</button></div>`;}).join('');
  return `<div class="splbox">${body}
    <div class="splitadd ${rows.length?'hidden':''}">
      <button class="splmini splnew">🤝 יש שותף בתשלום?</button></div>
    <div class="splform hidden">
      <div class="hintxt">מי עוד מתחלק בסכום שמגיע לבנק על שם <b>${esc(d.last+' '+d.first)}</b>?</div>
      <input class="spl_q" placeholder="חפש תורם…" autocomplete="off">
      <div class="dpres spl_res"></div>
      <label class="fld"><span>כמה אחוז שייך לשותף</span>
        <input class="spl_pct" value="50" inputmode="decimal"></label>
      <button class="btn sm splcancel ghost">ביטול</button></div></div>`;
}
function wireSplit(d,body,redraw){
  body.querySelectorAll('.splgo').forEach(b=>b.onclick=()=>{
    const x=DB.find(y=>y.id==b.dataset.id); if(x)openDonor(x);});
  const form=body.querySelector('.splform'), add=body.querySelector('.splitadd');
  body.querySelectorAll('.splnew').forEach(b=>b.onclick=()=>{
    form.classList.remove('hidden'); add.classList.add('hidden');
    const q=form.querySelector('.spl_q'); q.focus();});
  body.querySelectorAll('.splcancel').forEach(b=>b.onclick=()=>{
    form.classList.add('hidden'); add.classList.remove('hidden');});
  const q=body.querySelector('.spl_q'), res=body.querySelector('.spl_res');
  if(q)q.oninput=()=>{
    const s=norm(q.value); if(!s){res.innerHTML='';return;}
    res.innerHTML=DB.filter(x=>x.id!==d.id&&matchStr(x.last+' '+x.first+' '+(x.english||''),s))
      .slice(0,8).map(x=>`<div class="dpr" data-id="${x.id}">${esc(x.last)} ${esc(x.first)}</div>`).join('')
      ||'<div class="dpr" style="color:var(--muted)">אין תוצאות</div>';
    res.querySelectorAll('.dpr[data-id]').forEach(el=>el.onclick=async()=>{
      const pct=parseFloat(body.querySelector('.spl_pct').value)||50;
      const r=await api('POST','/api/paysplit',{payer_id:d.id,donor_id:+el.dataset.id,pct});
      if(!r||!r.ok){toast('לא נשמר');return;}
      toast('נרשם ✓'+(r.split?(' — '+r.split+' סכומים נחתכו'):'')); await load(); redraw();});};
  body.querySelectorAll('.splx').forEach(b=>b.onclick=async()=>{
    if(!await uiConfirm('לבטל את החלוקה? סכומים שכבר נחתכו יישארו כפי שהם.'))return;
    await api('POST','/api/paysplit',{delete:1,id:+b.dataset.id});
    toast('בוטל ✓'); await load(); redraw();});
}
/* ---------- כמה התורם חייב — סיכום אחד, מפורט ---------- */
// כל מקור חוב בשורה נפרדת, כדי שיהיה ברור מאיפה הסכום מגיע ואפשר לבדוק אותו.
// מצב גבייה של יום פרנס: 0 טרם נגבה · 1 נגבה · 2 סודר (הכסף הגיע בתרומה
// נפרדת, מאיר עשה את החשבון — לא חוב ולא גבייה נפרדת)
function pPaidLbl(v){return +v===2?'✓ סודר':(+v===1?'✓ נגבה':'🔴 טרם נגבה');}
function pPaidCls(v){return +v===2?'setl':(+v===1?'yes':'no');}
// הקבוע החודשי מפוצל לייעודים: קופסה לכל אחד (1500 יששכר־זבולון,
// 4500 כולל יום). נשמר כהתחייבות חודשית, והסכום הקבוע הוא הסך הכל.
function monthlyPledges(d){return (d.pledges||[]).filter(p=>+p.monthly);}
// הסכום הקבוע שבכרטיס נבנה רק ממה שנרשם ביד — לא מהצעות ולא ממה שהסתיים
function fixTotal(d){return monthlyPledgesReal(d).reduce((s,p)=>s+amtNum(p.amount),0);}
function debtSummary(d){
  const cur=curSym(d), rows=[];
  // יתרת פתיחה מלפני 2026 — המערכת מכירה רק מינואר 2026, ומה שהיה לפני
  // כן נרשם ידנית בלשונית "פרטים" ונכנס לחשבון כמו שהוא
  const op=amtSigned(d.debt_open);
  if(Math.abs(op)>0.5)
    rows.push({t:(op>0?'חוב מלפני 2026':'שילם מראש (לפני 2026)'),v:op,
      s:String(d.debt_open_note||'').trim()||'יתרת פתיחה שנרשמה ידנית'});
  const iz=izSummary(d);
  const izDebt=(iz.manual!=null)?iz.manual:(iz.thru.length?iz.thruDebt:(iz.hasPay?iz.debt:0));
  if(izDebt>0.5)rows.push({t:'יששכר־זבולון',v:izDebt,
    s:iz.manual!=null?'עודכן ידנית':(iz.thru.length?'לפי "שולם עד חודש"':
      (iz.span+' חודשים × '+cur+Math.round(iz.monthly)))});
  // חודשים שלא נגבו אצל תורם קבוע. אם ההתחייבות היא יששכר־זבולון והוא
  // שילם מראש (או שהחוב עודכן ידנית) — אין חוב, ואסור לספור את אותו כסף שוב.
  const gc=gaps(d.months,d), fx=amtNum(fixedAmt(d));
  const izCovered=iz.monthly>0&&iz.monthly>=fx-0.5&&
    ((iz.manual!=null&&iz.manual<=0.5)||(iz.thru.length&&iz.thruDebt<=0.5));
  const gcRow=gc.length&&fx>0&&!izCovered;
  if(gcRow)rows.push({t:'חודשים שלא נגבו',v:gc.length*fx,
    s:gc.length+' × '+cur+Math.round(fx),
    chips:gc.map(i=>`<button class="gchip cgchip" data-m="${i}">${MON[i]} ✓</button>`).join('')});
  // ימי פרנס שטרם נגבו
  const pn=(d.parnes||[]).filter(p=>p.status!=='suggested'&&!+p.paid);
  const pnSum=pn.reduce((s2,p)=>s2+amtNum(p.amount),0);
  if(pnSum>0.5)rows.push({t:'ימי פרנס שטרם נגבו',v:pnSum,s:pn.length+' ימים'});
  // חיוב שנדחה אינו חוב מעצמו: ברוב המקרים ניסו לחייב שוב וזה עבר, או
  // שהתורם שילם באותו חודש בדרך אחרת (אלי וויינפעלד שילם 720 בכל חודש,
  // יהושע רוזנפלד שילם עשרות אלפים). לכן הרשימה מוצגת לבדיקה בלבד, ורק
  // מה שמסמנים ידנית "זה חוב" נכנס לסכום.
  // שבעה ניסיונות באותו חודש ובאותו סכום = שורה אחת, לא שבע.
  // רק חיוב שנדחה ומאיר סימן אותו במפורש "זה חוב" (ברשימה שמתחת לכרטיס)
  // נכנס לסכום. חודש שכבר נספר ב"חודשים שלא נגבו" לא נספר כאן שוב.
  const dec=declinedGroups(d).filter(r=>r.debt&&!(gcRow&&gc.includes(+r.iso.slice(5,7)-1)));
  const decSum=dec.reduce((s2,r)=>s2+r.a,0);
  if(decSum>0.5)
    rows.push({t:'🔴 חיובים שנדחו ולא נגבו',v:decSum,
      s:dec.length+' '+(dec.length===1?'חיוב':'חיובים'),
      list:dec.map(r=>({txt:gregLabel(r.iso)+' · '+cur+Math.round(r.a)
        +(r.tries>1?(' · '+r.tries+' ניסיונות'):''),tids:r.tids,undo:1}))});
  // מאיר: "התחייבות בתשלומים אינה חוב כל זמן שלא הגיע מועד הגבייה".
  // לכן מהתחייבות בתשלומים נספר רק מה שכבר היה אמור להיגבות ולא נגבה,
  // ועם חודש חסד אחד — כדי שקובץ בנק שטרם נקלט לא ייראה כמו חוב.
  const plOpen=p=>{
    const left=plLeft(d,p); if(left<=0.5)return 0;
    const plan=plPlan(d,p);
    if(!plan)return left;                       // התחייבות רגילה — כל היתרה
    const late=Math.max(0, plan.due - plan.done - 1);
    return Math.min(left, late*plan.per);
  };
  const pl=(d.pledges||[]).filter(p=>!+p.monthly&&plOpen(p)>0.5);
  const plSum=pl.reduce((s2,p)=>s2+plOpen(p),0);
  if(plSum>0.5)
    rows.push({t:'התחייבות שטרם ניתנה',v:plSum,
      s:pl.length+' '+(pl.length===1?'התחייבות':'התחייבויות'),
      list:pl.map(p=>({txt:plWhat(p)+' · '+cur+Math.round(plOpen(p))
        +(plPlan(d,p)?' (תשלומים שאיחרו)':(amtNum(p.paid)?(' (מתוך '+cur+Math.round(amtNum(p.amount))+', שולם '+cur+Math.round(amtNum(p.paid))+')'):''))}))});
  return {rows,total:rows.filter(r=>!r.info).reduce((s2,r)=>s2+r.v,0),cur};
}
// שורה אחת בלבד. הסכום עצמו הוא הקישור — לחיצה פותחת את הפירוט
// ורואים בדיוק ממה הוא מורכב: מה לא עבר ומה עוד לא נשלח.
let DEBTOPEN=false;
function debtHTML(d){
  const x=debtSummary(d);
  const f=n=>(n<0?'-':'')+x.cur+Math.abs(Math.round(n)).toLocaleString('en-US');
  // חוב שסודר — שורה זעירה אחת בלבד, עם ההסבר שנכתב בזמן הסידור
  if(String(d.debt_ok||'').trim())
    return `<div class="debtok">✓ החוב סודר${d.debt_note?(' · '+esc(d.debt_note)):''}`
      +`<button class="debtundo" id="debtundo" title="החזר לחוב פתוח">↺</button></div>`;
  // אין חוב — אין חלון. גם לא שורת "אין חוב פתוח" וגם לא ניסיונות
  // חיוב שנדחו: הם נמצאים בלשונית "🔴 לא עבר" ואין להם מה לתפוס מקום כאן.
  if(!x.rows.length||x.total<=0.5)return '';
  return `<div class="debtline" id="debtline">💰 יתרה פתוחה
      <button class="debtamt" id="debtgo">${f(x.total)}</button>
      <span class="debtcue">${DEBTOPEN?'▲':'▼ ממה?'}</span>
      <button class="debtsetl" id="debtsetl" title="סוכם עם התורם בדרך אחרת">סודר</button></div>
    <div class="debtokform hidden" id="debtokform">
      <input id="debtokwhy" placeholder="איך סודר? (למשל: ישלים בצ׳ק בראש חודש)">
      <button class="btn sm" id="debtokgo">💾 סודר</button></div>
    <div class="debtdet ${DEBTOPEN?'':'hidden'}" id="debtdet">
      ${x.rows.map(r=>`<div class="dsrow ${r.info?'info':''}"><span>${r.t}${r.s?`<small>${esc(r.s)}</small>`:''}${r.tip?`<small class="dstip">${esc(r.tip)}</small>`:''}${r.list?`<span class="dslist">${r.list.map(t=>`<small>${esc(t.txt)}${(t.tids||[]).length?`<button class="dsok${t.undo?' on':''}" data-tids="${esc(t.tids.join(','))}" data-undo="${t.undo?1:0}" title="${t.undo?'לא חוב — הורד מהסכום':'הכסף הזה באמת חסר — הוסף לחוב'}">${t.undo?'✓ חוב':'זה חוב'}</button>`:''}</small>`).join('')}</span>`:''}${r.chips?`<span class="dschips">${r.chips}<small>לחץ על חודש כדי לסמן שנגבה</small></span>`:''}</span><b>${f(r.v)}</b></div>`).join('')}
    </div>`;
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
  const sf=steadyFor(d);
  const lbl=c=>(sf&&/^(קבוע|הוראת קבע)$/.test(c))?(esc(c)+' <small class="csub">· '+esc(sf)+'</small>'):esc(c);
  return `<details class="dsec cattot"><summary>🎯 כמה נתרם לכל ייעוד</summary>
    <div class="catrow head"><span>ייעוד</span><b>${GREGYEAR}</b><b>הכל</b></div>
    ${rows.map(x=>`<div class="catrow"><span>${lbl(x.c)}</span><b>${x.year?f(x.year):'—'}</b><b>${f(x.all)}</b></div>`).join('')}
    <div class="catrow tot"><span>סה"כ</span><b>${f(tY)}</b><b>${f(tA)}</b></div></details>`;
}
function cardDetails(d,body){
  const cl=CATS.includes(d.category||'')?CATS:CATS.concat([d.category]);
  const sel=cl.map(c=>`<option ${c===(d.category||'')?'selected':''} value="${esc(c)}">${esc(catLabel(c))}</option>`).join('');
  const f=(k,v,dir)=>v?`<div class="rf"><div class="k">${k}</div><div class="v" ${dir?'dir="ltr"':''}>${esc(v)}</div></div>`:'';
  const gc=gaps(d.months,d).length;
  const dt=donorTotals(d), curd=curSym(d);
  // פירוט מה תרם ועבור מה — ישירות במסך הראשי
  const gitems=[];
  (d.parnes||[]).forEach(p=>gitems.push({k:p.night_date||'',amt:amtNum(p.amount),what:(DAYKIND[p.kind]||'🌙 פרנס')+(p.date_text?(' · '+p.date_text):'')+(p.hyear?(' '+p.hyear):''),ded:p.dedication||'',parnes:true,pid:p.id,paid:+p.paid,rm:p.method||d.channel||''}));
  (d.donations||[]).forEach(x=>gitems.push({k:x.date||'',amt:amtNum(x.amount),what:'',when:x.date?gregLabel(x.date):'',
    cur:(String(x.cur||'').trim()==='₪'?'₪':(String(x.cur||'').trim()==='$'?'$':curd)),
    ded:giveNote(x),rm:x.method||'',don:true,did:x.id,cat:x.category||'',note:x.note||'',
    prev:String(x.prev_year||''),prevn:String(x.prev_note||''),
    needthx:needThanks(x),thanked:+x.thanked}));
  gitems.sort((a,b)=>String(b.k||'').localeCompare(String(a.k||'')));   // החדשות למעלה, לפי תאריך אמיתי
  const methChip=rm=>rm?(chBadgeRaw(rm)||`<span class="givemeth">${esc(chLabel(rm))}</span>`):'';
  const GVSHOW=8;                       // מציגים את האחרונות; השאר נפתחות בלחיצה — פחות גלילה
  const gvrow=g=>{
    const curd=g.cur||curSym(d);            // מטבע השורה עצמה
    const st=g.parnes?`<span class="pstat ${pPaidCls(g.paid)}">${pPaidLbl(g.paid)}</span>`:'';
    const tog=g.parnes?`<button class="collectbtn ${+g.paid===1?'yes':'no'}" data-pid="${g.pid}">${+g.paid===1?'בטל גבייה':'✓ סמן נגבה'}</button>`
      +`<button class="collectbtn setl setlbtn ${+g.paid===2?'on':''}" data-pid="${g.pid}" title="הכסף הגיע בתרומה נפרדת — אין מה לגבות">${+g.paid===2?'בטל סודר':'סודר'}</button>`:'';
    const ed=g.don?`<button class="gvedit" data-did="${g.did}" title="שנה עבור מה">✏️</button>`:'';
    const fb=(g.don&&g.needthx)
      ? `<button class="fbbtn ${g.thanked?'yes':'no'}" data-fb="${g.did}" title="${g.thanked?'קיבל פידבק':'עוד לא קיבל פידבק'}">פידבק</button>` : '';
    // חלון אחד לכל תרומה: עבור מה · פירוט · כלל קבוע לאותו סכום
    const pan=g.don?`<div class="gvpanel hidden" data-pan="${g.did}">
      <div class="gvlbl">עבור מה ${curd}${g.amt} האלה?</div>
      <div class="addrow"><select class="gvcatsel" data-did="${g.did}">${dnCatOpts(g.cat)}</select></div>
      <div class="addrow gvnewrow hidden" style="margin-top:5px">
        <input class="gvcatnew" data-did="${g.did}" placeholder="שם הייעוד החדש">
        <button class="btn sm gvcatok" data-did="${g.did}">➕ הוסף</button></div>
      <div class="addrow gvbldgrow hidden" style="margin-top:5px">
        <input class="gvbldg" data-did="${g.did}" list="bldgitems3" placeholder="🏗️ מה תרם בבניין? (שולחן / עמוד / מטר…)">
        <button class="btn sm gvbldgok" data-did="${g.did}">➕ הוסף</button></div>
      <div class="addrow" style="margin-top:5px"><input class="gvnote" placeholder="פירוט (למשל: סעודת ראש חודש)" value="${esc(g.ded)}">
        <button class="btn sm gvsave" data-did="${g.did}">💾</button></div>
      <label class="gvall"><input type="checkbox" class="gvrule"> 🔁 כל ${curd}${g.amt} של התורם הזה = זה (גם בעתיד)</label>
      <div class="gvprev"><div class="gvlbl">📌 מזה על שנה קודמת (${GREGYEAR-1} ואחורה)</div>
        <div class="addrow"><input class="gvprevi curpick2" data-did="${g.did}" inputmode="decimal"
            placeholder="כמה" value="${esc(g.prev||'')}">
          <input class="gvprevn" data-did="${g.did}" placeholder="עבור מה — למשל: יששכר־זבולון ${GREGYEAR-1}"
            value="${esc(g.prevn||'')}">
          <button class="btn sm gvprevok" data-did="${g.did}">💾</button></div>
        <div class="hintxt">כשתשלום אחד סגר גם חוב ישן — הסכום הזה יוצא מחשבון ${GREGYEAR} ונזקף כנגד ההתחייבות הקודמת.</div></div>
      <button class="btn sm ghost gvsplit" data-did="${g.did}" style="width:100%;margin-top:6px">✂️ לחלק את ${curd}${g.amt} לכמה ייעודים</button>
      <div class="gvsplitbox hidden" data-sp="${g.did}">
        <div class="gvlbl" style="margin-top:8px">✂️ חלוקת ${curd}${g.amt}</div>
        <div class="sprows"></div>
        <div class="addrow"><button class="btn sm ghost spadd">➕ עוד ייעוד</button>
          <button class="btn sm spok" data-did="${g.did}" data-tot="${g.amt}">💾 שמור חלוקה</button></div>
        <div class="hintxt spmsg">הסכומים חייבים להסתכם ל-${curd}${g.amt}</div></div>
      <button class="btn sm ghost gvmove" data-did="${g.did}" style="width:100%;margin-top:6px">👥 להעביר את ${curd}${g.amt} או חלק ממנו לתורם אחר</button>
      <div class="gvmovebox hidden" data-mv="${g.did}">
        <div class="addrow" style="margin-top:6px">
          <input class="mvamt" type="number" min="1" max="${g.amt}" value="${g.amt}" placeholder="כמה להעביר">
          <span class="mvof">מתוך ${curd}${g.amt}</span></div>
        <input class="mvq" placeholder="🔍 למי להעביר? — חפש שם…" autocomplete="off">
        <div class="mvres dpres"></div>
        <div class="hintxt">אם מעבירים את כל הסכום — התרומה עוברת כולה לכרטיס השני. אם מעבירים חלק — נשאר כאן מה שנותר, ואצלו נפתחת תרומה באותו תאריך.</div></div>
      <button class="btn sm ghost gvdel" data-did="${g.did}" style="width:100%;margin-top:6px;color:var(--bad)">🗑 מחק את התרומה הזו</button></div>`:'';
    // בכל תרומה: סכום · עבור מה · תאריך · דרך מה נתרם. לחיצה על הייעוד פותחת את החלון.
    const what=g.don
      ? `<button class="gvcatbtn${g.cat?'':' need'}" data-did="${g.did}" title="לחץ כדי לשנות">${g.cat?esc(g.cat):'עבור מה?'}</button>`
      : esc(g.what);
    return `<div class="giverow"><span class="giveamt">${g.amt?(curd+g.amt):'—'}</span><div class="givewhat">${what}`
      + `${g.when?`<span class="givedate">${esc(g.when)}</span>`:''} ${methChip(g.rm)} ${st}${tog}${ed}${fb}`
      + `${amtNum(g.prev)>0.5?`<span class="prevchip">📌 ${curd}${Math.round(amtNum(g.prev)).toLocaleString('en-US')} ${esc(g.prevn||('על '+(GREGYEAR-1)))}</span>`:''}`
      + `${g.ded?`<div class="givesub">${esc(g.ded)}</div>`:''}${pan}</div></div>`;
  };
  // מאיר: "גם בפרטי תרומות למטה, איפה שכתוב כל ההכנסות של התרומות,
  // שיהיה שורה באדום כמה חייב" — אותו חשבון של השורה האדומה שבראש
  let oweLine='';
  try{ const L=monthLedger(d);
    if(L&&L.debt>0.5)
      oweLine=`<div class="dnowe">🔴 מאז ${esc(fmtMonth(L.first))} התחייב
        <b>${curd}${L.due.toLocaleString('en-US')}</b> · נתן
        <b>${curd}${L.got.toLocaleString('en-US')}</b> · חסר
        <b>${curd}${L.debt.toLocaleString('en-US')}</b></div>`;
  }catch(e){}
  const give=gitems.length?bldgList('bldgitems3')+`<div class="givelist"><div class="givehd">💵 מה תרם ועבור מה <span class="givecnt">${gitems.length}</span></div>${oweLine}`
    + gitems.slice(0,GVSHOW).map(gvrow).join('')
    + (gitems.length>GVSHOW?`<details class="gvmore"><summary>הצג עוד ${gitems.length-GVSHOW}</summary>${gitems.slice(GVSHOW).map(gvrow).join('')}</details>`:'')
    + `</div>`:'';
  const pdebts=(d.parnes||[]).filter(p=>p.status!=='suggested'&&!+p.paid);
  const pdebtsum=pdebts.reduce((s,p)=>s+amtNum(p.amount),0);
  const pdebtcur=pdebts.length?pCur(pdebts[0],d):curd;
  body.innerHTML=`${contactBtns(d)?`<div class="cardcbar">${contactBtns(d)}</div>`:''}
    ${pdebts.length?`<div class="debtbanner">🌙 פרנס שטרם נגבה: <b>${pdebtsum?(pdebtcur+pdebtsum):(pdebts.length+' ימים')}</b>${pdebts.map(p=>' · '+esc(DAYKIND[p.kind]||'🌙')+' '+esc(p.date_text||'')).join('')}</div>`:''}
    ${debtHTML(d)}
    ${debtBarHTML(d)}
    <div class="two"><label class="fld"><span>שם משפחה</span><input id="f_last" value="${esc(d.last)}"></label>
      <label class="fld"><span>שם פרטי</span><input id="f_first" value="${esc(d.first)}"></label></div>
    <div class="two"><label class="fld"><span>התחייבות</span><select id="f_category">${sel}</select></label>
      <label class="fld"><span>דרגת קוויטל</span><select id="f_tier">${tierOpts(d)}</select></label></div>
    ${hasFreq(d)?`<label class="fld"><span>תדירות</span><select id="f_frequency">${freqOpts(d.frequency)}</select></label>`:''}
    <div class="curline">מטבע: <button class="curbtn" id="f_cur" type="button" title="לחץ להחלפת מטבע">${d.region==='il'?'🇮🇱 ₪':'🇺🇸 $'}</button>
      <small>הסכומים הקבועים נרשמים בסוף העמוד, בשורות ההתחייבות</small></div>
    ${hasOccKv(d)?`<div class="two"><label class="fld"><span>🗓️ חודש קוויטל (מזדמנים)</span><select id="f_kvmon">${HMORD.map(m=>`<option ${m===(d.kv_month||'')?'selected':''}>${m}</option>`).join('')}</select></label>
      <label class="fld"><span>שנה עברית</span><select id="f_kvyr">${heYearOpts(d.kv_year||HEBYEAR)}</select></label></div>`:''}
    <button class="btn" id="f_saveall" style="width:100%;margin:6px 0">💾 שמור</button>
    ${izSummaryHTML(d)}
    ${reconPendHTML(d)}
    ${catTotalsHTML(d)}
    ${give}
    ${(d.parnes||[]).filter(p=>p.status!=='suggested').length?`<details class="dsec"><summary>🗓️ ימים משובצים (פרנס / קפה / בוקר)</summary><div id="parnes"></div></details>`:''}
    ${d.tier==='יששכר_זבולון'?`<details class="dsec"><summary>🤝 יששכר־זבולון — האברכים שהוא מחזיק</summary><div id="partners"></div>
      <button type="button" class="opnlink" id="pa_opn" style="margin-top:6px">➕ הוסף עוד אברך</button>
      <div class="opnbox hidden" id="pa_opnbox">
        <div class="addrow"><select id="pa_name">${avOpts('')}</select><button class="btn sm" id="pa_add">הוסף</button></div>
        <div class="addrow hidden" id="pa_newrow"><input id="pa_new" placeholder="שם האברך החדש — משפחה ואז פרטי"></div>
      </div></details>`:''}
    ${(d.transactions||[]).length?`<details class="dsec"><summary>💳 חיובים ותשלומים (${(d.transactions||[]).length})</summary><div id="transactions"></div></details>`:''}
    ${(dt.all||dt.year||dt.pending)?`<div class="totals" style="cursor:pointer" id="gototot"><div class="tot"><span>נגבה בפועל</span><b>${curd}${dt.all}</b></div><div class="tot year"><span>השנה (${GREGYEAR})</span><b>${curd}${dt.year}</b></div>${dt.pending>0?`<div class="tot pend"><span>🔴 טרם נגבה</span><b>${curd}${dt.pending}</b></div>`:''}</div>`:''}
    ${commitHTML(d)}
    ${(d.unclassified||[]).length?(()=>{const uo=RCATS.map(c=>`<option value="${esc(c)}">${esc(c)||'— בחר עבור מה —'}</option>`).join('')
        +((CAMPAIGNS||[]).length?('<optgroup label="🎯 מגביות/ייעודים">'+CAMPAIGNS.filter(c=>!RCATS.includes(c)).map(c=>`<option value="${esc(c)}">${esc(c)}</option>`).join('')+'</optgroup>'):'')
        +'<option value="__new__">➕ עבור מה חדש… (טקסט חופשי)</option>';
      return `<datalist id="bldgitems">${(BUILDING_ITEMS||[]).map(x=>`<option value="${esc(x)}">`).join('')}</datalist><div class="unclbox"><div class="k">❓ ${d.unclassified.length} חיובים בלי ייעוד · $${(d.unclassified.reduce((s,x)=>s+(+x.amount||0),0)).toLocaleString('en-US',{maximumFractionDigits:2})} — כל סכום נקבע ברשימה למטה, וכאן רק אם הכל לאותו ייעוד</div>
      <div class="addrow uall"><select id="ucl_cat">${uo}</select>
        <input id="ucl_new" placeholder="שם הייעוד החדש…" style="display:none">
        <input id="ucl_bldg" list="bldgitems" placeholder="🏗️ מה תרם בבניין?" style="display:none">
        <select id="ucl_av" style="display:none">${avOpts()}</select>
        <div class="hintxt uclavhint" id="ucl_avhint" style="display:none"></div>
        <input id="ucl_avnew" placeholder="שם האברך החדש" style="display:none">
        <button class="btn sm" id="ucl_avadd" style="display:none">➕ הוסף</button>
        <button class="btn sm" id="ucl_save">💾 אותו דבר לכולם</button></div></div>`;})():''}
    <div class="sec"><h3>📄 מסמכים ותעודות</h3>
      <div class="avfiles dnfiles" id="dfiles">${(d.files||[]).filter(f=>f.kind==='donor').map(fileChip).join('')}<label class="filebtn sm">📎 צרף מסמך / תעודה<input type="file" multiple accept="application/pdf,image/*" id="df_file" hidden></label></div>
      <div class="hintxt">מה שמצורף כאן מופיע בכרטיס הראשי. שטרי יששכר־זבולון נמצאים בלשונית 🤝.</div></div>
    ${notesHTML(d)}
    <div class="cardfoot">
      <button type="button" class="footlink" id="f_merge">🔀 מזג עם כרטיס כפול</button>
      <span class="footsep">·</span>
      <button type="button" class="footlink danger" id="f_delete">🗑 מחק תורם</button>
      <div id="mergebox" class="hidden">
        <input id="mg_q" placeholder="🔍 חפש את הכרטיס הכפול למזג לכאן…" autocomplete="off">
        <div id="mg_res" class="dpres"></div>
        <div class="hintxt">הכרטיס הזה (${esc((d.last+' '+d.first).trim())}) יישאר, והכפול יתמזג לתוכו — כל התרומות, הקוויטל והאברכים יעברו לכאן.</div></div>
    </div>`;
  wireDelete(d, body);   // ראשון בתור: תקלה בחיווט אחר לא תשאיר את המחיקה בלי מאזין
  wireIzSum(body.querySelector('.izsum'), d);
  const fcur=document.getElementById('f_cur');
  if(fcur)fcur.onclick=async e=>{ e.preventDefault();
    d.region=(d.region==='il')?'':'il';
    await api('PUT','/api/donor/'+d.id,{region:d.region});
    toast(d.region==='il'?'שקלים ₪ ✓':'דולרים $ ✓');
    cardDetails(d,body); if(tab==='donors')renderDonors();};
  wireCommit(d,body);   // בלוק ההתחייבויות בתחתית העמוד
  const dgo=document.getElementById('debtgo'), ddt=document.getElementById('debtdet');
  if(dgo)dgo.onclick=()=>{DEBTOPEN=!DEBTOPEN; ddt.classList.toggle('hidden',!DEBTOPEN);
    document.querySelector('#debtline .debtcue').textContent=DEBTOPEN?'▲':'▼ ממה?';};
  // "סודר" — סוכם עם התורם בדרך אחרת. נשמר עם ההסבר, והחלון מתכווץ לשורה
  const dsb=document.getElementById('debtsetl'), dform=document.getElementById('debtokform');
  if(dsb&&dform)dsb.onclick=()=>{dform.classList.toggle('hidden');
    if(!dform.classList.contains('hidden'))document.getElementById('debtokwhy').focus();};
  const dokgo=document.getElementById('debtokgo');
  if(dokgo)dokgo.onclick=async()=>{
    const why=(document.getElementById('debtokwhy')||{value:''}).value.trim();
    d.debt_ok=todayStr(); d.debt_note=why;
    await api('PUT','/api/donor/'+d.id,{debt_ok:d.debt_ok,debt_note:why});
    toast('סומן כסודר ✓'); cardDetails(d,body); if(tab==='donors')renderDonors();};
  const dundo=document.getElementById('debtundo');
  if(dundo)dundo.onclick=async()=>{
    d.debt_ok=''; d.debt_note='';
    await api('PUT','/api/donor/'+d.id,{debt_ok:'',debt_note:''});
    toast('חזר לחוב פתוח'); cardDetails(d,body); if(tab==='donors')renderDonors();};
  // מסמכים בכרטיס הראשי — העלאה ומחיקה
  const dfi=document.getElementById('df_file');
  if(dfi)dfi.onchange=async()=>{
    for(const f of dfi.files){ const r=await uploadBlob('donor',d.id,f);
      if(r&&r.id)(d.files=d.files||[]).push({id:r.id,kind:'donor',name:f.name,mime:f.type}); }
    dfi.value=''; toast('צורף ✓'); cardDetails(d,body);};
  const dfb=document.getElementById('dfiles');
  if(dfb)dfb.querySelectorAll('.fdel').forEach(b2=>b2.onclick=async()=>{
    if(!await uiConfirm('למחוק את הקובץ?'))return;
    await api('DELETE','/api/file/'+b2.dataset.fid);
    d.files=(d.files||[]).filter(x=>x.id!=b2.dataset.fid);
    toast('נמחק'); cardDetails(d,body);});
  wireSplit(d, body, ()=>{const x=DB.find(y=>y.id===d.id)||d; cardDetails(x, body);});
  const gt=document.getElementById('gototot'); if(gt)gt.onclick=()=>{cardTab='details';renderCard(d);};
  body.querySelectorAll('.cosp2[data-did]').forEach(x=>x.onclick=()=>{const dd=DB.find(y=>y.id==x.dataset.did);if(dd)openDonor(dd);});
  body.querySelectorAll('.collectbtn:not(.setlbtn)').forEach(b=>b.onclick=async()=>{const p=(d.parnes||[]).find(x=>x.id==b.dataset.pid);if(!p)return;const np=+p.paid===1?0:1;p.paid=np;await api('PUT','/api/parnes/'+p.id,{paid:np});toast(np?'סומן כנגבה ✓':'סומן כטרם נגבה');cardDetails(d,body);if(tab==='donors')renderDonors();});
  body.querySelectorAll('.setlbtn').forEach(b=>b.onclick=async()=>{const p=(d.parnes||[]).find(x=>x.id==b.dataset.pid);if(!p)return;const np=+p.paid===2?0:2;p.paid=np;await api('PUT','/api/parnes/'+p.id,{paid:np});toast(np===2?'סומן כסודר ✓ — לא ייספר כחוב':'הסימון בוטל');cardDetails(d,body);if(tab==='donors')renderDonors();});
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
  // ---- חלוקת תרומה אחת לכמה ייעודים ----
  const spRow=(amt,cat)=>`<div class="addrow sprow" style="margin-top:5px">
    <input class="spamt" inputmode="decimal" placeholder="סכום" value="${esc(amt||'')}" style="max-width:96px">
    <select class="spcat">${dnCatOpts(cat||'')}</select>
    <button class="del sprm" title="הסר">✕</button></div>`;
  const spSum=box=>[...box.querySelectorAll('.spamt')].reduce((s,i)=>s+amtNum(i.value),0);
  const spWire=box=>{
    box.querySelectorAll('.sprm').forEach(x=>x.onclick=()=>{if(box.querySelectorAll('.sprow').length>2)x.closest('.sprow').remove();spUpd(box);});
    box.querySelectorAll('.spamt').forEach(x=>x.oninput=()=>spUpd(box));};
  const spUpd=box=>{const tot=amtNum(box.querySelector('.spok').dataset.tot),s=spSum(box);
    const m=box.querySelector('.spmsg');
    m.innerHTML=Math.abs(s-tot)<0.5?'<b style="color:var(--yes)">✓ מסתכם בדיוק</b>'
      :`נותרו לחלק: <b style="color:var(--no)">${curd}${Math.round((tot-s)*100)/100}</b>`;};
  body.querySelectorAll('.gvsplit').forEach(b=>b.onclick=()=>{
    const box=body.querySelector('.gvsplitbox[data-sp="'+b.dataset.did+'"]');
    const open=box.classList.toggle('hidden')===false;
    if(open&&!box.querySelector('.sprow')){
      const g=(d.donations||[]).find(x=>x.id==b.dataset.did)||{};
      box.querySelector('.sprows').innerHTML=spRow('',g.category||'')+spRow('','');
      spWire(box); spUpd(box);}
  });
  body.querySelectorAll('.spadd').forEach(b=>b.onclick=()=>{const box=b.closest('.gvsplitbox');
    box.querySelector('.sprows').insertAdjacentHTML('beforeend',spRow('',''));spWire(box);spUpd(box);});
  body.querySelectorAll('.spok').forEach(b=>b.onclick=async()=>{
    const box=b.closest('.gvsplitbox');
    const parts=[...box.querySelectorAll('.sprow')].map(r=>({
      amount:r.querySelector('.spamt').value.trim(), category:r.querySelector('.spcat').value.trim()}))
      .filter(x=>amtNum(x.amount)>0);
    if(parts.length<2){toast('צריך לפחות שני חלקים');return;}
    if(parts.some(x=>!x.category||x.category==='__new__')){toast('בחר עבור מה לכל חלק');return;}
    b.disabled=true;
    const r=await api('POST','/api/donation/'+b.dataset.did+'/split',{parts});
    b.disabled=false;
    if(!r||!r.ok){toast(r&&r.error?r.error:'החלוקה נכשלה');return;}
    parts.forEach(x=>{if(!(CAMPAIGNS||[]).includes(x.category))CAMPAIGNS.unshift(x.category);});
    toast('חולק ל-'+parts.length+' ייעודים ✓');
    await load(); const dd=DB.find(x=>x.id===d.id); if(dd)openDonor(dd,'details');});
  // מאיר: "תעשה לי כאן אפשרות מחיקה של תרומה שנכנסה או אפשרות להעביר את
  // התרומה או חלק ממנה למישהו אחר — למשל אם שניים נתנו ביחד תרומה אז אוכל
  // לחלק את התרומה ביניהם וזה עובר לכרטיס שלו".
  body.querySelectorAll('.gvmove').forEach(b=>b.onclick=()=>{
    const box=body.querySelector('.gvmovebox[data-mv="'+b.dataset.did+'"]');
    if(box.classList.toggle('hidden')===false)box.querySelector('.mvq').focus();});
  body.querySelectorAll('.gvmovebox').forEach(box=>{
    const did=box.dataset.mv, q=box.querySelector('.mvq'), res=box.querySelector('.mvres');
    const go=async other=>{
      const dn=(d.donations||[]).find(x=>x.id==did)||{};
      const tot=amtNum(dn.amount), amt=amtNum(box.querySelector('.mvamt').value)||tot;
      if(amt<=0||amt>tot+0.01){toast('הסכום להעברה חייב להיות עד '+curd+Math.round(tot));return;}
      const nm=(other.last+' '+other.first).trim();
      const all=Math.abs(amt-tot)<0.01;
      if(!await uiConfirm(all?('להעביר את כל התרומה של '+curd+Math.round(tot)+' אל "'+nm+'"?')
        :('להעביר '+curd+Math.round(amt)+' מתוך '+curd+Math.round(tot)+' אל "'+nm+'"?\nכאן יישארו '+curd+Math.round(tot-amt)+'.')))return;
      const r=await api('POST','/api/donation/'+did+'/move',{to:other.id,amount:String(amt)});
      if(!r||!r.ok){toast(r&&r.error?r.error:'ההעברה נכשלה');return;}
      toast('הועבר אל '+nm+' ✓');
      await load(); const dd=DB.find(x=>x.id===d.id); if(dd)openDonor(dd,'details');};
    q.oninput=()=>{const s=norm(q.value);
      if(!s){res.innerHTML='';return;}
      const m=DB.filter(x=>x.id!==d.id&&norm(x.last+' '+x.first+' '+x.english+' '+x.phone).includes(s)).slice(0,8);
      res.innerHTML=m.map(x=>`<div class="dpr" data-id="${x.id}">${esc(x.last)} ${esc(x.first)} <span style="color:var(--muted)">#${x.id}</span></div>`).join('')
        ||'<div class="dpr" style="color:var(--muted)">אין תוצאות</div>';
      res.querySelectorAll('.dpr[data-id]').forEach(el=>el.onclick=()=>{
        const other=DB.find(x=>x.id==el.dataset.id); if(other)go(other);});};});
  body.querySelectorAll('.gvdel').forEach(b=>b.onclick=async()=>{
    const dn=(d.donations||[]).find(x=>x.id==b.dataset.did); if(!dn)return;
    if(!await uiConfirm('למחוק את התרומה של '+curd+Math.round(amtNum(dn.amount))
      +(dn.date?(' מ-'+gregLabel(dn.date)):'')+'?\nהיא תרד מהכרטיס ולא תחזור בייבוא הבא.'))return;
    await api('DELETE','/api/donation/'+dn.id);
    toast('נמחק ✓');
    await load(); const dd=DB.find(x=>x.id===d.id); if(dd)openDonor(dd,'details');});
  body.querySelectorAll('.gvcatsel').forEach(s=>s.onchange=()=>{
    const pan=s.closest('.gvpanel');
    pan.querySelector('.gvbldgrow').classList.add('hidden');
    if(s.value==='__new__'){
      pan.querySelector('.gvnewrow').classList.remove('hidden');
      pan.querySelector('.gvcatnew').focus();
      return;
    }
    // בניין — קודם מפרטים מה נתרם, ורק אז נשמר
    if(isBldgCat(s.value)){
      pan.querySelector('.gvnewrow').classList.add('hidden');
      pan.querySelector('.gvbldgrow').classList.remove('hidden');
      pan.querySelector('.gvbldg').focus();
      return;
    }
    saveGvCat(s.dataset.did,s.value);
  });
  body.querySelectorAll('.gvbldgok').forEach(b=>b.onclick=async()=>{
    const pan=b.closest('.gvpanel'), inp=pan.querySelector('.gvbldg'), it=inp.value.trim();
    if(it.length<2){toast('כתוב מה הוא תרם בבניין');inp.focus();return;}
    const sel=pan.querySelector('.gvcatsel');
    b.disabled=true; await bldgRemember(it);
    await saveGvCat(b.dataset.did,(sel.value||'הבניין הקדוש')+' — '+it);
  });
  body.querySelectorAll('.gvbldg').forEach(i=>i.onkeydown=e=>{
    if(e.key==='Enter'){e.preventDefault();i.closest('.gvpanel').querySelector('.gvbldgok').click();}});
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
  // מאיר: "כבר רשמתי את התשלום הזה מזמן, איך אני מעדכן שחלק מזה על
  // 2025?" — על תרומה שכבר רשומה, מתוך אותו חלון של ✏️
  body.querySelectorAll('.gvprevok').forEach(b=>b.onclick=async()=>{
    if(b.dataset.busy)return; b.dataset.busy='1';
    try{
      const inp=body.querySelector('.gvprevi[data-did="'+b.dataset.did+'"]');
      const dn=(d.donations||[]).find(x=>x.id==b.dataset.did); if(!dn)return;
      const v=inp.value.trim(), n=amtNum(v);
      if(v&&n>amtNum(dn.amount)+0.5){toast('הסכום גדול מהתרומה עצמה');inp.focus();return;}
      const nt=(body.querySelector('.gvprevn[data-did="'+b.dataset.did+'"]')||{value:''}).value.trim();
      dn.prev_year=v?String(n):''; dn.prev_note=v?nt:'';
      await api('PUT','/api/donation/'+dn.id,{prev_year:dn.prev_year,prev_note:dn.prev_note});
      toast(v?('נרשם: '+curSym(d)+Math.round(n)+' על '+(GREGYEAR-1)+' ✓'):'בוטל — הכל על '+GREGYEAR);
      // מציירים מיד מהנתון שכבר עודכן כאן — בלי להמתין לרענון מהשרת,
      // שממילא עונה מהמטמון ומחזיר את הכרטיס כמו שהיה
      openDonor(d,'details');
      if(tab==='donors')renderDonors();
      load();
    } finally{ delete b.dataset.busy; }});
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
  const uclSave=document.getElementById('ucl_save');
  const uclSel=document.getElementById('ucl_cat'), uclNew=document.getElementById('ucl_new');
  const uclBd=document.getElementById('ucl_bldg');
  const uclAv=document.getElementById('ucl_av');
  wireAvNew(uclAv,document.getElementById('ucl_avnew'),document.getElementById('ucl_avadd'));
  if(uclAv&&!AVLIST.length) loadAvList().then(()=>{document.querySelectorAll('select.uav1,#ucl_av').forEach(s2=>{s2.innerHTML=avOpts(s2.value);});});
  if(uclSel&&uclNew&&uclBd){ const shwA=()=>{const isNew=uclSel.value==='__new__';uclNew.style.display=isNew?'block':'none';
      const c=isNew?uclNew.value:uclSel.value;
      uclBd.style.display=/בנין|בניין/.test(c)?'block':'none';
      // מאיר: "למה שאבחר אברך? שהמערכת תראה לבד שכבר יש לו אברכים שהוא
      // מחזיק, זה לשלושתם ביחד, אז איך אבחר אברך אחד?" — כשיש לו אברכים
      // רשומים הכסף שייך ליששכר־זבולון שלו ומתחלק ביניהם, ואין מה לבחור.
      const izA=isIZcat(c), mine=izAvNames(d);
      if(uclAv) uclAv.style.display=(izA&&!mine.length)?'block':'none';
      const hint=document.getElementById('ucl_avhint');
      if(hint){ hint.style.display=(izA&&mine.length)?'block':'none';
        hint.textContent=izA&&mine.length
          ? ('ייזקף ליששכר־זבולון של '+(mine.length===1?'האברך שלו':mine.length+' האברכים שלו')
             +' — '+mine.join(' · ')) : ''; }
      const un=document.getElementById('ucl_avnew'),ua=document.getElementById('ucl_avadd');
      if((!izA||mine.length)&&un){un.style.display='none';ua.style.display='none';}};
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
    // אברך נבחר רק כשאין לו אף אברך רשום. כשיש — הכסף הוא של
    // יששכר־זבולון שלו כולו, ואין טעם לשייך אותו לאברך אחד מתוך שלושה.
    if(isIZcat(cat)&&!izAvNames(d).length){ avv2=(uclAv?uclAv.value:'').trim();
      if(!avv2||avv2==='__new__'){toast('בחר אברך מהרשימה');if(uclAv)uclAv.focus();return;} }
    uclSave.disabled=true;uclSave.textContent='שומר…';
    const r=await api('POST','/api/classify',{donor_id:d.id,category:cat,avreich:avv2});
    if(!r||!r.ok){uclSave.disabled=false;uclSave.textContent='💾 שמור לכולם';toast('השמירה נכשלה');return;}
    toast('עודכנו '+r.updated+' תרומות ✓');
    await load(); const dd=DB.find(x=>x.id===d.id); if(dd)openDonor(dd,'details');};
  // ---- רישום תרומה חדשה, ישירות מהדף הראשי ----
  renderParnesEdit(d); renderTransactions(d);
  if(d.tier==='יששכר_זבולון'){
    renderPartners(d);
    // מאיר: "לא נותן לבחור אברך מהרשימה אלא סתם לכתוב שדה חופשי" —
    // הבחירה היא מרשימת האברכים של הכולל, ומי שאינו בה נוסף אליה קודם.
    // מאיר: "כבר כתוב למעלה בחר אברך... למה יש פה שוב משבצת? זה מיותר" —
    // הבחירה השנייה נועדה רק להוספת אברך נוסף, ולכן מקופלת עד שלוחצים.
    const pas=document.getElementById('pa_name'), panew=document.getElementById('pa_newrow');
    const paop=document.getElementById('pa_opn');
    if(paop)paop.onclick=()=>{const bx=document.getElementById('pa_opnbox');
      bx.classList.toggle('hidden');
      if(!bx.classList.contains('hidden')&&pas)pas.focus();};
    if(pas&&!AVLIST.length)loadAvList().then(()=>{pas.innerHTML=avOpts('');});
    if(pas&&panew)pas.onchange=()=>{const on=pas.value==='__new__';
      panew.classList.toggle('hidden',!on);
      if(on)document.getElementById('pa_new').focus();};
    const pab=document.getElementById('pa_add');
    if(pab)pab.onclick=async()=>{
      const isNew=pas&&pas.value==='__new__';
      const n=(isNew?document.getElementById('pa_new').value:(pas?pas.value:'')).trim();
      if(n.length<2){toast('בחר אברך מהרשימה, או הוסף אברך חדש');return;}
      if(isNew){const a=await api('POST','/api/avreich/new',{name:n});
        if(!a||!a.ok){toast('ההוספה לרשימת האברכים נכשלה');return;}}
      const r=await api('POST','/api/partner',{donor_id:d.id,avreich:n});
      d.partners=(d.partners||[]).concat([{id:r.id,avreich:n}]);
      await loadAvList();
      if(panew)panew.classList.add('hidden');
      const pn=document.getElementById('pa_new'); if(pn)pn.value='';
      if(pas)pas.innerHTML=avOpts('');
      const pbx=document.getElementById('pa_opnbox'); if(pbx)pbx.classList.add('hidden');
      renderPartners(d);toast('נוסף ✓');};
  }
  const dnDate=document.getElementById('dn_date'); if(dnDate)dnDate.value=todayStr();
  const dnCat=document.getElementById('dn_cat'), dnMeth=document.getElementById('dn_method');
  const isBldg=c=>/בנין|בניין/.test(c||'');
  const dnShow=()=>{
    const o=dnCat.options[dnCat.selectedIndex], day=o?o.dataset.day:'';
    document.getElementById('dn_daybox').classList.toggle('hidden',!day);
    document.getElementById('dn_newrow').classList.toggle('hidden',dnCat.value!=='__new__');
    document.getElementById('dn_bldg_l').classList.toggle('hidden',!isBldg(dnCat.value));
    document.getElementById('dn_ccbox').classList.toggle('hidden',!/אשראי|אונליין/.test(dnMeth.value));
    const ab=document.getElementById('dn_add');       // הכפתור אומר בדיוק מה יישמר
    if(ab)ab.textContent=day?('💾 שמור '+(DAYSAVE[day]||'יום פרנס')):'💾 שמור תרומה';
  };
  if(dnCat){dnCat.onchange=dnShow;dnMeth.onchange=dnShow;dnShow();}
  // מאיר: "העביר בכל חודש מינואר עד אוגוסט 1000 שקל" — סימון אחד פותח
  // טווח חודשים, וכל חודש נרשם כתשלום נפרד עם תאריך מדויק, בדיוק כמו
  // תשלום שנכנס מבנק ווסט או מאוטורייז.
  const dnRep=document.getElementById('dn_rep'), dnRepBox=document.getElementById('dn_repbox'),
        dnFrom=document.getElementById('dn_from'), dnTo=document.getElementById('dn_to'),
        dnHint=document.getElementById('dn_rephint'), dnCur=document.getElementById('dn_cur');
  // כל התאריכים בטווח, על אותו יום בחודש כמו התאריך שנבחר למעלה
  const repDates=()=>{
    const a=(dnFrom&&dnFrom.value)||'', b=(dnTo&&dnTo.value)||'';
    if(!a||!b)return [];
    const day=((dnDate&&dnDate.value)||todayStr()).slice(8,10)||'01';
    const out=[]; let [y,m]=a.split('-').map(Number); const [ey,em]=b.split('-').map(Number);
    while(y*12+m<=ey*12+em && out.length<60){
      const last=new Date(y,m,0).getDate();                 // 31 בפברואר אינו קיים
      out.push(y+'-'+String(m).padStart(2,'0')+'-'+String(Math.min(+day,last)).padStart(2,'0'));
      m++; if(m>12){m=1;y++;}
    }
    return out;
  };
  const dnRepShow=()=>{
    if(!dnRep)return;
    const on=dnRep.checked;
    dnRepBox.classList.toggle('hidden',!on);
    dnHint.classList.toggle('hidden',!on);
    if(on){
      const l=repDates(), a=amtNum((document.getElementById('dn_amt')||{}).value||0);
      const cs=(dnCur&&dnCur.value)||cur;
      dnHint.textContent=l.length
        ? ('ייכתבו '+l.length+' תשלומים: '+l[0]+' עד '+l[l.length-1]
           +(a?(' · '+cs+a.toLocaleString('en-US')+' כל חודש · סה"כ '+cs+(a*l.length).toLocaleString('en-US')):''))
        : 'בחר מאיזה חודש ועד איזה חודש';
    }
  };
  if(dnRep){
    dnRep.onchange=dnRepShow;
    [dnFrom,dnTo,dnDate,dnCur,document.getElementById('dn_amt')].forEach(x=>{
      if(x){x.addEventListener('change',dnRepShow);x.addEventListener('input',dnRepShow);}});
    dnRepShow();
  }
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
    const dcur=(dnCur&&dnCur.value)||'';
    let made=0;
    if(amt&&!dayKind){
      // תשלום חוזר: שורה לכל חודש בטווח. אחרת — שורה אחת בתאריך שנבחר.
      const dates=(dnRep&&dnRep.checked)?repDates():[date];
      if(dnRep&&dnRep.checked&&!dates.length){toast('בחר מאיזה חודש ועד איזה חודש');dnAdd.disabled=false;return;}
      // "מזה על שנה קודמת" נרשם רק על התשלום הראשון בטווח — הוא הסכום
      // שסגר את החוב הישן, ולא סכום שחוזר בכל חודש
      const prevI=document.getElementById('dn_prev');
      let prevLeft=prevI?amtNum(prevI.value):0;
      for(const dt of dates){
        const py=prevLeft>0.5?String(Math.min(prevLeft,amtNum(amt))):'';
        if(py)prevLeft-=amtNum(py);
        const pn=py?((document.getElementById('dn_prevn')||{value:''}).value.trim()):'';
        const body={donor_id:d.id,amount:amt,category:cat,method,date:dt,note,cur:dcur,prev_year:py,prev_note:pn};
        const r=await api('POST','/api/donation',body);
        d.donations=(d.donations||[]).concat([{id:r.id,donor_id:d.id,amount:amt,category:cat,
          method,date:dt,note,cur:dcur,prev_year:py,paid:1}]);
        made++;
      }
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
    toast((made>1?('נרשמו '+made+' תשלומים ✓'):'נרשם ✓')+(dayKind?' + יום נתפס':'')+(pray?' + שם לקוויטל':''));
    cardDetails(d,body); if(tab==='donors')renderDonors();
  };
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
  const FF=['last','first','category','frequency'];   // הסכום נשמר מהשורות עצמן
  wireFields(d,FF);
  wireNotes(d,body);
  // שינוי ההתחייבות מחליף גם את מה שרלוונטי להציג (תדירות רק לקבועים)
  const catSel=document.getElementById('f_category');
  if(catSel)catSel.addEventListener('change',()=>setTimeout(()=>cardDetails(d,body),150));
  // כפתור הפידבק על שורת התרומה — אדום עד שקיבל, ירוק אחרי
  body.querySelectorAll('.fbbtn[data-fb]').forEach(b2=>b2.onclick=async e=>{
    e.stopPropagation();
    const x=(d.donations||[]).find(y=>y.id==b2.dataset.fb); if(!x)return;
    x.thanked=+x.thanked?0:1;
    await api('PUT','/api/donation/'+x.id,{thanked:x.thanked});
    toast(x.thanked?'סומן: קיבל פידבק ✓':'סומן: עדיין לא קיבל פידבק');
    cardDetails(d,body); if(tab==='donors')renderDonors();});
  // סימון חודש שלא עבר — ישירות מהכרטיס
  body.querySelectorAll('.cgchip').forEach(b3=>b3.onclick=async e=>{
    e.stopPropagation(); const i=+b3.dataset.m, prev=d.months;
    d.months=setMonthChar(d.months,i,'c');
    await api('PUT','/api/donor/'+d.id,{months:d.months});
    toastUndo(MON[i]+' — נגבה ✓',async()=>{d.months=prev;await api('PUT','/api/donor/'+d.id,{months:prev});cardDetails(d,body);});
    cardDetails(d,body); if(tab==='donors')renderDonors();});
  // חיוב שנדחה נספר בחוב רק אם מסמנים אותו ידנית — ראה debtSummary
  body.querySelectorAll('.dsok').forEach(b3=>b3.onclick=async e=>{
    e.stopPropagation();
    const tids=String(b3.dataset.tids||'').split(',').filter(Boolean); if(!tids.length)return;
    const off=b3.dataset.undo==='1';
    const set=v=>(d.declined||[]).forEach(x=>{if(tids.indexOf(String(x.tid))>=0)x.is_debt=v;});
    await api('POST','/api/recon/debt',off?{tids,undo:1}:{tids});
    set(off?0:1); DEBTOPEN=true; cardDetails(d,body); if(tab==='donors')renderDonors();
    toastUndo(off?'ירד מהחוב':'נוסף לחוב',async()=>{
      await api('POST','/api/recon/debt',off?{tids}:{tids,undo:1});
      set(off?1:0); cardDetails(d,body); if(tab==='donors')renderDonors();});});
  // ✕ — חיוב שנדחה ואינו רלוונטי כלל (תקלה בדוח, ניסיון כפול): יורד מהרשימה
  body.querySelectorAll('.dechide').forEach(b3=>b3.onclick=async e=>{
    e.stopPropagation();
    const tids=String(b3.dataset.tids||'').split(',').filter(Boolean); if(!tids.length)return;
    const set=v=>(d.declined||[]).forEach(x=>{if(tids.indexOf(String(x.tid))>=0)x.covered=v;});
    await api('POST','/api/recon/nodebt',{tids}); set(1);
    cardDetails(d,body); if(tab==='donors')renderDonors();
    toastUndo('הוסתר',async()=>{await api('POST','/api/recon/nodebt',{tids,undo:1});set(0);
      cardDetails(d,body); if(tab==='donors')renderDonors();});});
  const tierSel=document.getElementById('f_tier'); if(tierSel)tierSel.onchange=()=>applyTierSelect(d);
  const kvmon=document.getElementById('f_kvmon'),kvyr=document.getElementById('f_kvyr');
  const saveKvMY=async()=>{d.kv_month=kvmon.value;d.kv_year=kvyr.value;await api('PUT','/api/donor/'+d.id,{kv_month:d.kv_month,kv_year:d.kv_year});toast('עודכן · '+d.kv_month+' '+d.kv_year+' ✓');cardDetails(d,body);};
  if(kvmon)kvmon.onchange=saveKvMY; if(kvyr)kvyr.onchange=saveKvMY;
  addMic(document.getElementById('dn_note'));
  // הייעודים נקבעים בשורות "סכום קבוע" עצמן — אין יותר טור ייעודים נפרד
  document.getElementById('f_saveall').onclick=async()=>{const b2={};FF.forEach(k=>{const el=document.getElementById('f_'+k);if(el){b2[k]=el.value;d[k]=el.value;}});
    await api('PUT','/api/donor/'+d.id,b2);cardDetails(d,body);toast('נשמר ✓');if(tab==='donors')renderDonors();};
}

// מחיקת תורם — חלון אישור ברור, ודיווח אמיתי אם נכשל
async function wireDelete(d, body){
  const btns=[...(body||document).querySelectorAll('#f_delete,.delcard')];
  if(!btns.length) return;
  const run=async delBtn=>{
    const nm=((d.last||'')+' '+(d.first||'')).trim();
    const n=(d.donations||[]).length, p=(d.parnes||[]).length, av=(d.partners||[]).length;
    const det=[n?n+' תרומות':'',p?p+' פרנס':'',av?av+' אברכים':''].filter(Boolean).join(' · ');
    if(!await uiConfirm('למחוק לצמיתות את "'+nm+'"?\n'+(det?('יימחקו גם: '+det+'\n'):'')+'אי אפשר לבטל את זה.')) return;
    delBtn.disabled=true; delBtn.textContent='מוחק…';
    let r=null; try{ r=await api('DELETE','/api/donor/'+d.id); }catch(e){ r={ok:false,detail:String(e)}; }
    if(!r||!r.ok){
      delBtn.disabled=false; delBtn.textContent='🗑 מחק תורם';
      toast('המחיקה נכשלה'+((r&&(r.detail||r.error))?': '+(r.detail||r.error):' — נסה שוב'));
      return;
    }
    DB=DB.filter(x=>x.id!==d.id); ov.classList.remove('show');
    try{localStorage.removeItem('kc_donor');}catch(e){}
    toast('התורם נמחק ✓'); render();
  };
  btns.forEach(b=>b.onclick=()=>run(b));
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
    <div class="addrow"><input id="pr_new" placeholder="שם לתפילה (למשל: יעקב בן שרה לרפואה שלמה)" value="${esc(sugg)}"><button class="btn sm" id="pr_add">💾 שמור שם</button></div>`;
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
const RCATS=['','קבוע','יששכר־זבולון','כולל יום','פרנס לילה','חדר קפה','ארוחת בוקר','נר למאור','קוויטל','מזדמן','חד-פעמי','הבניין הקדוש'];
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
      <label class="fld"><span>ערוץ חיוב</span><select id="f_channel" class="chansel">${channelOpts(d.channel)}</select></label></div>
    <label class="fld"><span>כתובת (רחוב ומספר)</span><input id="f_addr" value="${esc(d.addr)}" dir="${d.region==='il'?'rtl':'ltr'}"></label>
    <div class="two"><label class="fld"><span>עיר</span><input id="f_city" value="${esc(d.city||'')}" dir="${d.region==='il'?'rtl':'ltr'}"></label>
      <label class="fld"><span>מדינה</span><input id="f_country" value="${esc(d.country||'')}" dir="${d.region==='il'?'rtl':'ltr'}"></label></div>
    <label class="fld"><span>מיקוד</span><input id="f_zip" value="${esc(d.zip||'')}" dir="ltr"></label>
    <label class="fld"><span>עבור מה (מטרה כללית)</span><input id="f_purpose" value="${esc(d.purpose)}"></label>
    <label class="fld"><span>📝 הערות (למשל: הגיע דרך אבא קלוק) — ניתן לחיפוש</span><textarea id="f_notes" rows="3" placeholder="כתוב כאן כל דבר שתרצה למצוא אחר כך בחיפוש">${esc(d.notes||'')}</textarea></label>
    ${d.notes?`<div class="hintxt" style="margin:-4px 2px 8px">🔎 <a class="notelink" href="#">חפש את כל מי שיש לו הערה דומה</a></div>`:''}
    <button class="btn" id="f_saveall" style="width:100%;margin:6px 0">💾 שמור פרטים</button>
    ${f('סטטוס תשלום',d.pay_status)}${d.created?f('נוסף למערכת',d.created+(d.source?(' · דרך '+d.source):'')):''}
    ${d.months?`<div class="rf" style="flex-direction:column;gap:6px"><div class="k">מפת חודשים${gaps(d.months,d).length?' · <b style="color:var(--no)">'+gaps(d.months,d).length+' לא עברו</b>':''}</div>${monthGrid(d.months,d)}</div>`:''}`;
  renderPhones(d); renderEmails(d);
  body.insertAdjacentHTML('beforeend',
    '<div class="sec" style="text-align:center"><button class="btn ghost delbig delcard" style="width:100%">🗑 מחיקת התורם לצמיתות</button></div>');
  wireDelete(d,body);
  const INF=['english','business','region','channel','addr','city','country','zip','purpose','notes','debt_open','debt_open_note'];
  wireFields(d,INF);
  wireChanSel(document.getElementById('f_channel'));
  const sv=document.getElementById('f_saveall');
  if(sv)sv.onclick=async()=>{
    const body2={};
    INF.forEach(k=>{const el=document.getElementById('f_'+k); if(el)body2[k]=el.value;});
    if(body2.channel==='__new__')body2.channel=d.channel||'';   // לא נשמר לפני שהוזן שם
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
      <div class="addrow"><select id="cl_ch">${clkOpts('')}</select><input id="cl_date" type="date" value="${todayStr()}"></div>
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
  document.getElementById('cl_add').onclick=async()=>{let ch=document.getElementById('cl_ch').value;if(ch==='__new__'){toast('כתוב את שם סוג הקשר');return;}const date=document.getElementById('cl_date').value,sum=document.getElementById('cl_sum').value.trim(),next=document.getElementById('cl_next').value;if(!sum&&!date)return;const r=await api('POST','/api/contact',{donor_id:d.id,channel:ch,date:date,summary:sum,next_date:next});d.contacts=d.contacts||[];d.contacts.unshift({id:r.id,channel:ch,date:date,summary:sum,next_date:next});if(next){d.tasks=d.tasks||[];d.tasks.push({id:r.task_id,donor_id:d.id,due_date:next,kind:'followup',note:sum.slice(0,80),done:0});}document.getElementById('cl_sum').value='';
    if(clF.arr.length){toast('מעלה קבצים…');for(const f of clF.arr)await uploadBlob('contact',r.id,f);clF.reset();await refresh();toast('נשמר עם האסמכתאות ✓');return;}
    renderContacts(d);renderReminders(d);toast('נשמר ✓');};
  wireKindSel(document.getElementById('tk_kind'));
  wireClkSel(document.getElementById('cl_ch'));
  addMic(document.getElementById('cl_sum')); addMic(document.getElementById('tk_note'));
  document.getElementById('tk_add').onclick=async ev=>{const btn=ev.currentTarget;if(btn.disabled)return;const kind=await kindValue(document.getElementById('tk_kind'));if(!kind)return;const note=document.getElementById('tk_note').value.trim(),date=document.getElementById('tk_date').value;if(!date){toast('בחר תאריך');return;}btn.disabled=true;const r=await api('POST','/api/task',{donor_id:d.id,due_date:date,kind:kind,note:note});btn.disabled=false;if(r&&r.existing){toast('התזכורת כבר קיימת');return;}d.tasks=d.tasks||[];d.tasks.push({id:r.id,donor_id:d.id,due_date:date,kind:kind,note:note,done:0});document.getElementById('tk_note').value='';
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
  el.querySelectorAll('[data-done]').forEach(b=>b.onclick=async()=>{const t=d.tasks.find(x=>x.id==b.dataset.done);if(t)await setTaskDone(t,1,d);renderReminders(d);checkReminders();toast('בוצע ✓ · נרשם בקשר');});
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
  const cur=String(sel||'').trim();
  const src=(AVLIST.length?AVLIST:allAvreichim().map(n=>({name:n,taken:true,holders:[]})))
    .slice().sort((a,b)=>String(a.name).localeCompare(String(b.name),'he'));
  // האברך שכבר רשום בשורה חייב להופיע ברשימה גם אם אינו במאגר —
  // אחרת בחירה נראית ריקה והשם נמחק בשמירה הבאה.
  const has=src.some(a=>String(a.name).trim()===cur);
  const extra=(cur&&!has)?`<option value="${esc(cur)}" selected>${esc(cur)} — רשום כאן בלבד</option>`:'';
  return `<option value="" ${cur?'':'selected'}>— בחר אברך מהרשימה —</option>`+extra
    +src.map(a=>{const on=String(a.name).trim()===cur;
      // בשורה של האברך עצמו אין טעם לכתוב "אצל התורם הזה" — זו כפילות
      const t=on?'':(a.taken?(' — אצל '+((a.holders&&a.holders[0])?a.holders[0].name:'תורם')):' — פנוי');
      return `<option value="${esc(a.name)}" ${on?'selected':''}>${esc(a.name)}${esc(t)}</option>`;}).join('')
    +'<option value="__new__">➕ אברך חדש — הוסף לרשימה…</option>';
}
async function loadAvList(){ try{const r=await api('GET','/api/avreichim');
  AVLIST=(r&&r.rows)||r||[]; AVSTAT=(r&&r.rows)?r:null; AVPEND=(r&&r.pending)||[];}catch(e){} }
let AVPEND=[];
// שם מהרשימה הרשמית של הכולל שדומה לאברך שכבר רשום — מאיר מחליט אם זה
// אותו אדם (ואז הת"ז והטלפון מצטרפים אליו) או שני אנשים נפרדים.
// מאיר: "תלך רק לפי הקובץ ששלחתי" — הרשימה הרשמית היא רשימת האמת.
// מי שרשום אצלנו ואינו מופיע בה מסומן, כדי שיהיה ברור שצריך לברר עליו.
function avPendHTML(){
  const out=(AVLIST||[]).filter(a=>!(a.idnum||'').trim());
  if(!out.length)return '';
  return `<details class="avpend"><summary>❓ ${out.length} אברכים שאינם ברשימת הכולל שנשלחה</summary>
    <div class="hintxt" style="margin:0 2px 8px">הם רשומים כאן אך אינם מופיעים בקובץ. ייתכן שיצאו מהכולל או שהם בסדר אחר.</div>
    ${out.map(a=>`<div class="avpendrow"><div class="avpn"><b>${esc(a.name)}</b>${
      (a.holders||[]).length?` <small>מוחזק על ידי ${esc(a.holders.map(h=>h.name).join(', '))}</small>`
                            :' <small>אין מחזיק</small>'}</div></div>`).join('')}
  </details>`;
}
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
// מאיר: "אי אפשר כאן להוסיף דרך חדשה איך שהוא נותן" — הרשימה כאן
// מצרפת גם כל דרך תשלום שמאיר הוסיף בעצמו, ולא רק את הקבועות.
function dnMethList(){return DNMETH.concat((CHAN_C||[]).filter(x=>DNMETH.indexOf(x)<0));}
const DNBASE=['קבוע','יששכר־זבולון','כולל יום','פרנס לילה','חדר קפה','ארוחת בוקר','נר למאור','קוויטל','הבניין הקדוש','מזדמן','חד-פעמי'];
function dnCatList(){return DNBASE.concat((CAMPAIGNS||[]).filter(c=>c&&!DNBASE.includes(c)));}
// ייעוד התורם יכול להיות כמה דברים יחד — למשל יששכר־זבולון וגם נר למאור.
// נשמר בשדה אחד מופרד ב־" · ", כמו שזה גם מוצג בראש הכרטיס.
function purposeList(d){return String((d&&d.purpose)||'').split('·').map(x=>x.trim()).filter(Boolean);}
function purpChips(l){
  return l.map((c,i)=>`<span class="purpchip">${esc(c)}<button type="button" class="purpx" data-i="${i}" title="הסר">✕</button></span>`).join('')
    ||'<span class="hintxt">עוד לא נבחר ייעוד</span>';
}
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
  // תרומות בשני מטבעות אינן מתחברות — כל מטבע בסיכום שלו
  const totC={};list.forEach(x=>{const k=(String(x.cur||'').trim()==='₪'?'₪':(String(x.cur||'').trim()==='$'?'$':cur));
    totC[k]=(totC[k]||0)+amtNum(x.amount);});
  const totTxt=Object.keys(totC).filter(k=>Math.round(totC[k])>0)
    .map(k=>k+Math.round(totC[k]).toLocaleString('en-US')).join(' + ')||(cur+0);
  const dncats=['קבוע','מזדמן','יששכר־זבולון','פרנס לילה','חדר קפה','ארוחת בוקר','נר למאור','חד-פעמי'].concat(CAMPAIGNS||[]);
  const dmeths=['אשראי','אונליין','המחאה','מזומן','העברה בנקאית','בנק ווסט','Banquest','Authorize'];
  // פרנס יום — מוצג גם כאן בתרומות, עם סטטוס גבייה (נגבה/חוב)
  const pns=(d.parnes||[]).filter(p=>p.status!=='suggested');
  const pnsHtml=pns.length?`<div class="dncount">🌙 פרנס יום (${pns.length})</div>`+pns.map(p=>{const pc=pCur(p,d),pd=+p.paid;return `<div class="dncrow"><div class="dnci"><b>${pc}${esc(p.amount||'—')}</b> · ${esc(DAYKIND[p.kind]||'🌙 פרנס')} ${esc(p.date_text||'')}${p.hyear?(' '+esc(p.hyear)):''} <span class="pstat ${pd?'yes':'no'}">${pd?'✓ נגבה':'🔴 טרם נגבה'}</span></div><div class="dncact"><button class="collectbtn ${pd?'yes':'no'} pnspaid" data-pid="${p.id}">${pd?'בטל':'✓ נגבה'}</button></div></div>`;}).join(''):'';
  el.innerHTML=(list.length?`<div class="dncount">${list.length} תרומות · ${totTxt}</div>`:'')+(list.map(x=>dnRow(x,cur)).join('')||'<div class="hintxt">עדיין אין תרומות.</div>')+pnsHtml
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
  // הכתובת נדפסת על הקבלה כמו בקבלה אמריקאית רגילה, והמפתח קבוע לכל
  // תרומה כדי שהדפסה חוזרת תיתן את אותו מספר סידורי ולא מספר חדש
  const ad=[String(d.addr||'').trim(),
            [String(d.city||'').trim(),String(d.country||'').trim(),String(d.zip||'').trim()]
              .filter(Boolean).join(' ')].filter(Boolean).join(', ');
  const p=new URLSearchParams({n:name,a:x.amount||'',p:x.category||'',d:x.date||todayStr(),
    m:x.method||'',ad:ad,k:'d'+(x.id||('t'+d.id+'-'+(x.date||'')+'-'+(x.amount||'')))});
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
/* ---------- ספר החיובים: כל מה שנכנס מינואר, כל אמצעי בנפרד ---------- */
let LEDGER=null, ledSrc=null, ledFail=false, ledNoCat=false, ledAll=false, ledMon=null;
// שמות קריאים למקורות, בלי לאחד ביניהם — הוא ביקש לראות כל אחד לחוד
const SRCLBL={'Banquest 01-08-2026':'💳 בנק ווסט','Authorize 01-08-2026':'💳 אוטרייז',
  'Authorize 07-2026':'💳 אוטרייז (יולי)','Authorize אונליין':'💳 אוטרייז — מהאתר (חי)',
  'Donors Fund 2026':'🏦 דונרס פאנד','OJC 2026':'🏦 OJC','צ׳קים 2026':"🧾 צ'קים"};
const srcLabel=s2=>SRCLBL[s2]||s2;
async function renderLedger(scroll){
  const box=document.getElementById('ledgerbox'); if(!box)return;
  if(!LEDGER){ try{ LEDGER=await api('GET','/api/ledger?since=2026-01-01'); }catch(e){ LEDGER={groups:[]}; } }
  const f=n=>'$'+Math.round(n||0).toLocaleString('en-US');
  const L=LEDGER;
  const nc=noCatList(), ncs=nc.reduce((s,o)=>s+amtNum(o.x.amount),0);
  box.innerHTML=`<div class="ledtot">
      <div class="ledbig"><span>💰 נכנס מאז ינואר</span><b>${f(L.total)}</b><small>${L.n} חיובים</small></div>
      <button class="ledbig bad ${ledFail?'on':''}" id="ledfail"><span>🔴 לא עבר</span><b>${f(L.bad_total)}</b><small>${L.bad_n} חיובים — לחץ לראות</small></button>
      <button class="ledbig what ${ledNoCat?'on':''}" id="lednocat"><span>🎯 בלי ייעוד</span><b>${f(ncs)}</b><small>${nc.length} תרומות — להשלים עבור מה</small></button>
      <button class="ledbig nocard" id="lednocard"><span>💵 בלי כרטיס</span><b id="depcnt">…</b><small>מפקידים לשייך או לפתוח כרטיס</small></button>
    </div>
    <button class="btn ghost ${ledAll?'on':''}" id="ledall" style="width:100%;margin:0 2px 8px">📅 הכל לפי חודשים — מקורות וייעודים</button>
    <button class="btn ghost" id="ppsync" style="width:100%;margin:0 2px 8px">📧 משוך קבלות ותשלומים מהמייל (אוטרייז + PayPal)</button>
    <div id="leddet"></div>
    <div class="ledlist">${(L.groups||[]).map(g=>`<button class="ledrow ${ledSrc===g.src?'on':''}" data-s="${esc(g.src)}">
      <div class="ledn">${esc(srcLabel(g.src))}</div>
      <div class="ledm">${g.n} חיובים${g.first?(' · '+esc(g.first.slice(5))+' – '+esc(g.last.slice(5))):''}</div>
      ${g.bad_n?`<div class="ledbad">🔴 ${g.bad_n} לא עברו · ${f(g.bad_total)}</div>`:''}
      <b>${f(g.total)}</b></button>`).join('')}</div>`;
  box.querySelectorAll('.ledrow').forEach(b=>b.onclick=()=>{
    ledSrc=(ledSrc===b.dataset.s&&!ledFail)?null:b.dataset.s; ledFail=false; ledNoCat=false; ledMon=null; renderLedger(1);});
  document.getElementById('ledfail').onclick=()=>{ledFail=!ledFail; ledSrc=null; ledNoCat=false; ledMon=null; renderLedger(1);};
  document.getElementById('lednocat').onclick=()=>{ledNoCat=!ledNoCat; ledSrc=null; ledFail=false; ledMon=null; WFLIM=40; renderLedger(1);};
  document.getElementById('lednocard').onclick=()=>{flt='deposits'; DEPS=null; depOpen=null; tab='donors'; render();};
  document.getElementById('ledall').onclick=()=>{ledAll=!ledAll; ledSrc=null; ledFail=false; ledNoCat=false; ledMon=null; renderLedger(1);};
  const pps=document.getElementById('ppsync'); if(pps)pps.onclick=()=>runPaypalSync(pps);
  // מספר המפקידים שאין להם כרטיס — נטען ברקע כדי לא לעכב את המסך
  api('GET','/api/deposits').then(r=>{const e=document.getElementById('depcnt');
    if(e&&r)e.textContent=((r.names||0)+(r.cards||0));}).catch(()=>{});
  ledDetail(scroll);
}
// scroll=1 — לגלול לפירוט שנפתח, כדי שלא ייפתח מתחת למסך ויראה כאילו לא נלחץ
async function ledDetail(scroll){
  const el=document.getElementById('leddet'); if(!el)return;
  if(ledNoCat){ whatForBox(el); if(scroll)ledScroll(el); return; }
  if(ledAll){ monthsBox(el); if(scroll)ledScroll(el); return; }
  if(!ledSrc&&!ledFail){ el.innerHTML=''; document.querySelectorAll('.ledrow').forEach(b=>b.classList.remove('on')); return; }
  document.querySelectorAll('.ledrow').forEach(b=>b.classList.toggle('on',b.dataset.s===ledSrc));
  el.innerHTML='<div class="cnt">טוען…</div>';
  // פירוט חודשי של המקור שנבחר — כמה נכנס בכל חודש וכמה לא עבר
  const grp=(LEDGER&&(LEDGER.groups||[]).find(g=>g.src===ledSrc))||null;
  const f0=n=>'$'+Math.round(n||0).toLocaleString('en-US');
  const monHtml=(!ledFail&&grp&&(grp.mon||[]).length)?`<div class="monbox">
      <div class="mon-t">📅 ${esc(srcLabel(grp.src))} — לפי חודשים</div>
      <div class="monhead"><span>חודש</span><b>נכנס</b><b>לא עבר</b></div>
      ${grp.mon.map(m2=>`<button class="monrow ${ledMon===m2.ym?'on':''}" data-m="${m2.ym}">
        <span>${esc(fmtMonth(m2.ym+'-01')||m2.ym)}</span>
        <b>${m2.n?f0(m2.total):'—'}<small>${m2.n?(' · '+m2.n):''}</small></b>
        <b class="${m2.bad_n?'badm':''}">${m2.bad_n?f0(m2.bad_total):'—'}<small>${m2.bad_n?(' · '+m2.bad_n):''}</small></b>
      </button>`).join('')}
      <div class="monrow tot"><span>סה"כ</span><b>${f0(grp.total)}</b><b class="${grp.bad_n?'badm':''}">${grp.bad_n?f0(grp.bad_total):'—'}</b></div>
    </div>`:'';
  const u='/api/ledger?since=2026-01-01'+(ledFail?'&failed=1':('&src='+encodeURIComponent(ledSrc)));
  let r; try{ r=await api('GET',u); }catch(e){ r={rows:[]}; }
  const f=n=>'$'+Math.round(n||0).toLocaleString('en-US');
  const rows=(r.rows||[]).filter(x=>matchQ(x.name+' '+x.bank));
  const rows2=ledMon?rows.filter(x=>String(x.date||'').slice(0,7)===ledMon):rows;
  el.innerHTML=monHtml+`<div class="cnt">${ledFail?'🔴 חיובים שלא עברו':esc(srcLabel(ledSrc))}${ledMon?(' · '+esc(fmtMonth(ledMon+'-01')||ledMon)):''} — ${rows2.length} שורות${r.more?(' (מוצגות הראשונות)'):''}${ledMon?' <button class="btn sm ghost" id="monall">כל החודשים</button>':''}</div>
    <div class="list">${rows2.map(x=>`<div class="rowc ${x.status!=='settled'?'failrow':''}" data-id="${x.donor_id||''}">
      <div><div class="nm">${esc(x.name||x.bank||'—')}${x.name&&x.bank?` <small dir="ltr">${esc(x.bank)}</small>`:''}</div>
        <div class="purp">${esc(x.date)}${x.note?(' · '+esc(x.note)):''}${ledFail?(' · '+esc(srcLabel(x.src))):''}</div></div>
      <div class="meta"><b>${f(x.amount)}</b>${x.status!=='settled'?`<span class="txbadge no">${esc(STLBL[x.status]||x.status)}</span>`:''}</div>
    </div>`).join('')||'<div class="empty">אין שורות</div>'}</div>`;
  el.querySelectorAll('.rowc[data-id]').forEach(r2=>r2.onclick=()=>{
    const d=DB.find(x=>x.id==r2.dataset.id); if(d)openDonor(d); else toast('החיוב עדיין לא שויך לתורם');});
  if(scroll)ledScroll(el);
}
// כל החודשים מהחדש לישן: בכל חודש כמה נכנס, דרך איזה מקור, ולאיזה ייעוד
function monthsBox(el){
  const f=n=>'$'+Math.round(n||0).toLocaleString('en-US');
  const M={};
  ((LEDGER&&LEDGER.groups)||[]).forEach(g=>(g.mon||[]).forEach(m=>{
    const b=M[m.ym]=M[m.ym]||{ym:m.ym,total:0,n:0,bad:0,bad_n:0,src:{},cat:{}};
    b.total+=m.total||0; b.n+=m.n||0; b.bad+=m.bad_total||0; b.bad_n+=m.bad_n||0;
    if(m.total||m.bad_total)b.src[g.src]={t:m.total||0,n:m.n||0,bt:m.bad_total||0,bn:m.bad_n||0};}));
  // הייעודים מגיעים מהתרומות עצמן — שם יושב "עבור מה"
  DB.forEach(d=>(d.donations||[]).forEach(x=>{
    const ym=String(x.date||'').slice(0,7); if(ym.length!==7)return;
    const b=M[ym]=M[ym]||{ym,total:0,n:0,bad:0,bad_n:0,src:{},cat:{}};
    const c=String(x.category||'').trim()||'— בלי ייעוד —';
    const e=b.cat[c]=b.cat[c]||{t:0,n:0}; e.t+=amtNum(x.amount); e.n++;}));
  const list=Object.values(M).sort((a,b)=>b.ym.localeCompare(a.ym));
  el.innerHTML=`<div class="cnt">📅 הכל לפי חודשים — מהחדש לישן
      <button class="btn sm ghost" id="mballx">✕ סגור</button></div>
    ${list.map(b=>`<details class="monbox2"${b.ym===list[0].ym?' open':''}>
      <summary><b>${esc(fmtMonth(b.ym+'-01')||b.ym)}</b>
        <span class="m2t">${f(b.total)}</span>
        <small>${b.n} חיובים${b.bad_n?(' · 🔴 '+b.bad_n+' לא עברו '+f(b.bad)):''}</small></summary>
      <div class="m2sec">💳 דרך איפה עבר</div>
      ${Object.entries(b.src).sort((x,y)=>y[1].t-x[1].t).map(([k,v])=>`<div class="m2row">
        <span>${esc(srcLabel(k))}</span><b>${f(v.t)}</b><small>${v.n}${v.bn?(' · 🔴 '+v.bn):''}</small></div>`).join('')||'<div class="hintxt">—</div>'}
      <div class="m2sec">🎯 עבור מה</div>
      ${Object.entries(b.cat).sort((x,y)=>y[1].t-x[1].t).map(([k,v])=>`<div class="m2row">
        <span>${esc(k)}</span><b>${f(v.t)}</b><small>${v.n}</small></div>`).join('')||'<div class="hintxt">—</div>'}
    </details>`).join('')||'<div class="empty">אין נתונים</div>'}`;
  const c=document.getElementById('mballx'); if(c)c.onclick=()=>{ledAll=false;renderLedger();};
}
// גלילה אל הפירוט שנפתח — בלי זה הוא נפתח מתחת לגובה המסך ונראה כאילו לא נלחץ
function ledScroll(el){ if(el&&el.innerHTML)setTimeout(()=>el.scrollIntoView({block:'start',behavior:'smooth'}),40); }
const STLBL={declined:'🔴 סורב',error:'⚠️ שגיאה',voided:'בוטל',refund:'הוחזר',
  held:'מעוכב',pending:'🕒 ממתין'};
function renderCharges(){
  const all=[];
  DB.forEach(d=>(d.transactions||[]).forEach(t=>all.push({t,d})));
  all.sort((a,b)=>String(b.t.date||'').localeCompare(String(a.t.date||''))||b.t.id-a.t.id);
  const cnt=s=>all.filter(x=>x.t.status===s).length;
  const CF=[['','הכל',all.length],['pending','🕒 ממתין',cnt('pending')],['approved','✅ אושרו',cnt('approved')],['settled','💰 נגבו',cnt('settled')],['declined','🔴 סורבו',cnt('declined')]];
  // סרגל הסינון הישן נשען על טבלת העסקאות הידניות. אם היא ריקה — אין מה להציג
  chips.innerHTML=all.length?CF.map(([k,l,n])=>`<button class="chip ${chFilter===k?'on':''}" data-k="${k}">${l} <b>${n}</b></button>`).join(''):'';
  chips.querySelectorAll('.chip').forEach(c=>c.onclick=()=>{chFilter=c.dataset.k;renderCharges();});
  let rows=chFilter?all.filter(x=>x.t.status===chFilter):all;
  rows=rows.filter(x=>matchQ((x.d.last||'')+' '+(x.d.first||'')+' '+(x.t.category||'')));
  const paid=all.filter(x=>x.t.status==='settled'||x.t.status==='approved').reduce((s,x)=>s+amtNum(x.t.amount),0);
  const pend=all.filter(x=>x.t.status==='pending').reduce((s,x)=>s+amtNum(x.t.amount),0);
  view.innerHTML=`<div class="rbtitle">💳 טיפול והתאמת תרומות — לפי שיטת תשלום (ינואר–אוגוסט 2026)</div>
    <div class="addrow" style="margin:0 2px 8px"><button class="btn sm ghost" id="ch_mailsync" style="width:100%">📥 משוך מיילים (נכנסים + ששלחנו) ותייק אצל התורמים</button></div>
    <div class="addrow" style="margin:0 2px 8px"><button class="btn sm ghost" id="ch_anet" style="width:100%">💳 משוך חיובים מאוטרייז עכשיו</button></div>
    <div class="addrow" style="margin:0 2px 8px"><button class="btn sm ghost" id="ch_audit" style="width:100%">🔍 בדיקת סתירות — אקסל מול חיובים בפועל</button></div>
    <div id="auditbox"></div>
    <div id="ledgerbox">טוען…</div>
    <div id="reconboxes" class="reconboxes"></div>`+
    (rows.length?`<div class="cnt">${rows.length} חיובים</div><div class="list">`:'<div class="list hidden">')+
    (rows.map(({t,d})=>{const st=TXST[t.status]||TXST.pending;const rc=curSym(d);return `<div class="rowc" data-id="${d.id}"><div><div class="nm">${esc(d.last)} <small>${esc(d.first)}</small></div><div class="purp">${rc}${esc(t.amount)} ${t.category?('· '+esc(t.category)):''}${txInst(t,rc)}${txUntil(t)}</div></div><div class="meta"><span class="txbadge ${st.c}">${st.t}</span><span class="ph">${esc(t.date||'')}${t.method?(' · '+esc(t.method)):''}</span></div></div>`;}).join('')||'<div class="empty">אין חיובים</div>')+`</div>`;
  view.querySelectorAll('.rowc').forEach(r=>r.onclick=()=>openDonor(DB.find(x=>x.id==r.dataset.id)));
  renderLedger();
  const can=document.getElementById('ch_anet');
  if(can)can.onclick=async()=>{
    can.disabled=true; const o=can.textContent; can.textContent='מושך מאוטרייז…';
    const r=await api('POST','/api/authorize/sync',{days:10});
    can.disabled=false; can.textContent=o;
    if(r&&r.ok){const x=r.result||{};
      toast('נבדקו '+(x['נבדקו']||0)+' · נוספו '+(x['נוספו']||0)+' · שויכו '+(x['שויכו']||0));
      LEDGER=null; await load(); render();}
    else if(r&&r.error==='not_configured')
      toast('החיבור לאוטרייז עדיין לא הוגדר — צריך להזין את המפתחות ב-Render');
    else toast('לא הצליח: '+((r&&r.error)||'שגיאה'));};
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
  wireIzSum(nb,d);
}
// חיווט הסיכום: מעבר לשותף, וסימון התשלומים שלא סווגו
function wireIzSum(box,d){
  if(!box)return;
  box.querySelectorAll('.cosp2[data-did]').forEach(x=>x.onclick=()=>{const dd=DB.find(y=>y.id==x.dataset.did);if(dd)openDonor(dd);});
  const b2=box.querySelector('#izclaim');
  if(b2)b2.onclick=async()=>{
    const un=unclassifiedIz(d); if(!un.n)return;
    b2.disabled=true; b2.textContent='מסמן…';
    const CAT='יששכר־זבולון';
    for(const x of un.rows){
      const note=String(x.note||'').replace(/\s*·?\s*לא סווג[^·]*/,'').trim();
      x.category=CAT; x.note=note;
      await api('PUT','/api/donation/'+x.id,{category:CAT,note});
    }
    toast('סומנו '+un.n+' תשלומים ✓');
    await load();
    const nd=DB.find(y=>y.id===d.id)||d;
    Object.assign(d,nd);
    refreshIzSum(d); if(tab==='donors')renderDonors();};
}
function renderPartners(d){
  const el=document.getElementById('partners');if(!el)return;
  const act=(d.partners||[]).filter(p=>p.active!=0);
  const izfiles=(d.files||[]).filter(f=>f.kind==='iz'||!f.kind);
  const cur=curSym(d);
  el.innerHTML=act.map(p=>`<div class="pledge" style="flex-direction:column;align-items:stretch;gap:4px">
    <div style="display:flex;justify-content:space-between;align-items:center"><b>👨‍🎓 אברך שהוא מחזיק</b><button class="del" data-del="${p.id}">🗑</button></div>
    <select class="pfield pav" data-id="${p.id}" data-k="avreich" style="font-weight:700">${avOpts(p.avreich||'')}</select>
    <div class="addrow hidden pavnew" data-id="${p.id}"><input class="pavni" placeholder="שם האברך החדש — משפחה ואז פרטי"><button class="btn sm pavnb" data-id="${p.id}">➕ הוסף</button></div>
    <div class="two"><label class="fld"><span>סכום</span><div class="curwrap"><select class="pfield curpick" data-id="${p.id}" data-k="cur">${curOpts(pCur(p,d))}</select><input class="pfield" data-id="${p.id}" data-k="amount" value="${esc(p.amount||'')}" inputmode="decimal" placeholder="0"></div></label>
      <label class="fld"><span>איך משולם</span><select class="pfield chansel" data-id="${p.id}" data-k="method">${channelOpts(p.method)}</select></label></div>
    <label class="fld"><span>מתאריך (עברי)</span><input class="pfield" data-id="${p.id}" data-k="start_date" value="${esc(p.start_date||'')}" placeholder="א' אייר תשפ״ו"></label>
    <div class="fld"><span>🤝 מחזיקים יחד עם (אפשר כמה שותפים)</span>
      <div class="pwchips" data-id="${p.id}">${pwList(p).map((x,i)=>`<span class="pwchip">${x.id?'🔗 ':''}${esc(x.name)}<button class="pwx" data-id="${p.id}" data-idx="${i}" title="הסר">✕</button></span>`).join('')}</div>
      <input class="pwadd" data-id="${p.id}" placeholder="➕ הוסף שותף — חפש שם ובחר…" autocomplete="off"><div class="pwres dpres" data-id="${p.id}"></div></div>
    <label class="jointchk"><input type="checkbox" class="pjoint" data-id="${p.id}" ${+p.joint?'checked':''}> 🤝 מחזיקים אותו <b>ביחד</b> — הסכום למעלה הוא הסכום המשותף לכולם</label>
    ${+p.joint&&jointHolders(p)>1?`<label class="fld"><span>💳 מי משלם בפועל</span><select class="ppayer" data-id="${p.id}">
      <option value="">כל אחד את חלקו (${curSym(d)}${Math.round(amtNum(p.amount)/jointHolders(p))} לכל אחד)</option>
      ${jointGroup(p).map(g=>`<option value="${g.d.id}" ${jointPayerId(p)===g.d.id?'selected':''}>${esc(((g.d.business||'').trim()||((g.d.last||'')+' '+(g.d.first||'')).trim()))} — משלם את כל ${curSym(d)}${amtNum(p.amount)}</option>`).join('')}
    </select></label>
    <div class="hintxt" style="margin:-6px 2px 6px">כשעסק אחד או כרטיס אחד משלם על כולם — בחר אותו כאן, והסכום ייזקף רק אליו. ההגדרה חלה על כל המחזיקים.</div>
    <label class="fld"><span>💳 או: כמה <b>${esc((d.last+' '+(d.first||'')).trim())}</b> משלם בפועל מהכרטיס שלו (${pCur(p,d)})</span>
      <input class="pfield" data-id="${p.id}" data-k="share" value="${esc(p.share||'')}" inputmode="decimal" placeholder="השאר ריק לחלוקה שווה"></label>
    <div class="hintxt" style="margin:-6px 2px 6px">כשהחלוקה אינה שווה — רשום כאן אצל כל מחזיק את הסכום שלו (0 למי שמחזיק ואינו משלם). זה גובר על החלוקה השווה.</div>`:''}
    <label class="fld"><span>💵 שילם עד סוף חודש (מזומן / צ'ק ביד — תשלום שלא נרשם במערכת)</span><input type="month" class="pfield" data-id="${p.id}" data-k="paid_thru" value="${esc(p.paid_thru||'')}"></label>
    <label class="fld"><span>💰 הערה על האברך (למשל: "שילם הכל מראש 13/7")</span><input class="pfield" data-id="${p.id}" data-k="paid_note" value="${esc(p.paid_note||'')}" placeholder="הערה אחת — נשמרת ומוצגת בסיכום"></label>
    <button class="btn sm psave" data-id="${p.id}" style="width:100%;margin-top:4px">💾 שמור אברך</button>
  </div>`).join('');
  // מאיר: "עדיין לא כתוב אצל יואל שטטפלד כלום לגבי היששכר־זבולון שהוא
  // מחזיק ביחד עם בנימין". אברך שהוא מחזיק בשותפות והשורה שלו רשומה אצל
  // השותף מופיע גם כאן — בלי שדות עריכה, כי הם שייכים לשורה המקורית.
  const lnk=izLinkedRows(d);
  el.innerHTML+=lnk.map(x=>`<div class="pledge plink" style="flex-direction:column;align-items:stretch;gap:4px">
    <div style="display:flex;justify-content:space-between;align-items:center">
      <b>👨‍🎓 ${esc(x.avreich)}</b>
      <span class="plinktag">🤝 בשותפות</span></div>
    <div class="hintxt" style="margin:0">מחזיק אותו יחד עם
      <b class="cosp2" data-did="${x.did}">${esc(x.name)} ↗</b>${x.amount
        ?(' · '+(x.split?'התשלום יוצא ממנו':'רשום אצלו')+' '+cur+Math.round(amtNum(x.amount))):''}.
      השורה עצמה נמצאת בכרטיס שלו, ולכן נערכת שם — כדי שהסכום לא ייספר פעמיים.</div>
  </div>`).join('');
  if(!act.length&&!lnk.length)
    el.innerHTML='<div class="hintxt">עדיין לא הוזן. הוסף אברך למטה.</div>';
  el.innerHTML+=`<div class="izshtar"><div class="izshtar-t">📝 מעקב חוב יששכר־זבולון</div>
      <label class="fld"><span>🔴 כמה הוא חייב עכשיו (${cur}) — עדכון ידני שגובר על החישוב</span><input id="iz_debt" inputmode="decimal" value="${esc(d.iz_debt||'')}" placeholder="השאר ריק כדי לחשב אוטומטית"></label>
      <div class="hintxt">ההערה על ההתחייבות ("שילם מראש, מכסה עד אלול") נכתבת בשורת יששכר־זבולון בסוף דף התורם — שם הכל במקום אחד.</div></div>
    <div class="izshtar"><div class="izshtar-t">📄 שטר שותפות:</div><div class="avfiles">${izfiles.map(fileChip).join('')||'<span class="hintxt">אין שטר עדיין</span>'}<label class="filebtn">📎 העלה שטר הסכם<input type="file" accept="application/pdf,image/*" class="pshtar" hidden></label></div></div>`;
  const izd=el.querySelector('#iz_debt');
  if(izd)izd.onblur=async()=>{if((d.iz_debt||'')===izd.value.trim())return;
    d.iz_debt=izd.value.trim();
    await api('PUT','/api/donor/'+d.id,{iz_debt:d.iz_debt});
    refreshIzSum(d);toast('נשמר ✓');};
  // רשימת האברכים של הכולל — נטענת פעם אחת, וכשהיא מגיעה הבחירה מתמלאת
  if(!AVLIST.length)loadAvList().then(()=>{
    el.querySelectorAll('select.pav').forEach(s=>{
      const p=(d.partners||[]).find(x=>x.id==s.dataset.id);
      s.innerHTML=avOpts((p&&p.avreich)||'');});});
  // ➕ אברך חדש — נוסף לרשימת הכולל ונבחר מיד בשורה הזו
  el.querySelectorAll('select.pav').forEach(sel=>{
    const row=el.querySelector('.pavnew[data-id="'+sel.dataset.id+'"]');
    sel.addEventListener('change',()=>{const on=sel.value==='__new__';
      if(row){row.classList.toggle('hidden',!on);if(on)row.querySelector('.pavni').focus();}});
  });
  el.querySelectorAll('.pavnb').forEach(btn=>{
    const row=btn.closest('.pavnew'),inp=row.querySelector('.pavni');
    const add=async()=>{
      const nm=inp.value.trim();
      if(nm.length<2){toast('כתוב את שם האברך');inp.focus();return;}
      const p=(d.partners||[]).find(x=>x.id==btn.dataset.id); if(!p)return;
      btn.disabled=true;
      const r=await api('POST','/api/avreich/new',{name:nm});
      btn.disabled=false;
      if(!r||!r.ok){toast('ההוספה נכשלה');return;}
      p.avreich=nm;
      await api('PUT','/api/partner/'+p.id,{avreich:nm});
      await loadAvList();
      toast(r.existed?'האברך כבר היה ברשימה — נבחר ✓':'האברך נוסף לרשימה ונבחר ✓');
      renderPartners(d); refreshIzSum(d); if(tab==='donors')renderDonors();};
    btn.onclick=add;
    inp.onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();add();}};
  });
  el.querySelectorAll('.pfield').forEach(inp=>{
    const save=async()=>{const p=(d.partners||[]).find(x=>x.id==inp.dataset.id);if(!p)return;
      if(inp.value==='__new__')return;      // בחירת "דרך תשלום חדשה" — לא ערך לשמירה
      p[inp.dataset.k]=inp.value;await api('PUT','/api/partner/'+p.id,{[inp.dataset.k]:inp.value});refreshIzSum(d);
      if(inp.dataset.k==='cur')renderPartners(d);            // הסמלים בשדות מתעדכנים מיד
      if(inp.dataset.k==='avreich'){await loadAvList();renderPartners(d);}
      if((inp.dataset.k==='amount'||inp.dataset.k==='cur'||inp.dataset.k==='avreich')&&tab==='donors')renderDonors();};
    inp.onchange=save;
    if(inp.tagName!=='SELECT'){let tmr;inp.oninput=()=>{clearTimeout(tmr);tmr=setTimeout(save,800);};}
  });
  el.querySelectorAll('.psave').forEach(btn=>btn.onclick=async()=>{
    const p=(d.partners||[]).find(x=>x.id==btn.dataset.id);if(!p)return;
    const body={};el.querySelectorAll('.pfield[data-id="'+btn.dataset.id+'"]').forEach(inp=>{
      if(inp.value==='__new__')return; p[inp.dataset.k]=inp.value;body[inp.dataset.k]=inp.value;});
    await api('PUT','/api/partner/'+p.id,body);refreshIzSum(d);toast('נשמר ✓');if(tab==='donors')renderDonors();
  });
  // שדה שותפים — מספר שותפים (צ'יפים). בחירה מרשימה מקשרת לכרטיס (מופיע גם אצלו); Enter מוסיף כטקסט
  const savePw=async(p)=>{p.partner_with=pwList(p).map(x=>x.name).join(', ');p.partner_with_id=pwList(p).map(x=>x.id).join(',');await api('PUT','/api/partner/'+p.id,{partner_with:p.partner_with,partner_with_id:p.partner_with_id});renderPartners(d);if(tab==='donors')renderDonors();};
  const addPw=async(pid,name,did)=>{const p=(d.partners||[]).find(x=>x.id==pid);if(!p)return;const l=pwList(p);l.push({name:name,id:did?String(did):''});p.partner_with=l.map(x=>x.name).join(', ');p.partner_with_id=l.map(x=>x.id).join(',');await api('PUT','/api/partner/'+p.id,{partner_with:p.partner_with,partner_with_id:p.partner_with_id});
    // השותף שנבחר הוא תורם יששכר־זבולון לכל דבר — מסומן מיד על המסך
    const o=did&&DB.find(x=>x.id==did);
    if(o&&o.tier!=='יששכר_זבולון')o.tier='יששכר_זבולון';
    toast('שותף נוסף ✓ — מופיע גם אצלו');renderPartners(d);if(tab==='donors')renderDonors();};
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
  el.querySelectorAll('.cosp2[data-did]').forEach(x=>x.onclick=()=>{
    const dd=DB.find(y=>y.id==x.dataset.did); if(dd)openDonor(dd);});
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
// סוגי הקשר — הקבועים, ואחריהם כל סוג שמאיר הוסיף בעצמו
const CLKINDS=['טלפון','אימייל','וואטסאפ','פגישה'];
function clkOpts(cur){cur=(cur||'').trim();
  const l=CLKINDS.concat((CLK_C||[]).filter(x=>CLKINDS.indexOf(x)<0));
  return l.map(k=>`<option value="${esc(k)}"${k===cur?' selected':''}>${esc(k)}</option>`).join('')
    +(cur&&l.indexOf(cur)<0?`<option value="${esc(cur)}" selected>${esc(cur)}</option>`:'')
    +'<option value="__new__">➕ סוג קשר חדש…</option>';}
// הוספת סוג קשר מתוך התיבה עצמה — נשמר ומופיע מכאן והלאה
function wireClkSel(sel){
  if(!sel||sel._kbox2)return;
  const box=document.createElement('div'); box.className='chanbox';
  box.innerHTML='<input class="channew" placeholder="שם סוג הקשר (למשל: פגישה בבית)" style="display:none">'
    +'<button type="button" class="btn sm chandel" title="מחק סוג זה" style="display:none">🗑</button>';
  sel.parentNode.insertBefore(box,sel.nextSibling); sel._kbox2=box;
  const inp=box.querySelector('.channew'), del=box.querySelector('.chandel');
  const showDel=()=>{del.style.display=(CLK_C||[]).includes(sel.value)?'':'none';};
  sel.addEventListener('change',()=>{
    if(sel.value==='__new__'){inp.style.display='';inp.focus();del.style.display='none';return;}
    inp.style.display='none';showDel();});
  const add=async()=>{const nm=inp.value.trim(); if(!nm){inp.focus();return;}
    if(!(CLK_C||[]).includes(nm)){const r=await api('POST','/api/contactkinds',{name:nm});CLK_C=(r&&r.kinds)||CLK_C.concat([nm]);}
    inp.value='';inp.style.display='none';sel.innerHTML=clkOpts(nm);sel.value=nm;showDel();toast('נוסף סוג קשר ✓');};
  inp.onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();add();}};
  inp.onblur=()=>{if(inp.style.display==='none')return;
    if(inp.value.trim())add(); else{inp.style.display='none'; if(sel.value==='__new__')sel.value=CLKINDS[0];}};
  del.onclick=async()=>{const nm=sel.value; if(!nm||!(CLK_C||[]).includes(nm))return;
    if(!await uiConfirm('למחוק את סוג הקשר "'+nm+'" מהרשימה?\nרישומים קיימים יישארו כפי שהם.'))return;
    const r=await api('POST','/api/contactkinds',{name:nm,delete:1});CLK_C=(r&&r.kinds)||CLK_C.filter(x=>x!==nm);
    sel.innerHTML=clkOpts('');sel.value=CLKINDS[0];showDel();toast('נמחק');};
  showDel();
}
function renderContacts(d){
  const el=document.getElementById('clog');if(!el)return;
  // הכותרת כבר אומרת מה זה — אין צורך לחזור על "בוצע:" או "שלחנו:" גם בגוף
  const csum=c=>String(c.summary||'').replace(/^✓ בוצע:\s*/,'').replace(/^📤 (עניתי|שלחנו|נשלח):\s*/,'');
  const isRep=c=>!!c.reply_to;
  // כותרת השורה: פנייה שהגיעה מהתורם, מייל ששלחנו, תשובה שמאיר ענה, או משימה
  const head=c=>isRep(c)?'📤 עניתי לו':(c.direction==='out'?'📤 שלחנו':(c.task_id?'✅ משימה שבוצעה':esc(c.channel)));
  const rowHTML=c=>`<div class="logrow${c.direction==='out'?' outmail':''}${c.task_id?' taskdone':''}${isRep(c)?' replyrow':''}"><div class="pi"><b>${head(c)}</b> <small>${esc(c.date||'')}${hhmm(c.at)?(' · '+hhmm(c.at)):''}</small>${c.next_date?(' · <span style="color:var(--no)">חזור: '+esc(c.next_date)+'</span>'):''}<br>${esc(csum(c))}${(c.body||'').trim()?`<details class="mailfull"><summary>הצג את המייל המלא${(c.body_he||'').trim()?' (בעברית)':''}</summary>
      ${(c.body_he||'').trim()?`<pre class="mhe">${esc(c.body_he)}</pre>
        <details class="morig"><summary>🔤 הצג את המקור באנגלית</summary><pre>${esc(c.body)}</pre></details>`
      :`<pre>${esc(c.body)}</pre>${/[A-Za-z]{4}/.test(c.body||'')?`<button class="btn sm ghost mtr" data-cid="${c.id}">🌐 תרגם לעברית</button>`:''}`}
    </details>`:''}
    <div class="avfiles">${(c.files||[]).map(fileChip).join('')}<label class="filebtn">📎 צרף תמונה / הקלטה<input type="file" accept="image/*,audio/*,application/pdf" class="clup" data-id="${c.id}" hidden></label>
      <button class="btn sm ghost clrem" data-id="${c.id}">🔔 קבע תזכורת${(c.files||[]).length?' + האסמכתאות':''}</button>${(c.direction!=='out'&&!c.task_id)?`<button class="btn sm ghost creply" data-id="${c.id}">↩️ עניתי לו</button>`:''}${c.task_id?`<button class="btn sm ghost tundo" data-tid="${c.task_id}">↩️ החזר את המשימה לפתוחות</button>`:''}</div>
    <div class="teditpanel hidden" data-rep="${c.id}">
      <label class="fld"><span>✍️ מה עניתי לו</span><textarea class="rp_txt" data-id="${c.id}" rows="3" placeholder="הדבק כאן את מה שכתבת לו — או כתוב בקצרה. אפשר גם להשאיר ריק ורק לסמן שענית."></textarea></label>
      <div class="addrow" style="margin-top:6px"><input type="date" class="rp_date" data-id="${c.id}" value="${esc(todayStr())}"><button class="btn sm rp_save" data-id="${c.id}">💾 שמור את התשובה</button></div>
      ${c.channel==='אימייל'?'<div class="hintxt">אם ענית לו בג\'ימייל עצמו — התשובה נמשכת לכאן לבד ונתלית מתחת למייל הזה. כאן כותבים רק כשעונים מחוץ למייל.</div>':''}
    </div>
    <div class="teditpanel hidden" data-rem="${c.id}">
      <div class="fbrow"><label class="fld"><span>סוג</span><select class="cr_kind">${taskKindOpts()}</select></label>
        <label class="fld"><span>מתי להזכיר</span><input type="date" class="cr_date" value="${esc(todayStr())}"></label></div>
      <label class="fld"><span>פרטים</span><input class="cr_note" value="${esc(c.summary||'')}"></label>
      <button class="btn sm cr_save" data-id="${c.id}" style="margin-top:6px">➕ צור תזכורת</button>
    </div></div><button class="del" data-del="${c.id}">🗑</button></div>`;
  // תשובה נתלית מתחת לפנייה שעליה ענו, כדי שיהיה ברור מה הגיע ממנו ומה ענינו
  const all=d.contacts||[], kids={};
  all.forEach(c=>{if(c.reply_to)(kids[c.reply_to]=kids[c.reply_to]||[]).push(c);});
  Object.values(kids).forEach(a=>a.sort((x,y)=>String(x.at||x.date||'').localeCompare(String(y.at||y.date||''))));
  el.innerHTML=all.filter(c=>!c.reply_to)
    .map(c=>`<div class="thread">${rowHTML(c)}${(kids[c.id]||[]).map(rowHTML).join('')}</div>`)
    .join('')||'<div class="hintxt">אין עדיין תיעוד.</div>';
  addMics(el,['.rp_txt']);
  el.querySelectorAll('.creply').forEach(b=>b.onclick=()=>{
    const p=el.querySelector('.teditpanel[data-rep="'+b.dataset.id+'"]'); if(!p)return;
    p.classList.toggle('hidden');
    const ta=p.querySelector('.rp_txt'); if(!p.classList.contains('hidden')&&ta)ta.focus();});
  el.querySelectorAll('.rp_save').forEach(b=>b.onclick=async()=>{
    const id=b.dataset.id, ta=el.querySelector('.rp_txt[data-id="'+id+'"]'), dt=el.querySelector('.rp_date[data-id="'+id+'"]');
    b.disabled=true;
    const r=await api('POST','/api/contact/'+id+'/reply',{text:ta?ta.value.trim():'',date:dt?dt.value:'',at:nowStamp()});
    if(r&&r.ok&&r.contact){d.contacts=d.contacts||[];d.contacts.unshift(r.contact);renderContacts(d);toast('נרשם שענית ✓');}
    else{b.disabled=false;toast('לא נשמר — נסה שוב');}});
  el.querySelectorAll('.del').forEach(b=>b.onclick=async()=>{await api('DELETE','/api/contact/'+b.dataset.del);d.contacts=d.contacts.filter(x=>x.id!=b.dataset.del);renderContacts(d);});
  // ביטול הווי ישירות מהרישום — המשימה חוזרת לרשימה והשורה כאן נמחקת
  el.querySelectorAll('.tundo').forEach(b=>b.onclick=async()=>{
    const t=(d.tasks||[]).find(x=>x.id==b.dataset.tid);
    if(!t){toast('המשימה נמחקה — אפשר למחוק את השורה');return;}
    b.disabled=true; await setTaskDone(t,0,d);
    renderContacts(d);renderCardTasks(d);renderReminders(d);checkReminders();
    toast('חזרה לפתוחות ✓');});
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
// כמה נשאר לשלם מהתחייבות חד־פעמית: מה שהתחייב פחות מה שכבר שילם
// כמה נגבה בפועל לייעוד הזה מאז שנרשמה ההתחייבות. כך התחייבות בתשלומים
// מתעדכנת לבד — מאיר לא צריך למלא כל חודש כמה שולם.
// שותפות תשלום: הכסף לא נכנס אצל התורם הזה, אלא אצל תורם אחר שמשלם
// ביחד איתו (מאיר: "שולחים 2000 ביחד, אז אלף זה של לאקס"). כאן שולפים
// את הכרטיס שאצלו הכסף באמת נכנס, ואת החלק היחסי שמיוחס לכאן.
function viaDonorOf(p){
  const id=+(p&&p.via_donor_id||0); if(!id)return null;
  return (typeof DB!=='undefined'&&DB||[]).find(x=>x.id===id)||null;
}
function viaShare(p){
  const tot=amtNum(p.via_total), amt=amtNum(p.amount);
  return (tot>0.5&&amt>0)?Math.min(1,amt/tot):1;
}
function plCollected(d,p){
  const cat=String(p.category||'').trim(); if(!d||!cat)return 0;
  const via=viaDonorOf(p);
  let src=d, share=1;
  if(via){ src=via; share=viaShare(p); }
  else if((d.pledges||[]).filter(x=>String(x.category||'').trim()===cat).length>1)
    // שתי התחייבויות לאותו ייעוד — אי אפשר לדעת לאיזו שייך הכסף, ולכן
    // לא מייחסים אותו לאף אחת מהן ולא סופרים אותו פעמיים
    return 0;
  const from=String(p.date||'').slice(0,10);
  const rows=(src.donations||[]).filter(x=>{
    if(String(x.category||'').trim()!==cat)return false;
    const dt=String(x.date||'').slice(0,10);
    return !from||!dt||dt>=from;});
  const per=amtNum(p.permo);
  // תקרה חודשית: מול תשלום קבוע, לפי החלק המשותף עצמו (הסכום ששני
  // הצדדים שולחים ביחד) ולא לפי החלק היחסי — אחרת שני חיובים זהים
  // מהייבוא באותו חודש נספרים כפול, בלי קשר לשותפות
  const cap=via?(amtNum(p.via_total)||per):per;
  if(cap<=0.5)return share*rows.reduce((a,x)=>a+amtNum(x.amount),0);
  // תוכנית תשלומים היא חודשית: חודש אחד = תשלום אחד לכל היותר. אצל
  // אברמוביץ יש בכמה חודשים שני חיובים זהים מהייבוא, ובלי התקרה הזו
  // הם נספרו כשני תשלומים והמניין יצא גבוה מהאמת.
  const by={};
  rows.forEach(x=>{const m=String(x.date||'').slice(0,7)||'?';
    by[m]=(by[m]||0)+amtNum(x.amount);});
  return share*Object.keys(by).reduce((a,m)=>a+Math.min(cap, by[m]), 0);
}
// מי משלם דרך הכרטיס הזה עבור התחייבות של תורם אחר — כדי שיראה כאן
// שחלק ממה שהוא שולח שייך למישהו אחר, ולא ייראה כאילו הוא שלו
// חיפוש תורם להצמדה — משמש גם לשותפות תשלום וגם למיזוג כרטיסים
function wireDonorSearch(qEl,resEl,onPick,excludeId){
  if(!qEl||!resEl)return;
  qEl.oninput=()=>{
    const s=norm(qEl.value); if(!s){resEl.innerHTML='';return;}
    const m=(DB||[]).filter(x=>x.id!==excludeId
      &&norm(x.last+' '+x.first+' '+x.english+' '+x.phone).includes(s)).slice(0,8);
    resEl.innerHTML=m.map(x=>`<div class="dpr" data-did="${x.id}">${esc(x.last)} ${esc(x.first)} <span style="color:var(--muted)">#${x.id}</span></div>`).join('')
      ||'<div class="dpr" style="color:var(--muted)">אין תוצאות</div>';
    resEl.querySelectorAll('.dpr[data-did]').forEach(el=>el.onclick=()=>{
      const dd=DB.find(x=>x.id==el.dataset.did); if(!dd)return;
      onPick(dd); qEl.value=''; resEl.innerHTML='';});
  };
}
function viaLinkedIn(d){
  const out=[];
  (typeof DB!=='undefined'&&DB||[]).forEach(x=>(x.pledges||[]).forEach(p=>{
    if(+(p.via_donor_id||0)===d.id)out.push({from:x,p});}));
  return out;
}
// מה ששולם ידנית ומה שנגבה במערכת. תקרה בסכום ההתחייבות, כדי שסיווג
// מאוחר של תרומות ישנות לא ייצור "שולם" גדול מההתחייבות עצמה.
// מאיר: "תלך רק מה שמעודכן אצלך". כשיש תשלומים שנקלטו במערכת הם הקובעים,
// והסכום הידני אינו מתווסף עליהם — אחרת אותו כסף נספר פעמיים והמספרים
// סותרים זה את זה. הסכום הידני משמש רק כשעדיין לא נקלט כלום.
function plPaid(d,p){
  const tot=amtNum(p.amount), got=plCollected(d,p);
  const v=got>0.5?got:amtNum(p.paid);
  return tot>0.5?Math.min(tot,v):v;
}
function plLeft(d,p){
  if(p===undefined){p=d;d=null;}            // תאימות לקריאות ישנות
  return Math.max(0, amtNum(p.amount)-plPaid(d,p));
}
// תשלומים שכבר רשומים בכרטיס ומתאימים להתחייבות שנרשמת עכשיו — אותו סכום,
// מחודש ההתחלה והלאה. מאיר: "שלא יהיה פה כפילויות, שאוכל למזג את זה".
function instMatches(d,per,fromYM,cat){
  if(!(per>0.5))return [];
  const from=String(fromYM||'').slice(0,7);
  const tol=Math.max(1, per*0.02);
  return (d.donations||[]).filter(x=>{
    if(Math.abs(amtNum(x.amount)-per)>tol)return false;
    const m=String(x.date||'').slice(0,7);
    if(from&&m&&m<from)return false;
    return String(x.category||'').trim()!==String(cat||'').trim();
  }).sort((a,b)=>String(a.date||'').localeCompare(String(b.date||'')))
    .filter((x,i,l)=>{      // חודש אחד = תשלום אחד, כמו בספירה עצמה
      const m=String(x.date||'').slice(0,7);
      return !m||l.findIndex(y=>String(y.date||'').slice(0,7)===m)===i;});
}
// כמה בכל תשלום, כמה נשארו, ומתי התשלום האחרון
function plPlan(d,p){
  const per=amtNum(p.permo); if(per<=0.5)return null;
  const left=plLeft(d,p), tot=amtNum(p.amount);
  // 2,200 ל-12 תשלומים = 183.33 — בלי סובלנות קטנה זה היה מציג 13 תשלומים
  const n=Math.max(0, Math.ceil(left/per - 0.02));
  const all=tot>0.5?Math.max(n, Math.ceil(tot/per - 0.02)):n;
  const from=String(p.date||'').slice(0,7);
  // כמה תשלומים אמורים לעבור עד היום לפי הלוח. כשקובץ הבנק עדיין לא
  // נקלט, זה מסביר לבד למה נרשמו פחות — במקום שהמספר ייראה שגוי.
  const due=Math.min(all, Math.max(0, monthsBetween(from, todayStr().slice(0,7))+1));
  return {per, left, n, all, done:Math.max(0,all-n), due,
          from, end:monthPlus(from, all-1)};
}
function monthsBetween(a,b){
  const x=String(a||'').match(/^(\d{4})-(\d{2})/), y=String(b||'').match(/^(\d{4})-(\d{2})/);
  if(!x||!y)return -1;
  return (+y[1]*12 + +y[2]) - (+x[1]*12 + +x[2]);
}
// חודש + N חודשים, בעברית פשוטה ("נובמבר 2026")
function monthPlus(ym,n){
  const m=String(ym||'').match(/^(\d{4})-(\d{2})/); if(!m||n<0)return '';
  let y=+m[1], mo=+m[2]-1+n; y+=Math.floor(mo/12); mo=((mo%12)+12)%12;
  return MONFULL[mo]+' '+y;
}
function autoGrow(t){t.style.height='auto';t.style.height=(t.scrollHeight+6)+'px';}
// העתקה ללוח — עם נפילה חלופה לאפליקציה מותקנת (execCommand)
async function copyToClip(txt,okMsg){
  txt=(txt||'').trim();if(!txt){toast('אין מה להעתיק');return;}
  try{await navigator.clipboard.writeText(txt);toast(okMsg||'הועתק ✓');return;}catch(e){}
  try{const ta=document.createElement('textarea');ta.value=txt;ta.style.position='fixed';ta.style.opacity='0';document.body.appendChild(ta);ta.focus();ta.select();document.execCommand('copy');ta.remove();toast(okMsg||'הועתק ✓');}
  catch(e){prompt('העתק ידנית:',txt);}
}
let PRSAVE=null;
// טקסט שנכתב בשמות הקוויטל ולא נשמר — נשמר לפני יציאה, כדי שלא ייעלם
async function flushPrayers(){ const f=PRSAVE; PRSAVE=null;
  if(!f)return; try{ if(document.querySelector('.prtx')) await f(); }catch(e){} }
function renderPrayers(d){
  const el=document.getElementById('prayers');
  const prs=(d.prayers||[]);
  const allBtn=prs.length>1?`<button class="btn sm ghost" id="prcopyall" style="width:100%;margin-bottom:6px">📋 העתק את כל השמות</button>`:'';
  el.innerHTML=allBtn+(prs.map(p=>`<div class="prow"><textarea class="prtx" data-id="${p.id}">${esc(p.text)}</textarea><button class="prcopy" data-id="${p.id}" title="העתק שם">📋</button><button class="del" data-del="${p.id}">🗑</button></div>`).join('')||'<div class="hintxt">אין שמות עדיין. הוסף למטה.</div>')
    +(prs.length?`<button class="btn sm prsaveall" id="prsaveall" style="width:100%;margin-top:4px">💾 שמור שמות</button>
       <div class="hintxt dirtyhint hidden" id="prdirty">✏️ יש שינוי שעדיין לא נשמר — לחץ "💾 שמור שמות"</div>`:'');
  const prMark=()=>{const dirty=[...el.querySelectorAll('.prtx')].some(t=>{const p=prs.find(x=>x.id==t.dataset.id);return p&&p.text!==t.value;});
    const h=el.querySelector('#prdirty'),b2=el.querySelector('#prsaveall');
    if(h)h.classList.toggle('hidden',!dirty); if(b2)b2.classList.toggle('warn',dirty);};
  const prSaveAll=async()=>{let n=0;
    for(const t of el.querySelectorAll('.prtx')){const p=d.prayers.find(x=>x.id==t.dataset.id);
      if(!p||p.text===t.value)continue; p.text=t.value; await api('PUT','/api/prayer/'+p.id,{text:t.value}); n++;}
    prMark(); if(n)toast('נשמר ✓ '+n+' '+(n===1?'שם':'שמות')); else toast('אין מה לשמור');};
  el.querySelectorAll('.prtx').forEach(t=>{autoGrow(t);
    t.addEventListener('input',()=>{autoGrow(t);prMark();});
    t.onblur=async()=>{const p=d.prayers.find(x=>x.id==t.dataset.id);if(!p||p.text===t.value)return;p.text=t.value;await api('PUT','/api/prayer/'+p.id,{text:t.value});prMark();toast('נשמר ✓');};});
  const sa=el.querySelector('#prsaveall'); if(sa)sa.onclick=prSaveAll;
  PRSAVE=prSaveAll;   // כדי שסגירת הכרטיס לא תאבד טקסט שנכתב ולא נשמר
  el.querySelectorAll('.prcopy').forEach(b=>b.onclick=()=>{const t=el.querySelector('.prtx[data-id="'+b.dataset.id+'"]');copyToClip(t?t.value:'','השם הועתק ✓');});
  const ca=document.getElementById('prcopyall');if(ca)ca.onclick=()=>{const txt=[...el.querySelectorAll('.prtx')].map(t=>t.value.trim()).filter(Boolean).join('\n');copyToClip(txt,'כל השמות הועתקו ✓');};
  el.querySelectorAll('.del').forEach(b=>b.onclick=async()=>{await api('DELETE','/api/prayer/'+b.dataset.del);d.prayers=d.prayers.filter(x=>x.id!=b.dataset.del);renderPrayers(d);toast('נמחק');});
}
const DAYKIND={parnes:'🌙 פרנס',coffee:'☕ קפה',breakfast:'🍳 בוקר'};
const DAYSAVE={parnes:'🌙 יום פרנס',coffee:'☕ חדר קפה',breakfast:'🍳 ארוחת בוקר'};
// תורם שתפס ימים רצופים — רצף הימים שמכיל את היום שנבחר. תעודה אחת
// לכל הרצף, בלי לשאול: אם לקח ד' וה' אלול תיווצר תעודה של ד'–ה'
// היום והחודש של שורת פרנס. חלק מהשורות נשמרו בלי day/month ורק עם
// התאריך הכתוב ("ה' אלול"), ואז השוואה לפי השדות בלבד פספסה אותן
function pyClean(t){return String(t||'').replace(/["'\u05f3\u05f4]/g,'').trim();}
function pyDM(x){
  let dn=+((x&&x.day)||0), mo=(x&&x.month)||'';
  const t=String((x&&x.date_text)||'');
  if(!mo) mo=HMORD.find(m=>t.indexOf(m)>=0)||'';
  if(!dn){
    const head=pyClean(t.split(/\s+/)[0]);
    for(let n=1;n<=30;n++){ if(pyClean(heDay(n))===head){dn=n;break;} }
  }
  return {d:dn, m:mo};
}
function parnesRun(d,p){
  if(!d||!p)return [p];
  const me=pyDM(p);
  if(!me.d||!me.m)return [p];
  // אותו תורם, אותו חודש, ימים צמודים — תעודה אחת. בלי תנאים נוספים:
  // סוג הפרנס, סטטוס ושנה עברית לא נבדקים, כי בפועל הם נשמרים לא אחיד
  // ואז שני ימים שהתורם באמת לקח נשארו שתי תעודות
  const by={};
  (d.parnes||[]).forEach(x=>{
    const k=pyDM(x);
    if(!k.d||k.m!==me.m)return;
    if(!by[k.d]||(x.id&&p.id&&+x.id===+p.id))by[k.d]={...x, day:k.d, month:k.m};
  });
  let lo=me.d, hi=me.d;
  while(by[lo-1])lo--;
  while(by[hi+1])hi++;
  const out=[]; for(let n=lo;n<=hi;n++)out.push(by[n]);
  return out.length?out:[p];
}
function parnesCertUrl(d,p){
  const run=parnesRun(d,p);
  if(run.length>1)return parnesCertUrlMulti(d,run);
  const dtext=(p.day&&p.month)?(heDay(+p.day)+" "+p.month):(p.date_text||'');
  const yr=p.hyear||HEBYEAR;const date=dtext+(yr?(' '+yr):'');
  const names=(p.dedication&&p.dedication.trim())||(d&&d.prayers&&d.prayers[0]&&d.prayers[0].text)||'';
  return location.origin+'/parnes-cert?'+new URLSearchParams({kind:p.kind||'parnes',date,names}).toString();
}
// למה יום צמוד לא נכנס לאותה תעודה — מוצג מיד, במקום לנחש
function runWhyNot(d,p){
  if(!d||!p)return '';
  const me=pyDM(p);
  const near=(d.parnes||[]).filter(x=>{const k=pyDM(x);
    return k.m===me.m && Math.abs(k.d-me.d)===1;});
  if(!near.length)return 'אין לו יום צמוד ב'+(me.m||'חודש הזה')+' — תעודה ליום אחד';
  return '';
}
function openParnesCert(d,p){
  if(!p)return;
  const run=parnesRun(d,p);
  if(run.length>1)toast('תעודה משותפת: '+parnesDateLabel(run));
  else{const w=runWhyNot(d,p); if(w)toast(w);}
  window.open(parnesCertUrl(d,p),'_blank');
}
// כמה ימים בתעודה אחת — "ב'–ג' אלול תשפ\"ו" כשהם רצופים, אחרת "ב' ו־ה'"
function pyKey(p){return (HMORD.indexOf(p.month||'')*100)+(+p.day||0);}
function parnesDateLabel(list){
  const ok=list.filter(p=>p.month&&p.day).slice().sort((a,b)=>pyKey(a)-pyKey(b));
  if(!ok.length)return (list[0]&&list[0].date_text)||'';
  const yr=ok[0].hyear||HEBYEAR;
  const oneMonth=ok.every(p=>p.month===ok[0].month&&(p.hyear||HEBYEAR)===yr);
  if(!oneMonth)
    return ok.map(p=>heDay(+p.day)+' '+p.month+((p.hyear||HEBYEAR)?(' '+(p.hyear||HEBYEAR)):'')).join(' · ');
  const days=ok.map(p=>+p.day);
  const seq=days.every((n,i)=>i===0||n===days[i-1]+1);
  const body=(days.length>1&&seq)?(heDay(days[0])+'–'+heDay(days[days.length-1]))
    :days.map(heDay).join(' ו־');
  return body+' '+ok[0].month+(yr?(' '+yr):'');
}
function parnesCertUrlMulti(d,list){
  if(!list.length)return '';
  const date=parnesDateLabel(list);
  const dd=[...new Set(list.map(p=>(p.dedication||'').trim()).filter(Boolean))];
  const names=dd.join('\n')||((d&&d.prayers&&d.prayers[0]&&d.prayers[0].text)||'');
  return location.origin+'/parnes-cert?'+new URLSearchParams(
    {kind:list[0].kind||'parnes',date,names}).toString();
}
// אותה תעודה — כתמונה (PNG) לשליחה ישירה, בלי PDF
function parnesCertPng(d,p){
  const run=parnesRun(d,p);
  const dtext=(run.length>1)?parnesDateLabel(run)
    :((p.day&&p.month)?(heDay(+p.day)+" "+p.month):(p.date_text||''));
  const yr=(run.length>1)?'':(p.hyear||HEBYEAR);const date=dtext+(yr?(' '+yr):'');
  const names=(run.length>1)
    ? ([...new Set(run.map(x=>(x.dedication||'').trim()).filter(Boolean))].join('\n')
        ||((d&&d.prayers&&d.prayers[0]&&d.prayers[0].text)||''))
    : ((p.dedication&&p.dedication.trim())||(d&&d.prayers&&d.prayers[0]&&d.prayers[0].text)||'');
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
    <label class="fld"><span>💳 דרך מה ייגבה</span><select class="pymethod chansel" data-id="${p.id}">${channelOpts(p.method)}</select></label>
    <label class="fld" style="margin:4px 0"><span>🕯️ שמות ובקשות לתעודת הפרנס</span><textarea class="pyded" data-id="${p.id}" rows="2" placeholder="השמות שיוזכרו והבקשות (למשל: יעקב בן שרה לרפואה שלמה)">${esc(p.dedication||'')}</textarea></label>
    <button class="btn sm pydsave" data-id="${p.id}" style="margin:-2px 0 4px">💾 שמור שמות</button>
    <div class="txctl"><button class="dnpaid ${+p.paid?'yes':'no'} pypaid" data-id="${p.id}">${+p.paid?'נגבה ✓':'🔴 טרם נגבה'}</button><button class="btn sm ghost pycert" data-id="${p.id}">🖨️ תעודת פרנס</button><button class="btn sm ghost pypic" data-id="${p.id}">${p.photo==='sent'?'📷 תמונת הקדשה נשלחה ✓':'📷 סמן: תמונת הקדשה נשלחה'}</button>${p.photo==='sent'?'<span class="fbchip on">✓ נשלחה תמונת הקדשה</span>':''}</div><label class="remset">🔔 תזכורת: <input type="date" class="pyrem" data-txt="${esc(p.date_text)}"></label></div>`;}).join('')||'<div class="hintxt">אין עדיין.</div>');
  el.querySelectorAll('.pyded').forEach(t=>{autoGrow(t);t.addEventListener('input',()=>autoGrow(t));t.onblur=async()=>{const p=d.parnes.find(x=>x.id==t.dataset.id);if(!p||(p.dedication||'')===t.value)return;p.dedication=t.value;await api('PUT','/api/parnes/'+p.id,{dedication:t.value});toast('נשמר ✓');};});
  el.querySelectorAll('.pydsave').forEach(b=>b.onclick=async()=>{const p=d.parnes.find(x=>x.id==b.dataset.id);const t=el.querySelector('.pyded[data-id="'+b.dataset.id+'"]');if(!p||!t)return;p.dedication=t.value;await api('PUT','/api/parnes/'+p.id,{dedication:t.value});toast('נשמר ✓');});
  el.querySelectorAll('.pyamt').forEach(inp=>inp.onchange=async()=>{const p=d.parnes.find(x=>x.id==inp.dataset.id);if(!p)return;p.amount=inp.value.trim();await api('PUT','/api/parnes/'+p.id,{amount:p.amount});renderParnesEdit(d);toast('סכום עודכן ✓');});
  el.querySelectorAll('.pykind').forEach(sel=>sel.onchange=async()=>{const p=d.parnes.find(x=>x.id==sel.dataset.id);if(!p)return;p.kind=sel.value;await api('PUT','/api/parnes/'+p.id,{kind:p.kind});renderParnesEdit(d);toast('סוג עודכן ✓');});
  el.querySelectorAll('.pymethod').forEach(sel=>sel.onchange=async()=>{const p=d.parnes.find(x=>x.id==sel.dataset.id);if(!p||sel.value==='__new__')return;p.method=sel.value;await api('PUT','/api/parnes/'+p.id,{method:p.method});toast('אמצעי גבייה עודכן ✓');});
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
  ['weekly','קוויטל שבועי','מי שסומן שבועי בכרטיס'],
  ['occ','קוויטל מזדמן','לפי חודשים — נשמר לכל השנים'],
  ['klali','קוויטל כללי','הכל יחד להדפסה (בלי מזדמן ובלי "ללא")']
];
// הכללי מאגד את שלוש הדרגות האמיתיות בלבד
const KVREAL=['iz','101','weekly'];
const kvInType=(t,type)=>type==='klali'?KVREAL.includes(t):(t===type);
// מי נכנס לכל רשימה — חישוב אחד שגם התפריט וגם הרשימה עצמה נשענים עליו,
// כדי שהמספר שמאיר רואה בתפריט יהיה בדיוק מה שייפתח לו בפנים
function kvMembers(type){
  const seen=new Set();
  if(type==='occ'){ (DB||[]).forEach(d=>{if(isOccDonor(d))seen.add('d'+d.id);}); return seen; }
  (DB||[]).forEach(d=>{
    const prs=(d.prayers||[]);
    if(prs.length){ if(prs.some(p=>kvInType(prayerKvType(p.tier,d),type)))seen.add('d'+d.id); }
    else if(!(+d.kv_skip)){ const t=kvMemberType(d); if(t&&kvInType(t,type))seen.add('d'+d.id); }
  });
  (UNLINKED||[]).forEach(p=>{ if(kvInType(prayerKvType(p.tier,null),type))seen.add('l'+p.id); });
  return seen;
}
let kvSub=null;
function kvTypeLabel(t){return ({iz:'יש"ז','101':'כל לילה',weekly:'שבועי',occ:'מזדמן',klali:'כללי'})[t]||'כללי';}
// לאיזה קוויטל שייך התורם (לפי דרגה/קטגוריה) — למי שאמור להיות לו שם לתפילה
// מאיר: "אני עברתי על הכל וסידרתי מי שבוע ומי מזדמן" — מה שרשום בכרטיס
// הוא הקובע. אין ניחוש לפי סכומים, ומזדמן גובר על דרגת קוויטל ישנה
// שנשארה מהייבוא, כדי שהוא לא יופיע בקוויטל הכללי.
const isOccDonor=d=>String((d&&d.category)||'').trim()==='מזדמן';
// מאיר: "כל מי שיש לו קוויטל ללא הוא בתוך הכללי, את זה בוודאי צריך
// להוציא לגמרי מכל הקוויטלים". דרגה ריקה = "— ללא —" = מחוץ לכל הרשימות.
function kvMemberType(d){
  if(isOccDonor(d))return 'occ';
  if(d.tier==='יששכר_זבולון')return 'iz';
  if(d.tier==='קוויטל_101')return '101';
  if(d.tier==='קוויטל_שבועי'||d.tier==='קוויטל_כללי')return 'weekly';
  return null;
}
// הכלל הישן של "קבוע פחות מ-101" לא נמחק — הוא רק עבר למקום הנכון:
// הוא מקפיץ למעלה במסך "חסרים שמות קוויטל" את מי שכנראה מגיע לו קוויטל,
// במקום להכניס אותו לרשימת ההדפסה אחרי שמאיר סימן לו "ללא".
const kvSmallFixed=d=>!!(d&&d.category==='קבוע'&&amtNum(d.amount)>0&&amtNum(d.amount)<101);
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
    ${entries.map(e=>`<div class="kblock"><div class="who${e.did?' wholink':''}"${e.did?` data-did="${e.did}"`:''}>${esc(e.donor)} <span class="kvtag">${kvTypeLabel(e.kt)}</span>${e.did?' <span class="opencard">↗ כרטיס</span>':''}${e.loose?' <span class="loose">· לא משויך</span>':''}</div><div class="names hasflow" contenteditable="true" data-id="${e.id}">${esc(e.text)}</div><div class="namesflow">${esc(kvFlow(e.text))}</div></div>`).join('')||'<div class="empty">לא נמצאו שמות בקוויטל התואמים לחיפוש</div>'}`;
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
      <div class="kvmenu">${KVTYPES.map(([k,t,s])=>{const n=kvMembers(k).size;
        return `<button class="kvbtn" data-k="${k}"><b>${t}</b><span class="kvn">${n} ${n===1?'תורם':'תורמים'}</span><small>${s}</small></button>`;}).join('')}</div>`;
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
  // מסומני קוויטל קודם; אחריהם — לפי הכלל הישן — מי שנותן קבוע פחות
  // מ-101 ואין לו דרגה, כי כנראה מגיע לו קוויטל ורק לא נקבע לו עדיין
  const prio=d=>kvMemberType(d)?0:(kvSmallFixed(d)?1:2);
  list.sort((a,b)=>prio(a)-prio(b)||(a.last||'').localeCompare(b.last||'','he'));
  view.innerHTML=`<div class="kbar"><button class="back" id="kvback">→ סוגי קוויטל</button><b>🔴 תורמים בלי שם לקוויטל</b><span class="cnt2">(${list.length})</span></div>
    <div class="hintxt" style="margin:0 2px 8px">כל תורם שאין לו עדיין שם לתפילה. הקלד שם — או לחץ ✓ אם הוא לא ביקש קוויטל (יוסר מהרשימה). מסומני הקוויטל למעלה.</div>
    ${list.map(d=>{const yr=donorTotals(d).year,cs=curSym(d);return `<div class="kblock kvmiss" data-id="${d.id}"><div class="who wholink" data-did="${d.id}">${esc((d.last+' '+d.first).trim())} <span class="kvtag">${kvMemberType(d)?kvTypeLabel(kvMemberType(d)):(kvSmallFixed(d)?'ללא — קבוע '+curSym(d)+Math.round(amtNum(d.amount)):'אין קוויטל')}</span> <span class="kvyear ${yr>0?'':'zero'}">💵 השנה: ${cs}${yr}</span> <span class="opencard">↗ כרטיס</span></div>
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
// מה בדיוק נסרק ומה נדחה — כדי לדעת למה בקשה לא נכנסה
function intDiag(r){
  const box=document.getElementById('intdiag'); if(!box||!r)return;
  const sk=r.skipped||[];
  box.innerHTML=`<div class="hintxt" style="margin:0 2px 6px">🔎 נסרקו <b>${r.scanned||0}</b> מיילים
    (${esc(r.mailbox||'INBOX')} · מ־${esc(r.since||'')}${r.subject?(' · נושא "'+esc(r.subject)+'"'):''}${(r['from']||[]).length?(' · שולחים: '+esc((r['from']||[]).join(', '))):''})
    · נכנסו <b>${r.new||0}</b>${sk.length?(' · דילגתי על '+sk.length+' בלי שמות לתפילה'):''}</div>`
    +(sk.length?`<details class="dsec"><summary>מיילים שדילגתי עליהם (${sk.length})</summary>
      ${sk.map(x=>`<div class="miss2" dir="ltr">${esc(x.date||'')} · ${esc(x.from||'')} · ${esc(x.subject||'')}</div>`).join('')}</details>`:'');
}
function paintIntake(){
  const items=(INTAKE||[]).filter(x=>matchQ((x.names||'')+' '+(x.from_name||'')+' '+(x.from_email||'')+' '+(x.subject||'')));
  const nNew=(INTAKE||[]).filter(x=>x.status!=='handled').length;
  view.innerHTML=`<div class="kbar"><button class="back" id="kvback">→ סוגי קוויטל</button><b>📨 בקשות תפילה מהאתר</b><span class="cnt2">(${nNew} לטיפול)</span>
      <button class="btn sm" id="intSync">🔄 משוך מהמייל</button>
      <button class="btn sm ghost" id="intDiagBtn">🩺 בדיקה — מה יש בתיבה</button></div>
    ${INTAKE_CFG?'':`<div class="missbox">⚙️ חיבור המייל עדיין לא הוגדר בשרת. הגדר ב-Render את <b>GMAIL_USER</b> ו-<b>GMAIL_APP_PASSWORD</b> (וגם INTAKE_FROM לסינון לפי כתובת האתר). ראה הוראות.</div>`}
    <div class="hintxt" style="margin:2px 2px 8px">כל בקשה שהגיעה במייל מהאתר. ✅ = השמות כבר צורפו לקוויטל אצל התורם · 🔴 = עדיין לא. אפשר לערוך את השמות, לצרף לתורם, או לסמן שטופל.</div>
    <div id="intdiag"></div>
    <div id="intlist"></div>`;
  document.getElementById('kvback').onclick=()=>{kvSub=null;render();};
  document.getElementById('intSync').onclick=async()=>{
    const btn=document.getElementById('intSync');btn.disabled=true;btn.textContent='מושך…';
    const r=await api('POST','/api/intake/sync',{});
    if(!r.ok){toast(r.error==='not_configured'?'המייל לא מוגדר בשרת':'שגיאת משיכה: '+(r.detail||r.error||''));btn.disabled=false;btn.textContent='🔄 משוך מהמייל';return;}
    toast('נמשכו '+(r.new||0)+' בקשות'+(r.attached?' · '+r.attached+' צורפו אוטומטית לקוויטל לפי המייל':'')+' ✓');
    INTAKE=null;await loadIntake();paintIntake();intDiag(r);
  };
  const dgb=document.getElementById('intDiagBtn');
  if(dgb)dgb.onclick=async()=>{
    dgb.disabled=true; const o=dgb.textContent; dgb.textContent='בודק…';
    const r=await api('POST','/api/intake/diag',{});
    dgb.disabled=false; dgb.textContent=o;
    const box=document.getElementById('intdiag'); if(!box)return;
    if(!r||!r.ok){box.innerHTML='<div class="hintxt">שגיאה: '+esc((r&&(r.detail||r.error))||'')+'</div>';return;}
    box.innerHTML=`<div class="hintxt" style="margin:0 2px 6px">🩺 בתיבה <b>${esc(r.mailbox||'')}</b> מ־${esc(r.since||'')}:
      <b>${r.total||0}</b> מיילים. סינון פעיל: ${r.subject?('נושא "'+esc(r.subject)+'"'):'בלי נושא'} ·
      ${(r['from']||[]).length?('שולחים: '+esc((r['from']||[]).join(', '))):'בלי סינון שולח'}</div>
      ${(r.rows||[]).map(x=>`<div class="intdrow ${x.names?'ok':(x.subj_ok?'warn':'')}">
        <div dir="ltr" class="miss2">${esc(x.date||'')} · ${esc(x.from||'')}</div>
        <div dir="ltr"><b>${esc(x.subject||'(בלי נושא)')}</b></div>
        <div class="miss2">${x.from_ok?'✅ שולח':'⛔ שולח'} · ${x.subj_ok?'✅ נושא':'⛔ נושא'}${x.names!==undefined?(x.names?(' · ✅ שמות: '+esc(x.names)):' · 🔴 לא זוהו שמות'):''}</div>
        ${x.body?`<div class="miss2" dir="ltr" style="white-space:pre-wrap">${esc(x.body)}</div>`:''}
      </div>`).join('')||'<div class="hintxt">אין מיילים בתקופה הזו</div>'}`;
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
    toast(r.existing?('הכתובת כבר קיימת אצל '+(r.name||'')+' — צורף אליו ✓')
      :(r.from_recon?('נוצר כרטיס ל'+(r.name||'')+' — כולל כתובת מחיובי האשראי ✓'):('נוצר כרטיס ל'+(r.name||'תורם החדש')+' ✓')));
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
// שורת שם בקוויטל שומרת דרגה משלה מהייבוא. מה שרשום היום בכרטיס גובר
// עליה — אחרת תורם שמאיר העביר למזדמן ממשיך להופיע בכללי לפי דרגה ישנה.
function prayerKvType(pt,d){
  d=d||{};
  if(isOccDonor(d))return 'occ';
  if(d.tier)return kvMemberType(d)||'other';
  // לתורם מזוהה שאין לו דרגה — "ללא" — התווית הישנה על שורת השם אינה
  // מחזירה אותו פנימה. רק שם לא־משויך, שאין לו כרטיס להישען עליו,
  // נקבע לפי התווית שעליו.
  if(d.id)return 'other';
  if(pt==='יששכר_זבולון')return 'iz';
  if(pt==='קוויטל_101')return '101';
  if(pt==='שבועי'||pt==='קוויטל_שבועי'||pt==='קוויטל_כללי')return 'weekly';
  return 'other';
}
let kvListQ='';
/* ---------- הדפסה בלי שמות משפחה ----------
   מאיר: "אני לא רוצה שאנשים בכותל יראו מי התורמים שלנו" — בכללי ובמזדמן
   אפשר להדפיס עם שם פרטי בלבד. הבחירה נשמרת בין הכניסות. */
let KVNOLAST=false;
try{ KVNOLAST=localStorage.getItem('kc_kvnolast')==='1'; }catch(e){}
function kvSetNoLast(v){ KVNOLAST=!!v;
  try{ localStorage.setItem('kc_kvnolast', KVNOLAST?'1':'0'); }catch(e){} }
// השם כפי שהוא מוצג ומודפס. אצל תורם עם כרטיס לוקחים את השם הפרטי עצמו;
// אצל שם לא־משויך, שאין לו שדות נפרדים, מורידים את המילה הראשונה
// (שם המשפחה נכתב ראשון) ומשאירים את השאר.
function kvWho(g){
  const full=String(g.donor||'').trim();
  if(!KVNOLAST) return full;
  if(g.did){ const d=(DB||[]).find(x=>x.id===g.did);
    const f=String((d&&d.first)||'').trim();
    return f||full; }
  const ws=full.split(/\s+/);
  return ws.length>1 ? ws.slice(1).join(' ') : full;
}
function kvNoLastBtn(){
  return `<button class="btn sm ghost noprint" id="kvnolast">${
    KVNOLAST?'👁️ הצג שמות משפחה':'🙈 הדפסה בלי שמות משפחה'}</button>`;
}
function wireNoLast(redraw){
  const b=document.getElementById('kvnolast');
  if(b)b.onclick=()=>{ kvSetNoLast(!KVNOLAST); redraw(); };
}
function renderKvList(type){
  const title=KVTYPES.find(x=>x[0]===type)[1];
  view.innerHTML=`<div class="kbar"><button class="back" id="kvback">→ סוגי קוויטל</button><b>${title}</b><span class="cnt2" id="kvcnt"></span>${kvNoLastBtn()}<button class="print noprint" onclick="window.print()">הדפס 🖨️</button></div>
    <input class="avsearch noprint" id="kvsearch" placeholder="🔍 חפש שם תורם או שם שמוזכר בקוויטל…" value="${esc(kvListQ)}" autocomplete="off">
    <div class="hintxt noprint" style="margin:0 2px 8px">לתיקון: לחץ על השם, ערוך, ולחץ מחוץ לו — נשמר גם בכרטיס.${
      KVNOLAST?' <b>· מודפס בשם פרטי בלבד</b>':''}</div>
    <div class="hintxt noprint" id="kvout" style="margin:0 2px 8px"></div>
    <div id="kvlistwrap"></div>`;
  document.getElementById('kvback').onclick=()=>{kvListQ='';kvSub=null;render();};
  wireNoLast(()=>renderKvList(type));
  const si=document.getElementById('kvsearch');
  // הכללי מאגד את שלוש הדרגות האמיתיות בלבד. "מזדמן" ו"ללא" אינם דרגה
  // ואינם נכנסים אליו — מאיר: "כל מי שיש לו קוויטל ללא צריך לצאת לגמרי".
  const inType=t=>kvInType(t,type);
  function paint(){
    let entries=[]; let nOcc=0, nNone=0;
    DB.forEach(d=>{
      const prs=(d.prayers||[]);
      prs.forEach(p=>{const t=prayerKvType(p.tier,d);
        if(inType(t))entries.push({id:p.id,text:p.text,donor:(d.last+' '+d.first).trim(),last:d.last,did:d.id});
        else if(type==='klali'){ if(t==='occ')nOcc++; else nNone++; }});
      // מי שאין לו עדיין שם — נכנס לפי אותו כלל בדיוק
      if(!prs.length&&!(+d.kv_skip)){const t=kvMemberType(d);
        if(t&&inType(t))entries.push({id:null,newdid:d.id,text:'',donor:(d.last+' '+d.first).trim(),last:d.last,did:d.id,needname:true});}
    });
    UNLINKED.forEach(p=>{const t=prayerKvType(p.tier,null);
      if(inType(t))entries.push({id:p.id,text:p.text,donor:p.name||'—',last:(p.name||'').split(' ').slice(-1)[0],loose:true});});
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
    // מי לא נכנס ולמה — שלא ייעלם מישהו בשקט
    const outEl=document.getElementById('kvout');
    if(outEl)outEl.innerHTML=(type==='klali'&&(nOcc||nNone))
      ? 'לא נכללים כאן: '+[nOcc?(nOcc+' מזדמנים'):'',nNone?(nNone+' בדרגה "ללא"'):'']
          .filter(Boolean).join(' · ')+'. כדי לצרף מישהו — קבע לו דרגת קוויטל בכרטיס.'
      : '';
    document.getElementById('kvlistwrap').innerHTML=groups.map(g=>{
      const empty=!g.items.some(e=>(e.text||'').trim());
      const needname=g.items.some(e=>e.needname);
      return `<div class="kblock${empty?' kvempty':''}${g.items.length>1?' kvmulti':''}"><div class="who${g.did?' wholink':''}"${g.did?` data-did="${g.did}"`:''}>${esc(kvWho(g))}${g.did?' <span class="opencard">↗ כרטיס</span>':''}${needname?' <span class="kvtag">אין שם — הקלד כאן</span>':''}${g.loose?' <span class="loose">· לא משויך</span>':''}</div>`
        + g.items.map(e=>`<div class="names hasflow" contenteditable="true" ${e.id?`data-id="${e.id}"`:`data-newdid="${e.newdid}"`}>${esc(e.text)}</div>`
            + `<div class="namesflow">${esc(kvFlow(e.text))}</div>`).join('')
        + `</div>`;}).join('')||'<div class="empty">אין תוצאות</div>';
    view.querySelectorAll('.who[data-did]').forEach(w=>w.onclick=()=>openDonor(DB.find(x=>x.id==w.dataset.did),'kvittel'));
    bindKvEdit();
  }
  si.oninput=()=>{kvListQ=si.value;paint();};
  paint();
}
// מאיר: "כל שם ושם האם והבקשה ואז פסיק, והשם הבא באותה שורה — לא
// שיתפוס מקום". שורות בודדות מתחברות לרצף אחד, להדפסה בלבד.
function kvFlow(t){
  const parts=String(t||'').split(/\r?\n/).map(x=>x.trim()).filter(Boolean);
  if(parts.length<2)return parts.join('');
  let out=parts[0];
  for(let i=1;i<parts.length;i++) out += (/[,.:;·|]$/.test(out)?' ':', ') + parts[i];
  return out;
}
let KVOCCMON='';        // חודש יחיד להדפסה במזדמנים; ריק = הכל
function renderKvOcc(){
  const groups={},mdate={};
  const place=(d,hm,dt)=>{groups[hm]=groups[hm]||{};const pid=(d.prayers&&d.prayers[0])?d.prayers[0].id:null;groups[hm][d.id]={d,pid,text:(d.prayers&&d.prayers[0])?d.prayers[0].text:''};if(!mdate[hm]||(dt||'')>mdate[hm])mdate[hm]=dt||'';};
  // כל מי שרשום מזדמן — גם אם נשארה עליו דרגת קוויטל ישנה מהייבוא,
  // אחרת הוא נופל בין הכיסאות ולא מופיע באף רשימה
  DB.forEach(d=>{if(!isOccDonor(d))return;
    if(d.kv_month){const lastdt=(d.donations||[]).reduce((a,x)=>((x.date||'')>a?(x.date||''):a),'');place(d,d.kv_month+(d.kv_year?(' '+d.kv_year):''),lastdt);return;}  // חודש/שנה שנקבעו ידנית
    const dons=(d.donations||[]);
    if(!dons.length){place(d,'ללא תאריך','');return;}
    dons.forEach(dn=>place(d,dn.hmonth||'ללא תאריך',dn.date||''));});
  let months=Object.keys(groups).sort((a,b)=>(mdate[b]||'').localeCompare(mdate[a]||''));
  months=months.filter(hm=>matchQ(hm)||Object.values(groups[hm]).some(x=>matchQ(x.d.last+' '+x.d.first+' '+x.text)));
  // מאיר: "אני רוצה להדפיס במזדמנים רק את אלול וזה בוחר לי הכל" — בחירת
  // חודש אחד, ואז גם המסך וגם ההדפסה מכילים רק אותו
  const allMonths=months.slice();
  if(KVOCCMON && allMonths.indexOf(KVOCCMON)<0) KVOCCMON='';
  if(KVOCCMON) months=months.filter(hm=>hm===KVOCCMON);
  const nSel=months.reduce((a,hm)=>a+Object.keys(groups[hm]).length,0);
  view.innerHTML=`<div class="kbar"><button class="back" id="kvback">→ סוגי קוויטל</button><b>קוויטל מזדמן — לפי חודשים</b>${kvNoLastBtn()}<button class="print" onclick="window.print()">הדפס 🖨️</button></div>
    <div class="kvmonbar noprint"><label>🗓️ להדפיס</label>
      <select id="kvoccmon">
        <option value="">כל החודשים (${allMonths.reduce((a,hm)=>a+Object.keys(groups[hm]).length,0)})</option>
        ${allMonths.map(hm=>`<option value="${esc(hm)}"${hm===KVOCCMON?' selected':''}>${esc(hm)} (${Object.keys(groups[hm]).length})</option>`).join('')}
      </select>
      <span class="kvmoncnt">${nSel} תורמים בהדפסה</span></div>
    ${KVNOLAST?'<div class="hintxt noprint" style="margin:0 2px 8px"><b>מודפס בשם פרטי בלבד</b></div>':''}
    ${months.map(hm=>{const list=Object.values(groups[hm]);return `<div class="kvmonth"><h3>🗓️ ${esc(hm)} <small>(${list.length})</small></h3>${list.map(x=>`<div class="kblock"><div class="who wholink" data-did="${x.d.id}">${esc(kvWho({did:x.d.id,donor:(x.d.last+' '+x.d.first).trim()}))} <span class="opencard">↗ כרטיס</span></div>${x.pid?`<div class="names hasflow" contenteditable="true" data-id="${x.pid}">${esc(x.text)}</div><div class="namesflow">${esc(kvFlow(x.text))}</div>`:'<div class="hintxt">אין שם לתפילה — הוסף בכרטיס התורם</div>'}</div>`).join('')}</div>`;}).join('')||'<div class="empty">אין תרומות מזדמנות</div>'}`;
  document.getElementById('kvback').onclick=()=>{kvSub=null;KVOCCMON='';render();};
  wireNoLast(renderKvOcc);
  const ms=document.getElementById('kvoccmon');
  if(ms)ms.onchange=()=>{KVOCCMON=ms.value;renderKvOcc();};
  view.querySelectorAll('.who[data-did]').forEach(w=>w.onclick=()=>openDonor(DB.find(x=>x.id==w.dataset.did),'kvittel'));
  bindKvEdit();
}

/* ---------- פרנס יום + שלט ---------- */
let pyKind='parnes';
function savePy(){try{localStorage.setItem('kc_py',JSON.stringify({kind:pyKind,month:pyMonth,day:pyDay}));}catch(e){}}
const PKINDS=[['parnes','🌙 פרנס לילה'],['coffee','☕ חדר קפה'],['breakfast','🍳 ארוחת בוקר']];
// לילה אחד יכול להיות מוחזק בידי כמה תורמים — לכל תאריך נשמרת רשימה
function parnesTaken(kind){const taken={};DB.forEach(d=>(d.parnes||[]).forEach(p=>{
  if((p.kind||'parnes')!==kind)return; if(!(p.month&&p.day))return;
  const k=p.month+'|'+p.day; (taken[k]=taken[k]||[]).push({...p,donor:(d.last+' '+d.first).trim(),dref:d});}));
  return taken;}
// המחזיק ה'ראשי' של הלילה לצביעת המשבצת: מאושר גובר על הצעה
function pyMain(l){return (l||[]).find(x=>x.status!=='suggested')||(l||[])[0]||null;}
function kindToggle(){return `<div class="ktoggle">${PKINDS.map(([k,l])=>`<button class="ktog ${pyKind===k?'on':''}" data-k="${k}">${l}</button>`).join('')}</div>`;}
function bindKindToggle(){view.querySelectorAll('.ktog').forEach(b=>b.onclick=()=>{pyKind=b.dataset.k;pyDay=null;render();});}
function renderParnes(){
  chips.innerHTML='';
  savePy();   // שמירת המקום (חודש/יום) לשחזור אחרי רענון
  const taken=parnesTaken(pyKind);
  if(!pyMonth){
    view.innerHTML=kindToggle()+pyPickBar()+`<div class="cnt">בחר חודש לראות ולשבץ את 30 הימים</div>
      <div class="hmgrid">${HMORD.map(m=>{const cnt=Object.keys(taken).filter(k=>k.startsWith(m+'|')).length;return `<button class="hmbtn" data-m="${m}"><span>${m}</span>${cnt?`<span class="hmc">${cnt}</span>`:''}</button>`;}).join('')}</div>`;
    bindKindToggle(); wirePyPick();
    view.querySelectorAll('.hmbtn').forEach(b=>b.onclick=()=>{pyMonth=b.dataset.m;pyDay=null;render();});
    return;
  }
  const days=[];for(let i=1;i<=30;i++)days.push(i);
  view.innerHTML=kindToggle()+pyPickBar()+`<div class="pbar"><button class="back" id="pmback">→ כל החודשים</button>
      <div class="monthnav"><button class="mnav" id="pmprev">${esc(hMonHop(-1))}</button>
        <b>חודש ${pyMonth}</b>
        <button class="mnav" id="pmnext">${esc(hMonHop(1))}</button></div></div>
    <div class="hintxt swipehint">👉 החלק באצבע על הלוח כדי להחליף חודש · או לחץ על שם החודש שאתה רוצה</div>
    <div class="dlegend"><span class="lg full"></span>מאושר <span class="lg sugg"></span>הצעה <span class="lg free"></span>פנוי</div>
    <div class="daygrid">${days.map(n=>{const l=taken[pyMonth+'|'+n]||[];const t=pyMain(l);const cls=t?(t.status==='suggested'?'sugg':'full'):'free';const unpaid=l.some(x=>x.status!=='suggested'&&!+x.paid);return `<button class="daycell ${cls} ${unpaid?'unpaid':''} ${l.length>1?'multi':''} ${pyDay===n?'sel':''}" data-d="${n}"><span class="dn">${heDay(n)}</span>${t?`<span class="dnm">${l.map(x=>esc(x.donor.split(' ')[0])).join('<br>')}</span>${unpaid?'<span class="unpaiddot">🔴</span>':''}`:'<span class="dplus">+</span>'}</button>`;}).join('')}</div>
    <div id="daypanel"></div>`;
  bindKindToggle(); wirePyPick();
  document.getElementById('pmback').onclick=()=>{pyMonth=null;pyDay=null;render();};
  view.querySelectorAll('.daycell').forEach(b=>b.onclick=()=>{pyDay=+b.dataset.d;render();});
  document.getElementById('pmprev').onclick=()=>pyHop(-1);
  document.getElementById('pmnext').onclick=()=>pyHop(1);
  swipeMonth(view.querySelector('.daygrid'));
  if(pyDay)renderDayPanel(taken);
}
// מעבר חודש: החלקה באצבע שמאלה = החודש הבא, ימינה = החודש הקודם.
// אחרי אלול חוזרים לתשרי, ולפני תשרי — אלול.
function hMonHop(step){
  const i=HMORD.indexOf(pyMonth);
  return i<0?'':HMORD[(i+step+HMORD.length)%HMORD.length];
}
function pyHop(step){
  const i=HMORD.indexOf(pyMonth); if(i<0)return;
  pyMonth=HMORD[(i+step+HMORD.length)%HMORD.length]; pyDay=null; render();
}
function swipeMonth(el){
  if(!el)return;
  let x0=null,y0=null,t0=0;
  el.addEventListener('touchstart',e=>{const t=e.touches[0];x0=t.clientX;y0=t.clientY;t0=Date.now();},{passive:true});
  el.addEventListener('touchend',e=>{
    if(x0===null)return;
    const t=e.changedTouches[0], dx=t.clientX-x0, dy=t.clientY-y0;
    x0=null;
    if(Date.now()-t0>700)return;              // גרירה איטית — כנראה גלילה
    if(Math.abs(dx)<55||Math.abs(dx)<Math.abs(dy)*1.6)return;   // תנועה אנכית — גלילה
    pyHop(dx<0?-1:1);                          // שמאלה = הבא (הגלילה זזה עם האצבע)
  },{passive:true});
}
function renderDayPanel(taken){
  const panel=document.getElementById('daypanel');if(!panel)return;
  const list=taken[pyMonth+'|'+pyDay]||[], dtext=heDay(pyDay)+" "+pyMonth;
  const kindL=PKINDS.find(k=>k[0]===pyKind)[1];
  // כל מחזיק של הלילה מקבל בלוק משלו, ומתחתם תמיד אפשר לצרף עוד תורם
  panel.innerHTML=list.map(t=>pySlotHTML(t,dtext)).join('')
    +`<div class="sec"><h3>➕ ${list.length?'הוסף עוד תורם לאותו לילה':('שבץ '+kindL)} — ${esc(dtext)}</h3>
      ${list.length?`<div class="hintxt">${list.length===1?'תורם אחד כבר משובץ':(list.length+' תורמים כבר משובצים')} ללילה הזה. אפשר לצרף עוד — לכל אחד הקדשה וסכום משלו.</div>`:''}
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
        <button class="btn" id="dp_save">${list.length?'צרף ללילה זה':'שבץ ללילה זה'}</button></div></div>`;
  list.forEach(t=>pyWireSlot(t,dtext,taken));
  // תרומה שממתינה לשיבוץ — התורם והסכום כבר ידועים, אין מה לחפש שוב
  if(PYPICK){
    const mine=list.find(x=>x.donor_id===PYPICK.donor_id);
    const box=document.createElement('div');
    box.className='sec pypickbox';
    box.innerHTML=mine
      ? `<h3>🎯 ${esc(PYPICK.name)} כבר משובץ ללילה הזה</h3>
         <div class="hintxt">${+mine.paid?'הלילה כבר מסומן כנגבה — אפשר רק לרשום את הייעוד על התרומה.':'נסמן אותו כנגבה ונרשום את הייעוד על התרומה.'}</div>
         <button class="btn" id="pyp_mark">✓ ${PYPICK.cur}${esc(PYPICK.amount)} — נגבה על הלילה הזה</button>`
      : `<h3>🎯 לשבץ את ${esc(PYPICK.name)} ל־${esc(dtext)}</h3>
         <div class="hintxt">${list.length?('הלילה כבר מוחזק בידי '+list.map(x=>esc(x.donor)).join(', ')+' — אפשר לצרף אותו כשותף.'):'הלילה פנוי.'}</div>
         <label class="fld"><span>בקשה ללימוד הלילה / הקדשה (רשות)</span><textarea id="pyp_ded" rows="2">${esc(PYPICK.ded||'')}</textarea></label>
         <button class="btn" id="pyp_take">🌙 שבץ ${PYPICK.cur}${esc(PYPICK.amount)} ללילה הזה</button>`;
    panel.prepend(box);
    const mk=document.getElementById('pyp_mark');
    if(mk)mk.onclick=async()=>{mk.disabled=true;await pyPickDone(mine.id);};
    const tk=document.getElementById('pyp_take');
    if(tk)tk.onclick=async()=>{
      tk.disabled=true;
      const ded=(document.getElementById('pyp_ded')||{value:''}).value.trim();
      const r=await api('POST','/api/parnes',{donor_id:PYPICK.donor_id,day:pyDay,month:pyMonth,
        date_text:dtext,dedication:ded,amount:PYPICK.amount,kind:pyKind,status:'confirmed',
        currency:PYPICK.cur,hyear:HEBYEAR});
      if(!r||!r.id){tk.disabled=false;toast('לא שובץ');return;}
      await pyPickDone(r.id);};
  }
  const qi=document.getElementById('dp_q'),res=document.getElementById('dp_res');let chosen=null;
  const pickChosen=nd=>{chosen=nd;
    const ch=document.getElementById('dp_chosen'), fm=document.getElementById('dp_form');
    if(!ch||!fm)return;                     // הלוח כבר נבנה מחדש — אין למי לכתוב
    ch.textContent='נבחר: '+(nd.last+' '+(nd.first||'')).trim();
    fm.style.display='block'; if(res)res.innerHTML='';
    if(qi)qi.value=(nd.last+' '+(nd.first||'')).trim();};
  document.getElementById('dp_new').onclick=()=>openNewDonor(nd=>pickChosen(nd));
  qi.oninput=()=>{const s=norm(qi.value);if(!s){res.innerHTML='';return;}const m=DB.filter(d=>norm(d.last+' '+d.first+' '+d.english).includes(s)).slice(0,8);
    res.innerHTML=m.map(d=>`<div class="dpr" data-id="${d.id}">${esc(d.last)} ${esc(d.first)} ${d.tier==='יששכר_זבולון'?'· יש"ז':''}</div>`).join('');
    res.querySelectorAll('.dpr').forEach(x=>x.onclick=()=>pickChosen(DB.find(y=>y.id==x.dataset.id)));};
  document.getElementById('dp_open').onclick=()=>{if(chosen)openDonor(chosen);};
  document.getElementById('dp_kv').onclick=()=>{if(chosen)openDonor(chosen,'kvittel');};
  document.getElementById('dp_save').onclick=async ev=>{
    const btn=ev.currentTarget; if(btn.disabled)return;
    if(!chosen){toast('בחר תורם');return;}
    if(list.some(x=>x.donor_id===chosen.id)){toast('התורם כבר משובץ ללילה הזה');return;}
    btn.disabled=true;
    const ded=document.getElementById('dp_ded').value.trim(),amt=document.getElementById('dp_amt').value.trim(),status=document.getElementById('dp_status').value;
    const r=await api('POST','/api/parnes',{donor_id:chosen.id,day:pyDay,month:pyMonth,date_text:dtext,dedication:ded,amount:amt,kind:pyKind,status,currency:curSym(chosen)});
    if(r.existing){toast('היום הזה כבר משובץ לתורם הזה');render();return;}
    chosen.parnes=chosen.parnes||[];chosen.parnes.push({id:r.id,donor_id:chosen.id,day:pyDay,month:pyMonth,date_text:dtext,dedication:ded,amount:amt,kind:pyKind,status});
    if(r.suggestions&&r.suggestions.length)chosen.parnes.push(...r.suggestions);
    toast('שובץ ✓'+(r.suggestions&&r.suggestions.length?' + '+r.suggestions.length+' הצעות לשנים הבאות':''));render();};
}
// בלוק של מחזיק אחד בלילה. המזהים ייחודיים לפי מספר הרשומה, כדי שכמה
// מחזיקים באותו לילה לא ידרסו זה את שדותיו של זה.
function pySlotHTML(t,dtext){
  const sugg=t.status==='suggested', paid=+t.paid, amt=t.amount||'', k=t.id;
  const dpcur=pCur(t,DB.find(x=>x.id==t.donor_id));
  return `<div class="sec pyslot" data-pid="${k}"><h3>${sugg?'🔵 הצעה':(paid?'🟢 נגבה':'🔴 חוב — טרם נגבה')} · ${esc(dtext)}</h3>
    <div class="remitem ${sugg?'':(paid?'given':'')}"><div class="ri"><b>${esc(t.donor)}</b>${amt?(' · <b style="color:'+(paid?'var(--yes)':'var(--no)')+'">'+dpcur+esc(amt)+'</b>'):''}${t.method?(' · '+esc(chLabel(t.method))):''}</div></div>
    <div class="fld" style="margin:6px 0"><span>💰 סכום — מלא ידני לכל פרנס</span>
      <div class="two" style="gap:6px;margin-top:3px"><input class="dp_amt_edit" value="${esc(amt)}" inputmode="decimal" placeholder="כמה תרם">
        <select class="dp_cur_edit" style="max-width:110px"><option value="$" ${dpcur==='$'?'selected':''}>$ דולר</option><option value="₪" ${dpcur==='₪'?'selected':''}>₪ שקל</option></select></div>
      <button class="btn sm dp_amt_save" style="margin-top:6px;width:100%">💾 שמור סכום</button></div>
    <label class="fld" style="margin:6px 0"><span>💳 איך נגבה (אמצעי תשלום)</span><select class="dp_method chansel">${channelOpts(t.method)}</select></label>
    ${sugg?'':`<button class="dnpaid ${+paid===1?'yes':'no'} dppaid" style="margin:2px 0 8px;width:100%">${+paid===1?'✓ נגבה — לחץ לביטול':'🔴 חוב — סמן שנגבה'}</button>
      <button class="dnpaid setl dpsetl ${+paid===2?'on':''}" style="margin:0 0 8px;width:100%">${+paid===2?'✓ סודר — לחץ לביטול':'סודר — הכסף הגיע בתרומה נפרדת'}</button>`}
    ${sugg?'<div class="hintxt">הצעה — פנה אליו האם לעשות לו גם השנה. אם הסכים, אשר.</div>':''}
    <label class="fld" style="margin:6px 0"><span>🕯️ שמות ובקשות לתעודה</span><textarea class="dp_ded_edit" rows="2" placeholder="השמות שיוזכרו והבקשות">${esc(t.dedication||'')}</textarea></label>
    <button class="btn sm dp_ded_save" style="margin-bottom:6px">💾 שמור שמות</button>
    <div class="movebox">🔀 העבר ליום אחר:
      <select class="dpmvmon">${HMORD.map(m=>`<option ${m===pyMonth?'selected':''}>${m}</option>`).join('')}</select>
      <select class="dpmvday">${[...Array(30)].map((_,i)=>`<option value="${i+1}" ${(i+1)===pyDay?'selected':''}>${heDay(i+1)}</option>`).join('')}</select>
      <button class="btn sm dpmove">העבר</button></div>
    <div class="avfiles">${(t.files||[]).map(fileChip).join('')}<label class="filebtn">📷 העלה תמונת הקדשה<input type="file" accept="image/*,application/pdf" class="pyupload" hidden></label></div>
    <div class="addrow">${sugg?'<button class="btn sm dpconfirm" style="background:var(--yes)">✅ אישר — עבור למאושר</button>':''}<button class="btn sm dpsend" style="background:#25D366;border-color:#25D366">📤 שלח לתורם</button><button class="btn sm dpopen">📋 כרטיס</button><button class="btn sm ghost dpkv">🕯️ קוויטל</button><button class="btn sm dpprint">🖨️ תעודה</button><button class="del dpdel">מחק</button></div></div>`;
}
function pyWireSlot(t,dtext,taken){
  const box=document.querySelector('.pyslot[data-pid="'+t.id+'"]'); if(!box)return;
  const q=c=>box.querySelector('.'+c);
  const rec=()=>(t.dref&&t.dref.parnes||[]).find(x=>x.id==t.id);
  const methSel=q('dp_method');
  wireChanSel(methSel);            // "➕ דרך תשלום חדשה" — שדה להקלדת השם
  // "__new__" הוא סימן לפתוח שדה, לא אמצעי תשלום. אסור לשמור אותו.
  const mVal=()=>{const v=methSel?methSel.value:t.method;return v==='__new__'?(t.method||''):v;};
  const setPMeth=v=>{if(v==='__new__')return;t.method=v;const p=rec();if(p)p.method=v;};
  const amtSave=async()=>{const damt=q('dp_amt_edit'),dcur=q('dp_cur_edit');t.amount=damt.value.trim();t.currency=dcur.value;
    const mv=mVal();setPMeth(mv);const p=rec();if(p){p.amount=t.amount;p.currency=t.currency;}
    await api('PUT','/api/parnes/'+t.id,{amount:t.amount,currency:t.currency,method:mv});toast('נשמר ✓');render();};
  const ab=q('dp_amt_save'); if(ab)ab.onclick=amtSave;
  if(methSel)methSel.addEventListener('change',async()=>{
    if(methSel.value==='__new__')return;        // רק פותח את שדה ההקלדה
    setPMeth(methSel.value);
    await api('PUT','/api/parnes/'+t.id,{method:methSel.value});toast('אמצעי נשמר ✓');});
  const pb=q('dppaid');
  if(pb)pb.onclick=async()=>{const np=+t.paid===1?0:1;t.paid=np;const mv=mVal();setPMeth(mv);
    const p=rec();if(p)p.paid=np;await api('PUT','/api/parnes/'+t.id,{paid:np,method:mv});
    toast(np?'סומן כנגבה ✓':'סומן כחוב שטרם נגבה');render();};
  const ps=q('dpsetl');
  if(ps)ps.onclick=async()=>{const np=+t.paid===2?0:2;t.paid=np;
    const p=rec();if(p)p.paid=np;await api('PUT','/api/parnes/'+t.id,{paid:np});
    toast(np===2?'סומן כסודר ✓ — לא ייספר כחוב':'הסימון בוטל');render();};
  const dded=q('dp_ded_edit');
  const ddedSave=async()=>{t.dedication=dded.value;const p=rec();if(p)p.dedication=dded.value;
    await api('PUT','/api/parnes/'+t.id,{dedication:dded.value});toast('נשמר ✓');};
  dded.onblur=()=>{if((t.dedication||'')!==dded.value)ddedSave();};
  q('dp_ded_save').onclick=ddedSave;
  q('dpmove').onclick=async()=>{
    const nm=q('dpmvmon').value, nd=+q('dpmvday').value;
    if(nm===pyMonth && nd===pyDay){toast('בחר יום אחר');return;}
    const ndtext=heDay(nd)+' '+nm, p=rec();
    await api('PUT','/api/parnes/'+t.id,{day:nd,month:nm,date_text:ndtext,hyear:t.hyear||(p&&p.hyear)||''});
    if(p){p.day=nd;p.month=nm;p.date_text=ndtext;}
    pyMonth=nm;pyDay=nd;toast('הועבר ל־'+ndtext+' ✓');render();};
  const cf=q('dpconfirm');
  if(cf)cf.onclick=async()=>{await api('PUT','/api/parnes/'+t.id,{status:'confirmed'});const p=rec();if(p)p.status='confirmed';toast('אושר ✓ עבר למאושר');render();};
  box.querySelector('.pyupload').onchange=e=>uploadFile('parnes',t.id,e.target,load);
  box.querySelectorAll('.fdel').forEach(b=>b.onclick=async()=>{await api('DELETE','/api/file/'+b.dataset.fid);load();});
  q('dpopen').onclick=()=>openDonor(t.dref);
  q('dpkv').onclick=()=>openDonor(t.dref,'kvittel');
  q('dpprint').onclick=()=>openParnesCert(t.dref,{...t,date_text:t.date_text||dtext});
  const sb=q('dpsend'); if(sb)sb.onclick=()=>shareParnesMenu({...t,date_text:t.date_text||dtext},t.dref);
  q('dpdel').onclick=async()=>{await api('DELETE','/api/parnes/'+t.id);
    t.dref.parnes=(t.dref.parnes||[]).filter(x=>x.id!=t.id);
    const note='פרנס יום '+(t.date_text||dtext)+' — הכן הדפסה וצור קשר';
    t.dref.tasks=(t.dref.tasks||[]).filter(x=>!(x.kind==='parnes'&&x.note===note));
    checkReminders();render();toast('נמחק');};
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
  if(String(d&&d.debt_ok||'').trim())return [];   // סודר עם התורם — לא חוב פתוח
  const out=[];
  (d.pledges||[]).forEach(p=>{ if(p.status==='נתן'||+p.monthly)return;   // חודשית = שוטפת, לא חוב
    out.push({what:(p.category||'התחייבות'),amt:amtNum(p.amount),kind:'pledge',id:p.id,when:''}); });
  (d.parnes||[]).forEach(p=>{ if(p.status==='suggested'||+p.paid)return;
    out.push({what:(PKLBL[p.kind]||'🌙 פרנס יום'),amt:amtNum(p.amount),kind:'parnes',id:p.id,
              when:[p.date_text,p.hyear].filter(Boolean).join(' ')}); });
  // תרומה *לא* נחשבת חוב. שורת תרומה היא רישום של כסף, לא התחייבות —
  // ולכן כסף שנכנס הופיע כאן כאילו התורם חייב אותו. חוב הוא רק מה
  // שהתורם התחייב ועדיין לא נתן.
  // תורם קבוע שלא נגבה ממנו חודשים — בדיוק כמו בחלון החוב שבכרטיס,
  // ובלי לספור פעמיים כשהחוב של יששכר־זבולון כבר מכסה את אותם חודשים
  try{
    const iz0=izSummary(d), gc=gaps(d.months,d), fx=amtNum(fixedAmt(d));
    const izCov=iz0.monthly>0&&iz0.monthly>=fx-0.5&&
      ((iz0.manual!=null&&iz0.manual<=0.5)||(iz0.thru.length&&iz0.thruDebt<=0.5));
    if(gc.length&&fx>0&&!izCov){
      // אצל תורם יששכר־זבולון החישוב מדויק רק כשמוגדר "שולם עד חודש"
      // לכל אברך. בלי זה נשענים על החודשים שסומנו בכרטיס, וזה עלול
      // להחמיץ חודשים ישנים — ולכן אומרים את זה במפורש.
      const nothru=iz0.parts.length&&!iz0.thru.length&&iz0.manual==null;
      out.push({what:'📅 חודשים שלא נגבו'+(iz0.parts.length?(' · '+iz0.parts.length+' אברכים'):''),
                amt:gc.length*fx,kind:'months',id:0,
                when:gc.map(i=>MON[i]).join(' · ')
                  +(nothru?' — לא הוגדר "שולם עד חודש" לאברכים, החישוב לפי החודשים שסומנו בכרטיס':'')});
    }
  }catch(e){}
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
    <div class="hintxt" style="margin:0 2px 8px">חוב = מה שהתורם התחייב ועדיין לא נתן. נכנס לכאן: 🤝 יששכר־זבולון שלא שולם (לפי "שולם עד חודש" או עדכון ידני) · 🎯 התחייבות/קמפיין שטרם ניתן · 🌙 פרנס יום שנתפס ולא נגבה · 🏛️ יתרה בבניין.<br>תרומות שנכנסו בפועל אינן חוב ואינן נספרות כאן.</div>
    <div class="list">${rows.map((r,i)=>`<div class="rowc debtrow"><div class="rowmain" data-did="${r.d.id}">
      <div class="nm">${esc(r.d.last)} <small>${esc(r.d.first)}</small></div>
      ${r.list.map((x,j)=>`<div class="miss"><span class="dbw">${esc(x.what)}</span>${x.when?(' <small>'+esc(x.when)+'</small>'):''}
        — <b style="color:var(--no)">${x.amt?f(x.amt):'ללא סכום'}</b>${(x.kind!=='iz'&&x.kind!=='months')?`<button class="btn sm dbpaid" data-i="${i}" data-j="${j}" onclick="event.stopPropagation()">✓ נגבה</button>`:''}</div>`).join('')}
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
  const missed=q1.filter(d=>gaps(d.months,d).length>0).sort((a,b)=>gaps(b.months,b).length-gaps(a.months,a).length);
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
    <div class="submuted">רק תורמים קבועים נבדקים כאן — מי שמסומן "קבוע", מי שיש לו התחייבות חודשית,
      או מי ששילם שלושה חודשים רצופים. מזדמן שתרם פעם אחת לא נספר כמפספס.<br>
      לחץ על חודש כדי לסמן שנגבה · "הסר שורה" מסמן שטופל</div>
    <div class="list">${missed.map(d=>{const g=gaps(d.months,d);return `<div class="rowc"><div class="rowmain" data-id="${d.id}"><div class="nm">${esc(d.last)} <small>${esc(d.first)}</small></div><div class="miss">לא עבר: ${g.map(i=>`<span class="gchip" data-id="${d.id}" data-m="${i}">${MON[i]} ✓</span>`).join(' ')}</div></div><div class="meta"><button class="btn sm ghost missdismiss" data-id="${d.id}">הסר שורה</button>${monthGrid(d.months,d)}</div></div>`;}).join('')||'<div class="hintxt">אין פספוסים 🎉</div>'}</div>`;
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
  view.querySelectorAll('.missdismiss').forEach(b=>b.onclick=async e=>{e.stopPropagation();const d=DB.find(x=>x.id==b.dataset.id);const prev=d.months;let nm=d.months;gaps(nm,d).forEach(i=>nm=setMonthChar(nm,i,'h'));d.months=nm;await api('PUT','/api/donor/'+d.id,{months:nm});
    toastUndo('הוסר ✓',async()=>{d.months=prev;await api('PUT','/api/donor/'+d.id,{months:prev});renderMissed();});renderMissed();});
}

/* ---------- אברכים (יששכר־זבולון) ---------- */
let avView='cards', avSort='last', avSearch='', AVSTAT=null;
function avFirstAvreich(d){return ((d.partners||[]).filter(p=>p.active!=0)[0]||{}).avreich||'';}
function avSumAmt(d){return (d.partners||[]).filter(p=>p.active!=0).reduce((s,p)=>s+amtNum(p.amount),0);}
function sortIZ(list){const s=list.slice();
  if(avSort==='av') s.sort((a,b)=>(avFirstAvreich(a)||'תתת').localeCompare(avFirstAvreich(b)||'תתת','he'));
  else if(avSort==='amt') s.sort((a,b)=>avSumAmt(b)-avSumAmt(a));
  else s.sort((a,b)=>(a.last||'').localeCompare(b.last||'','he'));
  return s;}
function filterIZ(){const nq=norm(avSearch);
  // גם אברך שמוחזק בשותפות ורשום אצל השותף נכנס לחיפוש — אחרת תורם
  // שכל האברכים שלו משותפים לא היה נמצא לפי שם האברך
  const txt=d=>d.last+' '+d.first+' '+(d.partners||[]).map(p=>p.avreich).join(' ')
    +' '+izLinkedRows(d).map(x=>x.avreich).join(' ');
  // גם מי שלא סומן בדרגה אבל מחזיק אברך בשותפות עם תורם אחר — אחרת
  // השותף היה נעלם מהרשימה למרות שהוא מחזיק
  return sortIZ(DB.filter(d=>d.tier==='יששכר_זבולון'||izLinkedRows(d).length)
    .filter(d=>matchQ(txt(d)))
    .filter(d=>!nq||norm(txt(d)).includes(nq)));}
// רשימת האברכים של הכולל לפי שם משפחה — מי מחזיק כל אחד, ממתי ובכמה.
// מכאן אפשר לשבץ שותף לאברך פנוי, ולראות מיד למי עוד אין.
let avOpenId=null, avSwapId=null, avHistId=null, avInfoId=null, izHist=false;
// חיפוש אברך לפי שם משפחה, שם פרטי, או שם השותף — בכל סדר ובאיות קרוב
function avFiltered(){
  const s2=avSearch.trim(); if(!s2)return AVLIST;
  return AVLIST.filter(a=>matchStr(a.name+' '+(a.note||'')+' '+(a.holders||[]).map(h=>h.name).join(' '),s2));
}
async function renderAvByAv(){
  chips.innerHTML='';
  view.innerHTML='<div class="cnt">טוען את רשימת האברכים…</div>';
  await loadAvList();
  const st=AVSTAT||{total:AVLIST.length,free:AVLIST.filter(a=>!a.holders.length).length};
  const q2=avSearch.trim();
  const rows=avFiltered();
  view.innerHTML=`<div class="avbar">
      <input id="avsearch" class="avsearch" placeholder="🔍 חפש אברך או שותף…" value="${esc(avSearch)}" autocomplete="off">
      <button class="btn sm ghost" id="avizhist">🕘 היסטוריה</button><button class="btn sm ghost" id="avprint">🖨️ הדפסה</button><button class="btn sm" id="avslips">🕯️ דפי קוויטל</button><button class="btn sm" id="avcards2">👥 לפי תורמים</button></div>
    <div class="avstat">👨‍🎓 <b>${st.total}</b> אברכים בכולל · <b class="${st.free?'avfreen':''}">${st.free}</b> בלי שותף${q2?` · מוצגים ${rows.length}`:''}</div>
    ${avPendHTML()}
    <div class="addrow avnewbox"><input id="av_new" placeholder="➕ אברך חדש — שם משפחה ואז שם פרטי"><button class="btn sm" id="av_newbtn">הוסף</button></div>
    <div class="avwrap"><div class="avinner">
      <div class="avghead"><span class="g1">#</span><span class="g2">האברך</span><span class="g3">הזבולון</span><span class="g4">מתאריך</span><span class="g5">סכום</span><span class="g6">הערות</span><span class="g7"></span></div>
      <div class="avtlist">${rows.map((a,i)=>avRowHTML(a,i)).join('')||'<div class="empty">אין תוצאות</div>'}</div>
    </div></div>`;
  const se=document.getElementById('avsearch');
  se.oninput=()=>{avSearch=se.value;clearTimeout(se._t);se._t=setTimeout(()=>{
    const p=se.selectionStart;paintByAv();const s2=document.getElementById('avsearch');
    if(s2){s2.focus();try{s2.setSelectionRange(p,p);}catch(e){}}},250);};
  document.getElementById('avcards2').onclick=()=>{avView='cards';render();};
  document.getElementById('avizhist').onclick=()=>{izHist=true;renderIzHistory();};
  document.getElementById('avprint').onclick=()=>{avView='avprint';render();};
  document.getElementById('avslips').onclick=()=>window.open('/iz-slips','_blank');
  wireByAv();
}
// יומן כללי — כל שינוי שנעשה ביששכר־זבולון, אצל כל האברכים והתורמים
async function renderIzHistory(){
  chips.innerHTML='';
  view.innerHTML='<div class="cnt">טוען היסטוריה…</div>';
  let r=null; try{ r=await api('GET','/api/izhistory'); }catch(e){}
  const rows=(r&&r.rows)||[];
  view.innerHTML=`<div class="avbar"><button class="btn sm" id="izback">→ חזרה לרשימת האברכים</button></div>
    <div class="avstat">🕘 <b>${rows.length}</b> שינויים ביששכר־זבולון — מהחדש לישן</div>
    <div class="avtlist">${rows.map(x=>`<div class="avtrow"><div class="izhrow">
      <b>${esc(x.hdate||'')}</b> <small>${esc(x.date||'')}${hhmm(x.at)?(' · '+hhmm(x.at)):''}</small>
      ${x.donor?` · <a class="avhold" data-did="${x.donor_id}">${esc(x.donor)}</a>`:''}
      <div>${esc(x.text||'')}</div></div></div>`).join('')||'<div class="empty">אין עדיין היסטוריה</div>'}</div>`;
  document.getElementById('izback').onclick=()=>{izHist=false;renderAvByAv();};
  view.querySelectorAll('.avhold').forEach(a=>a.onclick=()=>{const d=DB.find(x=>x.id==a.dataset.did);if(d)openDonor(d);});
}
function paintByAv(){
  const rows=avFiltered();
  const el=view.querySelector('.avtlist'); if(!el)return;
  el.innerHTML=rows.map((a,i)=>avRowHTML(a,i)).join('')||'<div class="empty">אין תוצאות</div>';
  wireByAv();
}
function avRowHTML(a,ix){
  const h=a.holders||[], open=avOpenId===a.name, sw=avSwapId;
  const amtOf=x=>{const v=(x.share!==''&&x.share!=null)?x.share:(x.amount||'');
    const n=amtNum(v); return n?String(Math.round(n)):String(v||'');};
  // שותף מקושר — השורה עצמה רשומה אצל המחזיק השני, ולכן הסכום והתאריך
  // נערכים שם ולא כאן. מוצג כדי שהרשימה תהיה מסונכרנת עם מה שנרשם בכרטיס.
  const line=(x,first)=>`<div class="avg${x&&x.linked?' avglink':''}" ${x&&!x.linked?`data-pid="${x.pid}"`:''}>
    <span class="g1">${first?`<span class="avnum">${ix+1}</span>`:''}</span>
    <span class="g2">${first?`<a class="avname" data-av="${esc(a.name)}" title="לחץ לפרטים של האברך">${esc(a.name)}</a>`:''}</span>
    <span class="g3">${x?`<a class="avhold" data-did="${x.id}" title="פתח כרטיס">${esc(x.name)}</a>${x.linked?` <small class="avlinktag">🤝 יחד עם ${esc(x.via||'')}</small>`:''}`:'<span class="avfree">— אין שותף —</span>'}</span>
    <span class="g4">${x&&!x.linked?`<input class="avh_dt" data-pid="${x.pid}" value="${esc(x.start_date||'')}" placeholder="מתאריך">`:(x?`<small class="avlinkdt">${esc(x.start_date||'')}</small>`:'')}</span>
    <span class="g5">${x&&!x.linked?`<input class="avh_amt" data-pid="${x.pid}" value="${esc(amtOf(x))}" inputmode="decimal" placeholder="—">`:''}</span>
    <span class="g6">${first?`<input class="avnote" data-av="${esc(a.name)}" data-id="${a.aid||''}" value="${esc(a.note||'')}" placeholder="הערות…">`:''}</span>
    <span class="g7">${x&&!x.linked?`<button class="ib avh_swap" data-pid="${x.pid}" title="החלף תורם">🔀</button><button class="ib rd avh_rm" data-pid="${x.pid}" title="הסר שותפות">✕</button>`:''}${first?`<button class="ib avslip" data-av="${esc(a.name)}" title="פתק קוויטל של האברך">🕯️</button><button class="ib avassign" data-av="${esc(a.name)}" title="${h.length?'הוסף עוד שותף':'שבץ שותף'}">➕</button>${(a.log||[]).length?`<button class="ib avhist2" data-av="${esc(a.name)}" title="היסטוריה של האברך">🕘</button>`:''}<button class="ib rd avgone" data-av="${esc(a.name)}" title="יצא מהכולל">🚪</button>`:''}</span>
  </div>${sw&&x&&!x.linked&&sw===x.pid?`<div class="avswapbox"><input class="sw_q" data-pid="${x.pid}" placeholder="לאיזה תורם להעביר…" autocomplete="off"><div class="dpres sw_res" data-pid="${x.pid}"></div></div>`:''}`;
  return `<div class="avtrow ${h.length?'':'isfree'}" data-av="${esc(a.name)}">
    ${h.length?h.map((x,i)=>line(x,i===0)).join(''):line(null,true)}
    ${avInfoId===a.name?`<div class="avinfobox">
      <label class="fld"><span>👨‍🎓 שם האברך (שם משפחה ואז שם פרטי)</span><input class="avname2" data-av="${esc(a.name)}" data-id="${a.aid||''}" value="${esc(a.name)}"></label>
      <div class="two" style="margin-top:6px"><label class="fld"><span>📞 טלפון</span><input class="avf" data-k="phone" data-av="${esc(a.name)}" dir="ltr" value="${esc(a.phone||'')}"></label>
        <label class="fld"><span>📧 אימייל</span><input class="avf" data-k="email" data-av="${esc(a.name)}" dir="ltr" value="${esc(a.email||'')}"></label></div>
      <label class="fld" style="margin-top:6px"><span>🏠 כתובת</span><input class="avf" data-k="addr" data-av="${esc(a.name)}" value="${esc(a.addr||'')}"></label>
      <div class="two" style="margin-top:6px"><label class="fld"><span>🆔 תעודת זהות</span><input class="avf" data-k="idnum" data-av="${esc(a.name)}" dir="ltr" inputmode="numeric" value="${esc(a.idnum||'')}"></label>
        <label class="fld"><span>📖 סדר</span><input class="avf" data-k="seder" data-av="${esc(a.name)}" value="${esc(a.seder||'')}"></label></div>
      ${(a.idnum&&+a.id_ok===0)?'<div class="hintxt" style="color:var(--no)">⚠️ ספרת הביקורת של תעודת הזהות אינה מסתדרת — כדאי לוודא מול הכולל</div>':''}
      ${a.started?`<div class="hintxt">התחיל: ${esc(a.started)}</div>`:''}</div>`:''}
    ${avHistId===a.name?`<div class="avhistbox">${(a.log||[]).map(L=>
      `<div class="avhline"><b>${esc(L.hdate||'')}</b> <small>${esc(L.date||'')}</small>${L.donor?(' · '+esc(L.donor)):''}<br>${esc(L.text||'')}</div>`).join('')||'<div class="hintxt">אין עדיין היסטוריה</div>'}</div>`:''}
    ${open?`<div class="avassignbox">
      <input class="av_q" data-av="${esc(a.name)}" placeholder="חפש תורם…" autocomplete="off">
      <div class="dpres av_res" data-av="${esc(a.name)}"></div>
      <div class="chosen av_ch" data-av="${esc(a.name)}"></div>
      <div class="two" style="margin-top:6px"><label class="fld"><span>📅 מתאריך (עברי)</span>${hebDateSel('av_dt','')}</label>
        <label class="fld"><span>סכום לחודש</span><input class="av_amt" data-av="${esc(a.name)}" inputmode="decimal" placeholder="—"></label></div>
      <div class="hintxt av_hint" data-av="${esc(a.name)}"></div>
      <button class="btn sm av_save" data-av="${esc(a.name)}" style="width:100%;margin-top:6px">💾 שבץ ועדכן אצל התורם</button></div>`:''}
  </div>`;
}
// פתק הקוויטל של אברך — אותה דרך בדיוק כמו תעודת פרנס יום: פתיחה לצפייה
// והדפסה, או העתקה כתמונה לשליחה בוואטסאפ.
async function openIzSlip(av){
  let rows=[];
  try{ const r=await api('GET','/api/izslips?av='+encodeURIComponent(av)); rows=(r&&r.rows)||[]; }catch(e){}
  if(!rows.length){toast('לא נמצא תורם לאברך הזה');return;}
  const rs=document.getElementById('remsheet'), remov=document.getElementById('remov');
  const url=r=>'/izslip.png?'+new URLSearchParams({av:r.avreich,donor:r.donor,names:r.names||''}).toString();
  rs.innerHTML=`<button class="x" id="rx">✕</button><h2>🕯️ פתק קוויטל — ${esc(av)}</h2>
    ${rows.map((r,i)=>`<div class="izslipbox">
      <div class="hintxt">זבולון: <b>${esc(r.donor)}</b>${r.names?'':' · אין עדיין שמות לקוויטל'}</div>
      <img class="izslipimg" src="${esc(url(r))}" alt="">
      <div class="addrow"><button class="btn sm izslipcopy" data-i="${i}">📋 העתק תמונה (דף שלם)</button>
        <button class="btn sm ghost izslipopen" data-i="${i}">🖨️ הדפסה (חצי דף)</button></div></div>`).join('')}`;
  remov.classList.add('show');
  document.getElementById('rx').onclick=()=>remov.classList.remove('show');
  rs.querySelectorAll('.izslipopen').forEach(b=>b.onclick=()=>
    window.open('/iz-slips?av='+encodeURIComponent(av),'_blank'));
  rs.querySelectorAll('.izslipcopy').forEach(b=>b.onclick=async()=>{
    const r=rows[+b.dataset.i];
    try{
      const blob=await fetch(url(r)).then(x=>x.blob());
      if(navigator.canShare&&navigator.canShare({files:[new File([blob],'kvittel.png',{type:'image/png'})]})){
        await navigator.share({files:[new File([blob],'kvittel.png',{type:'image/png'})]}); return; }
      await navigator.clipboard.write([new ClipboardItem({'image/png':blob})]);
      toast('התמונה הועתקה ✓');
    }catch(e){ window.open(url(r),'_blank'); }});
}
function wireByAv(){
  const nb=document.getElementById('av_newbtn'), ni=document.getElementById('av_new');
  if(nb&&!nb._w){nb._w=1;
    const addAv=async()=>{const nm=(ni.value||'').trim(); if(!nm){ni.focus();return;}
      nb.disabled=true; const r=await api('POST','/api/avreich',{name:nm}); nb.disabled=false;
      if(r&&r.error==='exists'){toast('האברך כבר ברשימה');return;}
      ni.value=''; toast('נוסף לרשימה ✓'); renderAvByAv();};
    nb.onclick=addAv; ni.onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();addAv();}};}
  const reload=async()=>{await load();await renderAvByAv();};
  view.querySelectorAll('.avhold').forEach(a=>a.onclick=()=>{const d=DB.find(x=>x.id==a.dataset.did);if(d)openDonor(d);});
  // שם האברך — שינוי כאן מחליף את השם גם אצל כל המחזיקים שלו
  view.querySelectorAll('.avname').forEach(a2=>a2.onclick=()=>{
    avInfoId=(avInfoId===a2.dataset.av)?null:a2.dataset.av; paintByAv();});
  view.querySelectorAll('.avname2').forEach(inp=>inp.onchange=async()=>{
    const a=AVLIST.find(x=>x.name===inp.dataset.av), nm=inp.value.trim();
    if(!a||!nm||nm===a.name){inp.value=a?a.name:inp.value;return;}
    await api('POST','/api/avreich',{id:a.aid,name:nm});
    if(avInfoId===a.name)avInfoId=nm;      // הכרטיס נשאר פתוח על השם החדש
    if(avHistId===a.name)avHistId=nm;
    toast('שם האברך עודכן ✓'); reload();});
  view.querySelectorAll('.avnote').forEach(inp=>inp.onchange=async()=>{
    const a=AVLIST.find(x=>x.name===inp.dataset.av); if(!a)return;
    a.note=inp.value; await api('POST','/api/avreich',{id:a.aid,name:a.name,note:inp.value}); toast('ההערה נשמרה ✓');});
  // תאריך וסכום — נשמרים אצל התורם ברגע היציאה מהשדה
  const saveH=async(pid,body)=>{const r=await api('POST','/api/avreich/holder',{pid:+pid,at:nowStamp(),...body});
    if(r&&r.error==='already'){toast('האברך כבר משובץ אצל התורם הזה');return false;}
    if(!r||!r.ok){toast('לא נשמר');return false;} return true;};
  view.querySelectorAll('.avh_dt').forEach(inp=>inp.onchange=async()=>{
    if(await saveH(inp.dataset.pid,{start_date:inp.value.trim()})){toast('התאריך עודכן ✓');reload();}});
  view.querySelectorAll('.avh_amt').forEach(inp=>inp.onchange=async()=>{
    if(await saveH(inp.dataset.pid,{amount:inp.value.trim()})){toast('הסכום עודכן אצל התורם ✓');reload();}});
  view.querySelectorAll('.avh_rm').forEach(b=>b.onclick=async()=>{
    if(!await uiConfirm('להסיר את השותפות הזו?\nהאברך יישאר ברשימה, בלי שותף.'))return;
    if(await saveH(b.dataset.pid,{remove:1})){toast('הוסר ✓');reload();}});
  view.querySelectorAll('.avh_swap').forEach(b=>b.onclick=()=>{
    avSwapId=(avSwapId===+b.dataset.pid)?null:+b.dataset.pid; paintByAv();});
  view.querySelectorAll('.sw_q').forEach(qi=>{
    const pid=qi.dataset.pid, res=view.querySelector('.sw_res[data-pid="'+pid+'"]');
    qi.focus();
    qi.oninput=()=>{const s2=norm(qi.value);if(!s2){res.innerHTML='';return;}
      const m=DB.filter(d=>norm(d.last+' '+d.first+' '+d.english+' '+d.business).includes(s2)).slice(0,8);
      res.innerHTML=m.map(d=>`<div class="dpr" data-id="${d.id}">${esc(d.last)} ${esc(d.first)}${d.tier==='יששכר_זבולון'?' · יש"ז':''}</div>`).join('')||'<div class="dpr" style="color:var(--muted)">אין תוצאות</div>';
      res.querySelectorAll('.dpr[data-id]').forEach(x=>x.onclick=async()=>{
        if(await saveH(pid,{donor_id:+x.dataset.id})){avSwapId=null;toast('הועבר לתורם החדש ✓');reload();}});};});
  // פתק הקוויטל של אברך אחד — לצפייה, להדפסה, ולהעתקה כתמונה (כמו פרנס יום)
  view.querySelectorAll('.avslip').forEach(b=>b.onclick=()=>openIzSlip(b.dataset.av));
  view.querySelectorAll('.avassign').forEach(b=>b.onclick=()=>{
    avOpenId=(avOpenId===b.dataset.av)?null:b.dataset.av; avSwapId=null; paintByAv();});
  view.querySelectorAll('.avhist2').forEach(b=>b.onclick=()=>{
    avHistId=(avHistId===b.dataset.av)?null:b.dataset.av; paintByAv();});

  view.querySelectorAll('.avf').forEach(inp=>inp.onchange=async()=>{
    const a=AVLIST.find(x=>x.name===inp.dataset.av); if(!a)return;
    a[inp.dataset.k]=inp.value;
    await api('POST','/api/avreich',{id:a.aid,name:a.name,[inp.dataset.k]:inp.value});
    toast('נשמר ✓');});
  // יצא מהכולל — השותפויות נסגרות והאברך יורד מהרשימה, עם תאריך בהיסטוריה
  view.querySelectorAll('.avgone').forEach(b=>b.onclick=async()=>{
    const a=AVLIST.find(x=>x.name===b.dataset.av); if(!a)return;
    const who=(a.holders||[]).map(h=>h.name);
    // מאיר: "אמורה להיות הערה מתי האברך יצא ומי הוא היה" — התאריך העברי
    // נשאל כאן, ונשמר על המקום שהתפנה אצל כל מחזיק.
    const msg=who.length
      ? ('באיזה תאריך (עברי) '+a.name+' יצא מהכולל?\nהמקום יישאר פתוח אצל '+who.join(', ')
         +' — המניין שלהם לא ישתנה, ורק השם יתפנה.')
      : ('באיזה תאריך (עברי) '+a.name+' יצא מהכולל?\nהוא יירד מהרשימה, וההיסטוריה שלו תישמר.');
    const hd=await uiPrompt(msg, HEBTODAY);
    if(hd===null)return;
    const r=await api('POST','/api/avreich',{id:a.aid,name:a.name,delete:1,force:1,
      at:nowStamp(),hdate:hd||HEBTODAY});
    if(!r||!r.ok){toast('לא בוצע');return;}
    toast('יצא מהכולל ✓'); await load(); renderAvByAv();});
  view.querySelectorAll('.av_q').forEach(qi=>{
    const av=qi.dataset.av, res=view.querySelector('.av_res[data-av="'+CSS.escape(av)+'"]'),
          ch=view.querySelector('.av_ch[data-av="'+CSS.escape(av)+'"]');
    qi.focus();
    qi.oninput=()=>{const s2=norm(qi.value);if(!s2){res.innerHTML='';return;}
      const m=DB.filter(d=>norm(d.last+' '+d.first+' '+d.english+' '+d.business).includes(s2)).slice(0,8);
      res.innerHTML=m.map(d=>`<div class="dpr" data-id="${d.id}">${esc(d.last)} ${esc(d.first)}${d.tier==='יששכר_זבולון'?' · יש"ז':''}</div>`).join('')||'<div class="dpr" style="color:var(--muted)">אין תוצאות</div>';
      res.querySelectorAll('.dpr[data-id]').forEach(x=>x.onclick=()=>{
        const d=DB.find(y=>y.id==x.dataset.id);
        ch.textContent='נבחר: '+(d.last+' '+(d.first||'')).trim(); ch.dataset.did=d.id;
        res.innerHTML=''; qi.value=(d.last+' '+(d.first||'')).trim();
        // מאיר: "זה אמור להיות כבר מסונכרן שיש לו 700 שהוא משלם ואין שותף
        // אז אוטומטית זה יכתוב 700" — הסכום נלקח ממה שהוא כבר משלם
        const g=avDonorRate(d), am=view.querySelector('.av_amt[data-av="'+CSS.escape(av)+'"]'),
              hn=view.querySelector('.av_hint[data-av="'+CSS.escape(av)+'"]');
        if(am&&g.amt&&!am.value.trim())am.value=String(g.amt);
        if(hn)hn.textContent=g.why||'';});};});
  view.querySelectorAll('.av_save').forEach(b=>b.onclick=async()=>{
    const av=b.dataset.av, sel=v=>view.querySelector('.'+v+'[data-av="'+CSS.escape(av)+'"]');
    const ch=sel('av_ch'), did=ch&&ch.dataset.did;
    if(!did){toast('בחר תורם');return;}
    const a=AVLIST.find(x=>x.name===av);
    b.disabled=true;
    const r=await api('POST','/api/avreich/assign',{avreich_id:a&&a.aid,name:av,donor_id:+did,
      start_date:hebDateGet(view.querySelector('.hedate.av_dt')),
      amount:(sel('av_amt').value||'').trim(),at:nowStamp()});
    b.disabled=false;
    if(r&&r.error==='already'){toast('כבר משובץ אצל התורם הזה');return;}
    if(!r||!r.ok){toast('לא נשמר');return;}
    avOpenId=null; toast('שובץ אצל '+r.donor+' ✓'); reload();});
}
// גיליון להדפסה של רשימת האברכים — בלי כפתורים, כל הטורים על הדף
async function renderAvPrint(){
  chips.innerHTML='';
  view.innerHTML='<div class="cnt">מכין להדפסה…</div>';
  await loadAvList();
  const rows=avFiltered(), free=rows.filter(a=>!a.holders.length).length;
  const today=new Date(), z=n=>String(n).padStart(2,'0');
  const dstr=z(today.getDate())+'/'+z(today.getMonth()+1)+'/'+today.getFullYear();
  const line=[];
  rows.forEach((a,i)=>{
    const h=a.holders||[];
    if(!h.length)line.push({i:i+1,nm:a.name,who:'— אין שותף —',dt:a.started||'',amt:'',note:a.note||'',free:1});
    else h.forEach((x,k)=>{const v=(x.share!==''&&x.share!=null)?x.share:(x.amount||''),n=amtNum(v);
      line.push({i:k?'':i+1,nm:k?'':a.name,who:x.name,dt:x.start_date||'',
        amt:n?String(Math.round(n)):String(v||''),note:k?'':(a.note||''),free:0});});
  });
  view.innerHTML=`<div class="avbar noprint">
      <button class="back" id="avpback">→ חזרה לרשימה</button>
      <button class="print" onclick="window.print()">הדפס 🖨️</button></div>
    <div class="avtabtitle"><b>רשימת אברכי הכולל — יששכר־זבולון</b>
      <div class="prsub">${rows.length} אברכים · ${free} בלי שותף · הופק ${dstr}</div></div>
    <table class="avtable prtable"><thead><tr>
      <th style="width:34px">#</th><th>האברך</th><th>הזבולון</th><th>מתאריך</th><th>סכום</th><th>הערות</th></tr></thead>
    <tbody>${line.map(r=>`<tr class="${r.free?'prfree':''}"><td>${r.i}</td><td><b>${esc(r.nm)}</b></td>
      <td>${esc(r.who)}</td><td>${esc(r.dt)}</td><td>${r.amt?('$'+esc(r.amt)):''}</td><td>${esc(r.note)}</td></tr>`).join('')}</tbody>
    </table>`;
  document.getElementById('avpback').onclick=()=>{avView='byav';render();};
}
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
  if(avView==='byav') return renderAvByAv();
  if(avView==='avprint') return renderAvPrint();
  const totalAv=DB.reduce((s,d)=>s+(d.partners||[]).filter(p=>p.active!=0).length,0);
  view.innerHTML=`<div class="avbar">
      <input id="avsearch" class="avsearch" placeholder="🔍 חפש תורם או אברך…" value="${esc(avSearch)}" autocomplete="off">
      <select id="avsort" class="avsortsel">
        <option value="last">מיון: תורם (א-ב)</option>
        <option value="av">מיון: אברך (א-ב)</option>
        <option value="amt">מיון: סכום (גבוה→נמוך)</option>
      </select>
      <button class="btn sm" id="avbyavbtn">👨‍🎓 לפי אברכים</button><button class="btn sm" id="avtablebtn">🖨️ טבלה</button></div>
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
        <div class="avps">${act.length?act.map(p=>avPartnerRow(p)).join(''):''}${izLinkedHTML(d,cs)}${act.length||izLinkedRows(d).length?'':'<div class="hintxt">אין אברך פעיל כרגע</div>'}</div>
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
  document.getElementById('avbyavbtn').onclick=()=>{avView='byav';render();};
  searchEl.oninput=()=>{avSearch=searchEl.value;paintList();};
  sortSel.onchange=()=>{avSort=sortSel.value;paintList();};
  paintList();
}
// שותפים לאותו אברך — מקישור ידני (partner_with) וגם זיהוי אוטומטי של תורמים אחרים שמחזיקים אותו אברך
function avCoHolders(p){
  const av=norm(p.avreich||'');const set=new Map();
  if(av)(DB||[]).forEach(o=>{if(o.id==p.donor_id)return;(o.partners||[]).forEach(q=>{if(q.active==0)return;if(norm(q.avreich||'')===av){const nm=(o.last+' '+o.first).trim();const k=norm(nm);if(!set.has(k))set.set(k,{name:nm,id:o.id});}});});
  pwList(p).forEach(x=>{if(x.name){const k=norm(x.name);if(!set.has(k))set.set(k,{name:x.name,id:x.id});}});
  // מי שמתחלק עם בעל השורה בתשלום הוא שותף גם באברך עצמו — אלא אם יש לו
  // אברך משלו. מאיר: "אדלין ודהאן — כל אחד נותן 1000 ליששכר־זבולון שלו,
  // וזה יוצא מהעסק בתשלום אחד של 2000". שם החלוקה היא של הכסף בלבד.
  const own=(DB||[]).find(x=>x.id==p.donor_id);
  if(own&&av)(own.paysplit||[]).forEach(s=>{
    const o=(DB||[]).find(x=>x.id===s.with_id); if(!o||o.id==p.donor_id)return;
    if((o.partners||[]).some(q=>q.active!=0&&String(q.avreich||'').trim()))return;
    const nm=(o.last+' '+o.first).trim(),k=norm(nm);
    if(nm&&!set.has(k))set.set(k,{name:nm,id:o.id});});
  return [...set.values()];
}
// כמה התורם משלם לאברך. קודם כל מקום שהתפנה — הסכום שלו הוא הסכום שכבר
// סוכם עליו; אחרת הסכום החוזר על עצמו אצל שאר האברכים שלו.
function avDonorRate(d){
  const act=(d.partners||[]).filter(p=>p.active!=0);
  const slot=act.find(p=>!String(p.avreich||'').trim()&&amtNum(p.amount)>0);
  if(slot)return {amt:Math.round(amtNum(slot.amount)),
    why:'לפי המקום שהתפנה' + (slot.prev_avreich?(' אחרי '+slot.prev_avreich):'')};
  const cnt={};
  act.forEach(p=>{const v=Math.round(amtNum(p.amount)); if(v>0)cnt[v]=(cnt[v]||0)+1;});
  let best=0,bn=0; Object.keys(cnt).forEach(v=>{if(cnt[v]>bn){best=+v;bn=cnt[v];}});
  if(best)return {amt:best, why:'לפי מה שהוא משלם על '+(bn===1?'האברך השני':'שאר האברכים')};
  return {amt:0, why:''};
}
// שמות האברכים שהתורם מחזיק בפועל — כולל אלה שהשורה שלהם רשומה אצל השותף
function izAvNames(d){
  const out=[];
  (d.partners||[]).forEach(p=>{const n=String(p.avreich||'').trim(); if(p.active!=0&&n)out.push(n);});
  izLinkedRows(d).forEach(x=>{if(out.indexOf(x.avreich)<0)out.push(x.avreich);});
  return out;
}
// מקום שהתפנה — האברך שהיה בו יצא מהכולל, והתורם עדיין מחזיק אותו
function avOpenSlot(p){return !String(p.avreich||'').trim()&&!!String(p.prev_avreich||'').trim();}
function avSlotNote(p){
  if(!avOpenSlot(p))return '';
  return `<div class="avgap">🚪 ${esc(p.prev_avreich)} יצא מהכולל`
    +`${p.prev_ended?(' ב'+esc(p.prev_ended)):''} — המקום פתוח, חפש אברך חדש ומלא כאן</div>`;
}
function avPartnerRow(p){
  const co=avCoHolders(p);
  const coHtml=co.length?`<div class="avco">🤝 מוחזק במשותף עם: ${co.map(x=>x.id?`<span class="cosp2" data-did="${x.id}">${esc(x.name)} ↗</span>`:esc(x.name)).join(', ')}</div>`:'';
  return `<div class="avp${avOpenSlot(p)?' avpgap':''}" data-pid="${p.id}">
    ${avSlotNote(p)}
    <div class="avmain"><input class="avf avname" data-k="avreich" value="${esc(p.avreich||'')}" placeholder="${avOpenSlot(p)?'שם האברך החדש למקום הזה':'שם האברך'}">
      <div class="avamt"><span>$</span><input class="avf" data-k="amount" value="${esc(p.amount||'')}" placeholder="סכום" inputmode="decimal"></div>
      <button class="avend" title="החלפת אברך — הקודם יישמר בהיסטוריה">🔄 החלפה</button></div>
    <div class="avsub">
      <label class="avfld"><span>💳 אמצעי</span><select class="avf avmethod chansel" data-k="method">${channelOpts(p.method)}</select></label>
      <label class="avfld"><span>📅 מתאריך ההסכם</span><input class="avf" data-k="start_date" value="${esc(p.start_date||'')}" placeholder="למשל א' אייר תשפ״ה"></label>
      <label class="avfld"><span>📝 הערות</span><input class="avf" data-k="note" value="${esc(p.note||'')}" placeholder="—"></label></div>
    <label class="avfld" style="margin-top:6px"><span>💰 עדכון תשלום ידני (למשל: שילם הכל מראש)</span><input class="avf" data-k="paid_note" value="${esc(p.paid_note||'')}" placeholder="הערת תשלום"></label>
    <label class="jointchk" style="margin-top:6px"><input type="checkbox" class="avjoint" data-pid="${p.id}" ${+p.joint?'checked':''}> 🤝 נותנים ביחד סכום אחד משותף (לא לחבר)</label>
    <button class="btn sm avsave" data-pid="${p.id}" style="width:100%;margin-top:6px">💾 שמור</button>
    <div class="hintxt avdirty hidden">✏️ יש שינוי שעדיין לא נשמר</div>
    ${coHtml}</div>`;
}
function bindAvFields(){
  view.querySelectorAll('.avp').forEach(row=>{const pid=row.dataset.pid;
    const dirty=row.querySelector('.avdirty'), sbtn=row.querySelector('.avsave');
    const mark=on=>{ if(dirty)dirty.classList.toggle('hidden',!on);
      if(sbtn)sbtn.classList.toggle('warn',on); };
    const saveAll=async(quiet)=>{
      const body={};
      row.querySelectorAll('.avf').forEach(i=>{body[i.dataset.k]=i.value;});
      await api('PUT','/api/partner/'+pid,body);
      DB.forEach(d=>(d.partners||[]).forEach(p=>{if(p.id==pid)Object.assign(p,body);}));
      mark(false); if(!quiet)toast('נשמר ✓');
    };
    row._saveAll=saveAll;
    if(sbtn)sbtn.onclick=()=>saveAll();
    row.querySelectorAll('.avf').forEach(inp=>{
      const save=async()=>{const body={};body[inp.dataset.k]=inp.value;await api('PUT','/api/partner/'+pid,body);DB.forEach(d=>(d.partners||[]).forEach(p=>{if(p.id==pid)p[inp.dataset.k]=inp.value;}));mark(false);toast('נשמר ✓');};
      inp.oninput=()=>mark(true);          // מסמנים שיש שינוי — השמירה בלחיצה
      inp.onchange=save;                   // יציאה מהשדה שומרת גם היא, כרשת ביטחון
    });
    // מאיר: "אז אמור להיות עוד חלון ריק שאחפש לו אברך אחד ואמלא כאן".
    // החלפה אינה סוגרת את השורה — היא מפנה את המקום ומשאירה אותו פתוח,
    // עם השם והתאריך של מי שהיה בו, כדי שמניין האברכים יישאר נכון.
    row.querySelector('.avend').onclick=async()=>{
      let p0=null; DB.forEach(d=>(d.partners||[]).forEach(p=>{if(p.id==pid)p0=p;}));
      const nm=String((p0&&p0.avreich)||'').trim();
      if(!nm){toast('המקום כבר פתוח');return;}
      const hd=await uiPrompt('באיזה תאריך (עברי) '+nm+' יצא?', HEBTODAY);
      if(hd===null)return;
      const body={avreich:'',start_date:'',prev_avreich:nm,prev_ended:hd||HEBTODAY};
      await api('PUT','/api/partner/'+pid,body);
      if(p0)Object.assign(p0,body);
      renderAvreich(); toast('המקום פתוח — מלא אברך חדש');};
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
// מאיר: "חשוב לי ההיסטוריה של האברכים השותפים — מתי נכנס חדש לפי תאריך
// עברי שאעדכן ומתי יצא". שתי שכבות: שותפויות שנסגרו לגמרי, ולצידן היומן
// עצמו — יציאה מהכולל, כניסה למקום שהתפנה, שינוי תאריך או סכום.
async function showAvHist(d){
  const hist=(d.partners||[]).filter(p=>p.active==0).sort((a,b)=>(b.start_date||'').localeCompare(a.start_date||''));
  const open=(d.partners||[]).filter(p=>p.active!=0&&avOpenSlot(p));
  const rs=document.getElementById('remsheet'),remov=document.getElementById('remov');
  rs.innerHTML=`<button class="x" id="rx">✕</button><h2>🕘 היסטוריית אברכים — ${esc(d.last)} ${esc(d.first)}</h2>
    <div class="hintxt">טוען את היומן…</div>`;
  remov.classList.add('show');document.getElementById('rx').onclick=()=>remov.classList.remove('show');
  let log=[]; try{const r=await api('GET','/api/izhistory?donor='+d.id); log=(r&&r.rows)||[];}catch(e){}
  rs.innerHTML=`<button class="x" id="rx">✕</button><h2>🕘 היסטוריית אברכים — ${esc(d.last)} ${esc(d.first)}</h2>
    ${open.map(p=>`<div class="remitem"><div class="ri"><b style="color:#8a5a12">🚪 מקום פתוח</b><br>
      <small>${esc(p.prev_avreich||'')} יצא מהכולל${p.prev_ended?(' ב'+esc(p.prev_ended)):''}${p.amount?(' · $'+esc(p.amount)):''}</small></div></div>`).join('')}
    ${hist.map(p=>`<div class="remitem"><div class="ri"><b>${esc(p.avreich||'—')}</b><br><small>התחיל: ${esc(p.start_date||'?')} · הסתיים: ${esc(p.ended_date||'?')} ${p.amount?('· $'+esc(p.amount)):''}${p.note?(' · '+esc(p.note)):''}</small></div></div>`).join('')}
    ${log.length?`<div class="hintxt" style="margin:8px 2px 4px">📖 יומן השינויים</div>`+log.map(L=>
      `<div class="remitem"><div class="ri"><b>${esc(L.hdate||L.date||'')}</b>${L.date?(' <small>'+esc(L.date)+'</small>'):''}<br><small>${esc(L.text||'')}</small></div></div>`).join(''):''}
    ${(open.length||hist.length||log.length)?'':'<div class="hintxt">אין היסטוריה.</div>'}`;
  document.getElementById('rx').onclick=()=>remov.classList.remove('show');
}


/* ---------- תורמים ישנים: מי שלא נכנס ממנו כסף מאז תאריך מסוים ---------- */
let OLD=null, oldSince='2024-01-01';
/* ---------- 📋 לבדיקה — כל השאלות במקום אחד ----------
   מאיר: "חשוב לי שזה יהיה מרוכז במקום אחד, שאדפיס ואעדכן אחד אחד".
   כל תורם שיש לגביו שאלה מופיע כאן עם המספרים, עם סטטוס שאפשר לקבוע
   ועם מקום להערה. מה שסומן "טופל" או "בסדר" יורד מהרשימה הפתוחה. */
const RVST=[['ok','בסדר'],['check','צריך בדיקה'],['debt','חוב אמיתי'],['done','טופל']];
let RVSTAT=null, RVSHOW='open';
// תורמים שהסכום שלהם הגיע מהייבוא אבל הכסף ממשיך להיכנס כרגיל — אין שם
// שום שאלה פתוחה, ואין סיבה להטריח את מאיר לעבור עליהם אחד־אחד
let RVASKALL=false, RVQUIET=0;
function reviewList(){
  const out=[]; RVQUIET=0;
  (DB||[]).forEach(d=>{
    let a=null; try{a=purposeAlloc(d);}catch(e){}
    // אין התחייבות רשומה, אבל יש סכום שהמערכת הסיקה מהייבוא. זו לא שאלה
    // של חוב אלא של רישום: האם הוא בכלל התחייבות. מאיר עובר על אלה
    // ומחליט אחד־אחד — וזו בדיוק הרשימה להדפסה.
    if(!a||a.exp<=0.5){
      let rows=[]; try{rows=commitRows(d);}catch(e){}
      const ask=rows.filter(r=>r.conf===0&&r.amt>0.5);
      if(!ask.length)return;
      const ob=obsYear(d), cur=curSym(d);
      // ממשיך לתת עד החודש האחרון שיש עליו נתונים — אין מה לשאול עליו
      if(ob.sum>0.5&&ob.last>=dataThru()&&!RVASKALL){RVQUIET++;return;}
      out.push({d, kind:'ask', gap:0, exp:0, got:ob.sum, per:Math.round(ob.per),
        thru:'', rows:ask.map(r=>({what:r.what, per:r.amt})),
        why:'לא רשום שהוא התחייב סכום. בכרטיס הופיע '+cur+Math.round(ask[0].amt)
            +' מהייבוא, ובפועל נכנס ממנו השנה '+cur+Math.round(ob.sum)
            +(ob.n?(' ב-'+ob.n+' '+(ob.n===1?'חודש':'חודשים')+' — '+cur+Math.round(ob.per)+' בממוצע'):'')
            +'. לאשר, לתקן, או לקבוע שאין התחייבות.'});
      return;
    }
    const gap=a.exp-a.got;
    let kind='', why='';
    if(a.got<=0.5){kind='none'; why='לא נכנס ממנו כסף כלל בתקופה';}
    else if(a.steady>0.5){kind='amount';
      why='משלם '+curSym(d)+Math.round(a.steady)+' בכל חודש בלי לפספס, וכאן רשום '
          +curSym(d)+Math.round(a.per)+' — או שהסכום שגוי, או שיש לו עוד התחייבות נפרדת';}
    else if(gap>0.5){kind='short';
      why='חסרים '+curSym(d)+Math.round(gap)+' — חודשים שלא נגבו';}
    else return;
    out.push({d, kind, why, gap:Math.round(gap), exp:a.exp, got:a.got,
      per:Math.round(a.per), thru:a.thru, rows:a.rows});
  });
  const ord={short:0, amount:1, none:2, ask:3};
  out.sort((x,y)=>(ord[x.kind]-ord[y.kind])||(y.gap-x.gap)||(y.got-x.got));
  return out;
}
const RVKIND={short:['🔴','חוסר אמיתי'],amount:['💡','הסכום בכרטיס'],none:['❓','לא נגבה כלום'],
              ask:['❔','לא רשום שהתחייב — צריך להחליט']};
const RVKINDSUB={
  short:'התחייבות שאתה רשמת, והכסף שנכנס בפועל קטן ממנה.',
  amount:'משלם באותו סכום בכל חודש, אבל בכרטיס רשום סכום אחר.',
  none:'רשומה התחייבות ולא נכנס ממנו כלום בתקופה.',
  ask:'הסכום כאן הגיע מהייבוא ולא ממך, ולכן הוא לא נחשב חוב. אשר אותו, תקן אותו, או קבע שאין התחייבות — ואז הוא לא יופיע יותר.'};
/* ---------- 💳 חיובים בלי תורם ----------
   מאיר על פיינגולד: "עוד חיובים שלא מופיעים פה בכלל". כסף שנגבה בפועל
   בבנק או באשראי ואינו רשום אצל אף תורם. מקובץ לפי המשלם — אותו אדם
   חוזר כל חודש — כך שהחלטה אחת מטפלת בכל החיובים שלו יחד. */
let ULDATA=null;
function ulKey(r){
  return ((r.first||'')+'|'+(r.last||'')+'|'+(r.email||'')).toLowerCase();
}
async function renderUnlinked(){
  view.innerHTML='<div class="cnt">טוען…</div>';
  try{ ULDATA=await api('GET','/api/unlinked'); }catch(e){ ULDATA={rows:[],total:0}; }
  const rows=(ULDATA&&ULDATA.rows)||[];
  const g={}, order=[];
  rows.forEach(r=>{const k=ulKey(r);
    if(!g[k]){g[k]={k,first:r.first||'',last:r.last||'',email:r.email||'',items:[],sugg:r.sugg||[]};order.push(k);}
    g[k].items.push(r);
    if(!g[k].sugg.length && (r.sugg||[]).length) g[k].sugg=r.sugg;});
  const groups=order.map(k=>g[k]);
  groups.forEach(x=>{x.sum=x.items.reduce((a,r)=>a+amtNum(r.amount),0);});
  groups.sort((a,b)=>b.sum-a.sum);
  const f=n=>'$'+Math.round(n).toLocaleString('en-US');
  const opts=(sel)=>(DB||[]).slice().sort((a,b)=>(a.last||'').localeCompare(b.last||'','he'))
    .map(d=>`<option value="${d.id}"${String(d.id)===String(sel)?' selected':''}>${esc((d.last+' '+d.first).trim())}</option>`).join('');
  view.innerHTML=`<div class="cnt">💳 חיובים שנגבו ואינם רשומים אצל אף תורם
      <small style="color:var(--muted)"> · ${rows.length} חיובים · ${f(ULDATA.total||0)}</small></div>
    <div class="hintxt" style="margin:0 2px 10px">הכסף נכנס בפועל, אבל הוא לא מופיע אצל אף אחד — ולכן גם לא בסיכומים.
      לכל שורה יש הצעה לפי מייל או שם. אשר, בחר תורם אחר, או סמן שאינו שייך לאף אחד.</div>
    <div id="ullist">${groups.map(x=>{
      const dates=x.items.slice(0,8).map(r=>esc(gregLabel(r.iso||r.date))+' · '+f(amtNum(r.amount))).join('<br>');
      const more=x.items.length>8?('<br>ועוד '+(x.items.length-8)):'';
      const s0=x.sugg[0];
      return `<div class="ulg" data-k="${esc(x.k)}">
        <div class="ulhead"><span class="ulnm">${esc((x.first+' '+x.last).trim()||'—')}</span>
          <span class="ulsum">${f(x.sum)}</span>
          <span class="ulwhy">${x.items.length} ${x.items.length===1?'חיוב':'חיובים'}</span></div>
        ${x.email?`<div class="ulmail">${esc(x.email)}</div>`:''}
        <div class="uldates">${dates}${more}</div>
        <div class="ulb">
          <select class="ulpick">${s0?'':'<option value="">— בחר תורם —</option>'}${opts(s0&&s0.id)}</select>
          ${s0?`<span class="ulwhy">הצעה: ${esc(s0.why)}</span>`:'<span class="ulwhy">אין הצעה — בחר ידנית</span>'}
        </div>
        <div class="ulb ulact">
          <button class="btn sm ulok">✓ שייך לתורם הזה</button>
          <button class="btn sm ghost ulskip">✕ לא שייך לאף אחד</button>
        </div></div>`;}).join('')||'<div class="empty">🎉 כל החיובים משויכים</div>'}</div>`;
  wireUnlinked(groups);
}
function wireUnlinked(groups){
  const byk={}; groups.forEach(x=>byk[x.k]=x);
  view.querySelectorAll('.ulg').forEach(el=>{
    const x=byk[el.dataset.k]; if(!x)return;
    const tids=x.items.map(r=>r.tid);
    el.querySelector('.ulok').onclick=async b=>{
      const sel=el.querySelector('.ulpick'), did=sel&&sel.value;
      if(!did){toast('בחר תורם');return;}
      const r=await api('POST','/api/unlinked',{tids,donor_id:+did});
      if(!r||!r.ok){toast('לא נשמר');return;}
      el.classList.add('done');
      el.querySelector('.ulact').innerHTML='<span class="ulwhy">✓ שויך · '+(r.donations||0)+' תרומות נרשמו</span>';
      toast('שויך ✓');
      try{ DB=await api('GET','/api/db'); }catch(e){}   // הכרטיס יתעדכן מיד
    };
    el.querySelector('.ulskip').onclick=async()=>{
      if(!await uiConfirm('לסמן ש-'+((x.first+' '+x.last).trim()||'החיובים האלה')+' אינם שייכים לאף תורם?'))return;
      await api('POST','/api/unlinked',{tids,skip:1});
      el.classList.add('done');
      el.querySelector('.ulact').innerHTML='<span class="ulwhy">✕ סומן שאינו שייך</span>';
      toast('סומן');};
  });
}
async function renderReview(){
  view.innerHTML='<div class="empty">טוען…</div>';
  if(!RVSTAT){ try{RVSTAT=(await api('GET','/api/review')).rows||{};}catch(e){RVSTAT={};} }
  const all=reviewList();
  const closed=x=>['ok','done'].includes((RVSTAT[x.d.id]||{}).status);
  const l=RVSHOW==='all'?all:all.filter(x=>!closed(x));
  const nDone=all.filter(closed).length;
  const by=k=>l.filter(x=>x.kind===k);
  const sec=k=>{const g=by(k); if(!g.length)return '';
    return `<div class="rvsec"><div class="rvsec-t">${RVKIND[k][0]} ${RVKIND[k][1]} — ${g.length}</div>
      <div class="rvsub">${RVKINDSUB[k]||''}</div>
      ${g.map(rvRow).join('')}</div>`;};
  view.innerHTML=`<div class="rvbar noprint">
      <span class="cnt">${l.length} לבדיקה${nDone?(' · '+nDone+' סומנו'):''}</span>
      <button class="btn sm ghost" id="rvall">${RVSHOW==='all'?'הצג רק פתוחים':'הצג גם מה שסומן'}</button>
      ${(RVQUIET||RVASKALL)?`<button class="btn sm ghost" id="rvask">${RVASKALL?'הסתר את מי שנותן כרגיל':('❔ עוד '+RVQUIET+' עם סכום מהייבוא שנותנים כרגיל')}</button>`:''}
      <button class="btn sm" id="rvprint">🖨️ הדפס</button></div>
    <div class="hintxt noprint" style="margin:0 2px 10px">כל שורה: השם, המספרים והשאלה. קבע סטטוס, כתוב הערה אם צריך, ולחץ על השם כדי לפתוח את הכרטיס ולתקן את ההתחייבות בתחתיתו.</div>
    <div id="rvlist">${['short','amount','none','ask'].map(sec).join('')||'<div class="empty">אין מה לבדוק 🎉</div>'}</div>`;
  document.getElementById('rvall').onclick=()=>{RVSHOW=RVSHOW==='all'?'open':'all';renderReview();};
  const ab=document.getElementById('rvask');
  if(ab)ab.onclick=()=>{RVASKALL=!RVASKALL;renderReview();};
  document.getElementById('rvprint').onclick=()=>window.print();
  wireReview();
}
function rvRow(x){
  const st=(RVSTAT[x.d.id]||{}), cur=curSym(x.d);
  const f=n=>cur+Math.round(n).toLocaleString('en-US');
  return `<div class="rvrow ${st.status||''} ${x.kind}" data-id="${x.d.id}">
    <div class="rvhead"><span class="rvnm">${esc((x.d.last+' '+x.d.first).trim())}</span>
      <span class="rvnum">${x.kind==='ask'?('נכנס '+f(x.got)):(f(x.got)+' מתוך '+f(x.exp))}</span></div>
    <div class="rvwhy">${esc(x.why)}</div>
    <div class="rvdet">${x.rows.map(r=>esc(r.what)+' · '+f(r.per)+(x.kind==='ask'?'':' לחודש')).join(' | ')}</div>
    <div class="rvbtns noprint">${RVST.map(([k,t])=>
      `<button class="rvb ${st.status===k?'on '+k:''}" data-st="${k}">${t}</button>`).join('')}</div>
    <input class="rvnote" value="${esc(st.note||'')}" placeholder="הערה — מה סוכם">
    <div class="rvline"></div></div>`;
}
function wireReview(){
  view.querySelectorAll('.rvnm').forEach(b=>b.onclick=()=>{
    const d=DB.find(x=>x.id==b.closest('.rvrow').dataset.id); if(d)openDonor(d);});
  const save=async(id,st,nt)=>{
    RVSTAT[id]=Object.assign({},RVSTAT[id],{status:st,note:nt});
    await api('POST','/api/review',{donor_id:+id,status:st,note:nt});};
  view.querySelectorAll('.rvb').forEach(b=>b.onclick=async()=>{
    const row=b.closest('.rvrow'), id=row.dataset.id;
    const cur=(RVSTAT[id]||{}).status, st=(cur===b.dataset.st)?'':b.dataset.st;
    await save(id, st, (RVSTAT[id]||{}).note||'');
    toast(st?('סומן: '+(RVST.find(x=>x[0]===st)||['',''])[1]):'הסימון בוטל');
    renderReview();});
  view.querySelectorAll('.rvnote').forEach(inp=>inp.onchange=async()=>{
    const id=inp.closest('.rvrow').dataset.id;
    await save(id,(RVSTAT[id]||{}).status||'',inp.value.trim()); toast('נשמר ✓');});
  addMics(view,['.rvnote']);
}
/* ---------- 🧾 תשלומים כפולים ----------
   הייבוא רשם בעבר את אותו תשלום פעמיים כשהוא דווח משני מקורות עם תאריך
   רישום שונה. הבאג תוקן, וכאן רואים מה כבר נרשם כפול ומוחקים שורה אחת. */
let DUPS=null;
let DUPALL=false;
async function renderDups(){
  view.innerHTML='<div class="empty">טוען…</div>';
  if(!DUPS){ try{ DUPS=await api('GET','/api/dups'+(DUPALL?'?all=1':'')); }catch(e){ DUPS={groups:[]}; } }
  const g=DUPS.groups||[];
  const f=n=>'$'+Math.round(n).toLocaleString('en-US');
  const ap=DUPS.approved||0;
  view.innerHTML=`<div class="cnt">${g.length} מקרים של אותו תורם, אותו חודש ואותו סכום —
      סה"כ ${f(DUPS.extra||0)} שנספרו פעמיים</div>
    <div class="hintxt" style="margin:0 2px 10px">אותו תשלום דווח לפעמים בשני קבצים — פעם מהבנק ופעם מחברת הסליקה, עם תאריך רישום שונה — ולכן נרשם פעמיים.
      הבאג תוקן ומעכשיו זה לא יקרה, אבל מה שכבר נרשם נשאר כאן להחלטה שלך.<br>
      <b>אם התורם באמת שילם פעמיים באותו חודש</b> — לחץ <b>✓ תקין</b> והשורה תרד מהרשימה ולא תחזור.
      🗑 מוחק שורה אחת בלבד.
      ${ap?`<br><button class="btn sm ghost" id="dupshow">${DUPALL?'הסתר את המאושרים':('הצג גם '+ap+' שאושרו')}</button>`:''}</div>
    <div id="duplist">${g.map(dupGroup).join('')||'<div class="empty">אין כפילויות 🎉</div>'}</div>`;
  const sb=document.getElementById('dupshow');
  if(sb)sb.onclick=()=>{DUPALL=!DUPALL;DUPS=null;renderDups();};
  wireDups();
}
function dupGroup(x){
  const f=n=>'$'+Math.round(n).toLocaleString('en-US');
  return `<div class="dupg" data-did="${x.donor_id}">
    <div class="dupg-t"><span class="dupopen" style="cursor:pointer;text-decoration:underline dotted">${esc(x.name)}</span>
      <span class="dupamt">${f(x.amount)} × ${x.rows.length}</span>
      <span class="dupmo">${esc(fmtMonth(x.month+'-01')||x.month)}</span></div>
    ${(x.missed||[]).length?`<div class="dupmiss">↩️ אותו סכום לא נגבה ב-${x.missed.map(m=>esc(fmtMonth(m+'-01')||m)).join(', ')} — ייתכן שזו השלמה ולא כפילות</div>`:''}
    <div class="dupok-bar"><button class="dupok${x.ok?' on':''}" data-mo="${esc(x.month)}" data-amt="${x.amount}">${x.ok?'✓ אושר — לחץ לביטול':(x.missed&&x.missed.length?'✓ תקין, זו השלמה':'✓ תקין, שילם פעמיים')}</button></div>
    ${x.rows.map(r=>`<div class="duprow" data-rid="${r.id}">
      <span class="dupd">${esc(gregLabel(r.date)||r.date)}</span>
      <span class="dupsrc">${esc(r.method||'')}${r.method&&r.note?' · ':''}${esc(String(r.note||'').slice(0,60))}</span>
      <button class="dupdel">🗑 מחק שורה</button></div>`).join('')}</div>`;
}
function wireDups(){
  view.querySelectorAll('.dupopen').forEach(b=>b.onclick=()=>{
    const d=DB.find(x=>x.id==b.closest('.dupg').dataset.did); if(d)openDonor(d);});
  // "בדקתי, זה תקין" — הקבוצה יורדת מהרשימה ולא חוזרת
  view.querySelectorAll('.dupok').forEach(b=>b.onclick=async()=>{
    const g=b.closest('.dupg'); const on=b.classList.contains('on');
    b.disabled=true;
    const r=await api('POST','/api/dups/ok',{donor_id:+g.dataset.did,
      month:b.dataset.mo, amount:+b.dataset.amt, undo:on?1:0});
    if(!r||!r.ok){b.disabled=false;toast('לא נשמר');return;}
    toast(on?'האישור בוטל':'אושר ✓ — ירד מהרשימה');
    DUPS=null; renderDups();});
  view.querySelectorAll('.duprow').forEach(row=>{
    const b=row.querySelector('.dupdel');
    b.onclick=async()=>{
      const left=[...row.parentElement.querySelectorAll('.duprow:not(.gone)')].length;
      if(left<2){toast('נשארה שורה אחת — אין מה למחוק');return;}
      if(!await uiConfirm('למחוק את שורת התשלום הזו?'))return;
      b.disabled=true;
      const r=await api('DELETE','/api/donation/'+row.dataset.rid);
      if(!r||!r.ok){b.disabled=false;toast('המחיקה נכשלה');return;}
      row.classList.add('gone'); b.textContent='נמחק ✓';
      toast('נמחק ✓'); DUPS=null; await load(); renderDups();};
  });
}
async function renderOld(){
  view.innerHTML='<div class="empty">טוען…</div>';
  if(!OLD){ try{ OLD=await api('GET','/api/inactive?since='+encodeURIComponent(oldSince)); }
            catch(e){ OLD={donors:[]}; } }
  const l=OLD.donors||[];
  const seen=l.filter(d=>d.mail_seen&&d.mail_seen!=='none').length;
  const chk=l.filter(d=>d.mail_seen).length;
  view.innerHTML=`<div class="oldbar">
      <span>לא נכנס כסף מאז</span>
      <input type="date" id="oldsince" value="${esc(oldSince)}">
      <button class="btn sm ghost" id="oldmail">🔎 חפש אותם במייל</button>
      <span class="hintxt" id="oldstat">${chk?(chk+' נבדקו · '+seen+' נמצאו במייל'):''}</span>
    </div>
    <div class="cnt">${l.length} תורמים בלי שום כסף מאז ${esc(oldSince)}</div>
    <div class="hintxt" style="margin:0 2px 9px">התרומות במערכת מתחילות מינואר 2026, ולכן הבדיקה במייל היא הראיה לשנים שלפני.
      🔎 החיפוש עובר על <b>הקבלות מספקי הסליקה</b> (אוטרייז, פייפאל, נדרים, דונורס פאנד) ועל <b>סיכומי בנק ווסט היומיים</b>, ומחפש בהם את האימייל של התורם ואת שמו באנגלית.
      מייל שהתורם שלח אלינו <b>אינו</b> נחשב ראיה — רק כסף.</div>
    <div id="oldlist">${l.map(oldRow).join('')||'<div class="empty">אין תורמים כאלה 🎉</div>'}</div>`;
  document.getElementById('oldsince').onchange=e=>{oldSince=e.target.value||'2024-01-01';OLD=null;renderOld();};
  const mb=document.getElementById('oldmail'); if(mb)mb.onclick=()=>runMailCheck(mb);
  wireOldRows();
}
function oldRow(d){
  const t=[];
  if(d.kv)t.push('<span class="oldtag">🕯️ קוויטל</span>');
  if(d.av)t.push('<span class="oldtag">🤝 '+d.av+' אברכים</span>');
  if(d.pl)t.push('<span class="oldtag">🎯 התחייבות</span>');
  if(d.files)t.push('<span class="oldtag">📄 מסמכים</span>');
  if(d.amount)t.push('<span class="oldtag">קבוע '+esc(d.amount)+'</span>');
  if(d.last_money)t.push('<span class="oldtag">כסף אחרון '+esc(String(d.last_money).slice(0,7))+'</span>');
  if(!d.rows)t.push('<span class="oldtag">אין שום שורת כסף בכרטיס</span>');
  if(d.twin)t.push('<span class="oldtag ok">🔀 כרטיס כפול? '+esc(d.twin.name)+' — כסף עד '+esc(d.twin.last)+'</span>');
  const rc=d.mail_seen&&d.mail_seen!=='none';
  if(rc)t.push('<span class="oldtag ok">🧾 נמצא בקבלה / בסיכום בנק '+esc(d.mail_seen)+' — תרם!</span>');
  else if(d.mail_seen)t.push('<span class="oldtag warn">📭 אין קבלה ואין אותו בסיכומי הבנק</span>');
  return `<div class="oldrow" data-id="${d.id}">
    <div class="oldmain oldopen" title="פתח את הכרטיס"><div class="oldnm">${esc(d.name)} ${d.english?('<small>'+esc(d.english)+'</small>'):''}</div>
      <div class="oldsub">${esc(d.email||'')}${d.email&&d.phone?' · ':''}${esc(d.phone||'')}</div>
      ${t.length?('<div class="oldtags">'+t.join('')+'</div>'):''}</div>
    <button class="oldkeep">להשאיר</button>
    <button class="olddel">🗑 מחק</button></div>`;
}
function wireOldRows(){
  const box=document.getElementById('oldlist'); if(!box)return;
  const drop=id=>{OLD.donors=(OLD.donors||[]).filter(x=>x.id!=id);
    const c=document.querySelector('.cnt'); if(c)c.textContent=OLD.donors.length+' תורמים בלי שום כסף מאז '+oldSince;};
  box.querySelectorAll('.oldrow').forEach(row=>{
    const id=+row.dataset.id;
    // מאיר: "כשאני לוחץ על שם תורם זה לא מעביר אותי לכרטיס שלו". הלחיצה
    // נכשלה בשתיקה כשהכרטיס לא היה ברשימה שנטענה. עכשיו לוחצים על כל
    // אזור השם, ואם הכרטיס חסר — נטען מחדש, ורק אז נאמר שהוא לא נמצא.
    row.querySelector('.oldopen').onclick=async()=>{
      let d=DB.find(x=>x.id===id);
      if(!d){ await load(); d=DB.find(x=>x.id===id); }
      if(d)openDonor(d); else toast('הכרטיס לא נמצא — רענן את הדף');};
    row.querySelector('.oldkeep').onclick=async()=>{
      await api('PUT','/api/donor/'+id,{keep_old:1});
      row.remove(); drop(id); toast('נשמר — לא יופיע יותר ברשימה');};
    row.querySelector('.olddel').onclick=async()=>{
      const nm=row.querySelector('.oldnm').textContent.trim();
      if(!await uiConfirm('למחוק לצמיתות את '+nm+'?\nכל הקוויטל, ההערות והמסמכים שלו יימחקו איתו.'))return;
      const r=await api('DELETE','/api/donor/'+id);
      if(!r||r.error){toast('לא נמחק');return;}
      row.classList.add('gone'); drop(id);
      DB=DB.filter(x=>x.id!==id);
      setTimeout(()=>row.remove(),350); toast('נמחק');};
  });
}
async function runMailCheck(btn){
  const lbl=btn.textContent, set=t=>btn.textContent=t;
  btn.disabled=true; set('מתחיל…');
  const r=await api('POST','/api/inactive/mailcheck',{since:oldSince});
  if(!r||!r.ok){btn.disabled=false;set(lbl);
    toast(r&&r.error==='not_configured'?'המייל לא מוגדר בשרת (GMAIL_USER / GMAIL_APP_PASSWORD)':'שגיאה');return;}
  for(let i=0;i<1800;i++){
    await new Promise(res=>setTimeout(res,2000));
    let st;try{st=await api('GET','/api/inactive/mailcheck/status');}catch(e){continue;}
    if(!st)continue;
    if(st.running){set('בודק… '+(st.done||0)+'/'+(st.total||0));continue;}
    btn.disabled=false;set(lbl);
    if(st.error){toast('שגיאת חיפוש: '+st.error);return;}
    OLD=null; await renderOld();
    toast('הבדיקה הסתיימה — '+(st.hit||0)+' נמצאו במייל');return;
  }
  btn.disabled=false;set(lbl); toast('הבדיקה עדיין רצה ברקע');
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
// מאיר: "תעשה לי השוואה מה רשום באקסל שלנו ומה מופיע במערכת, ותבנה לי
// טבלה מסודרת של ההבדלים שאראה מי לא רשמנו". מדביקים כאן שתי עמודות
// מהאקסל (שם וסכום), וההשוואה רצה מול מה שבאמת נכנס במערכת.
function campParse(txt){
  const out=[];
  String(txt||'').split(/\r?\n/).forEach(ln=>{
    if(!ln.trim())return;
    // שם וסכום מופרדים בטאב / פסיק / נקודה־פסיק, או סכום בסוף השורה
    let m=ln.split(/\t|;|,(?=[^,]*$)/);
    let name,amt;
    if(m.length>=2){ name=m.slice(0,-1).join(' '); amt=m[m.length-1]; }
    else { const g=ln.match(/^(.*?)[\s.\u2013-]+([\d,.]+)\s*$/); if(!g)return; name=g[1]; amt=g[2]; }
    name=String(name).replace(/["\u05f4]/g,'"').trim();
    if(!name)return;
    out.push({name:name, amt:amtNum(amt)});
  });
  return out;
}
// התאמת שם מהאקסל לתורם — עברית או אנגלית, בלי תלות בסדר המילים
function campFind(name){
  const q=norm(name), toks=q.split(' ').filter(t=>t.length>=2);
  const lat=/[a-zA-Z]/.test(name), ln=name.toLowerCase().trim();
  let hit=null;
  for(const d of (DB||[])){
    if(lat){
      const e=String(d.english||'').toLowerCase().trim();
      const b=String(d.business||'').toLowerCase().trim();
      if(e&&(e===ln||(e.split(' ').every(w=>ln.includes(w))&&ln.split(' ').every(w=>e.includes(w))))){hit=d;break;}
      if(b&&b===ln){hit=d;break;}
    }
    const h=norm((d.last||'')+' '+(d.first||''));
    if(h&&toks.length&&toks.every(t=>h.includes(t))){hit=d;break;}
  }
  if(hit)return hit;
  // ניסיון שני — לפי צליל בעברית (איות שונה)
  const f=fzHe(q);
  if(f&&f.length>=4)for(const d of (DB||[])){
    const hf=fzHe(norm((d.last||'')+' '+(d.first||'')));
    if(hf&&hf.includes(f))return d;
  }
  return null;
}
function campCompare(rows){
  const rs=document.getElementById('remsheet'), remov=document.getElementById('remov');
  const cur=curSym({});
  rs.innerHTML=`<button class="x" id="rx">✕</button>
    <h2>🔍 השוואה מול האקסל — ${esc(campSel)}</h2>
    <div class="hintxt">העתק מהאקסל שתי עמודות — שם וסכום — והדבק כאן. אפשר גם שם ואחריו הסכום באותה שורה.</div>
    <textarea id="cmp_in" rows="8" placeholder="לאם זאב\t1100&#10;Elchanan Abramowitz\t1100&#10;קאהן אלון 360"></textarea>
    <button class="btn" id="cmp_go" style="width:100%;margin-top:6px">📊 השווה</button>
    <div id="cmp_out"></div>`;
  remov.classList.add('show');
  document.getElementById('rx').onclick=()=>remov.classList.remove('show');
  document.getElementById('cmp_go').onclick=()=>{
    const xl=campParse(document.getElementById('cmp_in').value);
    if(!xl.length){document.getElementById('cmp_out').innerHTML='<div class="hintxt">לא זיהיתי שורות. ודא שיש שם וסכום בכל שורה.</div>';return;}
    // סכום לכל תורם במערכת
    const sys={};
    rows.forEach(r=>{sys[r.id]=sys[r.id]||{name:r.name,amt:0,cur:r.cur};sys[r.id].amt+=r.amt;});
    const miss=[], diff=[], extra=[], seen=new Set();
    xl.forEach(x=>{
      const d=campFind(x.name);
      if(!d){miss.push({name:x.name,amt:x.amt,nocard:1});return;}
      seen.add(d.id);
      const s=sys[d.id];
      if(!s)miss.push({name:(d.last+' '+d.first).trim(),amt:x.amt,id:d.id});
      else if(Math.round(s.amt)!==Math.round(x.amt))
        diff.push({name:s.name,id:d.id,xl:x.amt,sy:s.amt,cur:s.cur});
    });
    Object.keys(sys).forEach(id=>{if(!seen.has(+id))extra.push({id:+id,...sys[id]});});
    const f=(v,c)=>(c||'$')+Math.round(v).toLocaleString('en-US');
    const tbl=(ttl,cls,list,cols)=>list.length?`<div class="cmphd ${cls}">${ttl} — ${list.length}</div>
      <div class="camptbl">${list.map((r,i)=>`<div class="camprow2"><span class="c1">${i+1}</span>
        <span class="c2">${r.id?`<a class="avhold" data-did="${r.id}">${esc(r.name)}</a>`:esc(r.name)}${r.nocard?' <small class="cmpno">אין כרטיס במערכת</small>':''}</span>
        ${cols(r,f)}</div>`).join('')}</div>`:'';
    document.getElementById('cmp_out').innerHTML=
      `<div class="cmpsum">באקסל ${xl.length} שורות · במערכת ${Object.keys(sys).length} תורמים</div>`
      + tbl('🔴 באקסל ולא רשום אצלנו','bad',miss,(r,f)=>`<span class="c3"><b>${f(r.amt)}</b></span><span class="c4">באקסל</span><span class="c5"></span>`)
      + tbl('🟡 סכום שונה','warn',diff,(r,f)=>`<span class="c3"><b>${f(r.xl,r.cur)}</b></span><span class="c4">במערכת ${f(r.sy,r.cur)}</span><span class="c5"></span>`)
      + tbl('⚪ במערכת ולא באקסל','muted',extra,(r,f)=>`<span class="c3"><b>${f(r.amt,r.cur)}</b></span><span class="c4">במערכת</span><span class="c5"></span>`)
      + (miss.length||diff.length||extra.length?'':'<div class="cmphd ok">✅ הכל תואם — אין הבדלים</div>');
    rs.querySelectorAll('.avhold').forEach(a=>a.onclick=()=>{const d=DB.find(x=>x.id==a.dataset.did);if(d){remov.classList.remove('show');openDonor(d);}});
  };
}
let campSel='';        // הייעוד שנבחר לדוח
// דוח קמפיין — מאיר: "איך אני מוציא דוח כמה ומי נתן לקמפיין מסוים,
// למשל קמחא דפסחא תשפ\"ו". הדוח נבנה מהכסף שבאמת נכנס (התרומות), ולצדו
// מי התחייב וטרם נתן — כדי שיהיה ברור למי עוד לפנות.
function campRows(cat){
  const out=[];
  DB.forEach(d=>(d.donations||[]).forEach(x=>{
    if(String(x.category||'').trim()!==cat)return;
    out.push({id:d.id,name:(d.last+' '+d.first).trim(),eng:d.english||'',
      amt:amtNum(x.amount),cur:(String(x.cur||'').trim()==='₪'?'₪':(String(x.cur||'').trim()==='$'?'$':curSym(d))),
      date:x.date||'',method:x.method||'',phone:splitPhones(d.phone)[0]||''});}));
  return out.sort((a,b)=>b.amt-a.amt||a.name.localeCompare(b.name,'he'));
}
// מי התחייב לייעוד הזה ועדיין לא נכנס ממנו כסף
function campOwes(cat){
  const paid=new Set(campRows(cat).map(r=>r.id));
  const out=[];
  DB.forEach(d=>(d.pledges||[]).forEach(p=>{
    if(String(p.category||'').trim()!==cat||paid.has(d.id))return;
    if(String(p.status||'')==='נתן')return;
    out.push({id:d.id,name:(d.last+' '+d.first).trim(),amt:amtNum(p.amount),
      cur:curSym(d),phone:splitPhones(d.phone)[0]||''});}));
  return out.sort((a,b)=>b.amt-a.amt);
}
function campList(){
  const m={};
  DB.forEach(d=>(d.donations||[]).forEach(x=>{const c=String(x.category||'').trim();
    if(c)m[c]=(m[c]||0)+amtNum(x.amount);}));
  (CAMPAIGNS||[]).forEach(c=>{c=String(c||'').trim(); if(c&&!(c in m))m[c]=0;});
  DB.forEach(d=>(d.pledges||[]).forEach(p=>{const c=String(p.category||'').trim();
    if(c&&!(c in m))m[c]=0;}));
  return Object.keys(m).sort((a,b)=>m[b]-m[a]||a.localeCompare(b,'he'));
}
function renderCamp(){
  chips.innerHTML='';
  const cats=campList();
  if(!campSel||cats.indexOf(campSel)<0)campSel=cats[0]||'';
  const rows=campSel?campRows(campSel):[], owes=campSel?campOwes(campSel):[];
  const byCur={}; rows.forEach(r=>{byCur[r.cur]=(byCur[r.cur]||0)+r.amt;});
  const tot=Object.keys(byCur).map(k=>k+Math.round(byCur[k]).toLocaleString('en-US')).join(' + ')||'—';
  const owesum={}; owes.forEach(r=>{if(r.amt)owesum[r.cur]=(owesum[r.cur]||0)+r.amt;});
  const owetot=Object.keys(owesum).map(k=>k+Math.round(owesum[k]).toLocaleString('en-US')).join(' + ');
  const donors=new Set(rows.map(r=>r.id)).size;
  view.innerHTML=`<div class="avbar noprint">
      <select id="campsel" class="avsortsel">${cats.map(c=>`<option value="${esc(c)}"${c===campSel?' selected':''}>${esc(c)}</option>`).join('')}</select>
      <button class="btn sm" id="campcopy">📋 העתק</button>
      <button class="btn sm ghost" id="campcsv">⬇️ אקסל</button>
      <button class="btn sm" id="campcmp">🔍 השוואה מול אקסל</button>
      <button class="print" onclick="window.print()">הדפס 🖨️</button></div>
    <div class="camphd"><h3>🎯 ${esc(campSel||'—')}</h3>
      <div class="campsum"><span><b>${tot}</b> נכנס</span><span><b>${donors}</b> תורמים</span>
        <span><b>${rows.length}</b> תשלומים</span>${owetot?`<span class="campowe">🔴 ${owetot} התחייבו וטרם נתנו</span>`:''}</div></div>
    <div class="camptbl">
      <div class="camprow2 head"><span class="c1">#</span><span class="c2">תורם</span><span class="c3">סכום</span><span class="c4">תאריך</span><span class="c5">איך</span></div>
      ${rows.map((r,i)=>`<div class="camprow2"><span class="c1">${i+1}</span>
        <span class="c2"><a class="avhold" data-did="${r.id}">${esc(r.name)}</a>${r.eng?`<small class="cen">${esc(r.eng)}</small>`:''}</span>
        <span class="c3"><b>${r.cur}${Math.round(r.amt).toLocaleString('en-US')}</b></span>
        <span class="c4">${esc(r.date?gregLabel(r.date):'')}</span>
        <span class="c5">${r.method?(chBadgeRaw(r.method)||esc(chLabel(r.method))):''}</span></div>`).join('')
        ||'<div class="empty">עדיין לא נכנס כסף לייעוד הזה</div>'}
    </div>
    ${owes.length?`<div class="camphd" style="margin-top:14px"><h3>🔴 התחייבו וטרם נתנו — ${owes.length}</h3></div>
      <div class="camptbl">${owes.map((r,i)=>`<div class="camprow2 owe"><span class="c1">${i+1}</span>
        <span class="c2"><a class="avhold" data-did="${r.id}">${esc(r.name)}</a></span>
        <span class="c3">${r.amt?('<b>'+r.cur+Math.round(r.amt).toLocaleString('en-US')+'</b>'):'—'}</span>
        <span class="c4" dir="ltr">${esc(r.phone)}</span><span class="c5"></span></div>`).join('')}</div>`:''}`;
  const sel=document.getElementById('campsel');
  if(sel)sel.onchange=()=>{campSel=sel.value;renderCamp();};
  const cmp=document.getElementById('campcmp');
  if(cmp)cmp.onclick=()=>campCompare(rows);
  view.querySelectorAll('.avhold').forEach(a=>a.onclick=()=>{const d=DB.find(x=>x.id==a.dataset.did);if(d)openDonor(d);});
  const txt=()=>[campSel,tot+' · '+donors+' תורמים','']
    .concat(rows.map((r,i)=>(i+1)+'. '+r.name+' — '+r.cur+Math.round(r.amt).toLocaleString('en-US')
      +(r.date?(' · '+gregLabel(r.date)):''))).join('\n');
  const cp=document.getElementById('campcopy');
  if(cp)cp.onclick=async()=>{try{await navigator.clipboard.writeText(txt());toast('הועתק ✓');}catch(e){toast('לא הצלחתי להעתיק');}};
  const cs=document.getElementById('campcsv');
  if(cs)cs.onclick=()=>{
    const q=v=>'"'+String(v==null?'':v).replace(/"/g,'""')+'"';
    const csv=['שם,שם באנגלית,סכום,מטבע,תאריך,אמצעי,טלפון']
      .concat(rows.map(r=>[r.name,r.eng,Math.round(r.amt),r.cur,r.date,chLabel(r.method),r.phone].map(q).join(',')))
      .join('\n');
    const a=document.createElement('a');
    a.href='data:text/csv;charset=utf-8,%EF%BB%BF'+encodeURIComponent(csv);
    a.download=campSel.replace(/[\\/:*?"<>|]/g,'-')+'.csv';
    document.body.appendChild(a);a.click();a.remove();};
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
  // פתוחות — לפי תאריך היעד הקרוב. שבוצעו — האחרונות שנעשו למעלה.
  if(showDone)all.sort((a,b)=>(b.done_at||b.done_date||b.due_date||'').localeCompare(a.done_at||a.done_date||a.due_date||''));
  else all.sort((a,b)=>(a.due_date||'9999').localeCompare(b.due_date||'9999'));
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
    <div class="list">${pdebts.map(x=>`<div class="rowc"><div class="rowmain" data-did="${x.d.id}"><div class="nm">${esc(x.d.last)} <small>${esc(x.d.first)}</small></div><div class="miss">${esc(DAYKIND[x.p.kind]||'🌙 פרנס')}${x.p.date_text?(' · '+esc(x.p.date_text)):''}${x.p.hyear?(' '+esc(x.p.hyear)):''}${x.p.amount?(' · '+pCur(x.p,x.d)+esc(x.p.amount)):''} — <b style="color:var(--no)">טרם נגבה</b></div>${contactBtns(x.d)}</div><div class="meta"><button class="btn sm pcollect" data-pid="${x.p.id}" data-did="${x.d.id}">✓ נגבה</button></div></div>`).join('')}</div>`:'';
  const renews=[]; DB.forEach(d=>{const r=renewInfo(d);if(r&&matchQ(d.last+' '+d.first))renews.push({d,r});});
  renews.sort((a,b)=>(a.r.date||'').localeCompare(b.r.date||''));
  const renewSec=renews.length?`<div class="misshead" style="margin-top:10px">🔴 חידוש שותפות יש"ז מתקרב (${renews.length})</div>
    <div class="list">${renews.map(x=>`<div class="rowc"><div class="rowmain" data-did="${x.d.id}"><div class="nm">${esc(x.d.last)} <small>${esc(x.d.first)}</small></div><div class="miss">🤝 ${x.r.avreich?esc(x.r.avreich)+' · ':''}${x.r.days<0?'עברה שנה מההתחלה':('סיום שנה '+fmtGreg(x.r.date))}${x.r.days>=0?(' · בעוד '+x.r.days+' ימים'):''} — <b style="color:var(--no)">לחדש + תעודה חדשה</b></div>${contactBtns(x.d)}</div><div class="meta"><button class="btn sm avopen2" data-did="${x.d.id}">כרטיס</button></div></div>`).join('')}</div>`:'';
  view.innerHTML=`<div class="whobar">${WHO.map(([w,l])=>`<button class="whochip ${taskWho===w?'on':''}" data-w="${w}">${l} <b>${cnt(w)}</b></button>`).join('')}</div>
    <div class="addrow" style="margin:0 2px 8px"><button class="btn sm ghost" id="tk_mailsync" style="width:100%">📥 משוך מיילים (נכנסים + ששלחנו) ותייק אצל התורמים</button></div>
    <div class="addrow" style="margin:0 2px 8px"><button class="btn sm ghost" id="tk_anetsync" style="width:100%">💳 משוך חיובים מאוטרייז עכשיו</button></div>${renewSec}${debtSec}
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
    <div class="cnt" style="display:flex;justify-content:space-between;align-items:center;gap:8px"><span>${all.length} ${showDone?'משימות שבוצעו':'משימות · לפי תאריך קרוב'}</span><button class="btn sm ghost" id="toggledone">${showDone?'🔔 חזרה לפתוחות':'✓ הצג שבוצעו'}</button></div>
    ${showDone?'<div class="submuted">"↩️ החזר לפתוחות" מבטל את הווי והמשימה חוזרת לרשימה — גם הרישום בכרטיס התורם נמחק. "✏️ ערוך" משנה את הטקסט בלי לבטל את הביצוע.</div>':''}<div class="list">${all.map((t,i)=>{
    const over=t.due_date&&t.due_date<today, icon=kindLabel(t.kind).split(' ')[0], g=gcalLink(t,t.donor||t.note||'משימה');
    const isParnes=t.kind==='parnes'&&taskParnes(t);
    return `<div class="rowc taskrow ${showDone?'donerow':''}" data-i="${i}"><button class="tdone ${showDone?'restore':''}" data-done="${i}" title="${showDone?'החזר לפתוחות':'בוצע'}">${showDone?'↩️ החזר לפתוחות':'✓'}</button>
      <div><div class="nm">${icon} ${esc(t.donor||t.note||'משימה')}</div>${isCustKind(t.kind)?`<div class="miss2">📌 ${esc(custKind(t.kind))}</div>`:''}${t.donor&&t.note?`<div class="miss2">${esc(t.note)}</div>`:''}${t.dref?contactBtns(t.dref):''}</div>
      <div class="meta"><span class="tdate ${showDone?'':(over?'over':'')}">${showDone?('✓ '+esc(t.done_date||t.due_date||'—')+(hhmm(t.done_at)?(' '+hhmm(t.done_at)):'')+' · ע"י '+esc(t.done_by||whoName(t))):esc(t.due_date||'—')}</span>
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
  }).join('')||`<div class="empty">${showDone?'עדיין לא סומנה אף משימה כבוצעה':'אין משימות פתוחות 🎉'}</div>`}</div>`;
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
  view.querySelectorAll('.tsave').forEach(b=>b.onclick=async()=>{const t=all[b.dataset.i];const note=view.querySelector('.tnote[data-i="'+b.dataset.i+'"]').value.trim(),date=view.querySelector('.tdate2[data-i="'+b.dataset.i+'"]').value;const whoEl=view.querySelector('.twho[data-i="'+b.dataset.i+'"]');const who=whoEl?whoEl.value:(t.assignee||'');const kEl=view.querySelector('.tkindsel[data-i="'+b.dataset.i+'"]');const kind=kEl?(await kindValue(kEl)):(t.kind||'other');if(!kind)return;const rsp=await api('PUT','/api/task/'+t.id,{note:note,kind:kind,due_date:date,assignee:who});t.note=note;t.kind=kind;t.due_date=date;t.assignee=who;const rec=t.dref?(t.dref.tasks||[]).find(x=>x.id===t.id):GTASKS.find(x=>x.id===t.id);if(rec){rec.note=note;rec.kind=kind;rec.due_date=date;rec.assignee=who;}if(rsp&&rsp.contact)putLog(t.dref,rsp.contact);toast(who==='אהרן'?'הועבר לאהרן ✓':'נשמר ✓');render();});
  view.querySelectorAll('.tdel').forEach(b=>b.onclick=async()=>{const t=all[b.dataset.i];if(!await uiConfirm('למחוק את המשימה?'))return;await api('DELETE','/api/task/'+t.id);if(t.dref)t.dref.tasks=(t.dref.tasks||[]).filter(x=>x.id!==t.id);else GTASKS=GTASKS.filter(x=>x.id!==t.id);toast('נמחק');render();checkReminders();});
  view.querySelectorAll('.tparnes').forEach(b=>b.onclick=()=>{const t=all[b.dataset.i],p=taskParnes(t);if(!p){toast('לא נמצא פרנס');return;}tab='parnes';pyKind=p.kind||'parnes';pyMonth=p.month;pyDay=+p.day;flt='';plaque=null;document.querySelectorAll('.tab').forEach(x=>x.classList.toggle('on',x.dataset.tab==='parnes'));render();});
  // משימה חדשה — חיפוש ובחירת תורם
  let ntChosen=null;
  const ntq=document.getElementById('nt_q'),ntres=document.getElementById('nt_res'),ntch=document.getElementById('nt_chosen');
  ntq.oninput=()=>{const s=norm(ntq.value);if(!s){ntres.innerHTML='';ntChosen=null;ntch.style.display='none';return;}
    const m=DB.filter(d=>norm(d.last+' '+d.first+' '+d.english+' '+d.phone+' '+d.business).includes(s)).slice(0,8);
    ntres.innerHTML=m.map(d=>`<div class="dpr" data-id="${d.id}">${esc(d.last)} ${esc(d.first)}${d.tier==='יששכר_זבולון'?' · יש"ז':''}${d.phone?(' · '+esc(splitPhones(d.phone)[0])):''}</div>`).join('')||'<div class="dpr" style="color:var(--muted)">אין תוצאות</div>';
    ntres.querySelectorAll('.dpr[data-id]').forEach(x=>x.onclick=()=>{ntChosen=DB.find(y=>y.id==x.dataset.id);ntch.style.display='block';ntch.innerHTML='✓ נבחר: <b>'+esc((ntChosen.last+' '+ntChosen.first).trim())+'</b>';ntres.innerHTML='';ntq.value=(ntChosen.last+' '+ntChosen.first).trim();});};
  const an=document.getElementById('tk_anetsync');
  if(an)an.onclick=async()=>{
    an.disabled=true; const old=an.textContent; an.textContent='מושך מאוטרייז…';
    const r=await api('POST','/api/authorize/sync',{days:10});
    an.disabled=false; an.textContent=old;
    if(r&&r.ok){const x=r.result||{};
      toast('נבדקו '+(x['נבדקו']||0)+' · נוספו '+(x['נוספו']||0)+' · שויכו '+(x['שויכו']||0));
      await load(); render();}
    else if(r&&r.error==='not_configured')
      toast('החיבור לאוטרייז עדיין לא הוגדר — צריך להזין את המפתחות ב-Render');
    else toast('לא הצליח: '+((r&&r.error)||'שגיאה'));};
  const tms=document.getElementById('tk_mailsync');
  if(tms)tms.onclick=()=>runMailSync(tms);
  const ntF=pendFiles('nt_files','nt_file');
  wireKindSel(document.getElementById('nt_kind'));
  addMic(document.getElementById('nt_note'));
  addMics(view,['.tnote']);
  document.getElementById('nt_add').onclick=async ev=>{
    const btn=ev.currentTarget; if(btn.disabled)return;
    const kind=await kindValue(document.getElementById('nt_kind'));if(!kind)return;
    const date=document.getElementById('nt_date').value,note=document.getElementById('nt_note').value.trim();
    const whoEl=document.getElementById('nt_who');
    const who=whoEl?whoEl.value:inWho;   // ברירת המחדל לפי החלון, וניתן לשנות כאן
    if(!note&&!ntChosen){toast('כתוב מה צריך לעשות');return;}
    if(!date){toast('בחר תאריך');return;}
    btn.disabled=true;                   // לחיצה כפולה יצרה שתי משימות זהות
    const body={due_date:date,kind:kind,note:note,assignee:who};
    if(ntChosen)body.donor_id=ntChosen.id;
    const r=await api('POST','/api/task',body);
    if(r&&r.existing){btn.disabled=false;toast('המשימה כבר קיימת');render();return;}
    const rec={id:r.id,donor_id:ntChosen?ntChosen.id:null,due_date:date,kind:kind,note:note,assignee:who,done:0};
    if(ntChosen){ntChosen.tasks=ntChosen.tasks||[];ntChosen.tasks.push(rec);}else{GTASKS.push(rec);}
    if(ntF.arr.length){toast('מעלה קבצים…');for(const f of ntF.arr)await uploadBlob('task',r.id,f);ntF.reset();await load();}
    toast('המשימה נוספה ✓'+(who?' — '+who:''));render();checkReminders();};
  view.querySelectorAll('.ttup').forEach(inp=>inp.onchange=()=>uploadFile('task',+inp.dataset.id,inp,load));
  view.querySelectorAll('.teditpanel .fdel').forEach(b=>b.onclick=async()=>{await api('DELETE','/api/file/'+b.dataset.fid);load();});
  view.querySelectorAll('.taskrow').forEach(r=>r.onclick=e=>{if(e.target.classList.contains('tdone')||e.target.classList.contains('gcal'))return;const t=all[r.dataset.i];if(t.dref)openDonor(t.dref);});
  const setDone=(t,v)=>setTaskDone(t,v,t.dref);
  view.querySelectorAll('.tdone').forEach(b=>b.onclick=async e=>{e.stopPropagation();const t=all[b.dataset.done];
    if(showDone){await setDone(t,0);toast('הוחזר לפתוחות ✓');render();checkReminders();}
    else{await setDone(t,1);render();checkReminders();toastUndo('בוצע ✓ · נרשם בכרטיס',async()=>{await setDone(t,0);render();checkReminders();});}
  });
  const tgd=document.getElementById('toggledone');if(tgd)tgd.onclick=()=>{showDone=!showDone;render();};
}

/* ---------- הפקדות שלא זוהו (צ'ייס / זל) ---------- */
// כל שם מפקיד מופיע פעם אחת עם כל ההפקדות שלו. משייכים לתורם — וכל השורות
// שלו נסגרות יחד, וגם כל מה שיגיע בעתיד באותו שם.
let DEPS=null, depOpen=null, depKind='bank';
async function renderDeposits(){
  chips.innerHTML='';
  view.innerHTML='<div class="cnt">טוען הפקדות…</div>';
  try{ DEPS=await api('GET','/api/deposits'); }catch(e){ DEPS={rows:[]}; }
  const all=(DEPS&&DEPS.rows)||[];
  const kind=all.filter(x=>(x.kind||'bank')===depKind);
  const rows=kind.filter(x=>matchQ(x.name));
  const f=n=>'$'+Math.round(n).toLocaleString('en-US');
  const isBank=depKind==='bank';
  view.innerHTML=`<div class="misshead">💵 ${isBank?"הפקדות שלא זוהו — צ'ייס / זל":'חיובי אשראי שלא זוהו — אוטרייז / בנק ווסט'}</div>
    <div class="submuted">כל שם מופיע פעם אחת. שייך אותו לתורם — וכל השורות שלו ייכנסו לכרטיס,
      וגם כל מה שיגיע בעתיד באותו שם. מה שלא רלוונטי — "לא רלוונטי", ולא תישאל עליו שוב.</div>
    <div class="deptabs">
      <button class="dtab ${isBank?'on':''}" data-kind="bank">🏦 בנק — צ'ייס / זל <b>${DEPS.names||0}</b></button>
      <button class="dtab ${isBank?'':'on'}" data-kind="card">💳 אשראי <b>${DEPS.cards||0}</b></button></div>
    <div class="avstat">💵 <b>${kind.length}</b> שמות · <b>${kind.reduce((s,x)=>s+x.n,0)}</b> ${isBank?'הפקדות':'חיובים'} · <b>${f(kind.reduce((s,x)=>s+x.total,0))}</b>${rows.length!==kind.length?` · מוצגים ${rows.length}`:''}</div>
    <button class="btn ghost" id="depback" style="margin:8px 2px">→ חזרה לחיובים</button>
    <div class="list">${rows.map(x=>`<div class="depcard" data-k="${esc(x.key)}">
      <div class="depnm" dir="ltr">${esc(x.name)}</div>
      <div class="depmeta">${x.n} ${x.n===1?'הפקדה':'הפקדות'} · <b>${f(x.total)}</b>${x.dates.length?(' · '+esc(x.dates[0])+(x.dates.length>1?(' – '+esc(x.dates[x.dates.length-1])):'')):''}${x.src?(' · '+esc(x.src)):''}</div>
      ${x.note?`<div class="depnote" dir="ltr">${esc(x.note)}</div>`:''}
      ${x.email||x.phone?`<div class="depmeta">${esc(x.email||'')}${x.email&&x.phone?' · ':''}${esc(x.phone||'')}</div>`:''}
      <div class="deprow"><button class="btn sm depmatch" data-k="${esc(x.key)}">🔗 שייך לתורם</button>
        <button class="btn sm ghost depnew" data-k="${esc(x.key)}">➕ תורם חדש</button>
        <button class="del depign" data-k="${esc(x.key)}">🗑 לא רלוונטי</button></div>
      ${depOpen===x.key?`<div class="depbox">
        <input class="dep_q" data-k="${esc(x.key)}" placeholder="חפש תורם קיים…" autocomplete="off">
        <div class="dpres dep_res" data-k="${esc(x.key)}"></div></div>`:''}
    </div>`).join('')||'<div class="empty">אין הפקדות שממתינות לזיהוי 🎉</div>'}</div>`;
  document.getElementById('depback').onclick=()=>{flt='';tab='charges';render();};
  view.querySelectorAll('.dtab').forEach(b=>b.onclick=()=>{
    depKind=b.dataset.kind; depOpen=null; renderDeposits();});
  const rec=k=>all.find(x=>x.key===k);
  view.querySelectorAll('.depmatch').forEach(b=>b.onclick=()=>{
    depOpen=(depOpen===b.dataset.k)?null:b.dataset.k; renderDeposits();});
  view.querySelectorAll('.dep_q').forEach(qi=>{
    const k=qi.dataset.k, res=view.querySelector('.dep_res[data-k="'+CSS.escape(k)+'"]');
    qi.focus();
    // הצעה ראשונית לפי תעתיק השם מאנגלית
    const seed=norm((rec(k)||{}).name||'').split(' ').filter(w=>w.length>2)[0]||'';
    const run=s2=>{ if(!s2){res.innerHTML='';return;}
      const m=DB.filter(d=>norm(d.last+' '+d.first+' '+d.english+' '+d.business).toLowerCase()
        .includes(s2.toLowerCase())).slice(0,10);
      res.innerHTML=m.map(d=>`<div class="dpr" data-id="${d.id}">${esc(d.last)} ${esc(d.first)}${d.business?(' · '+esc(d.business)):''}${d.english?(' · <span dir="ltr">'+esc(d.english)+'</span>'):''}</div>`).join('')
        ||'<div class="dpr" style="color:var(--muted)">אין תוצאות — נסה שם אחר או "תורם חדש"</div>';
      res.querySelectorAll('.dpr[data-id]').forEach(x=>x.onclick=async()=>{
        const r=await api('POST','/api/deposits/map',{name:(rec(k)||{}).name,donor_id:+x.dataset.id});
        if(!r||!r.ok){toast('לא שויך');return;}
        depOpen=null; toast('שויך ✓ '+(r.linked||0)+' הפקדות נכנסו לכרטיס');
        await load(); renderDeposits();});};
    if(seed)run(seed);
    qi.oninput=()=>run(norm(qi.value));});
  view.querySelectorAll('.depnew').forEach(b=>b.onclick=()=>{
    const x=rec(b.dataset.k); if(!x)return;
    openNewDonor(async nd=>{
      const r=await api('POST','/api/deposits/map',{name:x.name,donor_id:nd.id});
      toast('נפתח כרטיס ושויך ✓'+(r&&r.linked?(' — '+r.linked+' הפקדות'):''));
      await load(); renderDeposits();}, {english:x.name, email:x.email||'', phone:x.phone||''});});
  view.querySelectorAll('.depign').forEach(b=>b.onclick=async()=>{
    const x=rec(b.dataset.k); if(!x)return;
    if(!await uiConfirm('לסמן את "'+x.name+'" כלא רלוונטי?\n'+x.n+' הפקדות יורדו מהרשימה ולא תישאל עליהן שוב.'))return;
    await api('POST','/api/deposits/map',{name:x.name,ignore:1,tids:x.tids});
    toast('הוסר ✓'); renderDeposits();});
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
  f.onclick=()=>{if(SRACT){try{stopDictation();}catch(e){}SRACT=null;f.classList.remove('rec');}openDictPad();};})();
load();
