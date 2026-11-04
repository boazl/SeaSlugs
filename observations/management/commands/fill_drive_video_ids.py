"""Fill Sample.drive_video_id from the copies in the Google Drive folder (run on the Mac, after copy_to_drive and
after Google Drive has finished uploading).

Google Drive for desktop keeps each uploaded file's Drive id in the extended attribute
"com.google.drivefs.item-id#S"; this command reads it with `xattr`. A file Drive has not uploaded yet has no id
and is reported -- run again later. Default is a dry run; --apply backs up and saves (only that one column).
"""
import re
import subprocess
from django.core.management.base import BaseCommand
from django.db import transaction
from observations.models import Sample
from observations.local_videos import DRIVE_ID_RE
from observations.management.commands.copy_to_drive import drive_video_path, DRIVE_ROOT
from observations.table_transfer import create_backup

XATTR = 'com.google.drivefs.item-id#S'


def drive_id(path):
    try:
        out = subprocess.run(['xattr', '-p', XATTR, str(path)], capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return ''
    value = out.stdout.strip()
    return value if out.returncode == 0 and re.fullmatch(DRIVE_ID_RE, value) else ''


class Command(BaseCommand):
    help = 'Fill the Google Drive ids of the observations\' video copies.'

    def add_arguments(self, parser):
        parser.add_argument('--dest', default=DRIVE_ROOT)
        parser.add_argument('--apply', action='store_true')

    def handle(self, *args, **opts):
        found, missing = [], []
        for sample in Sample.objects.filter(deleted_at__isnull=True).exclude(local_video_file='').exclude(video_url='').select_related('trip'):
            path = drive_video_path(sample, opts['dest'])
            value = drive_id(path) if path and path.is_file() else ''
            (found if value else missing).append((sample, path, value))
        changed = [(s, v) for s, _, v in found if s.drive_video_id != v]
        self.stdout.write(f'With a Drive id: {len(found)} (changed: {len(changed)}); without: {len(missing)}')
        for sample, path, _ in missing:
            self.stdout.write(self.style.WARNING(f'  no Drive id yet: #{sample.pk} {path}'))
        if not opts['apply']:
            self.stdout.write('Dry run -- run with --apply to save.'); return
        if changed:
            self.stdout.write(f'Backup: {create_backup()}')
            with transaction.atomic():
                for sample, value in changed:
                    Sample.objects.filter(pk=sample.pk).update(drive_video_id=value)
        self.stdout.write(self.style.SUCCESS(f'Saved {len(changed)} Drive ids.'))
