# -*- coding: utf-8 -*-
"""שרת CRM כולל חצות — מגיש את הממשק + API לשמירה (SQLite)."""
import sqlite3, json, os, re, base64, datetime, csv, io, gzip, time, hashlib, threading, urllib.parse
from urllib.parse import quote

def today_iso():
    return datetime.date.today().isoformat()

def now_iso():
    return datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from hebdate import week_before, greg_to_heb_monthyear, greg_to_heb_full, current_heb_year, heb_to_greg, future_parnes, heb_greg_year, kvittel_default_month, HMONTHS

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

def emails_of(s):
    """כל כתובות המייל של תורם. לתורם יכולות להיות כמה כתובות בשדה אחד,
    מופרדות בפסיק / נקודה-פסיק / קו נטוי / רווח — כולן משמשות לזיהוי ולשליחה."""
    return [e for e in re.split(r'[;,/\s]+', (s or '').strip().lower()) if '@' in e]

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
    CREATE TABLE IF NOT EXISTS task_kinds(name TEXT PRIMARY KEY, created TEXT);
    CREATE TABLE IF NOT EXISTS pay_channels(name TEXT PRIMARY KEY, created TEXT);
    CREATE TABLE IF NOT EXISTS contact_kinds(name TEXT PRIMARY KEY, created TEXT);
    CREATE TABLE IF NOT EXISTS avreichim(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE,
        last TEXT, first TEXT, note TEXT, started TEXT, created TEXT);
    CREATE TABLE IF NOT EXISTS avreich_log(id INTEGER PRIMARY KEY AUTOINCREMENT, avreich TEXT,
        donor_id INTEGER, date TEXT, hdate TEXT, text TEXT, at TEXT);
    CREATE TABLE IF NOT EXISTS deleted_donors(key TEXT PRIMARY KEY, last TEXT, first TEXT,
        english TEXT, created TEXT);
    CREATE TABLE IF NOT EXISTS name_map(src TEXT PRIMARY KEY, donor_id INTEGER,
        ignored INTEGER DEFAULT 0, created TEXT);
    CREATE TABLE IF NOT EXISTS pay_split(id INTEGER PRIMARY KEY AUTOINCREMENT,
        payer_id INTEGER, donor_id INTEGER, pct REAL DEFAULT 50, note TEXT, created TEXT,
        UNIQUE(payer_id, donor_id));
    CREATE TABLE IF NOT EXISTS sugg_reject(donor_id INTEGER, kind TEXT, val TEXT, created TEXT);
    CREATE TABLE IF NOT EXISTS intake(id INTEGER PRIMARY KEY AUTOINCREMENT, message_id TEXT UNIQUE,
        from_name TEXT, from_email TEXT, subject TEXT, received TEXT, body TEXT, names TEXT,
        donor_id INTEGER, status TEXT DEFAULT 'new', created TEXT);
    """)
    # מיגרציה — הוספת עמודות חדשות אם חסרות (דיסק קבוע קיים)
    for col, ddl in [('phone', 'TEXT'), ('email', 'TEXT'), ('addr', 'TEXT'), ('ended', 'TEXT')]:
        try: con.execute('ALTER TABLE avreichim ADD COLUMN %s %s' % (col, ddl))
        except Exception: pass
    for col, ddl in [('start_date', 'TEXT'), ('amount', 'TEXT'), ('active', 'INTEGER DEFAULT 1'), ('ended_date', 'TEXT'), ('method', 'TEXT'), ('partner_with', 'TEXT'), ('partner_with_id', 'INTEGER'), ('renew_date', 'TEXT'), ('paid_note', 'TEXT'), ('joint', 'INTEGER DEFAULT 0'), ('paid_thru', 'TEXT'), ('joint_payer', 'INTEGER'), ('share', 'TEXT')]:
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
    # חוב יש"ז שמאיר מעדכן ידנית — גובר על החישוב האוטומטי מהתרומות
    try: con.execute("ALTER TABLE donors ADD COLUMN iz_debt TEXT")
    except Exception: pass
    # "החוב סודר" — מאיר סיכם עם התורם דרך אחרת. תאריך הסידור וההסבר.
    try: con.execute("ALTER TABLE donors ADD COLUMN debt_ok TEXT")
    except Exception: pass
    try: con.execute("ALTER TABLE donors ADD COLUMN debt_note TEXT")
    except Exception: pass
    # התחייבות חוזרת מדי חודש (למשל נר למאור) — להבדיל מהתחייבות חד־פעמית
    try: con.execute("ALTER TABLE pledges ADD COLUMN monthly INTEGER DEFAULT 0")
    except Exception: pass
    try: con.execute("ALTER TABLE donors ADD COLUMN notes TEXT")   # הערות חופשיות (למשל: הגיע דרך אבא קלוק)
    except Exception: pass
    try: con.execute("ALTER TABLE contacts_log ADD COLUMN msg_id TEXT")   # מזהה מייל — למניעת תיוק כפול
    except Exception: pass
    try: con.execute("ALTER TABLE contacts_log ADD COLUMN body TEXT")     # גוף המייל (רק מה שהתורם כתב)
    except Exception: pass
    try: con.execute("ALTER TABLE contacts_log ADD COLUMN att_checked INTEGER DEFAULT 0")  # נבדקו קבצים מצורפים
    except Exception: pass
    try: con.execute("ALTER TABLE contacts_log ADD COLUMN body_he TEXT")   # תרגום המייל לעברית
    except Exception: pass
    try: con.execute("ALTER TABLE contacts_log ADD COLUMN direction TEXT DEFAULT ''")  # 'out' = מייל ששלחנו לתורם
    except Exception: pass
    # תיעוד ביצוע משימה — מתי בוצעה ובידי מי, ורישום הקשר שנוצר ממנה
    try: con.execute("ALTER TABLE tasks ADD COLUMN done_date TEXT")
    except Exception: pass
    try: con.execute("ALTER TABLE tasks ADD COLUMN done_by TEXT")
    except Exception: pass
    # שעת הביצוע לפי השעון של מאיר (הדפדפן שולח אותה) — השרת רץ בשעון אחר
    try: con.execute("ALTER TABLE tasks ADD COLUMN done_at TEXT")
    except Exception: pass
    try: con.execute("ALTER TABLE contacts_log ADD COLUMN task_id INTEGER")
    except Exception: pass
    try: con.execute("ALTER TABLE contacts_log ADD COLUMN at TEXT")
    except Exception: pass
    # תשובה שמאיר ענה על פנייה — נתלית מתחת לפנייה עצמה ולא כרישום נפרד
    try: con.execute("ALTER TABLE contacts_log ADD COLUMN reply_to INTEGER")
    except Exception: pass
    # זוגות שנבדקו וסומנו "לא אותו אדם" — לא יופיעו שוב ברשימת המיזוג
    try: con.execute("CREATE TABLE IF NOT EXISTS not_dupes(a INTEGER, b INTEGER, created TEXT, PRIMARY KEY(a,b))")
    except Exception: pass
    # הצעות כתובת שנדחו — לא יוצעו שוב לאותו תורם
    try: con.execute("CREATE TABLE IF NOT EXISTS addr_reject(donor_id INTEGER, addr TEXT, created TEXT, PRIMARY KEY(donor_id,addr))")
    except Exception: pass
    try: con.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_clog_msg ON contacts_log(msg_id) WHERE msg_id IS NOT NULL AND msg_id<>''")
    except Exception: pass
    # סימון "לא צריך קוויטל" (וי אדום) — כדי להסיר מרשימת חסרי־שמות בלי לשנות דרגה
    # כלל קבוע לתורם: סכום מסוים אצלו תמיד שייך לאותו ייעוד (למשל $3,500 = מעקות · בניין)
    try:
        con.execute("CREATE TABLE IF NOT EXISTS donor_rules(id INTEGER PRIMARY KEY AUTOINCREMENT, "
                    "donor_id INTEGER, amount REAL, category TEXT, note TEXT, created TEXT)")
        con.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_rule_donor ON donor_rules(donor_id,amount)")
    except Exception:
        pass

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
        # חיוב שמאיר דחה במפורש ("דלג") — לא חוזר לכרטיס גם בשחזור אוטומטי
        try: con.execute("ALTER TABLE recon ADD COLUMN skipped INTEGER DEFAULT 0")
        except Exception: pass
        # חיוב שנדחה אבל סודר בדרך אחרת — יורד מהחוב בלחיצה אחת
        try: con.execute("ALTER TABLE recon ADD COLUMN no_debt INTEGER DEFAULT 0")
        except Exception: pass
        # חיוב שנדחה שמאיר סימן במפורש כחוב אמיתי. חיוב שנדחה אינו חוב
        # מעצמו — ברוב המקרים ניסו לחייב שוב וזה עבר, או שהתורם שילם באותו
        # חודש בדרך אחרת. רק סימון ידני מכניס אותו לסכום החוב.
        try: con.execute("ALTER TABLE recon ADD COLUMN is_debt INTEGER DEFAULT 0")
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
    # ---- צ'ייס ינואר–7 באוגוסט 2026: רק כסף שנכנס (זל, ACH, העברות בנקאיות) ----
    # הדוח שמאיר שלח מסונן ל"All credit transactions" — אין בו שום חיוב שיצא.
    try:
        cp = os.path.join(HERE, 'chase_seed.json')
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='recon_chase_v1'").fetchone() and os.path.exists(cp):
            def _ne(s): return re.sub(r'[^a-z0-9]', '', (s or '').lower())
            byeng = {}
            for d in con.execute("SELECT id,english,business FROM donors"):
                for v in (d['english'], d['business']):
                    if (v or '').strip():
                        byeng.setdefault(_ne(v), d['id'])
            con.execute("DELETE FROM recon WHERE source LIKE \"צ'ייס%\" AND COALESCE(processed,0)=0")
            nr = matched = 0
            for x in json.load(open(cp, encoding='utf-8')):
                did = byeng.get(_ne(x['name']))
                con.execute("""INSERT OR IGNORE INTO recon(tid,first,last,amount,date,addr,city,state,zip,
                                   phone,email,recurring,donor_id,category,processed,source,status)
                               VALUES(?,?,?,?,?,'','','','','','',0,?,?,0,?,'settled')""",
                            (x['tid'], x['first'], x['last'], x['amount'], x['date'], did,
                             x.get('note', ''), "צ'ייס " + x['method']))
                nr += 1
                if did: matched += 1
            con.execute("INSERT INTO seed_flags(name) VALUES('recon_chase_v1')")
            matched += apply_name_map(con)      # שמות שמאיר כבר שייך פעם אחת
            print(f"  צ'ייס ינו-אוג: נטענו {nr}, הותאמו {matched}")
    except Exception as e:
        print("  שגיאת צ'ייס:", e)
    # יום פרנס שנרשם כמה פעמים לאותו תורם — יום אחד ולא חמישה. שומרים את
    # השורה הראשונה, ומעבירים אליה גבייה/סכום/הקדשה שנרשמו על הכפולות.
    try:
        seen, dead = {}, []
        for r in con.execute("SELECT id,donor_id,kind,date_text,hyear,amount,dedication,paid,"
                             "method,currency FROM parnes WHERE COALESCE(status,'')<>'suggested' "
                             "ORDER BY id"):
            k = (r['donor_id'], r['kind'] or '', r['date_text'] or '', r['hyear'] or '')
            if k not in seen:
                seen[k] = dict(r); continue
            keep = seen[k]
            for c in ('amount', 'dedication', 'method', 'currency'):
                if not str(keep.get(c) or '').strip() and str(r[c] or '').strip():
                    con.execute("UPDATE parnes SET %s=? WHERE id=?" % c, (r[c], keep['id']))
                    keep[c] = r[c]
            if int(r['paid'] or 0) and not int(keep.get('paid') or 0):
                con.execute("UPDATE parnes SET paid=1 WHERE id=?", (keep['id'],))
                keep['paid'] = 1
            dead.append(r['id'])
        for i in dead:
            con.execute("DELETE FROM parnes WHERE id=?", (i,))
        if dead:
            print('  ימי פרנס כפולים שאוחדו: %d' % len(dead))
    except Exception as e:
        print('  parnes dedup error:', e)
    # מטבע ליום פרנס — תורם בארץ ב-₪, כל השאר ב-$
    try:
        n = con.execute("""UPDATE parnes SET currency=(
                             SELECT CASE WHEN COALESCE(d.region,'')='il' THEN '₪' ELSE '$' END
                             FROM donors d WHERE d.id=parnes.donor_id)
                           WHERE COALESCE(TRIM(currency),'')=''""").rowcount
        if n:
            print('  מטבע שהושלם לימי פרנס: %d' % n)
    except Exception as e:
        print('  parnes currency error:', e)
    # יצחק אדלין ואלירן דהאן שולחים לבנק העברה אחת ומתחלקים בה חצי־חצי.
    # הכסף מגיע על שם אדלין, ולכן כל סכום שלו נחתך לשניים בין שני הכרטיסים.
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='paysplit_adlin_v1'").fetchone():
            a = con.execute("SELECT id FROM donors WHERE last='אדלין' AND first='יצחק'").fetchone()
            e = con.execute("SELECT id FROM donors WHERE last LIKE 'דה%ן' AND first='אלירן'").fetchone()
            if a and e:
                con.execute("INSERT OR IGNORE INTO pay_split(payer_id,donor_id,pct,note,created) "
                            "VALUES(?,?,50,'ההעברה מגיעה על שם אדלין — חצי־חצי',?)",
                            (a['id'], e['id'], today_iso()))
                print('  אדלין/דהאן: נרשמה חלוקה חצי־חצי')
            con.execute("INSERT INTO seed_flags(name) VALUES('paysplit_adlin_v1')")
        # רץ בכל עלייה — סכום שאושר לתורם אחרי שנקבעה החלוקה נחתך גם הוא
        n = apply_pay_split(con)
        if n:
            print('  סכומים שנחתכו בין שותפים לתשלום: %d' % n)
    except Exception as e:
        print('  paysplit error:', e)
    # שם שנכתב בבנק עם שגיאת הקלדה של אות אחת — Rosenfed במקום Rosenfeld וכדומה
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='recon_nearnames_v1'").fetchone():
            n = link_near_names(con)
            con.execute("INSERT INTO seed_flags(name) VALUES('recon_nearnames_v1')")
            print('  חיובים ששויכו למרות שגיאת כתיב בשם: %d' % n)
    except Exception as e:
        print('  near names error:', e)
    # TOSFOSYOMTOV02 בצ'ייס = משה דויטש. שתיים משלוש השורות כתוב בהן במפורש
    # "zichron avos from moishe deutsch", והשלישית באה מאותו ORIG ID.
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='chase_deutsch_v1'").fetchone():
            r = con.execute("SELECT id FROM donors WHERE last='דויטש' AND first LIKE 'משה%'").fetchone()
            if r:
                con.execute("INSERT OR REPLACE INTO name_map(src,donor_id,ignored,created) "
                            "VALUES('tosfosyomtov02',?,0,?)", (r['id'], today_iso()))
                n = apply_name_map(con)
                print('  משה דויטש: %d העברות ACH מצ\'ייס שויכו לכרטיס' % n)
            con.execute("INSERT INTO seed_flags(name) VALUES('chase_deutsch_v1')")
    except Exception as e:
        print('  chase deutsch error:', e)
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

    # תאריך מדויק לתרומות שנוצרו מחיובי אשראי — היו שמורות עם חודש בלבד
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='exact_dates_v1'").fetchone():
            MONX = {'Jan':'01','Feb':'02','Mar':'03','Apr':'04','May':'05','Jun':'06',
                    'Jul':'07','Aug':'08','Sep':'09','Oct':'10','Nov':'11','Dec':'12'}
            # מפה: (תורם, חודש, סכום) -> יום מדויק מהחיוב. רק כשיש התאמה יחידה
            cand = {}
            for r in con.execute("SELECT donor_id,date,amount FROM recon WHERE donor_id IS NOT NULL"):
                m = re.match(r'(\d{2})-([A-Za-z]{3})-(\d{4})', r['date'] or '')
                if not m:
                    continue
                key = (r['donor_id'], f"{m.group(3)}-{MONX.get(m.group(2),'01')}", round(float(r['amount'] or 0), 2))
                cand.setdefault(key, set()).add(m.group(1))
            nfix = 0
            for r in con.execute("""SELECT id,donor_id,date,amount FROM donations
                                    WHERE length(COALESCE(date,''))=7 AND method IN ('Authorize','Banquest')"""):
                try:
                    key = (r['donor_id'], r['date'], round(float(r['amount'] or 0), 2))
                except Exception:
                    continue
                days = cand.get(key)
                if days and len(days) == 1:      # יום אחד ברור — לא מנחשים
                    con.execute("UPDATE donations SET date=? WHERE id=?",
                                (r['date'] + '-' + list(days)[0], r['id']))
                    nfix += 1
            con.execute("INSERT INTO seed_flags(name) VALUES('exact_dates_v1')")
            print(f'  תאריך מדויק לתרומות אשראי: {nfix}')
    except Exception as e:
        print('  exact dates error:', e)

    # אוולין וולסי־פיינגולד: כרטיס כפול + תרומות אקסל שגויות. החיובים בפועל הם המקור הנכון.
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='finegold_fix_v1'").fetchone():
            k = con.execute("""SELECT id FROM donors WHERE last LIKE '%וולסי%' AND last LIKE '%פיינגולד%'
                               ORDER BY id LIMIT 1""").fetchone()
            o = con.execute("""SELECT id FROM donors WHERE last LIKE 'פיינגולד%' AND last NOT LIKE '%וולסי%'
                               AND COALESCE(first,'') LIKE '%וולסין%' ORDER BY id LIMIT 1""").fetchone()
            if k:
                keep = k['id']
                if o and o['id'] != keep:
                    drop = o['id']
                    for t in ('pledges', 'parnes', 'prayers', 'donations', 'contacts_log',
                              'tasks', 'partners', 'transactions', 'building'):
                        try: con.execute(f"UPDATE {t} SET donor_id=? WHERE donor_id=?", (keep, drop))
                        except Exception: pass
                    for t in ('recon', 'intake'):
                        try: con.execute(f"UPDATE {t} SET donor_id=? WHERE donor_id=?", (keep, drop))
                        except Exception: pass
                    # שדות שחסרים בכרטיס שנשאר — משלימים מהכרטיס שנמחק
                    for f in ('english', 'amount', 'category', 'tier', 'channel', 'phone', 'email'):
                        try:
                            con.execute(f"""UPDATE donors SET {f}=(SELECT {f} FROM donors WHERE id=?)
                                            WHERE id=? AND COALESCE(TRIM({f}),'')=''""", (drop, keep))
                        except Exception: pass
                    con.execute("DELETE FROM donors WHERE id=?", (drop,))
                # תרומות סיכום מהאקסל של $100 — לא נגבו בפועל, מוחקים
                ndel = con.execute("""DELETE FROM donations WHERE donor_id=? AND note='ייבוא 2026'
                                      AND method='Authorize' AND CAST(amount AS REAL)=100""", (keep,)).rowcount
                # כל חיובי האשראי שלה (שני האיותים) משויכים לכרטיס הזה
                con.execute("""UPDATE recon SET donor_id=? WHERE lower(last) LIKE '%finegold%'
                               AND (donor_id IS NULL OR donor_id<>?)""", (keep, keep))
                # כתובת עדכנית — אוהיו
                con.execute("""UPDATE donors SET addr=?, city=?, region=?, zip=?, country=? WHERE id=?""",
                            ('22626 Calverton Road', 'Beachwood', 'OH', '44122', 'US', keep))
                con.execute("INSERT INTO seed_flags(name) VALUES('finegold_fix_v1')")
                print(f'  פיינגולד: אוחדו כרטיסים, נמחקו {ndel} תרומות $100 שגויות, החיובים שויכו')
    except Exception as e:
        print('  finegold fix error:', e)

    # פיצול קירזנר: יוסי (הרטשטיין) וישראל/שארפ (וייל) — שני מנויים נפרדים שנרשמו על כרטיס אחד
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='kirzner_split_v1'").fetchone():
            y = con.execute("""SELECT * FROM donors WHERE last LIKE '%קירזנר%'
                               AND id IN (SELECT donor_id FROM partners WHERE avreich LIKE '%הרטשטיין%')""").fetchone()
            s = con.execute("""SELECT * FROM donors WHERE last LIKE '%קירזנר%'
                               AND (last LIKE '%harp%' OR last LIKE '%שארפ%' OR LOWER(COALESCE(business,'')) LIKE '%harp%')
                               ORDER BY id LIMIT 1""").fetchone()
            if not y:
                print('  קירזנר: לא נמצא כרטיס עם הרטשטיין — מדלג')
            else:
                yid = y['id']
                # פרטי הקשר שיושבים על כרטיס "שארפ" הם של יוסי (yossikirzner@gmail.com) — מעבירים אליו
                if s:
                    sid = s['id']
                    for col in ('email', 'phone', 'addr', 'city', 'country', 'zip'):
                        if (s[col] or '').strip() and not (y[col] or '').strip():
                            con.execute(f"UPDATE donors SET {col}=? WHERE id=?", (s[col], yid))
                else:
                    con.execute("INSERT INTO donors(last,first,created,source) VALUES('קירזנר','ישראל',?,'פיצול קירזנר')",
                                (today_iso(),))
                    sid = con.execute("SELECT last_insert_rowid()").fetchone()[0]
                # כרטיס ישראל — פרטי החברה מתוך חיובי האוטורייז של Sharp Managment
                con.execute("""UPDATE donors SET last='קירזנר', first='ישראל', english='Izzy Kirzner',
                               business='Sharp Managment', email='ikirzner@sharpmgmt.com', phone='+1 917-209-5919',
                               addr='2365 Nostrand Ave, 2nd Floor', city='Brooklyn', country='NY', zip='11210',
                               category=?, tier=?, channel=?, amount='1000', months=?, pay_status=?, region=?
                               WHERE id=?""",
                            (y['category'] or 'קבוע', y['tier'] or 'יששכר_זבולון', y['channel'] or 'בנק_ווסט',
                             y['months'] or '', y['pay_status'] or '', y['region'] or '', sid))
                con.execute("UPDATE donors SET amount='1000' WHERE id=?", (yid,))
                # האברך של ישראל — וייל; הרטשטיין נשאר אצל יוסי
                con.execute("UPDATE partners SET donor_id=? WHERE donor_id=? AND avreich LIKE '%וייל%'", (sid, yid))
                # הקוויטל של יוסי הועתק בעבר גם לכרטיס "שארפ" — מקור הבלבול. מוחקים את הכפילות מכרטיס ישראל
                con.execute("""DELETE FROM prayers WHERE donor_id=? AND TRIM(COALESCE(text,'')) IN
                               (SELECT TRIM(COALESCE(text,'')) FROM prayers WHERE donor_id=?)""", (sid, yid))
                # מפת ימי החיוב האמיתיים בבנק ווסט: מנוי "Yossi Kirzner" ב-15, מנוי "Kirzner" (החברה) ב-20
                MONB = {'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04', 'May': '05', 'Jun': '06',
                        'Jul': '07', 'Aug': '08', 'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12'}
                dy, ds = {}, {}
                for r in con.execute("""SELECT first,last,amount,date FROM recon
                                        WHERE source LIKE 'Banquest%' AND last LIKE '%irzner%'"""):
                    mm = re.match(r'(\d{2})-([A-Za-z]{3})-(\d{4})', r['date'] or '')
                    if not mm or round(float(r['amount'] or 0), 2) != 1000.0:
                        continue
                    key = f"{mm.group(3)}-{MONB.get(mm.group(2), '01')}"
                    (dy if (r['first'] or '').strip().lower() == 'yossi' else ds)[key] = mm.group(1)
                # חלוקת התרומות הכפולות — אחת לכל אח, עם היום המדויק של המנוי שלו
                moved = fixed = flagged = 0
                bym = {}
                for r in con.execute("""SELECT id,date FROM donations WHERE donor_id=? AND note LIKE 'ייבוא 2026%'
                                        AND method='Banquest' AND ROUND(CAST(amount AS REAL),2)=1000.0
                                        ORDER BY date, id""", (yid,)):
                    bym.setdefault((r['date'] or '')[:7], []).append(r['id'])
                for mon, ids in bym.items():
                    if len(ids) >= 2:                      # השורה השנייה שייכת לישראל
                        con.execute("UPDATE donations SET donor_id=? WHERE id=?", (sid, ids[1]))
                        moved += 1
                        if ds.get(mon):
                            con.execute("UPDATE donations SET date=? WHERE id=?", (mon + '-' + ds[mon], ids[1])); fixed += 1
                    if dy.get(mon):                        # ליוסי — היום של המנוי שלו
                        con.execute("UPDATE donations SET date=? WHERE id=?", (mon + '-' + dy[mon], ids[0])); fixed += 1
                    else:                                  # אין חיוב תואם בבנק ווסט — מסמנים לבדיקה
                        con.execute("UPDATE donations SET note='ייבוא 2026 · לבדוק — אין חיוב תואם' WHERE id=?", (ids[0],))
                        flagged += 1
                # שיוך שורות החיוב לאח הנכון, כדי שהאישור בדף חיובים ייפול למקום
                con.execute("""UPDATE recon SET donor_id=? WHERE source LIKE 'Banquest%' AND last LIKE '%irzner%'
                               AND LOWER(TRIM(first))='kirzner' AND COALESCE(processed,0)=0""", (sid,))
                con.execute("""UPDATE recon SET donor_id=? WHERE source LIKE 'Banquest%' AND last LIKE '%irzner%'
                               AND LOWER(TRIM(first))='yossi' AND COALESCE(processed,0)=0""", (yid,))
                con.execute("""UPDATE recon SET donor_id=? WHERE LOWER(TRIM(email))='ikirzner@sharpmgmt.com'
                               AND LOWER(TRIM(first))='izzy' AND COALESCE(processed,0)=0""", (sid,))
                con.execute("""UPDATE recon SET donor_id=? WHERE LOWER(TRIM(email))='yaelkirzner@gmail.com'
                               AND COALESCE(processed,0)=0""", (yid,))
                for did, note in ((sid, 'קירזנר ישראל (שארפ) — לאמת אימייל וכתובת, ולקבל שמות לקוויטל'),
                                  (sid, 'מרטין קירזנר $5,000 (24/3) חויב מאותו כרטיס של שארפ — לברר אם שייך לישראל או לכרטיס נפרד'),
                                  (yid, 'קירזנר יוסי — ינואר ופברואר רשומים $1,000 בלי חיוב תואם; ב-26/2 נגבו $4,000+$1,800 שטרם אושרו. להשוות')):
                    if not con.execute("SELECT 1 FROM tasks WHERE donor_id=? AND note=?", (did, note)).fetchone():
                        con.execute("INSERT INTO tasks(donor_id,due_date,kind,note) VALUES(?,?,'check',?)",
                                    (did, today_iso(), note))
                con.execute("INSERT INTO seed_flags(name) VALUES('kirzner_split_v1')")
                print(f'  פיצול קירזנר: יוסי #{yid} / ישראל #{sid} — הועברו {moved} תרומות, תאריך מדויק {fixed}, לבדיקה {flagged}')
    except Exception as e:
        print('  kirzner split error:', e)

    # קירזנר — השלמות מהמשרד: שני חיובי קמחא דפסחא של ישראל, ויעל (הכלה) בכרטיס נפרד
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='kirzner_split_v2'").fetchone():
            yr = con.execute("""SELECT id FROM donors WHERE last LIKE '%קירזנר%'
                                AND id IN (SELECT donor_id FROM partners WHERE avreich LIKE '%הרטשטיין%')""").fetchone()
            sr = con.execute("""SELECT id FROM donors WHERE last LIKE '%קירזנר%'
                                AND (LOWER(COALESCE(business,'')) LIKE '%harp%' OR LOWER(COALESCE(email,'')) LIKE '%sharpmgmt%')
                                ORDER BY id LIMIT 1""").fetchone()
            if not sr:
                print('  קירזנר v2: לא נמצא כרטיס שארפ — מדלג')
            else:
                sid = sr['id']
                # שני החיובים של 24/3 שייכים לישראל — הוא נתן, והבת נתנה בשמו. קמחא דפסחא תשפ"ו
                con.execute("""UPDATE recon SET donor_id=?, category='קמחא דפסחא תשפ"ו'
                               WHERE LOWER(TRIM(email))='ikirzner@sharpmgmt.com' AND COALESCE(processed,0)=0""", (sid,))
                nt = 'מרטין קירזנר — הבת של ישראל; נתנה $5,000 קמחא דפסחא תשפ"ו בשמו (בנוסף ל-$5,000 שלו)'
                old = (con.execute("SELECT notes FROM donors WHERE id=?", (sid,)).fetchone()['notes'] or '').strip()
                if nt not in old:
                    con.execute("UPDATE donors SET notes=? WHERE id=?", ((old + ' · ' + nt).strip(' ·') if old else nt, sid))
                con.execute("DELETE FROM tasks WHERE donor_id=? AND note LIKE 'מרטין קירזנר $5,000%'", (sid,))
                try: con.execute("""INSERT OR IGNORE INTO campaigns(name,created) VALUES('קמחא דפסחא תשפ"ו',?)""", (today_iso(),))
                except Exception: pass
                # יעל — הכלה. כרטיס נפרד לגמרי, ולא אצל יוסי
                yl = con.execute("""SELECT id FROM donors WHERE last LIKE '%קירזנר%'
                                    AND (first LIKE '%יעל%' OR LOWER(COALESCE(email,'')) LIKE '%yaelkirzner%')
                                    ORDER BY id LIMIT 1""").fetchone()
                if yl:
                    lid = yl['id']
                else:
                    con.execute("""INSERT INTO donors(last,first,english,phone,email,addr,city,country,zip,
                                                      category,region,created,source)
                                   VALUES('קירזנר','יעל','Yael Kirzner','+1 718-640-8361','yaelkirzner@gmail.com',
                                          '766 Sherwood St','Valley Stream','NY','11581','מזדמן','us',?,'פיצול קירזנר')""",
                                (today_iso(),))
                    lid = con.execute("SELECT last_insert_rowid()").fetchone()[0]
                con.execute("""UPDATE recon SET donor_id=? WHERE LOWER(TRIM(email))='yaelkirzner@gmail.com'
                               AND COALESCE(processed,0)=0""", (lid,))
                if yr:
                    con.execute("UPDATE tasks SET note=REPLACE(note,'; ב-26/2',' · ב-26/2') WHERE donor_id=?", (yr['id'],))
                con.execute("INSERT INTO seed_flags(name) VALUES('kirzner_split_v2')")
                print(f'  קירזנר v2: קמחא דפסחא לישראל #{sid}, יעל בכרטיס נפרד #{lid}')
    except Exception as e:
        print('  kirzner v2 error:', e)

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

    # מיזוג בנק ווסט: כל חיוב שטרם אושר, מסווג לפי כל הנתונים שיש — רשימות החגים,
    # דרגת יששכר־זבולון, דוח הקבועים והוראות הקבע. מה שלא מזוהה בוודאות נשאר לאישור ידני.
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='bankwest_merge_v1'").fetchone():
            camp = {}
            try:
                with open(os.path.join(HERE, 'campaign_lists.json'), encoding='utf-8') as f:
                    for L in json.load(f).get('lists', []):
                        for x in campaign_match(con, L['rows'], L.get('from', ''), L.get('to', '')):
                            if x['donor_id']:
                                camp.setdefault(x['donor_id'], []).append((x['amount'], L['label']))
            except Exception as e:
                print('  bankwest: אין רשימות חגים —', e)
            subs = {}
            try:
                with open(os.path.join(HERE, 'donations_2026_seed.json'), encoding='utf-8') as f:
                    for r in json.load(f):
                        subs.setdefault(r['donor_id'], []).append(
                            (round(float(r['amount']), 2), r.get('category') or 'קבוע'))
            except Exception:
                pass
            dinfo = {r['id']: (r['tier'] or '', r['category'] or '')
                     for r in con.execute("SELECT id,tier,category FROM donors")}
            q = ("SELECT tid,donor_id,amount,date,recurring FROM recon "
                 "WHERE source LIKE 'Banquest%' AND COALESCE(processed,0)=0 "
                 "AND COALESCE(status,'settled')='settled' AND donor_id IS NOT NULL")
            ins = repl = left = 0
            by = {}
            for r in list(con.execute(q)):
                did = r['donor_id']
                a = round(float(r['amount'] or 0), 2)
                diso = _recon_iso(r['date'])
                if not diso:
                    left += 1
                    continue
                tier, dcat = dinfo.get(did, ('', ''))
                cat = why = ''
                for amt, lbl in camp.get(did, []):
                    if abs(amt - a) < 0.01:
                        cat, why = lbl, lbl
                        break
                if not cat:
                    for amt, c in subs.get(did, []):
                        if abs(amt - a) < 0.01:
                            cat, why = c, 'דוח הקבועים'
                            break
                if not cat and r['recurring'] and 'יששכר' in tier:
                    cat, why = 'יששכר־זבולון', 'דרגת יששכר־זבולון'
                if not cat and r['recurring']:
                    cat, why = (dcat or 'קבוע'), 'הוראת קבע'
                if not cat:
                    left += 1
                    continue
                if con.execute("SELECT 1 FROM donations WHERE donor_id=? AND date=? AND method='Banquest' "
                               "AND ROUND(CAST(amount AS REAL),2)=?", (did, diso, a)).fetchone():
                    con.execute("UPDATE recon SET processed=1, category=? WHERE tid=?", (cat, r['tid']))
                    continue                      # כבר רשומה — רק סוגרים את השורה בתור
                # שורת הסיכום החודשית מדוח הקבועים מוחלפת בחיוב האמיתי — אותו כסף, תאריך מדויק
                n = con.execute("DELETE FROM donations WHERE donor_id=? AND substr(COALESCE(date,''),1,7)=? "
                                "AND COALESCE(note,'') LIKE 'ייבוא 2026%' AND method='Banquest' "
                                "AND ROUND(CAST(amount AS REAL),2)=?", (did, diso[:7], a)).rowcount
                repl += max(0, n)
                con.execute("INSERT INTO donations(donor_id,date,amount,category,method,note,paid) "
                            "VALUES(?,?,?,?,'Banquest',?,1)",
                            (did, diso, r['amount'], cat, 'ייבוא בנק ווסט · ' + why))
                con.execute("UPDATE recon SET processed=1, category=? WHERE tid=?", (cat, r['tid']))
                ins += 1
                by[why] = by.get(why, 0) + 1
            con.execute("INSERT INTO seed_flags(name) VALUES('bankwest_merge_v1')")
            print('  מיזוג בנק ווסט: נכנסו %d, הוחלפו %d שורות סיכום, נשארו לאישור %d' % (ins, repl, left))
            for k, v in sorted(by.items(), key=lambda x: -x[1]):
                print('      %-24s %d' % (k, v))
    except Exception as e:
        print('  bankwest merge error:', e)

    # סבב שני: כל שאר חיובי בנק ווסט שיש להם כרטיס ולא סווגו — נכנסים לפי הקטגוריה של הכרטיס,
    # מסומנים "לא סווג", ולכל תורם נפתחת משימה אחת לבדוק עבור מה. הכסף נכנס, הבדיקה נשארת פתוחה.
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='bankwest_merge_v2'").fetchone():
            dinfo = {r['id']: ((r['category'] or ''), ((r['last'] or '') + ' ' + (r['first'] or '')).strip())
                     for r in con.execute("SELECT id,category,last,first FROM donors")}
            q = ("SELECT tid,donor_id,amount,date FROM recon "
                 "WHERE source LIKE 'Banquest%' AND COALESCE(processed,0)=0 "
                 "AND COALESCE(status,'settled')='settled' AND donor_id IS NOT NULL")
            ins = 0
            perdonor = {}
            for r in list(con.execute(q)):
                did = r['donor_id']
                a = round(float(r['amount'] or 0), 2)
                diso = _recon_iso(r['date'])
                if not diso:
                    continue
                cat = (dinfo.get(did, ('', ''))[0]) or 'מזדמן'
                if con.execute("SELECT 1 FROM donations WHERE donor_id=? AND date=? AND method='Banquest' "
                               "AND ROUND(CAST(amount AS REAL),2)=?", (did, diso, a)).fetchone():
                    con.execute("UPDATE recon SET processed=1, category=? WHERE tid=?", (cat, r['tid']))
                    continue
                con.execute("DELETE FROM donations WHERE donor_id=? AND substr(COALESCE(date,''),1,7)=? "
                            "AND COALESCE(note,'') LIKE 'ייבוא 2026%' AND method='Banquest' "
                            "AND ROUND(CAST(amount AS REAL),2)=?", (did, diso[:7], a))
                con.execute("INSERT INTO donations(donor_id,date,amount,category,method,note,paid) "
                            "VALUES(?,?,?,?,'Banquest','ייבוא בנק ווסט · לא סווג — לבדוק עבור מה',1)",
                            (did, diso, r['amount'], cat))
                con.execute("UPDATE recon SET processed=1, category=? WHERE tid=?", (cat, r['tid']))
                ins += 1
                perdonor[did] = perdonor.get(did, 0) + 1
            # ללא משימות — השאלות מוצגות בדף החיובים ובכרטיס התורם
            con.execute("INSERT INTO seed_flags(name) VALUES('bankwest_merge_v2')")
            print('  בנק ווסט סבב שני: נכנסו %d חיובים אצל %d תורמים (מסומנים לבדיקה)' % (ins, len(perdonor)))
    except Exception as e:
        print('  bankwest v2 error:', e)

    # מיזוג אוטורייז — אותו היגיון כמו בנק ווסט. חיובי פרנס לילה ($480) לא נכנסים כאן:
    # הם דורשים בחירת יום עברי, ולכן נשארים לאישור בדף החיובים.
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='authorize_merge_v1'").fetchone():
            camp = {}
            try:
                with open(os.path.join(HERE, 'campaign_lists.json'), encoding='utf-8') as f:
                    for L in json.load(f).get('lists', []):
                        for x in campaign_match(con, L['rows'], L.get('from', ''), L.get('to', '')):
                            if x['donor_id']:
                                camp.setdefault(x['donor_id'], []).append((x['amount'], L['label']))
            except Exception:
                pass
            subs = {}
            try:
                with open(os.path.join(HERE, 'donations_2026_seed.json'), encoding='utf-8') as f:
                    for r in json.load(f):
                        subs.setdefault(r['donor_id'], []).append(
                            (round(float(r['amount']), 2), r.get('category') or 'קבוע'))
            except Exception:
                pass
            dinfo = {r['id']: ((r['tier'] or ''), (r['category'] or ''),
                               ((r['last'] or '') + ' ' + (r['first'] or '')).strip())
                     for r in con.execute("SELECT id,tier,category,last,first FROM donors")}
            PARNES_AMT = {480.0}
            q = ("SELECT tid,donor_id,amount,date,recurring,category FROM recon "
                 "WHERE source NOT LIKE 'Banquest%' AND COALESCE(processed,0)=0 "
                 "AND COALESCE(status,'settled')='settled' AND donor_id IS NOT NULL")
            ins = repl = skip_py = 0
            by, perdonor = {}, {}
            for r in list(con.execute(q)):
                did = r['donor_id']
                a = round(float(r['amount'] or 0), 2)
                diso = _recon_iso(r['date'])
                if not diso:
                    continue
                if a in PARNES_AMT or (r['category'] or '') in ('פרנס לילה', 'חדר קפה', 'ארוחת בוקר'):
                    skip_py += 1
                    continue                      # פרנס — צריך לבחור יום, נשאר לאישור ידני
                tier, dcat, _nm = dinfo.get(did, ('', '', ''))
                cat = why = ''
                for amt, lbl in camp.get(did, []):
                    if abs(amt - a) < 0.01:
                        cat, why = lbl, lbl
                        break
                if not cat:
                    for amt, c in subs.get(did, []):
                        if abs(amt - a) < 0.01:
                            cat, why = c, 'דוח הקבועים'
                            break
                if not cat and r['recurring'] and 'יששכר' in tier:
                    cat, why = 'יששכר־זבולון', 'דרגת יששכר־זבולון'
                if not cat and r['recurring']:
                    cat, why = (dcat or 'קבוע'), 'הוראת קבע'
                if not cat:
                    cat, why = (dcat or 'מזדמן'), 'לא סווג'
                    perdonor[did] = perdonor.get(did, 0) + 1
                if con.execute("SELECT 1 FROM donations WHERE donor_id=? AND date=? AND method='Authorize' "
                               "AND ROUND(CAST(amount AS REAL),2)=?", (did, diso, a)).fetchone():
                    con.execute("UPDATE recon SET processed=1, category=? WHERE tid=?", (cat, r['tid']))
                    continue
                n = con.execute("DELETE FROM donations WHERE donor_id=? AND substr(COALESCE(date,''),1,7)=? "
                                "AND COALESCE(note,'') LIKE 'ייבוא 2026%' AND method='Authorize' "
                                "AND ROUND(CAST(amount AS REAL),2)=?", (did, diso[:7], a)).rowcount
                repl += max(0, n)
                note = 'ייבוא אוטורייז · ' + (why if why != 'לא סווג' else 'לא סווג — לבדוק עבור מה')
                con.execute("INSERT INTO donations(donor_id,date,amount,category,method,note,paid) "
                            "VALUES(?,?,?,?,'Authorize',?,1)", (did, diso, r['amount'], cat, note))
                con.execute("UPDATE recon SET processed=1, category=? WHERE tid=?", (cat, r['tid']))
                ins += 1
                by[why] = by.get(why, 0) + 1
            # ללא משימות — השאלות מוצגות בדף החיובים ובכרטיס התורם
            con.execute("INSERT INTO seed_flags(name) VALUES('authorize_merge_v1')")
            print('  מיזוג אוטורייז: נכנסו %d, הוחלפו %d שורות סיכום, פרנס שנשאר לאישור %d' % (ins, repl, skip_py))
            for k, v in sorted(by.items(), key=lambda x: -x[1]):
                print('      %-24s %d' % (k, v))
    except Exception as e:
        print('  authorize merge error:', e)

    # פרנס־יום שאושר מדף החיובים ולא נוצרה לו תזכורת (התזכורת הותנתה בתאריך החיוב במקום בתאריך הלילה)
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='parnes_task_v1'").fetchone():
            nadd = 0
            q = ("SELECT p.id,p.donor_id,p.date_text,p.hyear,p.night_date,d.last,d.first "
                 "FROM parnes p JOIN donors d ON d.id=p.donor_id "
                 "WHERE COALESCE(p.status,'confirmed')<>'suggested'")
            for r in list(con.execute(q)):
                nm = ((r['last'] or '') + ' ' + (r['first'] or '')).strip()
                note = '🌙 לעשות פרנס לילה — ' + nm
                if con.execute("SELECT 1 FROM tasks WHERE donor_id=? AND kind='parnes' AND note=?",
                               (r['donor_id'], note)).fetchone():
                    continue
                nd = r['night_date'] or ''
                if not nd:
                    g = heb_greg_year(r['date_text'] or '', r['hyear'] or '') or heb_to_greg(r['date_text'] or '')
                    nd = g.isoformat() if g else ''
                    if nd:
                        con.execute("UPDATE parnes SET night_date=? WHERE id=?", (nd, r['id']))
                if not nd or nd < today_iso():
                    continue                      # לילה שכבר עבר — בלי תזכורת חדשה
                due = (datetime.date.fromisoformat(nd) - datetime.timedelta(days=7)).isoformat()
                if due < today_iso():
                    due = today_iso()
                con.execute("INSERT INTO tasks(donor_id,due_date,kind,note) VALUES(?,?,?,?)",
                            (r['donor_id'], due, 'parnes', note))
                nadd += 1
            con.execute("INSERT INTO seed_flags(name) VALUES('parnes_task_v1')")
            print('  תזכורות פרנס שהושלמו: %d' % nadd)
    except Exception as e:
        print('  parnes task error:', e)

    # תיקון פרנס v2 — שני דברים:
    # א) לילות שנשמרו עם תאריך לועזי מהשנה הלא נכונה (חושב לפי "המופע הבא" ולא לפי השנה שנבחרה)
    # ב) לילה שכבר עבר ולא סומן כבוצע — צריך תזכורת דווקא עכשיו, לא לדלג עליו
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='parnes_task_v2'").fetchone():
            nfix = nadd = 0
            q = ("SELECT p.id,p.donor_id,p.date_text,p.hyear,p.night_date,p.paid,p.kind,d.last,d.first "
                 "FROM parnes p JOIN donors d ON d.id=p.donor_id "
                 "WHERE COALESCE(p.status,'confirmed')<>'suggested'")
            today = today_iso()
            floor = (datetime.date.fromisoformat(today) - datetime.timedelta(days=60)).isoformat()
            for r in list(con.execute(q)):
                nd = r['night_date'] or ''
                if r['hyear']:
                    g = heb_greg_year(r['date_text'] or '', r['hyear'])
                    if g and g.isoformat() != nd:      # התאריך לא תואם לשנה שנבחרה — מתקנים
                        nd = g.isoformat()
                        con.execute("UPDATE parnes SET night_date=? WHERE id=?", (nd, r['id']))
                        nfix += 1
                if not nd:
                    continue
                nm = ((r['last'] or '') + ' ' + (r['first'] or '')).strip()
                note = '🌙 לעשות פרנס לילה — ' + nm
                ex = con.execute("SELECT id,due_date FROM tasks WHERE donor_id=? AND kind='parnes' "
                                 "AND note LIKE ? AND COALESCE(done,0)=0",
                                 (r['donor_id'], note + '%')).fetchone()
                if nd >= today:
                    due = (datetime.date.fromisoformat(nd) - datetime.timedelta(days=7)).isoformat()
                    if due < today:
                        due = today
                elif nd >= floor:
                    due = today                        # הלילה כבר עבר ולא סומן — מזכירים היום
                else:
                    continue                           # לילה ישן — לא מציפים את הרשימה
                full = note + ('' if nd >= today else ' (הלילה היה ב-' + nd + ')')
                if ex:
                    if ex['due_date'] != due:     # התזכורת נקבעה לפי תאריך שגוי — מיישרים
                        con.execute("UPDATE tasks SET due_date=?, note=? WHERE id=?", (due, full, ex['id']))
                        nfix += 1
                    continue
                con.execute("INSERT INTO tasks(donor_id,due_date,kind,note) VALUES(?,?,?,?)",
                            (r['donor_id'], due, 'parnes', full))
                nadd += 1
            con.execute("INSERT INTO seed_flags(name) VALUES('parnes_task_v2')")
            print('  פרנס v2: תוקנו %d תאריכי לילה, נוספו %d תזכורות' % (nfix, nadd))
    except Exception as e:
        print('  parnes v2 error:', e)

    # מרמרשטיין: השם העברי בכרטיס הוא "משה" בעוד שבאנגלית רשום Zev — מיישרים לזאב,
    # וקובעים את הכללים שהמשרד מסר: $2,700 = יששכר־זבולון (שלושה אברכים), $1,100 = קמחא דפסחא תשפ"ו
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='marmurstein_v1'").fetchone():
            r = con.execute("SELECT id,first FROM donors WHERE last LIKE '%מרמרשטיין%' "
                            "AND LOWER(COALESCE(english,'')) LIKE '%zev%'").fetchone()
            if r:
                if (r['first'] or '').strip() != 'זאב':
                    con.execute("UPDATE donors SET first='זאב' WHERE id=?", (r['id'],))
                for amt, cat, note in ((2700.0, 'יששכר־זבולון', 'שלושה אברכים ביחד'),
                                       (1100.0, 'קמחא דפסחא תשפ"ו', '')):
                    con.execute("INSERT OR REPLACE INTO donor_rules(donor_id,amount,category,note,created) "
                                "VALUES(?,?,?,?,?)", (r['id'], amt, cat, note, today_iso()))
                    con.execute("UPDATE donations SET category=? WHERE donor_id=? "
                                "AND ROUND(CAST(amount AS REAL),2)=?", (cat, r['id'], amt))
                    if note:
                        con.execute("UPDATE donations SET note=TRIM(COALESCE(note,'')||' · '||?,' ·') "
                                    "WHERE donor_id=? AND ROUND(CAST(amount AS REAL),2)=? "
                                    "AND COALESCE(note,'') NOT LIKE ?", (note, r['id'], amt, '%' + note + '%'))
                print('  מרמרשטיין זאב: השם והכללים עודכנו (#%d)' % r['id'])
            con.execute("INSERT INTO seed_flags(name) VALUES('marmurstein_v1')")
    except Exception as e:
        print('  marmurstein error:', e)

    # צ׳קים 2026 + דונרס פאנד + OJC — הכל מאותה רשימה, בלי כפילויות.
    # מי שזוהה נכנס ישר לכרטיס; מי שלא — נשאר לבדיקה בדף החיובים.
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='checks_ojc_2026_v1'").fetchone():
            with open(os.path.join(HERE, 'checks_2026.json'), encoding='utf-8') as f:
                book = json.load(f)
            byhe, byen = {}, {}
            for r in con.execute("SELECT id,last,first,english,business,aliases FROM donors"):
                byhe.setdefault(((r['last'] or '') + ' ' + (r['first'] or '')).strip(), []).append(r['id'])
                for fld in (r['english'], r['business'], r['aliases']):
                    t = (fld or '').strip().lower()
                    if t:
                        byen.setdefault(t, []).append(r['id'])

            def whois(hint):
                """כרטיס התורם לפי השם העברי המדויק, ואם אין — לפי השם הלועזי. רק התאמה יחידה."""
                he = (hint.get('he') or '').strip()
                if len(byhe.get(he, [])) == 1:
                    return byhe[he][0]
                en = (hint.get('en') or '').strip().lower()
                if len(byen.get(en, [])) == 1:
                    return byen[en][0]
                if en:
                    hit = [i for k, v in byen.items() if en in k or k in en for i in v]
                    if len(set(hit)) == 1:
                        return hit[0]
                return None

            rules = {}
            try:
                for r in con.execute("SELECT donor_id,amount,category FROM donor_rules"):
                    rules[(r['donor_id'], round(float(r['amount'] or 0), 2))] = r['category']
            except Exception:
                pass
            dcat = {r['id']: (r['category'] or '') for r in con.execute("SELECT id,category FROM donors")}
            SRCNAME = {"צ'ק": "צ׳קים 2026", 'דונרס': 'Donors Fund 2026', 'OJC': 'OJC 2026'}
            SUMMETH = {"צ'ק": 'Checks', 'דונרס': 'Donors Fund', 'OJC': 'OJC'}   # שם השיטה בשורות הסיכום
            people = book.get('people', {})
            found = {w: (whois(h) if h else None) for w, h in people.items()}
            ins = dup = wait = repl = 0
            for i, r in enumerate(book.get('rows', [])):
                did = found.get(r['who'])
                a = round(float(r['amount'] or 0), 2)
                meth = r['method']
                if did:
                    if con.execute("SELECT 1 FROM donations WHERE donor_id=? AND date=? AND method=? "
                                   "AND ROUND(CAST(amount AS REAL),2)=?", (did, r['date'], meth, a)).fetchone():
                        dup += 1
                        continue
                    # שורת הסיכום החודשית מדוח הקבועים מוחלפת בתשלום האמיתי — אותו כסף, תאריך מדויק
                    old = con.execute(
                        "SELECT id,category FROM donations WHERE donor_id=? AND date=? AND method=? "
                        "AND COALESCE(note,'') LIKE 'ייבוא 2026%' AND ROUND(CAST(amount AS REAL),2)=?",
                        (did, r['date'][:7], SUMMETH[meth], a)).fetchone()
                    cat = rules.get((did, a)) or (old['category'] if old else '') or ''
                    note = 'ייבוא ' + SRCNAME[meth] + (('  · אסמכתא ' + r['ref']) if r.get('ref') else '')
                    if old:
                        con.execute("DELETE FROM donations WHERE id=?", (old['id'],))
                        repl += 1
                    if not cat:
                        cat = dcat.get(did) or 'מזדמן'
                        note += ' · לא סווג — לבדוק עבור מה'
                    con.execute("INSERT INTO donations(donor_id,date,amount,category,method,note,paid) "
                                "VALUES(?,?,?,?,?,?,1)", (did, r['date'], a, cat, meth, note))
                    ins += 1
                else:                       # אין כרטיס ודאי — נשאר לאישור ידני בדף החיובים
                    nm = re.sub(r'\s*\([^)]*\)', '', r['who'].replace(',,', ',')).strip()
                    if ',' in nm:
                        last, _, first = nm.partition(',')          # "Rosenfeld, David"
                    else:
                        first, _, last = nm.rpartition(' ')          # "Malcolm Y. Azaroh"
                    tid = 'chk26-%03d' % i
                    con.execute("INSERT OR IGNORE INTO recon(tid,first,last,amount,date,recurring,"
                                "donor_id,processed,source,status) VALUES(?,?,?,?,?,0,NULL,0,?,'settled')",
                                (tid, first.strip(), last.strip(), '%.2f' % a, r['date'], SRCNAME[meth]))
                    wait += 1
            # הדוח הוא הרישום האמיתי לינואר–אוגוסט 2026. לכן אצל מי שמופיע בו, ההערכות
            # החודשיות מדוח הקבועים באותם ערוצים ובאותם חודשים כבר מיותרות — אחרת הכסף נספר פעמיים.
            hit = sorted({d0 for d0 in found.values() if d0})
            gone = 0
            for did in hit:
                gone += con.execute(
                    "DELETE FROM donations WHERE donor_id=? AND length(COALESCE(date,''))=7 "
                    "AND date BETWEEN '2026-01' AND '2026-08' AND COALESCE(note,'') LIKE 'ייבוא 2026%' "
                    "AND method IN ('Checks','Donors Fund','OJC')", (did,)).rowcount
                # תשלום שנתי ששולם בבת אחת — 12 שורות ההערכה שוות בדיוק לתשלום אחד בדוח
                yr = con.execute("SELECT COUNT(*) k, ROUND(SUM(CAST(amount AS REAL)),2) s FROM donations "
                                 "WHERE donor_id=? AND length(COALESCE(date,''))=7 AND date LIKE '2026%' "
                                 "AND method='Annualy' AND COALESCE(note,'') LIKE 'ייבוא 2026%'",
                                 (did,)).fetchone()
                if yr and yr['k'] and con.execute(
                        "SELECT 1 FROM donations WHERE donor_id=? AND date LIKE '2026-%' AND length(date)=10 "
                        "AND method IN (?,?,?) AND ROUND(CAST(amount AS REAL),2)=?",
                        (did, "צ'ק", 'דונרס', 'OJC', yr['s'])).fetchone():
                    gone += con.execute(
                        "DELETE FROM donations WHERE donor_id=? AND length(COALESCE(date,''))=7 "
                        "AND date LIKE '2026%' AND method='Annualy' AND COALESCE(note,'') LIKE 'ייבוא 2026%'",
                        (did,)).rowcount
            con.execute("INSERT INTO seed_flags(name) VALUES('checks_ojc_2026_v1')")
            print('  צ׳קים/דונרס/OJC 2026: נכנסו %d, החליפו %d שורות סיכום, נמחקו עוד %d הערכות, '
                  'כבר היו %d, לבדיקה %d' % (ins, repl, gone, dup, wait))
            for w, d0 in sorted(found.items()):
                if not d0:
                    print('      לא זוהה כרטיס: %s' % w)
    except Exception as e:
        print('  checks/ojc 2026 error:', e)

    # קלמן לאקס — תורם חדש (לא חיים לאקס). נפתח לו כרטיס, ושלוש תרומות הדונרס שלו נכנסות אליו.
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='kalman_lax_v1'").fetchone():
            row = con.execute("SELECT id FROM donors WHERE last='לאקס' AND first='קלמן'").fetchone()
            did = row['id'] if row else con.execute(
                "INSERT INTO donors(last,first,english,category,created,source) "
                "VALUES('לאקס','קלמן','Kalman Lax','מזדמן',?,'דונרס פאנד 2026')",
                (today_iso(),)).lastrowid
            n = 0
            for r in list(con.execute("SELECT tid,amount,date FROM recon WHERE tid LIKE 'chk26-%' "
                                      "AND last='Lax' AND first='Kalman'")):
                a = round(float(r['amount'] or 0), 2)
                if not con.execute("SELECT 1 FROM donations WHERE donor_id=? AND date=? AND method='דונרס' "
                                   "AND ROUND(CAST(amount AS REAL),2)=?", (did, r['date'], a)).fetchone():
                    con.execute("INSERT INTO donations(donor_id,date,amount,category,method,note,paid) "
                                "VALUES(?,?,?,'מזדמן','דונרס','ייבוא Donors Fund 2026 · לא סווג — לבדוק עבור מה',1)",
                                (did, r['date'], a))
                    n += 1
                con.execute("UPDATE recon SET donor_id=?, processed=1 WHERE tid=?", (did, r['tid']))
            con.execute("INSERT INTO seed_flags(name) VALUES('kalman_lax_v1')")
            print('  קלמן לאקס: כרטיס #%d, נכנסו %d תרומות' % (did, n))
    except Exception as e:
        print('  kalman lax error:', e)

    # יעקב מקס — "מקס יעקב" ו"מקס יעקב שלום" הם אותו אדם. הכרטיס הכפול מתמזג לכרטיס הוותיק,
    # וה-$500 מהצ׳קים מחליף את שורת ההערכה החודשית שכבר הייתה שם. לא נפתח כרטיס חדש.
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='yaakov_max_v1'").fetchone():
            keep = con.execute("SELECT id FROM donors WHERE last='מקס' AND first='יעקב שלום'").fetchone()
            dupe = con.execute("SELECT id FROM donors WHERE last='מקס' AND first='יעקב'").fetchone()
            if keep:
                kid = keep['id']
                if dupe and dupe['id'] != kid:
                    for t in ('pledges', 'parnes', 'prayers', 'donations', 'contacts_log', 'tasks',
                              'partners', 'transactions', 'building', 'recon', 'intake'):
                        try:
                            con.execute("UPDATE %s SET donor_id=? WHERE donor_id=?" % t, (kid, dupe['id']))
                        except Exception:
                            pass
                    con.execute("DELETE FROM donors WHERE id=?", (dupe['id'],))
                for r in list(con.execute("SELECT tid,amount,date FROM recon WHERE tid LIKE 'chk26-%' "
                                          "AND last='Max' AND first='Yaakov'")):
                    a = round(float(r['amount'] or 0), 2)
                    con.execute("DELETE FROM donations WHERE donor_id=? AND date=? "
                                "AND ROUND(CAST(amount AS REAL),2)=? AND COALESCE(method,'')=''",
                                (kid, r['date'][:7], a))          # שורת ההערכה החודשית — אותו כסף
                    if not con.execute("SELECT 1 FROM donations WHERE donor_id=? AND date=? AND method=? "
                                       "AND ROUND(CAST(amount AS REAL),2)=?",
                                       (kid, r['date'], "צ'ק", a)).fetchone():
                        con.execute("INSERT INTO donations(donor_id,date,amount,category,method,note,paid) "
                                    "VALUES(?,?,?,'מזדמן',?,'ייבוא צ׳קים 2026  · אסמכתא 16384943 · "
                                    "לא סווג — לבדוק עבור מה',1)", (kid, r['date'], a, "צ'ק"))
                    con.execute("UPDATE recon SET donor_id=?, processed=1 WHERE tid=?", (kid, r['tid']))
                con.execute("INSERT INTO seed_flags(name) VALUES('yaakov_max_v1')")
                print('  יעקב מקס: אוחד לכרטיס #%d' % kid)
    except Exception as e:
        print('  yaakov max error:', e)

    # רבקה וורצברגר היא בתו של יידל — התרומה נרשמת בכרטיס שלו, ושמה מצוין לידה.
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='werzberger_rivka_v1'").fetchone():
            dad = con.execute("SELECT id FROM donors WHERE last='וורצברגר' AND first='יידל'").fetchone() \
                or con.execute("SELECT id FROM donors WHERE lower(COALESCE(english,''))='yiddl werzberger'").fetchone()
            if dad:
                did = dad['id']
                for r in list(con.execute("SELECT tid,amount,date FROM recon WHERE tid LIKE 'chk26-%' "
                                          "AND last='Werzberger' AND first='Rebbeca'")):
                    a = round(float(r['amount'] or 0), 2)
                    if not con.execute("SELECT 1 FROM donations WHERE donor_id=? AND date=? AND method='דונרס' "
                                       "AND ROUND(CAST(amount AS REAL),2)=?", (did, r['date'], a)).fetchone():
                        con.execute("INSERT INTO donations(donor_id,date,amount,category,method,note,paid) "
                                    "VALUES(?,?,?,'מזדמן','דונרס',?,1)",
                                    (did, r['date'], a, 'רבקה וורצברגר (הבת) · אסמכתא Donors34202 '
                                                        '· לא סווג — לבדוק עבור מה'))
                    con.execute("UPDATE recon SET donor_id=?, processed=1 WHERE tid=?", (did, r['tid']))
                con.execute("INSERT INTO seed_flags(name) VALUES('werzberger_rivka_v1')")
                print('  רבקה וורצברגר: נרשמה בכרטיס של יידל #%d' % did)
    except Exception as e:
        print('  werzberger error:', e)

    # שלושה תורמים חדשים מרשימת קמחא דפסחא תשפ"ו, ומחיקת השורה שאיש לא מזהה
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='newdonors_kd_v1'").fetchone():
            KD = 'קמחא דפסחא תשפ"ו'
            NEW = {   # שם בדוח → (שם משפחה, שם פרטי, לועזי, הערה)
                'Dworkin': ('דבורקין', 'מאיר', 'Meir Dworkin', 'הגיע דרך יצחק שטטפלד'),
                'Goldberger': ('גולדברגר', '', 'A. Goldberger', 'הגיע דרך אבא קלוק'),
                'Rosenfeld': ('רוזנפלד', 'דוד', 'David Rosenfeld', 'חתן של חיים ולאה אסתר לאקס'),
            }
            con.execute("INSERT OR IGNORE INTO campaigns(name,created) VALUES(?,?)", (KD, today_iso()))
            made = 0
            for r in list(con.execute("SELECT tid,first,last,amount,date,source FROM recon "
                                      "WHERE tid LIKE 'chk26-%' AND COALESCE(processed,0)=0")):
                key = (r['last'] or '').strip()
                if key == 'Azaroh':          # לא מזוהה, ולפי בקשת מאיר לא נכנס לשום רשימה
                    con.execute("DELETE FROM recon WHERE tid=?", (r['tid'],))
                    continue
                if key not in NEW:
                    continue
                he_last, he_first, en, note = NEW[key]
                row = con.execute("SELECT id FROM donors WHERE last=? AND COALESCE(first,'')=?",
                                  (he_last, he_first)).fetchone()
                did = row['id'] if row else con.execute(
                    "INSERT INTO donors(last,first,english,category,notes,created,source) "
                    "VALUES(?,?,?,'מזדמן',?,?,?)",
                    (he_last, he_first, en, note, today_iso(), 'קמחא דפסחא תשפ"ו')).lastrowid
                if not row:
                    made += 1
                meth = 'OJC' if 'OJC' in (r['source'] or '') else 'דונרס'
                a = round(float(r['amount'] or 0), 2)
                if not con.execute("SELECT 1 FROM donations WHERE donor_id=? AND date=? AND method=? "
                                   "AND ROUND(CAST(amount AS REAL),2)=?", (did, r['date'], meth, a)).fetchone():
                    con.execute("INSERT INTO donations(donor_id,date,amount,category,method,note,paid) "
                                "VALUES(?,?,?,?,?,?,1)", (did, r['date'], a, KD, meth, note))
                con.execute("UPDATE recon SET donor_id=?, processed=1, category=? WHERE tid=?",
                            (did, KD, r['tid']))
            con.execute("INSERT INTO seed_flags(name) VALUES('newdonors_kd_v1')")
            print('  תורמי קמחא דפסחא חדשים: נפתחו %d כרטיסים' % made)
    except Exception as e:
        print('  new kd donors error:', e)

    # שורת סיכום חודשית ישנה (בלי אמצעי תשלום ובלי הערה) שנשארה לצד התשלום האמיתי מהדוח —
    # אותו תורם, אותו חודש, אותו סכום. אלה כפילויות ודאיות.
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='checks_dupsum_v1'").fetchone():
            n = con.execute("""DELETE FROM donations WHERE id IN (
                SELECT s.id FROM donations s JOIN donations r ON r.donor_id=s.donor_id
                   AND length(r.date)=10 AND substr(r.date,1,7)=s.date
                   AND ROUND(CAST(r.amount AS REAL),2)=ROUND(CAST(s.amount AS REAL),2)
                   AND r.method IN ('צ''ק','דונרס','OJC')
                WHERE length(s.date)=7 AND s.date LIKE '2026%'
                  AND COALESCE(s.method,'')='' AND COALESCE(s.note,'')='')""").rowcount
            con.execute("INSERT INTO seed_flags(name) VALUES('checks_dupsum_v1')")
            print('  שורות סיכום כפולות שנמחקו: %d' % n)
    except Exception as e:
        print('  dupsum error:', e)

    # RZH (עלבויגן) — התרומה לא שייכת לנו, רק עשינו טובה. הכרטיס יורד לגמרי.
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='elbogen_rzh_drop_v1'").fetchone():
            row = con.execute("SELECT id FROM donors WHERE last='עלבויגן' AND first='RZH FOUNDATION'").fetchone()
            if row:
                did = row['id']
                for kind, tbl in (('parnes', 'parnes'), ('contact', 'contacts_log'), ('task', 'tasks'),
                                  ('donation', 'donations'), ('transaction', 'transactions')):
                    try:
                        con.execute("DELETE FROM files WHERE kind=? AND ref_id IN "
                                    "(SELECT id FROM %s WHERE donor_id=?)" % tbl, (kind, did))
                    except Exception:
                        pass
                try: con.execute("DELETE FROM files WHERE kind='iz' AND ref_id=?", (did,))
                except Exception: pass
                for t in ('pledges', 'parnes', 'prayers', 'donations', 'contacts_log', 'tasks',
                          'partners', 'transactions', 'building', 'donor_rules'):
                    try: con.execute("DELETE FROM %s WHERE donor_id=?" % t, (did,))
                    except Exception: pass
                for t in ('recon', 'intake'):
                    try: con.execute("UPDATE %s SET donor_id=NULL WHERE donor_id=?" % t, (did,))
                    except Exception: pass
                con.execute("DELETE FROM donors WHERE id=?", (did,))
                print('  עלבויגן RZH: הכרטיס נמחק (#%d)' % did)
            con.execute("INSERT INTO seed_flags(name) VALUES('elbogen_rzh_drop_v1')")
    except Exception as e:
        print('  elbogen drop error:', e)

    # ניקול אייזנברגר — הכרטיס הנפרד מתמזג לכרטיס שמחזיק את אותו מייל (יערט)
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='eisenberger_merge_v1'").fetchone():
            MAIL = 'eisenberger.nicole@gmail.com'
            cand = [dict(r) for r in con.execute(
                "SELECT id,last,first,email FROM donors WHERE lower(COALESCE(email,'')) LIKE ?",
                ('%' + MAIL + '%',))]
            if len(cand) > 1:
                cnt = {}
                for r in con.execute("SELECT donor_id, COUNT(*) n FROM donations GROUP BY donor_id"):
                    cnt[r['donor_id']] = r['n']
                # נשאר הכרטיס של יערט/ירט; אם אין — זה עם הכי הרבה תרומות
                cand.sort(key=lambda x: (0 if re.search(r'ירט|ערט', x['last'] or '') else 1, -cnt.get(x['id'], 0)))
                keep = cand[0]['id']
                for x in cand[1:]:
                    mv = merge_into(con, keep, x['id'])
                    print('  אייזנברגר: #%d מוזג לתוך #%d (%s)' % (x['id'], keep, mv))
            con.execute("INSERT INTO seed_flags(name) VALUES('eisenberger_merge_v1')")
    except Exception as e:
        print('  eisenberger merge error:', e)

    # ניקוי כפילויות בקוויטל — שמות שנוספו פעמיים כשצורפו שמות מהאתר יותר מפעם אחת
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='kvittel_dedup_v1'").fetchone():
            _rm, _mg, _d = dedupe_prayers(con)
            con.execute("INSERT INTO seed_flags(name) VALUES('kvittel_dedup_v1')")
            print('  ניקוי כפילויות קוויטל: %d בלוקים כפולים נמחקו, %d אוחדו, אצל %d תורמים' % (_rm, _mg, _d))
    except Exception as e:
        print('  kvittel dedup error:', e)

    # משימות "עבור מה" יורדות מרשימת המשימות — השאלות מוצגות בדף החיובים ובכרטיס התורם עצמו
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='drop_uncl_tasks_v1'").fetchone():
            n = con.execute("DELETE FROM tasks WHERE note LIKE '❓ עבור מה נגבו%' "
                            "OR note LIKE 'לבדוק עבור מה נגבו%'").rowcount
            con.execute("INSERT INTO seed_flags(name) VALUES('drop_uncl_tasks_v1')")
            print('  משימות "עבור מה" שהוסרו מרשימת המשימות: %d' % n)
    except Exception as e:
        print('  drop uncl tasks error:', e)

    # משימות "לבדוק עבור מה" — לכתוב בהן את הסכומים והתאריכים המדויקים, אחרת אי אפשר לענות עליהן
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='unclassified_task_v2'").fetchone():
            nre = 0
            rows = list(con.execute("SELECT id,donor_id,note FROM tasks WHERE note LIKE 'לבדוק עבור מה נגבו%' "
                                    "AND COALESCE(done,0)=0"))
            for t in rows:
                meth = 'Banquest' if 'בנק ווסט' in (t['note'] or '') else 'Authorize'
                lbl = 'בנק ווסט' if meth == 'Banquest' else 'אוטרייז'
                dons = list(con.execute(
                    "SELECT date,amount FROM donations WHERE donor_id=? AND method=? "
                    "AND COALESCE(note,'') LIKE '%לא סווג%' ORDER BY date", (t['donor_id'], meth)))
                if not dons:
                    continue
                def _he(d):
                    m = re.match(r'(\d{4})-(\d{2})-(\d{2})', d or '')
                    return '%s/%s/%s' % (m.group(3), m.group(2), m.group(1)) if m else (d or '')
                items = ' · '.join('$%s ב-%s' % (
                    ('%g' % float(x['amount'] or 0)), _he(x['date'])) for x in dons[:6])
                more = '' if len(dons) <= 6 else ' ועוד %d' % (len(dons) - 6)
                tot = sum(float(x['amount'] or 0) for x in dons)
                note = ('❓ עבור מה נגבו %d חיובי %s · סה"כ $%s — %s%s'
                        % (len(dons), lbl, ('%g' % tot), items, more))
                con.execute("UPDATE tasks SET note=?, kind='verify' WHERE id=?", (note, t['id']))
                nre += 1
            con.execute("INSERT INTO seed_flags(name) VALUES('unclassified_task_v2')")
            print('  משימות "עבור מה" עם סכומים ותאריכים: %d' % nre)
    except Exception as e:
        print('  unclassified task error:', e)

    # איות שמות מקובל — גם בקוויטל שכבר נשמר (אדינא -> עדינה וכו')
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='he_spell_v1'").fetchone():
            import gmail_intake as _gis
            nsp = 0
            for tb, cl in (('prayers', 'text'), ('prayers', 'name'), ('intake', 'names'), ('donors', 'first'), ('donors', 'last')):
                try:
                    for r in con.execute(f"SELECT rowid AS rid, {cl} AS v FROM {tb} WHERE COALESCE({cl},'')<>''"):
                        nv = _gis._he_spell(r['v'])
                        if nv != r['v']:
                            con.execute(f"UPDATE {tb} SET {cl}=? WHERE rowid=?", (nv, r['rid'])); nsp += 1
                except Exception: pass
            con.execute("INSERT INTO seed_flags(name) VALUES('he_spell_v1')")
            print(f'  יישור איות שמות בעברית: {nsp}')
    except Exception as e:
        print('  he spell error:', e)

    # בקשות קוויטל שנשמרו עם אנגלית בתוכן — פענוח מחדש, כדי שלא תישאר מילה אחת באנגלית
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='intake_he_v1'").fetchone():
            import gmail_intake as _gih
            nfix = 0
            rows = list(con.execute("""SELECT id,body,names FROM intake
                                       WHERE names GLOB '*[A-Za-z]*' AND COALESCE(body,'')<>''"""))
            for r in rows:
                try:
                    ne = _gih._parse_names(r['body'] or '')
                except Exception:
                    continue
                if ne.strip() and ne.strip() != (r['names'] or '').strip():
                    con.execute("UPDATE intake SET names=? WHERE id=?", (ne.strip(), r['id']))
                    nfix += 1
            con.execute("INSERT INTO seed_flags(name) VALUES('intake_he_v1')")
            print(f'  בקשות קוויטל שתורגמו לעברית: {nfix} מתוך {len(rows)}')
    except Exception as e:
        print('  intake he error:', e)

    # שנים עבריות שנשמרו עם גרשיים עבריים (תשפ״ו) — מיישרים ל-" כמו בכל הרשימות במסך,
    # אחרת הבורר לא מזהה את השנה שנשמרה וקופץ לשנה הראשונה ברשימה (תשפ"ה)
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='heb_quote_v1'").fetchone():
            nq = 0
            for tb, cl in (('donors', 'kv_year'), ('parnes', 'hyear')):
                try:
                    nq += con.execute(f"SELECT COUNT(*) FROM {tb} WHERE {cl} LIKE '%״%'").fetchone()[0]
                    con.execute(f"UPDATE {tb} SET {cl}=REPLACE({cl},'״','\"') WHERE {cl} LIKE '%״%'")
                except Exception: pass
            con.execute("INSERT INTO seed_flags(name) VALUES('heb_quote_v1')")
            print(f'  יישור גרשיים בשנים עבריות: {nq}')
    except Exception as e:
        print('  heb quote error:', e)

    # אינדקסים — בלעדיהם כל שאילתה לפי תורם סורקת את כל הטבלה, וזה מה שמאט את דף החיובים
    for _ix, _tb, _cl in (('idx_don_donor', 'donations', 'donor_id'), ('idx_prayers_donor', 'prayers', 'donor_id'),
                          ('idx_tasks_donor', 'tasks', 'donor_id'), ('idx_clog_donor', 'contacts_log', 'donor_id'),
                          ('idx_parnes_donor', 'parnes', 'donor_id'), ('idx_partners_donor', 'partners', 'donor_id'),
                          ('idx_trans_donor', 'transactions', 'donor_id'), ('idx_pledges_donor', 'pledges', 'donor_id'),
                          ('idx_building_donor', 'building', 'donor_id'), ('idx_recon_donor', 'recon', 'donor_id'),
                          ('idx_recon_email', 'recon', 'email'), ('idx_intake_donor', 'intake', 'donor_id'),
                          ('idx_intake_from', 'intake', 'from_email'), ('idx_files_ref', 'files', 'ref_id')):
        try: con.execute(f"CREATE INDEX IF NOT EXISTS {_ix} ON {_tb}({_cl})")
        except Exception: pass

    # שחזור שיוכים שנותקו במיזוג כרטיסים ישן — שורות חיוב ובקשות מהאתר שהצביעו לכרטיס שנמחק.
    # מחזירים אותן לכרטיס הנכון לפי אימייל; אם אין התאמה ודאית — משחררים לרשימת הלא-משויכים.
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='merge_orphans_v1'").fetchone():
            emap = {}
            for d in con.execute("SELECT id,email FROM donors"):
                for e in emails_of(d['email']):
                    if e in emap and emap[e] != d['id']:
                        emap[e] = None
                    elif e not in emap:
                        emap[e] = d['id']
            relinked = freed = 0
            for tbl, col in (('recon', 'email'), ('intake', 'from_email')):
                try:
                    rows = list(con.execute(
                        f"SELECT rowid AS rid, {col} AS em FROM {tbl} "
                        "WHERE donor_id IS NOT NULL AND donor_id NOT IN (SELECT id FROM donors)"))
                except Exception:
                    continue
                for r in rows:
                    nid = next((emap[e] for e in emails_of(r['em']) if emap.get(e)), None)
                    con.execute(f"UPDATE {tbl} SET donor_id=? WHERE rowid=?", (nid, r['rid']))
                    if nid: relinked += 1
                    else: freed += 1
            con.execute("INSERT INTO seed_flags(name) VALUES('merge_orphans_v1')")
            print(f'  שחזור שיוכים אחרי מיזוג: הוחזרו {relinked}, שוחררו {freed}')
    except Exception as e:
        print('  merge orphans error:', e)

    # שורה מאקסל הקבועים יורדת רק כשיש לצידה חיוב אמיתי עם תאריך מדויק, באותו
    # חודש ובאותו סכום. תורם שמשלם ב-ACH או בהעברה בנקאית אינו מופיע בדוחות
    # האשראי והצ׳קים, ומחיקה גורפת מוחקת אצלו את כל היסטוריית התשלומים.
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='drop_recurring_est_v2'").fetchone():
            n = con.execute(
                "DELETE FROM donations WHERE length(COALESCE(date,''))=7 "
                "AND COALESCE(note,'') LIKE 'ייבוא 2026%' AND EXISTS("
                "  SELECT 1 FROM donations r WHERE r.donor_id=donations.donor_id "
                "  AND length(COALESCE(r.date,''))=10 AND substr(r.date,1,7)=donations.date "
                "  AND ROUND(CAST(r.amount AS REAL),2)=ROUND(CAST(donations.amount AS REAL),2))").rowcount
            con.execute("INSERT INTO seed_flags(name) VALUES('drop_recurring_est_v2')")
            print('  שורות אקסל הקבועים שנמחקו (כפולות בלבד): %d' % n)
    except Exception as e:
        print('  drop recurring est error:', e)

    # מאיר: "תיצמד רק לנתונים אמיתיים שקיבלת". שורות דוח הקבועים הן הערכה
    # חודשית בלי יום חיוב, והן ניפחו סכומים — אצל עזרא מקס הוסיפו כ-$8,000
    # מעל התשלומים שנכנסו בפועל מ-OJC. כל שורה בלי יום בחודש יורדת.
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='drop_recurring_est_v3'").fetchone():
            n = con.execute("DELETE FROM donations WHERE length(COALESCE(date,''))=7").rowcount
            con.execute("INSERT INTO seed_flags(name) VALUES('drop_recurring_est_v3')")
            print('  שורות הערכה מדוח הקבועים שנמחקו: %d' % n)
    except Exception as e:
        print('  drop est v3 error:', e)

    # יעקב יוסף קלוק — הוראת קבע של $700 לחודש דרך קפיטל 1, ליששכר־זבולון
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='klock_capital1_v1'").fetchone():
            row = None
            for r in con.execute("SELECT id,last,first FROM donors WHERE last IN ('קלוק','קלאק','קלעק')"):
                if 'יעקב' in (r['first'] or ''):
                    row = r; break
            if True:
                # אבא קלוק הוא אדם אחר — אם אין כרטיס ליעקב יוסף, נפתח לו כרטיס משלו
                did = row['id'] if row else con.execute(
                    "INSERT INTO donors(last,first,english,category,tier,channel,created,source) "
                    "VALUES('קלוק','יעקב יוסף','Yaakov Yosef Klock','קבוע','יששכר_זבולון','קפיטל 1',?,'ידני')",
                    (today_iso(),)).lastrowid
                added = 0
                for mm in range(1, 9):                     # ינואר–אוגוסט 2026
                    dt = '2026-%02d-01' % mm
                    if con.execute("SELECT 1 FROM donations WHERE donor_id=? AND date=? "
                                   "AND ROUND(CAST(amount AS REAL),2)=700.0", (did, dt)).fetchone():
                        continue
                    con.execute("INSERT INTO donations(donor_id,date,amount,category,method,note,paid) "
                                "VALUES(?,?,'700.00','יששכר־זבולון','קפיטל 1','הוראת קבע חודשית',1)",
                                (did, dt))
                    added += 1
                con.execute("UPDATE donors SET channel=COALESCE(NULLIF(TRIM(channel),''),'קפיטל 1') WHERE id=?",
                            (did,))
                print('  קלוק קפיטל 1: נוספו %d חיובים חודשיים של $700 (#%d)' % (added, did))
            con.execute("INSERT INTO seed_flags(name) VALUES('klock_capital1_v1')")
    except Exception as e:
        print('  klock capital1 error:', e)

    # קאסנדרה לקומב — תורמת אמיתית שאין לה עדיין כרטיס. נפתח כדי שהחיובים ייכנסו אליה.
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='lacombe_card_v1'").fetchone():
            have = [r['id'] for r in con.execute("SELECT id,last,english FROM donors")
                    if _fz(r['last'] or '') == _fz('לקומב')
                    or 'lacombe' in (r['english'] or '').lower()]
            if not have:
                con.execute("INSERT INTO donors(last,first,english,category,created,source) "
                            "VALUES('לאקומב','קאסנדרה','Cassandra Lacombe','מזדמן',?,'אוטורייז')",
                            (today_iso(),))
                print('  קאסנדרה לקומב: נפתח כרטיס')
            elif len(have) == 1:      # קיים כרטיס — נשלים לו את השם הלועזי לזיהוי החיובים
                con.execute("UPDATE donors SET english='Cassandra Lacombe' WHERE id=? "
                            "AND TRIM(COALESCE(english,''))=''", (have[0],))
            con.execute("INSERT INTO seed_flags(name) VALUES('lacombe_card_v1')")
    except Exception as e:
        print('  lacombe card error:', e)

    # יואל ברקוביץ ודוד פורסבסקי — תורמים חדשים שהגיעו דרך אבא קלוק לקמחא דפסחא תשפ"ו
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='klock_kd_donors_v1'").fetchone():
            KD = 'קמחא דפסחא תשפ"ו'
            con.execute("INSERT OR IGNORE INTO campaigns(name,created) VALUES(?,?)", (KD, today_iso()))
            for hl, hf, en in (('ברקוביץ', 'יואל', 'Joel Berkowitz'),
                               ('פורסבסקי', 'דוד', 'David Profesorske')):
                have = [r['id'] for r in con.execute("SELECT id,last,first FROM donors")
                        if _fz(r['last'] or '') == _fz(hl) and _fz(r['first'] or '') == _fz(hf)]
                if not have:
                    did = con.execute(
                        "INSERT INTO donors(last,first,english,category,notes,created,source) "
                        "VALUES(?,?,?,'מזדמן','הגיע דרך אבא קלוק',?,?)",
                        (hl, hf, en, today_iso(), KD)).lastrowid
                    print('  %s %s: נפתח כרטיס' % (hf, hl))
                else:
                    did = have[0]
                # כך החיוב שייכנס אליהם יסווג מיד לקמחא דפסחא ולא יישאר "לא סווג"
                try:
                    con.execute("INSERT OR IGNORE INTO donor_rules(donor_id,amount,category,note,created) "
                                "VALUES(?,1100,?,'הגיע דרך אבא קלוק',?)", (did, KD, today_iso()))
                except Exception:
                    pass
            con.execute("INSERT INTO seed_flags(name) VALUES('klock_kd_donors_v1')")
    except Exception as e:
        print('  klock kd donors error:', e)

    # The Four Thirty Ownes = יהושע פרנקל (שם העסק), קמחא דפסחא. סאמט־הרמן אינו שלנו.
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='frankel_samet_v1'").fetchone():
            KD = 'קמחא דפסחא תשפ"ו'
            r = con.execute("SELECT id,business FROM donors WHERE last='פרנקל' AND first='יהושע'").fetchone()
            if r:
                if not (r['business'] or '').strip():
                    con.execute("UPDATE donors SET business='The Four Thirty Owners' WHERE id=?", (r['id'],))
                try:
                    con.execute("INSERT OR IGNORE INTO donor_rules(donor_id,amount,category,note,created) "
                                "VALUES(?,1100,?,'',?)", (r['id'], KD, today_iso()))
                except Exception:
                    pass
            n = con.execute("DELETE FROM recon WHERE COALESCE(processed,0)=0 AND donor_id IS NULL "
                            "AND lower(TRIM(first))='samet'").rowcount
            con.execute("INSERT INTO seed_flags(name) VALUES('frankel_samet_v1')")
            print('  פרנקל/סאמט: העסק נרשם, %d שורות סאמט נמחקו' % n)
    except Exception as e:
        print('  frankel samet error:', e)

    # אלחנן אברמוביץ — האברך שלו נשאר בלי סכום ובלי אמצעי, ולכן הסיכום הראה התחייבות $0.
    # הוא משלם 600+750 בבנק ווסט בכל 15 לחודש.
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='abramowitz_iz_v1'").fetchone():
            r = con.execute("SELECT id FROM donors WHERE last='אברמוביץ' AND first='אלחנן'").fetchone()
            if r:
                did = r['id']
                rows = [dict(x) for x in con.execute(
                    "SELECT * FROM partners WHERE donor_id=? AND COALESCE(active,1)!=0", (did,))]
                if not rows:
                    con.execute("INSERT INTO partners(donor_id,avreich,amount,method,active) "
                                "VALUES(?,'רוזנבלט אהרן','1350','בנק_ווסט',1)", (did,))
                    print('  אברמוביץ: נוסף אברך רוזנבלט אהרן — $1,350 בבנק ווסט')
                elif len(rows) == 1:
                    con.execute("UPDATE partners SET amount=COALESCE(NULLIF(TRIM(amount),''),'1350'), "
                                "avreich=COALESCE(NULLIF(TRIM(avreich),''),'רוזנבלט אהרן'), "
                                "method=COALESCE(NULLIF(TRIM(method),''),'בנק_ווסט') WHERE id=?",
                                (rows[0]['id'],))
                    print('  אברמוביץ: הושלם סכום 1350 ואמצעי בנק ווסט לאברך')
                else:
                    for x, amt in zip(rows, ('750', '600')):
                        con.execute("UPDATE partners SET amount=COALESCE(NULLIF(TRIM(amount),''),?), "
                                    "method=COALESCE(NULLIF(TRIM(method),''),'בנק_ווסט') WHERE id=?",
                                    (amt, x['id']))
                    print('  אברמוביץ: הושלמו סכומי האברכים (750 / 600)')
            con.execute("INSERT INTO seed_flags(name) VALUES('abramowitz_iz_v1')")
    except Exception as e:
        print('  abramowitz iz error:', e)

    # אברך שמופיע ברשימת יש"ז אך חסר בכרטיס — יהודה בולמן אצל דניאל יעקובסון
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='iz_bulman_v1'").fetchone():
            r = con.execute("SELECT id FROM donors WHERE last='יעקובסון' AND first='דניאל'").fetchone()
            if r and not con.execute("SELECT 1 FROM partners WHERE donor_id=? AND avreich LIKE '%בולמן%'",
                                     (r['id'],)).fetchone():
                con.execute("INSERT INTO partners(donor_id,avreich,amount,start_date,method,active) "
                            "VALUES(?,?,'1000',?,'בנק_ווסט',1)",
                            (r['id'], 'בולמן יהודה', 'א\' כסליו תשפ"ו'))
                print('  יעקובסון דניאל: נוסף האברך בולמן יהודה — $1,000')
            con.execute("INSERT INTO seed_flags(name) VALUES('iz_bulman_v1')")
    except Exception as e:
        print('  iz bulman error:', e)

    # אשר מויאל — אותו סכום ואותו תאריך כמו האברך השני של גדליה פנסטר.
    # ובאופן כללי: מי שמחזיק כמה אברכים — התאריך זהה לכולם, אלא אם נרשם אחרת במפורש.
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='iz_same_date_v1'").fetchone():
            r = con.execute("SELECT p.id FROM partners p JOIN donors d ON d.id=p.donor_id "
                            "WHERE d.last='פנסטר' AND p.avreich LIKE '%מויאל%'").fetchone()
            if r:
                con.execute("UPDATE partners SET amount=COALESCE(NULLIF(TRIM(amount),''),'800') "
                            "WHERE id=?", (r['id'],))
            rows = [dict(x) for x in con.execute(
                "SELECT p.id,p.donor_id,p.start_date,d.last FROM partners p "
                "JOIN donors d ON d.id=p.donor_id WHERE COALESCE(p.active,1)!=0")]
            byd = {}
            for x in rows:
                byd.setdefault(x['donor_id'], []).append(x)
            n = 0
            for v in byd.values():
                if len(v) < 2 or v[0]['last'] == 'טאובנפלד':      # טאובנפלד — תאריכים שונים במכוון
                    continue
                dates = {(x['start_date'] or '').strip() for x in v if (x['start_date'] or '').strip()}
                if len(dates) != 1:
                    continue
                dt = dates.pop()
                for x in v:
                    if not (x['start_date'] or '').strip():
                        con.execute("UPDATE partners SET start_date=? WHERE id=?", (dt, x['id']))
                        n += 1
            con.execute("INSERT INTO seed_flags(name) VALUES('iz_same_date_v1')")
            print('  תאריכי יש"ז שהושלמו מאברך אחר של אותו תורם: %d' % n)
    except Exception as e:
        print('  iz same date error:', e)

    # זאב שטרן — דב בער רובינפלד, $800 מא' שבט תשפ"ו. מאומת מול חיובי בנק ווסט
    # של William Stern: $800 ב-10 לחודש מינואר 2026.
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='stern_iz_v1'").fetchone():
            r = con.execute("SELECT p.id FROM partners p JOIN donors d ON d.id=p.donor_id "
                            "WHERE d.last='שטרן' AND d.first='זאב' AND p.avreich LIKE '%רובינפלד%'").fetchone()
            if r:
                con.execute("UPDATE partners SET amount=COALESCE(NULLIF(TRIM(amount),''),'800'), "
                            "start_date=COALESCE(NULLIF(TRIM(start_date),''),?), "
                            "method=COALESCE(NULLIF(TRIM(method),''),'בנק_ווסט') WHERE id=?",
                            ('א\' שבט תשפ"ו', r['id']))
                print('  שטרן זאב: רובינפלד דב בער — $800 מא\' שבט תשפ"ו')
            con.execute("INSERT INTO seed_flags(name) VALUES('stern_iz_v1')")
    except Exception as e:
        print('  stern iz error:', e)

    # התחייבות חודשית של $1,200 לנר למאור — מיטמן אפרים, מילר שמחה, פערל שלמה
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='ner_lemaor_1200_v1'").fetchone():
            n = 0
            for last, first in (('מיטמן', 'אפרים'), ('מילר', 'שמחה'), ('פערל', 'שלמה')):
                r = con.execute("SELECT id FROM donors WHERE last LIKE ? AND first LIKE ?",
                                ('%' + last + '%', '%' + first + '%')).fetchone()
                if not r:
                    continue
                ex = con.execute("SELECT 1 FROM pledges WHERE donor_id=? AND TRIM(category)='נר למאור'",
                                 (r['id'],)).fetchone()
                if ex:
                    continue
                con.execute("INSERT INTO pledges(donor_id,category,amount,status,date,note,monthly) "
                            "VALUES(?,'נר למאור','1200','נתן',?,'התחייבות חודשית — בנק ווסט',1)",
                            (r['id'], today_iso()))
                n += 1
            con.execute("INSERT INTO seed_flags(name) VALUES('ner_lemaor_1200_v1')")
            print('  נר למאור $1,200 לחודש: נוספה התחייבות ל-%d תורמים' % n)
    except Exception as e:
        print('  ner lemaor error:', e)

    # כרטיסים כפולים של אותו אדם שנוצרו בייבוא: אותו שם משפחה לפי צליל ושם פרטי
    # שמתיישב (עטרה / "עטרה (קטי)", דוד / "משה דוד", בריינה / "בנדל בריינא").
    # בני זוג נחסמים כי שמותיהם הפרטיים שונים.
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='dupe_name_merge_v1'").fetchone():
            def _fnames(s0):
                return [t for t in re.sub(r'[^\u05d0-\u05ea ]', ' ', s0 or '').split() if len(t) >= 2]

            def _firsts_ok(a0, b0):
                ta, tb = _fnames(a0), _fnames(b0)
                if not ta or not tb:
                    return False
                short, long = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
                return all(any(_firstok(x, y, strict=True) for y in long) for x in short)
            rows = [dict(r) for r in con.execute(
                "SELECT id,last,first,phone,email,addr,english FROM donors")]
            nd = set()
            try:
                for r in con.execute("SELECT a,b FROM not_dupes"):
                    nd.add((r['a'], r['b']))
            except Exception:
                pass
            bylast = {}
            for r in rows:
                k = _fz(r['last'] or '')
                if len(k) >= 3:
                    bylast.setdefault(k, []).append(r)

            def _rich(r):
                return sum(1 for k in ('phone', 'email', 'addr', 'english') if str(r.get(k) or '').strip())
            nmg2, merged = 0, []
            for k, grp in bylast.items():
                if len(grp) < 2:
                    continue
                for i in range(len(grp)):
                    for j in range(i + 1, len(grp)):
                        a1, b1 = grp[i], grp[j]
                        pair = (min(a1['id'], b1['id']), max(a1['id'], b1['id']))
                        if pair in nd or not _firsts_ok(a1['first'], b1['first']):
                            continue
                        # שניהם עם טלפונים שונים לגמרי — כנראה שני אנשים
                        p1 = {_ph10(x) for x in re.split(r'[;,/]+', a1['phone'] or '') if _ph10(x)}
                        p2 = {_ph10(x) for x in re.split(r'[;,/]+', b1['phone'] or '') if _ph10(x)}
                        if p1 and p2 and not (p1 & p2):
                            continue
                        kp, dp = (a1, b1) if _rich(a1) >= _rich(b1) else (b1, a1)
                        if merge_into(con, kp['id'], dp['id']):
                            nmg2 += 1
                            merged.append('%s %s ← %s' % (kp['last'], kp['first'] or '', dp['first'] or ''))
                            dp['id'] = kp['id']
            con.execute("INSERT INTO seed_flags(name) VALUES('dupe_name_merge_v1')")
            print('  כרטיסים כפולים שאוחדו לפי שם: %d%s'
                  % (nmg2, (' — ' + ' · '.join(merged[:8])) if merged else ''))
    except Exception as e:
        print('  dupe name merge error:', e)

    # מאיר קבע: חיים ולאה אסתר לאקס הם בעל ואישה בכרטיס אחד; מוסקוביץ העני
    # ואסתר הם שני תורמים נפרדים ואין למזג אותם לעולם
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='lax_moskowitz_v2'").fetchone():
            h = con.execute("SELECT id FROM donors WHERE last LIKE '%לאקס%' AND first LIKE '%חיים%'").fetchone()
            w = con.execute("SELECT id FROM donors WHERE last LIKE '%לאקס%' AND first LIKE '%לאה%'").fetchone()
            if h and w and h['id'] != w['id']:
                merge_into(con, h['id'], w['id'])
            if h:   # הכרטיס נושא את שניהם, גם אם האיחוד כבר קרה קודם
                con.execute("UPDATE donors SET first='חיים ולאה אסתר' WHERE id=? AND first NOT LIKE '%לאה%'",
                            (h['id'],))
                print('  לאקס: הכרטיס נושא את חיים ולאה אסתר')
            n2 = 0
            # ישראל ברודי ושרה ברודי אינם קשורים
            bs = [r['id'] for r in con.execute("SELECT id FROM donors WHERE last LIKE '%ברודי%'")]
            for i in range(len(bs)):
                for j in range(i + 1, len(bs)):
                    con.execute("INSERT OR IGNORE INTO not_dupes(a,b,created) VALUES(?,?,?)",
                                (min(bs[i], bs[j]), max(bs[i], bs[j]), today_iso()))
                    n2 += 1
            ms = [r['id'] for r in con.execute("SELECT id FROM donors WHERE last LIKE '%מוסקוביץ%'")]
            for i in range(len(ms)):
                for j in range(i + 1, len(ms)):
                    con.execute("INSERT OR IGNORE INTO not_dupes(a,b,created) VALUES(?,?,?)",
                                (min(ms[i], ms[j]), max(ms[i], ms[j]), today_iso()))
                    n2 += 1
            con.execute("INSERT INTO seed_flags(name) VALUES('lax_moskowitz_v2')")
            print('  מוסקוביץ / ברודי: %d זוגות סומנו כתורמים נפרדים' % n2)
    except Exception as e:
        print('  lax/moskowitz error:', e)

    # תרגומים שנשמרו זהים למקור — התרגום לא באמת קרה. מנקים כדי שירוצו מחדש
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='retranslate_v1'").fetchone():
            cur5 = con.execute(
                "UPDATE contacts_log SET body_he=NULL WHERE COALESCE(TRIM(body_he),'')<>'' "
                "AND REPLACE(REPLACE(TRIM(body_he),' ',''),CHAR(10),'')"
                "  = REPLACE(REPLACE(TRIM(body),' ',''),CHAR(10),'')")
            con.execute("INSERT INTO seed_flags(name) VALUES('retranslate_v1')")
            print('  תרגומים שנוקו לתרגום מחדש: %d' % cur5.rowcount)
    except Exception as e:
        print('  retranslate error:', e)

    # תיקוני איות ושמות עבריים שמאיר מסר, ואיחוד כרטיסים כפולים שנוצרו בגללם
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='namefix_aug11_v1'").fetchone():
            def _one(last, first=None):
                if first:
                    r = con.execute("SELECT id FROM donors WHERE last LIKE ? AND COALESCE(first,'') LIKE ?",
                                    ('%' + last + '%', '%' + first + '%')).fetchone()
                else:
                    r = con.execute("SELECT id FROM donors WHERE last LIKE ?", ('%' + last + '%',)).fetchone()
                return r['id'] if r else None
            nfix = 0
            # איות נכון של שמות משפחה בעברית
            for old, new in (('פק', 'פאק'), ('אמסעל', 'אמזל')):
                cur4 = con.execute("UPDATE donors SET last=? WHERE TRIM(last)=?", (new, old))
                nfix += cur4.rowcount
            # לאוניד גרוסמן = אליעזר גרוסמן (השם העברי)
            con.execute("UPDATE donors SET first='אליעזר' WHERE TRIM(last)='גרוסמן' AND TRIM(first)='לאוניד'")
            # שם ומשפחה שהוזנו הפוך — בנימין שטטפלד
            con.execute("UPDATE donors SET last='שטטפלד', first='בנימין' "
                        "WHERE TRIM(last)='בנימין' AND TRIM(first)='שטטפלד'")
            # כרטיסי שטטפלד/סטטפלד של ברכה — מתאחדים לכרטיס של יצחק וברכה
            keep = _one('שטטפלד', 'יצחק וברכה')
            nmg = 0
            if keep:
                for r in con.execute("SELECT id,last,first,english FROM donors WHERE id<>?", (keep,)):
                    if _fz(r['last']) != _fz('שטטפלד'):
                        continue
                    nm = ((r['first'] or '') + ' ' + (r['english'] or '')).lower()
                    if re.search(r'(?:^|\s)(?:ברכ|בט)|beth|brach', nm):
                        if merge_into(con, keep, r['id']):
                            nmg += 1
            # כרטיסים כפולים של אותו אדם — אותו טלפון ואותו שם משפחה לפי צליל
            rows = [dict(r) for r in con.execute("SELECT id,last,first,phone,email,addr FROM donors")]
            nd = set()
            try:
                for r in con.execute("SELECT a,b FROM not_dupes"):
                    nd.add((r['a'], r['b']))
            except Exception:
                pass
            byph = {}
            for r in rows:
                for ph in re.split(r'[/,]', r['phone'] or ''):
                    p10 = _ph10(ph)
                    if p10:
                        byph.setdefault(p10, []).append(r)
            def _score(r):
                return sum(1 for k in ('phone', 'email', 'addr') if str(r.get(k) or '').strip())
            done = set()
            for p10, grp in byph.items():
                if len(grp) < 2:
                    continue
                for i in range(len(grp)):
                    for j in range(i + 1, len(grp)):
                        a1, b1 = grp[i], grp[j]
                        if a1['id'] == b1['id'] or _fz(a1['last']) != _fz(b1['last']):
                            continue
                        # אותו טלפון ואותו שם משפחה זה גם המצב של בני זוג. ממזגים
                        # רק כששמות פרטיים מתיישבים — זהים, קיצור, או איות שונה.
                        f1, f2 = (a1['first'] or '').strip(), (b1['first'] or '').strip()
                        z1, z2 = _fz(f1), _fz(f2)
                        if f1 and f2:
                            if min(len(z1), len(z2)) >= 2:
                                if not (z1.startswith(z2) or z2.startswith(z1)):
                                    continue
                            elif not _fitfirst(f1, f2):
                                continue
                        pair = (min(a1['id'], b1['id']), max(a1['id'], b1['id']))
                        if pair in nd or pair in done:
                            continue
                        done.add(pair)
                        kp, dp = (a1, b1) if _score(a1) >= _score(b1) else (b1, a1)
                        if merge_into(con, kp['id'], dp['id']):
                            nmg += 1
            con.execute("INSERT INTO seed_flags(name) VALUES('namefix_aug11_v1')")
            print('  תיקוני איות: %d · כרטיסים שאוחדו לפי טלפון+שם: %d' % (nfix, nmg))
    except Exception as e:
        print('  namefix error:', e)

    # מפת החודשים של התורם התעדכנה ידנית, ולכן חודשים שכבר שולמו בפועל
    # (יש להם תרומה עם תאריך) נשארו מסומנים כלא־עברו. משלימים מהתרומות.
    # רץ בכל הפעלה, בלי דגל, כדי שיישאר מעודכן גם אחרי ייבוא חדש.
    try:
        yr = str(datetime.date.today().year)
        marks = {}
        for r in con.execute("SELECT donor_id, SUBSTR(date,6,2) mo FROM donations "
                             "WHERE LENGTH(COALESCE(date,''))>=7 AND SUBSTR(date,1,4)=?", (yr,)):
            try:
                i = int(r['mo']) - 1
            except Exception:
                continue
            if 0 <= i < 12 and r['donor_id']:
                marks.setdefault(r['donor_id'], set()).add(i)
        nmk = 0
        for did, mos in marks.items():
            row = con.execute("SELECT months FROM donors WHERE id=?", (did,)).fetchone()
            if not row:
                continue
            cur3 = list((row['months'] or '').ljust(12, '-')[:12])
            ch = False
            for i in mos:
                if cur3[i] not in ('p', 'c', 'h'):
                    cur3[i] = 'p'; ch = True
            if ch:
                con.execute("UPDATE donors SET months=? WHERE id=?", (''.join(cur3), did)); nmk += 1
        if nmk:
            print('  מפת חודשים שהושלמה מהתרומות: %d תורמים' % nmk)
    except Exception as e:
        print('  months sync error:', e)

    # שורות סיכום עם חודש בלבד שנשארו מרשימת הקבועים — נמחקות כשכבר יש
    # באותו חודש חיובים אמיתיים עם תאריך מדויק, כלומר הן כפילות.
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='month_only_cleanup_v1'").fetchone():
            ndel2, nkeep = 0, 0
            for r in con.execute("SELECT id,donor_id,amount,date FROM donations "
                                 "WHERE LENGTH(COALESCE(date,''))<=7").fetchall():
                if not r['donor_id'] or not (r['date'] or '').strip():
                    continue
                n = con.execute("SELECT COUNT(*) FROM donations WHERE donor_id=? AND LENGTH(date)>7 "
                                "AND SUBSTR(date,1,7)=?", (r['donor_id'], r['date'][:7])).fetchone()[0]
                if n:
                    con.execute("DELETE FROM donations WHERE id=?", (r['id'],)); ndel2 += 1
                else:
                    con.execute("UPDATE donations SET note=COALESCE(NULLIF(TRIM(note),''),?) WHERE id=?",
                                ('שורת סיכום מרשימת הקבועים — אין חיוב מדויק לחודש הזה', r['id']))
                    nkeep += 1
            con.execute("INSERT INTO seed_flags(name) VALUES('month_only_cleanup_v1')")
            print('  שורות חודש-בלבד: נמחקו %d כפילויות, נשארו %d ללא חיוב מקביל' % (ndel2, nkeep))
    except Exception as e:
        print('  month only cleanup error:', e)

    # טלפונים שמאיר אישר אחד־אחד מול אנשי הקשר. מספר בפורמט חיוג בינלאומי
    # ישראלי (012 + 1 + מספר אמריקאי) נשמר גם בצורתו הרגילה.
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='phones_confirmed_v1'").fetchone():
            CONF = [
                ('ווינשניידר', 'חיים פסח', '+1 312-315-3707', 'evaweinschneider@gmail.com'),
                ('סחייאק',     'אדי',      '+1 347-831-8883', ''),
                ('זייגלבוים',  'לוי',      '+1 917-776-1097', ''),
                ('הלברשטם',    'מארק',     '+1 718-377-7337', ''),
                ('טשרנס',      'אהרן',     '+1 347-321-5816', ''),
                ('פרלמוטר',    'יצחק',     '+1 410-358-4380', ''),
                ('אברמוביץ',   'אלחנן',    '+1 718-377-0930', ''),
            ]
            npf = 0
            for last, first, ph, em in CONF:
                r = con.execute("SELECT id,phone,email FROM donors WHERE last LIKE ? AND first LIKE ?",
                                ('%' + last + '%', '%' + first + '%')).fetchone()
                if not r:
                    continue
                if not (r['phone'] or '').strip():
                    con.execute("UPDATE donors SET phone=? WHERE id=?", (ph, r['id'])); npf += 1
                if em and not (r['email'] or '').strip():
                    con.execute("UPDATE donors SET email=? WHERE id=?", (em, r['id']))
            # הצעות שמאיר כבר דחה — שלא יחזרו במסך ההשלמה
            for last, first, ph in (('גינסברג', 'אהרן', '+1 (718) 440-6276'),
                                    ('ברקוביץ', 'יואל', '1-718-619-5635'),
                                    ('אברמוביץ', 'לאה', '1-718-377-0930'),
                                    ('פוקס', 'שמשון', '+972 52-715-4167')):
                r = con.execute("SELECT id FROM donors WHERE last LIKE ? AND first LIKE ?",
                                ('%' + last + '%', '%' + first + '%')).fetchone()
                if r:
                    con.execute("INSERT INTO sugg_reject(donor_id,kind,val,created) "
                                "VALUES(?,'phone',?,?)", (r['id'], ph, today_iso()))
            con.execute("INSERT INTO seed_flags(name) VALUES('phones_confirmed_v1')")
            print('  טלפונים שאושרו ידנית: %d' % npf)
    except Exception as e:
        print('  confirmed phones error:', e)

    # סורוס פאונדיישן — מאיר ביקש למחוק לגמרי מהמערכת
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='soros_delete_v1'").fetchone():
            r = con.execute("SELECT id FROM donors WHERE last LIKE '%סורוס%'").fetchone()
            if r:
                did = r['id']
                for t in ('donations', 'recon', 'tasks', 'contacts_log', 'pledges', 'parnes',
                          'partners', 'prayers', 'transactions', 'building'):
                    try:
                        con.execute("DELETE FROM %s WHERE donor_id=?" % t, (did,))
                    except Exception:
                        pass
                try:
                    con.execute("DELETE FROM files WHERE kind='donor' AND ref_id=?", (did,))
                except Exception:
                    pass
                con.execute("DELETE FROM donors WHERE id=?", (did,))
                print('  סורוס פאונדיישן: הכרטיס נמחק לגמרי (#%d)' % did)
            con.execute("INSERT INTO seed_flags(name) VALUES('soros_delete_v1')")
    except Exception as e:
        print('  soros delete error:', e)

    # ה-$1,200 של נר למאור אינו מופיע באף חודש בדוח בנק ווסט — פותחים משימה לבדיקה
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='ner_lemaor_check_v1'").fetchone():
            r = con.execute("SELECT id FROM donors WHERE last LIKE '%מיטמן%' AND first LIKE '%אפרים%'").fetchone()
            if r:
                con.execute("INSERT INTO tasks(donor_id,due_date,kind,note,done,assignee) "
                            "VALUES(?,?,'verify',?,0,'מאיר')",
                            (r['id'], today_iso(),
                             'לבדוק בבנק ווסט את ההוראת קבע של $1,200 נר למאור — היא לא מופיעה '
                             'באף חודש בדוח (ינואר–אוגוסט). אפרים מחויב $1,000 ב-1 לחודש עד יוני '
                             'ו-$1,650 מיולי, שורה אחת בלבד בכל חודש. לבדוק אם יש חשבון סוחר שני, '
                             'או שההוראה לא רצה בכלל.'))
                print('  נר למאור: נפתחה משימת בדיקה אצל מיטמן אפרים')
            con.execute("INSERT INTO seed_flags(name) VALUES('ner_lemaor_check_v1')")
    except Exception as e:
        print('  ner lemaor check error:', e)

    # שניאור זלמן מיטמן אינו קשור לשאר המיטמנים — שלא יוצע מיזוג ביניהם
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='mittman_sz_notdupe_v1'").fetchone():
            sz = con.execute("SELECT id FROM donors WHERE last LIKE '%מיטמן%' AND first LIKE '%שניאור%'").fetchone()
            n = 0
            if sz:
                for r in con.execute("SELECT id FROM donors WHERE last LIKE '%מיטמן%' AND id<>?", (sz['id'],)):
                    a1, b1 = min(sz['id'], r['id']), max(sz['id'], r['id'])
                    con.execute("INSERT OR IGNORE INTO not_dupes(a,b,created) VALUES(?,?,?)", (a1, b1, today_iso()))
                    n += 1
            con.execute("INSERT INTO seed_flags(name) VALUES('mittman_sz_notdupe_v1')")
            print('  שניאור זלמן מיטמן: סומן כלא־קשור ל-%d מיטמנים' % n)
    except Exception as e:
        print('  mittman sz error:', e)

    # ציון כהן — $1,000 לשלושת המיטמנים ביחד (מאיר אישר), לא $1,400
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='zion_cohen_1000_v1'").fetchone():
            cur3 = con.execute(
                "UPDATE partners SET amount='1000' WHERE COALESCE(active,1)<>0 "
                "AND (avreich LIKE '%ציון%כהן%' OR avreich LIKE '%כהן%ציון%') "
                "AND donor_id IN (SELECT id FROM donors WHERE last LIKE '%מיטמן%')")
            con.execute("INSERT INTO seed_flags(name) VALUES('zion_cohen_1000_v1')")
            print('  ציון כהן: הסכום המשותף עודכן ל-$1,000 (%d שורות)' % cur3.rowcount)
    except Exception as e:
        print('  zion cohen amount error:', e)

    # ציון כהן מוחזק ביחד בידי שלושת המיטמנים — הסכום שייך לכולם יחד, לא לכל אחד
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='zion_cohen_joint_v1'").fetchone():
            cur2 = con.execute(
                "UPDATE partners SET joint=1 WHERE COALESCE(active,1)<>0 "
                "AND (REPLACE(avreich,'  ',' ') LIKE '%ציון%כהן%' OR REPLACE(avreich,'  ',' ') LIKE '%כהן%ציון%') "
                "AND donor_id IN (SELECT id FROM donors WHERE last LIKE '%מיטמן%')")
            con.execute("INSERT INTO seed_flags(name) VALUES('zion_cohen_joint_v1')")
            print('  ציון כהן: סומן כמוחזק ביחד אצל %d מהמיטמנים' % cur2.rowcount)
    except Exception as e:
        print('  zion cohen joint error:', e)

    # אנשין יעקב יוסף — הזבולון שלו נכתב בקובץ כ"דוד א" בלבד; מאיר אישר: דוד אהרוני
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='anshin_aharoni_v1'").fetchone():
            d = con.execute("SELECT id FROM donors WHERE last LIKE '%אהרוני%' AND first LIKE '%דוד%'").fetchone()
            if d:
                ex = con.execute("SELECT id FROM partners WHERE donor_id=? AND avreich LIKE '%אנשין%' "
                                 "AND avreich LIKE '%יוסף%'", (d['id'],)).fetchone()
                if ex:
                    con.execute("UPDATE partners SET amount=COALESCE(NULLIF(TRIM(amount),''),'600'), "
                                "start_date=COALESCE(NULLIF(TRIM(start_date),''),?), active=1 WHERE id=?",
                                ('א\' אלול תשפ"ה', ex['id']))
                else:
                    # אם הוא רשום בטעות אצל תורם אחר — מעבירים, אחרת יוצרים שורה חדשה
                    mv = con.execute("SELECT id FROM partners WHERE avreich LIKE '%אנשין%' AND avreich LIKE '%יוסף%'").fetchone()
                    if mv:
                        con.execute("UPDATE partners SET donor_id=?, amount=COALESCE(NULLIF(TRIM(amount),''),'600'), "
                                    "start_date=COALESCE(NULLIF(TRIM(start_date),''),?), active=1 WHERE id=?",
                                    (d['id'], 'א\' אלול תשפ"ה', mv['id']))
                    else:
                        con.execute("INSERT INTO partners(donor_id,avreich,amount,start_date,active) VALUES(?,?,?,?,1)",
                                    (d['id'], 'אנשין יעקב יוסף', '600', 'א\' אלול תשפ"ה'))
                print('  דוד אהרוני: אנשין יעקב יוסף — $600 מא\' אלול תשפ"ה')
            con.execute("INSERT INTO seed_flags(name) VALUES('anshin_aharoni_v1')")
    except Exception as e:
        print('  anshin aharoni error:', e)

    # חיובים שנשארו ללא כרטיס כי השם על האשראי שונה מהשם בכרטיס
    # (Marc Mendelson = מוטי מנדלסון, Schia Rosenfed בלי ל׳, Beth = ברכה שטטפלד).
    for _flag, _link in (
        ('card_name_link_v1', {
            'marc mendelson':           ('מנדלסון', 'יוסף מרדכי'),
            'schia rosenfed':           ('רוזנפלד', 'יהושע'),
            'daniel jacobson':          ('יעקובסון', 'דניאל'),
            'danial jacobson':          ('יעקובסון', 'דניאל'),
            'brachca statfeld':         ('שטטפלד', 'יצחק וברכה'),
            'ilana rosenfeld':          ('רוזנפלד', 'אילנה'),
            'zev marmurstein schwadel': ('מרמרשטיין', 'זאב'),
        }),
        ('card_name_link_v2', {
            'beth statfeld':            ('שטטפלד', 'יצחק וברכה'),
        }),
        ('card_name_link_v3', {
            'gold star restoration':    ('דונט', 'מוטי'),
        }),
        ('card_name_link_v4', {
            'bespoke mittman':          ('מיטמן', 'מאיר'),
        }),
        ('card_name_link_v5', {
            'fransis frechter':         ('פרכטר', 'פייגא לאה'),
            'y.y levi':                 ('לעווי', 'יוסף יהושע'),
            'cassandra lacombe':        ('לקומב', 'קאסנדרה'),
        }),
        ('card_name_link_v6', {
            'joel berkowitz':           ('ברקוביץ', 'יואל'),
            'david profesorske':        ('פורסבסקי', 'דוד'),
        }),
        ('card_name_link_v7', {
            'the four thirty ownes':    ('פרנקל', 'יהושע'),
            'sm berger':                ('ברגר', 'שמואל'),
        }),
    ):
        try:
            if con.execute("SELECT 1 FROM seed_flags WHERE name=?", (_flag,)).fetchone():
                continue
            n = link_card_names(con, _link)
            con.execute("INSERT INTO seed_flags(name) VALUES(?)", (_flag,))
            print('  חיובים ששויכו לפי שם על האשראי (%s): %d' % (_flag[-2:], n))
        except Exception as e:
            print('  card name link error:', e)

    # מוטי דונט — החיובים מגיעים על שם העסק Gold Star Restoration
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='goldstar_biz_v1'").fetchone():
            for hl, hf, biz in (('דונט', 'מוטי', 'Gold Star Restoration'),
                                ('מיטמן', 'מאיר', 'Bespoke')):
                r = con.execute("SELECT id,business FROM donors WHERE last=? AND first=?", (hl, hf)).fetchone()
                if r and not (r['business'] or '').strip():
                    con.execute("UPDATE donors SET business=? WHERE id=?", (biz, r['id']))
                    print('  %s %s: נרשם העסק %s' % (hf, hl, biz))
            con.execute("INSERT INTO seed_flags(name) VALUES('goldstar_biz_v1')")
    except Exception as e:
        print('  goldstar biz error:', e)

    # מנדלסון יוסף מרדכי = מוטי = Mark. הכינויים נשמרים בכרטיס וגם משמשים
    # להתאמת אנשי קשר, ולכן "מנדלסון מוטי" מהטלפון יימצא מעכשיו
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='mendelson_moti_v1'").fetchone():
            r = con.execute("SELECT id,aliases FROM donors WHERE last LIKE '%מנדלסון%' "
                            "AND first LIKE '%מרדכי%'").fetchone()
            if r:
                al = [x.strip() for x in re.split(r'[,;/]', r['aliases'] or '') if x.strip()]
                for x in ('מוטי', 'Mark', 'Marc'):
                    if x not in al:
                        al.append(x)
                con.execute("UPDATE donors SET aliases=? WHERE id=?", (', '.join(al), r['id']))
                # המספר מאיש הקשר "מנדלסון מוטי" — אינו בייצוא אנשי הקשר שנשלח
                con.execute("UPDATE donors SET phone='+1 917-816-8129' "
                            "WHERE id=? AND COALESCE(TRIM(phone),'')=''", (r['id'],))
                print('  מנדלסון: נוספו הכינויים מוטי / Mark והטלפון')
            con.execute("INSERT INTO seed_flags(name) VALUES('mendelson_moti_v1')")
    except Exception as e:
        print('  mendelson alias error:', e)

    # ייצוא אנשי קשר אחרי שגוגל מיזגה את הכפילויות — כרטיסים שלמים,
    # עם השם, הטלפון והכתובת יחד. רץ ראשון כי זה המקור האיכותי ביותר.
    try:
        seed3 = os.path.join(HERE, 'contacts_seed3.csv')
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='contacts_merged_v1'").fetchone() \
                and os.path.exists(seed3):
            import gcontacts as _gc3
            with open(seed3, encoding='utf-8-sig', errors='replace') as f:
                _cards3 = _gc3.parse_csv(f.read())
            _r3 = contacts_fill(con, _cards3)
            con.execute("INSERT INTO seed_flags(name) VALUES('contacts_merged_v1')")
            print('  אנשי קשר אחרי מיזוג בגוגל: %d כרטיסים · %d כתובות, %d טלפונים, %d מיילים'
                  % (_r3['donors'], _r3['filled']['addr'], _r3['filled']['phone'],
                     _r3['filled']['email']))
    except Exception as e:
        print('  merged contacts error:', e)

    # ייצוא VCF מהטלפון — כולל את החשבון השני ואת אנשי הקשר ששמורים במכשיר
    try:
        seedv = os.path.join(HERE, 'contacts_seed2.vcf')
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='contacts_vcf_v2'").fetchone() \
                and os.path.exists(seedv):
            import gcontacts as _gc2
            with open(seedv, encoding='utf-8', errors='replace') as f:
                _cards2 = _gc2.parse_any(f.read())
            _r2 = contacts_fill(con, _cards2)
            con.execute("INSERT INTO seed_flags(name) VALUES('contacts_vcf_v2')")
            print('  אנשי קשר מהטלפון (VCF): %d כרטיסים · %d כתובות, %d טלפונים, %d מיילים'
                  % (_r2['donors'], _r2['filled']['addr'], _r2['filled']['phone'],
                     _r2['filled']['email']))
    except Exception as e:
        print('  vcf seed error:', e)

    # השלמת כתובות, טלפונים, מיילים ושמות לקוויטל מייצוא אנשי הקשר של גוגל.
    # ממלא רק שדות ריקים, ולכן בטוח להריץ פעם אחת על הנתונים החיים.
    try:
        seedc = os.path.join(HERE, 'contacts_seed.csv')
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='contacts_seed_v3'").fetchone() \
                and os.path.exists(seedc):
            import gcontacts as _gc
            with open(seedc, encoding='utf-8-sig') as f:
                _cards = _gc.parse_csv(f.read())
            _r = contacts_fill(con, _cards)
            con.execute("INSERT OR IGNORE INTO seed_flags(name) VALUES('contacts_seed_v1')")
            con.execute("INSERT INTO seed_flags(name) VALUES('contacts_seed_v3')")
            print('  אנשי קשר מגוגל: %d כרטיסים · %d כתובות, %d טלפונים, %d מיילים, '
                  '%d קוויטל, %d הערות (לא שויכו %d)'
                  % (_r['donors'], _r['filled']['addr'], _r['filled']['phone'],
                     _r['filled']['email'], _r['kvittel'], _r['notes'], _r['unmatched_total']))
    except Exception as e:
        print('  contacts seed error:', e)

    # שיוך אוטומטי של חיובים שנשארו בלי כרטיס — מייל, טלפון, ותעתיק השם לעברית
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='recon_autolink_v1'").fetchone():
            n = link_by_identity(con)
            con.execute("INSERT INTO seed_flags(name) VALUES('recon_autolink_v1')")
            print('  חיובים ששויכו לפי מייל/טלפון/תעתיק: %d' % n)
    except Exception as e:
        print('  recon autolink error:', e)

    # שורה שנרשמה בעבר עם חודש בלבד, ולצידה אותו סכום עם תאריך מדויק — אותו כסף פעמיים.
    # שומרים את זו שיש לה תאריך.
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='month_only_dedup_v1'").fetchone():
            n = con.execute("DELETE FROM donations WHERE id IN (SELECT s.id FROM donations s JOIN donations r ON r.donor_id=s.donor_id AND length(r.date)=10 AND substr(r.date,1,7)=s.date AND ROUND(CAST(r.amount AS REAL),2)=ROUND(CAST(s.amount AS REAL),2) WHERE length(COALESCE(s.date,''))=7)").rowcount
            con.execute("INSERT INTO seed_flags(name) VALUES('month_only_dedup_v1')")
            print('  שורות חודש-בלבד שהוחלפו בתאריך מדויק: %d' % n)
    except Exception as e:
        print('  month only dedup error:', e)

    # משימות שכבר סומנו כבוצעו לפני שהתיעוד הזה נכנס — נרשמות רטרואקטיבית בדף
    # הקשר של התורם. תאריך הביצוע לא נשמר אז, ולכן נרשם תאריך היעד ומצוין שכך.
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='task_done_log_v1'").fetchone():
            n = 0
            for t in con.execute("SELECT * FROM tasks WHERE COALESCE(done,0)<>0 "
                                 "AND donor_id IS NOT NULL "
                                 "AND id NOT IN (SELECT COALESCE(task_id,-1) FROM contacts_log)"):
                day = (t['done_date'] or '').strip() or (t['due_date'] or '').strip()
                if not day:
                    continue
                who = (t['done_by'] or '').strip() or (t['assignee'] or '').strip() or 'מאיר'
                txt = task_text(t['kind'], t['note'])
                sfx = '' if (t['done_date'] or '').strip() else ' (לפי תאריך היעד)'
                con.execute("INSERT INTO contacts_log(donor_id,date,channel,summary,next_date,task_id) "
                            "VALUES(?,?,'משימה',?,'',?)",
                            (t['donor_id'], day, '✓ בוצע: %s · ע"י %s%s' % (txt, who, sfx), t['id']))
                con.execute("UPDATE tasks SET done_date=COALESCE(NULLIF(done_date,''),?), "
                            "done_by=COALESCE(NULLIF(done_by,''),?) WHERE id=?", (day, who, t['id']))
                n += 1
            con.execute("INSERT INTO seed_flags(name) VALUES('task_done_log_v1')")
            print('  משימות שבוצעו ונרשמו בדף הקשר: %d' % n)
    except Exception as e:
        print('  task done log error:', e)

    # ציון כהן — שלושת המיטמנים מחזיקים אותו יחד ב-$1,400 לחודש, אבל הכסף יוצא
    # משני כרטיסים בלבד: אפרים $650 וגבריאל $750. מאיר מחזיק ואינו משלם.
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='zion_split_v1'").fetchone():
            n = 0
            for first, share in (('אפרים', '650'), ('גבריאל', '750'), ('מאיר', '0')):
                r = con.execute("SELECT p.id FROM partners p JOIN donors d ON d.id=p.donor_id "
                                "WHERE d.last='מיטמן' AND d.first=? AND p.avreich LIKE '%ציון%'",
                                (first,)).fetchone()
                if r:
                    con.execute("UPDATE partners SET share=?, amount='1400', joint=1 WHERE id=?",
                                (share, r['id'])); n += 1
            con.execute("INSERT INTO seed_flags(name) VALUES('zion_split_v1')")
            print('  שותפות ציון כהן — חלוקה לפי הכרטיסים: %d מחזיקים' % n)
    except Exception as e:
        print('  zion split error:', e)

    # אפרים מיטמן — הקבוע שלו הוא גם יששכר־זבולון וגם נר למאור
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='purpose_multi_v1'").fetchone():
            r = con.execute("SELECT id,purpose FROM donors WHERE last='מיטמן' AND first='אפרים'").fetchone()
            if r and 'יששכר' not in (r['purpose'] or ''):
                p = ' · '.join([x for x in ['יששכר־זבולון'] + [(r['purpose'] or '').strip()] if x])
                con.execute("UPDATE donors SET purpose=? WHERE id=?", (p, r['id']))
            con.execute("INSERT INTO seed_flags(name) VALUES('purpose_multi_v1')")
    except Exception as e:
        print('  purpose multi error:', e)

    # משימות שנוצרו פעמיים מלחיצה כפולה על "הוסף משימה" — נשארת הראשונה.
    # רץ בכל עלייה, כי כפילות יכולה להיווצר שוב עד שכל המכשירים יתעדכנו.
    try:
        n = con.execute("""DELETE FROM tasks WHERE id IN (
            SELECT t.id FROM tasks t WHERE COALESCE(t.done,0)=0 AND t.id > (
              SELECT MIN(s.id) FROM tasks s WHERE COALESCE(s.done,0)=0
              AND COALESCE(s.donor_id,0)=COALESCE(t.donor_id,0)
              AND COALESCE(s.due_date,'')=COALESCE(t.due_date,'')
              AND COALESCE(s.kind,'')=COALESCE(t.kind,'')
              AND COALESCE(s.note,'')=COALESCE(t.note,'')))""").rowcount
        if n:
            print('  משימות כפולות שנמחקו: %d' % n)
    except Exception as e:
        print('  dupe tasks error:', e)

    # רשימת האברכים של הכולל — נבנית מהשמות שכבר מופיעים אצל התורמים, וממשיכה
    # להתעדכן בכל עלייה כדי שאברך שנוסף דרך כרטיס תורם ייכנס גם לרשימה.
    try:
        n = 0
        for r in con.execute("SELECT DISTINCT TRIM(avreich) a FROM partners "
                             "WHERE COALESCE(TRIM(avreich),'')<>''"):
            if not _is_avreich(r['a']):      # "כולל יום" אינו אברך — לא נכנס לרשימה
                continue
            if con.execute("SELECT 1 FROM avreichim WHERE name=?", (r['a'],)).fetchone():
                continue
            l, f = _split_av(r['a'])
            st = con.execute("SELECT start_date FROM partners WHERE TRIM(avreich)=? "
                             "AND COALESCE(start_date,'')<>'' ORDER BY id LIMIT 1", (r['a'],)).fetchone()
            con.execute("INSERT INTO avreichim(name,last,first,note,started,created) VALUES(?,?,?,'',?,?)",
                        (r['a'], l, f, (st['start_date'] if st else ''), today_iso()))
            n += 1
        if n:
            print('  אברכים שנוספו לרשימת הכולל: %d' % n)
    except Exception as e:
        print('  avreichim seed error:', e)

    # שמות אברכים שנרשמו בסדר הפוך — שם משפחה תמיד ראשון, כמו בשאר הרשימה.
    # ושורות "כולל יום" יורדות מרשימת האברכים (השותפות אצל התורם נשארת).
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='avreich_names_v1'").fetchone():
            for bad, good in (('דוד ישי', 'ישי דוד'), ('יצחק שטרנברג', 'שטרנברג יצחק')):
                if con.execute("SELECT 1 FROM avreichim WHERE name=?", (good,)).fetchone():
                    con.execute("DELETE FROM avreichim WHERE name=?", (bad,))
                else:
                    l, f = _split_av(good)
                    con.execute("UPDATE avreichim SET name=?, last=?, first=? WHERE name=?",
                                (good, l, f, bad))
                con.execute("UPDATE partners SET avreich=? WHERE TRIM(avreich)=?", (good, bad))
            n = con.execute("DELETE FROM avreichim WHERE name LIKE '%כולל יום%'").rowcount
            con.execute("INSERT INTO seed_flags(name) VALUES('avreich_names_v1')")
            print('  שמות אברכים סודרו · שורות כולל־יום שהוסרו מהרשימה: %d' % n)
    except Exception as e:
        print('  avreich names error:', e)

    # "ציון כהן" נרשם בסדר הפוך — כהן הוא שם המשפחה. ולגבריאל מיטמן חסר
    # תאריך התחלה בשותפות הזאת; שני אחיו רשומים א' שבט תשפ"ה על אותו אברך.
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='zion_name_v1'").fetchone():
            for bad, good in (('ציון כהן', 'כהן ציון'),):
                l, f = _split_av(good)
                if con.execute("SELECT 1 FROM avreichim WHERE name=?", (good,)).fetchone():
                    con.execute("DELETE FROM avreichim WHERE name=?", (bad,))
                else:
                    con.execute("UPDATE avreichim SET name=?, last=?, first=? WHERE name=?",
                                (good, l, f, bad))
                con.execute("UPDATE partners SET avreich=? WHERE TRIM(avreich)=?", (good, bad))
                # תאריך שחסר אצל מחזיק אחד — נלקח מהמחזיקים האחרים של אותו אברך
                st = con.execute("SELECT start_date FROM partners WHERE TRIM(avreich)=? "
                                 "AND COALESCE(TRIM(start_date),'')<>'' ORDER BY id LIMIT 1",
                                 (good,)).fetchone()
                if st:
                    con.execute("UPDATE partners SET start_date=? WHERE TRIM(avreich)=? "
                                "AND COALESCE(TRIM(start_date),'')=''", (st['start_date'], good))
            con.execute("INSERT INTO seed_flags(name) VALUES('zion_name_v1')")
            print('  כהן ציון: השם סודר והתאריך הושלם לכל המחזיקים')
    except Exception as e:
        print('  zion name error:', e)

    # מאיר מיטמן — $585 לחודש על הרכב של כולל חצות, לצד $1,000 האברך שלו.
    # יחד $1,585, בדיוק הסכום הקבוע שרשום בכרטיס.
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='meir_car_v1'").fetchone():
            r = con.execute("SELECT id FROM donors WHERE last='מיטמן' AND first='מאיר'").fetchone()
            if r:
                if not con.execute("SELECT 1 FROM pledges WHERE donor_id=? AND category='רכב כולל חצות'",
                                   (r['id'],)).fetchone():
                    con.execute("INSERT INTO pledges(donor_id,category,amount,status,date,monthly) "
                                "VALUES(?,'רכב כולל חצות','585','נתן',?,1)", (r['id'], today_iso()))
                con.execute("UPDATE donors SET purpose='יששכר־זבולון · רכב כולל חצות' WHERE id=?", (r['id'],))
            con.execute("INSERT INTO seed_flags(name) VALUES('meir_car_v1')")
            print('  מאיר מיטמן: נרשם רכב כולל חצות $585 לחודש')
    except Exception as e:
        print('  meir car error:', e)

    # תורם שנמחק ונוצר מחדש באחת המיגרציות — נמחק שוב
    try:
        n = purge_deleted(con)
        if n:
            print('  כרטיסים שנמחקו וחזרו — נמחקו שוב: %d' % n)
    except Exception as e:
        print('  purge deleted error:', e)

    # מיילים שמאיר ענה בג'ימייל ועדיין לא חוברו למייל שעליו ענו
    try:
        n = link_mail_replies(con)
        if n:
            print('  תשובות מייל שחוברו למייל המקורי: %d' % n)
    except Exception as e:
        print('  mail reply link error:', e)

    # שורות שנשארו תלויות בכרטיס שנמחק — כסף רפאים שנספר בסיכומים בלי שאף אחד רואה אותו.
    # רץ בכל עליית שרת, כי מיזוג או מחיקה יכולים ליצור אותן מחדש.
    try:
        gone = 0
        for t in ('pledges', 'parnes', 'prayers', 'donations', 'contacts_log', 'tasks',
                  'partners', 'transactions', 'building', 'donor_rules'):
            try:
                gone += con.execute("DELETE FROM %s WHERE donor_id IS NOT NULL "
                                    "AND donor_id NOT IN (SELECT id FROM donors)" % t).rowcount
            except Exception:
                pass
        for t in ('recon', 'intake'):
            try:
                con.execute("UPDATE %s SET donor_id=NULL WHERE donor_id IS NOT NULL "
                            "AND donor_id NOT IN (SELECT id FROM donors)" % t)
            except Exception:
                pass
        if gone:
            print('  שורות יתומות שנוקו: %d' % gone)
    except Exception as e:
        print('  orphan cleanup error:', e)

    # 058-453-0710 יושב באנשי הקשר גם על "מזכיר מבט דייטש" וגם על משה דויטש,
    # וכך הוא נדבק לכרטיס התורם. הוא יורד משם ונרשם כנדחה כדי שלא יחזור.
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='deutch_phone_v1'").fetchone():
            BAD = '058-453-0710'
            r = con.execute("SELECT id,phone FROM donors WHERE last='דויטש' "
                            "AND first LIKE 'משה%'").fetchone()
            if r:
                keep = ' / '.join(x.strip() for x in re.split(r'[;,/]+', r['phone'] or '')
                                  if x.strip() and _ph10(x) != _ph10(BAD))
                con.execute("UPDATE donors SET phone=? WHERE id=?", (keep, r['id']))
                con.execute("INSERT INTO sugg_reject(donor_id,kind,val,created) "
                            "VALUES(?,'phone',?,?)", (r['id'], BAD, today_iso()))
                # המספר הנכון, לפי איש הקשר "משה דויטש" שמאיר הראה
                con.execute("UPDATE donors SET phone='+1 814-440-8103' WHERE id=? "
                            "AND TRIM(COALESCE(phone,''))=''", (r['id'],))
                print('  משה דויטש: הטלפון תוקן ל+1 814-440-8103')
            con.execute("INSERT INTO seed_flags(name) VALUES('deutch_phone_v1')")
    except Exception as ex:
        print('  deutch phone error:', ex)

    # תרומה שנוצרה מחיוב שנגבה בפועל היא כסף שכבר בקופה, ולכן חייבת להיות
    # מסומנת כשולמה. בלי זה היא נספרה כחוב פתוח והציפה את מסך החובות.
    try:
        n = con.execute("UPDATE donations SET paid=1 WHERE COALESCE(paid,0)=0 "
                        "AND (note LIKE 'נכנס מ%' OR note LIKE 'ייבוא %')").rowcount
        if n:
            con.commit()
            print('  תרומות שנגבו בפועל וסומנו כשולמו: %d' % n)
    except Exception as ex:
        print('  paid fix error:', ex)

    # "כרטיס #273 במערכת כולל חצות" — הערה טכנית שנכתבה בייצוא לאנשי הקשר
    # וחזרה פנימה בייבוא. היא רק חוזרת על מספר הכרטיס שכבר מופיע בראש
    # הכרטיס, ולכן יורדת. הערות אמיתיות באותה שורה נשמרות.
    # רץ בכל עלייה ולא פעם אחת: ההערה נכתבת על ידינו בייצוא לאנשי הקשר,
    # ולכן היא חוזרת בכל ייבוא חוזר. השאר בשורה נשמר כמו שהוא.
    try:
        rx = re.compile(r'^\s*כרטיס\s*#\d+\s*במערכת כולל חצות\s*$')
        n = 0
        for r in con.execute("SELECT id,notes FROM donors "
                             "WHERE notes LIKE '%במערכת כולל חצות%'").fetchall():
            parts = [x.strip() for x in re.split(r'\s+·\s+|\n', r['notes'] or '')]
            keep = ' · '.join(x for x in parts if x and not rx.match(x))
            if keep != (r['notes'] or ''):
                con.execute("UPDATE donors SET notes=? WHERE id=?", (keep, r['id']))
                n += 1
        if n:
            con.commit()
            print('  הערת "כרטיס # במערכת" שהוסרה מהכרטיסים: %d' % n)
    except Exception as ex:
        print('  card note cleanup error:', ex)

    # כרטיס נפתח רק באישור של מאיר, לא לבד. הכרטיסים שנפתחו אוטומטית
    # למפקידים בלי כרטיס נסגרים, וההפקדות חוזרות לרשימה "הפקדות שלא זוהו"
    # שם מאיר משייך לתורם קיים או מאשר לפתוח כרטיס חדש.
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='opencard_undo_v1'").fetchone():
            ids = [r['id'] for r in con.execute(
                "SELECT id FROM donors WHERE source='הפקדה בלי כרטיס'")]
            for did in ids:
                con.execute("UPDATE recon SET donor_id=NULL, processed=0 WHERE donor_id=?", (did,))
                for t in ('donations', 'pledges', 'parnes', 'prayers', 'contacts_log',
                          'tasks', 'partners', 'transactions', 'building', 'donor_rules',
                          'avreich_log', 'sugg_reject', 'addr_reject'):
                    try:
                        con.execute("DELETE FROM %s WHERE donor_id=?" % t, (did,))
                    except Exception:
                        pass
                con.execute("DELETE FROM donors WHERE id=?", (did,))
            con.execute("INSERT INTO seed_flags(name) VALUES('opencard_undo_v1')")
            if ids:
                print('  כרטיסים שנפתחו אוטומטית ונסגרו: %d' % len(ids))
    except Exception as ex:
        print('  open card undo error:', ex)

    # כסף שנכנס חייב להופיע בכרטיס התורם — גם אם עדיין לא ידוע עבור מה.
    # עד היום חיוב כזה חיכה ב"ממתין לטיפול" ולא נספר בכלל, ומאיר צדק שזה
    # הפוך: קודם רואים את הכסף, והייעוד הוא סימון משני שאפשר להשלים אחר כך.
    #
    # רץ בכל עלייה, ולא רק על מה שעדיין "ממתין": היו מסלולים שסימנו חיוב
    # כ"טופל" בלי לרשום תרומה (למשל כשלא הצליחו לפענח את התאריך), והכסף
    # נעלם מהכרטיס. בערי גולדגראב חויב 480 בכל חודש מפברואר ובכרטיס הופיעו
    # שלוש שורות בלבד. לכן הבדיקה היא מול התרומות עצמן, לא מול הסימון.
    # ההשוואה היא לפי תורם + חודש + מסלול תשלום, ולפי סכום כולל ולא שורה מול
    # שורה: תרומה שמאיר פיצל לכמה ייעודים משנה סכומים אבל לא את הסך, וכך היא
    # לא נספרת בטעות כחסרה. הפילוח למסלול נחוץ כי אותו תורם שולח באותו חודש
    # גם צ׳ק וגם זל וגם חיוב אשראי — כסף נפרד לגמרי. חסר בחודש מושלם
    # מהחיובים הגדולים לקטנים.
    try:
        SRCLBL = {'Banquest': 'בנק ווסט', 'Authorize': 'אוטרייז'}

        def _fam(s):
            s = (s or '').strip().lower()
            if 'banquest' in s or 'בנק ווסט' in s: return 'bq'
            if 'authorize' in s or 'אוטרייז' in s or 'אוטורייז' in s: return 'az'
            if 'chase' in s or "צ'ייס" in s or 'צייס' in s: return 'ch'
            return s

        pend = {}
        for r in con.execute("SELECT tid,donor_id,amount,date,source,category,processed FROM recon "
                             "WHERE donor_id IS NOT NULL AND COALESCE(skipped,0)=0 "
                             "AND (status IS NULL OR status='settled') ORDER BY date,tid"):
            iso = _recon_iso(r['date']) or (r['date'] or '')[:10]
            if not iso or len(iso) < 7:
                continue
            try:
                amt = round(float(str(r['amount'] or 0).replace(',', '').replace('$', '')), 2)
            except Exception:
                continue
            if amt > 0:
                pend.setdefault((r['donor_id'], iso[:7], _fam(r['source'])), []).append((dict(r), iso, amt))
        paid_by = {}
        # החזרים (סכום שלילי) אינם נספרים בשני הצדדים, אחרת חודש עם החזר
        # נראה חסר וכל עלייה מוסיפה בו עוד שורה
        for r in con.execute("SELECT donor_id, SUBSTR(COALESCE(date,''),1,7) mo, method, "
                             "ROUND(CAST(amount AS REAL),2) a FROM donations "
                             "WHERE donor_id IS NOT NULL AND CAST(amount AS REAL)>0"):
            k = (r['donor_id'], r['mo'], _fam(r['method']))
            paid_by[k] = round(paid_by.get(k, 0) + (r['a'] or 0), 2)
        n = 0
        for key, lst in pend.items():
            gap = round(sum(a for _, _, a in lst) - paid_by.get(key, 0), 2)
            for r, iso, amt in sorted(lst, key=lambda x: -x[2]):
                # אותו תורם, אותו יום, אותו סכום — נחשב לאותו כסף. בדוחות יש
                # חיובים תאומים (אותו סכום, שניות הפרש) ואסור שיוכפלו בכרטיס.
                same = con.execute("SELECT 1 FROM donations WHERE donor_id=? AND date=? "
                                   "AND ROUND(CAST(amount AS REAL),2)=?",
                                   (r['donor_id'], iso, amt)).fetchone()
                if not same and gap >= amt - 0.01:
                    src = r['source'] or ''
                    meth = next((v for pre, v in SRCLBL.items() if src.startswith(pre)), src)
                    cat = (r['category'] or '').strip()
                    note = 'נכנס מ' + (meth or 'ייבוא')
                    if not cat:
                        note += ' · לא סווג — לבדוק עבור מה'
                    con.execute("INSERT INTO donations(donor_id,date,amount,category,method,note,paid) "
                                "VALUES(?,?,?,?,?,?,1)",
                                (r['donor_id'], iso, '%.2f' % amt, cat, meth, note))
                    gap = round(gap - amt, 2); n += 1
                if not r.get('processed'):
                    con.execute("UPDATE recon SET processed=1 WHERE tid=?", (r['tid'],))
        if n:
            con.commit()
            print('  חיובים שנכנסו לכרטיסי התורמים: %d' % n)
    except Exception as ex:
        print('  post pending error:', ex)
    # יצחק רוזנפלד: נעימי מרדכי מוחזק בשותפות עם יהושע רוזנפלד — חלקו 500
    # ולא 1000. אבלסון מאיר נשאר 1000. סך יששכר־זבולון שלו: 1500 לחודש.
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='yrosenfeld_share_v1'").fetchone():
            r = con.execute("SELECT id FROM donors WHERE last='רוזנפלד' AND first='יצחק'").fetchone()
            if r:
                n = con.execute("UPDATE partners SET amount='500' WHERE donor_id=? "
                                "AND avreich LIKE '%נעימי%'", (r['id'],)).rowcount
                if n:
                    print('  יצחק רוזנפלד: נעימי מרדכי — 500 (שותפות עם יהושע רוזנפלד)')
            con.execute("INSERT INTO seed_flags(name) VALUES('yrosenfeld_share_v1')")
    except Exception as ex:
        print('  rosenfeld share error:', ex)

    # בערי גולדגראב: ההתחייבות נרשמה כסכום כל החודשים יחד (7 × 480),
    # ולכן החוב יצא פי שבעה. ההתחייבות היא 480 לחודש.
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='goldgrab_amt_v1'").fetchone():
            r = con.execute("SELECT id,amount FROM donors WHERE last='גולדגראב' "
                            "AND first='בערי'").fetchone()
            if r and str(r['amount']).strip() == '3360':
                con.execute("UPDATE donors SET amount='480' WHERE id=?", (r['id'],))
                print('  בערי גולדגראב: הסכום הקבוע תוקן מ-3360 ל-480 לחודש')
            con.execute("INSERT INTO seed_flags(name) VALUES('goldgrab_amt_v1')")
    except Exception as ex:
        print('  goldgrab amount error:', ex)

    # זאב לאם הוא Steven Lamm — כך הוא רשום באנשי הקשר, עם אותו טלפון
    # (917-701-7148) שבכרטיס. אסתר לאם היא אדם אחר לגמרי, והשם האנגלי שלו
    # נדבק לכרטיס שלה בטעות בייבוא. חמשת התשלומים בקובץ הצ׳קים/דונרס נרשמו
    # על "Lamm, Steven" ולכן מעולם לא הגיעו לכרטיס.
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='lamm_steven_v3'").fetchone():
            z = con.execute("SELECT id FROM donors WHERE last='לאם' AND first='זאב'").fetchone()
            e2 = con.execute("SELECT id FROM donors WHERE last='לאם' AND first='אסתר'").fetchone()
            if z:
                con.execute("UPDATE donors SET english='Steven Lamm' WHERE id=? "
                            "AND COALESCE(TRIM(english),'')=''", (z['id'],))
                con.execute("UPDATE donors SET email=? WHERE id=? AND COALESCE(TRIM(email),'')=''",
                            ('stevenlamm@yahoo.com / slamm@goldentree.com / stevenlamm1@gmail.com',
                             z['id']))
                con.execute("UPDATE donors SET addr='1233 E 35 St', city='Brooklyn' "
                            "WHERE id=? AND COALESCE(TRIM(addr),'')=''", (z['id'],))
                # הייעודים לפי מה שמאיר מסר
                PAY = [('2026-01-07', '12000', 'דונרס', 'יששכר־זבולון — שנה מראש'),
                       ('2026-02-10', '1500', "צ'ק", 'הכנסת כלה — הרב קוריץ'),
                       ('2026-03-04', '360', 'דונרס', 'מתנות לאביונים תשפ"ו'),
                       ('2026-03-26', '1100', "צ'ק", 'קמחא דפסחא תשפ"ו'),
                       ('2026-06-11', '1800', 'דונרס', 'הכנסת כלה — רובינפלד')]
                n = mv = 0
                for dt, amt, meth, cat in PAY:
                    if con.execute("SELECT 1 FROM donations WHERE donor_id=? AND date=? "
                                   "AND CAST(amount AS REAL)=?",
                                   (z['id'], dt, float(amt))).fetchone():
                        continue
                    # התשלום כבר נכנס בטעות לכרטיס של אסתר (בגלל השם האנגלי
                    # שנדבק לה) — מעבירים אותו, לא יוצרים אחד חדש
                    if e2:
                        r0 = con.execute("SELECT id FROM donations WHERE donor_id=? AND date=? "
                                         "AND CAST(amount AS REAL)=?",
                                         (e2['id'], dt, float(amt))).fetchone()
                        if r0:
                            con.execute("UPDATE donations SET donor_id=?, category=COALESCE(NULLIF(?,''),category) "
                                        "WHERE id=?", (z['id'], cat, r0['id']))
                            mv += 1
                            continue
                    note = 'Lamm, Steven — מקובץ הצ׳קים/דונרס'
                    if not cat:
                        note += ' · לא סווג — לבדוק עבור מה'
                    con.execute("INSERT INTO donations(donor_id,date,amount,category,method,note,paid) "
                                "VALUES(?,?,?,?,?,?,1)", (z['id'], dt, amt, cat, meth, note))
                    n += 1
                if n or mv:
                    print('  זאב לאם = Steven Lamm: הועברו %d תשלומים, נוספו %d' % (mv, n))
            if z:
                # ה-$12,000 הם יששכר־זבולון לשנה מראש מינואר 2026, ולכן אין
                # לו חוב חודשי עד סוף השנה. מסמנים "שולם עד" אצל האברך.
                con.execute("UPDATE partners SET paid_thru='2026-12', paid_note=? "
                            "WHERE donor_id=? AND COALESCE(active,1)<>0 "
                            "AND COALESCE(TRIM(paid_thru),'')=''",
                            ('שילם שנה מראש — $12,000 בדונרס, 7 בינואר 2026', z['id']))
                # הייעודים האלה נכנסים לרשימת הייעודים כדי שיהיו זמינים לכולם
                for cnm in ('יששכר־זבולון — שנה מראש', 'הכנסת כלה', 'מתנות לאביונים תשפ"ו',
                            'קמחא דפסחא תשפ"ו'):
                    con.execute("INSERT OR IGNORE INTO campaigns(name,created) VALUES(?,?)",
                                (cnm, today_iso()))
            if e2:      # השם האנגלי של זאב שנדבק לכרטיס של אסתר
                con.execute("UPDATE donors SET english='' WHERE id=? "
                            "AND lower(TRIM(english))='steven lamm'", (e2['id'],))
            con.execute("INSERT INTO seed_flags(name) VALUES('lamm_steven_v3')")
    except Exception as ex:
        print('  lamm steven error:', ex)
    # כתובת שנגמרת במספר תלוש ("1241 E 28th St 4626") — הכלל הזה חדש, ולכן
    # כתובות שאושרו קודם כ"תקין" נבדקות שוב פעם אחת. אי אפשר לשלוח לשם דואר.
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='addr_tail_num_v1'").fetchone():
            rx = re.compile(r'(st|ave|avenue|rd|road|blvd|dr|drive|ln|lane|ct|court|pl|'
                            r'place|way|ter|terrace|pkwy|hwy)\.?\s+\d{3,}\s*$', re.I)
            n = 0
            for r in con.execute("SELECT id,addr FROM donors WHERE COALESCE(addr_ok,0)=1"):
                if rx.search((r['addr'] or '').split(',')[0].strip()):
                    con.execute("UPDATE donors SET addr_ok=0 WHERE id=?", (r['id'],))
                    n += 1
            con.execute("INSERT INTO seed_flags(name) VALUES('addr_tail_num_v1')")
            if n:
                print('  כתובות עם מספר תלוש שהוחזרו לתיקון: %d' % n)
    except Exception as e:
        print('  addr tail error:', e)
    # "דוב / פרכטר יעקב" — השם נחתך במקום הלא נכון בייבוא. שם המשפחה הוא
    # פרכטר והפרטי יעקב דוב, בדיוק כמו בכרטיס השני שלו.
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='frechter_name_v1'").fetchone():
            n = con.execute("UPDATE donors SET last='פרכטר', first='יעקב דוב' "
                            "WHERE last='דוב' AND first LIKE 'פרכטר%'").rowcount
            con.execute("INSERT INTO seed_flags(name) VALUES('frechter_name_v1')")
            if n:
                print('  פרכטר יעקב דוב: השם סודר (%d)' % n)
    except Exception as e:
        print('  frechter name error:', e)
    # שורות שנכנסו לקוויטל מתוך הערה טכנית ("כרטיס #452 במערכת כולל חצות") —
    # אלה לא שמות לתפילה, ואסור שיודפסו בקוויטל.
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='prayer_sysline_v1'").fetchone():
            n = 0
            for r in con.execute("SELECT id,text FROM prayers WHERE text LIKE '%במערכת כולל חצות%'"):
                keep = [l for l in (r['text'] or '').split('\n')
                        if not re.match(r'^\s*כרטיס\s*#?\d+\s*במערכת', l)]
                new = '\n'.join(x for x in keep if x.strip()).strip()
                if new != (r['text'] or ''):
                    if new:
                        con.execute("UPDATE prayers SET text=? WHERE id=?", (new, r['id']))
                    else:
                        con.execute("DELETE FROM prayers WHERE id=?", (r['id'],))
                    n += 1
            con.execute("INSERT INTO seed_flags(name) VALUES('prayer_sysline_v1')")
            if n:
                print('  שורות טכניות שהוסרו מהקוויטל: %d' % n)
    except Exception as e:
        print('  prayer sysline error:', e)
    # מאיר ביקש לא לקבוע מטבע לתורמים קיימים: יש מי שגר בארץ ותורם בדולרים,
    # ויש מספר ישראלי אצל תורם מברוקלין. הזיהוי האוטומטי חל רק על כרטיס חדש,
    # ובכל כרטיס אפשר להחליף מטבע בלחיצה. כאן מבטלים את הסימון שנעשה קודם.
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='region_il_undo_v1'").fetchone():
            n = con.execute("UPDATE donors SET region='' WHERE region='il'").rowcount
            con.execute("INSERT INTO seed_flags(name) VALUES('region_il_undo_v1')")
            if n:
                print('  סימון ארץ ישראל בוטל אצל %d תורמים (חוזרים לדולרים)' % n)
    except Exception as e:
        print('  region undo error:', e)
    # תעודות מעודכנות שמאיר שלח: מיטמן (שלושת האחים שרשומים עליה), האסט,
    # וטאובנפלד. נתלות לצד התעודה הישנה — לא מוחקות אותה.
    try:
        NEW = [('cert_mittman.pdf', "מיטמן — תעודה מעודכנת",
                ["SELECT id FROM donors WHERE last LIKE 'מיטמן%' AND first IN "
                 "('אפרים','מאיר','גבריאל')"]),
               ('cert_host.pdf', "האסט — תעודה מעודכנת",
                ["SELECT id FROM donors WHERE last LIKE 'האסט%' OR last LIKE 'הסט%'"]),
               ('cert_taubenfeld.pdf', "טאובנפלד — תעודה מעודכנת",
                ["SELECT id FROM donors WHERE last LIKE 'טאובנפלד%'"])]
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='certs_new_v1'").fetchone():
            tot = 0
            for fn, nm, qs in NEW:
                fp = os.path.join(HERE, fn)
                if not os.path.exists(fp):
                    continue
                data = open(fp, 'rb').read()
                name = 'תעודת יששכר־זבולון — %s.pdf' % nm
                for q in qs:
                    for r in list(con.execute(q)):
                        if con.execute("SELECT 1 FROM files WHERE kind='iz' AND ref_id=? AND name=?",
                                       (r['id'], name)).fetchone():
                            continue
                        con.execute("INSERT INTO files(kind,ref_id,name,mime,data,created) "
                                    "VALUES('iz',?,?,'application/pdf',?,?)",
                                    (r['id'], name, data, today_iso()))
                        tot += 1
            con.execute("INSERT INTO seed_flags(name) VALUES('certs_new_v1')")
            print('  תעודות מעודכנות שנתלו: %d' % tot)
    except Exception as e:
        print('  שגיאת תעודות מעודכנות:', e)
    # תעודת "כולל הוראה" של שמשון פינטער — 24 אברכים, $500 לכל אחד. זו
    # שותפות נפרדת מהיששכר־זבולון שלו בכולל חצות, ולכן היא נתלית פעמיים:
    # בדף התורם הראשי ובדף היששכר־זבולון שלו.
    try:
        pf = os.path.join(HERE, 'pinter_horaa.pdf')
        if (not con.execute("SELECT 1 FROM seed_flags WHERE name='pinter_horaa_v1'").fetchone()
                and os.path.exists(pf)):
            r = con.execute("SELECT id FROM donors WHERE last LIKE 'פינט%' AND first='שמשון'").fetchone()
            if r:
                data = open(pf, 'rb').read()
                nm = 'תעודת יששכר־זבולון — כולל הוראה.pdf'
                for k in ('donor', 'iz'):
                    if not con.execute("SELECT 1 FROM files WHERE kind=? AND ref_id=? AND name=?",
                                       (k, r['id'], nm)).fetchone():
                        con.execute("INSERT INTO files(kind,ref_id,name,mime,data,created) "
                                    "VALUES(?,?,?,'application/pdf',?,?)",
                                    (k, r['id'], nm, data, today_iso()))
                print('  שמשון פינטער: תעודת כולל הוראה נתלתה בכרטיס וביששכר־זבולון')
            con.execute("INSERT INTO seed_flags(name) VALUES('pinter_horaa_v1')")
    except Exception as e:
        print('  שגיאת תעודת פינטער:', e)
    # תעודות יששכר־זבולון: מאיר פיצל אותן לעמוד לכל תורם, ואנחנו תולים כל
    # תעודה בכרטיס שכתוב עליה. השיוך נעשה לפי השם ולא לפי מספר כרטיס, כדי
    # שיתאים גם לכרטיסים שנוספו מאז. תעודה שכבר תלויה לא נתלית פעמיים.
    try:
        mp = os.path.join(HERE, 'iz_certs_map.json')
        pdfp = os.path.join(HERE, 'iz_certs.pdf')
        if (not con.execute("SELECT 1 FROM seed_flags WHERE name='iz_certs_v10'").fetchone()
                and os.path.exists(mp) and os.path.exists(pdfp)):
            try:
                from pypdf import PdfReader, PdfWriter
            except Exception:
                PdfReader = None
                print('  תעודות יששכר־זבולון: pypdf לא מותקן — מדלגים')
            if PdfReader:
                mm = json.load(open(mp, encoding='utf-8'))
                rd = PdfReader(pdfp)
                bylast = {}
                for r in con.execute("SELECT id,last,first FROM donors"):
                    bylast.setdefault(_fz(r['last']), []).append((r['id'], r['first'] or ''))

                def _find(lastn, firstn):
                    """התאמה סלחנית: מאיר משנה שמות פרטיים בכרטיסים (משה אלטר
                    אפרים ← משה, מוטי ← מרדכי), ולכן אחרי התאמה מדויקת מנסים
                    מילה משותפת בשם הפרטי, ולבסוף שם משפחה יחיד במערכת."""
                    ex = by.get((_fz(lastn), _fz(firstn)), [])
                    if len(ex) == 1:
                        return ex[0]
                    # מפתח הדמיון מוריד אמות קריאה, ולכן שמות קצרים מתנגשים
                    # ("הורן" ו"אירני" הופכים שניהם ל"רנ"). בשמות כאלה לא
                    # מסתמכים על הדמיון בלבד — עדיף תעודה שממתינה מאשר תעודה
                    # שנתלית אצל האדם הלא נכון.
                    lk = _fz(lastn)
                    if len(lk) < 3:
                        return None
                    cand = bylast.get(lk, [])
                    if not cand:
                        return None
                    want = {_fz(w) for w in (firstn or '').split() if len(w) > 1}
                    ov = [i for i, f in cand
                          if want & {_fz(w) for w in f.split() if len(w) > 1}]
                    if len(ov) == 1:
                        return ov[0]
                    if len(cand) == 1:
                        return cand[0][0]
                    return None
                # תעודות שמאיר ביקש שלא ייכנסו — גם אם נתלו בהרצה קודמת
                for dp in mm.get('dropped', []):
                    con.execute("DELETE FROM files WHERE kind='iz' AND name=?",
                                ('תעודת יששכר־זבולון %02d.pdf' % dp,))
                by = {}
                for r in con.execute("SELECT id,last,first FROM donors"):
                    by.setdefault((_fz(r['last']), _fz(r['first'])), []).append(r['id'])
                nadd = nmiss = 0
                for x in mm.get('map', []):
                    did = _find(x['last'], x['first'])
                    if not did:
                        nmiss += 1; continue
                    ids = [did]
                    fname = 'תעודת יששכר־זבולון %02d.pdf' % x['page']
                    if con.execute("SELECT 1 FROM files WHERE kind='iz' AND ref_id=? AND name=?",
                                   (ids[0], fname)).fetchone():
                        continue
                    w = PdfWriter(); w.add_page(rd.pages[x['page'] - 1])
                    buf = io.BytesIO(); w.write(buf)
                    con.execute("INSERT INTO files(kind,ref_id,name,mime,data,created) "
                                "VALUES('iz',?,?,'application/pdf',?,?)",
                                (ids[0], fname, buf.getvalue(), today_iso()))
                    nadd += 1
                # אם נשארה תעודה שלא מצאה כרטיס (למשל שני כרטיסים באותו שם) —
                # לא נועלים, כדי שתיתלה לבד אחרי שהכרטיסים יאוחדו
                if not nmiss:
                    con.execute("INSERT INTO seed_flags(name) VALUES('iz_certs_v10')")
                print('  תעודות יששכר־זבולון: צורפו %d · לא זוהה כרטיס ל-%d' % (nadd, nmiss))
                # תזכורת ממוקדת — רק אצל מי שמאיר ביקש, לא אצל כולם
                for x in mm.get('reminders', []):
                    did2 = _find(x['last'], x['first'])
                    if not did2:
                        continue
                    ids = [did2]
                    if con.execute("SELECT 1 FROM tasks WHERE donor_id=? AND kind='cert'",
                                   (ids[0],)).fetchone():
                        continue
                    con.execute("INSERT INTO tasks(donor_id,due_date,kind,note,assignee) "
                                "VALUES(?,?,'cert',?,'')",
                                (ids[0], today_iso(), x.get('note') or 'לבדוק אם קיבל את התעודה'))
    except Exception as e:
        print('  שגיאת תעודות יששכר־זבולון:', e)
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
    # חיובים מאוטרייז/בנק ווסט שטרם אושרו — כדי לאשר אותם ישר מכרטיס התורם
    for d in donors: d['recon_pending'] = []
    try:
        for r in c.execute("""SELECT tid,first,last,amount,date,source,category,recurring,donor_id FROM recon
                              WHERE COALESCE(processed,0)=0 AND donor_id IS NOT NULL
                                AND (status IS NULL OR status='settled')"""):
            if r['donor_id'] in byid:
                byid[r['donor_id']]['recon_pending'].append(dict(r))
    except Exception:
        pass
    # חיובים שלא עברו. כרטיס שנדחה ואז נגבה בהצלחה אינו חוב — זה ניסיון
    # חוזר שהצליח. לכן כל דחייה נבדקת מול כסף שנכנס באותו סכום: בתוך
    # שבועיים ממנה, או בכל מקום באותו חודש לועזי (גם צ׳ק או זל, לא רק
    # חיוב חוזר בכרטיס). מה שלא כוסה — זה חוב אמיתי.
    for d in donors:
        d['declined'] = []
        d['declined_open'] = 0
    try:
        ok, okmon = {}, set()
        for r in c.execute("SELECT donor_id,amount,date FROM recon "
                           "WHERE donor_id IS NOT NULL AND COALESCE(status,'settled') IN ('settled','')"):
            iso = _recon_iso(r['date']) or (r['date'] or '')[:10]
            if iso:
                ok.setdefault((r['donor_id'], _amt2(r['amount'])), []).append(_days(iso))
                okmon.add((r['donor_id'], _amt2(r['amount']), iso[:7]))
        for r in c.execute("SELECT donor_id,amount,date FROM donations "
                           "WHERE donor_id IS NOT NULL AND CAST(amount AS REAL)>0"):
            iso = (r['date'] or '')[:10]
            if len(iso) >= 7:
                okmon.add((r['donor_id'], _amt2(r['amount']), iso[:7]))
                if len(iso) == 10:
                    ok.setdefault((r['donor_id'], _amt2(r['amount'])), []).append(_days(iso))
        for r in c.execute("SELECT tid,first,last,amount,date,source,status,donor_id,"
                           "COALESCE(no_debt,0) no_debt, COALESCE(is_debt,0) is_debt FROM recon "
                           "WHERE donor_id IS NOT NULL "
                           "AND COALESCE(status,'settled') NOT IN ('settled','') "
                           "ORDER BY date DESC"):
            if r['donor_id'] not in byid:
                continue
            iso = _recon_iso(r['date']) or (r['date'] or '')[:10]
            dd = _days(iso)
            amt = _amt2(r['amount'])
            hit = [x for x in ok.get((r['donor_id'], amt), []) if dd and -3 <= x - dd <= 14]
            if not hit and iso and (r['donor_id'], amt, iso[:7]) in okmon:
                hit = [1]
            row = dict(r)
            row['date_iso'] = iso
            row['covered'] = 1 if (hit or r['no_debt']) else 0
            byid[r['donor_id']]['declined'].append(row)
            if not row['covered']:
                byid[r['donor_id']]['declined_open'] += 1
    except Exception:
        pass
    # תורמים ששולחים לבנק סכום אחד ומתחלקים בו — מוצג בשני הכרטיסים
    for d in donors: d['paysplit'] = []
    try:
        nm = {r['id']: ((r['last'] or '') + ' ' + (r['first'] or '')).strip()
              for r in c.execute("SELECT id,last,first FROM donors")}
        for r in c.execute("SELECT id,payer_id,donor_id,pct,note FROM pay_split"):
            pct = float(r['pct'] or 50)
            if r['payer_id'] in byid:
                byid[r['payer_id']]['paysplit'].append(
                    {'id': r['id'], 'role': 'payer', 'with_id': r['donor_id'],
                     'with': nm.get(r['donor_id'], ''), 'pct': pct, 'note': r['note'] or ''})
            if r['donor_id'] in byid:
                byid[r['donor_id']]['paysplit'].append(
                    {'id': r['id'], 'role': 'partner', 'with_id': r['payer_id'],
                     'with': nm.get(r['payer_id'], ''), 'pct': pct, 'note': r['note'] or ''})
    except Exception:
        pass
    for d in donors: d['unclassified'] = []
    try:
        # רק מה שבאמת עוד בלי ייעוד. קודם נבדקה ההערה בלבד, ולכן חיוב
        # שכבר סווג המשיך להופיע בחלון "בלי ייעוד" בכרטיס.
        for r in c.execute("SELECT id,donor_id,date,amount,method FROM donations "
                           "WHERE COALESCE(note,'') LIKE '%לא סווג%' "
                           "AND COALESCE(TRIM(category),'')='' ORDER BY date"):
            if r['donor_id'] in byid:
                byid[r['donor_id']]['unclassified'].append(dict(r))
    except Exception:
        pass

    for d in donors: d['rules'] = []
    try:
        for r in c.execute("SELECT id,donor_id,amount,category,note FROM donor_rules ORDER BY amount DESC"):
            if r['donor_id'] in byid:
                byid[r['donor_id']]['rules'].append(dict(r))
    except Exception:
        pass

    # בקשות קוויטל מהאתר שטרם צורפו — לאישור ישירות מכרטיס התורם
    for d in donors: d['intake_pending'] = []
    try:
        emap = {}
        for d in donors:
            for e in emails_of(d['email']):
                if e in emap and emap[e] != d['id']:
                    emap[e] = None          # כתובת אצל שני תורמים — לא משייכים לבד
                elif e not in emap:
                    emap[e] = d['id']
        for r in c.execute("""SELECT id,from_name,from_email,subject,received,names,donor_id FROM intake
                              WHERE COALESCE(status,'')<>'handled' AND COALESCE(TRIM(names),'')<>''"""):
            did = r['donor_id'] or emap.get((r['from_email'] or '').strip().lower())
            if did and did in byid:
                byid[did]['intake_pending'].append(dict(r))
    except Exception:
        pass
    for d in donors: d['files'] = []
    parnes_files, contact_files, task_files, don_files, tx_files = {}, {}, {}, {}, {}
    try:
        for r in c.execute("SELECT id,kind,ref_id,name,mime FROM files"):
            meta = {'id': r['id'], 'name': r['name'], 'mime': r['mime'], 'kind': r['kind'] or ''}
            # 'iz' — שטרי יששכר־זבולון · 'donor' — מסמכים בכרטיס הראשי
            if r['kind'] in ('iz', 'donor') and r['ref_id'] in byid:
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
                'region','country','zip','city','iz_note','iz_debt','debt_ok','debt_note','kv_skip','addr_ok','frequency','months','kv_month','kv_year'}

def norm_zip(z, region):
    """מיקוד ארה\"ב בן 4 ספרות איבד אפס מוביל — משלים ל-5 ספרות."""
    z = str(z or '').strip()
    if region != 'il' and re.fullmatch(r'\d{4}', z):
        return '0' + z
    return z

KIND_HE = {'charge': '💳 לחייב', 'parnes': '🌙 פרנס יום', 'prayer': '🙏 להתפלל',
           'followup': '📞 לחזור', 'other': '🔔 תזכורת'}

_MONI = {'jan': '01', 'feb': '02', 'mar': '03', 'apr': '04', 'may': '05', 'jun': '06',
         'jul': '07', 'aug': '08', 'sep': '09', 'oct': '10', 'nov': '11', 'dec': '12'}


def _hedate(d):
    """'2026-03-14' -> '14/03/2026' — כדי שהתאריך יהיה קריא בתוך טקסט המשימה."""
    m = re.match(r'(\d{4})-(\d{2})-(\d{2})', d or '')
    return '%s/%s/%s' % (m.group(3), m.group(2), m.group(1)) if m else (d or '')


def _recon_iso(d):
    """'24-Mar-2026' -> '2026-03-24'."""
    m = re.match(r'(\d{2})-([A-Za-z]{3})-(\d{4})', d or '')
    return f"{m.group(3)}-{_MONI.get(m.group(2).lower(), '01')}-{m.group(1)}" if m else ''


def _amt2(a):
    """סכום כמספר עגול לשתי ספרות — להשוואה בין חיוב שנדחה לחיוב שעבר."""
    try:
        return round(float(str(a or 0).replace(',', '').replace('$', '')), 2)
    except Exception:
        return 0.0


def _days(iso):
    """'2026-03-24' -> מספר ימים, להשוואת קרבה בין תאריכים."""
    try:
        y, mo, d = (iso or '')[:10].split('-')
        return datetime.date(int(y), int(mo), int(d)).toordinal()
    except Exception:
        return 0


_FZTAB = str.maketrans('ךםןףץשזצתכ', 'כמנפצססטטק')


def _fz(s):
    """מפתח דמיון לשמות עבריים — בלי אמות קריאה, ועם איחוד אותיות שנשמעות דומה
    (שטטפלד/סטטפלד, רוזנפלד/רוסנפלד). לאיתור כרטיס קיים למרות איות שונה."""
    s = re.sub(r'[^א-ת]', '', s or '').translate(_FZTAB)
    s = re.sub(r'[אהעוי]', '', s)
    return re.sub(r'(.)\1+', r'\1', s)


def _lat(s):
    return re.sub(r'\s+', ' ', re.sub(r'[^a-z ]', ' ', (s or '').lower())).strip()


def _d7(s):
    return re.sub(r'[^0-9]', '', s or '')[-7:]


def _same_first(a, b):
    """שם פרטי זהה, או שאחד מהם קיצור/הרחבה של השני (משה = משה אלטר אפרים)."""
    if not a or not b:
        return False
    if a == b or a.startswith(b + ' ') or b.startswith(a + ' '):
        return True
    return a.split()[0] == b.split()[0] and min(len(a.split()[0]), len(b.split()[0])) >= 3


def campaign_match(con, rows, dfrom='', dto=''):
    """מתאים כל שורה מרשימת מגבית לתורם קיים ולחיוב אשראי שטרם אושר.
    לא כותב כלום — רק מחזיר מה נמצא, כדי שאפשר יהיה לראות לפני שמכניסים."""
    donors = [dict(r) for r in con.execute("SELECT id,last,first,english,email,phone FROM donors")]
    by_mail, by_ph, by_name, by_last, by_lf = {}, {}, {}, {}, {}

    def put(d, key, val):
        if not key:
            return
        d[key] = None if (key in d and d[key] != val) else d.get(key, val)   # מפתח כפול — לא משייכים לבד

    for d in donors:
        for e in emails_of(d['email']):
            put(by_mail, e, d['id'])
        for p in re.split(r'[/,]', d['phone'] or ''):
            if _d7(p):
                put(by_ph, _d7(p), d['id'])
        heb = _norm((d['last'] or '') + ' ' + (d['first'] or '')).strip()
        put(by_name, heb, d['id'])
        for nm in {_lat(d['english']), _lat((d['first'] or '') + ' ' + (d['last'] or '')),
                   _lat((d['last'] or '') + ' ' + (d['first'] or ''))}:
            if nm and ' ' in nm:
                put(by_name, nm, d['id'])
                put(by_name, ' '.join(reversed(nm.split())), d['id'])
        for k in {_lat(d['last']), _norm(d['last'])}:
            put(by_last, k, d['id'])
        # שם משפחה -> כל התורמים בשם הזה, עם שמות פרטיים מנוקים מסוגריים
        fr = (d['first'] or '')
        alias = {_norm(re.sub(r'\(.*?\)', ' ', fr))}
        alias |= {_norm(x) for x in re.findall(r'\((.*?)\)', fr)}
        for lk in {_norm(d['last']), _lat(d['last'])}:
            if lk:
                by_lf.setdefault(lk, []).append((d['id'], {a for a in alias if a}))
    charges = {}
    for r in con.execute("""SELECT tid,donor_id,amount,date,source FROM recon
                            WHERE donor_id IS NOT NULL AND COALESCE(processed,0)=0"""):
        iso = _recon_iso(r['date'])
        if (dfrom and iso and iso < dfrom) or (dto and iso and iso > dto):
            continue
        charges.setdefault(r['donor_id'], []).append(
            {'tid': r['tid'], 'amount': round(float(r['amount'] or 0), 2), 'date': iso, 'source': r['source'] or ''})
    used = set()
    out = []
    for r in rows:
        name = (r.get('name') or '').strip()
        try:
            amt = round(float(re.sub(r'[^0-9.\-]', '', str(r.get('amount') or '0')) or 0), 2)
        except ValueError:
            amt = 0.0
        did = how = None
        for e in emails_of(r.get('email')):
            if by_mail.get(e):
                did, how = by_mail[e], 'אימייל'; break
        if not did and _d7(r.get('phone')) and by_ph.get(_d7(r.get('phone'))):
            did, how = by_ph[_d7(r.get('phone'))], 'טלפון'
        if not did:
            for key, lbl in ((_lat(name), 'שם באנגלית'), (_norm(name), 'שם בעברית'),
                             (' '.join(reversed(_lat(name).split())), 'שם באנגלית (הפוך)')):
                if key and by_name.get(key):
                    did, how = by_name[key], lbl; break
        if not did:
            # שם משפחה + שם פרטי, כולל שם מקוצר/מורחב: "ברגר יצחק" = "ברגר יצחק (איצי)"
            nw = _norm(name).split()
            rl = _norm(r.get('last') or '') or (nw[0] if nw else '')
            rf = _norm(r.get('first') or '') or ' '.join(nw[1:])
            cands = by_lf.get(rl) or by_lf.get(_lat(r.get('last') or '')) or []
            if rl and rf and cands:
                hit = [c for c in cands if any(_same_first(a, rf) for a in c[1])]
                if len(hit) == 1:
                    did, how = hit[0][0], 'שם משפחה + שם פרטי'
            if not did and rl and not rf and len(cands) == 1:
                did, how = cands[0][0], 'שם משפחה בלבד'
        if not did:
            w = _lat(name).split() or _norm(name).split()
            for k in ([w[-1], w[0]] if w else []):
                if by_last.get(k):
                    did, how = by_last[k], 'שם משפחה בלבד'; break
        ch = None
        if did and amt:
            # מבין החיובים באותו סכום — הקרוב ביותר לתאריך המגבית
            cand = [c for c in charges.get(did, []) if c['tid'] not in used and abs(c['amount'] - amt) < 0.01]
            if cand:
                tgt = dto or dfrom
                cand.sort(key=lambda c: (abs(_days(c['date']) - _days(tgt)) if (tgt and c['date']) else 0,
                                         c['date']), reverse=not tgt)
                ch = cand[0]; used.add(ch['tid'])
        dn = next((d for d in donors if d['id'] == did), None)
        meth = (r.get('method') or '').strip()
        st = ('skip' if meth in ('Decline', 'טרם נגבה') else
              ('new' if not did else ('charged' if ch else 'nocharge')))
        out.append({'name': name, 'amount': amt, 'note': (r.get('note') or '').strip(),
                    'donor_id': did, 'how': how, 'method': meth,
                    'donor_name': ((dn['last'] or '') + ' ' + (dn['first'] or '')).strip() if dn else '',
                    'charge': ch, 'status': st})
    return out


def recon_apply(cur, tid, b):
    """אישור שורת חיוב אחת: יצירת/עדכון התורם, התרומה, המשימה והקוויטל.
    לא פותח ולא סוגר חיבור — כדי שאפשר יהיה לאשר קבוצה שלמה בבקשה אחת."""
    row = cur.execute("SELECT * FROM recon WHERE tid=?", (tid,)).fetchone()
    if not row:
        return (404, {'error': 'not found'})
    if b.get('skip') or (row['status'] and row['status'] != 'settled'):
        cur.execute("UPDATE recon SET processed=1, skipped=1 WHERE tid=?", (tid,))
        return (200, {'ok': True, 'skipped': True})
    did = b.get('donor_id')
    r_state = row['state'] or ''         # מדינה (NY וכו') נשמרת בשדה "מדינה"
    r_src = 'Banquest' if 'Banquest' in (row['source'] or '') else 'Authorize'
    if b.get('new_donor'):
        nd = b['new_donor']
        # מזדמן → הקוויטל מזדמן, עם חודש/שנה (ברירת מחדל: החודש הנוכחי, ומכ' בחודש — הבא)
        _occ = bool(nd.get('occasional'))
        _dcat = (nd.get('category') or '').strip() or ('מזדמן' if _occ else b.get('category', ''))
        _kvm, _kvy = ((nd.get('kv_month') or ''), (nd.get('kv_year') or '')) if _occ else ('', '')
        if _occ and not _kvm:
            _kvm, _kvy = kvittel_default_month()
        cur.execute("""INSERT INTO donors(last,first,english,phone,email,addr,city,country,zip,category,created,source,notes,tier,kv_month,kv_year)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (nd.get('last', ''), nd.get('first', ''), (row['first'] + ' ' + row['last']).strip(),
                     row['phone'], row['email'], row['addr'] or '', row['city'] or '', r_state, row['zip'] or '',
                     _dcat, today_iso(), r_src, nd.get('notes', ''),
                     ('' if _occ else (nd.get('tier') or '')), _kvm, _kvy))
        did = cur.lastrowid
        # שאר החיובים של אותו אדם (אותו מייל) — משויכים מיד לכרטיס החדש
        _em = (row['email'] or '').strip().lower()
        if _em:
            cur.execute("""UPDATE recon SET donor_id=? WHERE lower(TRIM(email))=?
                           AND TRIM(COALESCE(email,''))<>'' AND donor_id IS NULL""", (did, _em))
        if (nd.get('task') or '').strip() and not (b.get('task') or '').strip():
            cur.execute("INSERT INTO tasks(donor_id,due_date,kind,note) VALUES(?,?,?,?)",
                        (did, (nd.get('task_date') or today_iso()), 'followup', nd['task'].strip()))
    if not did:
        return (400, {'error': 'donor required'})
    # מילוי אוטומטי של שם אנגלי אם חסר בכרטיס (מיזוג השם מהייבוא)
    if not b.get('new_donor'):
        en = (row['first'] + ' ' + row['last']).strip()
        if en:
            cur.execute("UPDATE donors SET english=? WHERE id=? AND COALESCE(TRIM(english),'')=''", (en, did))
    if b.get('update_addr') and (row['addr'] or row['city'] or row['zip']):
        cur.execute("UPDATE donors SET addr=?, city=?, country=?, zip=? WHERE id=?",
                    (row['addr'] or '', row['city'] or '', r_state, row['zip'] or '', did))
    # משימה שנכתבה בדף החיובים / בכרטיס — נכנסת ללשונית המשימות
    _tk = (b.get('task') or '').strip()
    if _tk:
        cur.execute("INSERT INTO tasks(donor_id,due_date,kind,note,assignee) VALUES(?,?,?,?,?)",
                    (did, (b.get('task_date') or today_iso()), (b.get('task_kind') or 'followup'),
                     _tk, (b.get('task_who') or '')))
    # הערה שנכתבה בדף החיובים — נשמרת גם בהערות התורם (ניתן לחיפוש)
    unote = (b.get('note') or '').strip()
    if unote and b.get('note_to_donor'):
        cur2 = cur.execute("SELECT notes FROM donors WHERE id=?", (did,)).fetchone()
        old = (cur2['notes'] if cur2 else '') or ''
        if unote not in old:
            cur.execute("UPDATE donors SET notes=? WHERE id=?",
                        ((old + ' · ' + unote).strip(' ·') if old.strip() else unote, did))
    # שמות הקוויטל שהתורם שלח מהאתר — צירוף לכרטיס שלו
    kvt = (b.get('kv_text') or '').strip()
    if b.get('attach_kv') and kvt:
        dt = cur.execute("SELECT tier FROM donors WHERE id=?", (did,)).fetchone()
        have = set()
        for p in cur.execute("SELECT text FROM prayers WHERE donor_id=?", (did,)):
            for _l in (p['text'] or '').split('\n'):
                if kv_key(_l):
                    have.add(kv_key(_l))
        for ln in [l.strip() for l in kvt.split('\n') if l.strip()]:
            if kv_key(ln) not in have:      # בלי כפילויות — השוואה בלי פיסוק ומקפים
                cur.execute("INSERT INTO prayers(donor_id,name,text,tier) VALUES(?,'',?,?)",
                            (did, ln, (dt['tier'] if dt else '') or ''))
                have.add(ln)
        _dr = cur.execute("SELECT email FROM donors WHERE id=?", (did,)).fetchone()
        _ems = emails_of(row['email']) + [e for e in emails_of(_dr['email'] if _dr else '')]
        _ems = list(dict.fromkeys(_ems))
        if _ems:
            cur.execute("UPDATE intake SET donor_id=?, status='handled' WHERE lower(TRIM(from_email)) IN (%s) AND COALESCE(donor_id,0)=0"
                        % ','.join('?' * len(_ems)), [did] + _ems)
    # תאריך: '01-Jul-2026' -> '2026-07'
    MON = {'Jan':'01','Feb':'02','Mar':'03','Apr':'04','May':'05','Jun':'06','Jul':'07','Aug':'08','Sep':'09','Oct':'10','Nov':'11','Dec':'12'}
    dm = re.match(r'(\d{2})-([A-Za-z]{3})-(\d{4})', row['date'] or '')
    # תאריך מלא (יום-חודש-שנה) ולא רק חודש — כדי שיוצג מתי בדיוק נגבה
    diso = f"{dm.group(3)}-{MON.get(dm.group(2),'01')}-{dm.group(1)}" if dm else ''
    cat = b.get('category', '') or row['category'] or ''
    if not cat and did:                       # אין בחירה — אולי יש כלל קבוע לסכום הזה אצל התורם
        _rr = cur.execute("SELECT category FROM donor_rules WHERE donor_id=? AND ROUND(amount,2)=?",
                          (did, round(float(row['amount'] or 0), 2))).fetchone()
        if _rr:
            cat = _rr['category'] or ''
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
    # יום פרנס נתפס רק כשנבחר יום בפועל. בלי בחירה מפורשת הכסף נרשם
    # כתרומה רגילה, ומאיר ישבץ את הלילה בעצמו בלוח — המערכת לא ממציאה
    # תאריך ולא "מתאמת" לילה מראש.
    if cat in PKIND and (b.get('date_text') or b.get('month')):
        # פרנס־יום (במקום תרומה רגילה) — נגבה, עם השמות והיום שנבחר בבורר
        dtext = b.get('date_text', '')
        # התאריך הלועזי לפי השנה העברית שנבחרה; רק אם אין שנה — המופע הקרוב
        _ng = (heb_greg_year(dtext, b.get('hyear', '')) or heb_to_greg(dtext)) if dtext else None
        cur.execute("INSERT INTO parnes(donor_id,day,month,date_text,amount,dedication,kind,status,paid,night_date,hyear,method) VALUES(?,?,?,?,?,?,?,'confirmed',1,?,?,?)",
                    (did, b.get('day', 0), b.get('month', ''), dtext, row['amount'], b.get('dedication', ''), PKIND[cat],
                     _ng.isoformat() if _ng else '', b.get('hyear', ''), pay_method))
    else:
        _nt = 'ייבוא ' + pay_method + (' · הוראת קבע' if row['recurring'] else '')
        _un = (b.get('note') or '').strip()      # הערה שנכתבה בדף החיובים
        if _un:
            _nt += ' · ' + _un
        cur.execute("INSERT INTO donations(donor_id,date,amount,category,method,note,paid) VALUES(?,?,?,?,?,?,1)",
                    (did, diso, row['amount'], cat, pay_method, _nt))
    if row['recurring']:
        cur.execute("UPDATE donors SET category='קבוע' WHERE id=? AND COALESCE(category,'')=''", (did,))
    # תזכורת לעשות את הלילה בפועל — נקבעת לפי תאריך הלילה עצמו, לא לפי מתי שולם.
    # (קודם היא נוצרה רק אם החיוב היה מאוגוסט ואילך, ולכן לילה שנקנה מראש נעלם)
    if cat in PKIND:
        dn = cur.execute("SELECT last, first FROM donors WHERE id=?", (did,)).fetchone()
        nm = ((dn['last'] + ' ' + (dn['first'] or '')).strip()) if dn else ''
        _dtext = b.get('date_text', '')
        if _dtext:
            _pdue = None
            _ngd = heb_greg_year(_dtext, b.get('hyear', '')) or heb_to_greg(_dtext)
            if _ngd:
                _pdue = (_ngd - datetime.timedelta(days=7)).isoformat()
            _pdue = _pdue or week_before(_dtext) or today_iso()
            if _pdue < today_iso(): _pdue = today_iso()   # שבוע-לפני כבר עבר (או שהלילה עצמו עבר) — להיום
            _note = '🌙 לעשות פרנס לילה — ' + nm
            if not cur.execute("SELECT 1 FROM tasks WHERE donor_id=? AND kind='parnes' AND note=? AND COALESCE(done,0)=0",
                               (did, _note)).fetchone():
                cur.execute("INSERT INTO tasks(donor_id,due_date,kind,note) VALUES(?,?,?,?)",
                            (did, _pdue, 'parnes', _note))
        else:
            # אושר בלי לבחור יום — שלא ייעלם בלי שנדע
            _note = '🌙 לקבוע יום לפרנס — ' + nm
            if not cur.execute("SELECT 1 FROM tasks WHERE donor_id=? AND kind='parnes' AND note=? AND COALESCE(done,0)=0",
                               (did, _note)).fetchone():
                cur.execute("INSERT INTO tasks(donor_id,due_date,kind,note) VALUES(?,?,?,?)",
                            (did, today_iso(), 'parnes', _note))
    # כלל קבוע: "כל $X של התורם הזה = הייעוד הזה" — נשמר, ומוחל גם על מה שכבר נרשם
    _rl = b.get('rule') or {}
    if _rl.get('apply') and did:
        _amt = round(float(row['amount'] or 0), 2)
        cur.execute("INSERT OR REPLACE INTO donor_rules(donor_id,amount,category,note,created) "
                    "VALUES(?,?,?,?,?)", (did, _amt, cat, (_rl.get('note') or '').strip(), today_iso()))
        _rn = (_rl.get('note') or '').strip()
        cur.execute("UPDATE donations SET category=? WHERE donor_id=? AND ROUND(CAST(amount AS REAL),2)=?",
                    (cat, did, _amt))
        if _rn:
            cur.execute("UPDATE donations SET note=COALESCE(note,'')||' · '||? "
                        "WHERE donor_id=? AND ROUND(CAST(amount AS REAL),2)=? AND COALESCE(note,'') NOT LIKE ?",
                        (_rn, did, _amt, '%' + _rn + '%'))
    cur.execute("UPDATE recon SET processed=1, donor_id=?, category=? WHERE tid=?", (did, cat, tid))
    return (200, {'ok': True, 'donor_id': did})

_KV_STRIP = str.maketrans('ךםןףץ', 'כמנפצ')


def kv_key(t):
    """מפתח השוואה לשם קוויטל — בלי פיסוק, מקפים, גרשיים ורווחים כפולים.
    כך 'בן נעמי - בראות' ו'בן נעמי בראות' נחשבים לאותו שם."""
    t = re.sub(r'[^֐-׿\s]', ' ', t or '')
    return re.sub(r'\s+', ' ', t.translate(_KV_STRIP)).strip()


def kv_words(line):
    """מילות השורה, בלי פיסוק — להשוואת דמיון בין שתי שורות קוויטל."""
    return [w for w in kv_key(line).split() if len(w) > 1]


def kv_same(a, b):
    """האם שתי שורות קוויטל מדברות על אותו אדם ואותה בקשה — גם אם הניסוח שונה קצת
    (מקפים, פסיקים, מילה חסרה, בן/בת שהוקלד הפוך)."""
    wa, wb = kv_words(a), kv_words(b)
    if not wa or not wb:
        return False
    if wa[0] != wb[0]:
        return False          # שם פרטי שונה — אנשים שונים, גם אם שאר השורה דומה
    sa, sb = set(wa), set(wb)
    shared = len(sa & sb)
    return shared >= 0.7 * min(len(sa), len(sb)) and shared >= 3


def dedupe_prayers(con):
    """מאחד את שמות הקוויטל של כל תורם למשבצת אחת (לכל דרגה) בלי שמות כפולים.
    כששם מופיע פעמיים — נשמר הנוסח המפורט יותר. מחזיר (בלוקים שנמחקו, בלוקים שאוחדו, תורמים)."""
    removed = merged = 0
    donors = set()
    rows = [dict(r) for r in con.execute(
        "SELECT id,donor_id,tier,text FROM prayers WHERE COALESCE(TRIM(text),'')<>'' ORDER BY id")]
    grp = {}
    for r in rows:
        grp.setdefault((r['donor_id'], (r['tier'] or '')), []).append(r)
    for (did, _tier), rs in grp.items():
        kept = []
        for r in rs:
            for ln in (r['text'] or '').split('\n'):
                ln = ln.rstrip()
                if not kv_key(ln):
                    continue
                hit = next((i for i, x in enumerate(kept) if kv_same(x, ln)), None)
                if hit is None:
                    kept.append(ln)
                elif len(kv_key(ln)) > len(kv_key(kept[hit])):
                    kept[hit] = ln        # אותו אדם — שומרים את הנוסח המפורט יותר
        text = '\n'.join(kept).strip()
        if not text:
            continue
        head, rest = rs[0], rs[1:]
        changed = text != (head['text'] or '').strip()
        if changed:
            con.execute("UPDATE prayers SET text=? WHERE id=?", (text, head['id']))
        for r in rest:
            con.execute("DELETE FROM prayers WHERE id=?", (r['id'],))
            removed += 1
        if changed or rest:
            donors.add(did)
            merged += 1
    return removed, merged, len(donors)


_CERT_CFG = {
    'parnes':    {'bg': 'letterhead.jpg',        'box': (0.25, 0.095, 0.95, 0.89)},
    'coffee':    {'bg': 'letterhead-coffee.jpg', 'box': (0.09, 0.24, 0.91, 0.79)},
    'breakfast': {'bg': 'letterhead-coffee.jpg', 'box': (0.09, 0.24, 0.91, 0.79)},
}
_CERT_SMALL = re.compile(
    r'^(בן|בת|בר|ב["\'״׳]ר|ובן|ובת|ז["\'״׳]ל|ע["\'״׳]ה|זצ["\'״׳]ל|זצוק["\'״׳]?ל|הי["\'״׳]ד|'
    r'נ["\'״׳]י|שליט["\'״׳]א|שיחי["\'״׳]?|שיחיו|תחי["\'״׳]?|ותחי["\'״׳]?|'
    r'הר["\'״׳]ר|הרר|הרב|רבי|ר["\'״׳]|מוה["\'״׳]ר|הרה["\'״׳][גחצ]|הגה["\'״׳]צ|מרן|'
    r'מרת|מר|האשה|הבחור|הבתולה|הילד|הילדה|הנער|הנערה|'
    r'אביו|אביה|אמו|אמה|בנו|בנה|בתו|בתה|אחיו|אחיה|אחותו|אחותה|זקנו|זקנתו|'
    r'חמיו|חמותו|בעלה|אשתו|נכדו|נכדתו|חתנו|כלתו|דודו|דודתו)$')
# מילת קרבה שנצמדת לפתיח — "לע\"נ אביו" יורד לשורה משלו
_CERT_REL = re.compile(
    r'^(אביו|אביה|אמו|אמה|בנו|בנה|בתו|בתה|אחיו|אחיה|אחותו|אחותה|זקנו|זקנתו|'
    r'חמיו|חמותו|בעלה|אשתו|נכדו|נכדתו|חתנו|כלתו|דודו|דודתו|הוריו|הוריה)$')
_DON_R = .85        # שם התורם ביחס לשם שמתפללים עליו
_SML_R = .42        # תארים, קרבה ומילות קישור
# היכן נגמר השם ומתחילה הבקשה. מכאן והלאה האותיות קטנות יותר, כדי שהשם
# ושם האם יקבלו את הדגש החזק ביותר בתעודה.
_REQ_R = .42        # גודל הבקשה ביחס לשם
_SPACE_R = .92      # רוחב הרווח בין המילים
# פתיח שבא לפני השם ("לעילוי נשמת אסתר בת יהושע") — רק הפתיח קטן, והשמות
# שאחריו גדולים. שונה מברכה שבאה אחרי השם ונמשכת עד הסוף.
_CERT_LEAD = re.compile(r'^(לעילוי|נשמת|לע["\'״׳]?נ|לזכר|לזכות|לרפואת|לרפו["\'״׳]?ש|'
                        r'להצלחת|לישועת|לפרנסת|לזרע|לברכת|לכבוד|לרגל)$')
_CERT_REQ = re.compile(
    r'^(ו?ל)(רפוא\w*|הצלח\w*|זיווג\w*|זרע\w*|פרנס\w*|ישוע\w*|ברכ\w*|נחת|חיים|בני\w*|'
    r'שלום|עילוי|זכר|כל|אריכ\w*|בריא\w*|שנה|כפרת|הרחב\w*|מזל|שידוך|בן|בת)$'
    r'|^(לע["\'״׳]?נ|לזכות|לזכר|לרגל|לכבוד)$')
def _cert_lines(text):
    """פיצול לשורות כמו בתצוגה שבמסך: שם התורם בשורה משלו, "לע\"נ אביו"
    בשורה משלו, והשמות שמתפללים עליהם בשורה האחרונה."""
    raws = str(text or '').split('\n')
    later_lead = any(i > 0 and (r.split() or [''])[0] and _CERT_LEAD.match(r.split()[0])
                     for i, r in enumerate(raws))
    out = []
    for idx, raw in enumerate(raws):
        ws = raw.split()
        if not ws:
            out.append(('', 'names')); continue
        ded = -1
        for k in range(1, len(ws)):
            if _CERT_LEAD.match(ws[k]):
                ded = k; break
        if ded > 0:                       # "הר\"ר רפאל לע\"נ אביו יוסף"
            out.append((' '.join(ws[:ded]), 'donor'))
            ws = ws[ded:]
        elif idx == 0 and later_lead and not _CERT_LEAD.match(ws[0]):
            out.append((' '.join(ws), 'donor')); continue
        if _CERT_LEAD.match(ws[0]):
            i = 0
            while i < len(ws) and _CERT_LEAD.match(ws[i]):
                i += 1
            j = i
            while j < len(ws) and _CERT_REL.match(ws[j]):
                j += 1
            if j > i and j < len(ws):
                out.append((' '.join(ws[:j]), 'lead'))
                out.append((' '.join(ws[j:]), 'names'))
                continue
        out.append((' '.join(ws), 'names'))
    return out


_DEEP = (0x6a, 0x14, 0x14)
_BLACK = (0, 0, 0)
_INK = (0x1c, 0x17, 0x10)


def _bidi(s):
    try:
        from bidi.algorithm import get_display
        return get_display(s)
    except Exception:
        return s


def cert_png(kind='parnes', date='', names='', dedic='', width=1000, fmt='png'):
    """מצייר את תעודת הפרנס כתמונה — אותו בלאנק, אותו סידור, גופן שמתאים את עצמו לדף."""
    from PIL import Image, ImageDraw, ImageFont
    try:
        from PIL import features as _pf
        raqm = bool(_pf.check('raqm'))     # מנוע הכתיבה שמסדר עברית מימין לשמאל בעצמו
    except Exception:
        raqm = False
    cfg = _CERT_CFG.get(kind) or _CERT_CFG['parnes']
    im = Image.open(os.path.join(STATIC, cfg['bg'])).convert('RGB')
    if im.width != width:
        im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
    W, H = im.size
    x0, y0 = int(cfg['box'][0] * W), int(cfg['box'][1] * H)
    x1, y1 = int(cfg['box'][2] * W), int(cfg['box'][3] * H)
    bw, bh = x1 - x0, y1 - y0
    reg = os.path.join(STATIC, 'frankruhl-regular.ttf')
    bold = os.path.join(STATIC, 'frankruhl-bold.ttf')
    cache = {}

    def font(px, heavy):
        k = (int(px), heavy)
        if k not in cache:
            cache[k] = ImageFont.truetype(bold if heavy else reg, max(6, int(px)))
        return cache[k]

    # כל בלוק: (טקסט, יחס-גודל, מודגש, צבע, רווח-לפני, רווח-אחרי, גובה-שורה)
    if kind in ('coffee', 'breakfast'):
        ded = dedic or ('ארוחת בוקר היום נתרמה לזכות' if kind == 'breakfast'
                        else 'הקפה החלב שתיה חמה ועוגיות נתרמו לזכות')
        blocks = [(date, 1.05, True, _DEEP, 0, .3, 1.35),
                  ('פרנס יום', 2.15, True, _DEEP, .06, .18, 1.2),
                  (ded, 1.18, True, _DEEP, 0, .28, 1.3),
                  (names, 2.35, True, _BLACK, .1, .25, 1.18)]
    else:
        blocks = [('יהי רצון שזכות הלימודים והתפילות הנעשים כאן בכולל חצות '
                   'בעת רצון הגדול של חצות הלילה עד הבוקר', 1.0, False, _INK, 0, 0, 1.45),
                  (date, 1.55, True, _DEEP, .5, .35, 1.3),
                  ('יהיו ויעמדו לזכות', 1.0, False, _INK, 0, .15, 1.35),
                  (names, 2.3, True, _BLACK, .15, .35, 1.14)]
    blocks = [b for b in blocks if (b[0] or '').strip()]

    def _join(items):
        """רווח בין מילים — צר בכוונה, כדי שהמילים לא ייראו מרוחקות זו מזו."""
        out = []
        for i, it in enumerate(items):
            if i:
                out.append((' ', min(items[i - 1][1], it[1]) * _SPACE_R, items[i - 1][2]))
            out.append(it)
        return out

    def sized(raw, px, heavy, role='names'):
        """כל מילה בשורה עם הגודל שלה: השם שמתפללים עליו הכי גדול, שם
        התורם קטן ממנו, ותארים/קרבה/בקשה הכי קטנים. הקביעה נעשית פעם אחת
        על השורה השלמה, כדי שהיא תישמר גם אחרי שבירת שורה."""
        ws = raw.split()
        if role == 'lead':                                  # "לע\"נ אביו"
            return [(w, px * _SML_R, True) for w in ws]
        if role == 'donor':                                 # שם התורם
            return [(w, px * (_SML_R if _CERT_SMALL.match(w) else _DON_R), True) for w in ws]
        i, out = 0, []
        while i < len(ws) and _CERT_LEAD.match(ws[i]):     # פתיח לפני השם
            out.append((ws[i], px * _SML_R, True)); i += 1
        inreq = False
        for w in ws[i:]:
            if not inreq and _CERT_REQ.match(w):           # ברכה אחרי השם
                inreq = True
            if inreq:
                out.append((w, px * _REQ_R, True))
            elif _CERT_SMALL.match(w):
                out.append((w, px * _SML_R, False))
            else:
                out.append((w, px, heavy))
        return out

    def wrap(text, px, heavy, dr):
        """שבירת שורות לרוחב התיבה, תוך שמירה על שורות שנכתבו במפורש."""
        lines = []
        for raw, role in _cert_lines(text):
            ws = sized(raw, px, heavy, role)
            if not ws:
                lines.append([]); continue
            cur = []
            for it in ws:
                trial = cur + [it]
                wpx = sum(dr.textlength(t, font=font(sz, h)) for t, sz, h in trial)
                wpx += dr.textlength(' ', font=font(px, heavy)) * (len(trial) - 1)
                if wpx <= bw or not cur:
                    cur = trial
                else:
                    lines.append(_join(cur)); cur = [it]
            if cur:
                lines.append(_join(cur))
        return lines

    dr = ImageDraw.Draw(im)

    def layout(base):
        total, out = 0.0, []
        for i, (txt, mult, heavy, col, mt, mb, lh) in enumerate(blocks):
            px = base * mult
            total += mt * base
            ls = wrap(txt, px, heavy, dr)
            for ln in ls:
                out.append((ln, px * lh, col, total))
                total += px * lh
            total += mb * base
        return total, out

    lo, hi, best = 4.0, 220.0, 4.0
    for _ in range(26):                      # חיפוש בינארי לגודל שממלא את הדף
        mid = (lo + hi) / 2
        if layout(mid)[0] <= bh:
            best, lo = mid, mid
        else:
            hi = mid
    total, items = layout(best)
    top = y0 + max(0, (bh - total) / 2)      # ממורכז אנכית בתיבה
    for ln, lheight, col, off in items:
        wpx = sum(dr.textlength(t, font=font(s, h)) for t, s, h in ln)
        x = x0 + (bw - wpx) / 2
        base_y = top + off + lheight * .78
        # PIL מסדר עברית מימין לשמאל בעצמו; לכן רק סדר המקטעים מתהפך — הראשון נכתב הכי ימינה
        for t, s, h in reversed(ln):
            f = font(s, h)
            dr.text((x, base_y), t if raqm else t[::-1], font=f, fill=col, anchor='ls')
            x += dr.textlength(t, font=f)
    buf = io.BytesIO()
    if fmt == 'jpg':
        im.save(buf, 'JPEG', quality=88, optimize=True, progressive=True)
    else:
        im.save(buf, 'PNG', compress_level=6)
    return buf.getvalue()


MERGE_HEB = {'donations': 'תרומות', 'prayers': 'שמות קוויטל', 'parnes': 'פרנס יום',
             'tasks': 'משימות', 'contacts_log': 'רישומי קשר', 'partners': 'אברכים',
             'transactions': 'חיובים', 'pledges': 'התחייבויות', 'recon': 'שורות חיוב',
             'building': 'בניין', 'intake': 'בקשות מהאתר'}


def merge_into(con, keep, drop):
    """מיזוג כרטיס כפול לתוך הכרטיס שנשאר. מחזיר מה עבר, או None אם אחד מהם לא קיים.
    לא דורס דבר: שדות ריקים מושלמים, טלפונים ואימיילים מתאחדים, הערות מתחברות."""
    if keep == drop:
        return None
    cur = con.cursor()
    k = cur.execute("SELECT * FROM donors WHERE id=?", (keep,)).fetchone()
    d = cur.execute("SELECT * FROM donors WHERE id=?", (drop,)).fetchone()
    if not k or not d:
        return None
    moved = {}
    for t in ('pledges', 'parnes', 'prayers', 'donations', 'contacts_log', 'tasks',
              'partners', 'transactions', 'building', 'recon', 'intake'):
        try:
            n = cur.execute("SELECT COUNT(*) FROM %s WHERE donor_id=?" % t, (drop,)).fetchone()[0]
            cur.execute("UPDATE %s SET donor_id=? WHERE donor_id=?" % t, (keep, drop))
            if n:
                moved[t] = n
        except Exception:
            pass
    try: cur.execute("UPDATE files SET ref_id=? WHERE kind='iz' AND ref_id=?", (keep, drop))
    except Exception: pass
    kd = dict(k); dd = dict(d); sets = []; vals = []
    for col in ('first', 'english', 'business', 'addr', 'tier', 'category', 'purpose',
                'amount', 'region', 'country', 'zip', 'city', 'channel', 'pay_status',
                'kv_month', 'kv_year', 'labels', 'aliases', 'iz_note', 'iz_debt',
                'debt_ok', 'debt_note', 'months', 'last_active'):
        if col in kd and not str(kd.get(col) or '').strip() and str(dd.get(col) or '').strip():
            sets.append("%s=?" % col); vals.append(dd[col])
    kp = [p.strip() for p in re.split(r'[/,]', kd.get('phone') or '') if p.strip()]
    for p in re.split(r'[/,]', dd.get('phone') or ''):
        p = p.strip()
        if p and p not in kp:
            kp.append(p)
    if ' / '.join(kp) != (kd.get('phone') or ''):
        sets.append("phone=?"); vals.append(' / '.join(kp))
    ke = emails_of(kd.get('email'))
    for e in emails_of(dd.get('email')):
        if e not in ke:
            ke.append(e)
    if ', '.join(ke) != (kd.get('email') or '').strip():
        sets.append("email=?"); vals.append(', '.join(ke))
    kn = (kd.get('notes') or '').strip(); dn = (dd.get('notes') or '').strip()
    if dn and dn not in kn:
        sets.append("notes=?"); vals.append((kn + ' · ' + dn).strip(' ·') if kn else dn)
    if sets:
        cur.execute("UPDATE donors SET " + ",".join(sets) + " WHERE id=?", vals + [keep])
    det = ', '.join('%d %s' % (v, MERGE_HEB.get(kk, kk)) for kk, v in moved.items()) or 'ללא רשומות'
    try:
        cur.execute("INSERT INTO contacts_log(donor_id,date,channel,summary) VALUES(?,?,?,?)",
                    (keep, today_iso(), 'מערכת',
                     ('🔀 מוזג לכאן הכרטיס הכפול #%d %s' % (drop, ((dd.get('last') or '') + ' ' +
                      (dd.get('first') or '')).strip())) + ' — ' + det))
    except Exception:
        pass
    cur.execute("DELETE FROM donors WHERE id=?", (drop,))
    return moved


def _he_alt(gi, s, j_as_yud=False):
    """תעתיק שם לועזי לעברית. באפשרות השנייה J בתחילת שם נכתב כ־י׳ ולא כ־ג׳ —
    כך Jacobsen מגיע ל'יעקבסון' ולא ל'ג׳קובסן'."""
    s = (s or '').strip()
    if j_as_yud and s[:1] in ('J', 'j'):
        s = 'Y' + s[1:]
    return gi._he_name(s)


TASK_HE = {'charge': 'לחייב', 'parnes': 'פרנס יום', 'prayer': 'לבקש שמות לקוויטל',
           'followup': 'להתקשר', 'email': 'אימייל / וואטסאפ', 'verify': 'לבדוק שנגבה',
           'card': 'לבדוק כרטיס', 'other': 'משימה'}


def task_kind_he(kind):
    """שם המשימה בעברית. סוג שמאיר הגדיר בעצמו נשמר כ־'c:שם הסוג'."""
    k = (kind or '').strip()
    if k[:2] == 'c:':
        return k[2:].strip() or 'משימה'
    return TASK_HE.get(k, 'משימה')


def task_text(kind, note):
    """תיאור המשימה לתיעוד — סוג המשימה, ולצידו מה שנכתב בה. אם הטקסט כבר
    כולל את שם הסוג ('להתקשר על הקוויטל') לא חוזרים עליו פעמיים."""
    txt = task_kind_he(kind)
    note = (note or '').strip()
    if not note:
        return txt
    return note if txt in note else (txt + ' — ' + note)


def task_done_log(cur, tid, done=True, by='', when=''):
    """סימון משימה כבוצעה — ושורת תיעוד בדף הקשר של התורם: מה נעשה, מתי, ובידי מי.
    ביטול הווי מוחק את אותה שורה, כדי שלא יישאר תיעוד על משהו שלא קרה."""
    try:
        t = cur.execute("SELECT * FROM tasks WHERE id=?", (int(tid),)).fetchone()
    except Exception:
        return None
    if not t:
        return None
    if not done:
        cur.execute("UPDATE tasks SET done=0, done_date='', done_by='', done_at='' WHERE id=?", (t['id'],))
        cur.execute("DELETE FROM contacts_log WHERE task_id=?", (t['id'],))
        return None
    # 'when' מגיע מהדפדפן בפורמט 'YYYY-MM-DD HH:MM' — השעה של מאיר, לא של השרת
    at = (when or '').strip() or now_iso()
    day = at[:10]
    who = (by or '').strip() or (t['assignee'] or '').strip() or 'מאיר'
    cur.execute("UPDATE tasks SET done=1, done_date=?, done_by=?, done_at=? WHERE id=?",
                (day, who, at, t['id']))
    if not t['donor_id']:
        return None
    if cur.execute("SELECT 1 FROM contacts_log WHERE task_id=?", (t['id'],)).fetchone():
        return None
    summary = '✓ בוצע: %s · ע"י %s' % (task_text(t['kind'], t['note']), who)
    cur.execute("INSERT INTO contacts_log(donor_id,date,channel,summary,next_date,task_id,at) "
                "VALUES(?,?,'משימה',?,'',?,?)", (t['donor_id'], day, summary, t['id'], at))
    return {'id': cur.lastrowid, 'donor_id': t['donor_id'], 'date': day, 'channel': 'משימה',
            'summary': summary, 'next_date': '', 'task_id': t['id'], 'at': at}


def task_log_sync(cur, tid):
    """משימה שכבר בוצעה ומאיר תיקן בה את הטקסט, הסוג או האחראי — הרישום בכרטיס
    התורם מתעדכן יחד איתה, כדי שלא יישאר שם נוסח ישן."""
    try:
        t = cur.execute("SELECT * FROM tasks WHERE id=?", (int(tid),)).fetchone()
    except Exception:
        return None
    if not t or not t['done'] or not t['donor_id']:
        return None
    c = cur.execute("SELECT * FROM contacts_log WHERE task_id=?", (t['id'],)).fetchone()
    if not c:
        return None
    who = (t['done_by'] or '').strip() or (t['assignee'] or '').strip() or 'מאיר'
    old = c['summary'] or ''
    sfx = ' (לפי תאריך היעד)' if old.endswith('(לפי תאריך היעד)') else ''
    summary = '✓ בוצע: %s · ע"י %s%s' % (task_text(t['kind'], t['note']), who, sfx)
    cur.execute("UPDATE contacts_log SET summary=? WHERE id=?", (summary, c['id']))
    return {'id': c['id'], 'donor_id': t['donor_id'], 'date': c['date'], 'channel': 'משימה',
            'summary': summary, 'next_date': c['next_date'] or '', 'task_id': t['id'],
            'at': c['at'] or ''}


def _nkey(s):
    """שם מפקיד כפי שהוא מגיע מהבנק — לנרמול להשוואה."""
    return re.sub(r'[^a-z0-9\u0590-\u05ff ]+', ' ', (s or '').lower()).strip()
    

def apply_name_map(con):
    """שם מפקיד שמאיר כבר שייך פעם אחת — כל השורות שלו נקשרות לבד, גם
    בייבוא הבא. שם שסומן 'לא רלוונטי' נשאר בצד ולא נשאל שוב."""
    n = 0
    try:
        rows = list(con.execute("SELECT src,donor_id,ignored FROM name_map"))
    except Exception:
        return 0
    for m in rows:
        if m['ignored'] or not m['donor_id']:
            continue
        for r in con.execute("SELECT tid,last,first FROM recon WHERE donor_id IS NULL"):
            # אותו סדר בדיוק כמו במסך ההפקדות (שם פרטי ואז משפחה), ולמען
            # מפתחות שנשמרו בעבר בסדר ההפוך — מקבלים גם אותו
            f, l = (r['first'] or '').strip(), (r['last'] or '').strip()
            keys = {_nkey(' '.join(x for x in (f, l) if x)),
                    _nkey(' '.join(x for x in (l, f) if x))}
            if m['src'] in keys:
                con.execute("UPDATE recon SET donor_id=? WHERE tid=?", (m['donor_id'], r['tid']))
                n += 1
    if n:
        con.commit()
    return n


def _dkey(last, first):
    """מפתח זהות של תורם למעקב אחרי מחיקות — בלי גרשיים ורווחים."""
    return (_fz(last or '') + '|' + _fz(first or '')).strip('|')


def purge_deleted(con):
    """תורם שמאיר מחק נשאר מחוק. אחת המיגרציות או ייבוא חוזר עלולים ליצור
    אותו מחדש בעליית השרת, ואז נראה כאילו המחיקה לא עבדה. הסריקה הזו מוחקת
    שוב כל כרטיס שנוצר בשם שכבר נמחק."""
    n = 0
    try:
        keys = {r['key'] for r in con.execute("SELECT key FROM deleted_donors")}
    except Exception:
        return 0
    if not keys:
        return 0
    for r in con.execute("SELECT id,last,first FROM donors").fetchall():
        if _dkey(r['last'], r['first']) not in keys:
            continue
        for t in ('pledges', 'parnes', 'prayers', 'donations', 'contacts_log', 'tasks',
                  'partners', 'transactions', 'building', 'donor_rules', 'avreich_log',
                  'sugg_reject', 'addr_reject'):
            try: con.execute("DELETE FROM %s WHERE donor_id=?" % t, (r['id'],))
            except Exception: pass
        for t in ('recon', 'intake'):
            try: con.execute("UPDATE %s SET donor_id=NULL WHERE donor_id=?" % t, (r['id'],))
            except Exception: pass
        try:
            con.execute("DELETE FROM donors WHERE id=?", (r['id'],)); n += 1
        except Exception:
            pass
    if n:
        con.commit()
    return n


def iz_log(cur, avreich, donor_id, text, at='', hd=''):
    """כל שינוי ביששכר־זבולון נרשם פעמיים: בדף הקשר של התורם, וביומן של
    האברך. בשתי הרשומות מופיעים גם התאריך הלועזי וגם העברי."""
    at = (at or '').strip() or now_iso()
    day = at[:10]
    hd = (hd or '').strip() or greg_to_heb_full(day)
    # אם התאריך העברי כבר מופיע בטקסט (למשל 'מא\' אלול תשפ"ו') לא כופלים אותו
    line = text if (hd and hd in text) else ('%s%s' % (text, (' · ' + hd) if hd else ''))
    if donor_id:
        try:
            cur.execute("INSERT INTO contacts_log(donor_id,date,channel,summary,next_date,at) "
                        "VALUES(?,?,'יששכר־זבולון',?,'',?)", (donor_id, day, line, at))
        except Exception:
            pass
    try:
        cur.execute("INSERT INTO avreich_log(avreich,donor_id,date,hdate,text,at) "
                    "VALUES(?,?,?,?,?,?)", (avreich, donor_id, day, hd, text, at))
    except Exception:
        pass


def _is_avreich(name):
    """שורות כמו "כולל יום" אינן אברך של יששכר־זבולון ולא שייכות לרשימה."""
    n = (name or '').strip()
    return bool(n) and 'כולל יום' not in n


def _split_av(name):
    """שם אברך נשמר כ"משפחה פרטי" — מפרידים כדי למיין לפי שם משפחה."""
    p = re.sub(r'\s+', ' ', (name or '').strip()).split(' ')
    return (p[0] if p else ''), (' '.join(p[1:]) if len(p) > 1 else '')


def _srt(s):
    """מיון עברי פשוט — בלי גרשיים ורווחים מיותרים."""
    return re.sub(r'["\u05f3\u05f4\'`]', '', (s or '').strip())


def apply_pay_split(con):
    """שני תורמים ששולחים לבנק סכום אחד ומתחלקים בו — למשל יצחק אדלין ואלירן
    דהאן, חצי־חצי. הכסף מגיע על שם אחד מהם, ולכן כל שורה שלו שטרם אושרה
    נחתכת לשתיים: חלקו נשאר אצלו, וחלקו עובר לכרטיס של השותף. שורה שכבר
    אושרה לא נוגעים בה, ושורה שכבר נחתכה (הסיומת #a/#b) לא נחתכת שוב."""
    try:
        splits = list(con.execute("SELECT payer_id,donor_id,pct FROM pay_split"))
    except Exception:
        return 0
    n = 0
    for s in splits:
        pct = float(s['pct'] or 50)
        if not (0 < pct < 100):
            continue
        rows = list(con.execute(
            "SELECT * FROM recon WHERE donor_id=? AND COALESCE(processed,0)=0 "
            "AND tid NOT LIKE '%#a' AND tid NOT LIKE '%#b'", (s['payer_id'],)))
        for r in rows:
            try:
                amt = float(str(r['amount'] or 0).replace(',', '').replace('$', ''))
            except Exception:
                continue
            if amt <= 0:
                continue
            other = round(amt * pct / 100.0, 2)
            mine = round(amt - other, 2)
            cols = [k for k in r.keys() if k != 'tid']
            for suf, did, val in (('#a', r['donor_id'], mine), ('#b', s['donor_id'], other)):
                vals = []
                for k in cols:
                    if k == 'donor_id':
                        vals.append(did)
                    elif k == 'amount':
                        vals.append('%.2f' % val)
                    elif k == 'category':
                        vals.append(((r['category'] or '') + ' · חצי מהעברה משותפת').strip(' ·'))
                    else:
                        vals.append(r[k])
                con.execute("INSERT OR IGNORE INTO recon(tid,%s) VALUES(?%s)"
                            % (','.join(cols), ',?' * len(cols)), [r['tid'] + suf] + vals)
            con.execute("DELETE FROM recon WHERE tid=?", (r['tid'],))
            n += 1
    if n:
        con.commit()
    return n


def _lev1(a, b):
    """האם שתי מחרוזות רחוקות זו מזו באות אחת לכל היותר (שגיאת הקלדה)."""
    if a == b:
        return True
    la, lb = len(a), len(b)
    if abs(la - lb) > 1:
        return False
    if la > lb:
        a, b, la, lb = b, a, lb, la
    i = 0
    while i < la and a[i] == b[i]:
        i += 1
    j = 0
    while j < la - i and a[la - 1 - j] == b[lb - 1 - j]:
        j += 1
    return i + j >= la


def link_near_names(con):
    """שם מפקיד שנכתב בבנק עם שגיאת הקלדה של אות אחת — למשל Rosenfed במקום
    Rosenfeld — נשאר ברשימת "לא זוהו" למרות שהכרטיס קיים. הסריקה הזו מחברת
    אותו, אבל רק כשיש מועמד יחיד ורק כשהשם הפרטי זהה, כדי לא לטעות."""
    def _ne(s): return re.sub(r'[^a-z0-9 ]', '', (s or '').lower()).strip()
    cands = []
    for d in con.execute("SELECT id,english,business FROM donors"):
        for v in (d['english'], d['business']):
            k = _ne(v)
            if len(k) >= 6:
                cands.append((k, d['id']))
    n = 0
    for r in con.execute("SELECT tid,first,last FROM recon WHERE donor_id IS NULL"):
        nm = _ne(((r['first'] or '') + ' ' + (r['last'] or '')).strip())
        if len(nm) < 6:
            continue
        hit = {did for k, did in cands
               if _lev1(k, nm) and k.split(' ')[0] == nm.split(' ')[0]}
        if len(hit) == 1:
            con.execute("UPDATE recon SET donor_id=? WHERE tid=?", (hit.pop(), r['tid']))
            n += 1
    if n:
        con.commit()
    return n


def link_by_identity(con):
    """משייך חיובים שנשארו בלי כרטיס — לפי מייל, לפי טלפון, ולבסוף לפי תעתיק השם
    הלועזי לעברית. רק התאמה יחידה וברורה מתקבלת; כל השאר נשאר לאישור ידני."""
    try:
        import gmail_intake as _gi
    except Exception:
        _gi = None
    donors = [dict(r) for r in con.execute(
        "SELECT id,last,first,english,business,email,phone FROM donors")]
    bye, byp, byfz, bylat, byloc = {}, {}, {}, {}, {}

    def words(s):
        return ' '.join(sorted(re.sub(r'[^a-z ]', ' ', (s or '').lower()).split()))
    for d in donors:
        for e in emails_of(d['email']):
            e = e.lower()
            bye.setdefault(e, set()).add(d['id'])
            loc = e.split('@')[0]
            if len(loc) >= 6:
                byloc.setdefault(loc, set()).add(d['id'])
        for ph in re.split(r'[;,/]+', d['phone'] or ''):
            k = _ph10(ph)
            if k:
                byp.setdefault(k, set()).add(d['id'])
        byfz.setdefault((_fz(d['last'] or ''), _fz(d['first'] or '')), set()).add(d['id'])
        for src in (d['english'], d['business']):
            w = words(src)
            if len(w) >= 6:
                bylat.setdefault(w, set()).add(d['id'])
    found = {}
    for r in con.execute("SELECT tid,first,last,email,phone FROM recon "
                         "WHERE COALESCE(processed,0)=0 AND COALESCE(status,'settled')='settled' "
                         "AND donor_id IS NULL"):
        em = (r['email'] or '').strip().lower()
        ln, fn = (r['last'] or '').strip(), (r['first'] or '').strip()

        def one(s):
            return s if (s and len(s) == 1) else None
        ids = one(bye.get(em))
        if not ids:
            ids = one(byp.get(_ph10(r['phone'])))
        if not ids:                       # אותו שם משתמש במייל, דומיין אחר (עבודה מול פרטי)
            ids = one(byloc.get(em.split('@')[0])) if '@' in em else None
        if not ids:                       # השם הלועזי כפי שהוא בכרטיס, בלי תלות בסדר המילים
            ids = one(bylat.get(words(fn + ' ' + ln)))
        if not ids and _gi and len(re.sub(r'[^A-Za-z]', '', ln)) >= 4 \
                and len(re.sub(r'[^A-Za-z]', '', fn)) >= 2:
            # תעתיק לעברית — גם בסדר הפוך, וגם עם J בתחילת שם כ־י (Jacobsen = יעקבסון)
            for a, b in ((ln, fn), (fn, ln)):
                for jy in (False, True):
                    ha = _he_alt(_gi, a, jy); hb = _he_alt(_gi, b, jy)
                    ids = ids or one(byfz.get((_fz(ha), _fz(hb))))
        if ids:
            found[r['tid']] = list(ids)[0]
    if not found:
        return 0
    dinfo = {r['id']: ((r['category'] or ''), (r['tier'] or ''))
             for r in con.execute("SELECT id,category,tier FROM donors")}
    ins = 0
    for r in list(con.execute("SELECT tid,first,last,amount,date,source FROM recon "
                              "WHERE COALESCE(processed,0)=0 AND donor_id IS NULL")):
        did = found.get(r['tid'])
        if not did:
            continue
        a = round(float(str(r['amount']).replace(',', '') or 0), 2)
        diso = _recon_iso(r['date'])
        meth = 'Banquest' if 'Banquest' in (r['source'] or '') else 'Authorize'
        con.execute("UPDATE recon SET donor_id=? WHERE tid=?", (did, r['tid']))
        if not diso or con.execute(
                "SELECT 1 FROM donations WHERE donor_id=? AND date=? AND method=? "
                "AND ROUND(CAST(amount AS REAL),2)=?", (did, diso, meth, a)).fetchone():
            con.execute("UPDATE recon SET processed=1 WHERE tid=?", (r['tid'],))
            continue
        old = con.execute("SELECT id,category FROM donations WHERE donor_id=? AND date=? "
                          "AND ROUND(CAST(amount AS REAL),2)=?", (did, diso[:7], a)).fetchone()
        cat, tier = dinfo.get(did, ('', ''))
        if old:
            con.execute("DELETE FROM donations WHERE id=?", (old['id'],))
        cat = (old['category'] if old and old['category'] else '') \
            or ('יששכר־זבולון' if 'יששכר' in tier else (cat or 'מזדמן'))
        note = ('ייבוא ' + ('בנק ווסט' if meth == 'Banquest' else 'אוטורייז')
                + ' · על שם ' + ((r['first'] or '') + ' ' + (r['last'] or '')).strip())
        if not (old and old['category']):
            note += ' · לא סווג — לבדוק עבור מה'
        con.execute("INSERT INTO donations(donor_id,date,amount,category,method,note,paid) "
                    "VALUES(?,?,?,?,?,?,1)", (did, diso, a, cat, meth, note))
        con.execute("UPDATE recon SET processed=1, category=? WHERE tid=?", (cat, r['tid']))
        ins += 1
    return ins


def link_card_names(con, link):
    """משייך חיובים שנשארו בלי כרטיס, לפי טבלת 'השם על האשראי → השם בכרטיס'.
    מכניס את התשלום עם התאריך האמיתי, ומסמן את שורת החיוב כטופלה."""
    donors = [dict(r) for r in con.execute("SELECT id,last,first,english FROM donors")]
    ids = {}
    for k, (hl, hf) in link.items():
        hit = [d for d in donors if d['last'] == hl and (d['first'] or '') == hf]
        if not hit:      # איות שונה בעברית (לקומב / לאקומב) — השוואה לפי צליל
            hit = [d for d in donors if _fz(d['last'] or '') == _fz(hl)
                   and _fz(d['first'] or '') == _fz(hf)]
        if not hit:      # ואם עדיין לא — לפי השם הלועזי כפי שהוא על החיוב
            hit = [d for d in donors if (d['english'] or '').strip().lower() == k]
        if len({d['id'] for d in hit}) == 1:
            ids[k] = hit[0]['id']
    if not ids:
        return 0
    dinfo = {r['id']: ((r['category'] or ''), (r['tier'] or ''))
             for r in con.execute("SELECT id,category,tier FROM donors")}
    rules = {}
    try:
        for r in con.execute("SELECT donor_id,amount,category FROM donor_rules"):
            rules[(r['donor_id'], round(float(r['amount'] or 0), 2))] = r['category']
    except Exception:
        pass
    ins = 0
    for r in list(con.execute(
            "SELECT tid,first,last,amount,date,source FROM recon "
            "WHERE COALESCE(processed,0)=0 AND COALESCE(status,'settled')='settled' "
            "AND donor_id IS NULL")):
        did = ids.get(((r['first'] or '') + ' ' + (r['last'] or '')).strip().lower())
        if not did:
            continue
        a = round(float(str(r['amount']).replace(',', '') or 0), 2)
        diso = _recon_iso(r['date'])
        meth = 'Banquest' if 'Banquest' in (r['source'] or '') else 'Authorize'
        con.execute("UPDATE recon SET donor_id=? WHERE tid=?", (did, r['tid']))
        if not diso or con.execute(
                "SELECT 1 FROM donations WHERE donor_id=? AND date=? AND method=? "
                "AND ROUND(CAST(amount AS REAL),2)=?", (did, diso, meth, a)).fetchone():
            con.execute("UPDATE recon SET processed=1 WHERE tid=?", (r['tid'],))
            continue
        # שורה שנרשמה בעבר עם חודש בלבד — מוחלפת בתשלום עם התאריך המדויק
        old = con.execute("SELECT id,category FROM donations WHERE donor_id=? AND date=? "
                          "AND ROUND(CAST(amount AS REAL),2)=?", (did, diso[:7], a)).fetchone()
        cat, tier = dinfo.get(did, ('', ''))
        if old:
            con.execute("DELETE FROM donations WHERE id=?", (old['id'],))
            cat = old['category'] or cat
        cat = rules.get((did, a)) or (old['category'] if old and old['category'] else '') \
            or ('יששכר־זבולון' if 'יששכר' in tier else (cat or 'מזדמן'))
        note = ('ייבוא ' + ('בנק ווסט' if meth == 'Banquest' else 'אוטורייז')
                + ' · על שם ' + ((r['first'] or '') + ' ' + (r['last'] or '')).strip())
        if not rules.get((did, a)) and not (old and old['category']):
            note += ' · לא סווג — לבדוק עבור מה'
        con.execute("INSERT INTO donations(donor_id,date,amount,category,method,note,paid) "
                    "VALUES(?,?,?,?,?,?,1)", (did, diso, a, cat, meth, note))
        con.execute("UPDATE recon SET processed=1, category=? WHERE tid=?", (cat, r['tid']))
        ins += 1
    return ins


def _ph10(s):
    """עשר הספרות האחרונות של מספר טלפון — להשוואה בלי תלות בקידומת ובסימנים."""
    d = re.sub(r'\D', '', s or '')
    return d[-10:] if len(d) >= 10 else ''


def _surkey(c):
    """שם המשפחה של איש קשר, בלי הרעשים שמאיר משתמש בהם: קידומת "ב." או "א.ת.",
    ספרה בסוף, ותוספת כמו "- קוויטל". מחזיר מפתח לפי צליל."""
    s = (c.get('last') or c.get('name') or '') if isinstance(c, dict) else (c or '')
    s = re.split(r'\s[-–]\s', s)[0]                 # "לוי זייגלבוים - קוויטל"
    s = re.sub(r'(?:(?<=^)|(?<=\s))[\u05d0-\u05ea]\.', ' ', s)   # "ב." / "א.ת."
    s = re.sub(r'[0-9]+', ' ', s)
    w = [x for x in re.sub(r'[^\u05d0-\u05ea ]', ' ', s).split() if len(x) >= 3]
    return _fz(w[-1]) if w else ''


def cluster_contacts(cards):
    """אדם אחד מפוזר לעיתים על כמה כרטיסי אנשי קשר (אחד עם הכתובת, אחד עם המייל,
    אחד עם 'קוויטל' בשם). מאחדים לפי טלפון או מייל משותף לפני ההשוואה לתורמים."""
    par = list(range(len(cards)))

    def find(x):
        while par[x] != x:
            par[x] = par[par[x]]; x = par[x]
        return x

    seen = {}
    for i, c in enumerate(cards):
        for k in ['@' + e for e in c['emails']] + ['#' + _ph10(p) for p in c['phones'] if _ph10(p)]:
            j = seen.setdefault(k, i)
            a, b = find(i), find(j)
            if a != b:
                par[a] = b
    # כרטיס שיש בו רק שם (בלי טלפון ובלי מייל) מצטרף לכרטיס עם אותו שם משפחה
    # לפי צליל — כך "לוי זייגלבוים - קוויטל" מתחבר לכרטיס שנושא את הטלפון.
    bysur = {}
    for i, c in enumerate(cards):
        if c['phones'] or c['emails']:
            k = _surkey(c)
            if len(k) >= 4:
                bysur.setdefault(k, set()).add(find(i))
    for i, c in enumerate(cards):
        if c['phones'] or c['emails']:
            continue
        k = _surkey(c)
        if len(k) < 4:
            continue
        tgt = bysur.get(k)
        if tgt and len(tgt) == 1:          # רק כשאין ספק לאיזה אדם זה שייך
            a2, b2 = find(i), find(list(tgt)[0])
            if a2 != b2:
                par[a2] = b2
    groups = {}
    for i in range(len(cards)):
        groups.setdefault(find(i), []).append(i)
    out = []
    for idxs in groups.values():
        o = {'name': '', 'first': '', 'last': '', 'org': '', 'note': '',
             'emails': [], 'phones': [], 'addrs': [], 'labels': [], 'names': []}
        for i in idxs:
            c = cards[i]
            for k in ('emails', 'phones', 'addrs', 'labels'):
                for v in c.get(k) or []:
                    if v not in o[k]:
                        o[k].append(v)
            for k in ('name', 'first', 'last', 'org'):
                if not o[k] and c.get(k):
                    o[k] = c[k]
            nm = (_fz(c.get('last') or ''), _fz(c.get('first') or ''))
            if nm != ('', '') and nm not in o['names']:
                o['names'].append(nm)
            nt = (c.get('note') or '').strip()
            if nt and nt not in o['note']:
                o['note'] = (o['note'] + '\n' + nt).strip()
        out.append(o)
    return out


# הערה שנראית כמו שמות לקוויטל: 'בן/בת פלונית', או בקשה מפורשת
_IS_KVITTEL = re.compile(r'(?:^|\s)(?:בן|בת)\s|לרפוא|לזיווג|להצלח|לפרנס|לישוע|לזרע|לבנים|לתשוב|רפואה שלמ')


def _fitfirst(a, b):
    """שמות פרטיים תואמים — זהים, או שאחד קיצור/וריאציה של השני (יידי / יידל)."""
    return not a or not b or a.startswith(b) or b.startswith(a)


_CCACHE = {'cards': None}


def _contact_cards():
    """כל אנשי הקשר מהקבצים שהועלו — נקראים פעם אחת ונשמרים בזיכרון."""
    if _CCACHE['cards'] is not None:
        return _CCACHE['cards']
    import gcontacts as _g
    out = []
    for fn, fx in (('contacts_seed2.vcf', _g.parse_any), ('contacts_seed.csv', _g.parse_csv)):
        p = os.path.join(HERE, fn)
        if os.path.exists(p):
            try:
                with open(p, encoding='utf-8', errors='replace') as f:
                    out += fx(f.read())
            except Exception as e:
                print('  contact cache error %s: %s' % (fn, e))
    _CCACHE['cards'] = cluster_contacts(out)
    return _CCACHE['cards']


def _tok_he(s):
    """מילים עבריות משם איש קשר — בלי ראשי תיבות וסימני פיסוק ("ב.בוכינגר תולי")."""
    return [t for t in re.sub(r'[^\u05d0-\u05ea ]', ' ', s or '').split() if len(t) >= 2]


# כינויים נפוצים שאין דרך לגזור אותם מהצליל — מוטי אינו נשמע כמו מרדכי
_NICK = {
    'מוטי': 'מרדכי', 'מוטל': 'מרדכי', 'מארק': 'מרדכי', 'מרק': 'מרדכי', 'מוטה': 'מרדכי',
    'מוישי': 'משה', 'מושי': 'משה', 'מוישה': 'משה',
    'שיא': 'יהושע', 'שייע': 'יהושע', 'שיע': 'יהושע', 'שעיה': 'ישעיה',
    'יידל': 'יהודה', 'יודל': 'יהודה', 'יידי': 'יהודה', 'לייבי': 'יהודה',
    'תולי': 'נפתלי', 'טולי': 'נפתלי', 'טוליע': 'נפתלי',
    'גבי': 'גבריאל', 'אבי': 'אברהם', 'אברומי': 'אברהם', 'אברימי': 'אברהם',
    'זלמן': 'שניאור', 'סנדר': 'אלכסנדר', 'בערי': 'דוב', 'בעריש': 'דוב', 'בערל': 'דוב',
    'איצי': 'יצחק', 'איציק': 'יצחק', 'איציקל': 'יצחק',
    'שמילי': 'שמואל', 'שמולי': 'שמואל', 'מולי': 'שמואל',
    'מנדי': 'מנחם', 'מענדי': 'מנחם', 'מנדל': 'מנחם', 'מענדל': 'מנחם',
    'לייזר': 'אליעזר', 'לוזר': 'אליעזר',
    'יאנקי': 'יעקב', 'ינקי': 'יעקב', 'יענקל': 'יעקב', 'קופל': 'יעקב',
    'הרשי': 'צבי', 'הירש': 'צבי', 'העניך': 'חנוך',
    'פייבי': 'שרגא', 'פיבי': 'שרגא', 'נחי': 'נחמן', 'נתי': 'נתן',
}


def _nick(s):
    s = (s or '').strip()
    return _NICK.get(s, s)


def _firstok(a, b, strict=False):
    """שמות פרטיים של אותו אדם — זהים, כינוי מוכר, או אותו צליל.
    strict=True למיזוג כרטיסים: קיצור לפי תחילית/סיומת מתקבל רק כששני
    הצלילים ארוכים דיים, אחרת שמות קצרים ושונים (שרה מול ישראל) היו
    נראים תואמים. בהשלמת פרטים מאנשי קשר די בסף נמוך יותר."""
    a, b = (a or '').strip(), (b or '').strip()
    if not a or not b:
        return False
    if a == b or _nick(a) == _nick(b):
        return True
    x, y = _fz(_nick(a)), _fz(_nick(b))
    if not x or not y:
        return False
    if x == y and len(x) >= 2:
        return True
    mn = 3 if strict else 2
    if len(x) < mn or len(y) < mn:
        return False
    return x.startswith(y) or y.startswith(x) or x.endswith(y) or y.endswith(x)


def contacts_fill(con, cards, status=None):
    """משייך אנשי קשר מגוגל לכרטיסי התורמים וממלא רק שדות ריקים — כתובת, טלפון, מייל.
    לא דורס שום נתון קיים. מחזיר סיכום למסך."""
    st = status if status is not None else {}
    people = cluster_contacts(cards)
    donors = [dict(r) for r in con.execute(
        "SELECT id,last,first,english,business,addr,phone,email,aliases FROM donors")]
    by_email, by_phone, by_he, by_lat, by_last = {}, {}, {}, {}, {}

    def put(d, k, v):
        if k:
            d.setdefault(k, []).append(v)
    for d in donors:
        for e in emails_of(d['email']):
            put(by_email, e.lower(), d)
        for p in re.split(r'[;,/]+', d['phone'] or ''):
            put(by_phone, _ph10(p), d)
        put(by_he, (_fz(d['last'] or ''), _fz(d['first'] or '')), d)
        put(by_last, _fz(d['last'] or ''), d)
        for src in (d['english'], d['business']):
            t = re.sub(r'[^a-z ]', '', (src or '').lower()).strip()
            if t:
                put(by_lat, ' '.join(sorted(t.split())), d)

    def pick(lst):
        u = {x['id']: x for x in (lst or [])}
        return list(u.values())[0] if len(u) == 1 else None

    filled = {'addr': 0, 'phone': 0, 'email': 0}
    touched, unmatched, notes = set(), [], {}
    for c in people:
        st['scanned'] = st.get('scanned', 0) + 1
        names = c['names'] or [(_fz(c['last']), _fz(c['first']))]
        d = None
        for e in c['emails']:
            d = d or pick(by_email.get(e))
        for p in c['phones']:
            d = d or pick(by_phone.get(_ph10(p)))
        strong = bool(d)
        if not d:
            for (l, f) in names:
                d = d or pick(by_he.get((l, f))) or pick(by_he.get((f, l)))
            strong = bool(d)
        if not d:
            t = re.sub(r'[^a-z ]', '', (c['name'] or '').lower()).strip()
            if t:
                d = pick(by_lat.get(' '.join(sorted(t.split()))))
                strong = bool(d)
        if not d:
            # שם משפחה לפי צליל + שם פרטי שמתיישב איתו, בכל סדר שהוא ובלי תלות
            # בראשי תיבות. תופס "ב.בוכינגר תולי" מול בוכינגר נפתלי, ו"קייזרי גבי"
            # מול קייזרי גבריאל.
            toks = _tok_he(' '.join(x for x in (c['name'], c['first'], c['last'], c['org']) if x))
            cands = []
            for i, t in enumerate(toks):
                for cand in by_last.get(_fz(t), []) or []:
                    rest = [u for j, u in enumerate(toks) if j != i]
                    cf = (cand['first'] or '').strip()
                    alts = [cf] + [x.strip() for x in re.split(r'[,;/]', cand.get('aliases') or '') if x.strip()]
                    if not cf or any(_firstok(u, v) for u in rest for v in alts if v):
                        cands.append(cand)
            d = pick(cands)
            strong = bool(d)
        if not d:
            if c['addrs']:
                unmatched.append({'name': c['name'] or c['org'], 'addr': c['addrs'][0],
                                  'phone': ', '.join(c['phones'][:2]),
                                  'email': ', '.join(c['emails'][:1])})
            continue
        sets, vals = [], []
        if c['addrs'] and not (d['addr'] or '').strip():
            sets.append('addr=?'); vals.append(c['addrs'][0]); filled['addr'] += 1
        if strong and c['phones'] and not (d['phone'] or '').strip():
            # מספר שמאיר כבר דחה אצל התורם הזה לא חוזר בייבוא הבא
            try:
                bad = {_ph10(r['val']) or re.sub(r'\D', '', r['val'] or '')
                       for r in con.execute("SELECT val FROM sugg_reject "
                                            "WHERE donor_id=? AND kind='phone'", (d['id'],))}
            except Exception:
                bad = set()
            # אותו מספר מופיע לעיתים בכמה עיצובים — שומרים אותו פעם אחת
            uph, seenp = [], set()
            for ph in c['phones']:
                k = _ph10(ph) or re.sub(r'\D', '', ph)
                if k and k in bad:
                    continue
                if k and k not in seenp:
                    seenp.add(k); uph.append(ph.strip())
            if uph:
                sets.append('phone=?'); vals.append(' / '.join(uph[:3])); filled['phone'] += 1
        if strong and c['emails'] and not (d['email'] or '').strip():
            sets.append('email=?'); vals.append(c['emails'][0]); filled['email'] += 1
        if sets:
            con.execute("UPDATE donors SET " + ','.join(sets) + " WHERE id=?", vals + [d['id']])
            touched.add(d['id'])
            st['filled'] = len(touched)
        if strong and (c['note'] or '').strip():
            notes.setdefault(d['id'], c['note'].strip())
    # מי שנשאר בלי כתובת — מחפשים לפי שם משפחה ושם פרטי תואם, ולוקחים רק אם
    # כל אנשי הקשר המתאימים מצביעים על אותה כתובת אחת. אחרת זו ניחוש ולא נכתוב.
    byname = {}
    for c in people:
        if not c['addrs']:
            continue
        for (l, f) in (c['names'] or [(_fz(c['last']), _fz(c['first']))]):
            byname.setdefault(l, []).append((f, c))
    for d in donors:
        if (d['addr'] or '').strip() or d['id'] in touched:
            continue
        f = _fz(d['first'] or '')
        hits = [c for (cf, c) in byname.get(_fz(d['last'] or ''), []) if _fitfirst(cf, f)]
        addrs = {c['addrs'][0] for c in hits}
        if len(addrs) == 1:
            con.execute("UPDATE donors SET addr=? WHERE id=?", (addrs.pop(), d['id']))
            touched.add(d['id']); filled['addr'] += 1
    con.commit()
    # שמות לתפילה שרשומים בהערה של איש הקשר — נכנסים רק למי שאין לו קוויטל בכלל,
    # כדי שלא ייווצרו כפילויות אצל מי שכבר יש לו שמות.
    kv = nt = 0
    haskv = {r['donor_id'] for r in con.execute(
        "SELECT DISTINCT donor_id FROM prayers WHERE COALESCE(TRIM(text),'')<>''")}
    hasnote = {r['id'] for r in con.execute("SELECT id FROM donors WHERE TRIM(COALESCE(notes,''))<>''")}
    for did, note in notes.items():
        note = note.strip()
        if len(re.sub(r'[^א-ת]', '', note)) < 8:
            continue
        if _IS_KVITTEL.search(note):                 # שמות לתפילה — רק למי שאין לו קוויטל בכלל
            if did in haskv:
                continue
            con.execute("INSERT INTO prayers(donor_id,name,text,tier) VALUES(?,'',?,'')", (did, note))
            haskv.add(did); kv += 1
        elif did not in hasnote:                     # הערה רגילה — לשדה ההערות, אם הוא ריק
            con.execute("UPDATE donors SET notes=? WHERE id=?", (note, did))
            hasnote.add(did); nt += 1
    con.commit()
    unmatched.sort(key=lambda x: x['name'])
    return {'ok': True, 'cards': len(cards), 'people': len(people), 'donors': len(touched), 'kvittel': kv, 'notes': nt,
            'filled': filled, 'unmatched': unmatched[:400], 'unmatched_total': len(unmatched)}


def mail_subject_of(summary):
    """שחזור שורת הנושא מתוך התקציר שנשמר ביומן ('📧 נושא — תקציר · 📎 …')."""
    s = (summary or '').strip()
    for pre in ('📧 ', '📤 שלחנו: ', '📤 נשלח: '):
        if s.startswith(pre):
            s = s[len(pre):]
    s = s.split(' — ')[0]
    for sep in (' · 📎', ' · 🕯️'):
        s = s.split(sep)[0]
    return s.strip()


def link_mail_replies(con):
    """מייל שמאיר שלח מג'ימייל ונושאו זהה למייל שהתורם שלח לפניו — נתלה מתחתיו
    כתשובה. משלים את הקישור לפי Message-ID שנעשה כבר בזמן המשיכה, ומטפל גם
    בהיסטוריה ובמקרה שהתשובה נמשכה לפני המייל שעליו היא עונה. מוסיף קישורים
    בלבד, ולכן בטוח להרצה חוזרת."""
    import gmail_intake as _gi
    n = 0
    rows = con.execute("SELECT id,donor_id,summary,date FROM contacts_log "
                       "WHERE direction='out' AND channel='אימייל' "
                       "AND reply_to IS NULL AND donor_id IS NOT NULL").fetchall()
    for r in rows:
        par = _gi._parent_row(con, r['donor_id'], [], mail_subject_of(r['summary']),
                              r['date'] or '9999')
        if not par or par == r['id']:
            continue
        con.execute("UPDATE contacts_log SET reply_to=?, "
                    "summary=REPLACE(summary,'📤 שלחנו: ','📤 עניתי: ') WHERE id=?",
                    (par, r['id']))
        n += 1
    if n:
        con.commit()
    return n


def log_sent_mail(donor_id, to, subject, body, msg_id='', natt=0):
    """מתייק ביומן הקשר כל מייל שהמערכת שלחה לתורם — מיד, בלי להמתין למשיכה.
    המפתח זהה לזה של סריקת תיבת הנשלחים, כך שלא ייווצר רישום כפול."""
    if not donor_id:
        return
    key = 'out:%s|%s' % ((msg_id or '').strip(), donor_id)
    summary = '📤 שלחנו: ' + (subject or 'מייל') + ((' · 📎 %d קבצים מצורפים' % natt) if natt else '')
    try:
        con = db()
        con.execute("""INSERT INTO contacts_log(donor_id,date,channel,summary,next_date,msg_id,body,att_checked,direction,at)
                       VALUES(?,?,?,?,'',?,?,1,'out',?)""",
                    (donor_id, today_iso(), 'אימייל', summary, key, (body or '').strip(), now_iso()))
        con.commit(); con.close()
    except Exception:
        pass


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

# כל הנתונים נבנים מחדש מהמסד בכל בקשה, וזה הדבר הכבד ביותר בשרת. מחזיקים
# את התשובה המוכנה (גם דחוסה) ובונים אותה מחדש רק אחרי שינוי אמיתי.
_DATA_VER = 0
_DATA_TTL = 20          # גם בלי בקשת כתיבה — רענון תקופתי, למקרה של עדכון ברקע
_DATA_CACHE = {'ver': -1, 'at': 0.0, 'raw': b'', 'gz': b'', 'etag': ''}
# בניית התשובה עולה כ-14MB זיכרון. בלי המנעול הזה, עשר בקשות שמגיעות יחד
# בונות עשר פעמים במקביל — 140MB בבת אחת, וזה מה שהפיל את השרת.
# עם המנעול: אחד בונה, כל השאר ממתינים לו ומקבלים את אותה תשובה.
_DATA_LOCK = threading.Lock()


def bump_data():
    """נקרא בכל בקשה שמשנה נתונים — התשובה השמורה כבר לא תקפה."""
    global _DATA_VER
    _DATA_VER += 1


class H(BaseHTTPRequestHandler):
    def _send_cached(self, c):
        """תשובה שכבר מוכנה במטמון. אם ללקוח יש בדיוק אותה גרסה — 304 בלי גוף."""
        if (self.headers.get('If-None-Match') or '') == c['etag']:
            self.send_response(304)
            self.send_header('ETag', c['etag'])
            self.send_header('Cache-Control', 'no-cache')
            self.end_headers()
            return
        gz = c['gz'] and 'gzip' in (self.headers.get('Accept-Encoding') or '')
        data = c['gz'] if gz else c['raw']
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        if gz:
            self.send_header('Content-Encoding', 'gzip')
        self.send_header('ETag', c['etag'])
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send(self, code, body, ctype='application/json'):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', ctype + ('; charset=utf-8' if 'json' in ctype or 'html' in ctype or 'calendar' in ctype else ''))
        # דחיסה — הנתונים עוברים בערך פי עשרה יותר מהר בסלולרי
        enc = None
        _zip = any(t in ctype for t in ('json', 'html', 'text', 'javascript', 'css', 'svg', 'calendar'))
        if _zip and len(data) > 1024 and 'gzip' in (self.headers.get('Accept-Encoding') or ''):
            try:
                data = gzip.compress(data, 6); enc = 'gzip'
            except Exception:
                enc = None
        if enc:
            self.send_header('Content-Encoding', enc)
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
            global _DATA_CACHE

            def _fresh():
                c = _DATA_CACHE
                return (c['raw'] and c['ver'] == _DATA_VER
                        and time.time() - c['at'] < _DATA_TTL)
            if _fresh():
                return self._send_cached(_DATA_CACHE)
            with _DATA_LOCK:
                if _fresh():             # מישהו אחר כבר בנה בזמן שהמתנו
                    return self._send_cached(_DATA_CACHE)
                return self._build_data()

        if self.path.split('?')[0] == '/api/backup':
            # גיבוי מלא של המסד. נעשה דרך מנגנון הגיבוי של SQLite כדי לקבל
            # קובץ שלם ותקין גם בזמן שהמערכת עובדת. משמש גם לגיבוי אצל מאיר
            # וגם כדי לשלוח לי את הנתונים העדכניים כשצריך.
            try:
                light = urllib.parse.parse_qs(
                    urllib.parse.urlparse(self.path).query).get('light', [''])[0] == '1'
                tmp = os.path.join(HERE, '_backup_tmp.db')
                src = sqlite3.connect(DB)
                dst = sqlite3.connect(tmp)
                with dst:
                    src.backup(dst)
                src.close()
                if light:
                    # גיבוי קל לשליחה: כל הנתונים, בלי גוף הקבצים המצורפים
                    # (תעודות וצילומים). השמות נשארים, רק התוכן הכבד יורד.
                    dst.execute("UPDATE files SET data=x''")
                    dst.commit()
                    dst.isolation_level = None      # VACUUM לא רץ בתוך טרנזקציה
                    dst.execute("VACUUM")
                dst.close()
                raw = open(tmp, 'rb').read()
                try: os.remove(tmp)
                except Exception: pass
                blob = gzip.compress(raw, 6)
                name = 'kollel-crm-%s%s.db.gz' % (today_iso(), '-light' if light else '')
                self.send_response(200)
                self.send_header('Content-Type', 'application/gzip')
                self.send_header('Content-Disposition', 'attachment; filename="%s"' % name)
                self.send_header('Content-Length', str(len(blob)))
                self.end_headers()
                self.wfile.write(blob)
                print('  גיבוי הורד: %.1f MB (דחוס %.1f MB)' % (len(raw) / 1048576, len(blob) / 1048576))
                return
            except Exception as e:
                return self._send(500, {'error': 'backup', 'detail': str(e)[:200]})
        if self.path == '/api/health':
            return self._send(200, health_report())
        return self._get2()

    def _build_data(self):
            global _DATA_CACHE
            _ver = _DATA_VER
            donors, unlinked, general_tasks = get_all()
            con = db(); camps = [r['name'] for r in con.execute("SELECT name FROM campaigns ORDER BY created DESC, name")]
            bitems = [r['name'] for r in con.execute("SELECT name FROM building_items ORDER BY created DESC, name")]
            try: nd = [[r['a'], r['b']] for r in con.execute("SELECT a,b FROM not_dupes")]
            except Exception: nd = []
            try: ckinds = [r['name'] for r in con.execute("SELECT name FROM contact_kinds ORDER BY created, name")]
            except Exception: ckinds = []
            try: pchans = [r['name'] for r in con.execute("SELECT name FROM pay_channels ORDER BY created, name")]
            except Exception: pchans = []
            try: tkinds = [r['name'] for r in con.execute("SELECT name FROM task_kinds ORDER BY created, name")]
            except Exception: tkinds = []
            con.close()
            _raw = json.dumps({'donors': donors, 'unlinked_prayers': unlinked, 'general_tasks': general_tasks, 'campaigns': camps, 'building_items': bitems, 'not_dupes': nd, 'task_kinds': tkinds, 'pay_channels': pchans, 'contact_kinds': ckinds, 'heb_year': current_heb_year(), 'kv_default': list(kvittel_default_month())}, ensure_ascii=False).encode('utf-8')
            try: _gz = gzip.compress(_raw, 6)
            except Exception: _gz = b''
            # החתימה לפי התוכן עצמו: בנייה מחדש שיצא ממנה אותו מידע משאירה את
            # אותה חתימה, והדפדפן מקבל 304 בלי להוריד שוב מאומה
            _DATA_CACHE = {'ver': _ver, 'at': time.time(), 'raw': _raw, 'gz': _gz,
                           'etag': '"d%s"' % hashlib.md5(_raw).hexdigest()[:16]}
            return self._send_cached(_DATA_CACHE)

    def _get2(self):
        if False:
            pass
        if self.path.split('?')[0] == '/api/donors.vcf':
            # ייצוא כל התורמים כאיש קשר אחד ומסודר לכל תורם — לייבוא חזרה לאנשי הקשר
            con = db()
            rows = [dict(r) for r in con.execute(
                "SELECT id,last,first,english,business,phone,email,addr,city,region,zip,country,"
                "tier,category,notes FROM donors ORDER BY last,first")]
            con.close()
            def esc_v(x):
                return re.sub(r'[\r\n]+', ' ', str(x or '')).replace('\\', '\\\\').replace(';', '\\;').replace(',', '\\,')
            out = []
            for d in rows:
                he = ((d['last'] or '') + ' ' + (d['first'] or '')).strip()
                if not he and not (d['english'] or '').strip():
                    continue
                fn = he or d['english']
                out.append('BEGIN:VCARD')
                out.append('VERSION:3.0')
                out.append('N:%s;%s;;;' % (esc_v(d['last']), esc_v(d['first'])))
                out.append('FN:%s' % esc_v(fn))
                if (d['english'] or '').strip():
                    out.append('NICKNAME:%s' % esc_v(d['english']))
                if (d['business'] or '').strip():
                    out.append('ORG:%s' % esc_v(d['business']))
                for ph in re.split(r'[;,/]+', d['phone'] or ''):
                    ph = ph.strip()
                    if ph:
                        out.append('TEL;TYPE=CELL:%s' % ph)
                for em in re.split(r'[;,/ ]+', d['email'] or ''):
                    em = em.strip()
                    if '@' in em:
                        out.append('EMAIL;TYPE=INTERNET:%s' % em)
                if (d['addr'] or '').strip():
                    # בבסיס הנתונים עמודת country מחזיקה בפועל את המדינה בארה"ב (NY/NJ/FL)
                    st = (d['region'] or d['country'] or '').strip()
                    cty = 'Israel' if st.upper() == 'IL' else ('USA' if len(st) == 2 else '')
                    if st.upper() == 'IL':
                        st = ''
                    out.append('ADR;TYPE=HOME:;;%s;%s;%s;%s;%s' % (
                        esc_v(d['addr']), esc_v(d['city']), esc_v(st),
                        esc_v(d['zip']), esc_v(cty)))
                cats = ['תורמים']
                if (d['tier'] or '').strip():
                    cats.append('קוויטל')
                out.append('CATEGORIES:%s' % ','.join(cats))
                out.append('NOTE:%s' % esc_v('כרטיס #%d במערכת כולל חצות%s' % (
                    d['id'], (' · ' + d['notes'].replace('\n', ' · ')) if (d['notes'] or '').strip() else '')))
                out.append('END:VCARD')
            body = ('\r\n'.join(out) + '\r\n').encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/vcard; charset=utf-8')
            self.send_header('Content-Disposition', 'attachment; filename="kollel-donors.vcf"')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path.split('?')[0] == '/api/donors.csv':
            # רשימת תפוצה לדיוור — שורה לכל כתובת מייל, כדי שכל תורם יקבל מייל אישי בשמו
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            cat = (qs.get('cat', [''])[0] or '').strip()
            con = db()
            rows = con.execute("SELECT id,last,first,english,email,phone,category,tier,city,country FROM donors "
                               "ORDER BY last, first").fetchall()
            con.close()
            buf = io.StringIO()
            w = csv.writer(buf)
            w.writerow(['email', 'name', 'last', 'first', 'english', 'category', 'tier', 'phone', 'city', 'country', 'donor_id'])
            n = 0
            for r in rows:
                if cat and (r['category'] or '').strip() != cat:
                    continue
                for e in emails_of(r['email']):
                    w.writerow([e, ((r['last'] or '') + ' ' + (r['first'] or '')).strip(), r['last'] or '', r['first'] or '',
                                r['english'] or '', r['category'] or '', r['tier'] or '', r['phone'] or '',
                                r['city'] or '', r['country'] or '', r['id']])
                    n += 1
            data = ('﻿' + buf.getvalue()).encode('utf-8')   # BOM — כדי שאקסל יציג עברית נכון
            self.send_response(200)
            self.send_header('Content-Type', 'text/csv; charset=utf-8')
            self.send_header('Content-Disposition', 'attachment; filename="donors-mailing-list.csv"')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers(); self.wfile.write(data)
            return
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
        if self.path.split('?')[0] in ('/cert.png', '/cert.jpg'):
            # התעודה כתמונה — JPEG נשלח בוואטסאפ כתמונה פתוחה, PNG משמש להעתקה ללוח
            fmt = 'jpg' if self.path.split('?')[0].endswith('.jpg') else 'png'
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            g = lambda k: (qs.get(k, [''])[0] or '')
            try:
                data = cert_png(g('kind') or 'parnes', g('date'), g('names'), g('dedic'),
                                int(g('w') or 1000), fmt)
            except Exception as e:
                return self._send(500, {'error': 'cert', 'detail': str(e)})
            self.send_response(200)
            self.send_header('Content-Type', 'image/jpeg' if fmt == 'jpg' else 'image/png')
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Content-Disposition', 'inline; filename="parnes-cert.%s"' % fmt)
            self.end_headers(); self.wfile.write(data)
            return
        if self.path.split('?')[0] == '/api/avreichim':
            # רשימת האברכים לפי שם משפחה, ולצד כל אחד מי מחזיק אותו, ממתי ובכמה.
            # אברך בלי שותף מופיע גם הוא — הרשימה היא של הכולל, לא של התורמים.
            con = db()
            out = {}
            showall = (urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                       .get('all', [''])[0] == '1')
            gone = set()
            for r in con.execute("SELECT * FROM avreichim"):
                if (r['ended'] or '').strip() and not showall:
                    gone.add(r['name'])            # יצא מהכולל — לא ברשימה השוטפת
                    continue
                out[r['name']] = {'aid': r['id'], 'name': r['name'], 'last': r['last'] or '',
                                  'first': r['first'] or '', 'note': r['note'] or '',
                                  'started': r['started'] or '', 'ended': r['ended'] or '',
                                  'phone': r['phone'] or '', 'email': r['email'] or '',
                                  'addr': r['addr'] or '', 'holders': [], 'taken': False}
            for r in con.execute(
                    "SELECT TRIM(p.avreich) a, p.id pid, p.active, p.start_date, p.amount, p.share, "
                    "p.joint, d.id did, d.last, d.first FROM partners p "
                    "LEFT JOIN donors d ON d.id=p.donor_id WHERE COALESCE(TRIM(p.avreich),'')<>''"):
                g = out.get(r['a'])
                if g is None:
                    if r['a'] in gone or not _is_avreich(r['a']):
                        continue      # שותפות ישנה של אברך שיצא — לא מחזירה אותו לרשימה
                    l, f = _split_av(r['a'])
                    g = out[r['a']] = {'aid': None, 'name': r['a'], 'last': l, 'first': f,
                                       'note': '', 'started': '', 'ended': '', 'phone': '',
                                       'email': '', 'addr': '', 'holders': [], 'taken': False}
                if r['active'] is None or r['active'] != 0:
                    nm = ((r['last'] or '') + ' ' + (r['first'] or '')).strip()
                    if nm and nm not in [h['name'] for h in g['holders']]:
                        g['holders'].append({'id': r['did'], 'name': nm, 'pid': r['pid'],
                                             'start_date': r['start_date'] or '',
                                             'amount': r['amount'] or '', 'share': r['share'] or '',
                                             'joint': r['joint'] or 0})
                    g['taken'] = True
            names = {}
            for r in con.execute("SELECT id,last,first FROM donors"):
                names[r['id']] = ((r['last'] or '') + ' ' + (r['first'] or '')).strip()
            for r in con.execute("SELECT avreich,donor_id,date,hdate,text FROM avreich_log "
                                 "ORDER BY id DESC"):
                g = out.get(r['avreich'])
                if g is None:
                    continue
                g.setdefault('log', []).append({'date': r['date'] or '', 'hdate': r['hdate'] or '',
                                                'text': r['text'] or '',
                                                'donor': names.get(r['donor_id'], '')})
            con.close()
            rows = sorted(out.values(), key=lambda x: (_srt(x['last']), _srt(x['first'])))
            return self._send(200, {'rows': rows, 'total': len(rows),
                                    'free': sum(1 for x in rows if not x['holders'])})
        if self.path.split('?')[0] == '/api/ledger':
            # ספר החיובים: כל מה שנכנס מינואר, כל אמצעי בנפרד, וגם מה שלא עבר.
            # הנתונים מגיעים מטבלת ההתאמות — שם יושב כל חיוב אמיתי עם המקור שלו.
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            since = (qs.get('since', ['2026-01-01'])[0] or '2026-01-01')[:10]
            want = (qs.get('src', [''])[0] or '').strip()
            fail = qs.get('failed', [''])[0] == '1'
            con = db()
            names = {r['id']: ((r['last'] or '') + ' ' + (r['first'] or '')).strip()
                     for r in con.execute("SELECT id,last,first FROM donors")}
            groups, rows = {}, []
            for r in con.execute("SELECT tid,first,last,amount,date,source,status,donor_id,category "
                                 "FROM recon"):
                iso = _recon_iso(r['date']) or (r['date'] or '')[:10]
                if iso < since:
                    continue
                try:
                    amt = float(str(r['amount'] or 0).replace(',', '').replace('$', ''))
                except Exception:
                    amt = 0.0
                src = r['source'] or 'אחר'
                bad = (r['status'] or 'settled') not in ('settled', '')
                g = groups.setdefault(src, {'src': src, 'n': 0, 'total': 0.0, 'bad_n': 0,
                                            'bad_total': 0.0, 'first': '', 'last': '', 'mon': {}})
                ym = iso[:7]
                mo = g['mon'].setdefault(ym, {'ym': ym, 'n': 0, 'total': 0.0,
                                              'bad_n': 0, 'bad_total': 0.0})
                if bad:
                    g['bad_n'] += 1; g['bad_total'] += amt
                    mo['bad_n'] += 1; mo['bad_total'] += amt
                else:
                    g['n'] += 1; g['total'] += amt
                    mo['n'] += 1; mo['total'] += amt
                    if iso:
                        g['first'] = min(g['first'] or iso, iso); g['last'] = max(g['last'], iso)
                if (want and src != want) or (fail and not bad) or (not fail and want and bad):
                    continue
                if want or fail:
                    rows.append({'tid': r['tid'], 'name': names.get(r['donor_id'], ''),
                                 'donor_id': r['donor_id'],
                                 'bank': ' '.join(x for x in ((r['first'] or '').strip(),
                                                              (r['last'] or '').strip()) if x),
                                 'amount': round(amt, 2), 'date': iso, 'src': src,
                                 'status': r['status'] or 'settled', 'note': r['category'] or ''})
            con.close()
            for g in groups.values():
                g['total'] = round(g['total'], 2); g['bad_total'] = round(g['bad_total'], 2)
                for mo in g['mon'].values():
                    mo['total'] = round(mo['total'], 2); mo['bad_total'] = round(mo['bad_total'], 2)
                g['mon'] = sorted(g['mon'].values(), key=lambda x: x['ym'], reverse=True)
            out = sorted(groups.values(), key=lambda x: -x['total'])
            rows.sort(key=lambda x: x['date'], reverse=True)
            return self._send(200, {'groups': out, 'rows': rows[:600], 'more': max(0, len(rows) - 600),
                                    'since': since,
                                    'total': round(sum(g['total'] for g in out), 2),
                                    'n': sum(g['n'] for g in out),
                                    'bad_total': round(sum(g['bad_total'] for g in out), 2),
                                    'bad_n': sum(g['bad_n'] for g in out)})
        if self.path.split('?')[0] == '/api/deposits':
            # שמות מפקידים שלא זוהו — מקובצים לפי השם, כדי לשייך שם אחד ולסגור
            # את כל השורות שלו בבת אחת
            con = db()
            ign = {r['src'] for r in con.execute("SELECT src FROM name_map WHERE ignored=1")}
            g = {}
            for r in con.execute("SELECT tid,first,last,amount,date,source,email,phone,category FROM recon "
                                 "WHERE donor_id IS NULL"):
                try:                       # רק כסף שנכנס — משיכה או עמלה אינה תרומה
                    amt = float(str(r['amount'] or 0).replace(',', '').replace('$', ''))
                except Exception:
                    amt = 0.0
                if amt <= 0:
                    continue
                nm = ' '.join(x for x in ((r['first'] or '').strip(), (r['last'] or '').strip()) if x)
                k = _nkey(nm)
                if not k or k in ign:
                    continue
                src = r['source'] or ''
                # המסך הזה הוא על כסף שנכנס לבנק. חיובי אשראי (אוטרייז / בנק
                # ווסט) הם עולם אחר, ולכן מסומנים ומוצגים בלשונית נפרדת.
                kind = 'card' if re.match(r'(Authorize|Banquest)', src) else 'bank'
                e = g.setdefault(k, {'key': k, 'name': nm, 'n': 0, 'total': 0.0, 'dates': [],
                                     'src': src, 'kind': kind, 'email': r['email'] or '',
                                     'phone': r['phone'] or '', 'note': '', 'tids': []})
                e['n'] += 1
                if not e['note'] and (r['category'] or '').strip():
                    e['note'] = r['category'].strip()
                try: e['total'] += float(str(r['amount'] or 0).replace(',', '').replace('$', ''))
                except Exception: pass
                if r['date']: e['dates'].append(r['date'])
                e['tids'].append(r['tid'])
                if not e['email'] and r['email']: e['email'] = r['email']
            con.close()
            out = sorted(g.values(), key=lambda x: -x['total'])
            for e in out:
                # תאריכי אשראי מגיעים כ-'26-Mar-2026' — ממיינים לפי התאריך האמיתי
                e['dates'] = sorted(set(e['dates']), key=lambda d: _recon_iso(d) or d)
                e['total'] = round(e['total'], 2)
                e['tids'] = e['tids'][:200]
            bank = [x for x in out if x['kind'] == 'bank']
            return self._send(200, {'rows': out, 'names': len(bank),
                                    'deposits': sum(x['n'] for x in bank),
                                    'total': round(sum(x['total'] for x in bank), 2),
                                    'cards': len(out) - len(bank),
                                    'cards_total': round(sum(x['total'] for x in out
                                                             if x['kind'] == 'card'), 2)})
        if self.path.split('?')[0] == '/api/izhistory':
            # יומן כללי — כל השינויים ביששכר־זבולון, מהחדש לישן
            con = db()
            names = {r['id']: ((r['last'] or '') + ' ' + (r['first'] or '')).strip()
                     for r in con.execute("SELECT id,last,first FROM donors")}
            rows = [{'avreich': r['avreich'] or '', 'donor': names.get(r['donor_id'], ''),
                     'donor_id': r['donor_id'], 'date': r['date'] or '', 'hdate': r['hdate'] or '',
                     'text': r['text'] or '', 'at': r['at'] or ''}
                    for r in con.execute("SELECT * FROM avreich_log ORDER BY id DESC LIMIT 400")]
            con.close()
            return self._send(200, {'rows': rows})
        if self.path.split('?')[0] == '/api/unclassified':
            # תורמים שיש להם חיובים שנכנסו בלי לדעת עבור מה — לשאלה בדף החיובים
            con = db()
            src = (urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get('src', [''])[0] or '').strip()
            meth = {'banquest': ['Banquest'], 'authorize': ['Authorize'],
                    'checks': ["צ'ק"], 'donorsfund': ['דונרס', 'OJC']}.get(src, [])
            MLBL = {'Banquest': 'בנק ווסט', 'Authorize': 'אוטרייז'}   # שאר השיטות מוצגות כשמן
            q = ("SELECT n.id, n.donor_id, d.last, d.first, n.date, n.amount, n.method FROM donations n "
                 "JOIN donors d ON d.id=n.donor_id WHERE COALESCE(n.note,'') LIKE '%לא סווג%'")
            args = []
            if meth:
                q += " AND n.method IN (%s)" % ','.join('?' * len(meth)); args += meth
            q += " ORDER BY d.last, n.date"
            grp = {}
            for r in con.execute(q, args):
                g = grp.setdefault(r['donor_id'], {'donor_id': r['donor_id'],
                                                   'name': ((r['last'] or '') + ' ' + (r['first'] or '')).strip(),
                                                   'items': [], 'total': 0.0, 'methods': set()})
                lbl = MLBL.get(r['method'] or '', (r['method'] or 'אחר'))
                g['items'].append({'id': r['id'], 'date': r['date'],
                                   'amount': round(float(r['amount'] or 0), 2), 'method': lbl})
                g['total'] += float(r['amount'] or 0)
                g['methods'].add(lbl)
            out = []
            for g in grp.values():
                g['methods'] = ' · '.join(sorted(g['methods']))
                g['total'] = round(g['total'], 2)
                out.append(g)
            out.sort(key=lambda x: -x['total'])
            con.close()
            return self._send(200, {'ok': True, 'donors': out,
                                    'total': round(sum(x['total'] for x in out), 2)})
        if self.path.split('?')[0] == '/api/audit/phones':
            # הצעות טלפון לתורמים שאין להם — מתוך קבצי אנשי הקשר שהועלו
            try:
                cards = _contact_cards()
            except Exception as e:
                return self._send(200, {'ok': False, 'error': str(e), 'rows': []})
            con = db()
            donors = [dict(r) for r in con.execute(
                "SELECT id,last,first,english,email,tier FROM donors "
                "WHERE TRIM(COALESCE(phone,''))=''")]
            tot = {}
            for r in con.execute("SELECT donor_id, SUM(CAST(REPLACE(REPLACE(COALESCE(amount,'0'),',',''),"
                                 "'$','') AS REAL)) s FROM donations GROUP BY donor_id"):
                tot[r['donor_id']] = round(r['s'] or 0)
            used = set()
            for r in con.execute("SELECT phone FROM donors WHERE TRIM(COALESCE(phone,''))<>''"):
                for x in re.split(r'[;,/]+', r['phone'] or ''):
                    if _ph10(x):
                        used.add(_ph10(x))
            rej = set()
            try:
                for r in con.execute("SELECT donor_id,val FROM sugg_reject WHERE kind='phone'"):
                    rej.add((r['donor_id'], (r['val'] or '').strip()))
                    if (r['val'] or '').strip() == '*':
                        rej.add((r['donor_id'], '*'))
            except Exception:
                pass
            con.close()
            idx = {}
            for c in cards:
                if not c['phones']:
                    continue
                for t in _tok_he(' '.join(x for x in (c.get('name'), c.get('first'),
                                                     c.get('last'), c.get('org')) if x)):
                    idx.setdefault(_fz(t), []).append(c)
            out = []
            for d in donors:
                k = _fz(d['last'] or '')
                if (d['id'], '*') in rej:      # מאיר כבר אמר "אף אחד מהם" — לא לשאול שוב
                    continue
                seen, cands = set(), []
                # שם משפחה קצר מדי מכדי לחפש לפיו — התורם עדיין ברשימה, בלי הצעות
                for c in (idx.get(k, []) if len(k) >= 3 else []):
                    for ph in c['phones'][:2]:
                        p10 = _ph10(ph)
                        key = p10 or ph
                        if not key or key in seen or p10 in used:
                            continue
                        if (d['id'], ph.strip()) in rej:
                            continue
                        seen.add(key)
                        cands.append({'name': (c.get('name') or '').strip(), 'phone': ph.strip(),
                                      'email': (c['emails'][0] if c['emails'] else ''),
                                      'sure': bool(_firstok((c.get('first') or ''), d['first'] or ''))})
                cands.sort(key=lambda x: (not x['sure'],))
                # כל מי שאין לו טלפון נכנס לרשימה, גם כשלא נמצאה לו הצעה —
                # אחרת המסך מציג "אין הצעות" בזמן שעדיין חסרים עשרות טלפונים.
                out.append({'id': d['id'], 'name': ((d['last'] or '') + ' ' + (d['first'] or '')).strip(),
                            'tier': d['tier'] or '', 'email': d['email'] or '',
                            'tot': tot.get(d['id'], 0), 'cands': cands[:4]})
            # קודם מי שיש לו הצעה מוכנה, ואז לפי גובה התרומות
            out.sort(key=lambda x: (not x['cands'], -x['tot'], x['name']))
            return self._send(200, {'ok': True, 'rows': out, 'total': len(donors),
                                    'withcands': sum(1 for x in out if x['cands'])})
        if self.path.split('?')[0] == '/api/audit/noaddr':
            # מי אין לו כתובת בכרטיס, ומה אפשר להציע לו — מייצוא אנשי הקשר או מכתובת החיוב
            con = db()
            rows = [dict(r) for r in con.execute(
                "SELECT id,last,first,english,phone,email FROM donors "
                "WHERE TRIM(COALESCE(addr,''))='' ORDER BY last,first")]
            ids = {r['id'] for r in rows}
            tot = {}
            for r in con.execute("SELECT donor_id, SUM(CAST(REPLACE(REPLACE(COALESCE(amount,'0'),',',''),'$','') "
                                 "AS REAL)) s FROM donations GROUP BY donor_id"):
                tot[r['donor_id']] = round(r['s'] or 0, 2)
            bill = {}
            for r in con.execute("SELECT donor_id,addr,city,state,zip FROM recon "
                                 "WHERE donor_id IS NOT NULL AND TRIM(COALESCE(addr,''))<>''"):
                if r['donor_id'] in ids:
                    full = ', '.join([x for x in (r['addr'], r['city'], r['state'], r['zip']) if (x or '').strip()])
                    bill.setdefault(r['donor_id'], set()).add(full)
            rej = set()
            try:
                for r in con.execute("SELECT donor_id,addr FROM addr_reject"):
                    rej.add((r['donor_id'], (r['addr'] or '').strip()))
            except Exception:
                pass
            con.close()
            book = []
            try:
                with open(os.path.join(HERE, 'address_maps_seed.json'), encoding='utf-8') as f:
                    book = json.load(f)
            except Exception:
                book = []
            out = []
            for d in rows:
                sug = []
                if (d['first'] or '').strip():
                    cand = [x for x in book
                            if _fz(x.get('last') or '') == _fz(d['last'] or '')
                            and _same_first(x.get('first') or '', d['first'] or '')]
                    for x in cand[:3]:
                        sug.append({'addr': (x.get('addr') or '').replace('\n', ' ').strip(),
                                    'phone': ', '.join(x.get('phones') or []),
                                    'who': ((x.get('last') or '') + ' ' + (x.get('first') or '')).strip(),
                                    'src': 'אנשי קשר'})
                for a in sorted(bill.get(d['id'], []))[:3]:
                    sug.append({'addr': a, 'phone': '', 'who': '', 'src': 'כתובת חיוב'})
                sug = [s for s in sug if s['addr'] and (d['id'], s['addr']) not in rej]
                out.append({'id': d['id'],
                            'name': ((d['last'] or '') + ' ' + (d['first'] or '')).strip(),
                            'english': d['english'] or '', 'phone': d['phone'] or '',
                            'email': d['email'] or '', 'total': tot.get(d['id'], 0), 'suggest': sug})
            out.sort(key=lambda x: (-len(x['suggest']), -x['total']))
            return self._send(200, {'ok': True, 'count': len(out),
                                    'with_suggest': sum(1 for x in out if x['suggest']), 'people': out})
        if self.path.split('?')[0] == '/api/audit/unknown':
            # תורמים שמופיעים בחיובים ואין להם כרטיס — מקובצים לפי אדם, לא לפי חיוב
            con = db()
            try:
                import gmail_intake as _giu
            except Exception:
                _giu = None
            grp = {}
            for r in con.execute("SELECT tid,first,last,amount,date,email,phone,addr,city,state,zip,source "
                                 "FROM recon WHERE donor_id IS NULL AND COALESCE(processed,0)=0 "
                                 "AND COALESCE(status,'settled')='settled'"):
                em = (emails_of(r['email']) or [''])[0]
                key = em or _lat((r['first'] or '') + ' ' + (r['last'] or '')) or r['tid']
                g = grp.setdefault(key, {'name': ((r['first'] or '') + ' ' + (r['last'] or '')).strip(),
                                         'email': em, 'phone': r['phone'] or '', 'addr': r['addr'] or '',
                                         'city': r['city'] or '', 'state': r['state'] or '', 'zip': r['zip'] or '',
                                         'first': r['first'] or '', 'last': r['last'] or '',
                                         'n': 0, 'total': 0.0, 'src': set(), 'tids': [], 'dates': []})
                g['n'] += 1
                g['total'] += float(r['amount'] or 0)
                s0 = r['source'] or ''
                g['src'].add('בנק ווסט' if 'Banquest' in s0 else
                             'PayPal' if 'PayPal' in s0 else
                             s0 if not s0.startswith('Authorize') else 'אוטרייז')
                g['tids'].append(r['tid'])
                g['dates'].append(_recon_iso(r['date']) or r['date'])
                for f in ('phone', 'addr', 'city', 'zip'):
                    if not g[f] and r[f]:
                        g[f] = r[f]
            out = []
            dall = [dict(r) for r in con.execute("SELECT id,last,first FROM donors")]
            for g in grp.values():
                g['src'] = ' · '.join(sorted(g['src']))
                g['total'] = round(g['total'], 2)
                g['dates'] = sorted(d for d in g['dates'] if d)
                if _giu:
                    try:
                        g['he_last'] = _giu._he_name(g['last'])
                        g['he_first'] = _giu._he_name(g['first'])
                    except Exception:
                        g['he_last'] = g['he_first'] = ''
                else:
                    g['he_last'] = g['he_first'] = ''
                # הצעות: כרטיסים קיימים עם שם משפחה דומה — קליק אחד לשיוך במקום חיפוש
                g['suggest'] = []
                hk = _fz(g.get('he_last') or '')
                if len(hk) >= 3:
                    for d in dall:
                        dk = _fz(d['last'])
                        if len(dk) >= 3 and (dk == hk or dk in hk or hk in dk):
                            g['suggest'].append({'id': d['id'],
                                                 'name': ((d['last'] or '') + ' ' + (d['first'] or '')).strip()})
                        if len(g['suggest']) >= 4:
                            break
                out.append(g)
            out.sort(key=lambda x: -x['total'])
            con.close()
            return self._send(200, {'ok': True, 'groups': out,
                                    'total': round(sum(x['total'] for x in out), 2)})
        if self.path.split('?')[0] == '/api/audit/charges':
            # הצלבה של כל החיובים שטרם אושרו מול דוח הקבועים, רשימות החגים והוראות הקבע
            con = db()
            camp, subs = {}, {}
            try:
                with open(os.path.join(HERE, 'campaign_lists.json'), encoding='utf-8') as f:
                    for L in json.load(f).get('lists', []):
                        for x in campaign_match(con, L['rows'], L.get('from', ''), L.get('to', '')):
                            if x['donor_id']:
                                camp.setdefault(x['donor_id'], []).append((x['amount'], L['label']))
            except Exception:
                pass
            try:
                with open(os.path.join(HERE, 'donations_2026_seed.json'), encoding='utf-8') as f:
                    for r in json.load(f):
                        subs.setdefault(r['donor_id'], set()).add(round(float(r['amount']), 2))
            except Exception:
                pass
            names = {r['id']: ((r['last'] or '') + ' ' + (r['first'] or '')).strip()
                     for r in con.execute("SELECT id,last,first FROM donors")}
            out = []
            for r in con.execute("""SELECT tid,donor_id,first,last,amount,date,source,recurring FROM recon
                                    WHERE COALESCE(processed,0)=0 AND COALESCE(status,'settled')='settled'
                                    ORDER BY donor_id IS NOT NULL, last, first"""):
                a = round(float(r['amount'] or 0), 2)
                s0 = r['source'] or ''
                src = ('בנק ווסט' if 'Banquest' in s0 else
                       s0 if not s0.startswith('Authorize') else 'אוטרייז')
                why = ''
                if r['donor_id']:
                    why = next((c for amt, c in camp.get(r['donor_id'], []) if abs(amt - a) < 0.01), '')
                    if not why and r['recurring']:
                        why = 'הוראת קבע'
                    if not why and any(abs(x - a) < 0.01 for x in subs.get(r['donor_id'], ())):
                        why = 'דוח הקבועים'
                out.append({'tid': r['tid'], 'name': ((r['first'] or '') + ' ' + (r['last'] or '')).strip(),
                            'amount': a, 'date': r['date'], 'src': src, 'donor_id': r['donor_id'],
                            'donor_name': names.get(r['donor_id'], ''), 'why': why,
                            'bucket': ('nocard' if not r['donor_id'] else ('ok' if why else 'check'))})
            con.close()
            return self._send(200, {'ok': True, 'rows': out})
        if self.path.split('?')[0] == '/api/import/lists':
            # הרשימות שכבר הוזנו למערכת (פורים/פסח תשפ״ו) — לטעינה בלחיצה בדף הייבוא
            try:
                with open(os.path.join(HERE, 'campaign_lists.json'), encoding='utf-8') as f:
                    return self._send(200, json.load(f))
            except Exception:
                return self._send(200, {'lists': []})
        if self.path.split('?')[0] in ('/audit', '/audit.html'):
            return self._send(200, open(os.path.join(STATIC, 'audit.html'), 'rb').read(), 'text/html')
        if self.path.split('?')[0] in ('/import', '/import.html'):
            return self._send(200, open(os.path.join(STATIC, 'import.html'), 'rb').read(), 'text/html')
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
                x['rule_cat'] = x['rule_note'] = ''
                if r['donor_id']:
                    try:
                        _rr = con.execute("SELECT category,note FROM donor_rules WHERE donor_id=? AND ROUND(amount,2)=?",
                                          (r['donor_id'], round(float(r['amount'] or 0), 2))).fetchone()
                        if _rr:
                            x['rule_cat'] = _rr['category'] or ''
                            x['rule_note'] = _rr['note'] or ''
                    except Exception:
                        pass
                x['kv_names'] = ''
                ems = emails_of(r['email'])
                if r['donor_id']:                       # גם שאר כתובות המייל של אותו תורם
                    _dr = con.execute("SELECT email FROM donors WHERE id=?", (r['donor_id'],)).fetchone()
                    for _e in (emails_of(_dr['email']) if _dr else []):
                        if _e not in ems: ems.append(_e)
                if ems:
                    try:
                        nm = [q['names'] for q in con.execute(
                            """SELECT names FROM intake WHERE lower(TRIM(from_email)) IN (%s)
                               AND COALESCE(TRIM(names),'')<>'' ORDER BY id DESC LIMIT 3"""
                            % ','.join('?' * len(ems)), ems)]
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
        if self.path.split('?')[0] == '/api/audit/excel':
            # השוואה: תרומות שיובאו מהאקסל מול החיובים שנגבו בפועל (רק בתקופה שהאקסל מכסה)
            con = db()
            MON = {'Jan':'01','Feb':'02','Mar':'03','Apr':'04','May':'05','Jun':'06','Jul':'07',
                   'Aug':'08','Sep':'09','Oct':'10','Nov':'11','Dec':'12'}
            def _iso(d):
                m = re.match(r'(\d{2})-([A-Za-z]{3})-(\d{4})', d or '')
                return f"{m.group(3)}-{MON.get(m.group(2),'01')}" if m else ''
            rng = con.execute("""SELECT MIN(substr(date,1,7)) a, MAX(substr(date,1,7)) b FROM donations
                                 WHERE note='ייבוא 2026' AND method IN ('Authorize','Banquest')""").fetchone()
            lo, hi = (rng['a'] or '0000-00'), (rng['b'] or '9999-99')
            xl = {}
            for r in con.execute("""SELECT donor_id,method,date,amount FROM donations
                                    WHERE note='ייבוא 2026' AND method IN ('Authorize','Banquest')"""):
                m7 = (r['date'] or '')[:7]
                if lo <= m7 <= hi:
                    d = xl.setdefault(r['donor_id'], {}).setdefault(r['method'], {'n': 0, 's': 0.0})
                    d['n'] += 1; d['s'] += float(r['amount'] or 0)
            rc = {}
            for r in con.execute("SELECT donor_id,source,date,amount,status FROM recon WHERE donor_id IS NOT NULL"):
                if (r['status'] or 'settled') != 'settled':
                    continue
                m7 = _iso(r['date'])
                if not (lo <= m7 <= hi):
                    continue
                m = 'Banquest' if 'Banquest' in (r['source'] or '') else 'Authorize'
                d = rc.setdefault(r['donor_id'], {}).setdefault(m, {'n': 0, 's': 0.0})
                d['n'] += 1; d['s'] += float(r['amount'] or 0)
            names = {r['id']: (r['last'] + ' ' + (r['first'] or '')).strip()
                     for r in con.execute("SELECT id,last,first FROM donors")}
            out = []
            for did in set(list(xl) + list(rc)):
                if did not in names:
                    continue
                for m in ('Authorize', 'Banquest'):
                    a = xl.get(did, {}).get(m, {'n': 0, 's': 0.0})
                    b2 = rc.get(did, {}).get(m, {'n': 0, 's': 0.0})
                    diff = round(b2['s'] - a['s'], 2)
                    if abs(diff) < 1:
                        continue
                    out.append({'id': did, 'name': names[did], 'method': m,
                                'xl_n': a['n'], 'xl_sum': round(a['s'], 2),
                                'rc_n': b2['n'], 'rc_sum': round(b2['s'], 2), 'diff': diff})
            out.sort(key=lambda x: -abs(x['diff']))
            con.close()
            return self._send(200, {'from': lo, 'to': hi, 'items': out})
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
                        if ce in emails_of(d['email']):      # כל אחת מכתובות המייל של התורם
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
        if self.path == '/api/mail/paypal_sync/status':
            try:
                import gmail_intake
                return self._send(200, dict(gmail_intake.PP_STATUS))
            except Exception as e:
                return self._send(200, {'running': False, 'done': True, 'error': str(e)})
        if self.path == '/api/contacts/pull/status':
            try:
                import gcontacts
                return self._send(200, dict(gcontacts.STATUS))
            except Exception as e:
                return self._send(200, {'running': False, 'done': True, 'error': str(e)})
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
        bump_data()
        m = re.match(r'/api/recon/(.+)/donor$', self.path)
        if m:
            # שיוך שורת חיוב לכרטיס תורם קיים — מדף האימות
            b = self._body(); tid = urllib.parse.unquote(m.group(1))
            try:
                did = int(b.get('donor_id'))
            except (TypeError, ValueError):
                return self._send(400, {'error': 'donor_id required'})
            con = db()
            if not con.execute("SELECT 1 FROM donors WHERE id=?", (did,)).fetchone():
                con.close(); return self._send(404, {'error': 'donor not found'})
            con.execute("UPDATE recon SET donor_id=? WHERE tid=?", (did, tid))
            con.commit(); con.close()
            return self._send(200, {'ok': True, 'donor_id': did})
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
            con.execute("UPDATE pledges SET category=?,amount=?,status=?,note=?,monthly=? WHERE id=?",
                        (b.get('category',''), b.get('amount',''), b.get('status',''), b.get('note',''),
                         1 if b.get('monthly') else 0, pid))
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
            # ברגע שנקבע ייעוד — ההערה "לא סווג — לבדוק עבור מה" כבר לא נכונה
            if (b.get('category') or '').strip() and 'note' not in b:
                sets.append("note=TRIM(REPLACE(COALESCE(note,''),' · לא סווג — לבדוק עבור מה',''))")
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
            con = db(); cur = con.cursor(); sets = []; vals = []
            for k in ('due_date','kind','note','assignee'):
                if k in b: sets.append(f'{k}=?'); vals.append(b[k])
            if sets:
                cur.execute("UPDATE tasks SET " + ",".join(sets) + " WHERE id=?", vals + [pid])
            clog = None
            if 'done' in b:   # הווי נרשם גם בדף הקשר של התורם — מה נעשה, מתי, ובידי מי
                clog = task_done_log(cur, pid, done=bool(int(b.get('done') or 0)),
                                     by=b.get('done_by', ''),
                                     when=b.get('done_at', '') or b.get('done_date', ''))
            elif sets:        # עריכת משימה שכבר בוצעה — גם הרישום בכרטיס מתעדכן
                clog = task_log_sync(cur, pid)
            con.commit(); con.close()
            return self._send(200, {'ok': True, 'contact': clog})
        m = re.match(r'/api/partner/(\d+)$', self.path)
        if m:
            b = self._body(); pid = int(m.group(1))
            if 'joint_payer' in b:      # מי שמשלם בפועל — שייך לקבוצה כולה
                try:
                    con0 = db()
                    row = con0.execute("SELECT avreich FROM partners WHERE id=?", (pid,)).fetchone()
                    if row:
                        con0.execute("UPDATE partners SET joint_payer=? WHERE COALESCE(active,1)<>0 "
                                     "AND COALESCE(joint,0)<>0 AND TRIM(avreich)=TRIM(?)",
                                     (b.get('joint_payer') or None, row['avreich']))
                        con0.commit()
                    con0.close()
                except Exception as e:
                    print('  joint payer error:', e)
            con = db(); sets = []; vals = []
            for k in ('avreich','start_date','amount','note','active','ended_date','method','partner_with','partner_with_id','paid_note','paid_thru','renew_date','joint','joint_payer','share'):
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
        bump_data()
        # Authorize.net מודיע ברגע שחיוב עבר. מאמתים חתימה, מושכים את העסקה,
        # ורושמים אותה. חייב להיות לפני קריאת הגוף כ-JSON — החתימה על הגוף הגולמי.
        if self.path.split('?')[0] == '/api/authorize/webhook':
            try:
                import authorize_sync as anet
                raw = self.rfile.read(int(self.headers.get('Content-Length') or 0))
                if not anet.verify(raw, self.headers.get('X-ANET-Signature')):
                    return self._send(401, {'ok': False, 'error': 'bad_signature'})
                ev = json.loads(raw or b'{}')
                tid = anet.webhook_tid(ev)
                con = db()
                res = anet.sync(con, link=link_by_identity, only_tid=tid) if tid else {}
                con.close()
                ANETSTAT.update(last=now_iso(), last_ok=now_iso(), hooks=ANETSTAT['hooks'] + 1,
                                result=str(res), error='')
                print('  Authorize webhook:', ev.get('eventType', ''), tid, res)
                return self._send(200, {'ok': True, 'result': res})
            except Exception as e:
                ANETSTAT.update(last=now_iso(), error=str(e)[:200])
                print('  שגיאת webhook של Authorize:', e)
                return self._send(200, {'ok': False, 'error': str(e)[:200]})
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
        if self.path == '/api/intake/diag':
            try:
                import gmail_intake
            except Exception as e:
                return self._send(200, {'ok': False, 'error': 'module', 'detail': str(e)})
            return self._send(200, gmail_intake.diag(21))
        if self.path == '/api/intake/sync':
            try:
                import gmail_intake
            except Exception as e:
                return self._send(200, {'ok': False, 'error': 'module', 'detail': str(e)})
            con = db(); res = gmail_intake.sync(con); con.close()
            return self._send(200, res)
        if self.path == '/api/mail/paypal_sync':     # משיכת תשלומי PayPal מהמייל ומהספאם — ברקע
            try:
                import gmail_intake, threading
            except Exception as e:
                return self._send(200, {'ok': False, 'error': 'module', 'detail': str(e)})
            if not gmail_intake.configured():
                return self._send(200, {'ok': False, 'error': 'not_configured'})
            stt = gmail_intake.PP_STATUS
            if stt.get('running'):
                return self._send(200, {'ok': True, 'started': False, 'already': True, 'status': stt})
            stt.update({'running': True, 'new': 0, 'scanned': 0, 'total': 0, 'done': False,
                        'error': '', 'unparsed': []})
            def _runpp():
                c = db()
                try:
                    r = gmail_intake.sync_paypal(c, stt)
                    if not r.get('ok'):
                        stt['error'] = r.get('detail') or r.get('error') or 'שגיאה'
                    else:
                        stt['new'] = r.get('new', 0); stt['dup'] = r.get('dup', 0)
                except Exception as e:
                    stt['error'] = '%s: %s' % (type(e).__name__, e)
                finally:
                    try: c.close()
                    except Exception: pass
                    stt['running'] = False; stt['done'] = True
            threading.Thread(target=_runpp, daemon=True).start()
            return self._send(200, {'ok': True, 'started': True})
        if self.path == '/api/contacts/csv':   # קובץ אנשי קשר של גוגל — השלמת כתובות ממנו
            try:
                import gcontacts
            except Exception as e:
                return self._send(200, {'ok': False, 'error': 'module', 'detail': str(e)})
            txt = b.get('text') or ''
            if len(txt) < 20:
                return self._send(200, {'ok': False, 'error': 'empty'})
            try:
                cards = gcontacts.parse_any(txt)      # Google CSV או VCF מהטלפון
            except Exception as e:
                return self._send(200, {'ok': False, 'error': 'parse', 'detail': str(e)})
            if not cards:
                return self._send(200, {'ok': False, 'error': 'no_contacts'})
            con = db()
            try:
                res = contacts_fill(con, cards)
            finally:
                con.close()
            return self._send(200, res)
        if self.path == '/api/contacts/pull':   # משיכת אנשי הקשר מגוגל והשלמת כתובות — ברקע
            try:
                import gcontacts, threading
            except Exception as e:
                return self._send(200, {'ok': False, 'error': 'module', 'detail': str(e)})
            if not gcontacts.configured():
                return self._send(200, {'ok': False, 'error': 'not_configured'})
            stt = gcontacts.STATUS
            if stt.get('running'):
                return self._send(200, {'ok': True, 'started': False, 'already': True})
            stt.update({'running': True, 'done': False, 'error': '',
                        'found': 0, 'filled': 0, 'scanned': 0, 'result': None})

            def _runc():
                c = db()
                try:
                    cards = gcontacts.fetch(stt)
                    stt['result'] = contacts_fill(c, cards, stt)
                except Exception as e:
                    stt['error'] = str(e)
                finally:
                    try: c.close()
                    except Exception: pass
                    stt['running'] = False; stt['done'] = True
            threading.Thread(target=_runc, daemon=True).start()
            return self._send(200, {'ok': True, 'started': True})
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
                    # תשובה שנמשכה לפני המייל שעליו ענו — מחוברת עכשיו
                    try: link_mail_replies(c)
                    except Exception: pass
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
            # אם הכתובת כבר קיימת אצל תורם — מצרפים אליו במקום לפתוח כרטיס כפול
            if '@' in email:
                for d0 in con.execute("SELECT id,last,first,email FROM donors "
                                      "WHERE TRIM(COALESCE(email,''))<>''"):
                    if email in emails_of(d0['email']):
                        if text:
                            con.execute("INSERT INTO prayers(donor_id,name,text,tier) "
                                        "VALUES(?,'',?,'')", (d0['id'], text))
                        con.execute("UPDATE intake SET donor_id=?, status='handled' WHERE id=?",
                                    (d0['id'], iid))
                        con.commit(); con.close()
                        nm = (d0['last'] + ' ' + (d0['first'] or '')).strip()
                        return self._send(200, {'ok': True, 'id': d0['id'], 'existing': True,
                                                'name': nm})
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
            try: con.execute("DELETE FROM deleted_donors WHERE key=?",
                             (_dkey(b.get('last',''), b.get('first','')),))
            except Exception: pass
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
        m = re.match(r'/api/contact/(\d+)/translate$', self.path)
        if m:   # תרגום המייל לעברית ושמירתו — פעם אחת לכל מייל
            cid = int(m.group(1))
            con = db(); r = con.execute("SELECT body, body_he FROM contacts_log WHERE id=?", (cid,)).fetchone()
            if not r:
                con.close(); return self._send(404, {'error': 'not found'})
            if (r['body_he'] or '').strip():
                con.close(); return self._send(200, {'ok': True, 'he': r['body_he'], 'cached': True})
            src = (b.get('text') or r['body'] or '').strip()
            if not src:
                con.close(); return self._send(200, {'ok': False, 'error': 'empty'})
            try:
                import gmail_intake as _gi
                he = _gi.translate_he(src)
            except Exception as e:
                con.close(); return self._send(200, {'ok': False, 'error': 'module', 'detail': str(e)})
            if not he:
                con.close(); return self._send(200, {'ok': False, 'error': 'שירות התרגום לא זמין כרגע'})
            con.execute("UPDATE contacts_log SET body_he=? WHERE id=?", (he, cid))
            con.commit(); con.close()
            return self._send(200, {'ok': True, 'he': he})
        m = re.match(r'/api/contact/(\d+)/reply$', self.path)
        if m:   # "עניתי לו" — התשובה נשמרת תלויה בפנייה עצמה, ולא כרישום נפרד
            cid = int(m.group(1))
            con = db(); cur = con.cursor()
            par = cur.execute("SELECT * FROM contacts_log WHERE id=?", (cid,)).fetchone()
            if not par:
                con.close(); return self._send(404, {'error': 'not found'})
            root = par['reply_to'] or cid       # תשובה על תשובה נתלית באותה פנייה מקורית
            txt = (b.get('text') or '').strip()
            at = (b.get('at') or '').strip() or now_iso()
            day = (b.get('date') or '').strip() or at[:10]
            summary = txt or 'עניתי לו'
            cur.execute("""INSERT INTO contacts_log(donor_id,date,channel,summary,next_date,
                                                    direction,reply_to,at)
                           VALUES(?,?,?,?,'','out',?,?)""",
                        (par['donor_id'], day, par['channel'] or 'אימייל', summary, root, at))
            rid = cur.lastrowid
            con.commit(); con.close()
            return self._send(200, {'ok': True, 'contact': {
                'id': rid, 'donor_id': par['donor_id'], 'date': day, 'channel': par['channel'] or 'אימייל',
                'summary': summary, 'next_date': '', 'direction': 'out', 'reply_to': root, 'at': at}})
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
            if res.get('ok'):
                log_sent_mail(p['donor_id'], to, subject, body, res.get('msg_id'), len(atts))
            res['to'] = to
            res['count'] = len(atts)
            return self._send(200, res)
        # סימון ידני של חיוב שנדחה כחוב אמיתי (או ביטול הסימון). חיוב שנדחה
        # לא נספר בחוב מעצמו — רק מה שמאיר סימן כאן.
        if self.path in ('/api/recon/debt', '/api/recon/nodebt'):
            tids = b.get('tids') or ([b['tid']] if b.get('tid') else [])
            on = 0 if b.get('undo') else 1
            col = 'no_debt' if self.path.endswith('nodebt') else 'is_debt'
            if not tids:
                return self._send(400, {'error': 'no tid'})
            con = db()
            for t in tids:
                con.execute("UPDATE recon SET %s=? WHERE tid=?" % col, (on, str(t)))
            con.commit(); con.close()
            return self._send(200, {'ok': True, 'n': len(tids)})
        if self.path == '/api/campaigns':
            nm = (b.get('name') or '').strip()
            if nm and b.get('delete'):        # מחיקת ייעוד מהרשימה. תרומות שכבר סווגו לא נוגעים בהן
                con = db()
                used = con.execute("SELECT COUNT(*) FROM donations WHERE TRIM(COALESCE(category,''))=?",
                                   (nm,)).fetchone()[0]
                if used and not b.get('force'):
                    con.close()
                    return self._send(200, {'ok': False, 'error': 'in_use', 'used': used})
                if b.get('force') and used:    # משחררים את התרומות לסיווג מחדש
                    con.execute("UPDATE donations SET category='' WHERE TRIM(COALESCE(category,''))=?", (nm,))
                con.execute("DELETE FROM campaigns WHERE name=?", (nm,))
                try: con.execute("DELETE FROM donor_rules WHERE TRIM(COALESCE(category,''))=?", (nm,))
                except Exception: pass
                con.commit(); con.close()
                return self._send(200, {'ok': True, 'deleted': nm, 'freed': used})
            if nm:
                con = db(); con.execute("INSERT OR IGNORE INTO campaigns(name,created) VALUES(?,?)", (nm, today_iso())); con.commit(); con.close()
            return self._send(200, {'ok': True, 'name': nm})
        m = re.match(r'/api/donation/(\d+)/split$', self.path)
        if m:      # פיצול תרומה אחת לכמה ייעודים — הסכומים חייבים להסתכם במקורי
            did = int(m.group(1))
            parts = [p for p in (b.get('parts') or []) if str(p.get('amount') or '').strip()]
            con = db()
            row = con.execute("SELECT * FROM donations WHERE id=?", (did,)).fetchone()
            if not row:
                con.close(); return self._send(404, {'error': 'not found'})
            def _n(x):
                try:
                    return round(float(re.sub(r'[^0-9.]', '', str(x or '0')) or 0), 2)
                except Exception:
                    return 0.0
            tot = _n(row['amount'])
            ssum = round(sum(_n(p['amount']) for p in parts), 2)
            if len(parts) < 2:
                con.close(); return self._send(200, {'ok': False, 'error': 'צריך לפחות שני חלקים'})
            if abs(ssum - tot) > 0.5:
                con.close()
                return self._send(200, {'ok': False,
                                        'error': 'הסכומים לא מסתכמים לסכום המקורי (%s במקום %s)'
                                                 % (ssum, tot)})
            base = dict(row)
            # מעתיקים כל עמודה שקיימת בפועל בטבלה, חוץ ממה שמשתנה בפיצול
            cols = [c[1] for c in con.execute("PRAGMA table_info(donations)")
                    if c[1] not in ('id', 'amount', 'category', 'note')]
            newids = []
            for p in parts:
                cat = (p.get('category') or '').strip()
                if cat:
                    con.execute("INSERT OR IGNORE INTO campaigns(name,created) VALUES(?,?)", (cat, today_iso()))
                note = (base.get('note') or '').strip()
                note = (note + ' · ' if note else '') + 'פוצל מתרומה של $%s' % base['amount']
                names = cols + ['amount', 'category', 'note']
                vals = [base.get(c) for c in cols] + [str(_n(p['amount'])), cat, note[:400]]
                cur2 = con.execute("INSERT INTO donations(%s) VALUES(%s)"
                                   % (','.join(names), ','.join('?' * len(names))), vals)
                newids.append(cur2.lastrowid)
            con.execute("DELETE FROM donations WHERE id=?", (did,))
            con.commit(); con.close()
            return self._send(200, {'ok': True, 'ids': newids})
        if self.path == '/api/audit/phones':
            did = int(b.get('donor_id') or 0)
            ph = (b.get('phone') or '').strip()
            con = db()
            if did and b.get('reject') and ph:
                con.execute("INSERT INTO sugg_reject(donor_id,kind,val,created) VALUES(?,'phone',?,?)",
                            (did, ph, today_iso()))
            elif did and b.get('skip'):        # לא לשאול יותר על התורם הזה
                con.execute("INSERT INTO sugg_reject(donor_id,kind,val,created) VALUES(?,'phone','*',?)",
                            (did, today_iso()))
                for r in con.execute("SELECT val FROM sugg_reject WHERE donor_id=? AND kind='phone'", (did,)):
                    pass
            elif did and ph:
                con.execute("UPDATE donors SET phone=? WHERE id=? AND TRIM(COALESCE(phone,''))=''", (ph, did))
                if b.get('email'):
                    con.execute("UPDATE donors SET email=? WHERE id=? AND TRIM(COALESCE(email,''))=''",
                                (b['email'], did))
            con.commit(); con.close()
            return self._send(200, {'ok': True})
        if self.path == '/api/taskkinds':
            # סוגי משימה שהמשתמש מגדיר בעצמו — למשל "לבדוק יששכר זבולון שלו"
            nm = re.sub(r'\s+', ' ', (b.get('name') or '')).strip()[:60]
            con = db()
            if nm and b.get('delete'):
                con.execute("DELETE FROM task_kinds WHERE name=?", (nm,))
            elif nm:
                con.execute("INSERT OR IGNORE INTO task_kinds(name,created) VALUES(?,?)", (nm, today_iso()))
            names = [r['name'] for r in con.execute("SELECT name FROM task_kinds ORDER BY created, name")]
            con.commit(); con.close()
            return self._send(200, {'ok': True, 'name': nm, 'kinds': names})
        if self.path == '/api/deposits/map':
            # שיוך שם מפקיד לתורם — כל השורות שלו, וגם כל מה שיגיע בעתיד
            key = _nkey(b.get('name') or '')
            did = int(b.get('donor_id') or 0)
            if not key:
                return self._send(400, {'ok': False, 'error': 'no_name'})
            con = db(); cur = con.cursor()
            if b.get('ignore'):
                cur.execute("INSERT OR REPLACE INTO name_map(src,donor_id,ignored,created) "
                            "VALUES(?,NULL,1,?)", (key, today_iso()))
                cur.execute("DELETE FROM recon WHERE donor_id IS NULL AND tid IN (%s)"
                            % ','.join('?' * len(b.get('tids') or [])), (b.get('tids') or []))
                con.commit(); con.close()
                return self._send(200, {'ok': True, 'ignored': True})
            if not cur.execute("SELECT 1 FROM donors WHERE id=?", (did,)).fetchone():
                con.close(); return self._send(400, {'ok': False, 'error': 'no_donor'})
            cur.execute("INSERT OR REPLACE INTO name_map(src,donor_id,ignored,created) "
                        "VALUES(?,?,0,?)", (key, did, today_iso()))
            n = apply_name_map(con)
            sp = apply_pay_split(con)        # תורם שמתחלק עם שותף — הסכום נחתך מיד
            con.commit(); con.close()
            return self._send(200, {'ok': True, 'linked': n, 'split': sp})
        if self.path == '/api/authorize/sync':
            # "משוך עכשיו" מהמסך — סורק את הימים האחרונים ומכניס מה שחסר
            try:
                import authorize_sync as anet
            except Exception as e:
                return self._send(200, {'ok': False, 'error': 'המודול לא נטען: %s' % e})
            if not anet.configured():
                return self._send(200, {'ok': False, 'error': 'not_configured'})
            try:
                con = db()
                res = anet.sync(con, days=int(b.get('days') or 10), link=link_by_identity)
                con.close()
                ANETSTAT.update(last=now_iso(), last_ok=now_iso(), result=str(res), error='',
                                runs=ANETSTAT['runs'] + 1)
                return self._send(200, {'ok': True, 'result': res})
            except Exception as e:
                ANETSTAT.update(last=now_iso(), error=str(e)[:200])
                return self._send(200, {'ok': False, 'error': str(e)[:250]})
        if self.path == '/api/paysplit':
            # שני תורמים ששולחים לבנק סכום אחד ומתחלקים בו
            con = db(); cur = con.cursor()
            if b.get('delete'):
                cur.execute("DELETE FROM pay_split WHERE id=?", (int(b.get('id') or 0),))
                con.commit(); con.close()
                return self._send(200, {'ok': True, 'deleted': True})
            pid, did = int(b.get('payer_id') or 0), int(b.get('donor_id') or 0)
            try: pct = float(b.get('pct') or 50)
            except Exception: pct = 50.0
            if not pid or not did or pid == did or not (0 < pct < 100):
                con.close(); return self._send(400, {'ok': False, 'error': 'bad_args'})
            for x in (pid, did):
                if not cur.execute("SELECT 1 FROM donors WHERE id=?", (x,)).fetchone():
                    con.close(); return self._send(400, {'ok': False, 'error': 'no_donor'})
            cur.execute("INSERT OR REPLACE INTO pay_split(payer_id,donor_id,pct,note,created) "
                        "VALUES(?,?,?,?,?)", (pid, did, pct, (b.get('note') or '').strip()[:120],
                                              today_iso()))
            n = apply_pay_split(con)
            con.commit(); con.close()
            return self._send(200, {'ok': True, 'split': n})
        if self.path == '/api/avreich':
            # הוספה/עריכה/מחיקה של אברך ברשימת הכולל
            nm = re.sub(r'\s+', ' ', (b.get('name') or '')).strip()[:60]
            aid = b.get('id')
            con = db(); cur = con.cursor()
            if b.get('delete') and aid:
                r = cur.execute("SELECT name FROM avreichim WHERE id=?", (aid,)).fetchone()
                anm = r['name'] if r else ''
                held = [x for x in cur.execute(
                    "SELECT p.id,p.donor_id,d.last,d.first FROM partners p LEFT JOIN donors d ON d.id=p.donor_id "
                    "WHERE TRIM(p.avreich)=? AND COALESCE(p.active,1)<>0", (anm,))]
                if held and not b.get('force'):
                    con.close()
                    return self._send(200, {'ok': False, 'error': 'held', 'count': len(held),
                                            'who': [((x['last'] or '') + ' ' + (x['first'] or '')).strip()
                                                    for x in held]})
                at = (b.get('at') or '').strip() or now_iso()
                for x in held:      # השותפויות מסתיימות, וכל תורם מקבל שורה בדף הקשר
                    cur.execute("UPDATE partners SET active=0, ended_date=? WHERE id=?", (at[:10], x['id']))
                    iz_log(cur, anm, x['donor_id'],
                           '🚪 האברך %s יצא מהכולל — השותפות הסתיימה' % anm, at)
                if not held:
                    iz_log(cur, anm, None, '🚪 האברך %s יצא מהכולל' % anm, at)
                cur.execute("UPDATE avreichim SET ended=? WHERE id=?", (at[:10], aid))
            elif aid:
                sets, vals = [], []
                for k in ('note', 'started', 'phone', 'email', 'addr', 'ended'):
                    if k in b: sets.append(k + '=?'); vals.append(b[k])
                if nm:
                    l, f = _split_av(nm)
                    old = cur.execute("SELECT name FROM avreichim WHERE id=?", (aid,)).fetchone()
                    sets += ['name=?', 'last=?', 'first=?']; vals += [nm, l, f]
                    if old and old['name'] != nm:      # שינוי שם — גם אצל כל המחזיקים
                        cur.execute("UPDATE partners SET avreich=? WHERE TRIM(avreich)=?", (nm, old['name']))
                if sets:
                    cur.execute("UPDATE avreichim SET " + ','.join(sets) + " WHERE id=?", vals + [aid])
            elif nm:
                if cur.execute("SELECT 1 FROM avreichim WHERE name=?", (nm,)).fetchone():
                    con.close(); return self._send(200, {'ok': False, 'error': 'exists'})
                l, f = _split_av(nm)
                cur.execute("INSERT INTO avreichim(name,last,first,note,started,created) VALUES(?,?,?,?,?,?)",
                            (nm, l, f, (b.get('note') or ''), (b.get('started') or ''), today_iso()))
                aid = cur.lastrowid
            con.commit(); con.close()
            return self._send(200, {'ok': True, 'id': aid, 'name': nm})
        if self.path == '/api/avreich/holder':
            # עריכה מיידית של שורת אברך אצל תורם: תאריך, סכום, או העברה
            # לתורם אחר. כל שינוי נרשם אצל התורם, ומופיע מיד בשתי הרשימות.
            pid = int(b.get('pid') or 0)
            con = db(); cur = con.cursor()
            p = cur.execute("SELECT * FROM partners WHERE id=?", (pid,)).fetchone()
            if not p:
                con.close(); return self._send(404, {'ok': False, 'error': 'not_found'})
            dn = lambda i: (lambda r: ((r['last'] or '') + ' ' + (r['first'] or '')).strip() if r else '')(
                cur.execute("SELECT last,first FROM donors WHERE id=?", (i,)).fetchone())
            at = (b.get('at') or '').strip() or now_iso()
            logs = []
            sets, vals = [], []
            if 'start_date' in b and (b['start_date'] or '') != (p['start_date'] or ''):
                sets.append('start_date=?'); vals.append(b['start_date'])
                g = heb_anniv(b['start_date'] or '')
                sets.append('renew_date=?'); vals.append(g.isoformat() if g else None)
                logs.append((p['donor_id'], '📅 %s — תאריך ההתחלה שונה ל%s' % (p['avreich'], b['start_date'] or '—')))
            if 'amount' in b and str(b['amount'] or '') != str(p['amount'] or ''):
                sets.append('amount=?'); vals.append(b['amount'])
                logs.append((p['donor_id'], '💰 %s — הסכום שונה מ-%s ל-%s' % (
                    p['avreich'], (p['amount'] or '—'), (b['amount'] or '—'))))
            if 'share' in b:
                sets.append('share=?'); vals.append(b['share'])
            if 'avreich' in b:
                nm2 = re.sub(r'\s+', ' ', (b['avreich'] or '')).strip()
                if nm2 and nm2 != (p['avreich'] or ''):
                    sets.append('avreich=?'); vals.append(nm2)
                    logs.append((p['donor_id'], '🔀 האברך %s הוחלף ל%s' % (p['avreich'], nm2)))
            nd = int(b.get('donor_id') or 0)
            if nd and nd != p['donor_id']:
                if not cur.execute("SELECT 1 FROM donors WHERE id=?", (nd,)).fetchone():
                    con.close(); return self._send(400, {'ok': False, 'error': 'no_donor'})
                if cur.execute("SELECT 1 FROM partners WHERE donor_id=? AND TRIM(avreich)=? AND id<>? "
                               "AND COALESCE(active,1)<>0", (nd, p['avreich'], pid)).fetchone():
                    con.close(); return self._send(200, {'ok': False, 'error': 'already'})
                sets.append('donor_id=?'); vals.append(nd)
                logs.append((p['donor_id'], '↩️ האברך %s הועבר ל%s' % (p['avreich'], dn(nd))))
                logs.append((nd, '🤝 האברך %s הועבר לכאן מ%s' % (p['avreich'], dn(p['donor_id']))))
                cur.execute("UPDATE donors SET tier='יששכר_זבולון' WHERE id=? AND COALESCE(tier,'')<>'יששכר_זבולון'", (nd,))
            if b.get('remove'):
                cur.execute("UPDATE partners SET active=0, ended_date=? WHERE id=?", (at[:10], pid))
                logs.append((p['donor_id'], '❌ הפסיק את יששכר־זבולון עם האברך %s' % p['avreich']))
            elif sets:
                cur.execute("UPDATE partners SET " + ','.join(sets) + " WHERE id=?", vals + [pid])
            for did2, txt in logs:
                iz_log(cur, p['avreich'], did2, txt, at)
            con.commit(); con.close()
            return self._send(200, {'ok': True, 'changes': len(logs)})
        if self.path == '/api/avreich/assign':
            # שיוך אברך לתורם מתוך רשימת האברכים — נרשם אצל שניהם, עם תאריך
            aid = b.get('avreich_id'); did = int(b.get('donor_id') or 0)
            con = db(); cur = con.cursor()
            r = cur.execute("SELECT name,started FROM avreichim WHERE id=?", (aid,)).fetchone() if aid else None
            nm = (r['name'] if r else (b.get('name') or '')).strip()
            d = cur.execute("SELECT last,first,tier FROM donors WHERE id=?", (did,)).fetchone()
            if not nm or not d:
                con.close(); return self._send(400, {'ok': False, 'error': 'bad_input'})
            if cur.execute("SELECT 1 FROM partners WHERE donor_id=? AND TRIM(avreich)=? "
                           "AND COALESCE(active,1)<>0", (did, nm)).fetchone():
                con.close(); return self._send(200, {'ok': False, 'error': 'already'})
            at = (b.get('at') or '').strip() or now_iso()
            # לא הוקלד תאריך התחלה — נרשם היום, בתאריך העברי
            start = (b.get('start_date') or '').strip() or greg_to_heb_full(at[:10])
            amt = (b.get('amount') or '').strip()
            g = heb_anniv(start) if start else None
            cur.execute("INSERT INTO partners(donor_id,avreich,start_date,amount,active,renew_date) "
                        "VALUES(?,?,?,?,1,?)", (did, nm, start, amt, g.isoformat() if g else None))
            pid = cur.lastrowid
            if (d['tier'] or '') != 'יששכר_זבולון':      # שיוך אברך הופך אותו ליששכר־זבולון
                cur.execute("UPDATE donors SET tier='יששכר_זבולון' WHERE id=?", (did,))
            if r and not (r['started'] or '').strip() and start:
                cur.execute("UPDATE avreichim SET started=? WHERE id=?", (start, aid))
            dn = ((d['last'] or '') + ' ' + (d['first'] or '')).strip()
            iz_log(cur, nm, did, '🤝 התחיל יששכר־זבולון עם האברך %s%s%s' % (
                nm, (' · מ' + start) if start else '', (' · $' + amt) if amt else ''), at)
            con.commit(); con.close()
            return self._send(200, {'ok': True, 'pid': pid, 'donor': dn, 'name': nm,
                                    'start_date': start})
        if self.path == '/api/contactkinds':
            # סוגי קשר שמאיר מוסיף בעצמו — למשל "פגישה בבית" או "הודעה בפקס"
            nm = re.sub(r'\s+', ' ', (b.get('name') or '')).strip()[:40]
            con = db()
            if nm and b.get('delete'):
                con.execute("DELETE FROM contact_kinds WHERE name=?", (nm,))
            elif nm:
                con.execute("INSERT OR IGNORE INTO contact_kinds(name,created) VALUES(?,?)", (nm, today_iso()))
            names = [r['name'] for r in con.execute("SELECT name FROM contact_kinds ORDER BY created, name")]
            con.commit(); con.close()
            return self._send(200, {'ok': True, 'name': nm, 'kinds': names})
        if self.path == '/api/paychannels':
            # דרכי תשלום שמאיר מוסיף בעצמו — למשל קופה של גמ"ח או אפליקציה חדשה
            nm = re.sub(r'\s+', ' ', (b.get('name') or '')).strip()[:40]
            con = db()
            if nm and b.get('delete'):
                con.execute("DELETE FROM pay_channels WHERE name=?", (nm,))
            elif nm:
                con.execute("INSERT OR IGNORE INTO pay_channels(name,created) VALUES(?,?)", (nm, today_iso()))
            names = [r['name'] for r in con.execute("SELECT name FROM pay_channels ORDER BY created, name")]
            con.commit(); con.close()
            return self._send(200, {'ok': True, 'name': nm, 'channels': names})
        if self.path == '/api/building_items':
            nm = (b.get('name') or '').strip()
            if nm:
                con = db(); con.execute("INSERT OR IGNORE INTO building_items(name,created) VALUES(?,?)", (nm, today_iso())); con.commit(); con.close()
            return self._send(200, {'ok': True, 'name': nm})
        if self.path == '/api/donor':
            con = db(); cur = con.cursor()
            # נפתח מחדש כרטיס בשם שנמחק — הוא כבר לא נחשב "מחוק"
            try: cur.execute("DELETE FROM deleted_donors WHERE key=?",
                             (_dkey(b.get('last', ''), b.get('first', '')),))
            except Exception: pass
            cur.execute("""INSERT INTO donors(last,first,english,business,phone,email,addr,tier,category,purpose,amount,created,source,region,country,zip,city)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (b.get('last',''), b.get('first',''), b.get('english',''), b.get('business',''), b.get('phone',''),
                         b.get('email',''), b.get('addr',''), b.get('tier',''), b.get('category',''), b.get('purpose',''),
                         b.get('amount',''), today_iso(), 'ידני', b.get('region',''), b.get('country',''), norm_zip(b.get('zip',''), b.get('region','')), b.get('city','')))
            con.commit(); did = cur.lastrowid; con.close()
            return self._send(200, {'ok': True, 'id': did})
        if self.path == '/api/kvittel/dedup':
            con = db()
            try:
                rm, mg, dn = dedupe_prayers(con); con.commit()
            finally:
                con.close()
            return self._send(200, {'ok': True, 'removed': rm, 'merged': mg, 'donors': dn})
        if self.path == '/api/avreich/new':
            # הוספת אברך חדש לרשימה — רק דרך הפעולה הזו, לא בהקלדה חופשית
            nm = (b.get('name') or '').strip()
            if len(nm) < 2:
                return self._send(400, {'error': 'name required'})
            con = db()
            ex = con.execute("SELECT 1 FROM partners WHERE TRIM(avreich)=?", (nm,)).fetchone()
            if not ex:      # שורת שיוך ריקה שמחזיקה את השם ברשימה עד שישויך לתורם
                con.execute("INSERT INTO partners(donor_id,avreich,start_date,active,note) "
                            "VALUES(NULL,?,?,0,'נוסף לרשימת האברכים')", (nm, today_iso()))
            con.commit(); con.close()
            return self._send(200, {'ok': True, 'name': nm, 'existed': bool(ex)})
        if self.path == '/api/rule':
            # כלל קבוע: כל סכום X אצל התורם הזה = הייעוד הזה. מוחל גם על מה שכבר נרשם
            try:
                did = int(b.get('donor_id')); amt = round(float(b.get('amount')), 2)
            except (TypeError, ValueError):
                return self._send(400, {'error': 'donor_id/amount required'})
            cat = (b.get('category') or '').strip()
            note = (b.get('note') or '').strip()
            con = db(); cur = con.cursor()
            if b.get('delete'):
                cur.execute("DELETE FROM donor_rules WHERE donor_id=? AND ROUND(amount,2)=?", (did, amt))
                con.commit(); con.close()
                return self._send(200, {'ok': True, 'deleted': True})
            if not cat:
                con.close(); return self._send(400, {'error': 'category required'})
            BASE = {'קבוע', 'יששכר־זבולון', 'פרנס לילה', 'חדר קפה', 'ארוחת בוקר', 'נר למאור',
                    'קוויטל', 'מזדמן', 'חד-פעמי', 'אחר', 'בניין'}
            if cat not in BASE:
                cur.execute("INSERT OR IGNORE INTO campaigns(name,created) VALUES(?,?)", (cat, today_iso()))
            cur.execute("INSERT OR REPLACE INTO donor_rules(donor_id,amount,category,note,created) "
                        "VALUES(?,?,?,?,?)", (did, amt, cat, note, today_iso()))
            n = cur.execute("UPDATE donations SET category=? WHERE donor_id=? AND ROUND(CAST(amount AS REAL),2)=?",
                            (cat, did, amt)).rowcount
            if note:
                cur.execute("UPDATE donations SET note=TRIM(COALESCE(note,'')||' · '||?,' ·') "
                            "WHERE donor_id=? AND ROUND(CAST(amount AS REAL),2)=? AND COALESCE(note,'') NOT LIKE ?",
                            (note, did, amt, '%' + note + '%'))
            con.commit(); con.close()
            return self._send(200, {'ok': True, 'updated': n})
        if self.path == '/api/classify':
            # מענה על משימת "עבור מה" — מעדכן את התרומות בכרטיס התורם וסוגר את המשימה
            try:
                did = int(b.get('donor_id'))
            except (TypeError, ValueError):
                return self._send(400, {'error': 'donor_id required'})
            cat = (b.get('category') or '').strip()
            if not cat:
                return self._send(400, {'error': 'category required'})
            meth = (b.get('method') or '').strip()
            ids = [int(x) for x in (b.get('ids') or []) if str(x).isdigit()]
            con = db(); cur = con.cursor()
            BASE = {'קבוע', 'יששכר־זבולון', 'פרנס לילה', 'חדר קפה', 'ארוחת בוקר',
                    'נר למאור', 'קוויטל', 'מזדמן', 'חד-פעמי', 'אחר', 'בניין'}
            if cat not in BASE:
                cur.execute("INSERT OR IGNORE INTO campaigns(name,created) VALUES(?,?)", (cat, today_iso()))
            args = [cat, did]
            q = ("UPDATE donations SET category=?, "
                 "note=REPLACE(REPLACE(COALESCE(note,''),' · לא סווג — לבדוק עבור מה',''),' · לא סווג','') "
                 "WHERE donor_id=? AND COALESCE(note,'') LIKE '%לא סווג%'")
            if ids:                                  # סיווג של חיובים מסוימים בלבד
                q += " AND id IN (%s)" % ','.join('?' * len(ids)); args += ids
            if meth:
                q += " AND method=?"; args.append(meth)
            n = cur.execute(q, args).rowcount
            av = (b.get('avreich') or '').strip()
            if av:
                known = cur.execute("SELECT 1 FROM partners WHERE TRIM(avreich)=?", (av,)).fetchone()
                if not known:
                    con.close()
                    return self._send(400, {'error': 'unknown_avreich',
                                            'detail': 'האברך "%s" לא ברשימה — הוסף אותו קודם' % av})
            if av:
                # יששכר־זבולון — רושמים את האברך גם בשורת התרומה וגם ברשימת האברכים של התורם
                cur.execute("UPDATE donations SET note=TRIM(COALESCE(note,'')||' · '||?,' ·') "
                            "WHERE donor_id=? AND COALESCE(note,'') NOT LIKE ?" +
                            (" AND id IN (%s)" % ','.join('?' * len(ids)) if ids else ''),
                            [av, did, '%' + av + '%'] + ids)
                ex = cur.execute("SELECT id FROM partners WHERE donor_id=? AND TRIM(avreich)=? "
                                 "AND COALESCE(active,1)<>0", (did, av)).fetchone()
                if not ex:
                    amt = ''
                    r1 = cur.execute("SELECT amount FROM donations WHERE donor_id=? %s ORDER BY date DESC LIMIT 1"
                                     % ("AND id IN (%s)" % ','.join('?' * len(ids)) if ids else ''),
                                     [did] + ids).fetchone()
                    if r1:
                        amt = r1['amount'] or ''
                    cur.execute("INSERT INTO partners(donor_id,avreich,start_date,amount,active) VALUES(?,?,?,?,1)",
                                (did, av, today_iso(), amt))
            tid = b.get('task_id')
            if tid:
                task_done_log(cur, tid, done=True)
            con.commit(); con.close()
            return self._send(200, {'ok': True, 'updated': n})
        if self.path == '/api/audit/newdonor':
            # פתיחת כרטיס תורם מתוך חיובים שאין להם כרטיס, ושיוך כל החיובים שלו אליו
            tids = b.get('tids') or []
            last = (b.get('last') or '').strip()
            if not last:
                return self._send(400, {'error': 'last required'})
            con = db(); cur = con.cursor()
            cur.execute("""INSERT INTO donors(last,first,english,phone,email,addr,city,country,zip,
                                              category,created,source,notes)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?,'חיובים לא מזוהים',?)""",
                        (last, (b.get('first') or '').strip(), (b.get('english') or '').strip(),
                         (b.get('phone') or ''), (b.get('email') or '').strip().lower(),
                         (b.get('addr') or ''), (b.get('city') or ''), (b.get('state') or ''),
                         (b.get('zip') or ''), (b.get('category') or 'מזדמן'), today_iso(),
                         (b.get('notes') or '')))
            did = cur.lastrowid
            n = 0
            for t in tids:
                n += cur.execute("UPDATE recon SET donor_id=? WHERE tid=? AND donor_id IS NULL",
                                 (did, t)).rowcount
            em = (b.get('email') or '').strip().lower()
            if em:
                n += cur.execute("""UPDATE recon SET donor_id=? WHERE lower(TRIM(email))=?
                                    AND TRIM(COALESCE(email,''))<>'' AND donor_id IS NULL""", (did, em)).rowcount
            con.commit(); con.close()
            return self._send(200, {'ok': True, 'donor_id': did, 'linked': n})
        if self.path == '/api/import/campaign':
            # ייבוא רשימת מגבית שלמה: התאמה לתורם, לחיוב שטרם אושר, והכנסת התרומה במקומה
            rows = b.get('rows') or []
            cat = (b.get('category') or '').strip()
            dfrom, dto = (b.get('from') or '').strip(), (b.get('to') or '').strip()
            con = db(); cur = con.cursor()
            res = campaign_match(con, rows, dfrom, dto)
            if b.get('dry', True):
                con.close()
                return self._send(200, {'ok': True, 'rows': res})
            if not cat:
                con.close(); return self._send(400, {'error': 'category required'})
            BASE = {'', 'קבוע', 'יששכר־זבולון', 'פרנס לילה', 'חדר קפה', 'ארוחת בוקר',
                    'נר למאור', 'קוויטל', 'מזדמן', 'חד-פעמי', 'אחר'}
            if cat not in BASE:
                cur.execute("INSERT OR IGNORE INTO campaigns(name,created) VALUES(?,?)", (cat, today_iso()))
            ins = skipped = 0
            for x in res:
                if (not x['donor_id'] or x['status'] == 'skip'
                        or (b.get('only_charged') and not x['charge'])):
                    skipped += 1; continue
                ch = x['charge'] or {}
                dt = ch.get('date') or (b.get('default_date') or today_iso())
                # אמצעי התשלום: מהחיוב האמיתי אם נמצא, אחרת הצבע שסומן בגיליון
                meth = ('Banquest' if 'Banquest' in (ch.get('source') or '') else
                        ('Authorize' if ch.get('source') else (x.get('method') or b.get('method') or '')))
                if cur.execute("""SELECT 1 FROM donations WHERE donor_id=? AND category=?
                                  AND ROUND(CAST(amount AS REAL),2)=?""",
                               (x['donor_id'], cat, x['amount'])).fetchone():
                    skipped += 1; continue          # כבר נרשמה — בלי כפילות
                note = cat + (' · ' + x['method'] if (x['method'] and not ch) else '') + (' · ' + x['note'] if x['note'] else '')
                cur.execute("INSERT INTO donations(donor_id,date,amount,category,method,note,paid) VALUES(?,?,?,?,?,?,1)",
                            (x['donor_id'], dt, f"{x['amount']:.2f}", cat, meth, note))
                if ch.get('tid'):
                    cur.execute("UPDATE recon SET processed=1, donor_id=?, category=? WHERE tid=?",
                                (x['donor_id'], cat, ch['tid']))
                ins += 1
            con.commit(); con.close()
            return self._send(200, {'ok': True, 'inserted': ins, 'skipped': skipped, 'rows': res})
        if self.path == '/api/recon/batch':
            # אישור כל שורות התורם בבקשה אחת — במקום סבב רשת נפרד לכל שורה
            con = db(); cur = con.cursor(); did = b.get('donor_id'); out = []
            for it in (b.get('items') or []):
                ib = dict(it.get('body') or {})
                if did: ib['donor_id'] = did
                code, res = recon_apply(cur, it.get('tid'), ib)
                out.append(dict(res, tid=it.get('tid'), code=code))
                if res.get('donor_id'): did = res['donor_id']
            con.commit(); con.close()
            return self._send(200, {'ok': True, 'donor_id': did, 'results': out})
        m = re.match(r'/api/recon/([^/]+)$', self.path)
        if m:
            con = db(); cur = con.cursor()
            code, res = recon_apply(cur, m.group(1), b)
            con.commit(); con.close()
            return self._send(code, res)
        if self.path == '/api/audit/autolink':
            # שיוך אוטומטי של חיובים שנשארו בלי כרטיס — אפשר להריץ שוב אחרי כל ייבוא חדש
            con = db()
            try:
                n = link_by_identity(con)
                con.commit()
                left = con.execute("SELECT COUNT(*) FROM recon WHERE COALESCE(processed,0)=0 "
                                   "AND COALESCE(status,'settled')='settled' "
                                   "AND donor_id IS NULL").fetchone()[0]
            finally:
                con.close()
            return self._send(200, {'ok': True, 'linked': n, 'left': left})
        if self.path == '/api/addr/reject':
            # "לא מתאים" — ההצעה הזו לא תוצע שוב לתורם הזה
            did = b.get('donor_id'); addr = (b.get('addr') or '').strip()
            if not did or not addr:
                return self._send(400, {'error': 'donor_id/addr required'})
            con = db()
            con.execute("INSERT OR IGNORE INTO addr_reject(donor_id,addr,created) VALUES(?,?,?)",
                        (int(did), addr, today_iso()))
            con.commit(); con.close()
            return self._send(200, {'ok': True})
        if self.path == '/api/notdupe':
            # "לא אותו אדם" — כל הזוגות בקבוצה נשמרים כדי שלא תחזור לרשימת המיזוג
            ids = sorted({int(x) for x in (b.get('ids') or []) if str(x).isdigit()})
            if len(ids) < 2:
                return self._send(400, {'error': 'ids required'})
            con = db()
            n = 0
            for i, a in enumerate(ids):
                for c in ids[i + 1:]:
                    try:
                        con.execute("INSERT OR IGNORE INTO not_dupes(a,b,created) VALUES(?,?,?)",
                                    (a, c, today_iso()))
                        n += 1
                    except Exception:
                        pass
            con.commit(); con.close()
            return self._send(200, {'ok': True, 'pairs': n})
        if self.path == '/api/merge':
            # מיזוג שני כרטיסים כפולים: keep=הכרטיס שנשאר, drop=הכרטיס שנמחק
            try:
                keep = int(b.get('keep')); drop = int(b.get('drop'))
            except (TypeError, ValueError):
                return self._send(400, {'error': 'keep/drop required'})
            if keep == drop:
                return self._send(400, {'error': 'same id'})
            con = db()
            moved = merge_into(con, keep, drop)
            if moved is None:
                con.close(); return self._send(404, {'error': 'donor not found'})
            con.commit(); con.close()
            return self._send(200, {'ok': True, 'keep': keep, 'dropped': drop, 'moved': moved})
        if self.path == '/api/building':
            con = db(); cur = con.cursor()
            cur.execute("INSERT INTO building(donor_id,object,amount,paid,note,date) VALUES(?,?,?,?,?,?)",
                        (b.get('donor_id'), b.get('object',''), b.get('amount',''), b.get('paid',''), b.get('note',''), b.get('date', today_iso())))
            con.commit(); pid = cur.lastrowid; con.close()
            return self._send(200, {'ok': True, 'id': pid})
        if self.path == '/api/pledge':
            con = db(); cur = con.cursor()
            cur.execute("INSERT INTO pledges(donor_id,category,amount,status,date,note,monthly) VALUES(?,?,?,?,?,?,?)",
                        (b.get('donor_id'), b.get('category',''), b.get('amount',''), b.get('status','טרם'),
                         b.get('date',''), b.get('note',''), 1 if b.get('monthly') else 0))
            con.commit(); pid = cur.lastrowid; con.close()
            return self._send(200, {'ok': True, 'id': pid})
        if self.path == '/api/parnes':
            con = db(); cur = con.cursor()
            # מטבע: אם לא נבחר, נקבע לפי האזור של התורם — תורם בארץ ב-₪
            ccy = (b.get('currency') or '').strip()
            if not ccy:
                dr = cur.execute("SELECT region FROM donors WHERE id=?", (b.get('donor_id'),)).fetchone()
                ccy = '₪' if (dr and (dr['region'] or '') == 'il') else '$'
            # אותו יום, אותו תורם, אותו סוג — יום אחד ולא חמישה. לחיצה חוזרת
            # או שליחה כפולה מחזירה את השורה הקיימת במקום לפתוח עוד אחת.
            ex = cur.execute("SELECT id FROM parnes WHERE donor_id=? AND COALESCE(kind,'')=? "
                             "AND COALESCE(date_text,'')=? AND COALESCE(hyear,'')=? "
                             "AND COALESCE(status,'')<>'suggested'",
                             (b.get('donor_id'), b.get('kind', 'parnes'),
                              b.get('date_text', ''), b.get('hyear', ''))).fetchone()
            if ex and b.get('status', 'confirmed') != 'suggested':
                con.close()
                return self._send(200, {'ok': True, 'id': ex['id'], 'existing': True})
            # תאריך לועזי מדויק לפי השנה העברית שנבחרה; נפילה לחישוב המופע הקרוב אם אין שנה
            _ng = heb_greg_year(b.get('date_text', ''), b.get('hyear', '')) or heb_to_greg(b.get('date_text', ''))
            cur.execute("INSERT INTO parnes(donor_id,day,month,date_text,amount,dedication,kind,status,night_date,hyear,method,currency) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                        (b.get('donor_id'), b.get('day',0), b.get('month',''), b.get('date_text',''), b.get('amount',''), b.get('dedication',''), b.get('kind','parnes'), b.get('status','confirmed'), _ng.isoformat() if _ng else '', b.get('hyear',''), b.get('method',''), ccy))
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
            did = b.get('donor_id'); due = b.get('due_date', '')
            kind = b.get('kind', 'prayer'); note = b.get('note', ''); who = b.get('assignee', '')
            # לחיצה כפולה על "הוסף משימה" יצרה שתי משימות זהות. משימה פתוחה
            # זהה לגמרי כבר קיימת — מחזירים אותה במקום לפתוח עוד אחת.
            ex = cur.execute("SELECT id FROM tasks WHERE COALESCE(done,0)=0 "
                             "AND COALESCE(donor_id,0)=COALESCE(?,0) AND COALESCE(due_date,'')=? "
                             "AND COALESCE(kind,'')=? AND COALESCE(note,'')=?",
                             (did, due, kind, note)).fetchone()
            if ex:
                con.close()
                return self._send(200, {'ok': True, 'id': ex['id'], 'existing': True})
            cur.execute("INSERT INTO tasks(donor_id,due_date,kind,note,assignee) VALUES(?,?,?,?,?)",
                        (did, due, kind, note, who))
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
        bump_data()
        m = re.match(r'/api/intake/(\d+)$', self.path)
        if m:
            con = db(); con.execute("DELETE FROM intake WHERE id=?", (int(m.group(1)),)); con.commit(); con.close()
            return self._send(200, {'ok': True})
        m = re.match(r'/api/recon/(.+)$', self.path)
        if m:
            # מחיקת שורת חיוב מדף החיובים — למשל ניסיון תרומה. לא נוגע בתרומות שכבר הוכנסו לכרטיס
            tid = urllib.parse.unquote(m.group(1))
            con = db()
            n = con.execute("SELECT COUNT(*) FROM recon WHERE tid=?", (tid,)).fetchone()[0]
            con.execute("DELETE FROM recon WHERE tid=?", (tid,))
            con.commit(); con.close()
            return self._send(200, {'ok': n > 0, 'deleted': n})
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
            try:
                _d = con.execute("SELECT last,first,english FROM donors WHERE id=?", (did,)).fetchone()
                if _d:
                    con.execute("INSERT OR REPLACE INTO deleted_donors(key,last,first,english,created) "
                                "VALUES(?,?,?,?,?)",
                                (_dkey(_d['last'], _d['first']), _d['last'], _d['first'],
                                 _d['english'] or '', today_iso()))
            except Exception: pass
            for t in ('pledges','parnes','prayers','donations','contacts_log','tasks','partners',
                      'transactions','building','donor_rules','avreich_log','sugg_reject','addr_reject'):
                try: con.execute(f"DELETE FROM {t} WHERE donor_id=?", (did,))
                except Exception: pass
            # ניתוק שיוכים שנשארו במקומות אחרים, כדי שהתורם לא יופיע יותר בשום מסך
            for tbl in ('recon', 'intake'):
                try: con.execute(f"UPDATE {tbl} SET donor_id=NULL WHERE donor_id=?", (did,))
                except Exception: pass
            try:
                con.execute("DELETE FROM donors WHERE id=?", (did,))
                con.commit()
            except Exception as e:
                con.close(); return self._send(200, {'ok': False, 'error': 'delete_failed', 'detail': str(e)})
            gone = con.execute("SELECT COUNT(*) FROM donors WHERE id=?", (did,)).fetchone()[0] == 0
            con.close()
            return self._send(200, {'ok': gone} if gone else {'ok': False, 'error': 'still_exists'})
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
            if table == 'donations':
                # תרומה שנמחקה ביד לא חוזרת בשחזור האוטומטי של החיובים
                try:
                    d0 = con.execute("SELECT donor_id,date,amount FROM donations WHERE id=?", (rid,)).fetchone()
                    if d0 and d0['donor_id'] and (d0['date'] or ''):
                        a0 = round(float(str(d0['amount'] or 0).replace(',', '')), 2)
                        for rr in con.execute("SELECT tid,date,amount FROM recon WHERE donor_id=?",
                                              (d0['donor_id'],)):
                            ri = _recon_iso(rr['date']) or (rr['date'] or '')[:10]
                            if not ri or ri[:7] != (d0['date'] or '')[:7]:
                                continue
                            if abs(round(float(str(rr['amount'] or 0).replace(',', '')), 2) - a0) < .01:
                                con.execute("UPDATE recon SET skipped=1 WHERE tid=?", (rr['tid'],))
                                break
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

SYNCSTAT = {'last': '', 'last_ok': '', 'result': '', 'error': '', 'runs': 0}
ANETSTAT = {'last': '', 'last_ok': '', 'result': '', 'error': '', 'runs': 0, 'hooks': 0}

def health_report():
    """בדיקת מערכת — מה עובד, מה חסר, ומה דורש טיפול. ok / warn / bad לכל שורה."""
    rows = []
    def add(name, state, detail=''):
        rows.append({'name': name, 'state': state, 'detail': str(detail)})
    con = None
    try:
        con = db()
        n = lambda q, *a: (con.execute(q, a).fetchone() or [0])[0]
        donors = n("SELECT COUNT(*) FROM donors")
        add('בסיס הנתונים', 'ok', '%d תורמים · %d תרומות · %d חיובים'
            % (donors, n("SELECT COUNT(*) FROM donations"), n("SELECT COUNT(*) FROM recon")))
        try:
            sz = os.path.getsize(DB) / 1048576.0
            add('גודל הקובץ', 'ok' if sz < 400 else 'warn', '%.1f MB' % sz)
        except Exception:
            pass
        # תעודות פרנס — נכשלו בעבר כי Pillow לא הותקן
        try:
            import PIL
            from PIL import Image, ImageDraw, ImageFont      # noqa: F401
            add('תעודות פרנס (תמונה)', 'ok', 'Pillow %s מותקן' % getattr(PIL, '__version__', ''))
        except Exception as e:
            add('תעודות פרנס (תמונה)', 'bad', 'Pillow חסר — התעודה לא תיווצר (%s)' % e)
        # דואר
        gu = (os.environ.get('GMAIL_USER') or '').strip()
        if gu and (os.environ.get('GMAIL_APP_PASSWORD') or '').strip():
            add('משיכת מיילים', 'ok', gu)
        else:
            add('משיכת מיילים', 'bad', 'GMAIL_USER / GMAIL_APP_PASSWORD לא מוגדרים בשרת')
        if SYNCSTAT.get('error'):
            add('סנכרון אחרון', 'bad', '%s — %s' % (SYNCSTAT.get('last') or '', SYNCSTAT['error']))
        elif SYNCSTAT.get('last_ok'):
            add('סנכרון אחרון', 'ok', '%s · %s' % (SYNCSTAT['last_ok'], SYNCSTAT.get('result') or ''))
        else:
            add('סנכרון אחרון', 'warn', 'עדיין לא רץ מאז ההפעלה')
        add('תרגום מיילים לעברית', 'ok' if os.environ.get('ANTHROPIC_API_KEY') else 'warn',
            'תרגום איכותי מופעל' if os.environ.get('ANTHROPIC_API_KEY')
            else 'ללא ANTHROPIC_API_KEY — תרגום חינמי, איכות נמוכה יותר')
        add('שליחת מיילים', 'ok' if (os.environ.get('BREVO_API_KEY') or os.environ.get('SMTP_HOST'))
            else 'warn', 'Brevo מוגדר' if os.environ.get('BREVO_API_KEY') else 'לא מוגדר מפתח שליחה')
        # זיכרון — כדי לראות מבעוד מועד אם השרת מתקרב לגבול
        try:
            rss = 0
            with open('/proc/self/status') as fh:
                for ln in fh:
                    if ln.startswith('VmRSS:'):
                        rss = int(ln.split()[1]) / 1024; break
            lim = 512
            add('זיכרון בשרת', 'ok' if rss < lim * 0.7 else ('warn' if rss < lim * 0.9 else 'bad'),
                '%d MB מתוך %d' % (rss, lim))
        except Exception:
            pass
        # החיבור החי ל-Authorize.net
        try:
            import authorize_sync as _an
            if not _an.configured():
                add('חיבור ל-Authorize.net', 'warn',
                    'לא מוגדר — חסרים AUTHNET_LOGIN_ID ו-AUTHNET_TRANSACTION_KEY')
            else:
                sb = 'בדיקות (sandbox)' if 'apitest' in _an.endpoint() else 'חשבון אמיתי'
                add('חיבור ל-Authorize.net', 'ok', 'מחובר · %s' % sb)
                add('הודעה מיידית (Webhook)', 'ok' if _an._sig_key() else 'warn',
                    ('פעילה · התקבלו %d הודעות' % ANETSTAT['hooks']) if _an._sig_key()
                    else 'חסר AUTHNET_SIGNATURE_KEY — עובד רק במשיכה כל שעה')
                if ANETSTAT.get('error'):
                    add('משיכה אחרונה מ-Authorize', 'bad',
                        '%s — %s' % (ANETSTAT.get('last') or '', ANETSTAT['error']))
                elif ANETSTAT.get('last_ok'):
                    add('משיכה אחרונה מ-Authorize', 'ok',
                        '%s · %s' % (ANETSTAT['last_ok'], ANETSTAT.get('result') or ''))
                else:
                    add('משיכה אחרונה מ-Authorize', 'warn', 'עדיין לא רצה מאז ההפעלה')
        except Exception as e:
            add('חיבור ל-Authorize.net', 'warn', e)
        # חיובים שלא שויכו
        try:
            r = con.execute("SELECT COUNT(*), COALESCE(SUM(CAST(amount AS REAL)),0) FROM recon "
                            "WHERE donor_id IS NULL").fetchone()
            add('חיובים ללא כרטיס', 'ok' if not r[0] else 'warn', '%d חיובים · $%s'
                % (r[0], format(int(r[1] or 0), ',')))
        except Exception as e:
            add('חיובים ללא כרטיס', 'warn', e)
        # תרומות יתומות
        orph = n("SELECT COUNT(*) FROM donations WHERE donor_id NOT IN (SELECT id FROM donors)")
        add('תרומות בלי כרטיס', 'ok' if not orph else 'bad', '%d שורות' % orph)
        # פרטי קשר חסרים
        noaddr = n("SELECT COUNT(*) FROM donors WHERE COALESCE(TRIM(addr),'')=''")
        noph = n("SELECT COUNT(*) FROM donors WHERE COALESCE(TRIM(phone),'')='' AND COALESCE(TRIM(email),'')=''")
        add('תורמים בלי כתובת', 'ok' if noaddr < donors * 0.4 else 'warn', '%d מתוך %d' % (noaddr, donors))
        add('תורמים בלי טלפון ובלי מייל', 'ok' if noph < donors * 0.4 else 'warn', '%d מתוך %d' % (noph, donors))
        # אברכי יש"ז בלי סכום
        try:
            noamt = n("SELECT COUNT(*) FROM partners WHERE COALESCE(active,1)<>0 AND COALESCE(TRIM(amount),'')=''")
            add('אברכי יש"ז בלי סכום', 'ok' if not noamt else 'warn', '%d אברכים' % noamt)
        except Exception:
            pass
        # משימות שעבר זמנן
        over = n("SELECT COUNT(*) FROM tasks WHERE COALESCE(done,0)=0 AND COALESCE(due_date,'')<>'' AND due_date<?",
                 today_iso())
        add('משימות שעבר זמנן', 'ok' if not over else 'warn', '%d משימות' % over)
        # מיגרציות
        add('עדכוני מבנה שרצו', 'ok', '%d' % n("SELECT COUNT(*) FROM seed_flags"))
    except Exception as e:
        add('בסיס הנתונים', 'bad', e)
    finally:
        try:
            if con: con.close()
        except Exception:
            pass
    bad = sum(1 for r in rows if r['state'] == 'bad')
    warn = sum(1 for r in rows if r['state'] == 'warn')
    return {'ok': not bad, 'bad': bad, 'warn': warn, 'when': now_iso(), 'rows': rows}

def _intake_daily_loop():
    """תיוק המיילים — נכנסים ויוצאים — כל שעתיים, ומשיכת קוויטלים פעם ביום.
    כך כל התכתבות עם תורם יושבת בכרטיס שלו מעצמה. רץ רק אם ה-Gmail מוגדר."""
    import time
    try:
        import gmail_intake
    except Exception:
        return
    every = max(600, int(os.environ.get('MAILSYNC_SECONDS') or 2 * 3600))
    first, last_kv = True, 0.0
    while True:
        try:
            if gmail_intake.configured():
                if first:
                    time.sleep(20)   # להמתין שהשרת יתייצב לפני המשיכה הראשונה
                if time.time() - last_kv > 23 * 3600:      # קוויטלים — פעם ביום
                    con = db(); res = gmail_intake.sync(con); con.close()
                    print('  משיכת קוויטלים אוטומטית:', res)
                    last_kv = time.time()
                con = db(); res2 = gmail_intake.sync_contacts(con); con.close()
                print('  תיוק מיילים ליומן הקשר:', res2)
                SYNCSTAT.update(last=now_iso(), last_ok=now_iso(), result=str(res2), error='',
                                runs=SYNCSTAT['runs'] + 1)
        except Exception as e:
            print('  שגיאת משיכה אוטומטית:', e)
            SYNCSTAT.update(last=now_iso(), error=str(e)[:200])
        first = False
        time.sleep(every)

def _authnet_loop():
    """רשת הביטחון של החיבור ל-Authorize.net. ה-Webhook מביא כל חיוב תוך שניות,
    והסריקה הזו רצה כל שעה ואוספת כל מה שאולי לא הגיע — הודעה שאבדה, שרת
    שהיה למטה, או חיוב קבוע שנגבה בלילה. חיוב שכבר נרשם לא נרשם פעמיים."""
    import time
    try:
        import authorize_sync as anet
    except Exception:
        return
    every = max(600, int(os.environ.get('AUTHNET_SECONDS') or 3600))
    first = True
    while True:
        try:
            if anet.configured():
                if first:
                    time.sleep(25)
                con = db()
                res = anet.sync(con, days=int(os.environ.get('AUTHNET_DAYS') or 10),
                                link=link_by_identity)
                con.close()
                bump_data()
                ANETSTAT.update(last=now_iso(), last_ok=now_iso(), result=str(res), error='',
                                runs=ANETSTAT['runs'] + 1)
                if (res or {}).get('נוספו'):
                    print('  Authorize.net — חיובים חדשים:', res)
        except Exception as e:
            print('  שגיאת משיכה מ-Authorize.net:', e)
            ANETSTAT.update(last=now_iso(), error=str(e)[:200])
        first = False
        time.sleep(every)


def serve():
    ensure_schema()
    import threading
    threading.Thread(target=_intake_daily_loop, daemon=True).start()
    threading.Thread(target=_authnet_loop, daemon=True).start()
    print(f'CRM כולל חצות רץ על פורט {PORT}')
    ThreadingHTTPServer(('0.0.0.0', PORT), H).serve_forever()

if __name__ == '__main__':
    serve()
