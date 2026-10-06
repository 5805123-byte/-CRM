# -*- coding: utf-8 -*-
"""קריאת אסמכתא של העברה בנקאית (PDF) — שם המעביר, סכום, תאריך, אסמכתא, כתובת.

מאיר: "אני מעדיף שקבלות ישראליות יעברו דרך איזיקאונט… שאני אשלח לך אסמכתא
ואני אוציא משם קבלה, אין לי כוח להכניס שם את כל הנתונים של התורם."
הקובץ נקרא עם pypdf; ההיגיון הוא היוריסטי (לאומי, פועלים, מזרחי, דיסקונט…):
מה שלא זוהה נשאר ריק, ומאיר משלים במסך לפני ההפקה.
"""
import re


def pdf_text(data):
    """טקסט מכל העמודים. מחזיר '' אם pypdf לא זמין או הקובץ לא נקרא."""
    import io
    try:
        from pypdf import PdfReader
    except Exception:
        return ''
    try:
        r = PdfReader(io.BytesIO(data))
        return '\n'.join((p.extract_text() or '') for p in r.pages)
    except Exception:
        return ''


_OUR = ('כולל חצות', 'נחלת יהושע', 'זכרון אבות', 'kollel')
_BANKS = ('בנק', 'לאומי', 'פועלים', 'מזרחי', 'דיסקונט', 'פאג"י', 'פועלי אגודת', 'מרכנתיל', 'הבינלאומי', 'יהב', 'אוצר החייל', 'ירושלים', 'מסד')


def _num(s):
    s = (s or '').replace(',', '').replace('−', '-').strip()
    m = re.search(r'-?\d+(?:\.\d+)?', s)
    return abs(float(m.group(0))) if m else 0.0


def _date(s):
    """dd/mm/yy או dd/mm/yyyy או dd.mm.yyyy -> YYYY-MM-DD"""
    m = re.search(r'(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})', s or '')
    if not m:
        return ''
    d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if y < 100:
        y += 2000
    if not (1 <= mo <= 12 and 1 <= d <= 31):
        return ''
    return '%04d-%02d-%02d' % (y, mo, d)


def _is_name(line):
    t = line.strip()
    if not t or len(t) > 60 or re.search(r'\d', t):
        return False
    if any(x in t for x in _OUR) or any(x in t for x in _BANKS):
        return False
    if re.search(r'בע"מ|בע״מ|סניף|חשבון|כתובת|פרטי|מטרת|תאריך|סכום|אסמכתא|עמלה|שם\b', t):
        return False
    return bool(re.search(r'[֐-׿]', t))


def parse(text):
    """-> dict: name, addr, amount, date, ref, purpose, found (רשימת מה זוהה)."""
    out = {'name': '', 'addr': '', 'amount': 0.0, 'date': '', 'ref': '', 'purpose': '', 'found': []}
    if not text:
        return out
    lines = [l.strip() for l in text.splitlines()]
    lines = [l for l in lines if l]
    joined = '\n'.join(lines)
    # --- שם המעביר: השורה שאחרי "שם" בתוך "פרטי המעביר" (ולא בפרטי המוטב) ---
    start = 0
    for i, l in enumerate(lines):
        if 'פרטי המעביר' in l or 'פרטי המשלם' in l or 'פרטי מעביר' in l:
            start = i; break
    end = len(lines)
    for i in range(start + 1, len(lines)):
        if 'פרטי המוטב' in lines[i] or 'פרטי מוטב' in lines[i] or 'פרטי הזיכוי' in lines[i]:
            end = i; break
    for i in range(start, end):
        l = lines[i]
        if re.fullmatch(r'שם(\s*המעביר|\s*המשלם|\s*הלקוח)?\s*:?', l) and i + 1 < len(lines) and _is_name(lines[i + 1]):
            out['name'] = lines[i + 1]; break
        m = re.match(r'^שם(?:\s*המעביר|\s*המשלם|\s*הלקוח)?\s*:\s*(.+)$', l)
        if m and _is_name(m.group(1)):
            out['name'] = m.group(1).strip(); break
    if not out['name']:
        m = re.search(r'(?:מאת|שם המעביר|המעביר)\s*:?\s*\n?([^\n]+)', joined)
        if m and _is_name(m.group(1)):
            out['name'] = m.group(1).strip()
    # --- כתובת ---
    for i in range(start, end):
        if re.fullmatch(r'כתובת\s*:?', lines[i]) and i + 1 < len(lines):
            nxt = lines[i + 1]
            if not re.match(r'^(פרטי|שם|מס)', nxt):
                out['addr'] = nxt
            break
        m = re.match(r'^כתובת\s*:\s*(.+)$', lines[i])
        if m:
            out['addr'] = m.group(1).strip(); break
    # --- סכום: "סה"כ לחיוב" / "סכום ההעברה" / "סכום" ---
    amt = 0.0
    for key in (r'סה"כ\s*לחיוב', r'סה״כ\s*לחיוב', r'סכום\s*ההעברה(?:\s*לבנק\s*אחר)?', r'סכום\s*לזיכוי', r'סכום\s*ההפקדה', r'סכום\s*התשלום', r'\bסכום\b'):
        m = re.search(key + r'\s*:?\s*\n?\s*(-?[\d,]+(?:\.\d+)?)', joined)
        if m:
            amt = _num(m.group(1))
            if amt > 0:
                break
    if not amt:
        cands = [_num(x) for x in re.findall(r'(-?[\d,]{1,12}(?:\.\d{1,2})?)\s*(?:ש"ח|ש״ח|ש\'\'ח|₪|שח)', joined)]
        cands = [c for c in cands if c > 0]
        if cands:
            amt = max(cands)
    out['amount'] = amt
    # --- תאריך: תאריך ערך > תאריך ביצוע > התאריך הראשון במסמך ---
    for key in (r'תאריך\s*ערך(?:\s*ההעברה)?', r'תאריך\s*ביצוע', r'תאריך\s*ההעברה', r'תאריך\s*הפקדה', r'תאריך'):
        m = re.search(key + r'\s*:?\s*(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})', joined)
        if m:
            out['date'] = _date(m.group(1))
            if out['date']:
                break
    if not out['date']:
        m = re.search(r'\d{1,2}[./-]\d{1,2}[./-]\d{2,4}', joined)
        out['date'] = _date(m.group(0)) if m else ''
    # --- אסמכתא ---
    m = re.search(r'(?:אסמכתא|מס\'?\s*אסמכתא|מספר\s*אסמכתא|מספר\s*פעולה|reference)\s*:?\s*#?\s*([A-Za-z0-9\-]{3,})', joined, re.I)
    if m:
        out['ref'] = m.group(1)
    # --- מטרה ---
    m = re.search(r'(?:מטרת\s*ההעברה|מטרה|פרטים\s*למוטב|הערה\s*למוטב)\s*:?\s*\n?\s*([^\n]{1,60})', joined)
    if m and not re.match(r'^(אסמכתא|תאריך|סכום)', m.group(1)):
        out['purpose'] = m.group(1).strip()
    out['found'] = [k for k in ('name', 'addr', 'amount', 'date', 'ref', 'purpose') if out[k]]
    return out


def parse_pdf(data):
    return parse(pdf_text(data))
