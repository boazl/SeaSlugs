"""Moving library articles between the two environments (the Mac and the site), the same way images move
(see image_manager.py): each side exports a small JSON list of its articles -- details, a fingerprint of
each PDF, and the pages that pick the article -- and the other side compares it with its own, showing
which articles are missing on either side and which differ. The articles that need to go are then
selected and downloaded as ordinary files (each article's details as <slug>.article.json, plus its PDFs
as <slug>-he.pdf / <slug>-en.pdf) and uploaded on the other side, which creates or updates them.

Articles are matched by their slug; the pages that pick an article by natural keys (a species by its
scientific name, a genus by name, a family by name + sub-family, an order row by name + sub-order +
superfamily, a dive trip by its code), never by database ids, which differ between the environments."""
import hashlib
import json
from datetime import date, datetime, timezone as dt_timezone

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from .models import Article, DiveTrip, Species, TaxonFamily, TaxonGenus, TaxonOrder

MANIFEST_FORMAT = 'seaslugs-article-manifest-v1'
ARTICLE_FORMAT = 'seaslugs-article-v1'
LANGS = ('he', 'en')
DETAIL_FIELDS = ('title_he', 'title_en', 'source', 'link', 'published_on', 'show_on_home')
DETAIL_LABELS = {'title_he': 'כותרת (עברית)', 'title_en': 'כותרת (אנגלית)', 'source': 'מקור', 'link': 'קישור חיצוני',
                 'published_on': 'תאריך פרסום', 'show_on_home': 'הצגה בדף הבית'}
PAGE_LABELS = {'species': 'מינים', 'genera': 'סוגים', 'families': 'משפחות', 'orders': 'סדרות', 'trips': 'מסעות צלילה'}
MAX_UPLOAD_FILES = 60
MAX_UPLOAD_BYTES = 150 * 1024 * 1024
MAX_PDF_BYTES = 20 * 1024 * 1024

_hash_cache = {}


def _file_details(field):
    """[sha256, modification time, size] of a stored PDF, or None when there is none (or it is missing on disk)."""
    if not field:
        return None
    try:
        path = field.path
        import os
        stat = os.stat(path)
    except (OSError, NotImplementedError, ValueError):
        return None
    key = (path, stat.st_size, stat.st_mtime_ns)
    if key not in _hash_cache:
        with open(path, 'rb') as handle:
            _hash_cache[key] = hashlib.sha256(handle.read()).hexdigest()
    return [_hash_cache[key], int(stat.st_mtime), stat.st_size]


def _pages(article):
    """The pages that pick the article, by natural keys, sorted (so equal sets compare equal)."""
    return {
        'species': sorted(s.scientific_name for s in article.species.all()),
        'genera': sorted(g.name for g in article.genera.all()),
        'families': sorted([f.name, f.sub_family] for f in article.families.all()),
        'orders': sorted([o.name, o.sub_order, o.superfamily] for o in article.orders.all()),
        'trips': sorted(t.code for t in article.trips.all() if t.code),
    }


def article_entry(article):
    return {
        'slug': article.slug, 'title_he': article.title_he, 'title_en': article.title_en, 'source': article.source,
        'link': article.link, 'published_on': article.published_on.isoformat() if article.published_on else '',
        'show_on_home': article.show_on_home,
        'files': {lang: _file_details(getattr(article, 'pdf_' + lang)) for lang in LANGS},
        'pages': _pages(article),
    }


def _articles():
    return Article.objects.prefetch_related('species', 'genera', 'families', 'orders', 'trips').order_by('slug')


def build_manifest():
    return {'format': MANIFEST_FORMAT, 'exported_at': timezone.now().isoformat(),
            'articles': [article_entry(a) for a in _articles()]}


def article_document(article):
    """The details file downloaded with an article's PDFs (<slug>.article.json)."""
    return {'format': ARTICLE_FORMAT, 'exported_at': timezone.now().isoformat(), 'article': article_entry(article)}


def _valid_entry(entry):
    if not isinstance(entry, dict) or not isinstance(entry.get('slug'), str) or not entry['slug']:
        return False
    if not all(isinstance(entry.get(f), str) for f in ('title_he', 'title_en', 'source', 'link', 'published_on')):
        return False
    if not isinstance(entry.get('show_on_home'), bool) or not isinstance(entry.get('files'), dict) or not isinstance(entry.get('pages'), dict):
        return False
    for lang in LANGS:
        value = entry['files'].get(lang)
        if value is not None and not (isinstance(value, list) and len(value) == 3 and isinstance(value[0], str)
                                      and all(isinstance(x, int) for x in value[1:])):
            return False
    pages = entry['pages']
    if set(pages) != set(PAGE_LABELS):
        return False
    if not all(isinstance(x, str) for key in ('species', 'genera', 'trips') for x in pages[key]):
        return False
    if not all(isinstance(x, list) and len(x) == 2 and all(isinstance(y, str) for y in x) for x in pages['families']):
        return False
    if not all(isinstance(x, list) and len(x) == 3 and all(isinstance(y, str) for y in x) for x in pages['orders']):
        return False
    return True


def _page_text(key, value):
    if key == 'families':
        return ' — '.join(x for x in value if x)
    if key == 'orders':
        return ' — '.join(x for x in value if x)
    return value


def _when(seconds):
    return datetime.fromtimestamp(seconds, tz=dt_timezone.utc)


def compare_manifest(manifest):
    """This environment's articles against the other environment's list: missing here, only here, and for
    the articles in both, the details, PDFs and picked pages that differ."""
    if not isinstance(manifest, dict) or manifest.get('format') != MANIFEST_FORMAT or not isinstance(manifest.get('articles'), list):
        raise ValidationError('קובץ השוואת מאמרים לא תקין או גרסה לא נתמכת.')
    if not all(_valid_entry(e) for e in manifest['articles']):
        raise ValidationError('קובץ השוואת מאמרים לא תקין.')
    remote = {e['slug']: e for e in manifest['articles']}
    local = {a.slug: (a, article_entry(a)) for a in _articles()}
    result = {'missing_here': [], 'only_here': [], 'different': []}
    for slug, entry in sorted(remote.items()):
        if slug not in local:
            result['missing_here'].append({'slug': slug, 'title': entry['title_he'] or entry['title_en'] or slug})
    for slug, (article, here) in local.items():
        there = remote.get(slug)
        if there is None:
            result['only_here'].append({'slug': slug, 'title': str(article)})
            continue
        details = [DETAIL_LABELS[f] for f in DETAIL_FIELDS if here[f] != there[f]]
        pdfs = []
        for lang in LANGS:
            mine, theirs = here['files'][lang], there['files'][lang]
            label = 'PDF בעברית' if lang == 'he' else 'PDF באנגלית'
            if mine is None and theirs is None:
                continue
            if mine is None:
                pdfs.append({'label': label, 'state': 'חסר כאן'})
            elif theirs is None:
                pdfs.append({'label': label, 'state': 'חסר בסביבה השנייה'})
            elif mine[0] != theirs[0]:
                newer = 'כאן' if mine[1] > theirs[1] else 'בסביבה השנייה' if mine[1] < theirs[1] else ''
                pdfs.append({'label': label, 'state': 'תוכן שונה', 'newer': newer,
                             'size_here': mine[2], 'size_there': theirs[2], 'mtime_here': _when(mine[1]), 'mtime_there': _when(theirs[1])})
        pages = []
        for key, label in PAGE_LABELS.items():
            mine = {json.dumps(x, ensure_ascii=False): x for x in here['pages'][key]}
            theirs = {json.dumps(x, ensure_ascii=False): x for x in there['pages'][key]}
            only_mine = [_page_text(key, mine[k]) for k in sorted(set(mine) - set(theirs))]
            only_theirs = [_page_text(key, theirs[k]) for k in sorted(set(theirs) - set(mine))]
            if only_mine or only_theirs:
                pages.append({'label': label, 'only_here': only_mine, 'only_there': only_theirs})
        if details or pdfs or pages:
            result['different'].append({'slug': slug, 'title': str(article), 'details': details, 'pdfs': pdfs, 'pages': pages})
    result['only_here_slugs'] = [r['slug'] for r in result['only_here']]
    result['different_slugs'] = [r['slug'] for r in result['different']]
    return result


def _resolve_pages(pages):
    """The rows here for the natural keys of an article's pages, and the keys that have no row here."""
    found = {key: [] for key in PAGE_LABELS}
    missing = []

    def one(model, label, **lookup):
        rows = list(model.objects.filter(**lookup)[:2])
        if len(rows) == 1:
            return rows[0]
        missing.append(f'{label}: {" — ".join(v for v in lookup.values() if v)}' + (' (כמה התאמות)' if rows else ''))
        return None
    for name in pages['species']:
        found['species'].append(one(Species, 'מין', scientific_name=name))
    for name in pages['genera']:
        found['genera'].append(one(TaxonGenus, 'סוג', name=name))
    for name, sub in pages['families']:
        found['families'].append(one(TaxonFamily, 'משפחה', name=name, sub_family=sub))
    for name, sub_order, superfamily in pages['orders']:
        found['orders'].append(one(TaxonOrder, 'סדרה', name=name, sub_order=sub_order, superfamily=superfamily))
    for code in pages['trips']:
        found['trips'].append(one(DiveTrip, 'מסע', code=code))
    return {key: [r for r in rows if r is not None] for key, rows in found.items()}, missing


def receive(uploads, replace=False):
    """Creates or updates the articles whose details files (<slug>.article.json) are among `uploads`, with the
    PDFs uploaded alongside (<slug>-he.pdf / <slug>-en.pdf). A PDF already present here is replaced only with
    `replace`; the picked pages are set to those listed that exist here. Returns (done, notes)."""
    if not uploads or len(uploads) > MAX_UPLOAD_FILES:
        raise ValidationError(f'בחרו בין קובץ אחד ל־{MAX_UPLOAD_FILES} קבצים.')
    if sum(u.size for u in uploads) > MAX_UPLOAD_BYTES:
        raise ValidationError(f'עד {MAX_UPLOAD_BYTES // (1024 * 1024)}MB בהעלאה אחת.')
    entries, pdfs = {}, {}
    for upload in uploads:
        name = upload.name.rsplit('/', 1)[-1]
        if name.endswith('.article.json'):
            try:
                document = json.loads(upload.read().decode('utf-8'))
            except (ValueError, UnicodeDecodeError):
                raise ValidationError(f'{name}: קובץ פרטי מאמר לא תקין.')
            entry = document.get('article') if isinstance(document, dict) and document.get('format') == ARTICLE_FORMAT else None
            if not _valid_entry(entry):
                raise ValidationError(f'{name}: קובץ פרטי מאמר לא תקין או גרסה לא נתמכת.')
            entries[entry['slug']] = entry
        elif name.lower().endswith('.pdf') and name[:-4].rsplit('-', 1)[-1] in LANGS:
            if upload.size > MAX_PDF_BYTES:
                raise ValidationError(f'{name}: הקובץ גדול מדי (עד 20MB).')
            data = upload.read()
            if not data.startswith(b'%PDF'):
                raise ValidationError(f'{name}: אינו קובץ PDF.')
            slug, lang = name[:-4].rsplit('-', 1)
            pdfs[(slug, lang)] = data
        else:
            raise ValidationError(f'{name}: יש להעלות רק קבצים שהורדו מכאן (<כתובת>.article.json ו־<כתובת>-he.pdf / -en.pdf).')
    orphan_pdfs = sorted(f'{slug}-{lang}.pdf' for slug, lang in pdfs if slug not in entries)
    if orphan_pdfs:
        raise ValidationError('לקבצים האלה חסר קובץ פרטי המאמר (.article.json) באותה העלאה: ' + ', '.join(orphan_pdfs))
    if not entries:
        raise ValidationError('לא נבחר קובץ פרטי מאמר (.article.json).')
    from .table_transfer import create_backup
    create_backup()
    done, notes = [], []
    with transaction.atomic():
        for slug, entry in sorted(entries.items()):
            article = Article.objects.filter(slug=slug).first()
            created = article is None
            article = article or Article(slug=slug)
            for field in ('title_he', 'title_en', 'source', 'link', 'show_on_home'):
                setattr(article, field, entry[field])
            if entry['published_on']:
                try:
                    article.published_on = date.fromisoformat(entry['published_on'])
                except ValueError:
                    raise ValidationError(f'{slug}: תאריך פרסום לא תקין.')
            for lang in LANGS:
                data = pdfs.get((slug, lang))
                field = getattr(article, 'pdf_' + lang)
                if data is None:
                    if entry['files'][lang] and not field:
                        notes.append(f'{slug}: ה־PDF {"בעברית" if lang == "he" else "באנגלית"} לא הועלה ואין כאן קובץ כזה.')
                    continue
                if field and not replace:
                    if _file_details(field) and _file_details(field)[0] == hashlib.sha256(data).hexdigest():
                        continue            # the very same file is already here
                    notes.append(f'{slug}: כבר יש כאן PDF {"בעברית" if lang == "he" else "באנגלית"} — לא הוחלף. '
                                 'להחלפה יש לסמן "לאשר החלפת קובצי PDF קיימים" ולהעלות שוב.')
                    continue
                field.save(f'{slug}-{lang}.pdf', ContentFile(data), save=False)
            try:
                article.full_clean()
            except ValidationError as exc:
                raise ValidationError(f'{slug}: ' + '; '.join(exc.messages))
            article.save()
            rows, missing = _resolve_pages(entry['pages'])
            for key, values in rows.items():
                getattr(article, key).set(values)
            if missing:
                notes.append(f'{slug}: עמודים שלא נמצאו כאן ולכן לא קושרו — ' + ', '.join(missing))
            done.append(('נוסף' if created else 'עודכן', str(article)))
    return done, notes
