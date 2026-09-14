"""Read a JSON extraction of Observations. The source workbook is never modified."""
import json
import re
from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from observations.models import DiveTrip, Sample
from observations.table_transfer import create_backup


class Command(BaseCommand):
    help = 'Import missing trips and link existing gallery samples, locally only.'
    def add_arguments(self, parser):
        parser.add_argument('extraction')
        parser.add_argument('--apply', action='store_true')

    def handle(self, *args, **options):
        if settings.PRODUCTION: raise CommandError('Local import only; use table transfer for the server.')
        rows = json.loads(Path(options['extraction']).read_text())
        self.stdout.write(f'Source rows: {len(rows)}')
        if not options['apply']: return
        backup = create_backup(); added = linked = collections = 0
        with transaction.atomic():
            for row in rows:
                code = row['קוד_תצפית']
                if DiveTrip.objects.filter(code=code).exists(): continue
                title = row['שם'] or row['שמורה'] or row['מיון'] or code
                count = re.match(r'^(\d+)\s+(?:Species|species|Nudibranchs|Nudibranchs &)', title)
                trip = DiveTrip(code=code, title=title, source_sort=row['מיון'] or '', year=row['שנה'], month=row['חודש'],
                    start_day=row['יום_התחלה'], duration_days=row['מספר ימים'], country_name=row['מדינה'] or '',
                    region_name=row['אזור'] or '', reserve=(row['שמורה'] or '').strip(), sea_name=row['ים'] or '',
                    photographer=row['צלם'] or '', species_count=int(count[1]) if count else None,
                    source_metadata={'sheet':'Observations', 'row':row['source_row'], 'original':row})
                trip.full_clean(); trip.save(); added += 1
            for sample in Sample.objects.filter(trip__isnull=True):
                code = sample.source_metadata.get('expedition_code')
                trip = DiveTrip.objects.filter(code=code).first() if code else None
                if not trip: continue
                sample.trip = trip
                if sample.source_id in ('youtube:4z1ezvGEbFI', 'youtube:XN9IGI5FAsM'):
                    sample.kind = Sample.Kind.COLLECTION
                    if sample.source_id == 'youtube:4z1ezvGEbFI':
                        sample.year = sample.year or 2023
                        sample.month = sample.month or 7
                        sample.source_metadata['date_source'] = 'Existing video title: קניון אכזיב יולי 23'
                    sample.source_metadata['missing'] = []
                    # Existing site owner's curated summary videos, explicitly reclassified as collections.
                    if sample.deleted_at is None:
                        sample.save_reviewed(actor=sample.owner, approve=True)
                    else: sample.save()
                    collections += 1
                else: sample.save(update_fields=['trip'])
                linked += 1
        self.stdout.write(f'Added trips: {added}; linked samples: {linked}; collections: {collections}; backup: {backup.name}')
