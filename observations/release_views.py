import tempfile
import zipfile
from pathlib import Path
from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import PermissionDenied
from django.http import FileResponse
from django.shortcuts import render
from .table_transfer import create_backup, TABLES


@staff_member_required
def releases(request):
    if not request.user.is_superuser: raise PermissionDenied
    if request.method == 'POST' and request.POST.get('action') == 'backup':
        backup = create_backup()
        archive = tempfile.TemporaryFile()
        with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as bundle:
            bundle.write(backup, 'db.sqlite3')
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
    response = render(request, 'observations/releases.html', {'local':not settings.PRODUCTION, 'tables':[(key,str(model._meta.verbose_name_plural)) for key in ('species','countries','seas','regions','sites','groups','users','profiles','trips','samples') for model,fields in [TABLES[key]]]})
    response['Cache-Control'] = 'private, no-store'
    return response
