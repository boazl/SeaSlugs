"""/admin/drive-videos/ -- re-read the Google Drive ids of the local video copies (drive_videos.py).

GET shows the scan (what would change); "update" scans again, backs up and saves the new ids and empties the ids of
copies that are gone. Only on the Mac: the live site has no Drive folder and gets the ids by the samples table
transfer."""
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import render, redirect

from .drive_videos import scan, apply, available, drive_root, SAME, UPDATE, CLEAR, WAITING, MISSING
from .table_transfer import create_backup


@staff_member_required
def drive_videos(request):
    if not request.user.is_superuser: raise PermissionDenied
    if not available():
        return render(request, 'observations/drive_videos.html', {'unavailable': True, 'root': drive_root()})
    if request.method == 'POST':
        rows = scan()
        if any(r['action'] in (UPDATE, CLEAR) for r in rows):
            create_backup()
            count = apply(rows)
            messages.success(request, f'עודכנו {count} מזהי Google Drive. כדי שהשינוי יגיע לאתר החי — העבר את טבלת התצפיות (samples).')
        else:
            messages.info(request, 'אין שינויים לשמור.')
        return redirect('drive-videos')
    rows = scan()
    groups = {action: [r for r in rows if r['action'] == action] for action in (UPDATE, CLEAR, WAITING, MISSING)}
    return render(request, 'observations/drive_videos.html', {
        'root': drive_root(), 'groups': groups, 'same': sum(1 for r in rows if r['action'] == SAME),
        'changes': len(groups[UPDATE]) + len(groups[CLEAR])})
