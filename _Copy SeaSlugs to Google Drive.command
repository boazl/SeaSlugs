# Copy the site and the observations' video files into Google Drive (SeaSlugs.org.il folder).
# Safe to run again: unchanged files are skipped, an interrupted copy continues where it stopped.
cd /Users/boazliebes/SeaSlugs
source .venv/bin/activate
set -e
python manage.py backup_database
python manage.py migrate
# Djibouti's video moved into "Video Output"
python manage.py match_local_videos --apply --trip W --folder "/Users/boazliebes/Djibouti/Video Output" --set "521=פנינת ים.mp4" | tail -3
python manage.py copy_to_drive
echo
echo "Done. After Google Drive finishes uploading, share the Videos folder and run '_Fill Drive video ids.command'."
