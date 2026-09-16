"""Add species from an extracted taxonomic checklist that are not yet in the local catalog.

The extraction (the 'species' sheet of the personal reference spreadsheet) happens outside
this repository; this command only reads the resulting JSON ({'rows': [...]}, one dict per
species with the same keys as the sheet's columns). Existing species are left untouched —
see import_species_science for filling blanks on species that are already matched.
"""
import json
from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from observations.models import Species
from observations.table_transfer import create_backup

FIELDS = ['genus', 'species', 'author', 'order', 'family', 'superfamily', 'accepted_genus',
          'accepted_species', 'common_name', 'transliteration', 'language', 'distribution']


class Command(BaseCommand):
    help = 'Add species from an extracted checklist JSON that are missing from the local catalog.'

    def add_arguments(self, parser):
        parser.add_argument('file')
        parser.add_argument('--apply', action='store_true')

    def handle(self, *args, **options):
        if settings.PRODUCTION:
            raise CommandError('This import is intended for the local development database only.')
        data = json.loads(Path(options['file']).read_text())
        existing = set(Species.objects.values_list('scientific_name', flat=True))
        to_create = []
        for row in data['rows']:
            name = (row.get('GenusSpecies') or '').strip()
            if not name or name in existing:
                continue
            existing.add(name)  # guard against duplicate GenusSpecies within the file itself
            fields = {'scientific_name': name, 'source_id': row.get('name_code', '')}
            for field in FIELDS:
                value = row.get(field, '')
                if value:
                    fields[field] = value
            formatted_author = row.get('FormattedAuthor', '')
            if formatted_author:
                fields['formatted_author'] = formatted_author
            to_create.append(Species(**fields))
        self.stdout.write(f'{len(to_create)} species to add (checklist has {len(data["rows"])} rows).')
        if not options['apply']:
            for item in to_create[:20]:
                self.stdout.write('+ ' + item.scientific_name)
            if len(to_create) > 20:
                self.stdout.write(f'... and {len(to_create) - 20} more (use --apply to add them).')
            return
        backup = create_backup()
        with transaction.atomic():
            Species.objects.bulk_create(to_create, batch_size=500)
        report_path = Path(settings.DATA_DIR) / 'backups' / (backup.stem + '-species-catalog-import.json')
        report_path.write_text(json.dumps(
            {'backup': backup.name, 'added_count': len(to_create), 'added': [s.scientific_name for s in to_create]},
            ensure_ascii=False, indent=2))
        self.stdout.write(self.style.SUCCESS(
            f'Added {len(to_create)} species. Backup: {backup}. Report: {report_path}'))
