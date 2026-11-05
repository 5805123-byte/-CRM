# הרצה: python3 tools/mikve_takanon.py out.docx
"""התקנון והמחירון של המקווה — על הבלאנק של המקווה, ברוח המודעה הישנה.
טקסט מהמודעה הישנה כמו שהוא; המנויים מהמחירון החדש; בלי המילה "קבוצה"."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'server'))
from xml.sax.saxutils import escape
import mk_docs as M

INK, RED, GOLD, CREAM = '2A2320', '6E1B1B', 'A8823A', 'FBF6EA'
BLUE, BLUE_L = '1F5FD6', 'EEF3FD'
ORANGE, ORANGE_L = 'D98A0B', 'FEF6E4'
TEAL, TEAL_L = '0E8F7E', 'EAF7F4'
PURPLE, PURPLE_L = '6B4BC4', 'F1EDFB'
NAVY, NAVY_L = '1E2A5A', 'EEF1F8'
ALERT, ALERT_L = 'C62828', 'FDECEC'
GREEN = '0E7A55'
GREY, GREY_L = '6B7280', 'F3F5F8'
BODY = 8505
FONT = '<w:rFonts w:asciiTheme="majorBidi" w:hAnsiTheme="majorBidi" w:cstheme="majorBidi"/>'


def R(text, size=20, color=INK, bold=False):
    b = '<w:b/><w:bCs/>' if bold else ''
    return ('<w:r><w:rPr>%s%s<w:color w:val="%s"/><w:sz w:val="%d"/><w:szCs w:val="%d"/><w:rtl/></w:rPr>'
            '<w:t xml:space="preserve">%s</w:t></w:r>') % (FONT, b, color, size, size, escape(str(text)))


def P(runs, jc='right', before=0, after=40, line=264, shade=None, keep=False, ind=0, bottom=None):
    if isinstance(runs, str) and not runs.startswith('<w:r>'):
        runs = R(runs)
    jcv = {'right': 'left', 'center': 'center', 'left': 'right', 'both': 'both'}[jc]
    sh = '<w:shd w:val="clear" w:color="auto" w:fill="%s"/>' % shade if shade else ''
    bd = ('<w:pBdr><w:bottom w:val="single" w:sz="%s"/></w:pBdr>' % bottom) if bottom else ''
    kn = '<w:keepNext/>' if keep else ''
    ind_ = '<w:ind w:start="%d"/>' % ind if ind else ''
    return ('<w:p><w:pPr>%s%s%s<w:bidi/><w:spacing w:before="%d" w:after="%d" w:line="%d" w:lineRule="auto"/>%s'
            '<w:jc w:val="%s"/></w:pPr>%s</w:p>') % (kn, bd, sh, before, after, line, ind_, jcv, runs)


def bullet(runs, color=TEAL, size=19):
    if not runs.startswith('<w:r>'):
        runs = R(runs, size)
    return P(R('●  ', 12, color) + runs, after=30, line=252)


def gap(h=120):
    return '<w:p><w:pPr><w:spacing w:before="0" w:after="0" w:line="%d" w:lineRule="exact"/></w:pPr></w:p>' % h


def borders(color, top=None, sz=6, topsz=30, val='single'):
    t = top or color
    return ('<w:tcBorders><w:top w:val="single" w:sz="%d" w:space="0" w:color="%s"/>'
            '<w:left w:val="%s" w:sz="%d" w:space="0" w:color="%s"/><w:bottom w:val="%s" w:sz="%d" w:space="0" w:color="%s"/>'
            '<w:right w:val="%s" w:sz="%d" w:space="0" w:color="%s"/></w:tcBorders>') % (
        topsz, t, val, sz, color, val, sz, color, val, sz, color)


NOB = ('<w:tcBorders><w:top w:val="nil"/><w:left w:val="nil"/><w:bottom w:val="nil"/><w:right w:val="nil"/></w:tcBorders>')


def C(content, w, fill='FFFFFF', bd=NOB, mar=(110, 140, 110, 140), valign='top', span=1):
    if not content.endswith('</w:p>'):
        content += '<w:p><w:pPr><w:spacing w:before="0" w:after="0" w:line="20" w:lineRule="exact"/></w:pPr></w:p>'
    gs = '<w:gridSpan w:val="%d"/>' % span if span > 1 else ''
    t, s, b, e = mar
    return ('<w:tc><w:tcPr><w:tcW w:w="%d" w:type="dxa"/>%s%s<w:shd w:val="clear" w:color="auto" w:fill="%s"/>'
            '<w:tcMar><w:top w:w="%d" w:type="dxa"/><w:left w:w="%d" w:type="dxa"/><w:bottom w:w="%d" w:type="dxa"/>'
            '<w:right w:w="%d" w:type="dxa"/></w:tcMar><w:vAlign w:val="%s"/></w:tcPr>%s</w:tc>') % (
        w, gs, bd, fill, t, s, b, e, valign, content)


def T(rows, widths, spacing=0, total=None):
    tw = total or sum(widths) + spacing * (len(widths) + 1)
    sp = '<w:tblCellSpacing w:w="%d" w:type="dxa"/>' % spacing if spacing else ''
    x = ('<w:tbl><w:tblPr><w:bidiVisual/><w:tblW w:w="%d" w:type="dxa"/><w:jc w:val="center"/>%s'
         '<w:tblBorders><w:top w:val="nil"/><w:left w:val="nil"/><w:bottom w:val="nil"/><w:right w:val="nil"/>'
         '<w:insideH w:val="nil"/><w:insideV w:val="nil"/></w:tblBorders><w:tblLayout w:type="fixed"/>'
         '<w:tblCellMar><w:left w:w="0" w:type="dxa"/><w:right w:w="0" w:type="dxa"/></w:tblCellMar></w:tblPr><w:tblGrid>%s</w:tblGrid>') % (
        tw, sp, ''.join('<w:gridCol w:w="%d"/>' % w for w in widths))
    for r in rows:
        x += '<w:tr><w:trPr><w:cantSplit/></w:trPr>%s</w:tr>' % ''.join(r)
    return x + '</w:tbl>'


def section(title, color=NAVY, sub=''):
    runs = R(title, 30, color, True) + (R('  ' + sub, 18, GREY) if sub else '')
    return P(runs, before=200, after=80, keep=True, bottom='12" w:space="4" w:color="%s' % TEAL)


def nis(v):
    return '₪%s' % v


# ---------- כרטיס מנוי ----------
def card(name, price, color, light, lines, w):
    x = P(R(name, 22, INK, True), jc='center', after=20, line=240)
    x += P(R(nis(price), 44, color, True), jc='center', after=60, line=240, bottom='4" w:space="4" w:color="%s' % color)
    for ln in lines:
        x += bullet(ln, color, 17)
    return C(x, w, light, borders(color, color, sz=6, topsz=36), mar=(90, 110, 80, 110))


def two(text_bold, text, size=17, color=INK):
    return R(text_bold, size, color, True) + R(text, size, color)


W4 = [2050] * 4
row1 = [
    card('מנוי אשמורת הבוקר', 70, PURPLE, PURPLE_L, [], W4[0]),
    card('מנוי רגיל', 140, BLUE, BLUE_L, [
        R('כניסה אחת ביום עד השעה 13:05.', 17),
        two('ימי שישי וערבי חג: ', '2 כניסות ללא הגבלת זמן.'),
        R('המנוי לא כולל מגבת.', 17)], W4[1]),
    card('מנוי מורחב', 180, ORANGE, ORANGE_L, [
        R('2 כניסות ביום.', 17, INK, True),
        R('עם שהייה של שעתיים לפחות בין כניסה לכניסה.', 17),
        R('המנוי לא כולל מגבת.', 17, INK, True)], W4[2]),
    card('מנוי בחורים', 70, TEAL, TEAL_L, [
        R('ימים רגילים - 04:30 - 07:15.', 17),
        two('בימי שישי וערבי חג: ', '2 כניסות עד השעה 14:00.'),
        R('ימי שישי בשעון חורף: עד השעה 13:30 בלבד!', 17, ALERT, True),
        R('המנוי לא כולל מגבת.', 17)], W4[3]),
]
row2 = [
    card('מנוי רגיל + מנוי מגבת קטנה', 170, BLUE, BLUE_L, [R('כולל מנוי מגבת קטנה.', 17, INK, True)], W4[0]),
    card('מנוי רגיל + מגבת גדולה', 190, BLUE, BLUE_L, [R('כולל מגבת גדולה.', 17, INK, True)], W4[1]),
    card('מנוי מורחב + מגבת גדולה', 230, ORANGE, ORANGE_L, [R('כולל מגבת גדולה.', 17, INK, True)], W4[2]),
    card('מנוי VIP מורחב + מגבת גדולה + מגבת קטנה', 250, GOLD, CREAM, [R('כולל מגבת גדולה ומגבת קטנה.', 17, INK, True)], W4[3]),
]

body = ''
body += P(R('להלן התקנון והמחירון של המקווה', 40, RED, True), jc='center', after=20)
body += P(R('בתוקף מראש חודש כסלו תשפ"ז', 20, GOLD, True), jc='center', after=100)

# הודעה — מנוי המגבות ביחד עם המנוי
note = (P(R('הודעה חשובה', 26, RED, True), jc='center', after=50) +
        P(R('החל מראש חודש כסלו תשפ"ז, מנוי המגבות יהיה ביחד עם המנוי החודשי.', 21), jc='center', after=20) +
        P(R('לא יהיה עוד מנוי מגבות נפרד — בוחרים מנוי שכולל את המגבת, ומשלמים מנוי אחד לחודש.', 21), jc='center', after=20) +
        P(R('ניתן לעבור בין סוגי המנוי באופן אוטומטי דרך המערכת הטלפונית ', 19, GREY) + R('077-3412906', 21, BLUE, True), jc='center', after=0))
dbl = ('<w:tcBorders>' + ''.join('<w:%s w:val="double" w:sz="6" w:space="0" w:color="%s"/>' % (k, GOLD)
                                 for k in ('top', 'left', 'bottom', 'right')) + '</w:tcBorders>')
body += T([[C(note, 7400, CREAM, dbl, mar=(140, 200, 120, 200))]], [7400])

body += section('מנויים חודשיים')
body += T([row1], W4, spacing=60, total=BODY)
body += section('מנויים חודשיים הכוללים מגבת')
body += T([row2], W4, spacing=60, total=BODY)

# ---------- תעריפי כניסה מעבר לשעות המנוי ----------
body += section('תעריפי כניסה למנויים מעבר לשעות המנוי', sub='(בחיוב ערך צבור)')


def trow(label, price, w, hot=False):
    col = ALERT if hot else INK
    return P(R('◷  ', 16, GREY) + R(label, 18, col, hot) + R('   ' + nis(price), 19, col, True),
             after=30, shade=ALERT_L if hot else None)


weekday = (P(R('ימי חול', 21, NAVY, True), after=60, bottom='4" w:space="4" w:color="DDE3EC') +
           trow('חצי שעה ראשונה', 2, 0) + trow('עד השעה 13:00', 4, 0) + trow('13:00 - 17:00', 8, 0) +
           trow('החל מ-17:00', 16, 0, True) +
           P(two('ימי חנוכה: ', '(16:00-18:00 למנויים ללא מורחב) - ₪8', 16, '9A5B00'), before=60, after=0))
friday = (P(R('ימי שישי', 21, NAVY, True) + R('  (למוגבלים ל-14:00)', 15, GREY), after=60, bottom='4" w:space="4" w:color="DDE3EC') +
          trow('14:00 - 14:30', 4, 0) + trow('החל משעה 14:30', 8, 0) + trow('שעה לפני הדלקת הנרות', 16, 0, True))
body += T([[C(weekday, 3950, GREY_L, mar=(120, 150, 120, 150)), C(friday, 3950, GREY_L, mar=(120, 150, 120, 150))]],
          [3950, 3950], spacing=80, total=BODY)


body += P('<w:r><w:br w:type="page"/></w:r>', after=0)
# ---------- כניסה חד-פעמית (מזדמן) ----------
def prow(label, price, fill='FFFFFF', color=INK, bold=False, note=''):
    lab = R(label, 19, color, bold) + (R('  ' + note, 15, GREY) if note else '')
    return [C(P(lab, after=0), 6100, fill, mar=(70, 140, 70, 140), valign='center'),
            C(P(R(nis(price), 22, color, True), jc='left', after=0), 1900, fill, mar=(70, 140, 70, 140), valign='center')]


def subhead(t, note=''):
    return [C(P(R(t, 21, NAVY, True) + (R('  ' + note, 15, GREY) if note else ''), after=0, bottom='4" w:space="4" w:color="DDE3EC'),
              8000, 'FFFFFF', mar=(120, 140, 40, 140), span=2)]


body += section('כניסה חד-פעמית (מזדמן)')
rows = [subhead('יום חול רגיל', '(כולל מגבת)'),
        prow('03:30 - 12:00', 15, GREY_L), prow('12:00 - 17:00', 20), prow('17:00 - 03:30', 30, GREY_L),
        prow('ימי חנוכה (16:00-18:00)', 15, 'FFF7E0', '9A5B00', True, '(ללא הנחת ערך צבור)'),
        subhead('ימי שישי, שבת וחגים'),
        prow('ימי שישי (עד שעה וחצי לפני הדלקת נרות)', 20),
        prow('ימי שישי (שעה וחצי לפני הדלקת נרות)', 30, ALERT_L, ALERT, True),
        prow('ערבי חג (עד שעה וחצי לפני הדלקת נרות)', 30),
        prow('ערבי חג (בשעה וחצי לפני הדלקת נרות)', 40, ALERT_L, ALERT, True),
        prow('שבת וחג (ללא מגבת)', 10, 'FFFFFF', GREEN, True),
        [C(P(two('כניסה בשבת למזדמנים: ', 'למעט אנשים ששילמו כניסה בערב שבת, מותרת כניסה אחת ללא מגבת.', 16, GREY), after=0),
           8000, GREY_L, mar=(70, 140, 70, 140), span=2)]]
body += T(rows, [6100, 1900], total=8000)

# ---------- ערך צבור + שירות מגבות ----------
erech = (P(R('ערך צבור (פעימות)', 24, 'FFFFFF', True), after=20) +
         P(two('מינימום הטענה: ', '₪200', 18, 'DDE3F5'), after=20) +
         P(R('כולל מגבת', 17, 'F7C948', True), after=80) +
         P(R('20%  ', 34, 'F7C948', True) + R('הנחה קבועה', 20, 'FFFFFF', True), after=0) +
         P(R('(למעט שעות אחה"צ בחנוכה)', 15, 'C9D1EA'), after=0))
erech_t = T([[C(erech, 3900, NAVY, mar=(140, 160, 140, 160))],
             [C(P(R('מחיר לאחר הנחה:', 19, INK, True), after=0), 3900, 'FFFFFF', mar=(100, 160, 40, 160))]] +
            [[C(P(R(a, 18, INK, b) + R('   ' + nis(p), 20, col, True), after=0, bottom='2" w:space="4" w:color="E5E7EB'), 3900, 'FFFFFF', mar=(60, 160, 60, 160))]
             for a, p, col, b in (('בוקר', 12, BLUE, False), ('צהריים / ערשב"ק מוקדם', 16, BLUE, False),
                                  ('ערב / ערשב"ק מאוחר', 24, 'B26A00', True))], [3900])
towel = (P(R('שירות מגבות', 24, NAVY, True), after=60, bottom='8" w:space="4" w:color="%s' % TEAL) +
         P(R('מראש חודש כסלו מנוי המגבות כלול במנוי החודשי — ראו "מנויים חודשיים הכוללים מגבת".', 17, TEAL, True), after=80, shade=TEAL_L) +
         P(R('מגבת גדולה – שימוש חד-פעמי', 19) + R('   ₪5', 20, INK, True), after=30) +
         P(R('מגבת קטנה – שימוש חד-פעמי', 19) + R('   ₪2', 20, INK, True), after=30) +
         P(R('מגבת נוספת למנוי', 19) + R('   ₪3', 20, INK, True), after=80) +
         P(two('שימו לב: ', 'בשבת, חג, פורים, חוה"מ ותשעת הימים: אין התחייבות לאספקת מגבות. '
               'הנהלת המקווה תעשה מאמץ להביא מגבת קטנה יותר שיהיה לשימוש גם בזמנים המיוחדים.', 16, GREY), jc='both', after=40, shade=GREY_L) +
         P(R('אין להניח מגבות על הרצפה - הדבר גורם נזק למגבת.', 16, ALERT, True), after=0))
body += gap(160)
body += T([[C(erech_t, 3900, 'FFFFFF', borders('C9D1EA', NAVY, sz=4, topsz=4), mar=(0, 0, 0, 0)),
            C(towel, 3900, 'FFFFFF', borders('9ED9CF', TEAL, sz=6, topsz=30), mar=(120, 150, 120, 150))]],
          [3900, 3900], spacing=100, total=BODY)


body += P('<w:r><w:br w:type="page"/></w:r>', after=0)
# ---------- תקנון, הרשמה וקנסות ----------
fines = T([[C(P(R('קנס כספי (הכנסת אדם אחר ע"י מנוי / עישון / מזון):', 18, RED, True), after=0, bottom='4" w:space="4" w:color="F3C4C4'),
              7300, ALERT_L, mar=(90, 140, 40, 140), span=2)],
           [C(P(R('קנס בסיס', 19), after=0), 5300, ALERT_L, mar=(50, 140, 50, 140)),
            C(P(R('₪50', 20, INK, True), jc='left', after=0), 2000, ALERT_L, mar=(50, 140, 50, 140))],
           [C(P(R('הפרה שנייה', 19), after=0), 5300, ALERT_L, mar=(50, 140, 50, 140)),
            C(P(R('₪100', 20, INK, True), jc='left', after=0), 2000, ALERT_L, mar=(50, 140, 50, 140))],
           [C(P(R('הפרה חוזרת: ביטול מנוי', 17, 'FFFFFF', True), jc='center', after=0), 7300, ALERT, mar=(50, 140, 50, 140), span=2)]],
          [5300, 2000], total=7300)
join = T([[C(P(two('הצטרפות למנוי בחורים: ', 'רק בחודשים חשון, אלול ואייר.', 18, TEAL), after=20) +
             P(R('אין אפשרות להצטרף בתשרי וניסן כלל.', 18, ALERT, True), after=0),
             7300, TEAL_L, '<w:tcBorders><w:right w:val="single" w:sz="24" w:space="0" w:color="%s"/></w:tcBorders>' % TEAL,
             mar=(90, 160, 90, 160))]], [7300], total=7300)
rules = (P(R('⚖  תקנון, הרשמה וקנסות', 26, RED, True), after=80, bottom='6" w:space="4" w:color="F3C4C4') + fines + gap(120) +
         P(two('הרשמה ופניות: ', 'קיימים ב\'נדרים פלוס\' 2 טפסים נפרדים: להרשמה של מנוי חדש, ולפניות שוטפות/ עדכון סוגי מנוי וכו\'.', 18), jc='both', after=40) +
         P(two('חשוב: ', 'הרשמה במכונה ללא בחירת מנוי תחויב ככניסה מזדמנת.', 18, ALERT), after=80) +
         join + gap(100) +
         P(R('פניות מטופלות עד 2 ימי עסקים.', 18), after=30) +
         P(R('פעם בשנה תידרשו לחדש רישיון שנתי על סך ₪10.', 18), after=30) +
         P(two('מעבר בין סוגי המנוי: ', 'לא ניתן לעבור מנוי מט"ו אלול עד א\' חשון.', 18, ALERT), after=80) +
         bullet(R('הכניסה והשימוש במקווה הינה בהתאם לתקנון המקווה.', 16, GREY), ALERT, 16) +
         bullet(R('כל זיכוי כספי או תביעה יוכרע לפי התקנון.', 16, GREY), ALERT, 16) +
         bullet(R('מעשנים ומפרי חוק מוותרים מראש על כל טענה.', 16, GREY), ALERT, 16) +
         bullet(R('התקנון המלא ב\'נדרים פלוס\' ובמשרדי העמותה.', 16, GREY), ALERT, 16) +
         bullet(R('אין לבצע מגביות או להדביק מודעות ללא אישור ראש הכולל!', 16, INK, True), ALERT, 16) +
         bullet(R('איסור חמור לטבול כלים במקווה!', 16, ALERT, True), ALERT, 16))
body += gap(200)
body += T([[C(rules, 7900, 'FFFFFF', borders('F0B4B4', ALERT, sz=6, topsz=6) .replace(
    '<w:right w:val="single" w:sz="6"', '<w:right w:val="single" w:sz="36"'), mar=(140, 180, 140, 200))]], [7900], total=7900)

# ---------- הצהרות ----------
def legal(t, txt):
    return P(R(t, 18, NAVY, True), after=40) + P(R(txt, 15, '4B5563'), jc='both', after=0, line=252)


body += gap(200)
body += T([[C(legal('הצהרה משפטית:', 'המקווה הינו מוסד פרטי (לא ציבורי). השימוש מותר לאנשים פרטיים בכפוף לתקנון. '
                    'הכניסה מהווה ויתור מוחלט על כל תביעת נזיקין (גוף/רכוש) מכל סיבה שהיא.'), 2700, NAVY_L, mar=(120, 140, 120, 140)),
            C(legal('מצלמות אבטחה:', 'המקום מצולם לצרכי אבטחה. הכניסה מהווה הסכמה לצילום וויתור מוחלט ובלתי חוזר על כל טענה בדבר פגיעה בפרטיות.'),
              2700, NAVY_L, mar=(120, 140, 120, 140)),
            C(legal('חפצים אישיים:', 'הנכנס למקווה מפקיר מראש כל חפץ שהוא ישכח. הנהלת המקווה רשאית לעשות בזה כטוב בעיניה. מתקיים פינוי חפצים כמה פעמים ביום.'),
              2700, NAVY_L, mar=(120, 140, 120, 140))]], [2700, 2700, 2700], spacing=40, total=BODY)
body += P(R('הנהלת המקווה', 26, RED, True), jc='center', before=240, after=0)

out = sys.argv[1]
open(out, 'wb').write(M._fill(body))
print('ok', out)
