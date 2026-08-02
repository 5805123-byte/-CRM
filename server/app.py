# -*- coding: utf-8 -*-
"""שרת CRM כולל חצות — מגיש את הממשק + API לשמירה (SQLite)."""
import sqlite3, json, os, re, base64, datetime
from urllib.parse import quote

def today_iso():
    return datetime.date.today().isoformat()
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from hebdate import week_before, greg_to_heb_monthyear, current_heb_year, heb_to_greg

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
    """)
    # מיגרציה — הוספת עמודות חדשות אם חסרות (דיסק קבוע קיים)
    for col, ddl in [('start_date', 'TEXT'), ('amount', 'TEXT'), ('active', 'INTEGER DEFAULT 1'), ('ended_date', 'TEXT')]:
        try: con.execute(f"ALTER TABLE partners ADD COLUMN {col} {ddl}")
        except Exception: pass
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
    try: con.execute("ALTER TABLE donors ADD COLUMN iz_note TEXT")
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
                    con.execute("INSERT INTO donations(donor_id,date,amount,category,method,note) VALUES(?,?,?,?,?,?)",
                                (did, f"2026-{int(mo):02d}", str(rec.get('amount', '')), rec.get('category', 'קבוע'),
                                 rec.get('method', ''), 'ייבוא 2026'))
                    n += 1
            con.execute("INSERT INTO seed_flags(name) VALUES('donations2026_v2')")
            print(f'  ייבוא תרומות 2026: נוספו {n} תרומות')
    except Exception as e:
        print('  שגיאת ייבוא 2026:', e)
    # מיטמן מאיר (#337): תשלומי $585 הם לרכב כולל חצות, לא יששכר־זבולון (רץ אחרי ייבוא התרומות)
    try:
        if not con.execute("SELECT 1 FROM seed_flags WHERE name='mittman_585_car_v2'").fetchone():
            con.execute("""UPDATE donations SET category='רכב כולל חצות'
                           WHERE donor_id=337 AND CAST(amount AS REAL)=585""")
            con.execute("""UPDATE donors SET iz_note='תרומה נפרדת: $585/חודש לרכב כולל חצות (לא יש"ז)'
                           WHERE id=337 AND COALESCE(TRIM(iz_note),'')=''""")
            con.execute("INSERT INTO seed_flags(name) VALUES('mittman_585_car_v2')")
    except Exception: pass
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
    for r in c.execute("SELECT * FROM tasks ORDER BY due_date"):
        if r['donor_id'] in byid: byid[r['donor_id']]['tasks'].append(dict(r))
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
    parnes_files = {}
    try:
        for r in c.execute("SELECT id,kind,ref_id,name,mime FROM files"):
            meta = {'id': r['id'], 'name': r['name'], 'mime': r['mime']}
            if r['kind'] == 'iz' and r['ref_id'] in byid:
                byid[r['ref_id']]['files'].append(meta)
            elif r['kind'] == 'parnes':
                parnes_files.setdefault(r['ref_id'], []).append(meta)
        for d in donors:
            for p in d['parnes']:
                p['files'] = parnes_files.get(p['id'], [])
    except Exception:
        pass
    con.close()
    return donors, unlinked

DONOR_FIELDS = {'last','first','english','business','phone','email','addr','tier',
                'category','purpose','amount','channel','pay_status','last_active','notes',
                'region','country','zip','city','iz_note'}

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
            donors, unlinked = get_all()
            return self._send(200, {'donors': donors, 'unlinked_prayers': unlinked, 'heb_year': current_heb_year()})
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
            for r in con.execute("SELECT * FROM recon ORDER BY processed, last, first"):
                x = dict(r)
                if r['donor_id']:
                    d = con.execute("SELECT last,first,addr,category,tier FROM donors WHERE id=?", (r['donor_id'],)).fetchone()
                    if d:
                        x['match_name'] = (d['last'] + ' ' + (d['first'] or '')).strip()
                        x['match_addr'] = d['addr'] or ''
                        x['match_cat'] = d['category'] or ''
                        x['match_tier'] = d['tier'] or ''
                out.append(x)
            con.close()
            return self._send(200, out)
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
        m = re.match(r'/api/file/(\d+)$', self.path)
        if m:
            con = db(); r = con.execute("SELECT name,mime,data FROM files WHERE id=?", (int(m.group(1)),)).fetchone(); con.close()
            if not r: return self._send(404, {'error': 'not found'})
            self.send_response(200)
            self.send_header('Content-Type', r['mime'] or 'application/octet-stream')
            self.send_header('Content-Disposition', "inline; filename*=UTF-8''" + quote(r['name'] or 'file'))
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
            return self._send(200, open(fp, 'rb').read(), ctype)
        return self._send(404, {'error': 'not found'})

    def do_PUT(self):
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
            for k in ('day','month','date_text','amount','dedication','kind','status','photo','paid','night_date','hyear'):
                if k in b: sets.append(f'{k}=?'); vals.append(b[k])
            # אם התאריך העברי השתנה — חשב מחדש את תאריך הלילה הלועזי (לסימון הירח)
            if 'date_text' in b and 'night_date' not in b:
                _ng = heb_to_greg(b.get('date_text', ''))
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
            if sets:
                con.execute("UPDATE prayers SET " + ",".join(sets) + " WHERE id=?", vals + [pid])
                con.commit()
            con.close()
            return self._send(200, {'ok': True})
        m = re.match(r'/api/donation/(\d+)$', self.path)
        if m:
            b = self._body(); pid = int(m.group(1))
            con = db(); sets = []; vals = []
            for k in ('date','amount','category','method','note','fb_channel','fb_date','fb_followup','fb_note','paid'):
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
            for k in ('due_date','kind','note','done'):
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
            for k in ('avreich','start_date','amount','note','active','ended_date'):
                if k in b: sets.append(f'{k}=?'); vals.append(b[k])
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
        b = self._body()
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
            full_addr = ', '.join(p for p in [row['addr'], row['city'], row['state'], row['zip']] if p)
            if b.get('new_donor'):
                nd = b['new_donor']
                cur.execute("""INSERT INTO donors(last,first,english,phone,email,addr,category,created,source)
                               VALUES(?,?,?,?,?,?,?,?, 'Authorize')""",
                            (nd.get('last', ''), nd.get('first', ''), (row['first'] + ' ' + row['last']).strip(),
                             row['phone'], row['email'], full_addr, b.get('category', ''), today_iso()))
                did = cur.lastrowid
            if not did:
                con.close(); return self._send(400, {'error': 'donor required'})
            # מילוי אוטומטי של שם אנגלי אם חסר בכרטיס (מיזוג השם מ-Authorize)
            if not b.get('new_donor'):
                en = (row['first'] + ' ' + row['last']).strip()
                if en:
                    cur.execute("UPDATE donors SET english=? WHERE id=? AND COALESCE(TRIM(english),'')=''", (en, did))
            if b.get('update_addr') and full_addr:
                cur.execute("UPDATE donors SET addr=? WHERE id=?", (full_addr, did))
            # תאריך: '01-Jul-2026' -> '2026-07'
            MON = {'Jan':'01','Feb':'02','Mar':'03','Apr':'04','May':'05','Jun':'06','Jul':'07','Aug':'08','Sep':'09','Oct':'10','Nov':'11','Dec':'12'}
            dm = re.match(r'(\d{2})-([A-Za-z]{3})-(\d{4})', row['date'] or '')
            diso = f"{dm.group(3)}-{MON.get(dm.group(2),'01')}" if dm else ''
            cat = b.get('category', '') or row['category'] or ''
            cur.execute("INSERT INTO donations(donor_id,date,amount,category,method,note,paid) VALUES(?,?,?,?,?,?,1)",
                        (did, diso, row['amount'], cat, 'Authorize', 'התאמת יולי 2026' + (' · הוראת קבע' if row['recurring'] else '')))
            if row['recurring']:
                cur.execute("UPDATE donors SET category='קבוע' WHERE id=? AND COALESCE(category,'')=''", (did,))
            # פרנס לילה מאוגוסט ואילך — תזכורת לעשות לו את הלילה בפועל
            if cat == 'פרנס לילה' and diso >= '2026-08':
                dn = cur.execute("SELECT last, first FROM donors WHERE id=?", (did,)).fetchone()
                nm = ((dn['last'] + ' ' + (dn['first'] or '')).strip()) if dn else ''
                cur.execute("INSERT INTO tasks(donor_id,due_date,kind,note) VALUES(?,?,?,?)",
                            (did, today_iso(), 'parnes', '🌙 לעשות פרנס לילה — ' + nm))
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
            _ng = heb_to_greg(b.get('date_text', ''))
            cur.execute("INSERT INTO parnes(donor_id,day,month,date_text,amount,dedication,kind,status,night_date,hyear) VALUES(?,?,?,?,?,?,?,?,?,?)",
                        (b.get('donor_id'), b.get('day',0), b.get('month',''), b.get('date_text',''), b.get('amount',''), b.get('dedication',''), b.get('kind','parnes'), b.get('status','confirmed'), _ng.isoformat() if _ng else '', b.get('hyear','')))
            pid = cur.lastrowid
            due = week_before(b.get('date_text',''))
            tid = None
            if due:
                cur.execute("INSERT INTO tasks(donor_id,due_date,kind,note) VALUES(?,?,?,?)",
                            (b.get('donor_id'), due, 'parnes', 'פרנס יום ' + b.get('date_text','') + ' — הכן הדפסה וצור קשר'))
                tid = cur.lastrowid
            con.commit(); con.close()
            return self._send(200, {'ok': True, 'id': pid, 'reminder_id': tid, 'reminder_date': due})
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
            cur.execute("INSERT INTO tasks(donor_id,due_date,kind,note) VALUES(?,?,?,?)",
                        (b.get('donor_id'), b.get('due_date',''), b.get('kind','prayer'), b.get('note','')))
            con.commit(); pid = cur.lastrowid; con.close()
            return self._send(200, {'ok': True, 'id': pid})
        if self.path == '/api/partner':
            con = db(); cur = con.cursor()
            cur.execute("INSERT INTO partners(donor_id,avreich,start_date,amount,note,active) VALUES(?,?,?,?,?,1)",
                        (b.get('donor_id'), b.get('avreich',''), b.get('start_date',''), b.get('amount',''), b.get('note','')))
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
        m = re.match(r'/api/donor/(\d+)$', self.path)
        if m:
            did = int(m.group(1)); con = db()
            # קבצים תחילה (לפני מחיקת שורות parnes שהם מפנים אליהן)
            try: con.execute("DELETE FROM files WHERE ref_id=? AND kind='iz'", (did,))
            except Exception: pass
            try: con.execute("DELETE FROM files WHERE kind='parnes' AND ref_id IN (SELECT id FROM parnes WHERE donor_id=?)", (did,))
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
            con.execute(f"DELETE FROM {table} WHERE id=?", (rid,)); con.commit(); con.close()
            return self._send(200, {'ok': True})
        return self._send(404, {'error': 'not found'})

    def log_message(self, *a): pass

def serve():
    ensure_schema()
    print(f'CRM כולל חצות רץ על פורט {PORT}')
    ThreadingHTTPServer(('0.0.0.0', PORT), H).serve_forever()

if __name__ == '__main__':
    serve()
