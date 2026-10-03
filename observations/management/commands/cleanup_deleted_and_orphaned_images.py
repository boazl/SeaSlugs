"""One-time cleanup, a follow-up to rename_images_to_canonical, for the two kinds of image
file that command deliberately leaves alone because it only ever touches active (non-deleted)
samples:

1. A file under the media folder's observations/ subtree that no Sample row -- active or
   soft-deleted -- references by its exact stored path at all: genuinely orphaned, with
   nothing left to lose it would restore. These are simply deleted.

2. A soft-deleted sample's own image file, still sitting under whatever name it had before it
   was deleted (a random upload-time UUID, or a legacy content-hash name) -- rather than
   deleting these (the admin's own "restore" action clears Sample.deleted_at and brings the
   observation straight back, photo and all, so the file is still very much needed), they are
   renamed to the SAME canonical, human-meaningful name every active sample now has (see
   Sample.canonical_image_name), with '-deleted-sample' appended, so a deleted observation's
   file stays identifiable at a glance instead of being an opaque hash or UUID forever. If a
   file already happens to sit at that exact target name (a stale leftover from a previous,
   interrupted run of this same command), it is overwritten.

Two or more deleted samples -- or a deleted sample and an active one -- can share one
underlying file (see rename_images_to_canonical's own module docstring for why that happens);
every sample sharing a source file gets its own independent copy before that source is ever
removed, which is what keeps this correct regardless of how many samples point at the same
file. A deleted sample's file can also already be missing for the exact same reason
rename_images_to_canonical needed its own recovery step: an earlier, buggy (move-based) run
moved it away under a sibling ACTIVE sample before this command -- which only ever looks at
deleted samples -- had a chance to see it. The same content-hash recovery is used here too.

Dry run by default -- pass --apply to actually delete/rename files and update the database.
"""
import hashlib
import re
import shutil
from collections import defaultdict
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from observations.models import Sample
from observations.table_transfer import create_backup

_DELETED_SUFFIX = '-deleted-sample.jpg'
_LEGACY_HASH_RE = re.compile(r'observations/transfer/([0-9a-f]{64})\.jpg')


class Command(BaseCommand):
    help = ("Delete orphaned image files, and rename soft-deleted samples' own image files to "
            "a canonical '...-deleted-sample.jpg' name.")

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='Actually delete/rename files and write to the database (default: dry run report only).')

    def handle(self, *args, **options):
        apply = options['apply']
        root = Path(settings.MEDIA_ROOT).resolve()
        obs_root = root / 'observations'

        # Every path any sample (active or deleted) currently points at -- computed BEFORE
        # the rename pass below touches anything, so a deleted sample's own not-yet-renamed
        # file is correctly seen as "referenced" and never mistaken for an orphan.
        referenced = set(Sample.objects.exclude(image='').values_list('image', flat=True))

        orphaned = []
        if obs_root.is_dir():
            for path in sorted(obs_root.rglob('*.jpg')):
                if path.is_file() and str(path.relative_to(root)) not in referenced:
                    orphaned.append(path)

        deleted_samples = list(Sample.objects.exclude(image='').filter(deleted_at__isnull=False)
                                .select_related('species', 'trip').order_by('pk'))

        def content_hash_index():
            index = {}
            if obs_root.is_dir():
                for path in obs_root.rglob('*.jpg'):
                    if path.is_file():
                        index.setdefault(hashlib.sha256(path.read_bytes()).hexdigest(), path)
            return index

        def run():
            orphans_deleted = 0
            for path in orphaned:
                self.stdout.write(f'orphan: {path.relative_to(root)}')
                if apply:
                    path.unlink(missing_ok=True)
                orphans_deleted += 1

            groups = defaultdict(list)
            already_done = 0
            for sample in deleted_samples:
                if sample.image.name.endswith(_DELETED_SUFFIX):
                    already_done += 1
                    continue
                groups[sample.image.name].append(sample)

            renamed = recovered = 0
            missing_files = []
            hash_index = None

            for current, group in groups.items():
                source_path = root / current
                via_hash_recovery = False
                if not source_path.is_file():
                    legacy = _LEGACY_HASH_RE.fullmatch(current)
                    found = None
                    if legacy:
                        if hash_index is None:
                            hash_index = content_hash_index()
                        found = hash_index.get(legacy.group(1))
                    if found is None:
                        missing_files.extend((sample.pk, current) for sample in group)
                        continue
                    source_path = found
                    via_hash_recovery = True

                for sample in group:
                    base = sample.canonical_image_name()  # 'observations/<slug>.jpg'
                    desired = base[:-len('.jpg')] + _DELETED_SUFFIX
                    new_path = root / desired
                    if apply:
                        if new_path.exists():
                            new_path.unlink()
                        new_path.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(source_path, new_path)
                        Sample.objects.filter(pk=sample.pk).update(image=desired)
                    if via_hash_recovery:
                        recovered += 1
                        self.stdout.write(f'#{sample.pk}: {current} -> {desired}  (recovered by content hash; found at {source_path.relative_to(root)})')
                    else:
                        renamed += 1
                        self.stdout.write(f'#{sample.pk}: {current} -> {desired}')

                if apply and not via_hash_recovery:
                    source_path.unlink(missing_ok=True)

            return orphans_deleted, renamed, recovered, already_done, missing_files

        if apply:
            backup = create_backup()
            with transaction.atomic():
                orphans_deleted, renamed, recovered, already_done, missing_files = run()
            self.stdout.write(f'Backup created: {backup.name}')
        else:
            orphans_deleted, renamed, recovered, already_done, missing_files = run()

        self.stdout.write(
            f'orphaned files: {orphans_deleted} {"deleted" if apply else "to delete"}; '
            f'deleted-sample images: {renamed} to rename, {recovered} recovered by content hash, {already_done} already done')
        if missing_files:
            self.stdout.write(self.style.WARNING(f'{len(missing_files)} deleted samples reference a file that is missing on disk (left untouched):'))
            for pk, name in missing_files:
                self.stdout.write(f'  #{pk}: {name}')
        if not apply:
            self.stdout.write('Dry run only -- pass --apply to delete/rename files and update the database.')
