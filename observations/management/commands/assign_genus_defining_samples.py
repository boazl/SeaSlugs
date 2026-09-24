"""Point each TaxonGenus.defining_sample at its own dedicated genus-kind Sample
(kind=Sample.Kind.GENUS, species_other=<genus name>), whenever a published one exists --
overriding whatever species-level photo may currently be set there. A purpose-built genus
reference photo is a better representative of the whole genus in the gallery's genus panel
than a photo of one particular species standing in for it.

Safe to re-run: a genus with no matching genus-kind sample is left completely untouched, so
this never clears a value build_taxonomy_tables (or an admin) set some other way.
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from observations.models import Sample, TaxonGenus
from observations.table_transfer import create_backup

from .build_taxonomy_tables import _pick_defining_sample


class Command(BaseCommand):
    help = "Point TaxonGenus.defining_sample at each genus's own dedicated genus-kind Sample, when one exists."

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='Actually write to the database (default: dry run report only).')

    def handle(self, *args, **options):
        apply = options['apply']

        def genus_samples(name):
            return Sample.objects.filter(kind=Sample.Kind.GENUS, species_other=name,
                                          status='published', deleted_at__isnull=True)

        def run():
            updated = 0
            unchanged = 0
            for genus in TaxonGenus.objects.all():
                picked = _pick_defining_sample(genus_samples(genus.name))
                if not picked or genus.defining_sample_id == picked.pk:
                    unchanged += 1
                    continue
                updated += 1
                if apply:
                    genus.defining_sample = picked
                    genus.save(update_fields=['defining_sample'])
            return updated, unchanged

        if apply:
            backup = create_backup()
            with transaction.atomic():
                updated, unchanged = run()
            self.stdout.write(f'Backup created: {backup.name}')
        else:
            updated, unchanged = run()

        genera_with_sample = Sample.objects.filter(
            kind=Sample.Kind.GENUS, status='published', deleted_at__isnull=True,
        ).values('species_other').distinct().count()
        self.stdout.write(
            f'genus defining_sample: {updated} to update, {unchanged} already correct or no genus-kind sample '
            f'(of {TaxonGenus.objects.count()} genera; {genera_with_sample} distinct genera have a published genus-kind sample)'
        )
        if not apply:
            self.stdout.write('Dry run only -- pass --apply to write to the database.')
