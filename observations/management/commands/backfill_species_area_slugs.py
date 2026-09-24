"""One-time backfill: generate a slug for every SpeciesArea row that doesn't have one yet
(SpeciesArea.save() auto-generates a slug for new/edited rows going forward, but existing
rows created before the species-page feature shipped were never re-saved). Safe to re-run --
a row that already has a slug is left completely alone.
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from observations.models import SpeciesArea
from observations.table_transfer import create_backup


class Command(BaseCommand):
    help = "Generate a slug for every SpeciesArea row that doesn't have one yet."

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='Actually write to the database (default: dry run report only).')

    def handle(self, *args, **options):
        apply = options['apply']
        missing = SpeciesArea.objects.filter(slug__isnull=True).select_related('species', 'country', 'sea')

        def run():
            updated = 0
            for area in missing:
                area.slug = None  # force _generate_slug() to run even if called a second time in the same process
                if apply:
                    area.save(update_fields=['slug'])
                updated += 1
            return updated

        if apply:
            backup = create_backup()
            with transaction.atomic():
                updated = run()
            self.stdout.write(f'Backup created: {backup.name}')
        else:
            updated = run()

        total = SpeciesArea.objects.count()
        self.stdout.write(f'slugs: {updated} to generate (of {total} species-area rows total)')
        if not apply:
            self.stdout.write('Dry run only -- pass --apply to write to the database.')
