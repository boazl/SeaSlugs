cd /Users/boazliebes/SeaSlugs
source .venv/bin/activate
python manage.py match_local_videos | tee "Claude outputs/local-videos-match-report.txt"
echo
read -r -p "לשמור את ההתאמות במסד? (y/N) " answer
if [ "$answer" = "y" ] || [ "$answer" = "Y" ]; then
  python manage.py match_local_videos --apply
fi
