# -*- coding: utf-8 -*-
"""שרת CRM כולל חצות — מגיש את הממשק + API לשמירה (SQLite)."""
import sqlite3, json, os, re, base64
from urllib.parse import quote
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from hebdate import week_before, greg_to_heb_monthyear

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.environ.get('DB_PATH') or os.path.join(HERE, 'crm.db')
STATIC = os.path.join(HERE, 'static')
PORT = int(os.environ.get('PORT', 8000))

def db():
    con = sqlite3.connect(DB); con.row_factory = sqlite3.Row; return con

def ensure_schema():
    """יוצר טבלאות חדשות אם חסרות — כדי שעדכונים לא ידרשו למחוק נתונים קיימים (דיסק קבוע)."""
    con = db()
    con.executescript("""
    CREATE TABLE IF NOT EXISTS donations(id INTEGER PRIMARY KEY AUTOINCREMENT, donor_id INTEGER, date TEXT, amount TEXT, category TEXT, method TEXT, note TEXT);
    CREATE TABLE IF NOT EXISTS contacts_log(id INTEGER PRIMARY KEY AUTOINCREMENT, donor_id INTEGER, date TEXT, channel TEXT, summary TEXT, next_date TEXT);
    CREATE TABLE IF NOT EXISTS tasks(id INTEGER PRIMARY KEY AUTOINCREMENT, donor_id INTEGER, due_date TEXT, kind TEXT, note TEXT, done INTEGER DEFAULT 0);
    CREATE TABLE IF NOT EXISTS partners(id INTEGER PRIMARY KEY AUTOINCREMENT, donor_id INTEGER, avreich TEXT, start_date TEXT, amount TEXT, note TEXT, active INTEGER DEFAULT 1, ended_date TEXT);
    CREATE TABLE IF NOT EXISTS files(id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT, ref_id INTEGER, name TEXT, mime TEXT, data BLOB, created TEXT);
    """)
    # מיגרציה — הוספת עמודות חדשות אם חסרות (דיסק קבוע קיים)
    for col, ddl in [('start_date', 'TEXT'), ('amount', 'TEXT'), ('active', 'INTEGER DEFAULT 1'), ('ended_date', 'TEXT')]:
        try: con.execute(f"ALTER TABLE partners ADD COLUMN {col} {ddl}")
        except Exception: pass
    try: con.execute("ALTER TABLE parnes ADD COLUMN kind TEXT DEFAULT 'parnes'")
    except Exception: pass
    con.commit(); con.close()

def get_all():
    con = db(); c = con.cursor()
    donors = [dict(r) for r in c.execute("SELECT * FROM donors ORDER BY last,first")]
    byid = {d['id']: d for d in donors}
    for d in donors:
        d['pledges'] = []; d['parnes'] = []; d['prayers'] = []
        d['donations'] = []; d['contacts'] = []; d['tasks'] = []; d['partners'] = []
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
                'category','purpose','amount','channel','pay_status','last_active','notes'}

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
        n = int(self.headers.get('Content-Length', 0) or 0)
        return json.loads(self.rfile.read(n) or b'{}')

    def do_GET(self):
        if self.path == '/api/data':
            donors, unlinked = get_all()
            return self._send(200, {'donors': donors, 'unlinked_prayers': unlinked})
        if self.path.split('?')[0] == '/calendar.ics':
            return self._send(200, build_ics().encode('utf-8'), 'text/calendar')
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
                     '.png': 'image/png', '.svg': 'image/svg+xml', '.css': 'text/css',
                     '.webmanifest': 'application/manifest+json'}.get(ext, 'text/plain')
            return self._send(200, open(fp, 'rb').read(), ctype)
        return self._send(404, {'error': 'not found'})

    def do_PUT(self):
        m = re.match(r'/api/donor/(\d+)$', self.path)
        if m:
            b = self._body(); did = int(m.group(1))
            fields = {k: v for k, v in b.items() if k in DONOR_FIELDS}
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
            con.execute("UPDATE parnes SET day=?,month=?,date_text=?,amount=?,dedication=? WHERE id=?",
                        (b.get('day',0), b.get('month',''), b.get('date_text',''), b.get('amount',''), b.get('dedication',''), pid))
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
            con = db()
            con.execute("UPDATE donations SET date=?,amount=?,category=?,method=?,note=? WHERE id=?",
                        (b.get('date',''), b.get('amount',''), b.get('category',''), b.get('method',''), b.get('note',''), pid))
            con.commit(); con.close()
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
        return self._send(404, {'error': 'not found'})

    def do_POST(self):
        b = self._body()
        if self.path == '/api/pledge':
            con = db(); cur = con.cursor()
            cur.execute("INSERT INTO pledges(donor_id,category,amount,status,date,note) VALUES(?,?,?,?,?,?)",
                        (b['donor_id'], b.get('category',''), b.get('amount',''), b.get('status','טרם'), b.get('date',''), b.get('note','')))
            con.commit(); pid = cur.lastrowid; con.close()
            return self._send(200, {'ok': True, 'id': pid})
        if self.path == '/api/parnes':
            con = db(); cur = con.cursor()
            cur.execute("INSERT INTO parnes(donor_id,day,month,date_text,amount,dedication,kind) VALUES(?,?,?,?,?,?,?)",
                        (b['donor_id'], b.get('day',0), b.get('month',''), b.get('date_text',''), b.get('amount',''), b.get('dedication',''), b.get('kind','parnes')))
            pid = cur.lastrowid
            due = week_before(b.get('date_text',''))
            tid = None
            if due:
                cur.execute("INSERT INTO tasks(donor_id,due_date,kind,note) VALUES(?,?,?,?)",
                            (b['donor_id'], due, 'parnes', 'פרנס יום ' + b.get('date_text','') + ' — הכן הדפסה וצור קשר'))
                tid = cur.lastrowid
            con.commit(); con.close()
            return self._send(200, {'ok': True, 'id': pid, 'reminder_id': tid, 'reminder_date': due})
        if self.path == '/api/prayer':
            con = db(); cur = con.cursor()
            cur.execute("INSERT INTO prayers(donor_id,text,tier) VALUES(?,?,?)",
                        (b['donor_id'], b.get('text',''), b.get('tier','')))
            con.commit(); pid = cur.lastrowid; con.close()
            return self._send(200, {'ok': True, 'id': pid})
        if self.path == '/api/donation':
            con = db(); cur = con.cursor()
            cur.execute("INSERT INTO donations(donor_id,date,amount,category,method,note) VALUES(?,?,?,?,?,?)",
                        (b['donor_id'], b.get('date',''), b.get('amount',''), b.get('category',''), b.get('method',''), b.get('note','')))
            con.commit(); pid = cur.lastrowid; con.close()
            return self._send(200, {'ok': True, 'id': pid})
        if self.path == '/api/contact':
            con = db(); cur = con.cursor()
            cur.execute("INSERT INTO contacts_log(donor_id,date,channel,summary,next_date) VALUES(?,?,?,?,?)",
                        (b['donor_id'], b.get('date',''), b.get('channel',''), b.get('summary',''), b.get('next_date','')))
            cid = cur.lastrowid
            if b.get('next_date'):
                cur.execute("INSERT INTO tasks(donor_id,due_date,kind,note) VALUES(?,?,?,?)",
                            (b['donor_id'], b['next_date'], 'followup', b.get('summary','')[:80]))
            con.commit(); con.close()
            return self._send(200, {'ok': True, 'id': cid})
        if self.path == '/api/task':
            con = db(); cur = con.cursor()
            cur.execute("INSERT INTO tasks(donor_id,due_date,kind,note) VALUES(?,?,?,?)",
                        (b['donor_id'], b.get('due_date',''), b.get('kind','prayer'), b.get('note','')))
            con.commit(); pid = cur.lastrowid; con.close()
            return self._send(200, {'ok': True, 'id': pid})
        if self.path == '/api/partner':
            con = db(); cur = con.cursor()
            cur.execute("INSERT INTO partners(donor_id,avreich,start_date,amount,note,active) VALUES(?,?,?,?,?,1)",
                        (b['donor_id'], b.get('avreich',''), b.get('start_date',''), b.get('amount',''), b.get('note','')))
            con.commit(); pid = cur.lastrowid; con.close()
            return self._send(200, {'ok': True, 'id': pid})
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
        m = re.match(r'/api/(pledge|parnes|prayer|donation|contact|task|partner|file)/(\d+)$', self.path)
        if m:
            table = 'files' if m.group(1) == 'file' else m.group(1)
            con = db(); con.execute(f"DELETE FROM {table} WHERE id=?", (int(m.group(2)),)); con.commit(); con.close()
            return self._send(200, {'ok': True})
        return self._send(404, {'error': 'not found'})

    def log_message(self, *a): pass

def serve():
    ensure_schema()
    print(f'CRM כולל חצות רץ על פורט {PORT}')
    ThreadingHTTPServer(('0.0.0.0', PORT), H).serve_forever()

if __name__ == '__main__':
    serve()
