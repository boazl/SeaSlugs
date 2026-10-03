"""One-time migration: rename every active (non-deleted) sample's existing image file from
whatever it is currently called (a random upload-time UUID, or a content-hash name from the
transfer pipeline) to the canonical, human-meaningful name -- trip code + a kind-dependent
identity -- that every upload path (the public form, Django admin, the bulk folder importer,
the image manager's transfer upload) now writes new images under (see
Sample.canonical_image_name on the Sample model).

This keeps the two environments' media folders meaningfully comparable: once every image
is named this way, the image manager's cross-environment comparison tool (ניהול תמונות ->
"השוואת תמונות בין הסביבות") can diff by plain filename alone, which is also what makes the
rename itself safe to run independently in each environment -- it never needs to look at
the other side.

Two or more samples can legitimately reference the very same stored image file -- most often
a species sample and that genus/family/order's own "defining sample" (see
assign_genus_defining_samples), which is deliberately set to reuse one of its member species'
own photo as a representative image, rather than being its own separate upload. Each sample
still gets its own distinct canonical name (Sample.canonical_image_name depends on the
sample's own kind and identity, not on which file it happens to share), so every sample
sharing a source file is copied to its own destination before that shared source is ever
removed -- it is deleted only once every sample that was pointing at it has its own
independent copy, which is what makes the result correct regardless of processing order.

An earlier version of this command used a plain rename (move) per sample instead, which broke
exactly that case: whichever sample happened to be processed first stole the file out from
under every sibling still pointing at that same path, leaving their own Sample.image value
referencing a file that no longer existed. A real run against this project's own database hit
this: 19 genus-kind "defining sample" rows were left pointing at a file a sibling species
sample's own rename had already moved away. If a sample's own current file is missing for that
reason -- its current name follows the legacy content-hash scheme (sha256 of its own former
content) -- this command recovers it by searching every file currently in the media folder for
one whose content still matches that hash, before finally giving up and reporting it as
missing.

Run this once in EACH environment separately (the Mac, then production) after the code that
writes this scheme has been deployed there. Safe to re-run: any sample whose image is already
canonically named is left untouched.

Dry run by default -- pass --apply to actually rename files on disk and update the database.
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

_LEGACY_HASH_RE = re.compile(r'observations/transfer/([0-9a-f]{64})\.jpg')


class Command(BaseCommand):
    help = "Rename every active sample's image file to its canonical (trip code + identity) name."

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='Actually rename files and write to the database (default: dry run report only).')

    def handle(self, *args, **options):
        apply = options['apply']
        root = Path(settings.MEDIA_ROOT).resolve()
        samples = list(Sample.objects.exclude(image='').filter(deleted_at__isnull=True)
                       .select_related('species', 'trip').order_by('pk'))

        def content_hash_index():
            # sha256 -> Path, for every file currently under the media root's observations
            # folder. Built lazily, only the first time some sample's own file turns out to
            # be missing -- the ordinary case never needs it.
            index = {}
            obs_root = root / 'observations'
            if obs_root.is_dir():
                for path in obs_root.rglob('*.jpg'):
                    if path.is_file():
                        index.setdefault(hashlib.sha256(path.read_bytes()).hexdigest(), path)
            return index

        def run():
            groups = defaultdict(list)
            for sample in samples:
                groups[sample.image.name].append(sample)

            renamed = recovered = already_canonical = 0
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

                keep_source = False
                for sample in group:
                    desired = sample.canonical_image_name()
                    if current == desired and not via_hash_recovery:
                        already_canonical += 1
                        keep_source = True
                        continue
                    new_path = root / desired
                    if apply:
                        new_path.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(source_path, new_path)
                        Sample.objects.filter(pk=sample.pk).update(image=desired)
                    if via_hash_recovery:
                        recovered += 1
                        self.stdout.write(f'#{sample.pk}: {current} -> {desired}  (recovered by content hash; found at {source_path.relative_to(root)})')
                    else:
                        renamed += 1
                        self.stdout.write(f'#{sample.pk}: {current} -> {desired}')

                if apply and not via_hash_recovery and not keep_source:
                    source_path.unlink(missing_ok=True)

            return renamed, recovered, already_canonical, missing_files

        if apply:
            backup = create_backup()
            with transaction.atomic():
                renamed, recovered, already_canonical, missing_files = run()
            self.stdout.write(f'Backup created: {backup.name}')
        else:
            renamed, recovered, already_canonical, missing_files = run()

        total = len(samples)
        self.stdout.write(
            f'images: {renamed} to rename, {recovered} recovered by content hash, '
            f'{already_canonical} already canonical (of {total} active image-bearing samples)')
        if missing_files:
            self.stdout.write(self.style.WARNING(f'{len(missing_files)} samples reference a file that is missing on disk (left untouched):'))
            for pk, name in missing_files:
                self.stdout.write(f'  #{pk}: {name}')
        if not apply:
            self.stdout.write('Dry run only -- pass --apply to rename files and write to the database.')
