# -*- coding: utf-8 -*-
"""טוען את הנתונים הנקיים מ-crm-donors-filled.xlsx לבסיס נתונים SQLite (crm.db)."""
import sqlite3, openpyxl, os, re

HERE = os.path.dirname(os.path.abspath(__file__))
XLSX = os.path.join(HERE, '..', 'starter', 'crm-donors-filled.xlsx')
DB = os.environ.get('DB_PATH') or os.path.join(HERE, 'crm.db')

SCHEMA = """
DROP TABLE IF EXISTS donors;
DROP TABLE IF EXISTS pledges;
DROP TABLE IF EXISTS parnes;
DROP TABLE IF EXISTS prayers;
CREATE TABLE donors(
  id INTEGER PRIMARY KEY, last TEXT, first TEXT, english TEXT, business TEXT,
  phone TEXT, email TEXT, addr TEXT, tier TEXT, category TEXT, purpose TEXT,
  amount TEXT, channel TEXT, pay_status TEXT, last_active TEXT, months TEXT,
  labels TEXT, aliases TEXT, notes TEXT
);
CREATE TABLE pledges(
  id INTEGER PRIMARY KEY AUTOINCREMENT, donor_id INTEGER, category TEXT,
  amount TEXT, status TEXT, date TEXT, note TEXT
);
CREATE TABLE parnes(
  id INTEGER PRIMARY KEY AUTOINCREMENT, donor_id INTEGER, day INTEGER, month TEXT,
  ord INTEGER, date_text TEXT, amount TEXT, dedication TEXT, nusach TEXT
);
CREATE TABLE prayers(
  id INTEGER PRIMARY KEY AUTOINCREMENT, donor_id INTEGER, name TEXT, text TEXT, tier TEXT
);
DROP TABLE IF EXISTS occasional;
DROP TABLE IF EXISTS donations;
CREATE TABLE donations(
  id INTEGER PRIMARY KEY AUTOINCREMENT, donor_id INTEGER, date TEXT,
  amount TEXT, category TEXT, method TEXT, note TEXT
);
DROP TABLE IF EXISTS contacts_log;
CREATE TABLE contacts_log(
  id INTEGER PRIMARY KEY AUTOINCREMENT, donor_id INTEGER, date TEXT,
  channel TEXT, summary TEXT, next_date TEXT
);
DROP TABLE IF EXISTS tasks;
CREATE TABLE tasks(
  id INTEGER PRIMARY KEY AUTOINCREMENT, donor_id INTEGER, due_date TEXT,
  kind TEXT, note TEXT, done INTEGER DEFAULT 0
);
DROP TABLE IF EXISTS partners;
CREATE TABLE partners(
  id INTEGER PRIMARY KEY AUTOINCREMENT, donor_id INTEGER, avreich TEXT,
  start_date TEXT, amount TEXT, note TEXT, active INTEGER DEFAULT 1, ended_date TEXT
);
DROP TABLE IF EXISTS donations;
CREATE TABLE donations(
  id INTEGER PRIMARY KEY AUTOINCREMENT, donor_id INTEGER, date TEXT,
  amount TEXT, category TEXT, method TEXT, note TEXT
);
DROP TABLE IF EXISTS contacts_log;
CREATE TABLE contacts_log(
  id INTEGER PRIMARY KEY AUTOINCREMENT, donor_id INTEGER, date TEXT,
  channel TEXT, summary TEXT, next_date TEXT
);
DROP TABLE IF EXISTS tasks;
CREATE TABLE tasks(
  id INTEGER PRIMARY KEY AUTOINCREMENT, donor_id INTEGER, due_date TEXT,
  kind TEXT, note TEXT, done INTEGER DEFAULT 0
);
"""

NIK = re.compile(r'[֑-ׇ]')
def norm(s): return re.sub(r'\s+',' ',re.sub(r'[\"\x27\`]','',NIK.sub('',str(s or '')))).strip()

def v(c): return '' if c.value is None else str(c.value).strip()

def edist(a, b):
    """מרחק עריכה — לזיהוי כינויים (יוסי/יוסף, זאב/זאבי)."""
    if abs(len(a)-len(b)) > 2: return 9
    dp = list(range(len(b)+1))
    for i, ca in enumerate(a, 1):
        prev = dp[0]; dp[0] = i
        for j, cb in enumerate(b, 1):
            cur = dp[j]; dp[j] = min(dp[j]+1, dp[j-1]+1, prev+(ca != cb)); prev = cur
    return dp[-1]

def main():
    wb = openpyxl.load_workbook(XLSX)
    con = sqlite3.connect(DB); con.executescript(SCHEMA); cur = con.cursor()

    ws = wb['תורמים']; idx = {}; by_last = {}
    for r in range(2, ws.max_row+1):
        if not v(ws.cell(r,1)): continue
        did = r-1
        by_last.setdefault(norm(v(ws.cell(r,2))), []).append((did, norm(v(ws.cell(r,3)))))
        cur.execute("""INSERT INTO donors(id,last,first,english,business,phone,email,addr,tier,
            category,amount,channel,pay_status,last_active,months,labels,aliases) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (did, v(ws.cell(r,2)),v(ws.cell(r,3)),v(ws.cell(r,4)),v(ws.cell(r,5)),v(ws.cell(r,6)),
             v(ws.cell(r,7)),v(ws.cell(r,8)),v(ws.cell(r,15)),v(ws.cell(r,9)),v(ws.cell(r,11)),
             v(ws.cell(r,12)),v(ws.cell(r,13)),v(ws.cell(r,14)),v(ws.cell(r,22)),v(ws.cell(r,17)),v(ws.cell(r,21))))
        cur.execute("UPDATE donors SET purpose=? WHERE id=?", (v(ws.cell(r,23)), did))
        idx[norm(v(ws.cell(r,3))+' '+v(ws.cell(r,2)))] = did
        idx[norm(v(ws.cell(r,2))+' '+v(ws.cell(r,3)))] = did
        for al in v(ws.cell(r,21)).split(';'):
            if al.strip(): idx[norm(al)] = did

    # פרנס יום + תזכורת אוטומטית שבוע לפני
    try:
        from hebdate import week_before
    except Exception:
        week_before = lambda *a, **k: None
    if 'פרנס_יום' in wb.sheetnames:
        ws = wb['פרנס_יום']
        for r in range(2, ws.max_row+1):
            if not v(ws.cell(r,1)): continue
            did = idx.get(norm(v(ws.cell(r,5))))
            date_text = v(ws.cell(r,1))
            cur.execute("INSERT INTO parnes(donor_id,day,month,ord,date_text,amount,dedication,nusach) VALUES(?,?,?,?,?,?,?,?)",
                (did, int(v(ws.cell(r,2)) or 0), v(ws.cell(r,3)), int(v(ws.cell(r,4)) or 0),
                 date_text, v(ws.cell(r,6)), v(ws.cell(r,7)), v(ws.cell(r,8))))
            due = week_before(date_text)
            if did and due:
                cur.execute("INSERT INTO tasks(donor_id,due_date,kind,note) VALUES(?,?,?,?)",
                    (did, due, 'parnes', 'פרנס יום ' + date_text + ' — הכן הדפסה וצור קשר'))

    # שמות לתפילה
    def match_prayer(name):
        """התאמת שם בקוויטל לכרטיס תורם — מדויק, ואם לא, לפי שם משפחה זהה + כינוי לשם פרטי."""
        n = norm(name)
        if n in idx: return idx[n]
        toks = n.split()
        for i in range(len(toks)):
            ln = toks[i]
            if ln in by_last:
                rest = ' '.join(toks[:i] + toks[i+1:])
                for cand_did, cand_first in by_last[ln]:
                    if rest and cand_first and edist(rest, cand_first) <= 1:
                        return cand_did
        return None

    if 'שמות_לתפילה' in wb.sheetnames:
        ws = wb['שמות_לתפילה']
        linked = loose = 0
        for r in range(2, ws.max_row+1):
            if not v(ws.cell(r,1)): continue
            nm = v(ws.cell(r,3))
            did = match_prayer(nm)
            if did: linked += 1
            else: loose += 1
            cur.execute("INSERT INTO prayers(donor_id,name,text,tier) VALUES(?,?,?,?)",
                (did, nm, v(ws.cell(r,4)), v(ws.cell(r,6))))
        print(f'  קוויטל: {linked} משויכים לכרטיס, {loose} עדיין לא משויכים')

    # מזדמנים — ממוזגים לקטלוג הראשי: קיים -> תרומות לכרטיסו; חדש -> כרטיס מזדמן.
    HMON={'ינואר':'01','פברואר':'02','מרץ':'03','אפריל':'04','מאי':'05','יוני':'06',
          'יולי':'07','אוגוסט':'08','אוגסט':'08','ספטמבר':'09','אוקטובר':'10','נובמבר':'11','דצמבר':'12'}
    YEAR='2026'
    # מיזוגים מפורשים של מזדמנים לתורם קיים (שם שונה מהותית)
    OCC_ALIAS = { norm('דוויק אבי'): norm('דוואק אברהם') }
    def match_occasional(name):
        n = norm(name)
        if n in idx: return idx[n]
        if n in OCC_ALIAS and OCC_ALIAS[n] in idx: return idx[OCC_ALIAS[n]]
        toks = n.split()
        if len(toks) >= 2:
            oc_last = toks[0]; oc_first = ' '.join(toks[1:])
            for ln, lst in by_last.items():
                if edist(oc_last, ln) <= 1:
                    for cand_did, cand_first in lst:
                        if cand_first and edist(oc_first, cand_first) <= 1:
                            return cand_did
        return None

    if 'מזדמנים' in wb.sheetnames:
        ws = wb['מזדמנים']
        nextid = cur.execute("SELECT COALESCE(MAX(id),0) FROM donors").fetchone()[0] + 1
        new_c=match_c=don_c=0
        for r in range(2, ws.max_row+1):
            name=v(ws.cell(r,2))
            if not name: continue
            total=v(ws.cell(r,3)); detail=v(ws.cell(r,4))
            did=match_occasional(name)
            if not did:
                toks=name.split()
                last=toks[0] if toks else name; first=' '.join(toks[1:])
                did=nextid; nextid+=1
                cur.execute("INSERT INTO donors(id,last,first,category) VALUES(?,?,?,?)",(did,last,first,'מזדמן'))
                idx[norm(name)]=did; new_c+=1
            else:
                match_c+=1
            if detail and detail.lower()!='none':
                for part in detail.split(';'):
                    if ':' not in part: continue
                    mon,amt=part.split(':',1)
                    mm=HMON.get(mon.strip())
                    cur.execute("INSERT INTO donations(donor_id,date,amount,category) VALUES(?,?,?,?)",
                        (did, f"{YEAR}-{mm}" if mm else '', amt.strip(), 'מזדמן')); don_c+=1
            elif total and total.lower()!='none':
                cur.execute("INSERT INTO donations(donor_id,date,amount,category) VALUES(?,?,?,?)",
                    (did, YEAR, total, 'מזדמן')); don_c+=1
        print(f'  מזדמנים: {new_c} כרטיסים חדשים, {match_c} חוברו לקיימים, {don_c} תרומות')

    con.commit()
    for t in ('donors','pledges','parnes','prayers','donations'):
        n = cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f'  {t}: {n}')
    con.close()
    print('נוצר:', DB)

if __name__ == '__main__':
    main()
