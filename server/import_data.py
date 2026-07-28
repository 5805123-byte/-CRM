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
  id INTEGER PRIMARY KEY AUTOINCREMENT, donor_id INTEGER, text TEXT, tier TEXT
);
"""

NIK = re.compile(r'[֑-ׇ]')
def norm(s): return re.sub(r'\s+',' ',re.sub(r'[\"\x27\`]','',NIK.sub('',str(s or '')))).strip()

def v(c): return '' if c.value is None else str(c.value).strip()

def main():
    wb = openpyxl.load_workbook(XLSX)
    con = sqlite3.connect(DB); con.executescript(SCHEMA); cur = con.cursor()

    ws = wb['תורמים']; idx = {}
    for r in range(2, ws.max_row+1):
        if not v(ws.cell(r,1)): continue
        did = r-1
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
    if 'שמות_לתפילה' in wb.sheetnames:
        ws = wb['שמות_לתפילה']
        for r in range(2, ws.max_row+1):
            if not v(ws.cell(r,1)): continue
            did = idx.get(norm(v(ws.cell(r,3))))
            cur.execute("INSERT INTO prayers(donor_id,text,tier) VALUES(?,?,?)",
                (did, v(ws.cell(r,4)), v(ws.cell(r,6))))

    con.commit()
    for t in ('donors','pledges','parnes','prayers'):
        n = cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f'  {t}: {n}')
    con.close()
    print('נוצר:', DB)

if __name__ == '__main__':
    main()
