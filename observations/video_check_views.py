"""/admin/video-check/ -- YouTube videos that disappeared (video_check.py).

A superuser scans every live observation's YouTube link. The last scan's problem ids are kept in the session, and the
page lists the observations still using one of them, each with its choices:
  * update the link -- the video was uploaded to YouTube again; the new link must exist there and not be used by
    another observation. The local / Drive copies stay (they are the same exported file). Not logged on the news page:
    a re-upload is not a new video.
  * remove the link -- only when the observation has a photo; it stays, as a photo observation. The local / Drive
    copy fields are cleared with it.
  * delete the observation -- only when it has no photo (without the video it would have no media). A soft delete,
    as everywhere on the site: a manager can restore it, and it travels to the other environment with its mark.
The local and the live databases are separate: a fix made here reaches the other side only through the table
transfer (samples), or by scanning there as well."""
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import render, redirect
from django.utils import timezone

from . import activity
from .models import Sample, SpeciesArea, youtube_id
from .video_check import (scan, video_ids, check_video, PROBLEM_STATUSES, STATUS_NOT_FOUND, STATUS_RESTRICTED,
                          STATUS_ERROR)

SESSION_KEY = 'video_check'
STATUS_LABELS = {STATUS_NOT_FOUND: 'לא נמצא ב-YouTube (נמחק)',
                 STATUS_RESTRICTED: 'פרטי או חסום להטמעה',
                 STATUS_ERROR: 'הבדיקה נכשלה (אין תשובה מ-YouTube)'}


def _live_video_samples():
    return list(Sample.objects.filter(deleted_at__isnull=True).exclude(video_url='')
                .select_related('trip', 'species').order_by('pk'))


def _species_page_slug(sample):
    identity = sample.gallery_identity()
    if not identity: return ''
    return SpeciesArea.objects.filter(species_id=identity[0], country_id=identity[1], sea_id=identity[2],
                                      undetermined_variant=identity[3]).values_list('slug', flat=True).first() or ''


def _forget_if_unused(request, video_id):
    """Drop a problem id from the stored scan once no live observation uses it any more."""
    stored = request.session.get(SESSION_KEY)
    if not stored or video_id not in stored['problems']: return
    if video_id not in video_ids(_live_video_samples()):
        del stored['problems'][video_id]
        request.session[SESSION_KEY] = stored


def _apply(request, action, sample):
    old_id = youtube_id(sample.video_url)
    if action == 'update':
        url = request.POST.get('url', '').strip()
        new_id = youtube_id(url)
        if new_id == old_id:
            raise ValidationError('זה אותו סרטון — יש להזין את הקישור לסרטון שהועלה מחדש.')
        if check_video(new_id) == STATUS_NOT_FOUND:
            raise ValidationError('הסרטון בקישור החדש לא נמצא ב-YouTube.')
        sample.video_url = url
        sample.full_clean(validate_constraints=False)          # also refuses a video another observation already uses
        with activity.suppressed():                             # a re-upload is not a new video on the news page
            sample.save()
        message = f'הקישור של תצפית {sample.pk} עודכן.'
    elif action == 'remove_link':
        if not sample.image:
            raise ValidationError('לתצפית אין תמונה — מחיקת הקישור תשאיר אותה בלי מדיה. יש למחוק את התצפית.')
        sample.video_url = ''; sample.local_video_file = ''; sample.drive_video_id = ''
        sample.full_clean(validate_constraints=False)
        sample.save()
        message = f'הקישור לסרטון הוסר מתצפית {sample.pk}; התצפית נשארה עם התמונה.'
    elif action == 'delete':
        if sample.image:
            raise ValidationError('לתצפית יש תמונה — יש למחוק רק את הקישור לסרטון.')
        sample.soft_delete(request.user)
        message = f'תצפית {sample.pk} נמחקה (מנהל יכול לשחזר אותה).'
    else:
        raise ValidationError('פעולה לא מוכרת.')
    _forget_if_unused(request, old_id)
    return message


@staff_member_required
def video_check(request):
    if not request.user.is_superuser: raise PermissionDenied
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'scan':
            found = video_ids(_live_video_samples())
            statuses = scan(found)
            request.session[SESSION_KEY] = {
                'at': timezone.localtime().strftime('%d/%m/%Y %H:%M'), 'checked': len(statuses),
                'problems': {vid: status for vid, status in statuses.items() if status in PROBLEM_STATUSES}}
            bad = sum(1 for s in statuses.values() if s in PROBLEM_STATUSES)
            messages.success(request, f'נבדקו {len(statuses)} סרטונים; נמצאו {bad} בעייתיים.')
        else:
            sample = Sample.objects.filter(pk=request.POST.get('sample') or 0, deleted_at__isnull=True).exclude(video_url='').first()
            if sample is None:
                messages.error(request, 'התצפית לא נמצאה, או שכבר אין לה סרטון.')
            else:
                try:
                    messages.success(request, _apply(request, action, sample))
                except ValidationError as error:
                    messages.error(request, ' '.join(error.messages))
        return redirect('video-check')
    stored = request.session.get(SESSION_KEY)
    rows = []
    if stored:
        found = video_ids(_live_video_samples())
        for vid, status in sorted(stored['problems'].items(), key=lambda item: (PROBLEM_STATUSES.index(item[1]), item[0])):
            for sample in found.get(vid, ()):
                rows.append({'sample': sample, 'video_id': vid, 'status': status, 'status_label': STATUS_LABELS[status],
                             'has_image': bool(sample.image), 'species_slug': _species_page_slug(sample)})
    return render(request, 'observations/video_check.html', {'stored': stored, 'rows': rows})
