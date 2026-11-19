"""Moving genus identification files (TaxonGenus.identification_file / identification_file_en: a diagram, plate or key,
PDF or image) between the two environments, on the page "קבצי מאמרים וקובצי זיהוי" (/admin/article-files/), the same
way articles move (article_transfer.py):

- each side exports a small JSON list (no file contents): for every genus that has an identification file, a
  fingerprint of each language's file and the preview page chosen for it;
- the other side compares it with its own: genera whose file is missing here, files only here, and files or preview
  pages that differ (with which side is newer);
- the genera to move are ticked and downloaded as ordinary files -- <genus>.identification.json (the details) and the
  files themselves, <genus>-identification-he.<ext> / -en.<ext> -- and uploaded on the other side, which stores each
  file under the name it has at the source and sets its preview page (the preview picture is made again there).

A genus is matched by its name and must already exist at the destination (genera are created with the taxonomy, not
here). A file that already exists at the destination with other content is replaced only when that is confirmed; the
same file is never stored twice. Nothing is deleted at the destination: a file removed on one side is removed on the
other by hand. The caption and source of the file are page texts and travel with the table transfer (table `genera`).
"""
import hashlib
import io
import json
import os
import re
from datetime import datetime, timezone as dt_timezone
from pathlib import PurePosixPath

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import IDENTIFICATION_FILE_EXTENSIONS, IDENTIFICATION_FILE_MAX_BYTES, IDENTIFICATION_IMAGE_EXTENSIONS, TaxonGenus

MANIFEST_FORMAT = 'seaslugs-identification-manifest-v1'
DETAILS_FORMAT = 'seaslugs-identification-v1'
LANGS = ('he', 'en')
LANG_LABELS = {'he': 'קובץ בעברית', 'en': 'קובץ באנגלית'}
MAX_UPLOAD_FILES = 60
MAX_UPLOAD_BYTES = 150 * 1024 * 1024
FILE_NAME = re.compile(r'^(?P<genus>.+)-identification-(?P<lang>he|en)\.(?P<ext>[A-Za-z]+)$')
_hash_cache = {}


def _details(field):
    """[sha256, modification time, size, stored file name (no folder)] of a stored file, None when there is none
    (or it is missing on disk)."""
    if not field:
        return None
    try:
        path = field.path
        stat = os.stat(path)
    except (OSError, NotImplementedError, ValueError):
        return None
    key = (path, stat.st_size, stat.st_mtime_ns)
    if key not in _hash_cache:
        with open(path, 'rb') as handle:
            _hash_cache[key] = hashlib.sha256(handle.read()).hexdigest()
    return [_hash_cache[key], int(stat.st_mtime), stat.st_size, PurePosixPath(field.name).name]


def genus_entry(genus):
    return {'genus': genus.name,
            'files': {lang: _details(genus.identification_file_in(lang)) for lang in LANGS},
            'pages': {lang: genus.identification_page_in(lang) for lang in LANGS}}


def genera_with_files():
    return TaxonGenus.objects.filter(~Q(identification_file='') | ~Q(identification_file_en='')).order_by('name')


def build_manifest():
    return {'format': MANIFEST_FORMAT, 'exported_at': timezone.now().isoformat(),
            'genera': [genus_entry(g) for g in genera_with_files()]}


def details_document(genus):
    """The details file downloaded with a genus's identification files (<genus>.identification.json)."""
    return {'format': DETAILS_FORMAT, 'exported_at': timezone.now().isoformat(), 'genus': genus_entry(genus)}


def file_download_name(genus, lang):
    """The name a file is downloaded under: <genus>-identification-<lang>.<its extension>."""
    stored = genus.identification_file_in(lang).name
    return f'{genus.name}-identification-{lang}.{stored.rsplit(".", 1)[-1].lower()}'


def _valid_entry(entry):
    if not isinstance(entry, dict) or not isinstance(entry.get('genus'), str) or not entry['genus']:
        return False
    files, pages = entry.get('files'), entry.get('pages')
    if not isinstance(files, dict) or not isinstance(pages, dict) or set(files) != set(LANGS) or set(pages) != set(LANGS):
        return False
    for lang in LANGS:
        value = files[lang]
        if value is not None and not (isinstance(value, list) and len(value) == 4 and isinstance(value[0], str)
                                      and isinstance(value[1], int) and isinstance(value[2], int) and isinstance(value[3], str)):
            return False
        if not isinstance(pages[lang], int) or isinstance(pages[lang], bool) or pages[lang] < 1:
            return False
    return True


def _when(seconds):
    return datetime.fromtimestamp(seconds, tz=dt_timezone.utc)


def compare_manifest(manifest):
    """This environment's identification files against the other environment's list."""
    if not isinstance(manifest, dict) or manifest.get('format') != MANIFEST_FORMAT or not isinstance(manifest.get('genera'), list):
        raise ValidationError('קובץ השוואת קובצי זיהוי לא תקין או גרסה לא נתמכת.')
    if not all(_valid_entry(e) for e in manifest['genera']):
        raise ValidationError('קובץ השוואת קובצי זיהוי לא תקין.')
    remote = {e['genus']: e for e in manifest['genera']}
    local = {g.name: genus_entry(g) for g in genera_with_files()}
    known = set(TaxonGenus.objects.filter(name__in=list(remote)).values_list('name', flat=True))
    result = {'missing_here': [], 'only_here': [], 'different': []}
    for name, there in sorted(remote.items()):
        if name not in local:
            result['missing_here'].append({'genus': name, 'no_genus': name not in known,
                                           'langs': [LANG_LABELS[l] for l in LANGS if there['files'][l]]})
    for name, here in sorted(local.items()):
        there = remote.get(name)
        if there is None:
            result['only_here'].append({'genus': name, 'langs': [LANG_LABELS[l] for l in LANGS if here['files'][l]]})
            continue
        items = []
        for lang in LANGS:
            mine, theirs = here['files'][lang], there['files'][lang]
            if mine is None and theirs is None:
                continue
            if mine is None:
                items.append({'label': LANG_LABELS[lang], 'state': 'חסר כאן'})
            elif theirs is None:
                items.append({'label': LANG_LABELS[lang], 'state': 'חסר בסביבה השנייה'})
            elif mine[0] != theirs[0]:
                newer = 'כאן' if mine[1] > theirs[1] else 'בסביבה השנייה' if mine[1] < theirs[1] else ''
                items.append({'label': LANG_LABELS[lang], 'state': 'תוכן שונה', 'newer': newer,
                              'size_here': mine[2], 'size_there': theirs[2], 'mtime_here': _when(mine[1]), 'mtime_there': _when(theirs[1])})
            elif here['pages'][lang] != there['pages'][lang]:
                items.append({'label': LANG_LABELS[lang], 'state': f'עמוד תצוגה מקדימה שונה ({here["pages"][lang]} כאן, {there["pages"][lang]} שם)'})
        if items:
            result['different'].append({'genus': name, 'items': items})
    result['send'] = [r['genus'] for r in result['only_here']] + [r['genus'] for r in result['different']]
    return result


def _check_content(name, ext, data):
    if ext == 'pdf':
        if not data.startswith(b'%PDF'):
            raise ValidationError(f'{name}: אינו קובץ PDF.')
        return
    from PIL import Image
    try:
        Image.open(io.BytesIO(data)).verify()
    except Exception:
        raise ValidationError(f'{name}: אינו קובץ תמונה תקין.')


def receive(uploads, replace=False):
    """Stores the identification files of the genera whose details files (<genus>.identification.json) are among
    `uploads`, with the files uploaded alongside (<genus>-identification-he.<ext> / -en.<ext>). Returns (done, notes)."""
    if not uploads or len(uploads) > MAX_UPLOAD_FILES:
        raise ValidationError(f'בחרו בין קובץ אחד ל־{MAX_UPLOAD_FILES} קבצים.')
    if sum(u.size for u in uploads) > MAX_UPLOAD_BYTES:
        raise ValidationError(f'עד {MAX_UPLOAD_BYTES // (1024 * 1024)}MB בהעלאה אחת.')
    entries, files = {}, {}
    for upload in uploads:
        name = upload.name.rsplit('/', 1)[-1]
        if name.endswith('.identification.json'):
            try:
                document = json.loads(upload.read().decode('utf-8'))
            except (ValueError, UnicodeDecodeError):
                raise ValidationError(f'{name}: קובץ פרטי זיהוי לא תקין.')
            entry = document.get('genus') if isinstance(document, dict) and document.get('format') == DETAILS_FORMAT else None
            if not _valid_entry(entry):
                raise ValidationError(f'{name}: קובץ פרטי זיהוי לא תקין או גרסה לא נתמכת.')
            entries[entry['genus']] = entry
            continue
        match = FILE_NAME.match(name)
        ext = match.group('ext').lower() if match else ''
        if not match or ext not in IDENTIFICATION_FILE_EXTENSIONS:
            raise ValidationError(f'{name}: יש להעלות רק קבצים שהורדו מכאן (<סוג>.identification.json ו־<סוג>-identification-he / -en).')
        if upload.size > IDENTIFICATION_FILE_MAX_BYTES:
            raise ValidationError(f'{name}: הקובץ גדול מדי (עד 20MB).')
        data = upload.read()
        _check_content(name, ext, data)
        files[(match.group('genus'), match.group('lang'))] = data
    orphans = sorted(f'{g}-identification-{l}' for g, l in files if g not in entries)
    if orphans:
        raise ValidationError('לקבצים האלה חסר קובץ הפרטים (.identification.json) באותה העלאה: ' + ', '.join(orphans))
    if not entries:
        raise ValidationError('לא נבחר קובץ פרטי זיהוי (.identification.json).')
    from .table_transfer import create_backup
    create_backup()
    done, notes = [], []
    with transaction.atomic():
        for name, entry in sorted(entries.items()):
            genus = TaxonGenus.objects.filter(name=name).first()
            if genus is None:
                notes.append(f'{name}: הסוג אינו קיים כאן — לא הועבר. יש להוסיף אותו לטקסונומיה ולהעלות שוב.')
                continue
            changed = []
            for lang in LANGS:
                suffix = TaxonGenus.IDENTIFICATION_SUFFIX[lang]
                source = entry['files'][lang]
                field = genus.identification_file_in(lang)
                data = files.get((name, lang))
                if data is None:
                    if source and not field:
                        notes.append(f'{name}: ה{LANG_LABELS[lang]} לא הועלה ואין כאן קובץ כזה.')
                    elif source and field and (_details(field) or [''])[0] == source[0] and genus.identification_page_in(lang) != entry['pages'][lang]:
                        setattr(genus, 'identification_page' + suffix, entry['pages'][lang]); changed.append(f'עמוד {lang}')
                    continue
                same = field and (_details(field) or [''])[0] == hashlib.sha256(data).hexdigest()
                if field and not same and not replace:
                    notes.append(f'{name}: כבר יש כאן {LANG_LABELS[lang]} אחר — לא הוחלף. להחלפה יש לסמן "לאשר החלפת קובצי זיהוי קיימים" ולהעלות שוב.')
                    continue
                if not same:
                    stored = (source[3] if source else '') or f'{name}-identification-{lang}.pdf'
                    field.save(PurePosixPath(stored).name, ContentFile(data), save=False)
                    changed.append(LANG_LABELS[lang])
                if genus.identification_page_in(lang) != entry['pages'][lang]:
                    setattr(genus, 'identification_page' + suffix, entry['pages'][lang]); changed.append(f'עמוד {lang}')
            if changed:
                genus.save()
                done.append((name, ', '.join(changed)))
            else:
                done.append((name, 'ללא שינוי'))
    return done, notes
