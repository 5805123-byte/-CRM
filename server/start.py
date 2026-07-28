# -*- coding: utf-8 -*-
"""נקודת הכניסה לאירוח: זורע את בסיס הנתונים בפעם הראשונה, ואז מריץ את השרת."""
import os
HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
DB = os.environ.get('DB_PATH') or os.path.join(HERE, 'crm.db')

if not os.path.exists(DB):
    print('בסיס נתונים לא קיים — זורע מהאקסל...')
    import import_data
    import_data.main()

import app
app.serve()
