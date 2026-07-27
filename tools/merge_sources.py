# -*- coding: utf-8 -*-
"""
מיזוג נתונים: Google Contacts (CSV) + Donations Summary (Excel) -> חוברת מאוחדת.

שימוש:
    python3 tools/merge_sources.py --contacts contacts.csv --donations Donations.xlsx --out starter/crm-donors-filled.xlsx

מה נוצר בחוברת:
    תורמים               — כרטיס לכל תורם מגוגל (שם, טלפון, מייל, כתובת) + דרגת קוויטל שהותאמה
    לבדיקה_קוויטל        — שמות קוויטל שלא הותאמו אוטומטית, עם הצעת תורם לאישור ידני
    קובץ_התאמה_חודשיים   — התורמים החודשיים מהאקסל (שם אנגלי) + שתי עמודות עבריות ריקות למילוי
    מזדמנים              — תורמים מזדמנים (Occasional) לפי חודש
"""
import re, csv, argparse
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

_ap = argparse.ArgumentParser()
_ap.add_argument("--contacts", required=True, help="ייצוא Google Contacts בפורמט CSV")
_ap.add_argument("--donations", required=True, help="קובץ Donations Summary (xlsx)")
_ap.add_argument("--out", default="starter/crm-donors-filled.xlsx")
_ap.add_argument("--review-json", default=None, help="ייצוא רשימת ההתאמות-לבדיקה כ-JSON (לדף האישור)")
_ap.add_argument("--approvals", default=None, help="קובץ JSON של אישורים ידניים {שם_קוויטל: {choice}}")
_ap.add_argument("--phone-matches", default=None, help="קובץ JSON {שם_קוויטל: טלפון} לחיבור טלפונים שנמצאו לפי צליל")
_args = _ap.parse_args()
CONTACTS = _args.contacts
DON = _args.donations
OUT = _args.out

NIKUD = re.compile(r'[֑-ׇ]')
KV_SUFFIX = re.compile(r'[\-–—]?\s*ק[וו][ו]?[יי]?[ט]ל.*$')  # " - קוויטל" ווריאציות
TORM_SUFFIX = re.compile(r'\s*תורם\s*$')

def norm(s):
    if not s: return ''
    s = NIKUD.sub('', str(s))
    s = s.replace('"','').replace("'",'').replace('`','')
    s = KV_SUFFIX.sub('', s)
    s = TORM_SUFFIX.sub('', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s

FIN = str.maketrans('ךםןףץ','כמנפצ')
def loose(s):
    """מפתח 'רופף' לספיגת וריאציות איות: אותיות סופיות + וו/יי כפולים."""
    s = norm(s).translate(FIN)
    s = s.replace('וו','ו').replace('יי','י').replace('אא','א')
    s = re.sub(r'\s+','',s)
    return s

# ---------- קריאת אנשי קשר ----------
rows = list(csv.DictReader(open(CONTACTS, encoding='utf-8')))
def labs(r): return set(l.strip() for l in (r.get('Labels') or '').split(' ::: ') if l.strip())

KV = {'קוויטל','קוויטל ישז','קוויטל 101','קוויטל לא פעיל','יששכר זבולון','קוויטל אב פו'}
DON_L = {'תורמים','תורמים מזדמנים','תורמים בארץ עברית'}

def tier_from_labels(L):
    if 'קוויטל ישז' in L or 'יששכר זבולון' in L: return 'יששכר_זבולון'
    if 'קוויטל 101' in L: return 'קוויטל_101'
    if 'קוויטל' in L or 'קוויטל אב פו' in L: return 'קוויטל_כללי'
    if 'קוויטל לא פעיל' in L: return 'קוויטל_כללי'
    return ''

# מפת דרגה לפי שם עברי, מכרטיסי הקוויטל — לפי מפתח מדויק וגם מפתח רופף
tier_map = {}; tier_loose = {}; kv_names = {}
inactive = set()
order = {'יששכר_זבולון':3,'קוויטל_101':2,'קוויטל_כללי':1,'':0}
for r in rows:
    L = labs(r)
    if L & KV:
        raw = (r.get('First Name','')+' '+r.get('Middle Name','')+' '+r.get('Last Name',''))
        nm = norm(raw); lk = loose(raw); t = tier_from_labels(L)
        if nm and order.get(t,0) >= order.get(tier_map.get(nm,''),0): tier_map[nm]=t
        if lk and order.get(t,0) >= order.get(tier_loose.get(lk,''),0): tier_loose[lk]=t
        if lk: kv_names.setdefault(lk, norm(raw))
        if 'קוויטל לא פעיל' in L: inactive.add(nm)

def lookup_tier(nm, lk):
    if nm in tier_map: return tier_map[nm], 'מדויק'
    if lk in tier_loose: return tier_loose[lk], 'רופף'
    return '', ''
matched_kv_keys = set()

# ---------- חילוץ שמות התפילה מכרטיסי הקוויטל ----------
# השמות שמורים בשדה המותאם 'קוויטל' או בהערות
prayer_rows = []
for r in rows:
    L = labs(r)
    if not (L & KV): continue
    donor_nm = norm(r.get('First Name','')+' '+r.get('Middle Name','')+' '+r.get('Last Name',''))
    cf = (r.get('Custom Field 1 - Value') or '').strip()
    note = (r.get('Notes') or '').strip()
    prayer = cf or note
    if not prayer: continue
    prayer = prayer.replace('\r','').strip()
    prayer = re.sub(r',\s*,', ',', prayer)           # פסיקים כפולים
    # דלג על שאריות שדות טכניים (טלפון/מייל) או ערך מספרי בלבד
    if re.search(r'(Phone|E-?mail|- Value|:::)', prayer): continue
    if re.fullmatch(r'[\d\s\-\+()]+', prayer): continue
    prayer_rows.append({'donor':donor_nm, 'prayer':prayer, 'tier':tier_from_labels(L),
                        'tags':';'.join(sorted(L & KV))})

# ---------- בניית רשומות תורמים ----------
donors = []
seen = {}; seen_loose = set()
def phone_join(r):
    ps=[r.get('Phone 1 - Value',''),r.get('Phone 2 - Value','')]
    raw=' / '.join(p.strip() for p in ps if p.strip())
    return raw.replace(' ::: ',' / ')

def _norm_one_phone(x):
    """מנרמל מספר בודד: אמריקאי -> +1XXXXXXXXXX ; ישראלי -> +972 ; אחר נשמר."""
    x=x.strip()
    if not x: return ''
    has_plus=x.startswith('+')
    digits=re.sub(r'\D','',x)
    if not digits: return x
    if digits.startswith('00'): digits=digits[2:]
    if digits.startswith('972'):                     # ישראל
        return '+972 '+digits[3:].lstrip('0')
    if has_plus and not digits.startswith('1'):      # מדינה אחרת (בלגיה וכו') — נשמר
        return '+'+digits
    if digits.startswith('0') and len(digits)<=10:   # ישראלי מקומי 05x
        return '+972 '+digits[1:]
    if digits.startswith('1') and len(digits)==11:   # ארה"ב עם קידומת
        digits=digits[1:]
    if len(digits)==10:                              # ארה"ב 10 ספרות
        return f'+1 {digits[:3]}-{digits[3:6]}-{digits[6:]}'
    if has_plus: return '+'+digits
    return x

def normalize_phone(p):
    """מנרמל מחרוזת טלפון (יתכן כמה מספרים מופרדים ב-/)."""
    if not p: return ''
    parts=re.split(r'\s*/\s*',p)
    return ' / '.join(z for z in (_norm_one_phone(x) for x in parts) if z)

for r in rows:
    L = labs(r)
    if not (L & DON_L):   # רק כרטיסים עם תווית תורמים
        continue
    first=(r.get('First Name','')+' '+r.get('Middle Name','')).strip()
    last=r.get('Last Name','').strip()
    nm = norm(first+' '+last); lk = loose(first+' '+last)
    tier, how = lookup_tier(nm, lk)
    if tier and lk in tier_loose: matched_kv_keys.add(lk)
    addr = r.get('Address 1 - Formatted','') or ', '.join(x for x in [r.get('Address 1 - City',''),r.get('Address 1 - Country','')] if x)
    notes = ' | '.join(x for x in [r.get('Notes',''),r.get('Custom Field 1 - Value','')] if x)
    tags = ';'.join(sorted(L & (KV|DON_L)))
    donors.append({
        'first':re.sub(r'\s+',' ',first).strip(), 'last':last,
        'org':r.get('Organization Name',''),
        'phone':phone_join(r), 'email':r.get('E-mail 1 - Value',''),
        'addr':addr.replace('\n',', '), 'tier':tier, 'how':how, 'tags':tags,
        'bday':r.get('Birthday',''), 'notes':notes,
        'n-flag':'לא פעיל' if nm in inactive else '', 'nm':nm,
    })
    seen[nm]=True; seen_loose.add(lk)

# טעינת אישורים ידניים (מדף האישור)
approvals = {}
if _args.approvals:
    import json as _json
    approvals = {norm(k): v for k, v in _json.load(open(_args.approvals, encoding='utf-8')).items()}
donor_by_norm = {}
for d in donors:
    donor_by_norm[norm(d['first'] + ' ' + d['last'])] = d
n_linked = 0; n_newapproved = 0

# חיבורי טלפון שנמצאו לפי צליל
phone_matches = {}
if _args.phone_matches:
    import json as _json2
    phone_matches = {norm(k): v for k, v in _json2.load(open(_args.phone_matches, encoding='utf-8')).items()}

# אינדקס לפי שם-משפחה רופף מכל אנשי הקשר (לא רק תורמים), להצעת התאמות
all_by_surname={}
for r in rows:
    L=labs(r)
    if (L & KV) and not (L & DON_L):  # דלג על כרטיסי-קוויטל עצמם
        continue
    first=(r.get('First Name','')+' '+r.get('Middle Name','')).strip()
    last=r.get('Last Name','').strip()
    if not (first or last): continue
    entry={'first':norm(first),'last':norm(last),
           'phone':phone_join(r),'is_donor':bool(L & DON_L)}
    sur=loose(last or first.split(' ')[-1])
    if sur: all_by_surname.setdefault(sur,[]).append(entry)

def suggest(fullname):
    toks=norm(fullname).split(' ')
    if not toks: return []
    sur=loose(toks[-1]); firstl=loose(toks[0])
    cands=all_by_surname.get(sur,[])
    ranked=sorted(cands,key=lambda d:(0 if loose(d['first']).startswith(firstl[:2]) else 1,
                                      0 if d['is_donor'] else 1))
    return ranked

# כרטיסי קוויטל ללא כרטיס תורם -> רשימת 'לבדיקה' עם הצעת התאמה
review=[]; kv_only=0
for r in rows:
    L=labs(r)
    if (L & KV) and not (L & DON_L):
        raw=(r.get('First Name','')+' '+r.get('Middle Name','')+' '+r.get('Last Name',''))
        nm=norm(raw); lk=loose(raw)
        # החלת אישור ידני אם קיים
        if nm in approvals:
            ch = approvals[nm].get('choice')
            tier_here = tier_from_labels(L)
            if ch == '__new__':
                donors.append({'first':nm,'last':'','org':'','phone':'','email':'','addr':'',
                    'tier':tier_here,'how':'אושר: חדש','tags':';'.join(sorted(L&KV)),
                    'bday':'','notes':'','n-flag':'תורם חדש (אושר ידנית)','nm':nm})
                n_newapproved += 1
            else:
                dm = donor_by_norm.get(norm(ch))
                if dm is not None:
                    if not dm['tier']: dm['tier'] = tier_here
                    dm['how'] = 'אושר ידנית'
                else:
                    # איש קשר קיים שאינו מתויג 'תורמים' — נוסיף אותו כתורם עם הטלפון שאושר
                    donors.append({'first':ch,'last':'','org':'','phone':approvals[nm].get('phone',''),
                        'email':'','addr':'','tier':tier_here,'how':'אושר ידנית','tags':';'.join(sorted(L&KV)),
                        'bday':'','notes':'','n-flag':'חובר מאיש קשר (אושר ידנית)','nm':norm(ch)})
                    donor_by_norm[norm(ch)] = donors[-1]
                n_linked += 1
            seen[nm]=True; seen_loose.add(lk)
            continue
        if nm and nm not in seen and lk not in seen_loose:
            cands=suggest(nm)
            # ללא הצעת התאמה כלל -> זהו תורם מוכר מהקוויטל, נוסיף אותו לרשימה (בלי טלפון עדיין)
            if not cands:
                donors.append({'first':nm,'last':'','org':'','phone':'','email':'','addr':'',
                    'tier':tier_from_labels(L),'how':'מהקוויטל','tags':';'.join(sorted(L&KV)),
                    'bday':'','notes':'','n-flag':'מהקוויטל — אין טלפון עדיין','nm':nm})
                seen[nm]=True; seen_loose.add(lk); kv_only+=1
                continue
            sug=cands[0] if cands else None
            prayer=(r.get('Custom Field 1 - Value') or r.get('Notes') or '').replace('\r','').strip()
            review.append({'kv':nm,'tier':tier_from_labels(L),'prayer':prayer,
                'sug':(sug['first']+' '+sug['last']).strip() if sug else '',
                'sug_phone':sug['phone'] if sug else '',
                'sug_isdonor':('תורם' if sug and sug['is_donor'] else ('איש קשר' if sug else '')),
                'cands':[{'name':(c['first']+' '+c['last']).strip(),'phone':c['phone'],
                          'is_donor':c['is_donor']} for c in cands[:4]],
                'n':len(cands)})
            kv_only+=1

# ---------- קריאת תרומות (Data + Occasional) ----------
wb=openpyxl.load_workbook(DON, data_only=True)
def s(v):
    if v is None: return ''
    if isinstance(v,float): return str(int(v)) if v==int(v) else str(round(v,2))
    return str(v).strip()

CH={'banquest':'בנק_ווסט','authorize':'אותורייז','checks':'צק','check':'צק','ach':'העברה_בנקאית',
    'fidelity':'פידליטי','ojc':'OJC','donors fund':'דונורס_פאנד','website':'אתר','nedarim':'נדרים_פלוס'}
def chan(m):
    m=(m or '').strip(); return CH.get(m.lower(), m)

data=wb['Data']; data_rows=[]
for r in range(2,data.max_row+1):
    typ=s(data.cell(r,1).value); nm=s(data.cell(r,2).value)
    if not nm: continue
    en_name=s(data.cell(r,4).value); en_sur=s(data.cell(r,5).value)
    # שם עסק: כשעמודת Names אינה שם האדם (לא מכילה את שם המשפחה) — זהו שם עסק
    business = nm if (en_sur and en_sur.lower() not in nm.lower()) else ''
    data_rows.append({'type':typ,'names':nm,'method':chan(s(data.cell(r,3).value)),
        'en_name':en_name,'en_sur':en_sur,'business':business,
        'email':s(data.cell(r,6).value),'amount':s(data.cell(r,7).value)})

occ=wb['Occasional']; occ_rows=[]
months=['ינואר','פברואר','מרץ','אפריל','מאי','יוני','יולי','אוגוסט','ספטמבר','אוקטובר','נובמבר','דצמבר']
for r in range(2,occ.max_row+1):
    nm=s(occ.cell(r,1).value)
    if not nm: continue
    vals={months[i]:s(occ.cell(r,3+i).value) for i in range(12)}
    total=sum(float(v) for v in vals.values() if v and v.replace('.','').isdigit())
    occ_rows.append({'nm':nm,'vals':vals,'total':total})

# ---------- כתיבת החוברת ----------
FONT='Arial'
HF=PatternFill('solid',fgColor='1F4E78'); HFONT=Font(name=FONT,bold=True,color='FFFFFF')
YEL=PatternFill('solid',fgColor='FFF2CC')
thin=Side(style='thin',color='D9D9D9'); BD=Border(left=thin,right=thin,top=thin,bottom=thin)
owb=openpyxl.Workbook()

def sheet(title,headers,rows_data,yellow=()):
    ws=owb.create_sheet(title); ws.sheet_view.rightToLeft=True
    for c,h in enumerate(headers,1):
        cell=ws.cell(1,c,h); cell.fill=HF; cell.font=HFONT
        cell.alignment=Alignment(horizontal='center',vertical='center',wrap_text=True); cell.border=BD
        ws.column_dimensions[get_column_letter(c)].width=max(12,min(30,len(h)+6))
    for c in yellow: ws.cell(1,c).fill=YEL
    for i,row in enumerate(rows_data,2):
        for c,v in enumerate(row,1):
            cell=ws.cell(i,c,v); cell.border=BD; cell.font=Font(name=FONT,size=10)
    ws.freeze_panes='A2'; ws.row_dimensions[1].height=28
    return ws

owb.remove(owb.active)

# חיבור טלפונים שנמצאו לפי צליל (למי שאין לו טלפון) + נרמול כל הטלפונים
n_phone_added = 0
for d in donors:
    if not d.get('phone') and d.get('nm') in phone_matches and phone_matches[d['nm']]:
        d['phone'] = phone_matches[d['nm']]
        d['how'] = (d.get('how','') + ' +טלפון').strip()
        d['n-flag'] = 'טלפון חובר לפי צליל'
        n_phone_added += 1
    d['phone'] = normalize_phone(d.get('phone',''))
    # פיצול שם שמופיע מלא בשדה אחד -> שם פרטי + שם משפחה (המילה האחרונה = שם משפחה)
    if not d.get('last') and d.get('first'):
        toks = d['first'].split()
        if len(toks) >= 2:
            d['first'] = ' '.join(toks[:-1]); d['last'] = toks[-1]

# תורמים — מיון לפי שם משפחה (א-ב), עמודת שם משפחה לפני שם פרטי
tor_rows=[]
for i,d in enumerate(sorted(donors,key=lambda x:(x['last'] or 'תתת', x['first'])),1):
    tor_rows.append([f'ת-{i:05d}',d['last'],d['first'],d['org'],d['phone'],d['email'],
                     d['addr'],d['tier'],d.get('how',''),d['tags'],d['bday'],d['notes'],d['n-flag']])
sheet('תורמים',['מזהה_תורם','שם_משפחה_עברי','שם_פרטי_עברי','שם_עסק','טלפון','אימייל','כתובת',
    'דרגת_קוויטל','אופן_התאמה','תוויות_גוגל','יום_הולדת','הערות','סטטוס'],tor_rows)

# קובץ התאמה (Data החודשיים) — עם עמודות עבריות ריקות
mt_rows=[]
for i,d in enumerate(data_rows,1):
    mt_rows.append([f'M-{i:04d}',(d['en_name']+' '+d['en_sur']).strip() or d['names'],
        d['business'],d['type'],d['method'],d['amount'],d['email'],'',''])
sheet('קובץ_התאמה_חודשיים',['מפתח','שם_אנגלי','שם_עסק','סוג(ישז/חודשי)','אמצעי_תשלום','סכום_חודשי',
    'אימייל','שם פרטי עברי','שם משפחה עברי'],mt_rows,yellow=(8,9))

# מזדמנים (כבר בעברית)
oc_rows=[]
for i,d in enumerate(occ_rows,1):
    paid=';'.join(f'{m}:{v}' for m,v in d['vals'].items() if v)
    oc_rows.append([f'O-{i:04d}',d['nm'],int(d['total']) if d['total'] else '',paid])
sheet('מזדמנים',['מפתח','שם_עברי','סכום_כולל_השנה','פירוט_חודשי'],oc_rows)

# שמות_לתפילה — השמות שהאברכים קוראים, לפי דרגה
sp_rows=[]
torder={'יששכר_זבולון':0,'קוויטל_101':1,'קוויטל_כללי':2}
for i,d in enumerate(sorted(prayer_rows,key=lambda x:(torder.get(x['tier'],9),x['donor'])),1):
    sp_rows.append([f'ש-{i:04d}','',d['donor'],d['prayer'],'',d['tier'],d['tags']])
sp_ws=sheet('שמות_לתפילה',['מזהה_שם','מזהה_תורם','שם_התורם','שמות','בקשה','דרגת_תפילה','תוויות_קוויטל'],sp_rows)
sp_ws.column_dimensions['D'].width=70
for rr in range(2,len(sp_rows)+2):
    sp_ws.cell(rr,4).alignment=Alignment(wrap_text=True,vertical='top')

# לבדיקה — שמות קוויטל ללא כרטיס תורם + הצעת התאמה
rv_rows=[]
for i,d in enumerate(sorted(review,key=lambda x:(x['n']==0,x['tier']!='יששכר_זבולון',x['kv'])),1):
    match_hint = 'התאמה יחידה' if d['n']==1 else (f'{d["n"]} אפשרויות' if d['n']>1 else 'לא נמצא — אולי חדש')
    rv_rows.append([f'R-{i:04d}',d['kv'],d['tier'],d['sug'],d['sug_isdonor'],d['sug_phone'],match_hint,''])
sheet('לבדיקה_קוויטל',['מפתח','שם_בקוויטל','דרגה','שם_מוצע','סוג_מוצע','טלפון_מוצע','הערכת_התאמה','אישור(כן/לא)'],
    rv_rows,yellow=(8,))

owb.save(OUT)

# ---------- ייצוא JSON לדף האישור ----------
if _args.review_json:
    import json
    payload=[]
    for i,d in enumerate(sorted(review,key=lambda x:(x['n']!=1,x['tier']!='יששכר_זבולון',x['kv'])),1):
        payload.append({'id':f'R{i:04d}','kvittel':d['kv'],'tier':d['tier'],
            'prayer':d.get('prayer','')[:220],'candidates':d['cands'],'n':d['n']})
    json.dump(payload,open(_args.review_json,'w',encoding='utf-8'),ensure_ascii=False,indent=1)
    print('JSON לאישור:',_args.review_json,'(',len(payload),'שורות )')

# ---------- דוח ----------
from collections import Counter
tc=Counter(d['tier'] for d in donors if d['tier'])
hc=Counter(d.get('how','') for d in donors if d['tier'])
print('OUT:',OUT)
print('כרטיסי תורם מלאים (מגוגל):',len(donors))
print('  עם דרגת קוויטל שהותאמה אוטומטית:',sum(tc.values()),' ',dict(tc))
print('  אופן ההתאמה:',dict(hc))
if approvals:
    print('אישורים ידניים שהוחלו: חוברו לאיש קשר =',n_linked,'| נוספו כחדשים =',n_newapproved)
if phone_matches:
    print('טלפונים שחוברו לפי צליל:',n_phone_added)
print('שמות קוויטל שנשארו לבדיקה:',len(review))
one=sum(1 for d in review if d['n']==1); multi=sum(1 for d in review if d['n']>1); none=sum(1 for d in review if d['n']==0)
print('   התאמה יחידה מוצעת:',one,'| כמה אפשרויות:',multi,'| חדש/לא נמצא:',none)
print('תורמים חודשיים (Data) לקובץ ההתאמה:',len(data_rows))
print('מזדמנים (Occasional):',len(occ_rows))
