# -*- coding: utf-8 -*-
"""שרת CRM כולל חצות — מגיש את הממשק + API לשמירה (SQLite)."""
import sqlite3, json, os, re, base64, datetime
from urllib.parse import quote

def today_iso():
    return datetime.date.today().isoformat()
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from hebdate import week_before, greg_to_heb_monthyear, current_heb_year, heb_to_greg, future_parnes, heb_greg_year, HMONTHS

def heb_anniv(start_date):
    """המופע הבא (>= היום) של יום+חודש עברי מתוך תאריך תחילת שותפות — מתעלם משנת ההסכם."""
    txt = re.sub(r'[\"\']', '', str(start_date or '')).strip()
    toks = txt.split()
    if not toks:
        return None
    mon = next((t for t in toks[1:] if t in HMONTHS), None)
    if not mon:
        return None
    return heb_to_greg(toks[0] + ' ' + mon)

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.environ.get('DB_PATH') or os.path.join(HERE, 'crm.db')
STATIC = os.path.join(HERE, 'static')
PORT = int(os.environ.get('PORT', 8000))

def db():
    con = sqlite3.connect(DB); con.row_factory = sqlite3.Row; return con

_NIKUD = re.compile(r'[֑-ׇ]')
def _norm(s):
    """נרמול עברי לחיפוש לפי איות — הסרת ניקוד, גרשיים ורווחים, איחוד אותיות סופיות."""
    s = _NIKUD.sub('', str(s or ''))
    s = re.sub(r'[^א-תa-zA-Z ]', '', s)
    s = s.translate(str.maketrans('ךםןףץ', 'כמנפצ'))
    return s.strip()

def _intake_configured():
    try:
        import gmail_intake
        return gmail_intake.configured()
    except Exception:
        return False

def ensure_schema():
    """יוצר טבלאות חדשות אם חסרות — כדי שעדכונים לא ידרשו למחוק נתונים קיימים (דיסק קבוע)."""
    con = db()
    con.executescript("""
    CREATE TABLE IF NOT EXISTS donations(id INTEGER PRIMARY KEY AUTOINCREMENT, donor_id INTEGER, date TEXT, amount TEXT, category TEXT, method TEXT, note TEXT);
    CREATE TABLE IF NOT EXISTS contacts_log(id INTEGER PRIMARY KEY AUTOINCREMENT, donor_id INTEGER, date TEXT, channel TEXT, summary TEXT, next_date TEXT);
    CREATE TABLE IF NOT EXISTS tasks(id INTEGER PRIMARY KEY AUTOINCREMENT, donor_id INTEGER, due_date TEXT, kind TEXT, note TEXT, done INTEGER DEFAULT 0);
    CREATE TABLE IF NOT EXISTS partners(id INTEGER PRIMARY KEY AUTOINCREMENT, donor_id INTEGER, avreich TEXT, start_date TEXT, amount TEXT, note TEXT, active INTEGER DEFAULT 1, ended_date TEXT);
    CREATE TABLE IF NOT EXISTS files(id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT, ref_id INTEGER, name TEXT, mime TEXT, data BLOB, created TEXT);
    CREATE TABLE IF NOT EXISTS transactions(id INTEGER PRIMARY KEY AUTOINCREMENT, donor_id INTEGER, date TEXT, amount TEXT,
        category TEXT, method TEXT, status TEXT DEFAULT 'pending', trans_id TEXT, sub_id TEXT,
        inst_total INTEGER DEFAULT 1, inst_paid INTEGER DEFAULT 0, recurring INTEGER DEFAULT 0, note TEXT, created TEXT);
    CREATE TABLE IF NOT EXISTS building(id INTEGER PRIMARY KEY AUTOINCREMENT, donor_id INTEGER, object TEXT,
        amount TEXT, paid TEXT, note TEXT, date TEXT);
    CREATE TABLE IF NOT EXISTS recon(tid TEXT PRIMARY KEY, first TEXT, last TEXT, amount TEXT, date TEXT,
        addr TEXT, city TEXT, state TEXT, zip TEXT, phone TEXT, email TEXT, recurring INTEGER DEFAULT 0,
        donor_id INTEGER, category TEXT, processed INTEGER DEFAULT 0, source TEXT, status TEXT DEFAULT 'settled');
    CREATE TABLE IF NOT EXISTS campaigns(name TEXT PRIMARY KEY, created TEXT);
    CREATE TABLE IF NOT EXISTS building_items(name TEXT PRIMARY KEY, created TEXT);
    CREATE TABLE IF NOT EXISTS intake(id INTEGER PRIMARY KEY AUTOINCREMENT, message_id TEXT UNIQUE,
        from_name TEXT, from_email TEXT, subject TEXT, received TEXT, body TEXT, names TEXT,
        donor_id INTEGER, status TEXT DEFAULT 'new', created TEXT);
    """)
    # מיגרציה — הוספת עמודות חדשות אם חסרות (דיסק קבוע קיים)
    for col, ddl in [('start_date', 'TEXT'), ('amount', 'TEXT'), ('active', 'INTEGER DEFAULT 1'), ('ended_date', 'TEXT'), ('method', 'TEXT'), ('partner_with', 'TEXT'), ('partner_with_id', 'INTEGER'), ('renew_date', 'TEXT'), ('paid_note', 'TEXT'), ('joint', 'INTEGER DEFAULT 0')]:
        try: con.execute(f"ALTER TABLE partners ADD COLUMN {col} {ddl}")
        except Exception: pass
    # תאריך חידוש שותפות יש"ז — המופע הבא של תאריך תחילת ההסכם העברי (שנה מהתחלה). מחושב מחדש בכל הפעלה.
    try:
        for r in con.execute("SELECT id, start_date FROM partners WHERE COALESCE(active,1)<>0 AND COALESCE(TRIM(start_date),'')<>''").fetchall():
            g = heb_anniv(r['start_date'])
            con.execute("UPDATE partners SET renew_date=? WHERE id=?", (g.isoformat() if g else None, r['id']))
    except Exception as e:
        print('  שגיאת תאריך חידוש יש"ז:', e)
    try: con.execute("ALTER TABLE parnes ADD COLUMN kind TEXT DEFAULT 'parnes'")
    except Exception: pass
    try: con.execute("ALTER TABLE parnes ADD COLUMN status TEXT DEFAULT 'confirmed'")
    except Exception: pass
    try: con.execute("ALTER TABLE parnes ADD COLUMN photo TEXT")
    except Exception: pass
    try: con.execute("ALTER TABLE parnes ADD COLUMN paid INTEGER DEFAULT 0")
    except Exception: pass
    try: con.execute("ALTER TABLE parnes ADD COLUMN night_date TEXT")
    except Exception: pass
    try: con.execute("ALTER TABLE parnes ADD COLUMN hyear TEXT")
    except Exception: pass
    try: con.execute("ALTER TABLE parnes ADD COLUMN method TEXT")   # דרך מה תיגבה ההתחייבות
    except Exception: pass
    try: con.execute("ALTER TABLE parnes ADD COLUMN currency TEXT")   # מטבע הסכום ($ / ₪)
    except Exception: pass
    # מילוי תאריך לועזי של הלילה (לצורך היעלמות סימון הירח אחרי שהלילה עבר ושולם)
    try:
        for row in con.execute("SELECT id,date_text FROM parnes WHERE COALESCE(night_date,'')=''").fetchall():
            g = heb_to_greg(row['date_text'])
            if g: con.execute("UPDATE parnes SET night_date=? WHERE id=?", (g.isoformat(), row['id']))
    except Exception: pass
    for col in ('created', 'source', 'region', 'country', 'zip', 'city'):
        try: con.execute(f"ALTER TABLE donors ADD COLUMN {col} TEXT")
        except Exception: pass
    for col in ('fb_channel', 'fb_date', 'fb_followup', 'fb_note'):
        try: con.execute(f"ALTER TABLE donations ADD COLUMN {col} TEXT")
        except Exception: pass
    try: con.execute("ALTER TABLE donations ADD COLUMN paid INTEGER DEFAULT 0")
    except Exception: pass
    try: con.execute("ALTER TABLE donations ADD COLUMN thanked INTEGER DEFAULT 0")   # האם הודינו על התרומה
    except Exception: pass
    try: con.execute("ALTER TABLE donors ADD COLUMN iz_note TEXT")
    except Exception: pass
    try: con.execute("ALTER TABLE donors ADD COLUMN notes TEXT")   # הערות חופשיות (למשל: הגיע דרך אבא קלוק)
    except Exception: pass
    try: con.execute("ALTER TABLE contacts_log ADD COLUMN msg_id TEXT")   # מזהה מייל — למניעת תיוק כפול
    except Exception: pass
    try: con.execute("ALTER TABLE contacts_log ADD COLUMN body TEXT")     # גוף המייל (רק מה שהתורם כתב)
    except Exception: pass
    try: con.execute("ALTER TABLE contacts_log ADD COLUMN att_checked INTEGER DEFAULT 0")  # נבדקו קבצים מצורפים
    except Exception: pass
    try: con.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_clog_msg ON contacts_log(msg_id) WHERE msg_id IS NOT NULL AND msg_id<>''")
    except Exception: pass
    # סימון "לא צריך קוויטל" (וי אדום) — כדי להסיר מרשימת חסרי־שמות בלי לשנות דרגה
    try: con.execute("ALTER TABLE donors ADD COLUMN kv_skip INTEGER DEFAULT 0")
    except Exception: pass
    # סימון "כתובת תקינה/טופלה" — להסיר מרשימת כתובות לתיקון
    try: con.execute("ALTER TABLE donors ADD COLUMN addr_ok INTEGER DEFAULT 0")
    except Exception: pass
    # הקצאת משימה למזכיר (מאיר / אהרן / ריק=אני)
    try: con.execute("ALTER TABLE tasks ADD COLUMN assignee TEXT")
    except Exception: pass
    # תדירות תרומה — קבוע אך לא בהכרח חודשי (רבעוני / שנתי / לחגים וכו')
    try: con.execute("ALTER TABLE donors ADD COLUMN frequency TEXT")
    except Exception: pass
    # חודש+שנה עברית לתורם מזדמן — משייך את הקוויטל שלו לחודש/שנה מסוימים ברשימת המזדמנים
    try: con.execute("ALTER TABLE donors ADD COLUMN kv_month TEXT")
    except Exception: pass
    try: con.execute("ALTER TABLE donors ADD COLUMN kv_year TEXT")
    except Exception: pass
    # השלמת דרגת יששכר־זבולון לתורמים שהיו ברשימה אך לא סומנו (מקור אמת: iz_seed.json + כל מי שיש לו אברך)
    try:
        con.execute("""UPDATE donors SET tier='יששכר_זבולון'
                       WHERE id IN (SELECT donor_id FROM partners)
                       AND COALESCE(tier,'')<>'יששכר_זבולון'""")
        seed_path = os.path.join(HERE, 'iz_seed.json')
        if os.path.exists(seed_path):
            for rec in json.load(open(seed_path, encoding='utf-8')):
                # התאמה לפי מזהה + שם משפחה כדי לא לפגוע בכרטיס אחר אם המזהים שונים
                con.execute("""UPDATE donors SET tier='יששכר_זבולון'
                               WHERE id=? AND last=? AND COALESCE(tier,'')<>'יששכר_זבולון'""",
                            (rec.get('id'), rec.get('last', '')))
    except Exception: pass
    # תיקון מיקוד ארה"ב שאיבד את האפס המוביל (07666 שנשמר כ-7666). כל מיקוד אמריקאי בן 4 ספרות חסר אפס.
    try:
        con.execute("""UPDATE donors SET zip='0'||zip
                       WHERE COALESCE(region,'')<>'il' AND zip GLOB '[0-9][0-9][0-9][0-9]'""")
    except Exception: pass
    # ניקוי תזכורות פרנס יתומות — שהיום שלהן כבר נמחק מהלוח (מגרסה קודמת שלא מחקה את התזכורת)
    try:
        con.execute("""DELETE FROM tasks WHERE kind='parnes'
                       AND note LIKE 'פרנס יום %הכן הדפסה וצור קשר'
                       AND NOT EXISTS (SELECT 1 FROM parnes p
                         WHERE p.donor_id=tasks.donor_id
                         AND ('פרנס יום '||COALESCE(p.date_text,'')||' — הכן הדפסה וצור קשר')=tasks.note)""")
    except Exception: pass
    # השלמת אברכי יששכר־זבולון חסרים (חד-פעמי) — מרשימת האברכים המלאה ששלח המשתמש
    try:
        con.execute("CREATE TABLE IF NOT EXISTS seed_flags(name TEXT PRIMARY KEY)")
        done = con.execute("SELECT 1 FROM seed_flags WHERE name='partners_iz_v7'").fetchone()
        pseed = os.path.join(HERE, 'partners_iz_seed.json')
        if not done and os.path.exists(pseed):
            # ציון החזקה משותפת של האברך חנון יהודה (בליסקו + הרצוג)
            con.execute("""UPDATE partners SET note='מוחזק במשותף ע"י בליסקו שמואל יצחק והרצוג אהרן מרדכי — סה"כ $950'
                           WHERE donor_id=189 AND TRIM(avreich)='חנון יהודה'""")
            # ניקוי איות הפוך "כהן ציון" מגרסאות קודמות (הקנוני הוא "ציון כהן")
            con.execute("DELETE FROM partners WHERE TRIM(avreich)='כהן ציון' AND donor_id IN (335,336,337)")
            # עדכון הסכום המשותף של ציון כהן ל-$1400 (3 האחים מיטמן ביחד)
            con.execute("""UPDATE partners SET amount='1400',
                           note='מוחזק במשותף ע"י 3 האחים מיטמן (אפרים, מאיר, גבריאל) — סה"כ $1400'
                           WHERE TRIM(avreich)='ציון כהן' AND donor_id IN (335,336,337)""")
            na = 0
            for rec in json.load(open(pseed, encoding='utf-8')):
                did = rec.get('donor_id'); av = (rec.get('avreich') or '').strip()
                if not did or not av:
                    continue
                d = con.execute("SELECT last FROM donors WHERE id=?", (did,)).fetchone()
                if not d or (rec.get('last') and d['last'] != rec.get('last')):
                    continue  # שמירה מפני מזהה שהשתנה
                exists = con.execute("SELECT 1 FROM partners WHERE donor_id=? AND TRIM(avreich)=?", (did, av)).fetchone()
                if exists:
                    continue
                con.execute("INSERT INTO partners(donor_id,avreich,start_date,amount,note,active) VALUES(?,?,?,?,?,1)",
                            (did, av, rec.get('start', ''), rec.get('amount', ''), rec.get('note', '')))
                na += 1
            con.execute("INSERT INTO seed_flags(name) VALUES('partners_iz_v7')")
            print(f'  השלמת אברכים: נוספו {na} אברכים')
    except Exception as e:
        print('  שגיאת השלמת אברכים:', e)
    # תיקון כתובות שבורות (רחוב+עיר דבוקים, וקוד מדינה IL שגוי על כתובת אמריקאית)
    try:
        con.execute("CREATE TABLE IF NOT EXISTS seed_flags(name TEXT PRIMARY KEY)")
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='addrfix_v2'").fetchone():
            afix = os.path.join(HERE, 'address_fix_seed.json')
            nf = 0
            if os.path.exists(afix):
                for rec in json.load(open(afix, encoding='utf-8')):
                    cur = con.execute("UPDATE donors SET addr=? WHERE id=? AND last=? AND addr=?",
                                      (rec['new'], rec['id'], rec.get('last', ''), rec['old']))
                    nf += cur.rowcount
            # תיקון קוד מדינה IL→US לכל כתובת עם עיר אמריקאית ברורה (רץ אחרי תיקון הדביקות)
            US_CITY = re.compile(r'\b(Brooklyn|Flushing|Monsey|Lakewood|Los Angeles|Cleveland|Aventura|'
                                 r'Queens|Bronx|Manhattan|Far Rockaway|Valley Village|Teaneck|Great Neck|'
                                 r'Woodmere|Cedarhurst|Passaic|Baltimore|Chicago|Miami|Pittsburgh|'
                                 r'Spring Valley|Monroe|New York)\b', re.I)
            ni = 0
            for row in con.execute("SELECT id, addr FROM donors WHERE COALESCE(addr,'')<>''").fetchall():
                a = row['addr']
                if re.search(r'[א-ת]', a):
                    continue
                segs = a.split(' ::: '); changed = False; out = []
                for s in segs:
                    st = s.strip()
                    if US_CITY.search(st) and re.search(r',?\s*IL\s*$', st):
                        st = re.sub(r',?\s*IL\s*$', ', US', st); changed = True
                    out.append(st)
                if changed:
                    con.execute("UPDATE donors SET addr=? WHERE id=?", (' ::: '.join(out), row['id']))
                    ni += 1
            con.execute("INSERT INTO seed_flags(name) VALUES('addrfix_v2')")
            print(f'  תיקון כתובות: {nf} דביקות, {ni} IL→US')
    except Exception as e:
        print('  שגיאת תיקון כתובות:', e)
    # ניקוי הקדשות פרנס שקיבלו בטעות את שם הקטגוריה (במקום להישאר ריק לשמות התעודה)
    try:
        con.execute("CREATE TABLE IF NOT EXISTS seed_flags(name TEXT PRIMARY KEY)")
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='parnes_ded_clean'").fetchone():
            con.execute("""UPDATE parnes SET dedication='' WHERE TRIM(dedication) IN
                           ('חדר קפה','פרנס קפה','ארוחת בוקר','פרנס לילה','פרנס יום','קפה','בוקר','לילה')""")
            con.execute("INSERT INTO seed_flags(name) VALUES('parnes_ded_clean')")
    except Exception: pass
    # ניקוי קוויטלים שנוצרו בטעות מהקדשת פרנס (שם זהה להקדשת יום פרנס אצל אותו תורם)
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='prayer_parnes_dedup'").fetchone():
            con.execute("""DELETE FROM prayers WHERE EXISTS (
                             SELECT 1 FROM parnes p WHERE p.donor_id=prayers.donor_id
                             AND TRIM(COALESCE(p.dedication,''))=TRIM(COALESCE(prayers.text,''))
                             AND TRIM(COALESCE(p.dedication,''))<>'')""")
            con.execute("INSERT INTO seed_flags(name) VALUES('prayer_parnes_dedup')")
    except Exception: pass
    # טעינת עסקאות Authorize יולי 2026 לטבלת ההתאמה (דף הווב לטיפול)
    try:
        con.execute("CREATE TABLE IF NOT EXISTS seed_flags(name TEXT PRIMARY KEY)")
        try: con.execute("ALTER TABLE recon ADD COLUMN status TEXT DEFAULT 'settled'")
        except Exception: pass
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='recon_jul2026_v6'").fetchone():
            rp = os.path.join(HERE, 'recon_data.json')
            if os.path.exists(rp):
                # רענון מלא — מוחק עסקאות שטרם טופלו ומעלה מחדש עם סטטוס (עברו/לא עברו)
                con.execute("DELETE FROM recon WHERE source='Authorize 07-2026' AND COALESCE(processed,0)=0")
                nr = 0
                for x in json.load(open(rp, encoding='utf-8')):
                    con.execute("""INSERT OR IGNORE INTO recon(tid,first,last,amount,date,addr,city,state,zip,phone,email,recurring,donor_id,category,processed,source,status)
                                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,0,'Authorize 07-2026',?)""",
                                (x['tid'], x['first'], x['last'], x['amount'], x['date'], x['addr'], x['city'], x['state'],
                                 x['zip'], x['phone'], x['email'], x['recurring'], x.get('donor_id'), x.get('category', ''), x.get('status', 'settled')))
                    nr += 1
                con.execute("INSERT INTO seed_flags(name) VALUES('recon_jul2026_v6')")
                print(f'  התאמת Authorize: נטענו {nr} עסקאות')
    except Exception as e:
        print('  שגיאת התאמת Authorize:', e)
    # ייבוא Authorize ינואר–אוגוסט 2026 (חוץ מיולי) לדף ההתאמה — התאמה בזמן ריצה + מילוי שם אנגלי/כתובת
    try:
        ap = os.path.join(HERE, 'authorize_janaug_seed.json')
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='recon_janaug2026_v2'").fetchone() and os.path.exists(ap):
            def _d7(s): return re.sub(r'[^0-9]', '', s or '')[-7:]
            def _ne(s): return re.sub(r'\s+', ' ', (s or '').lower().strip())
            donors = [dict(r) for r in con.execute("SELECT id,last,first,english,email,phone,addr FROM donors")]
            dmap = {d['id']: d for d in donors}
            bymail = {}; byphone = {}; byeng = {}
            for d in donors:
                if d['email']: bymail.setdefault(_ne(d['email']), d['id'])
                for p in re.split(r'[/,]', d['phone'] or ''):
                    if _d7(p): byphone.setdefault(_d7(p), d['id'])
                if d['english']: byeng.setdefault(_ne(d['english']), d['id'])
            con.execute("DELETE FROM recon WHERE source='Authorize 01-08-2026' AND COALESCE(processed,0)=0")
            nr = matched = fen = fad = 0
            for x in json.load(open(ap, encoding='utf-8')):
                did = None
                if x['email'] and _ne(x['email']) in bymail: did = bymail[_ne(x['email'])]
                if not did and x['phone'] and _d7(x['phone']) in byphone: did = byphone[_d7(x['phone'])]
                if not did:
                    nm = _ne(x['first'] + ' ' + x['last'])
                    if nm and nm in byeng: did = byeng[nm]
                con.execute("""INSERT OR IGNORE INTO recon(tid,first,last,amount,date,addr,city,state,zip,phone,email,recurring,donor_id,category,processed,source,status)
                               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,0,'Authorize 01-08-2026',?)""",
                            (x['tid'], x['first'], x['last'], x['amount'], x['date'], x['addr'], x['city'], x['state'],
                             x['zip'], x['phone'], x['email'], x['recurring'], did, x.get('category', ''), x.get('status', 'settled')))
                nr += 1
                if did:
                    matched += 1
                    d = dmap.get(did)
                    if d and not (d['english'] or '').strip() and (x['first'] or x['last']):
                        con.execute("UPDATE donors SET english=? WHERE id=? AND COALESCE(TRIM(english),'')=''", ((x['first'] + ' ' + x['last']).strip(), did))
                        d['english'] = (x['first'] + ' ' + x['last']).strip(); fen += 1
                    if d and not (d['addr'] or '').strip() and x['addr']:
                        fulladdr = ', '.join([p for p in [x['addr'], x['city'], (x['state'] + ' ' + x['zip']).strip(), 'US'] if p])
                        con.execute("UPDATE donors SET addr=? WHERE id=? AND COALESCE(TRIM(addr),'')=''", (fulladdr, did))
                        d['addr'] = fulladdr; fad += 1
            con.execute("INSERT INTO seed_flags(name) VALUES('recon_janaug2026_v2')")
            print(f'  Authorize ינו-אוג: נטענו {nr}, הותאמו {matched}, שם-אנגלי {fen}, כתובות {fad}')
    except Exception as e:
        print('  שגיאת Authorize ינו-אוג:', e)
    # ---- בנק ווסט (Banquest) ינואר–אוגוסט 2026: מיזוג "עברו"+"נדחו", התאמה לפי שם אנגלי ----
    try:
        bp = os.path.join(HERE, 'banquest_seed.json')
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='recon_banquest_v1'").fetchone() and os.path.exists(bp):
            def _ne(s): return re.sub(r'[^a-z0-9]', '', (s or '').lower())
            donors = [dict(r) for r in con.execute("SELECT id,english FROM donors")]
            byeng = {}; bylast = {}
            for d in donors:
                if d['english']:
                    byeng.setdefault(_ne(d['english']), d['id'])
                    toks = d['english'].split()
                    if toks: bylast.setdefault(_ne(toks[-1]), []).append(d['id'])
            con.execute("DELETE FROM recon WHERE source='Banquest 01-08-2026' AND COALESCE(processed,0)=0")
            nr = matched = 0
            for x in json.load(open(bp, encoding='utf-8')):
                did = byeng.get(_ne(x['name']))
                if not did:
                    toks = x['name'].split()
                    cand = bylast.get(_ne(toks[-1]), []) if toks else []
                    if len(cand) == 1: did = cand[0]
                con.execute("""INSERT OR IGNORE INTO recon(tid,first,last,amount,date,addr,city,state,zip,phone,email,recurring,donor_id,category,processed,source,status)
                               VALUES(?,?,?,?,?,'','','','','','',?,?,?,0,'Banquest 01-08-2026',?)""",
                            (x['tid'], x['first'], x['last'], x['amount'], x['date'], x['recurring'], did, x.get('category', ''), x.get('status', 'settled')))
                nr += 1
                if did: matched += 1
            con.execute("INSERT INTO seed_flags(name) VALUES('recon_banquest_v1')")
            print(f'  Banquest ינו-אוג: נטענו {nr}, הותאמו {matched}')
    except Exception as e:
        print('  שגיאת Banquest:', e)
    # רשימת ייעודים/מגביות חופשית (עבור מה) — זריעת דוגמאות שהמשתמש הזכיר
    try:
        con.execute("CREATE TABLE IF NOT EXISTS seed_flags(name TEXT PRIMARY KEY)")
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='campaigns_seed_v1'").fetchone():
            for nm in ['מתנות לאביונים תשפ"ו', 'קמחא דפסחא תשפ"ו', 'סוכות תשפ"ו']:
                con.execute("INSERT OR IGNORE INTO campaigns(name,created) VALUES(?,?)", (nm, today_iso()))
            con.execute("INSERT INTO seed_flags(name) VALUES('campaigns_seed_v1')")
    except Exception as e:
        print('  שגיאת מגביות:', e)
    # ייבוא היסטוריית התרומות של הקבועים 2026 (חד-פעמי) — מקובץ הסיכום ששלח המשתמש
    try:
        con.execute("CREATE TABLE IF NOT EXISTS seed_flags(name TEXT PRIMARY KEY)")
        done = con.execute("SELECT 1 FROM seed_flags WHERE name='donations2026_v2'").fetchone()
        seed2026 = os.path.join(HERE, 'donations_2026_seed.json')
        if not done and os.path.exists(seed2026):
            # טעינה מחדש מלאה — מוחק ייבוא קודם ומעלה את הרשימה המעודכנת (כל הקבועים)
            con.execute("DELETE FROM donations WHERE note='ייבוא 2026'")
            emap = {}
            for row in con.execute("SELECT id, english FROM donors"):
                if row['english']:
                    emap[re.sub(r'\s+', ' ', row['english'].lower().strip())] = row['id']
            n = 0
            for rec in json.load(open(seed2026, encoding='utf-8')):
                did = emap.get(re.sub(r'\s+', ' ', (rec.get('english') or '').lower().strip())) or rec.get('donor_id')
                if not did:
                    continue
                for mo in rec.get('months', []):
                    con.execute("INSERT INTO donations(donor_id,date,amount,category,method,note,paid) VALUES(?,?,?,?,?,?,1)",
                                (did, f"2026-{int(mo):02d}", str(rec.get('amount', '')), rec.get('category', 'קבוע'),
                                 rec.get('method', ''), 'ייבוא 2026'))
                    n += 1
            con.execute("INSERT INTO seed_flags(name) VALUES('donations2026_v2')")
            print(f'  ייבוא תרומות 2026: נוספו {n} תרומות')
    except Exception as e:
        print('  שגיאת ייבוא 2026:', e)
    # תיקון כפילות: תרומת סיכום Authorize שכבר קיים לה חיוב אמיתי (אותו תורם+חודש) — נמחקת
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='authorize_dedup_v1'").fetchone():
            cur = con.execute("""DELETE FROM donations WHERE note='ייבוא 2026' AND method='Authorize' AND id IN (
                SELECT s.id FROM donations s WHERE s.note='ייבוא 2026' AND s.method='Authorize'
                AND EXISTS(SELECT 1 FROM donations r WHERE r.donor_id=s.donor_id AND r.date=s.date
                           AND r.note<>'ייבוא 2026' AND r.method='Authorize'))""")
            con.execute("INSERT INTO seed_flags(name) VALUES('authorize_dedup_v1')")
            print(f'  ניקוי כפילות Authorize↔סיכום: נמחקו {cur.rowcount} תרומות')
    except Exception as e:
        print('  שגיאת dedup Authorize:', e)
    # תיקון קטגוריה: תרומות סיכום שסומנו "יששכר־זבולון" אך התורם אינו יש"ז (tier) — לקבוע
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='summary_iz_fix_v1'").fetchone():
            cur = con.execute("""UPDATE donations SET category='קבוע' WHERE note='ייבוא 2026' AND category='יששכר־זבולון'
                AND donor_id IN (SELECT id FROM donors WHERE COALESCE(tier,'')<>'יששכר_זבולון')""")
            con.execute("INSERT INTO seed_flags(name) VALUES('summary_iz_fix_v1')")
            print(f'  תיקון קטגוריה סיכום (יש"ז->קבוע ללא-יש"ז): {cur.rowcount} תרומות')
    except Exception as e:
        print('  שגיאת תיקון קטגוריה:', e)
    # מיטמן מאיר (#337): תשלומי $585 הם לרכב כולל חצות, לא יששכר־זבולון (רץ אחרי ייבוא התרומות)
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='mittman_585_car_v2'").fetchone():
            con.execute("""UPDATE donations SET category='רכב כולל חצות'
                           WHERE donor_id=337 AND CAST(amount AS REAL)=585""")
            con.execute("""UPDATE donors SET iz_note='תרומה נפרדת: $585/חודש לרכב כולל חצות (לא יש"ז)'
                           WHERE id=337 AND COALESCE(TRIM(iz_note),'')=''""")
            con.execute("INSERT INTO seed_flags(name) VALUES('mittman_585_car_v2')")
    except Exception: pass
    # תיקוני יששכר־זבולון: שטטפלד (ברכה/יצחק) ולאקס — לפי מה שמסר המשתמש
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='statfeld_lax_iz'").fetchone():
            # ברכה שטטפלד #541 — מסומנת יש"ז, והאברך קלפר שייך לה (מועבר מיצחק #543)
            con.execute("UPDATE donors SET tier='יששכר_זבולון' WHERE id=541")
            con.execute("UPDATE partners SET donor_id=541 WHERE donor_id=543 AND TRIM(avreich) LIKE 'קלפר%'")
            # לאקס #283 — עוד $1000/חודש לשני אברכים בכולל יום
            if not con.execute("SELECT 1 FROM partners WHERE donor_id=283 AND avreich LIKE '%כולל יום%'").fetchone():
                con.execute("INSERT INTO partners(donor_id,avreich,amount,note,active) VALUES(283,'שני אברכים — כולל יום','1000','יש\"ז נוסף: $1000/חודש לשני אברכים בכולל יום',1)")
            # יצחק+ברכה שטטפלד — עוד $1000 ליהושע מאיר דויטש לכולל יום (משותף)
            if not con.execute("SELECT 1 FROM partners WHERE donor_id=543 AND avreich LIKE '%דויטש%כולל יום%'").fetchone():
                con.execute("INSERT INTO partners(donor_id,avreich,amount,note,active) VALUES(543,'יהושע מאיר דויטש — כולל יום','1000','יש\"ז לכולל יום — משותף: יצחק וברכה שטטפלד',1)")
            con.execute("INSERT INTO seed_flags(name) VALUES('statfeld_lax_iz')")
        # איחוד יצחק (#543) וברכה (#541) שטטפלד — בעל ואשה, כרטיס אחד
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='statfeld_merge'").fetchone():
            keep, drop = 543, 541
            k = con.execute("SELECT * FROM donors WHERE id=?", (keep,)).fetchone()
            d = con.execute("SELECT * FROM donors WHERE id=?", (drop,)).fetchone()
            if k and d:
                for t in ('pledges','parnes','prayers','donations','contacts_log','tasks','partners','transactions','building'):
                    try: con.execute(f"UPDATE {t} SET donor_id=? WHERE donor_id=?", (keep, drop))
                    except Exception: pass
                try: con.execute("UPDATE files SET ref_id=? WHERE kind='iz' AND ref_id=?", (keep, drop))
                except Exception: pass
                # השלמת שדות ריקים ומיזוג טלפונים
                kd, dd = dict(k), dict(d)
                for col in ('english','email','addr','region','country','zip','city'):
                    if not (kd.get(col) or '').strip() and (dd.get(col) or '').strip():
                        con.execute(f"UPDATE donors SET {col}=? WHERE id=?", (dd[col], keep))
                kp = [p.strip() for p in re.split(r'[/,]', kd.get('phone') or '') if p.strip()]
                for p in re.split(r'[/,]', dd.get('phone') or ''):
                    p = p.strip()
                    if p and p not in kp: kp.append(p)
                con.execute("UPDATE donors SET phone=?, first='יצחק וברכה', tier='יששכר_זבולון' WHERE id=?", (' / '.join(kp), keep))
                con.execute("DELETE FROM donors WHERE id=?", (drop,))
            # סימון הכולל של כל התחייבות
            con.execute("UPDATE partners SET note='יששכר־זבולון · כולל חצות' WHERE donor_id=543 AND avreich LIKE 'קלפר%'")
            con.execute("UPDATE partners SET note='יששכר־זבולון · כולל יום' WHERE donor_id=543 AND avreich LIKE '%דויטש%כולל יום%'")
            con.execute("INSERT INTO seed_flags(name) VALUES('statfeld_merge')")
    except Exception as e:
        print('  שגיאת תיקון שטטפלד/לאקס:', e)
    # בר חיים ברק (#67) — קוויטל כל לילה; ואיחוד ברינדא שוורץ הכפולה
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='barchaim_schwartz'").fetchone():
            con.execute("UPDATE donors SET tier='קוויטל_101' WHERE id=67")
            keep, drop = 536, 535  # ברינדל חנה נשארת, אברהם(Brenda) ממוזג
            k = con.execute("SELECT * FROM donors WHERE id=?", (keep,)).fetchone()
            d = con.execute("SELECT * FROM donors WHERE id=?", (drop,)).fetchone()
            if k and d:
                for t in ('pledges','parnes','prayers','donations','contacts_log','tasks','partners','transactions','building'):
                    try: con.execute(f"UPDATE {t} SET donor_id=? WHERE donor_id=?", (keep, drop))
                    except Exception: pass
                try: con.execute("UPDATE files SET ref_id=? WHERE kind='iz' AND ref_id=?", (keep, drop))
                except Exception: pass
                kd, dd = dict(k), dict(d)
                for col in ('english','email','addr','category','amount','region','country','zip','city'):
                    if not (kd.get(col) or '').strip() and (dd.get(col) or '').strip():
                        con.execute(f"UPDATE donors SET {col}=? WHERE id=?", (dd[col], keep))
                kp = [p.strip() for p in re.split(r'[/,]', kd.get('phone') or '') if p.strip()]
                for p in re.split(r'[/,]', dd.get('phone') or ''):
                    p = p.strip()
                    if p and p not in kp: kp.append(p)
                con.execute("UPDATE donors SET phone=? WHERE id=?", (' / '.join(kp), keep))
                con.execute("DELETE FROM donors WHERE id=?", (drop,))
            con.execute("INSERT INTO seed_flags(name) VALUES('barchaim_schwartz')")
    except Exception as e:
        print('  שגיאת בר חיים/שוורץ:', e)
    # שמות הקוויטל של ברק נחמן בר חיים (#67) — כל לילה — לפי מה שמסר המשתמש
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='barchaim_kvittel_v1'").fetchone():
            if con.execute("SELECT 1 FROM donors WHERE id=67").fetchone():
                con.execute("UPDATE donors SET first='ברק נחמן' WHERE id=67 AND TRIM(COALESCE(first,''))='ברק'")
                con.execute("UPDATE donors SET tier='קוויטל_101' WHERE id=67")
                if not con.execute("SELECT 1 FROM prayers WHERE donor_id=67").fetchone():
                    txt = ("נחמן בן אסתר זאלדע — לברכה והצלחה בכל הענינים\n"
                           "עליזה בת מרים — לבריאות ופרנסה\n"
                           "שירה בת עליזה — לבריאות ושידוך עם בן תורה אמיתי\n"
                           "אריה בן עליזה — הצלחה בלימוד התורה ובשאר עסקיו")
                    con.execute("INSERT INTO prayers(donor_id,name,text,tier) VALUES(67,'',?,?)",
                                (txt, 'קוויטל_101'))
            con.execute("INSERT INTO seed_flags(name) VALUES('barchaim_kvittel_v1')")
    except Exception as e:
        print('  שגיאת קוויטל בר חיים:', e)
    # קוויטל 101 מאנשי הקשר בגוגל — מסמן דרגת "כל לילה" ומייבא את שמות התפילה מההערות
    try:
        seed101 = os.path.join(HERE, 'kvittel101_seed.json')
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='kvittel101_v1'").fetchone() and os.path.exists(seed101):
            def _n(s): return re.sub(r'\s+', ' ', (s or '').strip())
            def _d7(s): return re.sub(r'[^0-9]', '', s or '')[-7:]
            donors = [dict(r) for r in con.execute("SELECT id,last,first,email,phone,tier FROM donors")]
            matched = imported = unlinked = 0
            for e in json.load(open(seed101, encoding='utf-8')):
                el, ef = _n(e.get('last')), _n(e.get('first'))
                emails = [x.lower() for x in (e.get('emails') or [])]
                phones = [x for x in (e.get('phones') or []) if x]
                hit = None
                # 1) טלפון  2) אימייל  3) שם משפחה+פרטי  4) שם משפחה יחיד
                for d in donors:
                    dphs = [_d7(p) for p in re.split(r'[/,]', d['phone'] or '') if _d7(p)]
                    if phones and any(p in dphs for p in phones): hit = d; break
                if not hit and emails:
                    for d in donors:
                        if (d['email'] or '').strip().lower() in emails and d['email']: hit = d; break
                if not hit and el and ef:
                    for d in donors:
                        if _n(d['last']) == el and _n(d['first']).split(' ')[0] == ef.split(' ')[0]: hit = d; break
                if not hit and el:
                    same = [d for d in donors if _n(d['last']) == el]
                    if len(same) == 1: hit = same[0]
                notes = (e.get('notes') or '').strip()
                if hit:
                    matched += 1
                    if (hit['tier'] or '') not in ('יששכר_זבולון', 'קוויטל_101'):
                        con.execute("UPDATE donors SET tier='קוויטל_101' WHERE id=?", (hit['id'],))
                    if notes and not con.execute("SELECT 1 FROM prayers WHERE donor_id=?", (hit['id'],)).fetchone():
                        con.execute("INSERT INTO prayers(donor_id,name,text,tier) VALUES(?,'',?,?)", (hit['id'], notes, 'קוויטל_101'))
                        imported += 1
                elif notes:
                    # אין כרטיס תואם אך יש שמות — נשמר כתפילה לא־משויכת (מופיע ברשימה עם "לא משויך")
                    con.execute("INSERT INTO prayers(donor_id,name,text,tier) VALUES(NULL,?,?,?)", ((el + ' ' + ef).strip(), notes, 'קוויטל_101'))
                    unlinked += 1
            con.execute("INSERT INTO seed_flags(name) VALUES('kvittel101_v1')")
            print(f'  קוויטל 101: הותאמו {matched}, יובאו {imported} שמות, {unlinked} לא־משויכים')
    except Exception as e:
        print('  שגיאת קוויטל 101:', e)
    # קוויטל כללי — כל המסומנים "קוויטל" בגוגל (לא רק 101), עם התאמה גמישה לאיות יידיש
    try:
        seedall = os.path.join(HERE, 'kvittel_all_seed.json')
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='kvittel_all_v1'").fetchone() and os.path.exists(seedall):
            def _d7(s): return re.sub(r'[^0-9]', '', s or '')[-7:]
            def _h(s):  # נירמול עברי — מתעלם מאותיות שווא/ניקוד ואיות כפול (וורצברגר≈ווערצבערגער)
                s = re.sub(r'[^\u0590-\u05ff]', '', s or '').replace('ע', '').replace('א', '').replace('ה', '')
                return re.sub(r'(.)\1+', r'\1', s)
            donors = [dict(r) for r in con.execute("SELECT id,last,first,email,phone,tier FROM donors")]
            for d in donors: d['_l'] = _h(d['last']); d['_f'] = _h(d['first'])
            matched = imported = unlinked = 0
            for e in json.load(open(seedall, encoding='utf-8')):
                emails = [x.lower() for x in (e.get('emails') or [])]
                phones = [x for x in (e.get('phones') or []) if x]
                el, ef = _h(e.get('last')), _h(e.get('first'))
                hit = None
                for d in donors:
                    dphs = [_d7(p) for p in re.split(r'[/,]', d['phone'] or '') if _d7(p)]
                    if phones and any(p in dphs for p in phones): hit = d; break
                if not hit and emails:
                    for d in donors:
                        if (d['email'] or '').strip().lower() in emails and d['email']: hit = d; break
                if not hit and el and ef:
                    for d in donors:
                        if d['_l'] == el and d['_f'][:len(ef)] == ef: hit = d; break
                if not hit and el:
                    same = [d for d in donors if d['_l'] == el]
                    if len(same) == 1: hit = same[0]
                notes = (e.get('notes') or '').strip()
                newtier = 'קוויטל_101' if e.get('is101') else 'קוויטל_שבועי'  # "קוויטל" לבד = שבועי
                if hit:
                    matched += 1
                    if (hit['tier'] or '') not in ('יששכר_זבולון', 'קוויטל_101'):
                        con.execute("UPDATE donors SET tier=? WHERE id=?", (newtier, hit['id']))
                    if notes and not con.execute("SELECT 1 FROM prayers WHERE donor_id=?", (hit['id'],)).fetchone():
                        con.execute("INSERT INTO prayers(donor_id,name,text,tier) VALUES(?,'',?,?)", (hit['id'], notes, newtier))
                        imported += 1
                elif notes:
                    con.execute("INSERT INTO prayers(donor_id,name,text,tier) VALUES(NULL,?,?,?)", ((e.get('last', '') + ' ' + e.get('first', '')).strip(), notes, newtier))
                    unlinked += 1
            con.execute("INSERT INTO seed_flags(name) VALUES('kvittel_all_v1')")
            print(f'  קוויטל כללי: הותאמו {matched}, יובאו {imported} שמות, {unlinked} לא־משויכים')
    except Exception as e:
        print('  שגיאת קוויטל כללי:', e)
    # קוויטל v2 — התאמה דו-כיוונית לשמות פרטיים (אליהו≈אלי) כדי לתפוס מי שלא הותאם
    try:
        seedall = os.path.join(HERE, 'kvittel_all_seed.json')
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='kvittel_all_v2'").fetchone() and os.path.exists(seedall):
            def _d7(s): return re.sub(r'[^0-9]', '', s or '')[-7:]
            def _h(s):
                s = re.sub(r'[^\u0590-\u05ff]', '', s or '').replace('ע', '').replace('א', '').replace('ה', '')
                return re.sub(r'(.)\1+', r'\1', s)
            donors = [dict(r) for r in con.execute("SELECT id,last,first,email,phone,tier FROM donors")]
            for d in donors: d['_l'] = _h(d['last']); d['_f'] = _h(d['first'])
            matched = imported = 0
            for e in json.load(open(seedall, encoding='utf-8')):
                emails = [x.lower() for x in (e.get('emails') or [])]
                phones = [x for x in (e.get('phones') or []) if x]
                el, ef = _h(e.get('last')), _h(e.get('first'))
                hit = None
                for d in donors:
                    dphs = [_d7(p) for p in re.split(r'[/,]', d['phone'] or '') if _d7(p)]
                    if phones and any(p in dphs for p in phones): hit = d; break
                if not hit and emails:
                    for d in donors:
                        if (d['email'] or '').strip().lower() in emails and d['email']: hit = d; break
                if not hit and el and ef:  # התאמה דו-כיוונית: אחד תחילית של השני
                    for d in donors:
                        if d['_l'] == el and (d['_f'].startswith(ef) or ef.startswith(d['_f'])): hit = d; break
                if not hit and el:
                    same = [d for d in donors if d['_l'] == el]
                    if len(same) == 1: hit = same[0]
                notes = (e.get('notes') or '').strip()
                newtier = 'קוויטל_101' if e.get('is101') else 'קוויטל_שבועי'
                if hit:
                    matched += 1
                    if (hit['tier'] or '') not in ('יששכר_זבולון', 'קוויטל_101'):
                        con.execute("UPDATE donors SET tier=? WHERE id=?", (newtier, hit['id']))
                    if notes and not con.execute("SELECT 1 FROM prayers WHERE donor_id=?", (hit['id'],)).fetchone():
                        con.execute("INSERT INTO prayers(donor_id,name,text,tier) VALUES(?,'',?,?)", (hit['id'], notes, newtier))
                        imported += 1
            con.execute("INSERT INTO seed_flags(name) VALUES('kvittel_all_v2')")
            print(f'  קוויטל v2: הותאמו {matched}, יובאו {imported}')
    except Exception as e:
        print('  שגיאת קוויטל v2:', e)
    # קוויטל v3 — שלוש התוויות: יש"ז / 101(כל־לילה) / קוויטל(שבועי), עם עדיפות (לא מוריד דרגה) וייבוא שמות
    try:
        seedall = os.path.join(HERE, 'kvittel_all_seed.json')
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='kvittel_all_v3'").fetchone() and os.path.exists(seedall):
            PRIO = {'יששכר_זבולון': 3, 'קוויטל_101': 2, 'קוויטל_שבועי': 1, 'קוויטל_כללי': 0, '': 0}
            def _d7(s): return re.sub(r'[^0-9]', '', s or '')[-7:]
            def _h(s):
                s = re.sub(r'[^\u0590-\u05ff]', '', s or '').replace('ע', '').replace('א', '').replace('ה', '')
                return re.sub(r'(.)\1+', r'\1', s)
            donors = [dict(r) for r in con.execute("SELECT id,last,first,email,phone,tier FROM donors")]
            for d in donors: d['_l'] = _h(d['last']); d['_f'] = _h(d['first'])
            matched = imported = retier = 0
            for e in json.load(open(seedall, encoding='utf-8')):
                emails = [x.lower() for x in (e.get('emails') or [])]
                phones = [x for x in (e.get('phones') or []) if x]
                el, ef = _h(e.get('last')), _h(e.get('first'))
                hit = None
                for d in donors:
                    dphs = [_d7(p) for p in re.split(r'[/,]', d['phone'] or '') if _d7(p)]
                    if phones and any(p in dphs for p in phones): hit = d; break
                if not hit and emails:
                    for d in donors:
                        if (d['email'] or '').strip().lower() in emails and d['email']: hit = d; break
                if not hit and el and ef:
                    for d in donors:
                        if d['_l'] == el and (d['_f'].startswith(ef) or ef.startswith(d['_f'])): hit = d; break
                if not hit and el:
                    same = [d for d in donors if d['_l'] == el]
                    if len(same) == 1: hit = same[0]
                tt = 'יששכר_זבולון' if e.get('isiz') else ('קוויטל_101' if e.get('is101') else 'קוויטל_שבועי')
                notes = (e.get('notes') or '').strip()
                if hit:
                    matched += 1
                    cur = hit['tier'] or ''
                    if PRIO.get(tt, 1) > PRIO.get(cur, 0):   # רק שדרוג, אף פעם לא הורדה
                        con.execute("UPDATE donors SET tier=? WHERE id=?", (tt, hit['id'])); hit['tier'] = tt; retier += 1
                    if notes and not con.execute("SELECT 1 FROM prayers WHERE donor_id=?", (hit['id'],)).fetchone():
                        con.execute("INSERT INTO prayers(donor_id,name,text,tier) VALUES(?,'',?,?)", (hit['id'], notes, hit['tier'] or tt))
                        imported += 1
            con.execute("INSERT INTO seed_flags(name) VALUES('kvittel_all_v3')")
            print(f'  קוויטל v3: הותאמו {matched}, דרגות {retier}, שמות {imported}')
    except Exception as e:
        print('  שגיאת קוויטל v3:', e)
    # קוויטל v4 — סיד מלא (שמות מ-Notes וגם מ-Custom Field) + התאמה רופפת לוריאנטים באיות (גאלד≈גולד)
    try:
        seedall = os.path.join(HERE, 'kvittel_all_seed.json')
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='kvittel_all_v5'").fetchone() and os.path.exists(seedall):
            PRIO = {'יששכר_זבולון': 3, 'קוויטל_101': 2, 'קוויטל_שבועי': 1, 'קוויטל_כללי': 0, '': 0}
            FIN = str.maketrans('םןץףך', 'מנצפכ')
            def _d7(s): return re.sub(r'[^0-9]', '', s or '')[-7:]
            def _h(s):   # נירמול בסיסי — מתעלם מא/ה/ע ואיות כפול
                s = re.sub(r'[^\u0590-\u05ff]', '', s or '').replace('ע', '').replace('א', '').replace('ה', '')
                return re.sub(r'(.)\1+', r'\1', s)
            def _h2(s):  # נירמול רופף — גם ו/י (אימות קריאה) וסופיות (גאלד↔גולד)
                s = _h(s).translate(FIN).replace('ו', '').replace('י', '')
                return re.sub(r'(.)\1+', r'\1', s)
            donors = [dict(r) for r in con.execute("SELECT id,last,first,email,phone,tier FROM donors")]
            for d in donors:
                d['_l'] = _h(d['last']); d['_f'] = _h(d['first']); d['_l2'] = _h2(d['last']); d['_f2'] = _h2(d['first'])
            entries = json.load(open(seedall, encoding='utf-8'))
            # רענון רשימת הלא־משויכים מהסיד (מהייבוא בלבד) לפני הרצה מחדש
            con.execute("DELETE FROM prayers WHERE donor_id IS NULL AND tier IN ('קוויטל_שבועי','קוויטל_101','יששכר_זבולון','קוויטל_כללי')")
            matched = imported = retier = unlinked = loose = 0
            for e in entries:
                emails = [x.lower() for x in (e.get('emails') or [])]
                phones = [x for x in (e.get('phones') or []) if x]
                el, ef = _h(e.get('last')), _h(e.get('first'))
                el2, ef2 = _h2(e.get('last')), _h2(e.get('first'))
                hit = None; via = ''
                for d in donors:
                    dphs = [_d7(p) for p in re.split(r'[/,]', d['phone'] or '') if _d7(p)]
                    if phones and any(p in dphs for p in phones): hit = d; via = 'phone'; break
                if not hit and emails:
                    for d in donors:
                        if (d['email'] or '').strip().lower() in emails and d['email']: hit = d; via = 'email'; break
                if not hit and el and ef:   # התאמה מדויקת שם משפחה + תחילת שם פרטי
                    for d in donors:
                        if d['_l'] == el and (d['_f'].startswith(ef) or ef.startswith(d['_f'])): hit = d; via = 'name'; break
                if not hit and el2 and ef2:  # התאמה רופפת (וריאנט איות) — שם משפחה רופף + שם פרטי רופף
                    cand = [d for d in donors if d['_l2'] == el2 and (d['_f2'].startswith(ef2) or ef2.startswith(d['_f2']))]
                    if len(cand) == 1: hit = cand[0]; via = 'loose'; loose += 1
                if not hit and el2:          # שם משפחה רופף ייחודי
                    cand = [d for d in donors if d['_l2'] == el2]
                    if len(cand) == 1: hit = cand[0]; via = 'loose-last'; loose += 1
                tt = 'יששכר_זבולון' if e.get('isiz') else ('קוויטל_101' if e.get('is101') else 'קוויטל_שבועי')
                notes = (e.get('notes') or '').strip()
                if hit:
                    matched += 1
                    cur = hit['tier'] or ''
                    if PRIO.get(tt, 1) > PRIO.get(cur, 0):
                        con.execute("UPDATE donors SET tier=? WHERE id=?", (tt, hit['id'])); hit['tier'] = tt; retier += 1
                    if notes and not con.execute("SELECT 1 FROM prayers WHERE donor_id=? AND COALESCE(TRIM(text),'')<>''", (hit['id'],)).fetchone():
                        con.execute("INSERT INTO prayers(donor_id,name,text,tier) VALUES(?,'',?,?)", (hit['id'], notes, hit['tier'] or tt))
                        imported += 1
                elif notes:
                    con.execute("INSERT INTO prayers(donor_id,name,text,tier) VALUES(NULL,?,?,?)", (e.get('display') or (e.get('last', '') + ' ' + e.get('first', '')).strip(), notes, tt))
                    unlinked += 1
            con.execute("INSERT INTO seed_flags(name) VALUES('kvittel_all_v5')")
            print(f'  קוויטל v5: הותאמו {matched} (רופף {loose}), שמות חדשים {imported}, דרגות {retier}, לא־משויכים {unlinked}')
    except Exception as e:
        print('  שגיאת קוויטל v5:', e)
    # קוויטל v6 — סנכרון חוזר לכל אנשי הקשר עם תווית "קוויטל": משייך גם תורמים שנוצרו אחרי הייבואים
    try:
        seedall = os.path.join(HERE, 'kvittel_all_seed.json')
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='kvittel_all_v6'").fetchone() and os.path.exists(seedall):
            PRIO = {'יששכר_זבולון': 3, 'קוויטל_101': 2, 'קוויטל_שבועי': 1, 'קוויטל_כללי': 1, '': 0}
            FIN = str.maketrans('םןץףך', 'מנצפכ')
            def _d7(s): return re.sub(r'[^0-9]', '', s or '')[-7:]
            def _h(s):
                s = re.sub(r'[^\u0590-\u05ff]', '', s or '').replace('ע', '').replace('א', '').replace('ה', '')
                return re.sub(r'(.)\1+', r'\1', s)
            def _h2(s):
                s = _h(s).translate(FIN).replace('ו', '').replace('י', '')
                return re.sub(r'(.)\1+', r'\1', s)
            donors = [dict(r) for r in con.execute("SELECT id,last,first,email,phone,tier FROM donors")]
            for d in donors:
                d['_l'] = _h(d['last']); d['_f'] = _h(d['first']); d['_l2'] = _h2(d['last']); d['_f2'] = _h2(d['first'])
                d['_dph'] = [_d7(p) for p in re.split(r'[/,]', d['phone'] or '') if _d7(p)]
            entries = json.load(open(seedall, encoding='utf-8'))
            newtier = imported = dupfix = 0
            for e in entries:
                emails = [x.lower() for x in (e.get('emails') or [])]
                phones = [x for x in (e.get('phones') or []) if x]
                el, ef = _h(e.get('last')), _h(e.get('first'))
                el2, ef2 = _h2(e.get('last')), _h2(e.get('first'))
                hits = []
                for d in donors:
                    if phones and any(p in d['_dph'] for p in phones): hits.append(d); continue
                    if emails and (d['email'] or '').strip().lower() in emails and d['email']: hits.append(d); continue
                    if el and ef and d['_l'] == el and (d['_f'].startswith(ef) or ef.startswith(d['_f'])): hits.append(d); continue
                if not hits and el2 and ef2:
                    cand = [d for d in donors if d['_l2'] == el2 and (d['_f2'].startswith(ef2) or ef2.startswith(d['_f2']))]
                    if len(cand) == 1: hits = cand
                if not hits and el2:
                    cand = [d for d in donors if d['_l2'] == el2]
                    if len(cand) == 1: hits = cand
                if not hits: continue
                tt = 'יששכר_זבולון' if e.get('isiz') else ('קוויטל_101' if e.get('is101') else 'קוויטל_שבועי')
                notes = (e.get('notes') or '').strip()
                for hit in hits:
                    cur = hit['tier'] or ''
                    if PRIO.get(tt, 1) > PRIO.get(cur, 0):
                        con.execute("UPDATE donors SET tier=? WHERE id=?", (tt, hit['id']))
                        if not cur: newtier += 1
                        else: dupfix += 1
                        hit['tier'] = tt
                    elif not cur:
                        con.execute("UPDATE donors SET tier=? WHERE id=?", (tt, hit['id'])); hit['tier'] = tt; newtier += 1
                    if notes and not con.execute("SELECT 1 FROM prayers WHERE donor_id=? AND COALESCE(TRIM(text),'')<>''", (hit['id'],)).fetchone():
                        con.execute("INSERT INTO prayers(donor_id,name,text,tier) VALUES(?,'',?,?)", (hit['id'], notes, hit['tier'] or tt))
                        imported += 1
            con.execute("INSERT INTO seed_flags(name) VALUES('kvittel_all_v6')")
            print(f'  \u05e7\u05d5\u05d5\u05d9\u05d8\u05dc v6: \u05d3\u05e8\u05d2\u05d5\u05ea \u05d7\u05d3\u05e9\u05d5\u05ea {newtier}, \u05db\u05e4\u05d5\u05dc\u05d9\u05dd {dupfix}, \u05e9\u05de\u05d5\u05ea {imported}')
    except Exception as e:
        print('  \u05e9\u05d2\u05d9\u05d0\u05ea \u05e7\u05d5\u05d5\u05d9\u05d8\u05dc v6:', e)
    # v7 — כללי אינו דרגת תורם אלא רק תצוגת הדפסה — כל קוויטל_כללי הופך לשבועי
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='klali_to_weekly_v1'").fetchone():
            n1 = con.execute("UPDATE donors SET tier='קוויטל_שבועי' WHERE tier='קוויטל_כללי'").rowcount
            n2 = con.execute("UPDATE prayers SET tier='קוויטל_שבועי' WHERE tier='קוויטל_כללי'").rowcount
            con.execute("INSERT INTO seed_flags(name) VALUES('klali_to_weekly_v1')")
            print(f'  מיזוג כללי->שבועי: תורמים {n1}, שמות {n2}')
    except Exception as e:
        print('  שגיאת כללי->שבועי:', e)
    # הדגמה חד‑פעמית — שמות הקוויטל שאסתר ברג שלחה מהאתר (11/7/2026), בעברית מלאה
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='berg_demo_kvittel_he_v1'").fetchone():
            row = con.execute("SELECT id FROM donors WHERE lower(COALESCE(email,''))='estigberg@gmail.com'").fetchone()
            if not row:
                cand = con.execute("SELECT id FROM donors WHERE last LIKE '%ברג%' AND first LIKE '%אסתר%'").fetchall()
                if len(cand) == 1: row = cand[0]
            if row:
                bid = row['id']
                con.execute("DELETE FROM prayers WHERE donor_id=? AND text LIKE '%Esther Tema%'", (bid,))  # הסרת הגרסה באנגלית אם נכנסה
                txt = 'רבקה בת אסתר טעמא לזיווג הגון\nטשערנא זעלדא בת אסתר טעמא לזיווג הגון\nעזריאל בן אסתר טעמא לזיווג הגון'
                if not con.execute("SELECT 1 FROM prayers WHERE donor_id=? AND text=?", (bid, txt)).fetchone():
                    con.execute("INSERT INTO prayers(donor_id,name,text,tier) VALUES(?,'',?,'')", (bid, txt))
                yr = 'תשפ"ו'
                con.execute("UPDATE donors SET kv_month=COALESCE(NULLIF(kv_month,''),?), kv_year=COALESCE(NULLIF(kv_year,''),?) WHERE id=?", ('תמוז', yr, bid))
                print('  קוויטל אסתר ברג (עברית): עודכן')
            con.execute("INSERT INTO seed_flags(name) VALUES('berg_demo_kvittel_he_v1')")
    except Exception as e:
        print('  שגיאת קוויטל ברג:', e)
    # תיקון פרטי קשר — יצחק (איצי) ברגר, לכרטיס הנכון
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='berger_itzik_contact_v1'").fetchone():
            r = con.execute("SELECT id FROM donors WHERE lower(COALESCE(email,''))='mark4realty@verizon.net'").fetchone()
            if not r:
                cand = con.execute("SELECT id FROM donors WHERE last LIKE '%ברגר%' AND first LIKE '%איצי%'").fetchall()
                if len(cand) == 1: r = cand[0]
            if r:
                con.execute("UPDATE donors SET email=?, phone=?, addr=?, city=?, country=?, zip=?, addr_ok=1 WHERE id=?",
                            ('mark4realty@verizon.net', '+1 917-803-1478', 'P.O. Box 33104', 'Brooklyn', 'US', '11204', r['id']))
                print('  פרטי יצחק ברגר: עודכנו')
            con.execute("INSERT INTO seed_flags(name) VALUES('berger_itzik_contact_v1')")
    except Exception as e:
        print('  שגיאת פרטי ברגר:', e)
    # איחוד כרטיסי יצחק (איצי) ברגר + סכומים $500 + שותפות עם גוטמן
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='berger_merge_v2'").fetchone():
            cands = con.execute("SELECT id FROM donors WHERE (last LIKE 'ברג%' OR last LIKE 'בערג%') AND (first LIKE '%יצחק%' OR first LIKE '%איצי%')").fetchall()
            ids = [r['id'] for r in cands]
            keep = None
            if len(ids) == 2:
                withp = [i for i in ids if con.execute('SELECT 1 FROM partners WHERE donor_id=?', (i,)).fetchone()]
                keep = withp[0] if withp else ids[0]
                drop = [i for i in ids if i != keep][0]
                k = con.execute('SELECT * FROM donors WHERE id=?', (keep,)).fetchone()
                d = con.execute('SELECT * FROM donors WHERE id=?', (drop,)).fetchone()
                if k and d:
                    for t in ('pledges','parnes','prayers','donations','contacts_log','tasks','partners','transactions','building'):
                        try: con.execute(f'UPDATE {t} SET donor_id=? WHERE donor_id=?', (keep, drop))
                        except Exception: pass
                    try: con.execute('UPDATE files SET ref_id=? WHERE ref_id=?', (keep, drop))
                    except Exception: pass
                    kp = [p.strip() for p in re.split(r'[/,]', dict(k).get('phone') or '') if p.strip()]
                    for p in re.split(r'[/,]', dict(d).get('phone') or ''):
                        p = p.strip()
                        if p and p not in kp: kp.append(p)
                    con.execute('UPDATE donors SET phone=? WHERE id=?', (' / '.join(kp), keep))
                    con.execute('DELETE FROM donors WHERE id=?', (drop,))
            elif len(ids) == 1:
                keep = ids[0]
            if keep:
                con.execute("UPDATE donors SET email=?, addr=?, city=?, country=?, zip=?, addr_ok=1, tier=? WHERE id=?",
                            ('mark4realty@verizon.net', 'P.O. Box 33104', 'Brooklyn', 'NY', '11204', 'יששכר_זבולון', keep))
                g = con.execute("SELECT id FROM donors WHERE lower(COALESCE(email,''))='sam4gutman@yahoo.com'").fetchone()
                if not g:
                    gc = con.execute("SELECT id FROM donors WHERE last LIKE '%גוטמן%' AND first LIKE '%בצלאל%'").fetchall()
                    if len(gc) == 1: g = gc[0]
                gid = g['id'] if g else None
                con.execute("UPDATE partners SET amount='500' WHERE donor_id=? AND avreich LIKE '%ירבלום%'", (keep,))
                if gid:
                    con.execute("UPDATE partners SET amount='500', partner_with=?, partner_with_id=? WHERE donor_id=? AND avreich LIKE '%ירבלום%'", ('ברגר יצחק (איצי)', keep, gid))
                    con.execute("UPDATE partners SET partner_with=?, partner_with_id=? WHERE donor_id=? AND avreich LIKE '%ירבלום%'", ('גוטמן בצלאל', gid, keep))
                print('  איחוד ברגר: בוצע (keep=%s)' % keep)
            con.execute("INSERT INTO seed_flags(name) VALUES('berger_merge_v2')")
    except Exception as e:
        print('  שגיאת איחוד ברגר:', e)
    # חלוקת סכומים בין שותפים לאותו אברך — בליסקו $500 / הרצוג $450 על חנון יהודה (הוקלד הסכום הכולל בטעות)
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='blisko_herzog_split_v1'").fetchone():
            con.execute("UPDATE partners SET amount='500' WHERE COALESCE(active,1)<>0 AND avreich LIKE '%חנון%' AND donor_id IN (SELECT id FROM donors WHERE last LIKE '%בליסק%')")
            con.execute("UPDATE partners SET amount='450' WHERE COALESCE(active,1)<>0 AND avreich LIKE '%חנון%' AND donor_id IN (SELECT id FROM donors WHERE last LIKE '%הרצוג%' AND first LIKE '%אהרן%')")
            con.execute("INSERT INTO seed_flags(name) VALUES('blisko_herzog_split_v1')")
            print('  חלוקת בליסקו/הרצוג: בוצע')
    except Exception as e:
        print('  שגיאת חלוקת בליסקו/הרצוג:', e)
    # טפלר + גולד יעקב — נותנים ביחד מאותו עסק סכום אחד (joint), לא לחבר
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='tepler_gold_joint_v1'").fetchone():
            con.execute("UPDATE partners SET joint=1 WHERE COALESCE(active,1)<>0 AND avreich LIKE '%שפירא%' AND donor_id IN (SELECT id FROM donors WHERE last LIKE '%טפלר%' OR (last LIKE '%גולד%' AND first LIKE '%יעקב%'))")
            con.execute("INSERT INTO seed_flags(name) VALUES('tepler_gold_joint_v1')")
            print('  טפלר/גולד משותף: בוצע')
    except Exception as e:
        print('  שגיאת טפלר/גולד:', e)
    # הדגמה — קוויטל שבועי של אלון קאהן (loxmejr@aol.com) בעברית מסודר
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='elon_kahn_kvittel_v1'").fetchone():
            r = con.execute("SELECT id, tier FROM donors WHERE lower(COALESCE(email,''))='loxmejr@aol.com'").fetchone()
            if not r:
                cand = con.execute("SELECT id, tier FROM donors WHERE last LIKE '%קאהן%' AND first LIKE '%אלון%'").fetchall()
                if len(cand) == 1: r = cand[0]
            if r:
                kid = r['id']
                if not (r['tier'] or '').strip():
                    con.execute("UPDATE donors SET tier='קוויטל_שבועי' WHERE id=?", (kid,))
                txt = 'שמעון יואל חיים בן פעסי — לברכת ילדים ולפרנסה טובה\nתמר ברכה בת מלכה — לזרע של קיימא, לפרנסה טובה ולרפואה שלמה\nמלכה בת הענא — לפרנסה טובה, לבריאות איתנה ולנחת מהילדים\nשמואל אהרן בן פרימעט — לבריאות איתנה'
                if not con.execute("SELECT 1 FROM prayers WHERE donor_id=? AND text=?", (kid, txt)).fetchone():
                    con.execute("INSERT INTO prayers(donor_id,name,text,tier) VALUES(?,'',?,'קוויטל_שבועי')", (kid, txt))
                print('  קוויטל אלון קאהן: נוסף')
            con.execute("INSERT INTO seed_flags(name) VALUES('elon_kahn_kvittel_v1')")
    except Exception as e:
        print('  שגיאת קוויטל אלון:', e)
    # הדגמה — קוויטל שבועי של דניאל הדר בעברית מסודר
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='daniel_hadar_kvittel_v1'").fetchone():
            cand = con.execute("SELECT id, tier FROM donors WHERE last LIKE '%הדר%' AND first LIKE '%דניאל%'").fetchall()
            if len(cand) == 1:
                kid = cand[0]['id']
                if not (cand[0]['tier'] or '').strip():
                    con.execute("UPDATE donors SET tier='קוויטל_שבועי' WHERE id=?", (kid,))
                txt = 'ירון חגג ומשפחתו — לכל הברכות\nדניאל בן יעל — למצוא דירה בחריש\nטובה רבקה בת הינדא יוסיפא — לשמחה\nגאלדא בת חיה רחל — לזיווג הגון'
                if not con.execute("SELECT 1 FROM prayers WHERE donor_id=? AND text=?", (kid, txt)).fetchone():
                    con.execute("INSERT INTO prayers(donor_id,name,text,tier) VALUES(?,'',?,'קוויטל_שבועי')", (kid, txt))
                print('  קוויטל דניאל הדר: נוסף')
            con.execute("INSERT INTO seed_flags(name) VALUES('daniel_hadar_kvittel_v1')")
    except Exception as e:
        print('  שגיאת קוויטל דניאל:', e)
    # שטטפלד בנימין ויואל — אחים בשותפות יש"ז מאותו עסק (לציין בשני הכרטיסים)
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='statfeld_bros_v1'").fetchone():
            con.execute("UPDATE donors SET iz_note=? WHERE last LIKE '%שטטפלד%' AND COALESCE(first,'') LIKE '%בנימין%'",
                        ('שותפות יש"ז עם אחיו יואל שטטפלד — נותנים ביחד מאותו עסק',))
            con.execute("UPDATE donors SET iz_note=? WHERE last LIKE '%שטטפלד%' AND COALESCE(first,'') LIKE '%יואל%'",
                        ('שותפות יש"ז עם אחיו בנימין שטטפלד — נותנים ביחד מאותו עסק (מחזיקים את האברך חבה יחזקאל)',))
            con.execute("""UPDATE partners SET note='במשותף עם אחיו יואל שטטפלד — אותו עסק'
                           WHERE active!=0 AND donor_id IN (SELECT id FROM donors WHERE last LIKE '%שטטפלד%' AND COALESCE(first,'') LIKE '%בנימין%')""")
            con.execute("INSERT INTO seed_flags(name) VALUES('statfeld_bros_v1')")
    except Exception as e:
        print('  שגיאת שטטפלד אחים:', e)
    # טאובנפלד מרים — כל אברך שהיא מחזיקה הוא $1300 לחודש (תוקן מ-800)
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='taubenfeld_1300_v1'").fetchone():
            con.execute("""UPDATE partners SET amount='1300'
                           WHERE active!=0 AND donor_id IN
                           (SELECT id FROM donors WHERE last LIKE '%אובנפלד%' AND COALESCE(first,'') LIKE '%מרים%')""")
            con.execute("INSERT INTO seed_flags(name) VALUES('taubenfeld_1300_v1')")
    except Exception as e:
        print('  שגיאת טאובנפלד:', e)
    # תזכורות פרנס פתוחות עם תאריך שעבר (שבוע-לפני שכבר חלף) — לקבוע להיום, לא בעבר
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='parnes_reminder_today_v1'").fetchone():
            con.execute("UPDATE tasks SET due_date=? WHERE kind='parnes' AND (done IS NULL OR done=0) AND COALESCE(due_date,'')<>'' AND due_date<?",
                        (today_iso(), today_iso()))
            con.execute("INSERT INTO seed_flags(name) VALUES('parnes_reminder_today_v1')")
    except Exception as e:
        print('  שגיאת תזכורות פרנס:', e)
    # תרומות היסטוריות שיובאו (2026) הן תשלומים שכבר עברו — לסמן כ"שולם"
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='donations_paid_v1'").fetchone():
            con.execute("UPDATE donations SET paid=1 WHERE note='ייבוא 2026' AND COALESCE(paid,0)=0")
            con.execute("INSERT INTO seed_flags(name) VALUES('donations_paid_v1')")
    except Exception as e:
        print('  שגיאת סימון שולם 2026:', e)
    # ניקוי כתובות: הפרדת מילים דבוקות (StBrooklyn→St, Brooklyn), מספר דבוק, ומדינה כפולה
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='addr_cleanup_v1'").fetchone():
            SUF = r'St|st|Ave|ave|Avenue|avenue|Rd|Road|Dr|Drive|Blvd|Ln|Lane|Ct|Court|Pl|Place|Way|Terrace|Parkway|Pkwy|Hwy|Highway|highway|Broadway|Street|street|Park'
            def _clean(s):
                s = re.sub(r'\b(' + SUF + r')([A-Z][a-z])', r'\1, \2', s)       # StBrooklyn -> St, Brooklyn
                s = re.sub(r'(\d(?:st|nd|rd|th))([A-Z][a-z])', r'\1 \2', s)      # 27thBrooklyn -> 27th Brooklyn
                s = re.sub(r'(\d)([A-Z][a-z])', r'\1 \2', s)                     # 3740Brooklyn -> 3740 Brooklyn
                s = re.sub(r'([\u0590-\u05ff])(\d)', r'\1 \2', s)                # יחזקאל41 -> יחזקאל 41
                s = re.sub(r'\b([A-Z]{2}),\s*\1\b', r'\1', s)                    # NY, NY -> NY
                s = re.sub(r'\s{2,}', ' ', s).strip()
                return s
            n = 0
            for row in con.execute("SELECT id, addr FROM donors WHERE COALESCE(addr,'')<>''").fetchall():
                new = ' ::: '.join(_clean(p) for p in row['addr'].split(' ::: '))
                if new != row['addr']:
                    con.execute("UPDATE donors SET addr=? WHERE id=?", (new, row['id']))
                    n += 1
            con.execute("INSERT INTO seed_flags(name) VALUES('addr_cleanup_v1')")
            print(f'  ניקוי כתובות: תוקנו {n}')
    except Exception as e:
        print('  שגיאת ניקוי כתובות:', e)
    # כתובות ארה"ב בפורמט תקין מהשדות המובנים של גוגל (רחוב, עיר, מדינה, מיקוד) — מספר בהתחלה
    try:
        seedm = os.path.join(HERE, 'address_maps_seed.json')
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='address_maps_v1'").fetchone() and os.path.exists(seedm):
            def _d7(s): return re.sub(r'[^0-9]', '', s or '')[-7:]
            def _h(s):
                s = re.sub(r'[^\u0590-\u05ff]', '', s or '').replace('ע', '').replace('א', '').replace('ה', '')
                return re.sub(r'(.)\1+', r'\1', s)
            donors = [dict(r) for r in con.execute("SELECT id,last,first,email,phone,region FROM donors")]
            for d in donors: d['_l'] = _h(d['last']); d['_f'] = _h(d['first'])
            fixed = 0
            for e in json.load(open(seedm, encoding='utf-8')):
                emails = [x.lower() for x in (e.get('emails') or [])]
                phones = [x for x in (e.get('phones') or []) if x]
                el, ef = _h(e.get('last')), _h(e.get('first'))
                hit = None
                for d in donors:
                    dphs = [_d7(p) for p in re.split(r'[/,]', d['phone'] or '') if _d7(p)]
                    if phones and any(p in dphs for p in phones): hit = d; break
                if not hit and emails:
                    for d in donors:
                        if (d['email'] or '').strip().lower() in emails and d['email']: hit = d; break
                if not hit and el and ef:  # שם מלא בלבד (בלי fallback על שם משפחה יחיד — למנוע שיוך כתובת שגוי)
                    for d in donors:
                        if d['_l'] == el and d['_f'][:len(ef)] == ef: hit = d; break
                if hit and (hit['region'] or '') != 'il':
                    con.execute("UPDATE donors SET addr=?, addr_ok=1 WHERE id=?", (e['addr'], hit['id']))
                    fixed += 1
            con.execute("INSERT INTO seed_flags(name) VALUES('address_maps_v1')")
            print(f'  כתובות ארה"ב בפורמט תקין: {fixed}')
    except Exception as e:
        print('  שגיאת כתובות מפות:', e)
    # כתובות v2 — פסיק בין מספר דירה לעיר (4506 Brooklyn → 4506, Brooklyn); רק אם לא נערכה ידנית
    try:
        seedm = os.path.join(HERE, 'address_maps_seed.json')
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='address_maps_v2'").fetchone() and os.path.exists(seedm):
            def _d7(s): return re.sub(r'[^0-9]', '', s or '')[-7:]
            def _h(s):
                s = re.sub(r'[^\u0590-\u05ff]', '', s or '').replace('ע', '').replace('א', '').replace('ה', '')
                return re.sub(r'(.)\1+', r'\1', s)
            donors = [dict(r) for r in con.execute("SELECT id,last,first,email,phone,addr FROM donors")]
            for d in donors: d['_l'] = _h(d['last']); d['_f'] = _h(d['first'])
            fixed = 0
            for e in json.load(open(seedm, encoding='utf-8')):
                old, new = e.get('addr_old'), e.get('addr')
                if not old or not new or old == new: continue
                emails = [x.lower() for x in (e.get('emails') or [])]
                phones = [x for x in (e.get('phones') or []) if x]
                el, ef = _h(e.get('last')), _h(e.get('first'))
                hit = None
                for d in donors:
                    dphs = [_d7(p) for p in re.split(r'[/,]', d['phone'] or '') if _d7(p)]
                    if phones and any(p in dphs for p in phones): hit = d; break
                if not hit and emails:
                    for d in donors:
                        if (d['email'] or '').strip().lower() in emails and d['email']: hit = d; break
                if not hit and el and ef:
                    for d in donors:
                        if d['_l'] == el and (d['_f'].startswith(ef) or ef.startswith(d['_f'])): hit = d; break
                if hit and (hit['addr'] or '').strip() == old:   # רק אם לא נערכה ידנית מאז
                    con.execute("UPDATE donors SET addr=? WHERE id=?", (new, hit['id']))
                    fixed += 1
            con.execute("INSERT INTO seed_flags(name) VALUES('address_maps_v2')")
            print(f'  כתובות פסיק v2: תוקנו {fixed}')
    except Exception as e:
        print('  שגיאת כתובות v2:', e)
    # פיצול כתובות ארה"ב מאוחדות למשבצות נפרדות: רחוב+מספר / עיר / מדינה / מיקוד
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='addr_split_v3'").fetchone():
            todo = con.execute("SELECT id,addr,city,country,zip,region FROM donors WHERE COALESCE(addr,'')<>''").fetchall()
            n = 0
            for d in todo:
                addr = d['addr'] or ''
                if (d['region'] or '') == 'il':
                    continue
                if re.search(r',\s*IL\s*$', addr) or 'ישראל' in addr:   # ישראל בסוף (לא מבלבל עם אילינוי) — לא נוגעים
                    continue
                if re.search(r'[\u0590-\u05ff]', addr.split(':::')[0].split(',')[0]):   # רחוב בעברית
                    continue
                if not re.search(r'\b\d{5}(?:-\d{4})?\b', addr):     # אין מיקוד — כנראה רחוב בלבד
                    continue
                st, ci, state, zp, co = split_us_addr(addr)
                if not st:
                    continue
                mdina = state or (co if co and co not in ('US', 'USA') else '')
                sets = ['addr=?']; vals = [st]                       # הרחוב תמיד מנוקה
                if ci and not (d['city'] or '').strip(): sets.append('city=?'); vals.append(ci)
                if mdina and not (d['country'] or '').strip(): sets.append('country=?'); vals.append(mdina)
                if zp and not (d['zip'] or '').strip(): sets.append('zip=?'); vals.append(zp)
                con.execute("UPDATE donors SET " + ",".join(sets) + " WHERE id=?", vals + [d['id']])
                n += 1
            con.execute("INSERT INTO seed_flags(name) VALUES('addr_split_v3')")
            print(f'  פיצול כתובות ארה"ב: {n}')
    except Exception as e:
        print('  שגיאת פיצול כתובות:', e)
    # מילוי "ערוץ חיוב" אוטומטי לפי אמצעי התשלום בתרומות (Banquest→בנק ווסט, Authorize→אותורייז וכו')
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='autochannel_v1'").fetchone():
            import collections
            M2C = {'banquest': 'בנק_ווסט', 'בנק ווסט': 'בנק_ווסט', 'authorize': 'אותורייז',
                   'checks': 'צק', 'check': 'צק', 'zelle': 'Zelle', 'ach': 'העברה_בנקאית',
                   'bank transfer': 'העברה_בנקאית', 'העברה בנקאית': 'העברה_בנקאית',
                   'donors fund': 'דונורס_פאנד', 'ojc': 'OJC', 'נדרים': 'נדרים', 'pledger': 'Pledger'}
            methods = collections.defaultdict(collections.Counter)
            for r in con.execute("SELECT donor_id, method FROM donations WHERE COALESCE(method,'')<>''"):
                ch = M2C.get((r['method'] or '').strip().lower())
                if ch and r['donor_id']:
                    methods[r['donor_id']][ch] += 1
            nch = npm = 0
            for did, cnt in methods.items():
                ch = cnt.most_common(1)[0][0]
                dr = con.execute("SELECT channel FROM donors WHERE id=?", (did,)).fetchone()
                if dr and not (dr['channel'] or '').strip():
                    con.execute("UPDATE donors SET channel=? WHERE id=?", (ch, did)); nch += 1
                cur2 = con.execute("UPDATE partners SET method=? WHERE donor_id=? AND active<>0 AND COALESCE(method,'')=''", (ch, did))
                npm += cur2.rowcount
            con.execute("INSERT INTO seed_flags(name) VALUES('autochannel_v1')")
            print(f'  ערוץ חיוב אוטומטי: תורמים {nch}, אברכים {npm}')
    except Exception as e:
        print('  שגיאת ערוץ חיוב:', e)

    # תאריך תחילת שותפות יש"ז לכל אברך — מקובץ האקסל ששלח המשתמש
    try:
        izp = os.path.join(HERE, 'iz_startdate_seed.json')
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='iz_startdate_v2'").fetchone() and os.path.exists(izp):
            def _hz(s):
                s = re.sub(r'[^\u0590-\u05ff ]', '', s or '').replace('\u05e2', '').replace('\u05d0', '').replace('\u05d4', '')
                return re.sub(r'(.)\1+', r'\1', s)
            def _tk(s): return set(t for t in (_hz(x) for x in (s or '').split()) if len(t) >= 2)
            def _tk2(s): return set(x for x in (re.sub(r'[\u05d5\u05d9]', '', t) for t in _tk(s)) if len(x) >= 2)
            donors = [dict(r) for r in con.execute("SELECT id,last,first FROM donors")]
            lastcount = {}
            for d in donors:
                d['_t'] = _tk(d['last'] + ' ' + (d['first'] or '')); d['_t2'] = _tk2(d['last'] + ' ' + (d['first'] or ''))
                d['_lh'] = _hz(d['last']); lastcount[d['_lh']] = lastcount.get(d['_lh'], 0) + 1
            parts = {}
            for p in con.execute("SELECT id,donor_id,avreich,amount,start_date FROM partners WHERE active<>0"):
                parts.setdefault(p['donor_id'], []).append(dict(p))
            nset = 0
            for e in json.load(open(izp, encoding='utf-8')):
                zt = _tk(e['zevulun']); zt2 = _tk2(e['zevulun']); best = None; bs = 0
                for d in donors:
                    sc = max(len(zt & d['_t']), len(zt2 & d['_t2']))
                    if sc > bs: bs = sc; best = d
                if bs < 2:
                    cand = [d for d in donors if d['_lh'] and len(d['_lh']) >= 3 and d['_lh'] in zt and lastcount[d['_lh']] == 1]
                    if len(cand) == 1: best = cand[0]
                    else: continue
                if not best: continue
                pl = parts.get(best['id'], [])
                if not pl: continue
                at = _tk(e['av_last'] + ' ' + e['av_first']); chosen = None
                if len(pl) == 1:
                    chosen = pl[0]
                else:
                    for p in pl:
                        if at & _tk(p['avreich']): chosen = p; break
                    if not chosen:
                        for p in pl:
                            try:
                                if abs(float(p['amount']) - float(e['amount'])) < 1: chosen = p; break
                            except Exception: pass
                    if not chosen: chosen = pl[0]
                if chosen and not (chosen['start_date'] or '').strip():
                    con.execute("UPDATE partners SET start_date=? WHERE id=?", (e['start'], chosen['id']))
                    chosen['start_date'] = e['start']; nset += 1
            con.execute("INSERT INTO seed_flags(name) VALUES('iz_startdate_v2')")
            print(f'  \u05ea\u05d0\u05e8\u05d9\u05da \u05d4\u05ea\u05d7\u05dc\u05ea \u05d9\u05e9"\u05d6: {nset}')
    except Exception as e:
        print('  iz start error:', e)

    # \u05d0\u05d9\u05d7\u05d5\u05d3 \u05d0\u05d1\u05e8\u05db\u05d9\u05dd \u05db\u05e4\u05d5\u05dc\u05d9\u05dd (\u05d0\u05d5\u05ea\u05d5 \u05e9\u05dd \u05d1\u05e1\u05d3\u05e8 \u05de\u05d9\u05dc\u05d9\u05dd \u05e9\u05d5\u05e0\u05d4 \u05d0\u05e6\u05dc \u05d0\u05d5\u05ea\u05d5 \u05ea\u05d5\u05e8\u05dd)
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='partner_dedup_v1'").fetchone():
            import collections as _co
            def _pn(s):
                s = re.sub(r'[^\u0590-\u05ff ]', '', s or '')
                return ' '.join(sorted(w for w in s.split() if len(w) >= 2))
            byd = _co.defaultdict(list)
            for p in con.execute("SELECT id,donor_id,avreich,amount,method,start_date FROM partners WHERE active<>0"):
                byd[p['donor_id']].append(dict(p))
            ndel = 0
            def _sc(p): return (1 if (p['amount'] or '').strip() else 0) + (1 if (p['start_date'] or '').strip() else 0) + (1 if (p['method'] or '').strip() else 0)
            for did, pl in byd.items():
                g = _co.defaultdict(list)
                for p in pl:
                    n = _pn(p['avreich'])
                    if n: g[n].append(p)
                for n, grp in g.items():
                    if len(grp) <= 1: continue
                    grp.sort(key=lambda p: (-_sc(p), p['id']))
                    for p in grp[1:]:
                        con.execute("DELETE FROM partners WHERE id=?", (p['id'],)); ndel += 1
            con.execute("INSERT INTO seed_flags(name) VALUES('partner_dedup_v1')")
            print(f'  dedup avreichim: {ndel}')
    except Exception as e:
        print('  partner dedup error:', e)

    # מיילים שכבר תויקו לפני שהיה תמצות — מקצרים לשורה אחת ומורידים את השרשור שלנו
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='maillog_gist_v3'").fetchone():
            import gmail_intake as _gi
            nfix = 0
            for r in con.execute("SELECT id,summary,body FROM contacts_log WHERE channel='אימייל'"):
                s = r['summary'] or ''
                head = s[1:].strip() if s.startswith('📧') else s
                if '\n' in head:
                    subj, rest = head.split('\n', 1)
                elif ' — ' in head:
                    subj, rest = head.split(' — ', 1)
                else:
                    subj, rest = head, ''
                src = (r['body'] or '').strip() or rest       # הטקסט המלא ששמור, אחרת מה שבתקציר
                if not src.strip():
                    continue
                gist = _gi._gist_he(subj, src)
                new_s = '📧 ' + subj.strip() + ((' — ' + gist) if gist else '')
                con.execute("UPDATE contacts_log SET summary=?, body=? WHERE id=?",
                            (new_s, _gi._strip_quoted(src), r['id']))
                nfix += 1
            con.execute("INSERT INTO seed_flags(name) VALUES('maillog_gist_v3')")
            print(f'  תמצות מיילים קיימים: {nfix}')
    except Exception as e:
        print('  mail gist error:', e)

    con.commit(); con.close()

def get_all():
    con = db(); c = con.cursor()
    donors = [dict(r) for r in c.execute("SELECT * FROM donors ORDER BY last,first")]
    byid = {d['id']: d for d in donors}
    for d in donors:
        d['pledges'] = []; d['parnes'] = []; d['prayers'] = []
        d['donations'] = []; d['contacts'] = []; d['tasks'] = []; d['partners'] = []; d['transactions'] = []; d['building'] = []
    try:
        for r in c.execute("SELECT * FROM building ORDER BY id"):
            if r['donor_id'] in byid: byid[r['donor_id']]['building'].append(dict(r))
    except Exception: pass
    for r in c.execute("SELECT * FROM pledges"):
        if r['donor_id'] in byid: byid[r['donor_id']]['pledges'].append(dict(r))
    for r in c.execute("SELECT * FROM parnes"):
        if r['donor_id'] in byid: byid[r['donor_id']]['parnes'].append(dict(r))
    unlinked = []
    for r in c.execute("SELECT * FROM prayers"):
        if r['donor_id'] in byid:
            byid[r['donor_id']]['prayers'].append({'id': r['id'], 'text': r['text'], 'tier': r['tier']})
        else:
            unlinked.append({'id': r['id'], 'name': r['name'], 'text': r['text'], 'tier': r['tier']})
    for r in c.execute("SELECT * FROM donations ORDER BY date DESC"):
        if r['donor_id'] in byid:
            dn = dict(r); dn['hmonth'] = greg_to_heb_monthyear(r['date'])
            byid[r['donor_id']]['donations'].append(dn)
    for r in c.execute("SELECT * FROM contacts_log ORDER BY date DESC"):
        if r['donor_id'] in byid: byid[r['donor_id']]['contacts'].append(dict(r))
    general_tasks = []
    for r in c.execute("SELECT * FROM tasks ORDER BY due_date"):
        if r['donor_id'] in byid: byid[r['donor_id']]['tasks'].append(dict(r))
        elif not r['donor_id']: general_tasks.append(dict(r))   # משימה חופשית בלי תורם
    for r in c.execute("SELECT * FROM partners"):
        if r['donor_id'] in byid: byid[r['donor_id']]['partners'].append(dict(r))
    try:
        for r in c.execute("SELECT * FROM transactions ORDER BY date DESC, id DESC"):
            if r['donor_id'] in byid:
                tr = dict(r); tr['hmonth'] = greg_to_heb_monthyear(r['date'])
                byid[r['donor_id']]['transactions'].append(tr)
    except Exception:
        pass
    for d in donors: d['files'] = []
    parnes_files, contact_files, task_files, don_files, tx_files = {}, {}, {}, {}, {}
    try:
        for r in c.execute("SELECT id,kind,ref_id,name,mime FROM files"):
            meta = {'id': r['id'], 'name': r['name'], 'mime': r['mime']}
            if r['kind'] == 'iz' and r['ref_id'] in byid:
                byid[r['ref_id']]['files'].append(meta)
            elif r['kind'] == 'parnes':
                parnes_files.setdefault(r['ref_id'], []).append(meta)
            elif r['kind'] == 'contact':      # אסמכתאות ליומן הקשר (צילומי מסך, הודעות קוליות)
                contact_files.setdefault(r['ref_id'], []).append(meta)
            elif r['kind'] == 'task':         # אסמכתאות למשימה
                task_files.setdefault(r['ref_id'], []).append(meta)
            elif r['kind'] == 'donation':     # אסמכתאות לתרומה (צ'ק, שובר אשראי)
                don_files.setdefault(r['ref_id'], []).append(meta)
            elif r['kind'] == 'transaction':  # אסמכתאות לחיוב
                tx_files.setdefault(r['ref_id'], []).append(meta)
        for d in donors:
            for p in d['parnes']:
                p['files'] = parnes_files.get(p['id'], [])
            for cl in d['contacts']:
                cl['files'] = contact_files.get(cl['id'], [])
            for tk in d['tasks']:
                tk['files'] = task_files.get(tk['id'], [])
            for dn in d['donations']:
                dn['files'] = don_files.get(dn['id'], [])
            for tx in d['transactions']:
                tx['files'] = tx_files.get(tx['id'], [])
        for tk in general_tasks:
            tk['files'] = task_files.get(tk['id'], [])
    except Exception:
        pass
    con.close()
    return donors, unlinked, general_tasks

# קיבוץ מקורות ההתאמה למשבצות נפרדות בדף החיובים
RECON_GROUPS = [
    ('authorize', 'אוטרייז', '💳'),
    ('banquest',  'בנק ווסט', '🏦'),
    ('checks',    'צ׳קים', '🧾'),
    ('transfers', 'העברות בנקאיות וזל', '🔁'),
    ('donorsfund','דונרס פאנד / OJC', '🎗️'),
]
def split_us_addr(addr):
    """מפרק כתובת ארה"ב מאוחדת ל(רחוב+מספר, עיר, מדינה, מיקוד, ארץ).
    בכתובת כפולה (מופרדת ב-:::) בוחר את החלק המלא (עם מיקוד) ומתעלם מהכפילות."""
    segs = [s.strip() for s in (addr or '').split(':::') if s.strip()]
    if not segs:
        return '', '', '', '', ''
    a = next((s for s in segs if re.search(r'\b\d{5}\b', s)), segs[0]).strip().strip(',').strip()
    parts = [p.strip() for p in a.split(',') if p.strip()]
    country = state = zipc = city = ''
    if parts and (re.fullmatch(r'(US|U\.?S\.?A\.?|USA|IL|ISRAEL|CANADA|UK)', parts[-1].upper().replace(' ', ''))
                  or parts[-1].strip() in ('ארצות הברית', 'ארה"ב', 'ארה״ב', 'ארהב', 'ישראל', 'קנדה')):
        country = parts.pop().upper().replace('.', '').replace(' ', '')
    if parts:
        if re.fullmatch(r'\d{5}(?:-\d{4})?', parts[-1]):
            zipc = parts.pop()
        else:
            m = re.search(r'\s(\d{5}(?:-\d{4})?)$', parts[-1])
            if m:
                zipc = m.group(1); parts[-1] = parts[-1][:m.start()].strip()
    if parts and re.fullmatch(r'[A-Za-z]{2}|N\.?Y\.?|[A-Za-z]\.[A-Za-z]\.?', parts[-1].strip()):
        state = parts.pop().replace('.', '').upper()
    if parts:
        city = parts.pop()
    street = ', '.join(parts)
    if not street and city:
        street = city; city = ''
    return street, city, state, zipc, country

def recon_group(s):
    s = (s or '').lower()
    if 'authorize' in s: return 'authorize'
    if 'banquest' in s or 'ווסט' in s: return 'banquest'
    if 'check' in s or 'צ׳ק' in s or "צ'ק" in s or 'צ״ק' in s: return 'checks'
    if 'zelle' in s or 'transfer' in s or 'ach' in s or 'העבר' in s or 'זל' in s: return 'transfers'
    if 'donors' in s or 'ojc' in s: return 'donorsfund'
    return 'other'

DONOR_FIELDS = {'last','first','english','business','phone','email','addr','tier',
                'category','purpose','amount','channel','pay_status','last_active','notes',
                'region','country','zip','city','iz_note','kv_skip','addr_ok','frequency','months','kv_month','kv_year'}

def norm_zip(z, region):
    """מיקוד ארה\"ב בן 4 ספרות איבד אפס מוביל — משלים ל-5 ספרות."""
    z = str(z or '').strip()
    if region != 'il' and re.fullmatch(r'\d{4}', z):
        return '0' + z
    return z

KIND_HE = {'charge': '💳 לחייב', 'parnes': '🌙 פרנס יום', 'prayer': '🙏 להתפלל',
           'followup': '📞 לחזור', 'other': '🔔 תזכורת'}

def build_ics():
    """פיד יומן לכל התזכורות הפתוחות — לחיבור אוטומטי ליומן Google."""
    con = db(); c = con.cursor()
    names = {r['id']: (r['last'] + ' ' + (r['first'] or '')).strip() for r in c.execute("SELECT id,last,first FROM donors")}
    out = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//Kollel Chatzot//CRM//HE',
           'CALSCALE:GREGORIAN', 'METHOD:PUBLISH', 'X-WR-CALNAME:תזכורות כולל חצות', 'X-WR-TIMEZONE:Asia/Jerusalem']
    for r in c.execute("SELECT * FROM tasks WHERE (done IS NULL OR done=0)"):
        d = re.sub(r'\D', '', r['due_date'] or '')[:8]
        if len(d) != 8: continue
        who = names.get(r['donor_id'], '')
        title = (KIND_HE.get(r['kind'], '🔔') + ' ' + who + ((' — ' + r['note']) if r['note'] else '')).strip()
        title = title.replace('\n', ' ').replace(',', '\\,').replace(';', '\\;')
        out += ['BEGIN:VEVENT', f'UID:task{r["id"]}@kollel-chatzot', f'DTSTART;VALUE=DATE:{d}',
                'STATUS:CONFIRMED', f'SUMMARY:{title}', 'BEGIN:VALARM', 'ACTION:DISPLAY',
                'TRIGGER:-PT9H', f'DESCRIPTION:{title}', 'END:VALARM', 'END:VEVENT']
    out.append('END:VCALENDAR')
    con.close()
    return '\r\n'.join(out)

class H(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype='application/json'):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', ctype + ('; charset=utf-8' if 'json' in ctype or 'html' in ctype or 'calendar' in ctype else ''))
        self.send_header('Content-Length', str(len(data)))
        self.end_headers(); self.wfile.write(data)

    def _body(self):
        try:
            n = int(self.headers.get('Content-Length', 0) or 0)
            return json.loads(self.rfile.read(n) or b'{}')
        except Exception:
            return {}

    def do_GET(self):
        if self.path == '/api/data':
            donors, unlinked, general_tasks = get_all()
            con = db(); camps = [r['name'] for r in con.execute("SELECT name FROM campaigns ORDER BY created DESC, name")]
            bitems = [r['name'] for r in con.execute("SELECT name FROM building_items ORDER BY created DESC, name")]; con.close()
            return self._send(200, {'donors': donors, 'unlinked_prayers': unlinked, 'general_tasks': general_tasks, 'campaigns': camps, 'building_items': bitems, 'heb_year': current_heb_year()})
        if self.path.split('?')[0] == '/calendar.ics':
            return self._send(200, build_ics().encode('utf-8'), 'text/calendar')
        if self.path.split('?')[0] == '/donate':
            return self._send(200, open(os.path.join(STATIC, 'donate.html'), 'rb').read(), 'text/html')
        if self.path.split('?')[0] == '/receipt':
            return self._send(200, open(os.path.join(STATIC, 'receipt.html'), 'rb').read(), 'text/html')
        if self.path.split('?')[0] == '/parnes-cert':
            return self._send(200, open(os.path.join(STATIC, 'parnes-cert.html'), 'rb').read(), 'text/html')
        if self.path.split('?')[0] == '/reconcile':
            return self._send(200, open(os.path.join(STATIC, 'reconcile.html'), 'rb').read(), 'text/html')
        if self.path.split('?')[0] == '/api/recon':
            con = db(); out = []
            try:
                import gmail_intake as _tr
            except Exception:
                _tr = None
            def _he_sugg(s):
                """הצעת איות עברי לשם האנגלי — כדי למלא מראש את שדות השם בכרטיס חדש."""
                if not _tr or not s:
                    return ''
                try:
                    return _tr._he_name(str(s).strip())
                except Exception:
                    return ''
            for r in con.execute("SELECT * FROM recon ORDER BY processed, last, first"):
                x = dict(r)
                if not r['donor_id']:
                    x['sugg_last'] = _he_sugg(r['last'])
                    x['sugg_first'] = _he_sugg(r['first'])
                # שמות קוויטל שהתורם שלח מהאתר — לפי אותה כתובת מייל
                x['kv_names'] = ''
                em = (r['email'] or '').strip().lower()
                if em:
                    try:
                        nm = [q['names'] for q in con.execute(
                            """SELECT names FROM intake WHERE lower(TRIM(from_email))=?
                               AND COALESCE(TRIM(names),'')<>'' ORDER BY id DESC LIMIT 3""", (em,))]
                        x['kv_names'] = '\n'.join(dict.fromkeys('\n'.join(nm).split('\n'))).strip()
                    except Exception:
                        pass
                if r['donor_id']:
                    d = con.execute("SELECT last,first,addr,category,tier,kv_month,kv_year FROM donors WHERE id=?", (r['donor_id'],)).fetchone()
                    if d:
                        x['match_name'] = (d['last'] + ' ' + (d['first'] or '')).strip()
                        x['match_addr'] = d['addr'] or ''
                        x['match_cat'] = d['category'] or ''
                        x['match_tier'] = d['tier'] or ''
                        x['match_kv_month'] = d['kv_month'] or ''
                        x['match_kv_year'] = d['kv_year'] or ''
                        # תרומות סיכום 2026 קיימות — לפי אמצעי ההתאמה. אותו אמצעי יוחלף אוטומטית; אחר דורש בדיקה
                        _pm = 'Banquest' if 'Banquest' in (r['source'] or '') else 'Authorize'
                        x['match_summary'] = con.execute("SELECT COUNT(*) FROM donations WHERE donor_id=? AND note='ייבוא 2026' AND method=?", (r['donor_id'], _pm)).fetchone()[0]
                        x['match_summary_other'] = con.execute("SELECT COUNT(*) FROM donations WHERE donor_id=? AND note='ייבוא 2026' AND COALESCE(method,'')<>?", (r['donor_id'], _pm)).fetchone()[0]
                out.append(x)
            con.close()
            return self._send(200, out)
        if self.path.split('?')[0] == '/api/recon/summary':
            con = db(); agg = {}
            for r in con.execute("SELECT source, processed, status FROM recon"):
                g = recon_group(r['source']); a = agg.setdefault(g, {'pending': 0, 'done': 0, 'total': 0})
                a['total'] += 1
                settled = (not r['status']) or r['status'] == 'settled'
                if r['processed']: a['done'] += 1
                elif settled: a['pending'] += 1
            con.close()
            groups = [{'key': k, 'label': l, 'icon': ic, **agg.get(k, {'pending': 0, 'done': 0, 'total': 0})} for k, l, ic in RECON_GROUPS]
            return self._send(200, groups)
        if self.path.split('?')[0] == '/api/campaigns':
            con = db()
            rows = [r['name'] for r in con.execute("SELECT name FROM campaigns ORDER BY created DESC, name")]
            con.close()
            return self._send(200, rows)
        if self.path.split('?')[0] == '/api/building_items':
            con = db()
            rows = [r['name'] for r in con.execute("SELECT name FROM building_items ORDER BY created DESC, name")]
            con.close()
            return self._send(200, rows)
        if self.path.split('?')[0] == '/api/intake':
            con = db(); out = []
            donors = [dict(r) for r in con.execute("SELECT id,last,first,email,phone,tier FROM donors")]
            def _kvn(s):  # נרמול להשוואת שמות — עברית+אנגלית, אותיות בלבד
                s = re.sub(r'[^א-תa-zA-Z ]', ' ', str(s or '').lower())
                s = s.translate(str.maketrans('ךםןףץ', 'כמנפצ'))
                return re.sub(r'\s+', ' ', s).strip()
            _STOP = {'בן', 'בת', 'ben', 'bas', 'bat', 'ver', 'reb'}
            try:
                import gmail_intake as _gi
            except Exception:
                _gi = None
            allpray = [_kvn(p['text']) for p in con.execute("SELECT text FROM prayers WHERE COALESCE(TRIM(text),'')<>''")]
            def _in_kvittel(names):
                head = _kvn((names or '').split('—')[0].split(' - ')[0])
                toks = [t for t in head.split() if len(t) >= 2 and t not in _STOP]
                if len(toks) < 2:
                    return False
                for pt in allpray:
                    if all(t in pt for t in toks):
                        return True
                return False
            for r in con.execute("SELECT * FROM intake ORDER BY (status='handled'), received DESC, id DESC"):
                x = dict(r); x['match'] = None
                # תעתיק־מחדש מתוך גוף המייל בכל טעינה — כדי שהשיפורים בעברית יחולו גם על בקשות ישנות
                if _gi and r['status'] != 'handled':
                    try:
                        rp = _gi._parse_names(r['body'] or '')
                        if rp.strip():
                            x['names'] = rp
                    except Exception:
                        pass
                if r['status'] != 'handled' and not (x['names'] or '').strip():
                    continue   # אין שמות לתפילה — לא מציגים ברשימה
                x['in_kvittel'] = _in_kvittel(x['names'])
                hit = None
                # מייל לזיהוי: קודם from_email, ואם לא — המייל שבתוך גוף המייל (המיילים מועברים דרך כתובת אחת)
                cand_emails = []
                fem = (r['from_email'] or '').strip().lower()
                if fem:
                    cand_emails.append(fem)
                if _gi:
                    try:
                        be = _gi._submitter_email(r['body'] or '')
                        if be and be.lower() not in cand_emails:
                            cand_emails.append(be.lower())
                    except Exception:
                        pass
                for ce in cand_emails:
                    for d in donors:
                        if (d['email'] or '').strip().lower() == ce and d['email']:
                            hit = d; break
                    if hit:
                        break
                if r['donor_id']:
                    hit = next((d for d in donors if d['id'] == r['donor_id']), hit)
                if hit:
                    x['match'] = {'id': hit['id'], 'name': (hit['last'] + ' ' + (hit['first'] or '')).strip(), 'tier': hit['tier'] or ''}
                    if not x['in_kvittel']:
                        ip = con.execute("SELECT COUNT(*) FROM prayers WHERE donor_id=? AND COALESCE(TRIM(text),'')<>''", (hit['id'],)).fetchone()[0]
                        x['in_kvittel'] = ip > 0
                out.append(x)
            con.close()
            return self._send(200, {'configured': _intake_configured(), 'items': out})
        if self.path == '/api/mail/contacts_sync/status':
            try:
                import gmail_intake
                return self._send(200, dict(gmail_intake.MAIL_STATUS))
            except Exception as e:
                return self._send(200, {'running': False, 'done': True, 'error': str(e)})
        m = re.match(r'/api/pubdonor/(\d+)$', self.path)
        if m:
            con = db(); r = con.execute("SELECT last,first,purpose,amount FROM donors WHERE id=?", (int(m.group(1)),)).fetchone(); con.close()
            if not r: return self._send(404, {'error': 'not found'})
            return self._send(200, {'last': r['last'], 'first': r['first'], 'purpose': r['purpose'], 'amount': r['amount']})
        if self.path.split('?')[0] == '/api/pubsearch':
            from urllib.parse import urlparse, parse_qs
            q = (parse_qs(urlparse(self.path).query).get('q', ['']) [0]).strip()
            nq = _norm(q)
            if len(nq) < 2:
                return self._send(200, [])
            con = db(); rows = []
            for r in con.execute("SELECT id,last,first FROM donors"):
                full = _norm((r['last'] or '') + ' ' + (r['first'] or ''))
                if nq in full or all(t in full for t in nq.split()):
                    rows.append({'id': r['id'], 'last': r['last'], 'first': r['first']})
                if len(rows) >= 8: break
            con.close()
            return self._send(200, rows)
        m = re.match(r'/api/file/(\d+)$', self.path.split('?')[0])
        if m:
            con = db(); r = con.execute("SELECT name,mime,data FROM files WHERE id=?", (int(m.group(1)),)).fetchone(); con.close()
            if not r: return self._send(404, {'error': 'not found'})
            from urllib.parse import urlparse as _up, parse_qs as _pq
            dl = _pq(_up(self.path).query).get('dl', ['0'])[0] == '1'   # הורדה למכשיר במקום פתיחה בדפדפן
            fname = (r['name'] or 'file').replace('"', '')
            ascii_name = re.sub(r'[^A-Za-z0-9._ -]+', '_', fname).strip() or 'file'   # גיבוי לדפדפנים ישנים
            self.send_response(200)
            self.send_header('Content-Type', 'application/octet-stream' if dl else (r['mime'] or 'application/octet-stream'))
            self.send_header('Content-Disposition',
                             ('attachment' if dl else 'inline') + '; filename="' + ascii_name + "\"; filename*=UTF-8''" + quote(fname))
            self.send_header('Content-Length', str(len(r['data'])))
            self.end_headers(); self.wfile.write(r['data']); return
        path = self.path.split('?')[0]
        if path == '/': path = '/index.html'
        fp = os.path.normpath(os.path.join(STATIC, path.lstrip('/')))
        if fp.startswith(STATIC) and os.path.isfile(fp):
            ext = os.path.splitext(fp)[1]
            ctype = {'.html': 'text/html', '.js': 'application/javascript', '.json': 'application/json',
                     '.png': 'image/png', '.svg': 'image/svg+xml', '.css': 'text/css', '.jpg': 'image/jpeg',
                     '.jpeg': 'image/jpeg', '.ttf': 'font/ttf', '.otf': 'font/otf', '.woff2': 'font/woff2',
                     '.webmanifest': 'application/manifest+json'}.get(ext, 'text/plain')
            if path == '/manifest.json':
                ctype = 'application/manifest+json'   # נדרש כדי שאנדרואיד ירשום את יעד השיתוף
            return self._send(200, open(fp, 'rb').read(), ctype)
        return self._send(404, {'error': 'not found'})

    def do_PUT(self):
        m = re.match(r'/api/intake/(\d+)$', self.path)
        if m:
            b = self._body()
            fields = {k: b[k] for k in ('names', 'status', 'donor_id') if k in b}
            if fields:
                con = db()
                con.execute("UPDATE intake SET " + ",".join(f"{k}=?" for k in fields) + " WHERE id=?",
                            tuple(fields.values()) + (int(m.group(1)),))
                con.commit(); con.close()
            return self._send(200, {'ok': True})
        m = re.match(r'/api/donor/(\d+)$', self.path)
        if m:
            b = self._body(); did = int(m.group(1))
            fields = {k: v for k, v in b.items() if k in DONOR_FIELDS}
            if 'zip' in fields:
                fields['zip'] = norm_zip(fields['zip'], fields.get('region', b.get('region', '')))
            if fields:
                con = db()
                con.execute("UPDATE donors SET " + ",".join(f"{k}=?" for k in fields) + " WHERE id=?",
                            list(fields.values()) + [did]); con.commit(); con.close()
            return self._send(200, {'ok': True})
        m = re.match(r'/api/pledge/(\d+)$', self.path)
        if m:
            b = self._body(); pid = int(m.group(1))
            con = db()
            con.execute("UPDATE pledges SET category=?,amount=?,status=?,note=? WHERE id=?",
                        (b.get('category',''), b.get('amount',''), b.get('status',''), b.get('note',''), pid))
            con.commit(); con.close()
            return self._send(200, {'ok': True})
        m = re.match(r'/api/parnes/(\d+)$', self.path)
        if m:
            b = self._body(); pid = int(m.group(1))
            con = db()
            sets=[];vals=[]
            for k in ('day','month','date_text','amount','dedication','kind','status','photo','paid','night_date','hyear','method','currency'):
                if k in b: sets.append(f'{k}=?'); vals.append(b[k])
            # אם התאריך העברי השתנה — חשב מחדש את תאריך הלילה הלועזי (לסימון הירח), לפי השנה העברית
            if 'date_text' in b and 'night_date' not in b:
                hy = b.get('hyear')
                if hy is None:
                    r = con.execute("SELECT hyear FROM parnes WHERE id=?", (pid,)).fetchone()
                    hy = r['hyear'] if r else ''
                _ng = heb_greg_year(b.get('date_text', ''), hy) or heb_to_greg(b.get('date_text', ''))
                sets.append('night_date=?'); vals.append(_ng.isoformat() if _ng else '')
            if sets:
                con.execute("UPDATE parnes SET "+",".join(sets)+" WHERE id=?", vals+[pid])
            con.commit(); con.close()
            return self._send(200, {'ok': True})
        m = re.match(r'/api/prayer/(\d+)$', self.path)
        if m:
            b = self._body(); pid = int(m.group(1))
            con = db(); sets = []; vals = []
            if 'text' in b: sets.append('text=?'); vals.append(b['text'])
            if 'tier' in b: sets.append('tier=?'); vals.append(b['tier'])
            if 'donor_id' in b: sets.append('donor_id=?'); vals.append(b['donor_id'])   # שיוך תפילה לא־משויכת לתורם
            if sets:
                con.execute("UPDATE prayers SET " + ",".join(sets) + " WHERE id=?", vals + [pid])
                con.commit()
            con.close()
            return self._send(200, {'ok': True})
        m = re.match(r'/api/donation/(\d+)$', self.path)
        if m:
            b = self._body(); pid = int(m.group(1))
            con = db(); sets = []; vals = []
            for k in ('date','amount','category','method','note','fb_channel','fb_date','fb_followup','fb_note','paid','thanked'):
                if k in b: sets.append(f'{k}=?'); vals.append(b[k])
            if sets:
                con.execute("UPDATE donations SET " + ",".join(sets) + " WHERE id=?", vals + [pid])
                con.commit()
            con.close()
            return self._send(200, {'ok': True})
        m = re.match(r'/api/contact/(\d+)$', self.path)
        if m:
            b = self._body(); pid = int(m.group(1))
            con = db()
            con.execute("UPDATE contacts_log SET date=?,channel=?,summary=?,next_date=? WHERE id=?",
                        (b.get('date',''), b.get('channel',''), b.get('summary',''), b.get('next_date',''), pid))
            con.commit(); con.close()
            return self._send(200, {'ok': True})
        m = re.match(r'/api/task/(\d+)$', self.path)
        if m:
            b = self._body(); pid = int(m.group(1))
            con = db(); sets = []; vals = []
            for k in ('due_date','kind','note','done','assignee'):
                if k in b: sets.append(f'{k}=?'); vals.append(b[k])
            if sets:
                con.execute("UPDATE tasks SET " + ",".join(sets) + " WHERE id=?", vals + [pid])
                con.commit()
            con.close()
            return self._send(200, {'ok': True})
        m = re.match(r'/api/partner/(\d+)$', self.path)
        if m:
            b = self._body(); pid = int(m.group(1))
            con = db(); sets = []; vals = []
            for k in ('avreich','start_date','amount','note','active','ended_date','method','partner_with','partner_with_id','paid_note','renew_date','joint'):
                if k in b: sets.append(f'{k}=?'); vals.append(b[k] or None if k == 'partner_with_id' else b[k])
            if 'start_date' in b:   # חישוב מחדש של תאריך החידוש כשמשנים את תחילת ההסכם
                g = heb_anniv(b.get('start_date') or '')
                sets.append('renew_date=?'); vals.append(g.isoformat() if g else None)
            if sets:
                con.execute("UPDATE partners SET " + ",".join(sets) + " WHERE id=?", vals + [pid])
                con.commit()
            con.close()
            return self._send(200, {'ok': True})
        m = re.match(r'/api/building/(\d+)$', self.path)
        if m:
            b = self._body(); bid = int(m.group(1))
            con = db(); sets = []; vals = []
            for k in ('object','amount','paid','note','date'):
                if k in b: sets.append(f'{k}=?'); vals.append(b[k])
            if sets:
                con.execute("UPDATE building SET " + ",".join(sets) + " WHERE id=?", vals + [bid])
                con.commit()
            con.close()
            return self._send(200, {'ok': True})
        m = re.match(r'/api/transaction/(\d+)$', self.path)
        if m:
            b = self._body(); tid = int(m.group(1))
            con = db(); sets = []; vals = []
            for k in ('date','amount','category','method','status','trans_id','sub_id','inst_total','inst_paid','recurring','note'):
                if k in b: sets.append(f'{k}=?'); vals.append(b[k])
            if sets:
                con.execute("UPDATE transactions SET " + ",".join(sets) + " WHERE id=?", vals + [tid])
                con.commit()
            con.close()
            return self._send(200, {'ok': True})
        return self._send(404, {'error': 'not found'})

    def do_POST(self):
        # יעד שיתוף (וואטסאפ/גלריה): בדרך כלל ה-Service Worker קולט זאת ושומר את הקבצים.
        # אם הוא עדיין לא פעיל — לפחות נפתח את האפליקציה במקום שגיאה.
        if self.path.split('?')[0] == '/share-target':
            try:
                ln = int(self.headers.get('Content-Length') or 0)
                if ln > 0:
                    self.rfile.read(ln)      # ריקון הגוף כדי לא לתקוע את החיבור
            except Exception:
                pass
            self.send_response(303)
            self.send_header('Location', '/?share=1')
            self.end_headers()
            return
        b = self._body()
        if self.path == '/api/intake/sync':
            try:
                import gmail_intake
            except Exception as e:
                return self._send(200, {'ok': False, 'error': 'module', 'detail': str(e)})
            con = db(); res = gmail_intake.sync(con); con.close()
            return self._send(200, res)
        if self.path == '/api/mail/contacts_sync':   # תיוק מיילים מתורמים — רץ ברקע כדי לא ליפול בטיימאאוט
            try:
                import gmail_intake, threading
            except Exception as e:
                return self._send(200, {'ok': False, 'error': 'module', 'detail': str(e)})
            if not gmail_intake.configured():
                return self._send(200, {'ok': False, 'error': 'not_configured'})
            stt = gmail_intake.MAIL_STATUS
            if stt.get('running'):
                return self._send(200, {'ok': True, 'started': False, 'already': True, 'status': stt})
            stt.update({'running': True, 'new': 0, 'scanned': 0, 'total': 0, 'done': False, 'error': ''})
            def _run():
                c = db()
                try:
                    r = gmail_intake.sync_contacts(c, stt)
                    if not r.get('ok'):
                        stt['error'] = r.get('detail') or r.get('error') or 'שגיאה'
                    else:
                        stt['new'] = r.get('new', stt.get('new', 0))
                except Exception as e:
                    stt['error'] = '%s: %s' % (type(e).__name__, e)
                finally:
                    try: c.close()
                    except Exception: pass
                    stt['running'] = False; stt['done'] = True
            threading.Thread(target=_run, daemon=True).start()
            return self._send(200, {'ok': True, 'started': True})
        m = re.match(r'/api/intake/(\d+)/attach$', self.path)
        if m:
            iid = int(m.group(1))
            con = db(); r = con.execute("SELECT * FROM intake WHERE id=?", (iid,)).fetchone()
            if not r:
                con.close(); return self._send(404, {'error': 'not found'})
            did = b.get('donor_id') or r['donor_id']
            reparsed = ''
            try:
                import gmail_intake as _gi2
                reparsed = _gi2._parse_names(r['body'] or '')
            except Exception:
                reparsed = ''
            text = (b.get('names') or reparsed or r['names'] or r['body'] or '').strip()
            if did:  # שיוך לכרטיס תורם קיים — דרגת השם לפי דרגת התורם (ריק=לפי הקטגוריה, למשל מזדמן)
                tier = con.execute("SELECT tier FROM donors WHERE id=?", (did,)).fetchone()
                tval = (tier['tier'] if tier else '') or ''
                con.execute("INSERT INTO prayers(donor_id,name,text,tier) VALUES(?,'',?,?)", (did, text, tval))
                con.execute("UPDATE intake SET donor_id=?, status='handled' WHERE id=?", (did, iid))
            else:     # הוספה לקוויטל בלי שיוך לתורם (שם לא־משויך)
                dispname = (r['from_name'] or r['from_email'] or (text.split('בן')[0].strip()) or 'מהאתר').strip()
                con.execute("INSERT INTO prayers(donor_id,name,text,tier) VALUES(NULL,?,?,?)", (dispname, text, 'קוויטל_שבועי'))
                con.execute("UPDATE intake SET status='handled' WHERE id=?", (iid,))
            con.commit(); con.close()
            return self._send(200, {'ok': True})
        m = re.match(r'/api/intake/(\d+)/newdonor$', self.path)
        if m:   # פתיחת כרטיס תורם חדש מתוך בקשת האתר
            iid = int(m.group(1))
            con = db(); r = con.execute("SELECT * FROM intake WHERE id=?", (iid,)).fetchone()
            if not r:
                con.close(); return self._send(404, {'error': 'not found'})
            reparsed = ''
            try:
                import gmail_intake as _gi3
                reparsed = _gi3._parse_names(r['body'] or '')
            except Exception:
                reparsed = ''
            text = (b.get('names') or reparsed or r['names'] or '').strip()
            last = (b.get('last') or '').strip()
            first = (b.get('first') or '').strip()
            email = (b.get('email') or r['from_email'] or '').strip().lower()
            # הצלבה מול חיובי האשראי (Authorize / Bank West) לפי אימייל — משיכת כתובת/טלפון/שם
            rec = None
            if email:
                rec = con.execute("""SELECT * FROM recon WHERE lower(TRIM(email))=? AND TRIM(COALESCE(email,''))<>''
                                     ORDER BY date DESC LIMIT 1""", (email,)).fetchone()
            english = phone = addr = city = region = country = zipc = ''
            if rec:
                first = first or (rec['first'] or '')
                last = last or (rec['last'] or '')
                english = (((rec['first'] or '') + ' ' + (rec['last'] or '')).strip())
                phone = rec['phone'] or ''
                addr = rec['addr'] or ''
                city = rec['city'] or ''
                region = rec['state'] or ''
                zipc = rec['zip'] or ''
                country = 'US'
            if not last:
                last = (r['from_name'] or '').strip()
            if not (last or first):   # אין שם — ניקח את השם הראשון מהקוויטל (לפני בן/בת)
                head = re.split(r'\bבן\b|\bבת\b', text)[0].strip() if text else ''
                last = head or 'תורם חדש'
            cur = con.execute("""INSERT INTO donors(last,first,english,business,phone,email,addr,tier,category,purpose,amount,created,source,region,country,zip,city)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (last, first, english, '', phone, email, addr, '', 'מזדמן', '', '', today_iso(),
                         ('אתר+אשראי' if rec else 'אתר'), region, country, zipc, city))
            did = cur.lastrowid
            if text:
                con.execute("INSERT INTO prayers(donor_id,name,text,tier) VALUES(?,'',?,'')", (did, text))
            # קישור חיובי האשראי שטרם שויכו לתורם הזה (לפי אימייל) — כדי שההיסטוריה תיראה בכרטיס
            if email:
                con.execute("""UPDATE recon SET donor_id=? WHERE lower(TRIM(email))=? AND TRIM(COALESCE(email,''))<>''
                               AND (donor_id IS NULL OR donor_id='' OR donor_id=0)""", (did, email))
            con.execute("UPDATE intake SET donor_id=?, status='handled' WHERE id=?", (did, iid))
            con.commit(); con.close()
            dname = (last + ' ' + first).strip() or english or 'תורם חדש'
            return self._send(200, {'ok': True, 'id': did, 'from_recon': bool(rec), 'name': dname})
        m = re.match(r'/api/contact/(\d+)/remind$', self.path)
        if m:   # יצירת תזכורת מתוך תיעוד קשר — כולל העתקת האסמכתאות (צילום אשראי, הקלטה)
            cid = int(m.group(1))
            con = db()
            c = con.execute("SELECT * FROM contacts_log WHERE id=?", (cid,)).fetchone()
            if not c:
                con.close(); return self._send(404, {'error': 'not found'})
            due = (b.get('due_date') or '').strip() or today_iso()
            kind = (b.get('kind') or 'charge').strip()
            note = (b.get('note') or c['summary'] or '').strip()
            cur = con.execute("INSERT INTO tasks(donor_id,due_date,kind,note,assignee) VALUES(?,?,?,?,?)",
                              (c['donor_id'], due, kind, note, (b.get('assignee') or '')))
            tid = cur.lastrowid
            n = 0
            if b.get('copy_files', True):   # אותם קבצים עוברים גם לתזכורת
                for f in con.execute("SELECT name,mime,data FROM files WHERE kind='contact' AND ref_id=?", (cid,)):
                    con.execute("INSERT INTO files(kind,ref_id,name,mime,data,created) VALUES('task',?,?,?,?,?)",
                                (tid, f['name'], f['mime'], f['data'], today_iso()))
                    n += 1
            con.commit(); con.close()
            return self._send(200, {'ok': True, 'id': tid, 'files': n, 'donor_id': c['donor_id']})
        m = re.match(r'/api/parnes/(\d+)/sendmail$', self.path)
        if m:   # שליחת תמונת ההקדשה/התעודה ישירות לתורם במייל — עם הקובץ מצורף
            pid = int(m.group(1))
            con = db()
            p = con.execute("SELECT * FROM parnes WHERE id=?", (pid,)).fetchone()
            if not p:
                con.close(); return self._send(404, {'error': 'not found'})
            d = con.execute("SELECT last,first,email FROM donors WHERE id=?", (p['donor_id'],)).fetchone()
            to = (b.get('to') or (d['email'] if d else '') or '').strip()
            atts = []
            for f in con.execute("SELECT name,mime,data FROM files WHERE kind='parnes' AND ref_id=?", (pid,)):
                atts.append((f['name'] or 'hakdasha.jpg', f['mime'] or 'image/jpeg', f['data']))
            con.close()
            if not to:
                return self._send(200, {'ok': False, 'error': 'no_recipient'})
            if not atts:
                return self._send(200, {'ok': False, 'error': 'no_files'})
            donor = ((d['last'] or '') + ' ' + (d['first'] or '')).strip() if d else ''
            dtext = (p['date_text'] or '') + ((' ' + p['hyear']) if p['hyear'] else '')
            subject = b.get('subject') or ('תעודת פרנס — כולל חצות' + ((' · ' + dtext) if dtext else ''))
            body = b.get('body') or (
                ('לכבוד ' + donor + ',\n\n' if donor else '') +
                'מצורפת תמונת ההקדשה' + ((' עבור ' + dtext) if dtext else '') + '.\n\n'
                'תזכו למצוות!\nכולל חצות')
            try:
                import mailer
            except Exception as e:
                return self._send(200, {'ok': False, 'error': 'module', 'detail': str(e)})
            res = mailer.send(to, subject, body, atts)
            res['to'] = to
            res['count'] = len(atts)
            return self._send(200, res)
        if self.path == '/api/campaigns':
            nm = (b.get('name') or '').strip()
            if nm:
                con = db(); con.execute("INSERT OR IGNORE INTO campaigns(name,created) VALUES(?,?)", (nm, today_iso())); con.commit(); con.close()
            return self._send(200, {'ok': True, 'name': nm})
        if self.path == '/api/building_items':
            nm = (b.get('name') or '').strip()
            if nm:
                con = db(); con.execute("INSERT OR IGNORE INTO building_items(name,created) VALUES(?,?)", (nm, today_iso())); con.commit(); con.close()
            return self._send(200, {'ok': True, 'name': nm})
        if self.path == '/api/donor':
            con = db(); cur = con.cursor()
            cur.execute("""INSERT INTO donors(last,first,english,business,phone,email,addr,tier,category,purpose,amount,created,source,region,country,zip,city)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (b.get('last',''), b.get('first',''), b.get('english',''), b.get('business',''), b.get('phone',''),
                         b.get('email',''), b.get('addr',''), b.get('tier',''), b.get('category',''), b.get('purpose',''),
                         b.get('amount',''), today_iso(), 'ידני', b.get('region',''), b.get('country',''), norm_zip(b.get('zip',''), b.get('region','')), b.get('city','')))
            con.commit(); did = cur.lastrowid; con.close()
            return self._send(200, {'ok': True, 'id': did})
        m = re.match(r'/api/recon/([^/]+)$', self.path)
        if m:
            tid = m.group(1); con = db(); cur = con.cursor()
            row = cur.execute("SELECT * FROM recon WHERE tid=?", (tid,)).fetchone()
            if not row:
                con.close(); return self._send(404, {'error': 'not found'})
            if b.get('skip') or (row['status'] and row['status'] != 'settled'):
                cur.execute("UPDATE recon SET processed=1 WHERE tid=?", (tid,)); con.commit(); con.close()
                return self._send(200, {'ok': True, 'skipped': True})
            did = b.get('donor_id')
            r_state = row['state'] or ''         # מדינה (NY וכו') נשמרת בשדה "מדינה"
            r_src = 'Banquest' if 'Banquest' in (row['source'] or '') else 'Authorize'
            if b.get('new_donor'):
                nd = b['new_donor']
                cur.execute("""INSERT INTO donors(last,first,english,phone,email,addr,city,country,zip,category,created,source,notes)
                               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                            (nd.get('last', ''), nd.get('first', ''), (row['first'] + ' ' + row['last']).strip(),
                             row['phone'], row['email'], row['addr'] or '', row['city'] or '', r_state, row['zip'] or '',
                             b.get('category', ''), today_iso(), r_src, nd.get('notes', '')))
                did = cur.lastrowid
                if (nd.get('task') or '').strip():     # משימה שנקבעה יחד עם פתיחת הכרטיס
                    cur.execute("INSERT INTO tasks(donor_id,due_date,kind,note) VALUES(?,?,?,?)",
                                (did, (nd.get('task_date') or today_iso()), 'followup', nd['task'].strip()))
            if not did:
                con.close(); return self._send(400, {'error': 'donor required'})
            # מילוי אוטומטי של שם אנגלי אם חסר בכרטיס (מיזוג השם מהייבוא)
            if not b.get('new_donor'):
                en = (row['first'] + ' ' + row['last']).strip()
                if en:
                    cur.execute("UPDATE donors SET english=? WHERE id=? AND COALESCE(TRIM(english),'')=''", (en, did))
            if b.get('update_addr') and (row['addr'] or row['city'] or row['zip']):
                cur.execute("UPDATE donors SET addr=?, city=?, country=?, zip=? WHERE id=?",
                            (row['addr'] or '', row['city'] or '', r_state, row['zip'] or '', did))
            # שמות הקוויטל שהתורם שלח מהאתר — צירוף לכרטיס שלו
            kvt = (b.get('kv_text') or '').strip()
            if b.get('attach_kv') and kvt:
                dt = cur.execute("SELECT tier FROM donors WHERE id=?", (did,)).fetchone()
                have = {(p['text'] or '').strip() for p in
                        cur.execute("SELECT text FROM prayers WHERE donor_id=?", (did,))}
                for ln in [l.strip() for l in kvt.split('\n') if l.strip()]:
                    if ln not in have:      # בלי כפילויות
                        cur.execute("INSERT INTO prayers(donor_id,name,text,tier) VALUES(?,'',?,?)",
                                    (did, ln, (dt['tier'] if dt else '') or ''))
                        have.add(ln)
                cur.execute("UPDATE intake SET donor_id=?, status='handled' WHERE lower(TRIM(from_email))=? AND COALESCE(donor_id,0)=0",
                            (did, (row['email'] or '').strip().lower()))
            # תאריך: '01-Jul-2026' -> '2026-07'
            MON = {'Jan':'01','Feb':'02','Mar':'03','Apr':'04','May':'05','Jun':'06','Jul':'07','Aug':'08','Sep':'09','Oct':'10','Nov':'11','Dec':'12'}
            dm = re.match(r'(\d{2})-([A-Za-z]{3})-(\d{4})', row['date'] or '')
            diso = f"{dm.group(3)}-{MON.get(dm.group(2),'01')}" if dm else ''
            cat = b.get('category', '') or row['category'] or ''
            # קטגוריה חופשית (עבור מה) — נשמרת לרשימה קבועה לשימוש חוזר
            BASE_CATS = {'', 'קבוע', 'יששכר־זבולון', 'פרנס לילה', 'חדר קפה', 'ארוחת בוקר', 'נר למאור', 'קוויטל', 'מזדמן', 'חד-פעמי', 'אחר'}
            if cat and cat not in BASE_CATS:
                cur.execute("INSERT OR IGNORE INTO campaigns(name,created) VALUES(?,?)", (cat, today_iso()))
            # אמצעי התשלום לפי מקור ההתאמה (Authorize / Banquest / בנק ווסט)
            pay_method = 'Banquest' if 'Banquest' in (row['source'] or '') else 'Authorize'
            # מילוי ערוץ החיוב בכרטיס (ובאברכים) לפי אמצעי התשלום — אוטומטית
            _chan = {'Authorize': 'אותורייז', 'Banquest': 'בנק_ווסט'}.get(pay_method, '')
            if _chan and did:
                cur.execute("UPDATE donors SET channel=? WHERE id=? AND COALESCE(channel,'')=''", (_chan, did))
                cur.execute("UPDATE partners SET method=? WHERE donor_id=? AND active<>0 AND COALESCE(method,'')=''", (_chan, did))
            # מניעת כפילות מול קובץ הסיכום 2026: רשומת סיכום באותו אמצעי, לאותו תורם+חודש,
            # מוחלפת ע"י העסקה המדויקת (אותו כסף בדיוק)
            if diso and did:
                cur.execute("DELETE FROM donations WHERE donor_id=? AND date=? AND note='ייבוא 2026' AND method=?", (did, diso, pay_method))
            PKIND = {'פרנס לילה': 'parnes', 'חדר קפה': 'coffee', 'ארוחת בוקר': 'breakfast'}
            if cat in PKIND:
                # פרנס־יום (במקום תרומה רגילה) — נגבה, עם השמות והיום שנבחר בבורר
                dtext = b.get('date_text', '')
                _ng = heb_to_greg(dtext) if dtext else None
                cur.execute("INSERT INTO parnes(donor_id,day,month,date_text,amount,dedication,kind,status,paid,night_date,hyear,method) VALUES(?,?,?,?,?,?,?,'confirmed',1,?,?,?)",
                            (did, b.get('day', 0), b.get('month', ''), dtext, row['amount'], b.get('dedication', ''), PKIND[cat],
                             _ng.isoformat() if _ng else '', b.get('hyear', ''), pay_method))
            else:
                cur.execute("INSERT INTO donations(donor_id,date,amount,category,method,note,paid) VALUES(?,?,?,?,?,?,1)",
                            (did, diso, row['amount'], cat, pay_method, 'ייבוא ' + pay_method + (' · הוראת קבע' if row['recurring'] else '')))
            if row['recurring']:
                cur.execute("UPDATE donors SET category='קבוע' WHERE id=? AND COALESCE(category,'')=''", (did,))
            # פרנס לילה מאוגוסט ואילך — תזכורת לעשות לו את הלילה בפועל, שבוע לפני הלילה
            if cat == 'פרנס לילה' and diso >= '2026-08':
                dn = cur.execute("SELECT last, first FROM donors WHERE id=?", (did,)).fetchone()
                nm = ((dn['last'] + ' ' + (dn['first'] or '')).strip()) if dn else ''
                _pdue = week_before(b.get('date_text', '')) or today_iso()
                if _pdue < today_iso(): _pdue = today_iso()
                cur.execute("INSERT INTO tasks(donor_id,due_date,kind,note) VALUES(?,?,?,?)",
                            (did, _pdue, 'parnes', '🌙 לעשות פרנס לילה — ' + nm))
            cur.execute("UPDATE recon SET processed=1, donor_id=?, category=? WHERE tid=?", (did, cat, tid))
            con.commit(); con.close()
            return self._send(200, {'ok': True, 'donor_id': did})
        if self.path == '/api/merge':
            # מיזוג שני כרטיסים כפולים: keep=הכרטיס שנשאר, drop=הכרטיס שנמחק
            try:
                keep = int(b.get('keep')); drop = int(b.get('drop'))
            except (TypeError, ValueError):
                return self._send(400, {'error': 'keep/drop required'})
            if keep == drop:
                return self._send(400, {'error': 'same id'})
            con = db(); cur = con.cursor()
            k = cur.execute("SELECT * FROM donors WHERE id=?", (keep,)).fetchone()
            d = cur.execute("SELECT * FROM donors WHERE id=?", (drop,)).fetchone()
            if not k or not d:
                con.close(); return self._send(404, {'error': 'donor not found'})
            # העברת כל רשומות הבן מהכרטיס הנמחק לכרטיס שנשאר
            for t in ('pledges', 'parnes', 'prayers', 'donations', 'contacts_log', 'tasks', 'partners', 'transactions', 'building'):
                try: cur.execute(f"UPDATE {t} SET donor_id=? WHERE donor_id=?", (keep, drop))
                except Exception: pass
            try: cur.execute("UPDATE files SET ref_id=? WHERE kind='iz' AND ref_id=?", (keep, drop))
            except Exception: pass
            # השלמת שדות ריקים בכרטיס שנשאר מתוך הכרטיס הנמחק; מיזוג טלפונים ייחודיים
            kd = dict(k); dd = dict(d); sets = []; vals = []
            for col in ('first', 'english', 'business', 'email', 'addr', 'tier', 'category',
                        'purpose', 'amount', 'region', 'country', 'zip', 'city'):
                if col in kd and not (kd.get(col) or '').strip() and (dd.get(col) or '').strip():
                    sets.append(f"{col}=?"); vals.append(dd[col])
            kp = [p.strip() for p in re.split(r'[/,]', kd.get('phone') or '') if p.strip()]
            for p in re.split(r'[/,]', dd.get('phone') or ''):
                p = p.strip()
                if p and p not in kp: kp.append(p)
            merged_phone = ' / '.join(kp)
            if merged_phone != (kd.get('phone') or ''):
                sets.append("phone=?"); vals.append(merged_phone)
            if sets:
                cur.execute("UPDATE donors SET " + ",".join(sets) + " WHERE id=?", vals + [keep])
            cur.execute("DELETE FROM donors WHERE id=?", (drop,))
            con.commit(); con.close()
            return self._send(200, {'ok': True, 'keep': keep, 'dropped': drop})
        if self.path == '/api/building':
            con = db(); cur = con.cursor()
            cur.execute("INSERT INTO building(donor_id,object,amount,paid,note,date) VALUES(?,?,?,?,?,?)",
                        (b.get('donor_id'), b.get('object',''), b.get('amount',''), b.get('paid',''), b.get('note',''), b.get('date', today_iso())))
            con.commit(); pid = cur.lastrowid; con.close()
            return self._send(200, {'ok': True, 'id': pid})
        if self.path == '/api/pledge':
            con = db(); cur = con.cursor()
            cur.execute("INSERT INTO pledges(donor_id,category,amount,status,date,note) VALUES(?,?,?,?,?,?)",
                        (b.get('donor_id'), b.get('category',''), b.get('amount',''), b.get('status','טרם'), b.get('date',''), b.get('note','')))
            con.commit(); pid = cur.lastrowid; con.close()
            return self._send(200, {'ok': True, 'id': pid})
        if self.path == '/api/parnes':
            con = db(); cur = con.cursor()
            # תאריך לועזי מדויק לפי השנה העברית שנבחרה; נפילה לחישוב המופע הקרוב אם אין שנה
            _ng = heb_greg_year(b.get('date_text', ''), b.get('hyear', '')) or heb_to_greg(b.get('date_text', ''))
            cur.execute("INSERT INTO parnes(donor_id,day,month,date_text,amount,dedication,kind,status,night_date,hyear,method) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                        (b.get('donor_id'), b.get('day',0), b.get('month',''), b.get('date_text',''), b.get('amount',''), b.get('dedication',''), b.get('kind','parnes'), b.get('status','confirmed'), _ng.isoformat() if _ng else '', b.get('hyear',''), b.get('method','')))
            pid = cur.lastrowid
            due = week_before(b.get('date_text',''))
            if due and due < today_iso(): due = today_iso()   # שבוע-לפני כבר עבר — קבע להיום, לא בעבר
            tid = None
            if due:
                cur.execute("INSERT INTO tasks(donor_id,due_date,kind,note) VALUES(?,?,?,?)",
                            (b.get('donor_id'), due, 'parnes', 'פרנס יום ' + b.get('date_text','') + ' — הכן הדפסה וצור קשר'))
                tid = cur.lastrowid
            # הצעות אוטומטיות לשנים הבאות — אותו יום עברי, כ"הצעה" שטרם נגבתה
            suggestions = []
            if b.get('status', 'confirmed') != 'suggested' and b.get('hyear'):
                for ys, gd in future_parnes(b.get('date_text', ''), b.get('hyear', ''), 3):
                    if cur.execute("SELECT 1 FROM parnes WHERE donor_id=? AND kind=? AND date_text=? AND hyear=?",
                                   (b.get('donor_id'), b.get('kind', 'parnes'), b.get('date_text', ''), ys)).fetchone():
                        continue
                    cur.execute("INSERT INTO parnes(donor_id,day,month,date_text,amount,dedication,kind,status,paid,night_date,hyear,method) VALUES(?,?,?,?,?,?,?,'suggested',0,?,?,?)",
                                (b.get('donor_id'), b.get('day', 0), b.get('month', ''), b.get('date_text', ''), b.get('amount', ''),
                                 b.get('dedication', ''), b.get('kind', 'parnes'), gd, ys, b.get('method', '')))
                    suggestions.append({'id': cur.lastrowid, 'donor_id': b.get('donor_id'), 'day': b.get('day', 0),
                                        'month': b.get('month', ''), 'date_text': b.get('date_text', ''), 'amount': b.get('amount', ''),
                                        'dedication': b.get('dedication', ''), 'kind': b.get('kind', 'parnes'), 'status': 'suggested',
                                        'paid': 0, 'night_date': gd, 'hyear': ys, 'method': b.get('method', '')})
            con.commit(); con.close()
            return self._send(200, {'ok': True, 'id': pid, 'reminder_id': tid, 'reminder_date': due, 'suggestions': suggestions})
        if self.path == '/api/prayer':
            con = db(); cur = con.cursor()
            cur.execute("INSERT INTO prayers(donor_id,text,tier) VALUES(?,?,?)",
                        (b.get('donor_id'), b.get('text',''), b.get('tier','')))
            con.commit(); pid = cur.lastrowid; con.close()
            return self._send(200, {'ok': True, 'id': pid})
        if self.path == '/api/donation':
            con = db(); cur = con.cursor()
            cur.execute("INSERT INTO donations(donor_id,date,amount,category,method,note) VALUES(?,?,?,?,?,?)",
                        (b.get('donor_id'), b.get('date',''), b.get('amount',''), b.get('category',''), b.get('method',''), b.get('note','')))
            con.commit(); pid = cur.lastrowid; con.close()
            return self._send(200, {'ok': True, 'id': pid, 'hmonth': greg_to_heb_monthyear(b.get('date',''))})
        if self.path == '/api/online':
            first = (b.get('first') or '').strip()
            last = (b.get('last') or '').strip()
            name = (last + ' ' + first).strip() or (b.get('name') or '').strip()
            amt = (b.get('amount') or '').strip()
            cur_sym = '$'  # ארה"ב בלבד — דולרים
            cat = (b.get('category') or 'תרומה מקוונת').strip()
            recurring = bool(b.get('recurring'))
            duration = (b.get('duration') or '').strip()
            try: installments = int(b.get('installments') or 1)
            except Exception: installments = 1
            prayers = b.get('prayers') if isinstance(b.get('prayers'), list) else []
            phone = (b.get('phone') or '').strip()
            email = (b.get('email') or '').strip()
            addr = (b.get('addr') or '').strip()
            notes = (b.get('notes') or '').strip()
            did = b.get('donor_id')
            did = int(did) if str(did).isdigit() else None
            con = db(); cur = con.cursor()
            valid = False
            if did:
                valid = bool(cur.execute("SELECT id FROM donors WHERE id=?", (did,)).fetchone())
            if valid:
                did = int(did)
            else:
                cur.execute("INSERT INTO donors(last,first,phone,email,addr,category,channel,notes,created,source) VALUES(?,?,?,?,?,?,?,?,?,?)",
                            (last or name, first, phone, email, addr, 'מזדמן', 'אונליין', 'תרומה מקוונת', today_iso(), 'אונליין'))
                did = cur.lastrowid
            # תיאור ההתחייבות
            if recurring:
                dtxt = '12 חודשים' if duration == '12' else 'ללא הגבלה'
                terms = 'הוראת קבע ' + cur_sym + amt + '/חודש · ' + dtxt
            else:
                terms = cur_sym + amt + (' · ' + str(installments) + ' תשלומים' if installments > 1 else ' · תשלום אחד')
            pay_label = (b.get('pay_label') or '').strip()
            parts = [terms]
            if pay_label: parts.append('אמצעי: ' + pay_label)
            if email: parts.append('מייל ' + email)
            if phone: parts.append('טל ' + phone)
            if notes: parts.append('הערה: ' + notes)
            note = 'תרומה מקוונת · ' + ' · '.join(parts)
            inst_total = (12 if duration == '12' else 0) if recurring else installments
            cur.execute("""INSERT INTO transactions(donor_id,date,amount,category,method,status,inst_total,inst_paid,recurring,note,created)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                        (did, '', amt, cat, pay_label, 'pending', inst_total, 0, 1 if recurring else 0, note, 'online'))
            plid = cur.lastrowid
            cur.execute("INSERT INTO tasks(donor_id,due_date,kind,note) VALUES(?,?,?,?)",
                        (did, '', 'charge', 'גבייה מקוונת: ' + terms + ' · ' + cat + ('' if valid else ' · ' + name)))
            for p in prayers[:4]:
                nm = (p.get('name') or '').strip()
                if not nm: continue
                mom = (p.get('mother') or '').strip()
                req = (p.get('request') or '').strip()
                txt = nm + (' בן/בת ' + mom if mom else '') + (' — ' + req if req else '')
                cur.execute("INSERT INTO prayers(donor_id,text,tier) VALUES(?,?,?)", (did, txt, ''))
            con.commit(); con.close()
            return self._send(200, {'ok': True, 'id': plid, 'donor_id': did})
        if self.path == '/api/contact':
            con = db(); cur = con.cursor()
            cur.execute("INSERT INTO contacts_log(donor_id,date,channel,summary,next_date) VALUES(?,?,?,?,?)",
                        (b.get('donor_id'), b.get('date',''), b.get('channel',''), b.get('summary',''), b.get('next_date','')))
            cid = cur.lastrowid; task_id = None
            if b.get('next_date'):
                cur.execute("INSERT INTO tasks(donor_id,due_date,kind,note) VALUES(?,?,?,?)",
                            (b.get('donor_id'), b['next_date'], 'followup', b.get('summary','')[:80]))
                task_id = cur.lastrowid
            con.commit(); con.close()
            return self._send(200, {'ok': True, 'id': cid, 'task_id': task_id})
        if self.path == '/api/task':
            con = db(); cur = con.cursor()
            cur.execute("INSERT INTO tasks(donor_id,due_date,kind,note,assignee) VALUES(?,?,?,?,?)",
                        (b.get('donor_id'), b.get('due_date',''), b.get('kind','prayer'), b.get('note',''), b.get('assignee','')))
            con.commit(); pid = cur.lastrowid; con.close()
            return self._send(200, {'ok': True, 'id': pid})
        if self.path == '/api/partner':
            con = db(); cur = con.cursor()
            cur.execute("INSERT INTO partners(donor_id,avreich,start_date,amount,note,active,method) VALUES(?,?,?,?,?,1,?)",
                        (b.get('donor_id'), b.get('avreich',''), b.get('start_date',''), b.get('amount',''), b.get('note',''), b.get('method','')))
            con.commit(); pid = cur.lastrowid; con.close()
            return self._send(200, {'ok': True, 'id': pid})
        if self.path == '/api/transaction':
            con = db(); cur = con.cursor()
            cur.execute("""INSERT INTO transactions(donor_id,date,amount,category,method,status,trans_id,sub_id,inst_total,inst_paid,recurring,note,created)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (b.get('donor_id'), b.get('date',''), b.get('amount',''), b.get('category',''), b.get('method',''),
                         b.get('status','pending'), b.get('trans_id',''), b.get('sub_id',''),
                         int(b.get('inst_total',1) or 1), int(b.get('inst_paid',0) or 0), 1 if b.get('recurring') else 0,
                         b.get('note',''), b.get('created','')))
            con.commit(); tid = cur.lastrowid; con.close()
            return self._send(200, {'ok': True, 'id': tid})
        if self.path == '/api/file':
            try: raw = base64.b64decode(b.get('data', ''))
            except Exception: return self._send(400, {'error': 'bad data'})
            if len(raw) > 15 * 1024 * 1024: return self._send(413, {'error': 'too large'})
            con = db(); cur = con.cursor()
            cur.execute("INSERT INTO files(kind,ref_id,name,mime,data,created) VALUES(?,?,?,?,?,?)",
                        (b.get('kind',''), b.get('ref_id'), b.get('name',''), b.get('mime',''), raw, b.get('created','')))
            con.commit(); fid = cur.lastrowid; con.close()
            return self._send(200, {'ok': True, 'id': fid})
        return self._send(404, {'error': 'not found'})

    def do_DELETE(self):
        m = re.match(r'/api/intake/(\d+)$', self.path)
        if m:
            con = db(); con.execute("DELETE FROM intake WHERE id=?", (int(m.group(1)),)); con.commit(); con.close()
            return self._send(200, {'ok': True})
        m = re.match(r'/api/donor/(\d+)$', self.path)
        if m:
            did = int(m.group(1)); con = db()
            # קבצים תחילה (לפני מחיקת שורות parnes שהם מפנים אליהן)
            try: con.execute("DELETE FROM files WHERE ref_id=? AND kind='iz'", (did,))
            except Exception: pass
            try: con.execute("DELETE FROM files WHERE kind='parnes' AND ref_id IN (SELECT id FROM parnes WHERE donor_id=?)", (did,))
            except Exception: pass
            try: con.execute("DELETE FROM files WHERE kind='contact' AND ref_id IN (SELECT id FROM contacts_log WHERE donor_id=?)", (did,))
            except Exception: pass
            try: con.execute("DELETE FROM files WHERE kind='task' AND ref_id IN (SELECT id FROM tasks WHERE donor_id=?)", (did,))
            except Exception: pass
            try: con.execute("DELETE FROM files WHERE kind='donation' AND ref_id IN (SELECT id FROM donations WHERE donor_id=?)", (did,))
            except Exception: pass
            try: con.execute("DELETE FROM files WHERE kind='transaction' AND ref_id IN (SELECT id FROM transactions WHERE donor_id=?)", (did,))
            except Exception: pass
            for t in ('pledges','parnes','prayers','donations','contacts_log','tasks','partners','transactions','building'):
                try: con.execute(f"DELETE FROM {t} WHERE donor_id=?", (did,))
                except Exception: pass
            con.execute("DELETE FROM donors WHERE id=?", (did,))
            con.commit(); con.close()
            return self._send(200, {'ok': True})
        m = re.match(r'/api/(pledge|parnes|prayer|donation|contact|task|partner|file|transaction|building)/(\d+)$', self.path)
        if m:
            DTBL = {'pledge': 'pledges', 'parnes': 'parnes', 'prayer': 'prayers', 'donation': 'donations',
                    'contact': 'contacts_log', 'task': 'tasks', 'partner': 'partners',
                    'transaction': 'transactions', 'file': 'files', 'building': 'building'}
            table = DTBL[m.group(1)]; rid = int(m.group(2))
            con = db()
            if table == 'parnes':
                # מחיקת תזכורת הפרנס שנוצרה אוטומטית יחד עם היום הזה
                try:
                    row = con.execute("SELECT donor_id, date_text FROM parnes WHERE id=?", (rid,)).fetchone()
                    if row:
                        note = 'פרנס יום ' + (row['date_text'] or '') + ' — הכן הדפסה וצור קשר'
                        con.execute("DELETE FROM tasks WHERE donor_id=? AND kind='parnes' AND note=?",
                                    (row['donor_id'], note))
                except Exception: pass
            if table in ('contacts_log', 'tasks', 'parnes', 'donations', 'transactions'):   # מחיקת האסמכתאות יחד עם השורה
                fk = {'contacts_log': 'contact', 'tasks': 'task', 'parnes': 'parnes',
                      'donations': 'donation', 'transactions': 'transaction'}[table]
                try: con.execute("DELETE FROM files WHERE kind=? AND ref_id=?", (fk, rid))
                except Exception: pass
            con.execute(f"DELETE FROM {table} WHERE id=?", (rid,)); con.commit(); con.close()
            return self._send(200, {'ok': True})
        return self._send(404, {'error': 'not found'})

    def log_message(self, *a): pass

def _intake_daily_loop():
    """משיכת קוויטלים מהמייל — פעם ביום (וגם פעם עם עליית השרת). רץ רק אם ה-Gmail מוגדר."""
    import time
    try:
        import gmail_intake
    except Exception:
        return
    first = True
    while True:
        try:
            if gmail_intake.configured():
                if first:
                    time.sleep(20)   # להמתין שהשרת יתייצב לפני המשיכה הראשונה
                con = db(); res = gmail_intake.sync(con); con.close()
                print('  משיכת קוויטלים אוטומטית:', res)
                con = db(); res2 = gmail_intake.sync_contacts(con); con.close()
                print('  תיוק מיילים ליומן הקשר:', res2)
        except Exception as e:
            print('  שגיאת משיכה אוטומטית:', e)
        first = False
        time.sleep(24 * 3600)   # שוב מחר

def serve():
    ensure_schema()
    import threading
    threading.Thread(target=_intake_daily_loop, daemon=True).start()
    print(f'CRM כולל חצות רץ על פורט {PORT}')
    ThreadingHTTPServer(('0.0.0.0', PORT), H).serve_forever()

if __name__ == '__main__':
    serve()
