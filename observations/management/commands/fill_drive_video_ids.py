"""Re-read the Google Drive ids of the observations' video copies (drive_videos.py) -- run on the Mac, after
copy_to_drive and after Google Drive has finished uploading. New ids are stored, ids of copies that are gone are
cleared, copies Drive has not uploaded yet are reported. The same scan runs on /admin/drive-videos/.
Default is a dry run; --apply backs up and saves (only that one column)."""
from django.core.management.base import BaseCommand, CommandError
from observations import drive_videos
from observations.drive_videos import scan, apply, available, UPDATE, CLEAR, WAITING, SAME
from observations.table_transfer import create_backup


class Command(BaseCommand):
    help = 'Re-read the Google Drive ids of the observations\' video copies.'

    def add_arguments(self, parser):
        parser.add_argument('--dest', default=None)
        parser.add_argument('--apply', action='store_true')

    def handle(self, *args, **opts):
        if not available(opts['dest']):
            raise CommandError(f'The Google Drive folder is not on this machine: {drive_videos.drive_root(opts["dest"])}')
        rows = scan(opts['dest'])
        count = lambda action: sum(1 for r in rows if r['action'] == action)
        self.stdout.write(f'Unchanged: {count(SAME)}; new id: {count(UPDATE)}; removed copy: {count(CLEAR)}; '
                          f'not uploaded yet: {count(WAITING)}')
        for row in rows:
            if row['action'] == WAITING:
                self.stdout.write(self.style.WARNING(f'  no Drive id yet: #{row["sample"].pk} {row["path"]}'))
        if not opts['apply']:
            self.stdout.write('Dry run -- run with --apply to save.'); return
        if count(UPDATE) or count(CLEAR):
            self.stdout.write(f'Backup: {create_backup()}')
        self.stdout.write(self.style.SUCCESS(f'Saved {apply(rows)} Drive ids.'))
