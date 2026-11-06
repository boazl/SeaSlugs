"""The Google Drive copies of the local videos: re-reading their Drive ids (Sample.drive_video_id).

copy_to_drive mirrors every observation's local video into the Drive folder; Google Drive for desktop keeps each
uploaded file's Drive id in the extended attribute "com.google.drivefs.item-id#S". When a local file is replaced
(a new export, a new name), the Drive copy is a NEW Drive file with a new id, and the old one goes to the Drive
trash -- the stored id then shows the old preview image and does not play on the live site. A rescan sorts every
observation into:

  same      the stored id is the copy's id
  update    the copy has another id -- store the new one
  clear     there is no copy any more (file removed, no local file / video) -- empty the stored id
  waiting   the copy is there but Drive has not uploaded it yet (no id): kept as it is, scan again later
  missing   no copy and no stored id -- nothing to do (run copy_to_drive)

Runs only on the Mac (the Drive folder and xattr); the ids reach the live site with the samples table transfer.
Used by /admin/drive-videos/ (drive_video_views.py) and `manage.py fill_drive_video_ids`."""
import re
import subprocess
from pathlib import Path

from django.db import transaction

from .local_videos import DRIVE_ID_RE

XATTR = 'com.google.drivefs.item-id#S'
SAME, UPDATE, CLEAR, WAITING, MISSING = 'same', 'update', 'clear', 'waiting', 'missing'
CHANGES = (UPDATE, CLEAR)


def drive_id(path):
    try:
        out = subprocess.run(['xattr', '-p', XATTR, str(path)], capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return ''
    value = out.stdout.strip()
    return value if out.returncode == 0 and re.fullmatch(DRIVE_ID_RE, value) else ''


def drive_root(dest=None):
    from .management.commands.copy_to_drive import DRIVE_ROOT
    return Path(dest or DRIVE_ROOT).expanduser()


def available(dest=None):
    """The Drive folder is on this machine (the Mac, Drive for desktop running)."""
    return drive_root(dest).is_dir()


def scan(dest=None):
    """[{sample, path, old, new, action}] for every live observation with a local video or a stored Drive id."""
    from django.db.models import Q
    from .models import Sample
    from .management.commands.copy_to_drive import drive_video_path
    root = drive_root(dest)
    rows = []
    samples = (Sample.objects.filter(deleted_at__isnull=True)
               .filter(Q(local_video_file__gt='', video_url__gt='') | Q(drive_video_id__gt=''))
               .select_related('trip', 'species').order_by('trip__code', 'pk'))
    for sample in samples:
        old = sample.drive_video_id
        path = drive_video_path(sample, root) if sample.local_video_file and sample.video_url else None
        if path is not None and path.is_file():
            new = drive_id(path)
            action = (SAME if new == old else UPDATE) if new else WAITING
            if not new: new = old
        else:
            new = ''
            action = CLEAR if old else MISSING
        rows.append({'sample': sample, 'path': path, 'old': old, 'new': new, 'action': action})
    return rows


def apply(rows):
    """Save the update / clear rows (only the drive_video_id column, no save() side effects). Returns their count."""
    from .models import Sample
    changes = [r for r in rows if r['action'] in CHANGES]
    with transaction.atomic():
        for row in changes:
            Sample.objects.filter(pk=row['sample'].pk).update(drive_video_id=row['new'])
    return len(changes)
