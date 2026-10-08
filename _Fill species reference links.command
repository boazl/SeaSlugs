cd /Users/boazliebes/SeaSlugs
source .venv/bin/activate
python manage.py migrate
python manage.py fill_reference_links --apply
