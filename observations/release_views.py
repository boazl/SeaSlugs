import tempfile
import zipfile
from pathlib import Path
from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import PermissionDenied
from django.http import FileResponse
from django.shortcuts import render
from .table_transfer import create_backup, backups_summary, TABLES


def backup_support_database():
    """A verified copy of the separate support (financial) database next to the other backups, or None if there is
    none yet (contributions app; never part of table transfers or a database replacement)."""
    import sqlite3
    from django.utils import timezone
    from .table_transfer import backups_dir
    source = Path(settings.DATABASES['support']['NAME'])
    if not source.exists():
        return None
    root = backups_dir(); root.mkdir(parents=True, exist_ok=True)
    target = root / f'support-{timezone.now():%Y%m%d-%H%M%S}.sqlite3'
    with sqlite3.connect(str(source)) as src, sqlite3.connect(str(target)) as dst:
        src.backup(dst)
        if dst.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise RuntimeError('support database backup failed its integrity check')
    target.chmod(0o600)
    return target


@staff_member_required
def releases(request):
    if not request.user.is_superuser: raise PermissionDenied
    if request.method == 'POST' and request.POST.get('action') == 'backup':
        backup = create_backup()
        archive = tempfile.TemporaryFile()
        with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as bundle:
            bundle.write(backup, 'db.sqlite3')
            support_backup = backup_support_database()
            if support_backup:
                bundle.write(support_backup, 'support.sqlite3')
            root = Path(settings.MEDIA_ROOT)
            if root.exists():
                for file in root.rglob('*'):
                    if file.is_file() and not file.is_symlink() and file.resolve().is_relative_to(root.resolve()):
                        bundle.write(file, 'media/' + file.relative_to(root).as_posix())
            bundle.writestr('README.txt', 'SQLite backup plus uploaded media. Pause writes during backup for a coordinated DB/media snapshot. Restore only with the matching code version and all application processes stopped. Contains private user data; do not upload to GitHub.')
        archive.seek(0)
        response = FileResponse(archive, as_attachment=True, filename='seaslugs-' + backup.stem + '.zip')
        response['Cache-Control'] = 'private, no-store'
        return response
    # The table order shown here comes straight from TABLES (table_transfer.py), which is
    # itself ordered to match the real transfer dependency chain -- see the comment there.
    response = render(request, 'observations/releases.html', {'local':not settings.PRODUCTION, 'tables':[(key,str(model._meta.verbose_name_plural)) for key,(model,fields) in TABLES.items()],'backups':backups_summary()})
    response['Cache-Control'] = 'private, no-store'
    return response
