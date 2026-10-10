"""Admin page "קבצי מאמרים וקובצי זיהוי": every article PDF and genus identification file stored on the
server, which row uses it, and a delete button for the files no row uses any more (orphans left behind
by replaced or cleared uploads).

A file that is in use is never deleted here -- it is removed from its own row ("לסלק" in the admin, or
the clear box on the observation form), which also deletes the file from disk."""
import mimetypes
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404
from django.shortcuts import redirect, render
from django.urls import NoReverseMatch, reverse
from django.views.decorators.http import require_POST

from .models import DiveTrip, Species, TaxonFamily, TaxonGenus, TaxonOrder

# (what the file is, row type shown in the table, model, field, admin url name)
ARTICLE, IDENTIFICATION = 'מאמר', 'זיהוי'
KINDS = (
    (ARTICLE, 'מין', Species, 'article_pdf', 'admin:observations_species_change'),
    (ARTICLE, 'סדרה', TaxonOrder, 'article_pdf', 'admin:observations_taxonorder_change'),
    (ARTICLE, 'משפחה', TaxonFamily, 'article_pdf', 'admin:observations_taxonfamily_change'),
    (ARTICLE, 'סוג', TaxonGenus, 'article_pdf', 'admin:observations_taxongenus_change'),
    (ARTICLE, 'מסע צלילה', DiveTrip, 'article_pdf', 'admin:observations_divetrip_change'),
    (IDENTIFICATION, 'סוג', TaxonGenus, 'identification_file', 'admin:observations_taxongenus_change'),
)
FOLDERS = ('articles', 'identification')
EXTENSIONS = {'.pdf', '.jpg', '.jpeg', '.png', '.webp', '.gif'}


def references():
    """{stored file name: [(row type, row text, admin edit url), ...]} for every row with a file."""
    found = {}
    for _what, label, model, field, url_name in KINDS:
        for row in model.objects.exclude(**{field: ''}).exclude(**{field + '__isnull': True}):
            try:
                url = reverse(url_name, args=[row.pk])
            except NoReverseMatch:
                url = ''
            found.setdefault(getattr(row, field).name, []).append((label, str(row), url))
    return found


def stored_files():
    """Every regular article / identification file under MEDIA_ROOT, as (name relative to MEDIA_ROOT, size, modified)."""
    media = Path(settings.MEDIA_ROOT).resolve()
    files = []
    for folder in FOLDERS:
        root = Path(settings.MEDIA_ROOT) / folder
        if not root.is_dir():
            continue
        for path in sorted(root.rglob('*')):
            if path.is_symlink() or not path.is_file() or path.suffix.lower() not in EXTENSIONS:
                continue
            if not path.resolve().is_relative_to(media):
                continue
            stat = path.stat()
            files.append((path.relative_to(media).as_posix(), stat.st_size, datetime.fromtimestamp(stat.st_mtime)))
    return files


def resolve_article(name):
    """The real path of an article / identification file named by the browser, or None when the name is not exactly one of them."""
    if not name or name.split('/', 1)[0] not in FOLDERS:
        return None
    path = Path(settings.MEDIA_ROOT) / name
    roots = [(Path(settings.MEDIA_ROOT) / folder).resolve() for folder in FOLDERS]
    try:
        resolved = path.resolve()
    except OSError:
        return None
    if path.is_symlink() or not any(resolved.is_relative_to(root) for root in roots) \
            or resolved.suffix.lower() not in EXTENSIONS or not resolved.is_file():
        return None
    return resolved


def _superuser(request):
    if not request.user.is_superuser:
        raise PermissionDenied


@staff_member_required
def article_files(request):
    _superuser(request)
    used = references()
    rows = []
    for name, size, modified in stored_files():
        rows.append({'name': name, 'what': IDENTIFICATION if name.startswith('identification/') else ARTICLE,
                     'size_mb': round(size / (1024 * 1024), 2), 'modified': modified, 'uses': used.get(name, [])})
    # A row that points at a file missing from the disk (e.g. after a database replace without media).
    on_disk = {r['name'] for r in rows}
    missing = [(name, uses) for name, uses in sorted(used.items()) if name not in on_disk]
    orphans = [r for r in rows if not r['uses']]
    response = render(request, 'observations/article_files.html', {
        'rows': rows, 'orphans': orphans, 'missing': missing,
        'total_mb': round(sum(r['size_mb'] for r in rows), 1), 'orphan_mb': round(sum(r['size_mb'] for r in orphans), 1)})
    response['Cache-Control'] = 'private, no-store'
    return response


@staff_member_required
def article_file_open(request):
    _superuser(request)
    path = resolve_article(request.GET.get('name', ''))
    if path is None:
        raise Http404
    response = FileResponse(path.open('rb'), content_type=mimetypes.guess_type(path.name)[0] or 'application/octet-stream')
    response['Content-Disposition'] = 'inline; filename="%s"' % path.name.replace('"', "'")
    response['Cache-Control'] = 'private, no-store'
    return response


@staff_member_required
@require_POST
def article_file_delete(request):
    _superuser(request)
    name = request.POST.get('name', '')
    path = resolve_article(name)
    if path is None:
        messages.error(request, 'הקובץ לא נמצא.')
    elif name in references():
        messages.error(request, 'הקובץ בשימוש — להסרתו יש לסמן "לסלק" בעמוד של השורה שמשתמשת בו.')
    else:
        path.unlink()
        messages.success(request, f'הקובץ נמחק: {name}')
    return redirect('article-files')
