"""Offline (local) copies of the YouTube videos, kept on the owner's Mac.

The site embeds videos from YouTube only. On dive trips the owner often works without internet, so the
admin side needs the Mac's own copy of every uploaded video:

- ``DiveTrip.local_video_folder``: the absolute folder on the Mac where that trip's exported videos (the
  files that were uploaded to YouTube) are kept, e.g. ``/Users/boazliebes/Movies/Anilao 2025/YouTube``.
- ``Sample.local_video_file``: the file name (name only, no folder) of the observation's video inside
  its trip's folder.

The full path is ``trip folder / file name``. Both fields travel through table transfer so that the two
environments hold the same values, but only the Mac can actually reach the files: on the live site the
folder simply does not exist, and the status falls back to "are the fields filled".
"""
from pathlib import Path, PurePosixPath
from django.core.exceptions import ValidationError

VIDEO_EXTENSIONS = ('.mp4', '.mov', '.m4v')

# Status of an observation's local copy (see local_video_status).
STATUS_NONE = 'none'          # the observation has no YouTube video at all -- nothing to mirror
STATUS_MISSING = 'missing'    # it has a YouTube video but no local copy is recorded (folder or file name empty)
STATUS_NOT_FOUND = 'not_found'  # recorded, the folder is reachable here, but the file is not in it
STATUS_OK = 'ok'              # recorded and the file exists here
STATUS_UNREACHABLE = 'unreachable'  # recorded, but the folder is not reachable on this machine (live site, unplugged drive)


def validate_local_video_folder(value):
    """Blank, or an absolute path on the Mac (starting with "/"; "~/" is expanded on use)."""
    value = (value or '').strip()
    if not value: return
    if not (value.startswith('/') or value.startswith('~/')):
        raise ValidationError('יש להזין נתיב מלא לתיקייה במק, שמתחיל ב-"/" (למשל /Users/boazliebes/Movies/…).')
    if '\x00' in value or any(part == '..' for part in PurePosixPath(value).parts):
        raise ValidationError('נתיב התיקייה אינו תקין.')


def validate_local_video_file(value):
    """Blank, or a bare video file name (no folder part) with a known video extension."""
    value = (value or '').strip()
    if not value: return
    if '/' in value or '\\' in value or '\x00' in value or value in ('.', '..'):
        raise ValidationError('יש להזין את שם הקובץ בלבד, בלי תיקייה (התיקייה נקבעת במסע הצלילה).')
    if not value.lower().endswith(VIDEO_EXTENSIONS):
        raise ValidationError('שם הקובץ חייב להסתיים באחת הסיומות: ' + ', '.join(VIDEO_EXTENSIONS) + '.')


def trip_folder(trip):
    """The trip's local folder as a Path (``~`` expanded), or None when not set."""
    folder = (getattr(trip, 'local_video_folder', '') or '').strip() if trip else ''
    return Path(folder).expanduser() if folder else None


def local_video_path(sample):
    """trip folder / file name, or None when either is missing."""
    name = (sample.local_video_file or '').strip()
    folder = trip_folder(sample.trip) if sample.trip_id else None
    if not name or folder is None: return None
    return folder / name


def local_video_status(sample):
    """One of the STATUS_* values above, for the manager's offline-copy marks."""
    if not sample.video_url: return STATUS_NONE
    path = local_video_path(sample)
    if path is None: return STATUS_MISSING
    if not path.parent.is_dir(): return STATUS_UNREACHABLE
    return STATUS_OK if path.is_file() else STATUS_NOT_FOUND


# ---------------------------------------------------------------------------------------------------------------
# Matching video files to observations (phase 2: filling the fields from the folders on the Mac)
#
# The exported files are named after the species without the author, e.g. "Chromodoris kalawakan.mov",
# "Aegires sp. 7.mov", "Chromodoris cf. strigata.mov"; a trip summary video is named like its title. Names are
# compared loosely: case, dots, underscores, dashes and repeated spaces are ignored ("Aegires sp  7" ==
# "Aegires sp. 7").
# ---------------------------------------------------------------------------------------------------------------
import re

VIDEO_OUTPUT_DIR_RE = re.compile(r'^video\s*output', re.I)


def normalize_video_name(text):
    text = (text or '').lower()
    for suffix in VIDEO_EXTENSIONS:
        if text.endswith(suffix): text = text[:-len(suffix)]
    return ' '.join(re.sub(r'[._\-]+', ' ', text).split())


def candidate_names(sample):
    """Every name the observation's video file may carry, normalized (most specific first)."""
    names = []
    if sample.species_id:
        genus, _, epithet = sample.species.scientific_name.partition(' ')
        qualifier = sample.identification_qualifier or ''
        stage = sample.life_stage or ''
        variant = sample.undetermined_variant or ''
        base = ' '.join(x for x in (genus, qualifier, epithet) if x)
        for name in (' '.join(x for x in (base, variant, stage) if x), ' '.join(x for x in (base, variant) if x),
                     base, sample.species.scientific_name):
            names.append(name)
    names += [sample.title, sample.title_en]
    result = []
    for name in names:
        key = normalize_video_name(name)
        if key and key not in result: result.append(key)
    return result


def video_files(folder):
    """normalized name -> [file names] of the video files directly inside `folder`."""
    files = {}
    try: entries = sorted(Path(folder).iterdir())
    except OSError: return files
    for entry in entries:
        if entry.is_file() and entry.name.lower().endswith(VIDEO_EXTENSIONS) and not entry.name.startswith('.'):
            files.setdefault(normalize_video_name(entry.name), []).append(entry.name)
    return files


def find_video_output_folders(root, depth=3):
    """Folders named "Video Output"/"VideoOutput…" under `root`, at most `depth` levels down."""
    root = Path(root).expanduser(); found = []
    def walk(folder, level):
        try: children = sorted(p for p in folder.iterdir() if p.is_dir() and not p.name.startswith('.'))
        except OSError: return
        for child in children:
            if VIDEO_OUTPUT_DIR_RE.match(child.name): found.append(child)
            elif level < depth and child.name not in ('Library', 'Applications') and not child.name.endswith(('.fcpbundle', '.app', '.photoslibrary')):
                walk(child, level + 1)
    walk(root, 1)
    return found


def location_suffix(file_key, name_key):
    """True when file_key is name_key followed by one place word ("redsea", "eilat"...)."""
    if not file_key.startswith(name_key + ' '): return False
    rest = file_key[len(name_key) + 1:]
    return ' ' not in rest and rest.isalpha() and len(rest) >= 3 and rest not in ('juv', 'cf', 'aff', 'sp', 'spp')


def match_trip(samples, folder):
    """Match the observations of one trip against the files of `folder`.
    Returns (matches: [(sample, file name)], unmatched: [sample], ambiguous: [(sample, [names])], unused: [file names])."""
    files = video_files(folder)
    matches, unmatched, ambiguous, used = [], [], [], set()
    for sample in samples:
        names = None
        for key in candidate_names(sample):
            if key in files: names = files[key]; break
        if names is None:
            # Second chance: the name plus one place word, e.g. "Chromodoris quadricolor RedSea.mov". The extra word
            # must be a real word -- never a number, a single letter or "juv" (that would be another sp./form/stage).
            for key in candidate_names(sample):
                found = [n for k, ns in files.items() for n in ns if location_suffix(k, key)]
                if found: names = found; break
        if names and len(names) > 1:
            # The same name exported twice (e.g. .mov and .m4v): the .mov is the default (the owner's rule).
            movs = [n for n in names if n.lower().endswith('.mov')]
            if len(movs) == 1: names = movs
        if names is None: unmatched.append(sample)
        elif len(names) == 1: matches.append((sample, names[0])); used.add(names[0])
        else: ambiguous.append((sample, names)); used.update(names)
    unused = sorted(n for names in files.values() for n in names if n not in used)
    return matches, unmatched, ambiguous, unused


# ---------------------------------------------------------------------------------------------------------------
# Phase 3: showing the local copy to a manager (gallery marks, the observation page's local player)
# ---------------------------------------------------------------------------------------------------------------
# Marked red in the gallery for a manager: the observation has a YouTube video but no usable local copy. A copy that
# is recorded but simply not reachable here (the live site, an unplugged drive) is not red -- the fields are filled.
NO_LOCAL_STATUSES = (STATUS_MISSING, STATUS_NOT_FOUND)
VIDEO_CONTENT_TYPE = 'video/mp4'   # .mp4/.m4v/.mov (H.264/HEVC): Safari and Chrome both play it under this type
CHUNK = 1024 * 1024


def local_video_url(sample):
    from django.urls import reverse
    return reverse('observation-local-video', args=[sample.pk])


def statuses(samples):
    """{sample pk: status} for the given samples that have a YouTube video (one folder check per trip)."""
    folders = {}
    result = {}
    for sample in samples:
        if not sample.video_url: continue
        path = local_video_path(sample)
        if path is None: result[sample.pk] = STATUS_MISSING; continue
        parent = path.parent
        if parent not in folders: folders[parent] = parent.is_dir()
        result[sample.pk] = STATUS_UNREACHABLE if not folders[parent] else STATUS_OK if path.is_file() else STATUS_NOT_FOUND
    return result


def gallery_statuses():
    """The gallery's manager data: {sample pk: status} of every live observation with a YouTube video."""
    from .models import Sample
    samples = Sample.objects.filter(deleted_at__isnull=True).exclude(video_url='').select_related('trip')
    return {str(pk): status for pk, status in statuses(samples).items()}


def annotate(samples):
    """Set .local_video_url (a playable local copy) and .local_video_missing (a video without one) on each sample."""
    found = statuses(samples)
    for sample in samples:
        status = found.get(sample.pk)
        sample.local_video_url = local_video_url(sample) if status == STATUS_OK else ''
        sample.local_video_missing = status in NO_LOCAL_STATUSES


def file_response(request, path):
    """The file with HTTP Range support -- Safari only plays a <video> whose server answers byte ranges (206)."""
    from django.http import FileResponse, HttpResponse, StreamingHttpResponse
    size = path.stat().st_size
    header = request.headers.get('Range', '')
    match = re.fullmatch(r'bytes=(\d*)-(\d*)', header.strip()) if header else None
    if header and not match:
        response = HttpResponse(status=416); response['Content-Range'] = f'bytes */{size}'; return response
    if match:
        first, last = match.groups()
        if first == '' and last == '':
            response = HttpResponse(status=416); response['Content-Range'] = f'bytes */{size}'; return response
        if first == '':
            start, end = max(size - int(last), 0), size - 1          # the last N bytes
        else:
            start, end = int(first), min(int(last), size - 1) if last else size - 1
        if start >= size or start > end:
            response = HttpResponse(status=416); response['Content-Range'] = f'bytes */{size}'; return response

        def chunks():
            with open(path, 'rb') as handle:
                handle.seek(start); remaining = end - start + 1
                while remaining > 0:
                    data = handle.read(min(CHUNK, remaining))
                    if not data: break
                    remaining -= len(data); yield data
        response = StreamingHttpResponse(chunks(), status=206, content_type=VIDEO_CONTENT_TYPE)
        response['Content-Range'] = f'bytes {start}-{end}/{size}'
        response['Content-Length'] = str(end - start + 1)
    else:
        response = FileResponse(open(path, 'rb'), content_type=VIDEO_CONTENT_TYPE)
        response['Content-Length'] = str(size)
    response['Accept-Ranges'] = 'bytes'
    response['Cache-Control'] = 'private, no-store'
    return response
