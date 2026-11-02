"""/admin/local-videos/ -- the manager's tool for the local (Mac, offline) video copies (local_videos.py).

Per trip: set the Mac folder, see each video observation's local status, pick its file from the folder's video files
(the automatic name match is pre-selected), fill every empty one automatically, and play the local copy. Writes
touch only the two local-video columns (update(), no save() side effects)."""
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.shortcuts import render, redirect
from django.urls import reverse
from urllib.parse import urlencode

from .models import DiveTrip, Sample
from .local_videos import (statuses, match_trip, video_files, trip_folder, validate_local_video_folder,
                           validate_local_video_file, local_video_url, STATUS_OK)

STATUS_LABELS = {'ok': 'קיים במק', 'missing': 'לא הוגדר', 'not_found': 'הקובץ לא נמצא בתיקייה',
                 'unreachable': 'התיקייה לא נגישה במחשב הזה'}


def _videos(trip):
    return list(Sample.objects.filter(trip=trip, deleted_at__isnull=True).exclude(video_url='')
                .select_related('trip', 'species').order_by('species__scientific_name', 'title', 'pk'))


@staff_member_required
def local_videos(request):
    if not request.user.is_superuser: raise PermissionDenied
    trips = list(DiveTrip.objects.filter(samples__deleted_at__isnull=True).exclude(samples__video_url='').distinct()
                 .order_by('-year', '-month', 'code'))
    summary = []
    for trip in trips:
        found = statuses(_videos(trip))
        summary.append({'trip': trip, 'total': len(found), 'ok': sum(1 for s in found.values() if s == STATUS_OK),
                        'missing': sum(1 for s in found.values() if s in ('missing', 'not_found'))})
    trip = next((t for t in trips if t.code == request.GET.get('trip', request.POST.get('trip'))), None)
    if request.method == 'POST' and trip:
        back = reverse('local-videos') + '?' + urlencode({'trip': trip.code})
        action = request.POST.get('action')
        try:
            with transaction.atomic():
                if action == 'folder':
                    folder = request.POST.get('folder', '').strip()
                    validate_local_video_folder(folder)
                    DiveTrip.objects.filter(pk=trip.pk).update(local_video_folder=folder)
                    messages.success(request, 'תיקיית המסע נשמרה.')
                elif action == 'auto':
                    matches = match_trip(_videos(trip), trip_folder(trip))[0] if trip_folder(trip) else []
                    count = 0
                    for sample, name in matches:
                        if not sample.local_video_file:
                            Sample.objects.filter(pk=sample.pk).update(local_video_file=name); count += 1
                    messages.success(request, f'מולאו אוטומטית {count} שמות קבצים.')
                elif action == 'files':
                    ids = {s.pk: s for s in _videos(trip)}
                    count = 0
                    for key, value in request.POST.items():
                        if not key.startswith('file-'): continue
                        sample = ids.get(int(key[5:])) if key[5:].isdigit() else None
                        if sample is None: continue
                        value = value.strip()
                        validate_local_video_file(value)
                        if value != sample.local_video_file:
                            Sample.objects.filter(pk=sample.pk).update(local_video_file=value); count += 1
                    messages.success(request, f'נשמרו {count} שינויים.')
        except ValidationError as error:
            messages.error(request, ' '.join(error.messages))
        return redirect(back)
    context = {'summary': summary, 'trip': trip}
    if trip:
        videos = _videos(trip)
        folder = trip_folder(trip)
        found = statuses(videos)
        files = sorted(n for names in video_files(folder).values() for n in names) if folder else []
        suggested = dict((s.pk, n) for s, n in match_trip(videos, folder)[0]) if folder and folder.is_dir() else {}
        used = {s.local_video_file for s in videos if s.local_video_file}
        rows = []
        for s in videos:
            status = found.get(s.pk)
            rows.append({'sample': s, 'status': status, 'status_label': STATUS_LABELS.get(status, ''),
                         'choice': s.local_video_file or suggested.get(s.pk, ''), 'suggested': not s.local_video_file and s.pk in suggested,
                         'play_url': local_video_url(s) if status == STATUS_OK else ''})
        context.update({'rows': rows, 'files': files, 'unused': [f for f in files if f not in used],
                        'folder_ok': bool(folder and folder.is_dir())})
    return render(request, 'observations/local_videos.html', context)
