# One-time first fill (Nov 2026): automatic matches + the files that cannot be matched by name.
cd /Users/boazliebes/SeaSlugs
source .venv/bin/activate
set -e
python manage.py match_local_videos --apply
python manage.py match_local_videos --apply --trip V --folder "/Users/boazliebes/Romblon Island/Video Output" --set "105=Romblon 2026 SlideShow.mov"
python manage.py match_local_videos --apply --trip I3 --folder "/Users/boazliebes/Mediterranean/Video Output" --set "106=קניון אכזיב יולי 23.mp4"
python manage.py match_local_videos --apply --trip C --folder "/Users/boazliebes/Anilao 2023/Video" --set "249=87 Slug Video.mp4"
python manage.py match_local_videos --apply --trip W --folder "/Users/boazliebes/Djibouti" --set "521=פנינת ים.mp4"
echo
echo "Done. Remaining without a local file:"
python manage.py match_local_videos | grep -E "^\[|No file|No folder|Several"
