"""Bulk-fill genus page texts (description / identification, Hebrew and English, and the
sources list) from a CSV file.

Dry run by default; pass --apply to save. Only BLANK fields are filled -- a text already
entered on the genus is never overwritten (it is reported as a conflict when the CSV
disagrees) -- and genus names must match an existing TaxonGenus exactly.

CSV columns (UTF-8, header row; every column except `genus` is optional):
  genus, description_he, description_en, identification_he, identification_en, sources
`sources` holds one source per line (a URL or a plain reference), exactly as in the admin.
"""
import csv
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from observations.models import TaxonGenus

FIELDS = ['description_he', 'description_en', 'identification_he', 'identification_en', 'sources']


class Command(BaseCommand):
    help = 'Fill blank genus description/identification/sources texts from a CSV file (dry run unless --apply).'

    def add_arguments(self, parser):
        parser.add_argument('file')
        parser.add_argument('--apply', action='store_true')

    def handle(self, *args, **options):
        path = Path(options['file'])
        if not path.exists():
            raise CommandError(f'No such file: {path}')
        with path.open(newline='', encoding='utf-8-sig') as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames or 'genus' not in reader.fieldnames:
                raise CommandError('The CSV needs a "genus" column.')
            unknown = [name for name in reader.fieldnames if name not in FIELDS + ['genus']]
            if unknown:
                raise CommandError(f'Unknown column(s): {", ".join(unknown)}')
            rows = list(reader)
        filled, unmatched, conflicts = [], [], []
        with transaction.atomic():
            for row in rows:
                name = (row.get('genus') or '').strip()
                genus = TaxonGenus.objects.filter(name=name).first() if name else None
                if not genus:
                    unmatched.append(name or '(blank)')
                    continue
                changed = []
                for field in FIELDS:
                    value = (row.get(field) or '').strip()
                    if not value:
                        continue
                    current = getattr(genus, field)
                    if current and current.strip() != value:
                        conflicts.append(f'{name}: {field}')
                    elif not current:
                        setattr(genus, field, value)
                        changed.append(field)
                if changed:
                    genus.full_clean(exclude=['family', 'defining_sample', 'identification_file'])
                    filled.append((name, changed))
                    if options['apply']:
                        genus.save(update_fields=changed)
        verb = 'updated' if options['apply'] else 'to update'
        self.stdout.write(f'{len(filled)} genera {verb}')
        for name, changed in filled:
            self.stdout.write(f'  {name}: {", ".join(changed)}')
        self.stdout.write(f'Unmatched genus names: {len(unmatched)}')
        for name in unmatched:
            self.stdout.write(f'  {name}')
        self.stdout.write(f'Conflicts (kept the existing text): {len(conflicts)}')
        for conflict in conflicts:
            self.stdout.write(f'  {conflict}')
        if not options['apply']:
            self.stdout.write('Dry run -- nothing saved. Pass --apply to save.')
