"""Copy the site and the observations' local video files into the Google Drive folder (run on the Mac).

    python manage.py copy_to_drive              # site + videos
    python manage.py copy_to_drive --videos-only
    python manage.py copy_to_drive --dry-run

Layout in the destination (default DRIVE_ROOT below):
- the site folder's contents at the top. Excluded: .venv, .git, __pycache__, the SQLite journal files, and the
  secrets .env / .secret_key. db.sqlite3 is a verified online backup, never a copy of the live file.
- Videos/<path under the home folder>/<file>: every observation's local video (trip folder / file name), in the
  same folder structure as on the Mac, e.g. Videos/Romblon Island/Video Output/Chromodoris kalawakan.mov. Only this
  folder is meant to be shared ("anyone with the link can view"); the site folder holds private data.

Existing files are overwritten when they differ (size or modification time); unchanged files are skipped, so an
interrupted run simply continues. Inside the site's own sub-folders and inside Videos the destination mirrors the
source: files that are no longer in the source are deleted. Files at the top of the destination that are not part
of the site (documents kept there by hand) are left alone.
"""
import os
import shutil
import sqlite3
from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from observations.models import Sample
from observations.local_videos import local_video_path

DRIVE_ROOT = '~/Library/CloudStorage/GoogleDrive-boaz.liebes@mail.huji.ac.il/האחסון שלי/SeaSlugs.org.il'
VIDEOS = 'Videos'
SKIP_DIRS = {'.venv', '.git', '__pycache__', VIDEOS}
SKIP_FILES = {'.env', '.secret_key', '.DS_Store', 'db.sqlite3'}


def drive_video_path(sample, root=DRIVE_ROOT):
    """Where the observation's local video goes in the Drive copy (None when it has no local video path)."""
    path = local_video_path(sample)
    if path is None: return None
    home = Path('~').expanduser()
    try: relative = path.relative_to(home)
    except ValueError: relative = Path(*path.parts[1:])   # outside the home folder (e.g. /Volumes/…)
    return Path(root).expanduser() / VIDEOS / relative


def backup_database(target):
    """A consistent online SQLite backup written to `target` (through a temporary name)."""
    temporary = target.with_name('db.sqlite3.part')
    with sqlite3.connect(str(settings.DATABASES['default']['NAME'])) as src, sqlite3.connect(temporary) as dst: src.backup(dst)
    os.replace(temporary, target)


class Command(BaseCommand):
    help = 'Copy the site and the local video files into the SeaSlugs.org.il Google Drive folder.'

    def add_arguments(self, parser):
        parser.add_argument('--dest', default=DRIVE_ROOT)
        parser.add_argument('--videos-only', action='store_true')
        parser.add_argument('--site-only', action='store_true')
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **opts):
        dest = Path(opts['dest']).expanduser()
        if not dest.is_dir(): raise CommandError(f'The destination folder does not exist: {dest}')
        self.dry = opts['dry_run']; self.copied = self.skipped = self.deleted = 0; self.bytes = 0
        if not opts['videos_only']: self.copy_site(Path(settings.BASE_DIR), dest)
        if not opts['site_only']: self.copy_videos(dest)
        self.stdout.write(self.style.SUCCESS(
            f'{"Dry run: " if self.dry else ""}copied {self.copied} files ({self.bytes / 1e9:.1f} GB), '
            f'unchanged {self.skipped}, deleted {self.deleted}.'))

    # -- helpers ----------------------------------------------------------------------------------------------
    def copy_file(self, source, target):
        try:
            same = target.is_file() and target.stat().st_size == source.stat().st_size \
                   and int(target.stat().st_mtime) == int(source.stat().st_mtime)
        except OSError: same = False
        if same: self.skipped += 1; return
        self.copied += 1; self.bytes += source.stat().st_size
        self.stdout.write(f'  copy {target}')
        if self.dry: return
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)

    def delete(self, path):
        self.deleted += 1; self.stdout.write(f'  delete {path}')
        if self.dry: return
        if path.is_dir() and not path.is_symlink(): shutil.rmtree(path)
        else: path.unlink()

    def mirror_dir(self, target, keep):
        """Delete what is inside `target` but not in `keep` (names)."""
        if not target.is_dir(): return
        for entry in target.iterdir():
            if entry.name not in keep and entry.name != '.DS_Store' and not entry.name.startswith('Icon'):
                self.delete(entry)

    # -- the site -----------------------------------------------------------------------------------------------
    def copy_site(self, base, dest):
        self.stdout.write(self.style.MIGRATE_HEADING(f'Site: {base} -> {dest}'))
        for folder, dirs, files in os.walk(base):
            folder = Path(folder); relative = folder.relative_to(base)
            dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not (relative == Path('.') and d == VIDEOS))
            names = sorted(f for f in files if f not in SKIP_FILES and not f.startswith('db.sqlite3-journal') and not f.endswith('.pyc'))
            for name in names: self.copy_file(folder / name, dest / relative / name)
            if relative != Path('.'):
                self.mirror_dir(dest / relative, set(dirs) | set(names))
        # the database: a consistent online backup, not the live file
        target = dest / 'db.sqlite3'
        self.stdout.write(f'  backup {target}'); self.copied += 1
        if not self.dry: backup_database(target)

    # -- the videos ---------------------------------------------------------------------------------------------
    def copy_videos(self, dest):
        self.stdout.write(self.style.MIGRATE_HEADING(f'Videos -> {dest / VIDEOS}'))
        wanted = {}
        missing = []
        samples = Sample.objects.filter(deleted_at__isnull=True).exclude(local_video_file='').exclude(video_url='').select_related('trip')
        for sample in samples:
            source = local_video_path(sample)
            if source is None or not source.is_file(): missing.append((sample, source)); continue
            wanted[drive_video_path(sample, dest)] = source
        for target, source in sorted(wanted.items()): self.copy_file(source, target)
        # mirror Videos/: remove files (and empty folders) that no observation uses any more
        root = dest / VIDEOS
        if root.is_dir():
            for folder, dirs, files in os.walk(root, topdown=False):
                for name in files:
                    path = Path(folder) / name
                    if path not in wanted and name != '.DS_Store': self.delete(path)
                if Path(folder) != root and not self.dry and not any(Path(folder).iterdir()): Path(folder).rmdir()
        for sample, source in missing:
            self.stdout.write(self.style.ERROR(f'  missing on the Mac: #{sample.pk} {sample.taxon_name or sample.title} ({source})'))
