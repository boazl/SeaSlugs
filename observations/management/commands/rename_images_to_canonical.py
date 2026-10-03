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

Run this once in EACH environment separately (the Mac, then production) after the code that
writes this scheme has been deployed there. Processes samples in a stable order (by pk) so
that, within a single run, a collision between two samples destined for the same base name
is resolved deterministically and reproducibly (see the -2, -3, ... suffixing in
canonical_image_name) -- running it a second time is a safe no-op: any sample whose image is
already canonically named is left untouched.

Safe to re-run. Dry run by default -- pass --apply to actually rename files on disk and
update the database.
"""
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from observations.models import Sample
from observations.table_transfer import create_backup


class Command(BaseCommand):
    help = "Rename every active sample's image file to its canonical (trip code + identity) name."

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='Actually rename files and write to the database (default: dry run report only).')

    def handle(self, *args, **options):
        apply = options['apply']
        root = Path(settings.MEDIA_ROOT).resolve()
        samples = Sample.objects.exclude(image='').filter(deleted_at__isnull=True).select_related('species', 'trip').order_by('pk')

        def run():
            renamed = 0
            already_canonical = 0
            missing_files = []
            for sample in samples:
                current = sample.image.name
                # Processed in pk order, with the rename committed immediately below (inside
                # the one shared transaction when --apply is given) -- so by the time a later
                # sample's canonical_image_name() runs its own collision check, it already
                # sees every earlier sample's NEW name, and resolves a shared base name to a
                # -2, -3, ... suffix the same deterministic way canonical_image_name() always
                # does for a brand-new upload.
                desired = sample.canonical_image_name()
                if current == desired:
                    already_canonical += 1
                    continue
                old_path = root / current
                new_path = root / desired
                if not old_path.is_file():
                    missing_files.append((sample.pk, current))
                    continue
                if apply:
                    new_path.parent.mkdir(parents=True, exist_ok=True)
                    old_path.rename(new_path)
                    Sample.objects.filter(pk=sample.pk).update(image=desired)
                self.stdout.write(f'#{sample.pk}: {current} -> {desired}')
                renamed += 1
            return renamed, already_canonical, missing_files

        if apply:
            backup = create_backup()
            with transaction.atomic():
                renamed, already_canonical, missing_files = run()
            self.stdout.write(f'Backup created: {backup.name}')
        else:
            renamed, already_canonical, missing_files = run()

        total = samples.count()
        self.stdout.write(f'images: {renamed} to rename, {already_canonical} already canonical (of {total} active image-bearing samples)')
        if missing_files:
            self.stdout.write(self.style.WARNING(f'{len(missing_files)} samples reference a file that is missing on disk (left untouched):'))
            for pk, name in missing_files:
                self.stdout.write(f'  #{pk}: {name}')
        if not apply:
            self.stdout.write('Dry run only -- pass --apply to rename files and write to the database.')
