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
CREATE TABLE occasional(
  id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, total TEXT, detail TEXT
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
DROP TABLE IF EXISTS partners;
CREATE TABLE partners(
  id INTEGER PRIMARY KEY AUTOINCREMENT, donor_id INTEGER, avreich TEXT, note TEXT
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

    # פרנס יום
    if 'פרנס_יום' in wb.sheetnames:
        ws = wb['פרנס_יום']
        for r in range(2, ws.max_row+1):
            if not v(ws.cell(r,1)): continue
            did = idx.get(norm(v(ws.cell(r,5))))
            cur.execute("INSERT INTO parnes(donor_id,day,month,ord,date_text,amount,dedication,nusach) VALUES(?,?,?,?,?,?,?,?)",
                (did, int(v(ws.cell(r,2)) or 0), v(ws.cell(r,3)), int(v(ws.cell(r,4)) or 0),
                 v(ws.cell(r,1)), v(ws.cell(r,6)), v(ws.cell(r,7)), v(ws.cell(r,8))))

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

    # מזדמנים
    if 'מזדמנים' in wb.sheetnames:
        ws = wb['מזדמנים']
        for r in range(2, ws.max_row+1):
            if not v(ws.cell(r,1)): continue
            cur.execute("INSERT INTO occasional(name,total,detail) VALUES(?,?,?)",
                (v(ws.cell(r,2)), v(ws.cell(r,3)), v(ws.cell(r,4))))

    con.commit()
    for t in ('donors','pledges','parnes','prayers','occasional'):
        n = cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f'  {t}: {n}')
    con.close()
    print('נוצר:', DB)

if __name__ == '__main__':
    main()
