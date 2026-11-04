# After Google Drive has uploaded the Videos folder: read each copy's Drive id and save it.
cd /Users/boazliebes/SeaSlugs
source .venv/bin/activate
python manage.py fill_drive_video_ids --apply
