"""📄 מסמכי המקווה על הבלאנק של המקווה (mikve_blank.docx).

מאיר: "צריך להכין מסמך עם כל הקבוצות והמחירים" + "זה [הבלאנק] של המקווה".
הבלאנק הוא קובץ Word שהרקע שלו (הלוגו, הפס בצד) יושב בכותרת העליונה — כאן מחליפים רק את גוף
המסמך, והכותרת, הגופנים והשוליים נשארים כמו שהם. בלי ספריות חיצוניות: zip + XML.
"""
import io
import os
import re
import zipfile
from xml.sax.saxutils import escape

BLANK = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'mikve_blank.docx')

# הצבעים של הבלאנק
INK, RED, GOLD, CREAM, BLUE, RULE = '2A2320', '6E1B1B', 'A8823A', 'FBF6EA', '2B86C5', 'E3D6B8'
FONT = '<w:rFonts w:asciiTheme="majorBidi" w:hAnsiTheme="majorBidi" w:cstheme="majorBidi"/>'


def _run(text, size=26, color=INK, bold=False):
    b = '<w:b/><w:bCs/>' if bold else ''
    return ('<w:r><w:rPr>%s%s<w:color w:val="%s"/><w:sz w:val="%d"/><w:szCs w:val="%d"/><w:rtl/></w:rPr>'
            '<w:t xml:space="preserve">%s</w:t></w:r>') % (FONT, b, color, size, size, escape(str(text)))


def _p(runs, jc='right', before=0, after=80, line=276, border=False, keep=False):
    """פסקה מימין לשמאל. runs — מחרוזת XML של ריצות (או טקסט פשוט)"""
    if not runs.startswith('<w:r>'):
        runs = _run(runs)
    bd = ('<w:pBdr><w:bottom w:val="single" w:sz="4" w:space="6" w:color="%s"/></w:pBdr>' % RULE) if border else ''
    kn = '<w:keepNext/>' if keep else ''
    # ב-Word עם bidi: "left" הוא הצד של תחילת השורה — כלומר ימין. מרכז נשאר מרכז
    jcv = {'right': 'left', 'center': 'center', 'left': 'right'}[jc]
    return ('<w:p><w:pPr>%s%s<w:bidi/><w:spacing w:before="%d" w:after="%d" w:line="%d" w:lineRule="auto"/>'
            '<w:jc w:val="%s"/></w:pPr>%s</w:p>') % (kn, bd, before, after, line, jcv, runs)


def _heading(text):  # לא בשימוש כרגע — לכותרות משנה במסמכים הבאים
    return _p('<w:r><w:rPr><w:color w:val="%s"/><w:rtl/></w:rPr><w:t xml:space="preserve">❖  </w:t></w:r>' % GOLD +
              _run(text, 34, RED, True), before=280, after=100, keep=True)


def _dia():
    return _p(_run('◆  ◆  ◆', 18, GOLD), jc='center', before=200, after=60)


def _cell(text, w, head=False, fill=None, jc='center', bold=False, color=None):
    sh = '<w:shd w:val="clear" w:color="auto" w:fill="%s"/>' % (fill or (GOLD if head else 'FFFFFF'))
    run = _run(text, 24 if not head else 24, color or ('FFFFFF' if head else INK), head or bold)
    jcv = {'right': 'left', 'center': 'center', 'left': 'right'}[jc]
    return ('<w:tc><w:tcPr><w:tcW w:w="%d" w:type="dxa"/>%s<w:tcMar><w:top w:w="90" w:type="dxa"/>'
            '<w:left w:w="140" w:type="dxa"/><w:bottom w:w="90" w:type="dxa"/><w:right w:w="140" w:type="dxa"/></w:tcMar>'
            '<w:vAlign w:val="center"/></w:tcPr><w:p><w:pPr><w:bidi/><w:spacing w:before="0" w:after="0"/>'
            '<w:jc w:val="%s"/></w:pPr>%s</w:p></w:tc>') % (w, sh, jcv, run)


def _table(head, rows, widths):
    """טבלה מימין לשמאל: שורת כותרת זהובה, שורות לסירוגין בקרם"""
    tw = sum(widths)
    b = '<w:%s w:val="single" w:sz="4" w:space="0" w:color="%s"/>'
    borders = ''.join(b % (k, RULE) for k in ('top', 'left', 'bottom', 'right', 'insideH', 'insideV'))
    x = ('<w:tbl><w:tblPr><w:bidiVisual/><w:tblW w:w="%d" w:type="dxa"/><w:jc w:val="center"/><w:tblBorders>%s</w:tblBorders>'
         '<w:tblLayout w:type="fixed"/></w:tblPr><w:tblGrid>%s</w:tblGrid>') % (
        tw, borders, ''.join('<w:gridCol w:w="%d"/>' % w for w in widths))
    x += '<w:tr><w:trPr><w:tblHeader/><w:cantSplit/></w:trPr>%s</w:tr>' % ''.join(
        _cell(h, w, head=True) for h, w in zip(head, widths))
    for i, r in enumerate(rows):
        fill = CREAM if i % 2 else 'FFFFFF'
        x += '<w:tr><w:trPr><w:cantSplit/></w:trPr>%s</w:tr>' % ''.join(
            _cell(v, w, fill=fill, jc='right' if j == 0 else 'center', bold=(j == 0)) for j, (v, w) in enumerate(zip(r, widths)))
    return x + '</w:tbl>'


def _notice(text):
    """מסגרת הודעה (כמו המסגרת של מספר הטלפון בבלאנק: קו זהוב כפול ורקע קרם). שורה ראשונה מודגשת"""
    lines = [x.strip() for x in str(text).strip().splitlines() if x.strip()]
    paras = ''
    for k, ln in enumerate(lines):
        first = k == 0 and len(lines) > 1
        paras += ('<w:p><w:pPr><w:bidi/><w:spacing w:before="0" w:after="%d" w:line="300" w:lineRule="auto"/><w:jc w:val="center"/></w:pPr>%s</w:p>'
                  % (100 if first else 40, _run(ln, 30 if first else 26, RED if first else INK, first)))
    d = '<w:%s w:val="double" w:sz="6" w:space="0" w:color="%s"/>'
    return ('<w:tbl><w:tblPr><w:bidiVisual/><w:tblW w:w="6600" w:type="dxa"/><w:jc w:val="center"/><w:tblLayout w:type="fixed"/></w:tblPr>'
            '<w:tblGrid><w:gridCol w:w="6600"/></w:tblGrid><w:tr><w:trPr><w:cantSplit/></w:trPr><w:tc><w:tcPr><w:tcW w:w="6600" w:type="dxa"/>'
            '<w:tcBorders>%s</w:tcBorders><w:shd w:val="clear" w:color="auto" w:fill="%s"/><w:tcMar><w:top w:w="160" w:type="dxa"/>'
            '<w:left w:w="227" w:type="dxa"/><w:bottom w:w="120" w:type="dxa"/><w:right w:w="227" w:type="dxa"/></w:tcMar></w:tcPr>%s</w:tc></w:tr></w:tbl>'
            % (''.join(d % (k, GOLD) for k in ('top', 'left', 'bottom', 'right')), CREAM, paras)) + \
        _p(_run('', 10), after=200)


def _nis(v):
    if v is None:
        return '—'
    return '₪%s' % ('%g' % v if v != int(v) else '{:,}'.format(int(v)))


def clean_name(name):
    """"2. מנוי רגיל" → "מנוי רגיל" """
    return re.sub(r'^\s*\d+\s*[.\-)]\s*', '', str(name or '')).strip() or str(name or '')


def pricelist(groups, *, title='מחירון קבוצות המקווה', date_line='', notice=''):
    """groups — [{'name','price'}] (מחיר לחודש בשקלים), בסדר שבו יופיעו. מחזיר bytes של קובץ docx.
    מאיר: "לא צריך לכתוב כניסה בודדת ולא על קבוצה ערך צבור… ולא על הקהילה, אני יביא לך את הפרטים אל תמציא"
    — רק הקבוצות שנבחרו והמחיר לחודש. בלי טקסטים נוספים."""
    W = [4600, 2000]             # רוחב הגוף בבלאנק: 11907 − 1134 − 2268 = 8505
    body = _p(_run(title, 44, RED, True), jc='center', after=40)
    if date_line:
        body += _p(_run(date_line, 22, GOLD), jc='center', after=60)
    body += _dia()
    if str(notice or '').strip():
        body += _notice(notice)
    body += _table(['קבוצה', 'מחיר לחודש'], [[clean_name(g['name']), _nis(g.get('price'))] for g in groups], W)
    body += _p(_run('הנהלת המקווה', 28, RED, True), jc='center', before=400, after=0)
    return _fill(body)


def _fill(body_xml):
    with open(BLANK, 'rb') as f:
        src = zipfile.ZipFile(io.BytesIO(f.read()))
    doc = src.read('word/document.xml').decode('utf-8')
    i = doc.index('<w:body>') + len('<w:body>')
    j = doc.rindex('<w:sectPr')            # הגדרות העמוד והכותרת (הבלאנק) נשארות
    doc = doc[:i] + body_xml + doc[j:]
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        for it in src.infolist():
            data = doc.encode('utf-8') if it.filename == 'word/document.xml' else src.read(it.filename)
            z.writestr(it, data)
    return out.getvalue()
