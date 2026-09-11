# SeaSlugs — סביבת פיתוח מקומית

Python 3.13, Django 5.2 LTS, SQLite.

## הפעלה

מתוך תיקיית הפרויקט:

```sh
source .venv/bin/activate
python manage.py runserver 127.0.0.1:8000
```

פתחו http://127.0.0.1:8000/ . לעצירה: Control-C.

## חשבון מנהל

```sh
source .venv/bin/activate
python manage.py createsuperuser
```

בחרו שם משתמש וסיסמה ב־Terminal ואז פתחו http://127.0.0.1:8000/admin/ .

## בדיקות

```sh
python manage.py check
python manage.py migrate
```

## שחזור הסביבה

```sh
/opt/homebrew/bin/python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -c "from pathlib import Path; from django.core.management.utils import get_random_secret_key; p = Path('.secret_key'); p.exists() or p.write_text(get_random_secret_key())"
python manage.py migrate
```

ההגדרות מיועדות לפיתוח מקומי בלבד (DEBUG=True). מסד הנתונים, הסביבה והמפתח המקומי אינם נשמרים ב־Git. טרם נוצר חשבון מנהל או חיבור למאגר מרוחק.
