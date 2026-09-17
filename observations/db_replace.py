"""Full-database replacement: back up, lock the site, let the admin download
the live database, work on it locally, then upload the replacement (plus any
images it needs that this environment doesn't have yet) and release the site
-- entirely through the browser, no shell or Render access required.

State lives on disk, not in the database being replaced: a flag file
(observations/maintenance.py) marks the site locked, and a single pending
replacement file (db-replace-staging/pending.sqlite3) marks a database
staged for review. Both survive page reloads, so nothing is lost if the
admin navigates away mid-review.
"""
import hashlib
import io
import os
import re
import sqlite3
from pathlib import Path

from PIL import Image, UnidentifiedImageError
from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.storage import default_storage
from django.db import connections
from django.http import FileResponse
from django.shortcuts import render, redirect

from . import maintenance
from .table_transfer import create_backup

MAX_UPLOAD = 200 * 1024 * 1024


def staging_root():
    root = Path(settings.DATA_DIR) / 'db-replace-staging'
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    return root


def pending_path():
    return staging_root() / 'pending.sqlite3'


def integrity_error(path):
    try:
        conn = sqlite3.connect(f'file:{path}?mode=ro', uri=True)
        try:
            ok = conn.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        finally:
            conn.close()
    except sqlite3.Error:
        return 'הקובץ אינו נפתח כמסד נתונים תקין.'
    return None if ok else 'בדיקת התקינות של מסד הנתונים נכשלה.'


def migration_mismatch(path):
    from django.db.migrations.loader import MigrationLoader
    expected = set(MigrationLoader(None, ignore_no_migrations=True).disk_migrations.keys())
    try:
        conn = sqlite3.connect(f'file:{path}?mode=ro', uri=True)
        try:
            actual = set(conn.execute('SELECT app, name FROM django_migrations').fetchall())
        finally:
            conn.close()
    except sqlite3.Error:
        return 'לא נמצאה בקובץ טבלת django_migrations תקינה.'
    if actual != expected:
        return (f'גרסת מסד הנתונים אינה תואמת לקוד הנוכחי '
                f'(חסרות {len(expected - actual)} מיגרציות, {len(actual - expected)} עודפות). '
                'הריצו python manage.py migrate על הקובץ לפני ההעלאה.')
    return None


def needed_images(path):
    conn = sqlite3.connect(f'file:{path}?mode=ro', uri=True)
    try:
        rows = conn.execute("SELECT image FROM samples WHERE image != '' AND deleted_at IS NULL").fetchall()
    finally:
        conn.close()
    return {r[0] for r in rows}


def missing_images(needed):
    return sorted(name for name in needed if not default_storage.exists(name))


MAX_MISSING_LISTED = 200


def missing_image_details(path, missing):
    # Content-hash filenames (observations/transfer/<sha256>.jpg) mean nothing to a
    # human, so for each missing image look up which sample(s) in the uploaded file
    # point at it and show the species/trip instead -- that's what the admin actually
    # needs to go find and re-upload. Capped so a huge first-time sync doesn't render
    # an enormous page.
    if not missing:
        return []
    shown = missing[:MAX_MISSING_LISTED]
    conn = sqlite3.connect(f'file:{path}?mode=ro', uri=True)
    try:
        placeholders = ','.join('?' for _ in shown)
        query = ('SELECT s.image, sp.scientific_name, s.species_other, t.title, t.year '
                 'FROM samples s '
                 'LEFT JOIN observations_species sp ON s.species_id = sp.id '
                 'LEFT JOIN dive_trips t ON s.trip_id = t.id '
                 'WHERE s.image IN (' + placeholders + ') AND s.deleted_at IS NULL')
        rows = conn.execute(query, shown).fetchall()
    finally:
        conn.close()
    by_image = {}
    for image, scientific_name, species_other, title, year in rows:
        species = scientific_name or species_other or 'ללא מין מזוהה'
        trip = ' · '.join(x for x in (title, str(year) if year else '') if x)
        by_image.setdefault(image, []).append(f'{species} ({trip})' if trip else species)
    hash_re = re.compile(r'observations/transfer/[0-9a-f]{64}\.jpg')
    return [{'name': name, 'labels': by_image.get(name, []), 'legacy': not hash_re.fullmatch(name)}
            for name in shown]


def replace_live_database(staged_path):
    # Same-filesystem atomic rename: a request already reading the old file
    # keeps its own handle on the old inode until it finishes; the next
    # request opens a fresh connection to the new one. Kept as its own
    # function so tests can patch it, matching how create_backup() is patched
    # everywhere else in this codebase instead of exercising a real live file.
    os.replace(staged_path, settings.DATABASES['default']['NAME'])
    connections.close_all()


def cleanup_orphaned_images():
    from .models import Sample, SiteImage
    root = Path(settings.MEDIA_ROOT).resolve()
    if not root.exists():
        return 0
    referenced = set(Sample.objects.exclude(image='').values_list('image', flat=True))
    referenced |= set(SiteImage.objects.exclude(image='').values_list('image', flat=True))
    removed = 0
    for path in root.rglob('*'):
        if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(root):
            continue
        name = path.relative_to(root).as_posix()
        if name not in referenced:
            path.unlink(missing_ok=True)
            removed += 1
    return removed


@staff_member_required
def db_replace(request):
    if not request.user.is_superuser:
        raise PermissionDenied
    context = {'local': not settings.PRODUCTION, 'locked': maintenance.is_locked()}
    if request.method == 'POST':
        try:
            action = request.POST.get('action')
            if action == 'lock':
                if request.POST.get('confirm') != 'yes':
                    raise ValidationError('יש לאשר את הנעילה.')
                create_backup()
                maintenance.lock()
                messages.success(request, 'האתר ננעל לתחזוקה ונוצר גיבוי. אפשר להוריד את מסד הנתונים הנוכחי ולהתחיל לעבוד עליו.')
                return redirect('db-replace')
            if action == 'unlock':
                path = pending_path()
                path.unlink(missing_ok=True)
                maintenance.unlock()
                messages.success(request, 'הנעילה בוטלה; האתר פעיל שוב. שום דבר לא הוחלף.')
                return redirect('db-replace')
            if not maintenance.is_locked():
                raise ValidationError('יש לנעול את האתר לפני שממשיכים.')
            if action == 'preview':
                upload = request.FILES.get('database')
                if not upload:
                    raise ValidationError('יש לבחור קובץ.')
                if upload.size > MAX_UPLOAD:
                    raise ValidationError('הקובץ גדול מהמותר.')
                if upload.read(16) != b'SQLite format 3\x00':
                    raise ValidationError('הקובץ אינו קובץ SQLite.')
                upload.seek(0)
                target = pending_path()
                with open(target, 'wb') as out:
                    for chunk in upload.chunks():
                        out.write(chunk)
                target.chmod(0o600)
                error = integrity_error(target) or migration_mismatch(target)
                if error:
                    target.unlink(missing_ok=True)
                    raise ValidationError(error)
                messages.success(request, 'הקובץ עבר בדיקה ומוכן לבדיקת תמונות.')
                return redirect('db-replace')
            if action == 'upload_images':
                if not pending_path().exists():
                    raise ValidationError('אין מסד נתונים ממתין; יש להעלות אותו קודם.')
                needed = needed_images(pending_path())
                from .media_transfer import save_images
                # One upload mechanism, always tied to one specific missing image: the
                # admin picks the file next to that image's own label (species + trip), so
                # the association is explicit rather than guessed from a filename or a bulk
                # match. When the target name itself encodes a content hash, that hash is
                # also verified, so a wrong file still can't be accepted for it by mistake.
                target = request.POST.get('target')
                if not target or target not in needed:
                    raise ValidationError('התמונה הזו כבר אינה נדרשת; רעננו את הדף.')
                upload = request.FILES.get('image')
                if not upload:
                    raise ValidationError('יש לבחור קובץ.')
                raw = upload.read()
                try:
                    with Image.open(io.BytesIO(raw)) as image:
                        if image.format != 'JPEG':
                            raise ValidationError('הקובץ אינו JPEG.')
                        image.verify()
                except (UnidentifiedImageError, OSError):
                    raise ValidationError('הקובץ אינו תמונה תקינה.')
                hash_match = re.fullmatch(r'observations/transfer/([0-9a-f]{64})\.jpg', target)
                if hash_match and hashlib.sha256(raw).hexdigest() != hash_match.group(1):
                    raise ValidationError('תוכן הקובץ אינו תואם לתמונה הנדרשת — ודאו שזה הקובץ הנכון.')
                save_images({target: raw})
                messages.success(request, 'התמונה הועלתה.')
                return redirect('db-replace')
            if action == 'commit':
                path = pending_path()
                if not path.exists():
                    raise ValidationError('אין מסד נתונים ממתין.')
                if request.POST.get('confirm') != 'yes':
                    raise ValidationError('יש לאשר את ההחלפה.')
                needed = needed_images(path)
                missing = missing_images(needed)
                if missing:
                    raise ValidationError(f'עדיין חסרות {len(missing)} תמונות ביעד. יש להעלות אותן לפני ההחלפה.')
                error = integrity_error(path) or migration_mismatch(path)
                if error:
                    raise ValidationError(error)
                create_backup()
                replace_live_database(path)
                removed = cleanup_orphaned_images() if request.POST.get('cleanup') == 'yes' else 0
                maintenance.unlock()
                messages.success(request, f'ההחלפה בוצעה והאתר שוחרר. נמחקו {removed} תמונות שאינן בשימוש עוד.' if request.POST.get('cleanup') == 'yes'
                                  else 'ההחלפה בוצעה והאתר שוחרר.')
                return redirect('db-replace')
        except ValidationError as exc:
            context['error'] = '; '.join(exc.messages)
    context['locked'] = maintenance.is_locked()
    if context['locked'] and pending_path().exists():
        needed = needed_images(pending_path())
        missing = missing_images(needed)
        context['pending'] = True
        context['needed_count'] = len(needed)
        context['missing_count'] = len(missing)
        context['missing_list'] = missing_image_details(pending_path(), missing)
        context['missing_list_truncated'] = len(missing) > MAX_MISSING_LISTED
    response = render(request, 'observations/db_replace.html', context)
    response['Cache-Control'] = 'no-store'
    return response


@staff_member_required
def db_replace_download(request):
    if not request.user.is_superuser:
        raise PermissionDenied
    if not maintenance.is_locked():
        raise PermissionDenied
    backup = create_backup()
    response = FileResponse(open(backup, 'rb'), as_attachment=True, filename='seaslugs-db.sqlite3')
    response['Cache-Control'] = 'private, no-store'
    return response
