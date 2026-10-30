"""Admin page "קבצי מאמרים וקובצי זיהוי": every article PDF (and its preview) and genus identification file
stored on the server, which row uses it, and deleting what is no longer needed -- like the image manager's
"redundant images": files no row uses (orphans left behind by replaced or cleared uploads, or drafts left in
the folder), one by one or all selected at once, and library articles that no page picks and that are not
on the home page (the article row together with its files).

A file that is in use is never deleted here -- it is removed from its own row ("לסלק" in the admin, or
the clear box on the observation form), which also deletes the file from disk."""
import mimetypes
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import redirect, render
from django.urls import NoReverseMatch, reverse
from django.views.decorators.http import require_POST

from .models import Article, TaxonGenus

# (what the file is, row type shown in the table, model, field, admin url name)
ARTICLE, IDENTIFICATION = 'מאמר', 'זיהוי'
KINDS = (
    (ARTICLE, 'מאמר (עברית)', Article, 'pdf_he', 'admin:observations_article_change'),
    (ARTICLE, 'מאמר (אנגלית)', Article, 'pdf_en', 'admin:observations_article_change'),
    (ARTICLE, 'תצוגה מקדימה (עברית)', Article, 'thumb_he', 'admin:observations_article_change'),
    (ARTICLE, 'תצוגה מקדימה (אנגלית)', Article, 'thumb_en', 'admin:observations_article_change'),
    (IDENTIFICATION, 'סוג (עברית)', TaxonGenus, 'identification_file', 'admin:observations_taxongenus_change'),
    (IDENTIFICATION, 'סוג (אנגלית)', TaxonGenus, 'identification_file_en', 'admin:observations_taxongenus_change'),
    (IDENTIFICATION, 'תצוגה מקדימה של סוג (עברית)', TaxonGenus, 'identification_thumb', 'admin:observations_taxongenus_change'),
    (IDENTIFICATION, 'תצוגה מקדימה של סוג (אנגלית)', TaxonGenus, 'identification_thumb_en', 'admin:observations_taxongenus_change'),
)
FOLDERS = ('articles', 'identification')
EXTENSIONS = {'.pdf', '.jpg', '.jpeg', '.png', '.webp', '.gif', '.html', '.htm'}
# Opened as plain text, never rendered: an HTML file left in the folder must not run on the site's origin.
TEXT_EXTENSIONS = {'.html', '.htm'}


def unused_articles():
    """Library articles that no species, order, family, genus or dive trip picks and that are not on the home page."""
    return list(Article.objects.filter(show_on_home=False, species__isnull=True, orders__isnull=True,
                                       families__isnull=True, genera__isnull=True, trips__isnull=True).distinct())


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
    context = {'local': not settings.PRODUCTION}
    if request.method == 'POST':
        from . import article_transfer
        import json
        action = request.POST.get('action')
        try:
            if action == 'export_manifest':
                body = json.dumps(article_transfer.build_manifest(), ensure_ascii=False, indent=2)
                response = HttpResponse(body, content_type='application/json; charset=utf-8')
                response['Content-Disposition'] = f'attachment; filename="seaslugs-articles-{"local" if context["local"] else "render"}.json"'
                return response
            if action == 'compare_manifest':
                upload = request.FILES.get('manifest')
                if not upload:
                    raise ValidationError('יש לבחור קובץ השוואה.')
                try:
                    manifest = json.loads(upload.read())
                except (ValueError, UnicodeDecodeError):
                    raise ValidationError('קובץ השוואת מאמרים לא תקין.')
                context['comparison'] = article_transfer.compare_manifest(manifest)
            elif action == 'upload_articles':
                done, notes = article_transfer.receive(request.FILES.getlist('files'), replace=request.POST.get('replace') == 'yes')
                messages.success(request, f'הועברו {len(done)} מאמרים: ' + ', '.join(f'{title} ({what})' for what, title in done))
                for note in notes:
                    messages.warning(request, note)
                return redirect('article-files')
        except ValidationError as exc:
            context['transfer_error'] = '; '.join(exc.messages)
    used = references()
    rows = []
    for name, size, modified in stored_files():
        rows.append({'name': name, 'what': IDENTIFICATION if name.startswith('identification/') else ARTICLE,
                     'size_mb': round(size / (1024 * 1024), 2), 'modified': modified, 'uses': used.get(name, [])})
    # A row that points at a file missing from the disk (e.g. after a database replace without media).
    on_disk = {r['name'] for r in rows}
    missing = [(name, uses) for name, uses in sorted(used.items()) if name not in on_disk]
    orphans = [r for r in rows if not r['uses']]
    response = render(request, 'observations/article_files.html', {**context,
        'library': list(Article.objects.order_by('slug')),
        'rows': rows, 'orphans': orphans, 'missing': missing, 'unused_articles': unused_articles(),
        'total_mb': round(sum(r['size_mb'] for r in rows), 1), 'orphan_mb': round(sum(r['size_mb'] for r in orphans), 1)})
    response['Cache-Control'] = 'private, no-store'
    return response


@staff_member_required
def article_file_open(request):
    _superuser(request)
    path = resolve_article(request.GET.get('name', ''))
    if path is None:
        raise Http404
    content_type = 'text/plain; charset=utf-8' if path.suffix.lower() in TEXT_EXTENSIONS else (
        mimetypes.guess_type(path.name)[0] or 'application/octet-stream')
    response = FileResponse(path.open('rb'), content_type=content_type)
    response['Content-Disposition'] = 'inline; filename="%s"' % path.name.replace('"', "'")
    response['Cache-Control'] = 'private, no-store'
    return response


@staff_member_required
@require_POST
def article_file_delete(request):
    """Deletes one file (its row's own button: "name") or every selected one ("names"); a file in use never."""
    _superuser(request)
    names = request.POST.getlist('name') or request.POST.getlist('names')
    used = references()
    deleted, refused = [], []
    for name in names:
        path = resolve_article(name)
        if path is None:
            refused.append(f'{name} (לא נמצא)')
        elif name in used:
            refused.append(f'{name} (בשימוש — להסרתו יש לסמן "לסלק" בעמוד של השורה שמשתמשת בו)')
        else:
            path.unlink()
            deleted.append(name)
    if not names:
        messages.error(request, 'לא נבחר אף קובץ.')
    if deleted:
        messages.success(request, (f'הקובץ נמחק: {deleted[0]}' if len(deleted) == 1 else f'נמחקו {len(deleted)} קבצים.'))
    for text in refused:
        messages.error(request, ('הקובץ בשימוש — להסרתו יש לסמן "לסלק" בעמוד של השורה שמשתמשת בו.' if len(names) == 1 and 'בשימוש' in text
                                 else 'הקובץ לא נמצא.' if len(names) == 1 else f'לא נמחק: {text}'))
    return redirect('article-files')


@staff_member_required
@require_POST
def unused_article_delete(request):
    """Deletes the selected library articles that no page picks (their PDFs and previews go with them)."""
    _superuser(request)
    unused = {str(a.pk): a for a in unused_articles()}
    chosen = [unused[pk] for pk in request.POST.getlist('articles') if pk in unused]
    for article in chosen:
        article.delete()
    if chosen:
        messages.success(request, f'נמחקו {len(chosen)} מאמרים: ' + ', '.join(str(a) for a in chosen))
    else:
        messages.error(request, 'לא נבחר מאמר שאינו בשימוש.')
    return redirect('article-files')


@staff_member_required
def article_transfer_file(request):
    """One file of an article for moving it to the other environment: its details (part=details,
    <slug>.article.json) or its PDF in one language (part=he / en, <slug>-he.pdf)."""
    _superuser(request)
    from . import article_transfer
    import json
    article = Article.objects.filter(slug=request.GET.get('article', '')).first()
    part = request.GET.get('part')
    if article is None or part not in ('details', 'he', 'en'):
        raise Http404
    if part == 'details':
        body = json.dumps(article_transfer.article_document(article), ensure_ascii=False, indent=2)
        response = HttpResponse(body, content_type='application/json; charset=utf-8')
        response['Content-Disposition'] = f'attachment; filename="{article.slug}.article.json"'
    else:
        field = getattr(article, 'pdf_' + part)
        if not field or not field.storage.exists(field.name):
            raise Http404
        response = FileResponse(field.open('rb'), as_attachment=True, filename=f'{article.slug}-{part}.pdf', content_type='application/pdf')
    response['Cache-Control'] = 'private, no-store'
    return response


@staff_member_required
@require_POST
def article_delete(request):
    """Deletes the selected library articles, picked by pages or not: the article row, its PDFs and previews,
    and with it every page's choice of it (the same as deleting it in the admin's "מאמרים")."""
    _superuser(request)
    chosen = list(Article.objects.filter(slug__in=request.POST.getlist('slugs')))
    if not chosen:
        messages.error(request, 'לא נבחר מאמר.')
    else:
        names = ', '.join(str(a) for a in chosen)
        for article in chosen:
            article.delete()
        messages.success(request, f'נמחקו {len(chosen)} מאמרים, עם הקבצים שלהם ובחירתם בכל העמודים: {names}')
    return redirect('article-files')
