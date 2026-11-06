"""/admin/local-videos/import/ -- attach a dive trip's video files to its observations (Mac only).

Like the folder import of photos, by dive trip: the manager picks the trip and the Mac folder of its exported
videos; every video file there gets a row with
  * the observation it belongs to -- the one already holding this file, else the automatic match by species name
    (local_videos.match_trip), else "a new observation" with fields guessed from the file name (species, cf./aff.,
    juv.) plus site, day and depth;
  * the existing observation's fields (species, site, day, depth, photo, current YouTube / file / Drive id);
  * where the file is on the Mac and where its copy is in Google Drive (with its Drive id, or "will be copied");
  * the YouTube link -- required for every selected row before anything is saved.
Applying (one transaction, after a backup): sets the trip's video folder, writes video_url, local_video_file and the
Drive id on each observation (creating the new ones; a manager's save publishes a complete one), then copies the
files that are not in Google Drive yet into it and reads the ids Drive has already given them. A copy Drive has not
uploaded yet gets its id later on /admin/drive-videos/. A link YouTube reports as deleted is refused.
Nothing is uploaded through the browser: the files stay where they are."""
import json
import re
import shutil
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.shortcuts import render, redirect
from django.urls import reverse
from urllib.parse import urlencode

from . import drive_videos
from .folder_import import match_species, filename_species, resolve_species_text, normalized
from .local_videos import video_files, match_trip, validate_local_video_folder, find_video_output_folders
from .management.commands.copy_to_drive import drive_path_for
from .models import LIBRARY_TRIP_CODES, DiveTrip, Sample, Site, Species, IdentificationQualifier, LifeStage, youtube_id
from .table_transfer import create_backup
from .video_check import check_video, STATUS_NOT_FOUND

NEW = 'new'
KINDS = (Sample.Kind.SPECIES, Sample.Kind.COLLECTION)


def folder_files(folder):
    return sorted(name for names in video_files(folder).values() for name in names)


def trip_samples(trip, deleted=False):
    return list(Sample.objects.filter(trip=trip, deleted_at__isnull=not deleted, kind__in=KINDS)
                .select_related('trip', 'species', 'site').order_by('species__scientific_name', 'title', 'pk'))


def same_folder(trip, folder):
    return bool(trip.local_video_folder) and Path(trip.local_video_folder).expanduser() == Path(folder).expanduser()


def drive_state(path):
    """{'available', 'path' (shown relative to the Drive folder), 'exists', 'id'} of the file's Google Drive copy."""
    root = drive_videos.drive_root()
    if not root.is_dir(): return {'available': False, 'path': '', 'exists': False, 'id': ''}
    copy = drive_path_for(path, root)
    exists = copy.is_file()
    return {'available': True, 'path': str(copy.relative_to(root)), 'full': copy, 'exists': exists,
            'id': drive_videos.drive_id(copy) if exists else ''}


def sample_label(sample):
    marks = (' — סרטון' if sample.video_url else '') + (' — תמונה' if sample.image else '') + (' — מחוקה' if sample.deleted_at else '')
    return f'#{sample.pk} {sample.taxon_label or sample.title}{marks}'


def sample_info(sample):
    return {'label': sample.taxon_label or sample.title, 'kind': sample.get_kind_display(),
            'site': str(sample.site) if sample.site_id else (sample.site_other or ''), 'day': sample.day or '',
            'depth': str(sample.depth) if sample.depth is not None else '', 'image': sample.image.url if sample.image else '',
            'video_url': sample.video_url, 'file': sample.local_video_file, 'drive': sample.drive_video_id,
            'status': 'מחוקה — שמירה תשחזר אותה' if sample.deleted_at else sample.get_status_display(), 'deleted': bool(sample.deleted_at)}


def guess_new(name, species):
    """Fields for a new observation, guessed from the file name."""
    species_id, variant = match_species(name, species)
    by_pk = {s.pk: s for s in species}
    stem = Path(name).stem
    return {'kind': Sample.Kind.SPECIES, 'title': '',
            'species': f'{by_pk[species_id].scientific_name} {variant}'.strip() if species_id else filename_species(name),
            'qualifier': next((q for q in ('cf.', 'aff.') if re.search(rf'\b{q[:-1]}\.?\s', stem, re.I)), ''),
            'life_stage': 'juv.' if re.search(r'\bjuv\b', stem, re.I) else '', 'site': '', 'day': '', 'depth': ''}


def build_rows(trip, folder, posted=None):
    names = folder_files(folder)
    samples = trip_samples(trip)
    # Deleted observations of the trip are offered too: a file that belongs to one of them would otherwise show as
    # "a new observation". A live observation always comes first; choosing a deleted one restores it on saving.
    deleted = trip_samples(trip, deleted=True)
    by_pk = {s.pk: s for s in samples + deleted}
    found = []                                  # in priority order: live holder, live match, deleted holder, deleted match
    for group in (samples, deleted):
        holders = {s.local_video_file: s for s in group if s.local_video_file} if same_folder(trip, folder) else {}
        matches = {}
        for sample, name in match_trip([s for s in group if s not in holders.values()], folder)[0]: matches.setdefault(name, sample)
        found += [holders, matches]
    assigned = found[0]
    species = list(Species.objects.all())
    rows = []
    for index, name in enumerate(names):
        path = Path(folder).expanduser() / name
        sample = next((d[name] for d in found if name in d), None)
        drive = drive_state(path)
        done = bool(sample and assigned.get(name) is sample and sample.video_url
                    and (not drive['available'] or (drive['id'] and drive['id'] == sample.drive_video_id)))
        restore = bool(sample and sample.deleted_at)
        row = {'index': index, 'name': name, 'path': str(path), 'size': path.stat().st_size if path.is_file() else 0,
               'drive': drive, 'sample': str(sample.pk) if sample else NEW, 'url': sample.video_url if sample else '',
               # selected by default: only a file that belongs to a live observation and is not attached to it yet
               'checked': bool(sample) and not done and not restore, 'done': done, 'deleted_match': restore,
               'new': guess_new(name, species), 'errors': []}
        if posted is not None:
            get = lambda key: posted.get(f'{key}_{index}', '')
            row['checked'] = str(index) in posted.getlist('selected')
            row['sample'] = get('sample') or NEW
            row['url'] = get('url').strip()
            row['new'] = {key: get(key).strip() for key in row['new']}
            if get('name') != name: row['errors'].append('רשימת הקבצים בתיקייה השתנתה — יש לטעון את הדף מחדש.')
        rows.append(row)
    rows.sort(key=lambda r: not r['checked'])          # the selected rows first (a stable sort keeps the file order)
    return rows, by_pk


def _clean_new(row, trip):
    """A new Sample from the row's fields (not saved)."""
    data = row['new']; errors = []
    kind = data['kind'] if data['kind'] in KINDS else Sample.Kind.SPECIES
    sample = Sample(trip=trip, kind=kind)
    if kind == Sample.Kind.SPECIES:
        species_pk, variant = resolve_species_text(data['species'])
        if not species_pk: errors.append(f'המין "{data["species"]}" לא נמצא ברשימת המינים. יש לבחור מין קיים (או להוסיף אותו לרשימה).')
        sample.species_id = species_pk; sample.undetermined_variant = variant
        if data['qualifier'] and data['qualifier'] not in IdentificationQualifier.objects.values_list('code', flat=True): errors.append('סימון זהות לא מוכר.')
        if data['life_stage'] and data['life_stage'] not in LifeStage.objects.values_list('code', flat=True): errors.append('שלב חיים לא מוכר.')
        sample.identification_qualifier = data['qualifier']; sample.life_stage = data['life_stage']
    elif not data['title']:
        errors.append('לאוסף מינים / מסע צלילה יש להזין כותרת.')
    sample.title = data['title']
    if data['site']:
        site = Site.objects.filter(pk=data['site'] if data['site'].isdigit() else 0, region_id=trip.region_id).first()
        if site is None: errors.append('אתר הצלילה אינו באזור המסע.')
        sample.site = site
    if data['day']:
        if not data['day'].isdigit() or not 1 <= int(data['day']) <= 31: errors.append('יום חייב להיות בין 1 ל-31.')
        else: sample.day = int(data['day'])
    if data['depth']:
        try: sample.depth = Decimal(data['depth'])
        except InvalidOperation: errors.append('עומק לא תקין.')
    return sample, errors


def validate(rows, by_pk, trip):
    """Fills each selected row's 'target' (the Sample to write) or its 'errors'. True when everything is valid."""
    seen_samples, seen_videos = {}, {}
    selected = [r for r in rows if r['checked']]
    for row in selected:
        if row['errors']: continue
        if not row['url']:
            row['errors'].append('יש להזין קישור YouTube.')
        else:
            try:
                row['video_id'] = youtube_id(row['url'])
                if row['video_id'] in seen_videos: row['errors'].append(f'אותו סרטון YouTube נבחר גם לקובץ {seen_videos[row["video_id"]]}.')
                seen_videos.setdefault(row['video_id'], row['name'])
            except ValidationError as error:
                row['errors'] += error.messages
        if row['sample'] == NEW:
            row['target'], errors = _clean_new(row, trip); row['errors'] += errors
        else:
            sample = by_pk.get(int(row['sample'])) if row['sample'].isdigit() else None
            if sample is None: row['errors'].append('התצפית שנבחרה לא נמצאה במסע.'); continue
            if sample.pk in seen_samples: row['errors'].append(f'התצפית נבחרה גם לקובץ {seen_samples[sample.pk]}.')
            seen_samples.setdefault(sample.pk, row['name'])
            row['target'] = sample
    for row in selected:
        if not row['errors'] and check_video(row['video_id']) == STATUS_NOT_FOUND:
            row['errors'].append('הסרטון בקישור לא נמצא ב-YouTube.')
    return bool(selected) and not any(r['errors'] for r in selected)


def apply(rows, trip, folder, user, copy_to_drive=True):
    selected = [r for r in rows if r['checked']]
    create_backup()
    counts = {'created': 0, 'updated': 0, 'restored': 0, 'copied': 0, 'waiting': 0}
    with transaction.atomic():
        if not same_folder(trip, folder):
            DiveTrip.objects.filter(pk=trip.pk).update(local_video_folder=folder)
            trip.local_video_folder = folder
        for row in selected:
            sample = row['target']; new = not sample.pk
            if new: sample.owner = user
            restored = bool(sample.deleted_at)
            if restored: sample.deleted_at = None; sample.deleted_by = None       # a manager brings it back
            sample.trip = trip
            if row['drive']['id']: drive_id = row['drive']['id']
            elif sample.local_video_file == row['name']: drive_id = sample.drive_video_id
            else: drive_id = ''
            sample.video_url = row['url']; sample.local_video_file = row['name']; sample.drive_video_id = drive_id
            try:
                # a manager's save publishes a complete observation (a trip collection too, not only a species)
                sample.save_reviewed(actor=user, approve=sample.is_complete())
            except ValidationError as error:
                raise ValidationError([f'{row["name"]}: {m}' for m in error.messages])
            counts['created' if new else 'restored' if restored else 'updated'] += 1
    if copy_to_drive and drive_videos.available():
        for row in selected:
            drive = row['drive']; source = Path(row['path'])
            if not drive['exists'] or drive['full'].stat().st_size != source.stat().st_size:
                drive['full'].parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, drive['full']); counts['copied'] += 1
            new_id = drive_videos.drive_id(drive['full'])
            if new_id and new_id != row['target'].drive_video_id:
                Sample.objects.filter(pk=row['target'].pk).update(drive_video_id=new_id)
            elif not new_id:
                counts['waiting'] += 1
    return counts


def _row_counts(rows):
    """The selected rows are shown; the others (new, deleted, already attached) sit in a closed list below them."""
    others = [r for r in rows if not r['checked']]
    return {'selected_count': len(rows) - len(others), 'other_count': len(others),
            'other_done': sum(1 for r in others if r['done']), 'other_deleted': sum(1 for r in others if r['deleted_match']),
            'other_new': sum(1 for r in others if r['sample'] == NEW),
            'other_rest': sum(1 for r in others if not r['done'] and not r['deleted_match'] and r['sample'] != NEW),
            'others_open': len(others) == len(rows)}


@staff_member_required
def video_import(request):
    if not request.user.is_superuser: raise PermissionDenied
    data = request.POST if request.method == 'POST' else request.GET
    pk = data.get('trip', '')
    trip = DiveTrip.objects.exclude(code__in=LIBRARY_TRIP_CODES).filter(pk=pk).first() if pk.isdigit() else None
    folder = (data.get('folder') or (trip.local_video_folder if trip else '') or '').strip()
    from .views import trip_picker_context
    context = {**trip_picker_context(trip.pk if trip else None), 'trip': trip, 'folder': folder, 'production': settings.PRODUCTION,
               'drive_available': drive_videos.available()}
    if not settings.PRODUCTION:
        context['suggested_folders'] = [str(p) for p in find_video_output_folders(Path.home())]
    if trip and folder:
        try:
            validate_local_video_folder(folder)
            if not Path(folder).expanduser().is_dir(): raise ValidationError('התיקייה לא נמצאה במחשב הזה.')
        except ValidationError as error:
            context['error'] = ' '.join(error.messages)
            return render(request, 'observations/video_import.html', context)
        rows, by_pk = build_rows(trip, folder, request.POST if request.method == 'POST' else None)
        if request.method == 'POST':
            if validate(rows, by_pk, trip):
                try:
                    counts = apply(rows, trip, folder, request.user, copy_to_drive=request.POST.get('copy_to_drive') == '1')
                except ValidationError as error:
                    context['error'] = ' '.join(error.messages)
                else:
                    text = f'עודכנו {counts["updated"]} תצפיות ונוצרו {counts["created"]} חדשות.'
                    if counts['restored']: text += f' שוחזרו {counts["restored"]} תצפיות מחוקות.'
                    if counts['copied']: text += f' הועתקו {counts["copied"]} קבצים ל-Google Drive.'
                    if counts['waiting']: text += f' ל-{counts["waiting"]} קבצים עוד אין מזהה Drive (ההעלאה ל-Drive עדיין רצה) — אחרי שתסתיים, עדכן אותם בדף "סרטונים ב-Google Drive".'
                    text += ' כדי שהשינויים יגיעו לאתר החי — העבר את טבלת התצפיות (samples).'
                    messages.success(request, text)
                    return redirect(reverse('video-import') + '?' + urlencode({'trip': trip.pk, 'folder': folder}))
            elif not any(r['checked'] for r in rows):
                context['error'] = 'לא נבחרו קבצים.'
            else:
                context['error'] = 'לא נשמר דבר: יש לתקן את השורות המסומנות באדום.'
        samples = sorted(by_pk.values(), key=lambda s: (bool(s.deleted_at), (s.taxon_label or s.title or '').lower()))
        context.update({
            'listed': True, 'rows': rows, **_row_counts(rows), 'samples': [(s.pk, sample_label(s)) for s in samples],
            'info_json': json.dumps({str(s.pk): sample_info(s) for s in samples}, ensure_ascii=False),
            'species': Species.objects.order_by('scientific_name'),
            'qualifiers': list(IdentificationQualifier.objects.values_list('code', flat=True)),
            'life_stages': list(LifeStage.objects.values_list('code', flat=True)),
            'sites': Site.objects.filter(region_id=trip.region_id).order_by('name') if trip.region_id else [],
            'folder_changes': not same_folder(trip, folder), 'kinds': [(k.value, k.label) for k in KINDS],
            'assigned_elsewhere': sum(1 for s in by_pk.values() if s.local_video_file) if not same_folder(trip, folder) else 0,
        })
    response = render(request, 'observations/video_import.html', context)
    response['Cache-Control'] = 'private, no-store'
    return response
