"""Import the legacy catalog using a read-only JSON extraction of the source workbook."""
import json
from pathlib import Path
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from observations.models import Sample, Species, Country, Sea, Region, Site
from observations.table_transfer import create_backup
from .import_gallery_species import match_key, GENERAL


class Command(BaseCommand):
    help = 'Import gallery samples locally. Existing imported records are never overwritten.'

    def add_arguments(self, parser):
        parser.add_argument('extraction')
        parser.add_argument('--owner', required=True)
        parser.add_argument('--apply', action='store_true')

    def handle(self, *args, **options):
        if settings.PRODUCTION:
            raise CommandError('Local import only.')
        source = json.loads(Path(options['extraction']).read_text())
        catalog = json.loads((settings.BASE_DIR/'dist/catalog.js').read_text().split('=', 1)[1].strip().removesuffix(';'))
        owner = get_user_model().objects.get(username=options['owner'])
        expeditions = {r['קוד_תצפית']: r for r in source['Observations']}
        expedition = expeditions['V']
        if (expedition['צלם'], expedition['אזור']) != ('Boaz Liebes', 'Romblon'):
            raise CommandError('Unexpected expedition V. Review source before importing.')
        species = {}
        for item in Species.objects.all():
            species.setdefault(match_key(item.scientific_name), []).append(item)
        planned = []
        for order, video in enumerate(catalog['videos']):
            source_id = 'youtube:' + video['id']
            if Sample.objects.filter(source_id=source_id).exists():
                continue
            code = {'romblon': 'V', 'redsea': 'J', 'mediterranean': 'I'}[video['region']]
            trip = expeditions[code]
            matches = species.get(match_key(video['title']), [])
            if len(matches) != 1 and video['title'] not in GENERAL:
                raise CommandError('Ambiguous or missing species: ' + video['title'])
            samples = [r for r in source['samples'] if r['ObservationID'] == code and match_key(r['species name'] or '') == match_key(video['title'])]
            planned.append((order, video, source_id, trip, matches[0] if len(matches) == 1 else None, samples))
        self.stdout.write(f'New samples: {len(planned)}; existing skipped: {len(catalog["videos"])-len(planned)}')
        if not options['apply'] or not planned:
            return
        backup = create_backup()
        report = []
        with transaction.atomic():
            philippines = Country.objects.get(name_en='Philippines')
            sea, _ = Sea.objects.get_or_create(name_en=expedition['ים'], defaults={'name': expedition['ים']})
            romblon, _ = Region.objects.get_or_create(country=philippines, name_en='Romblon', defaults={'name': 'רומבלון', 'sea': sea})
            regions = {'romblon': romblon, 'redsea': Region.objects.get(name_en='Eilat'), 'mediterranean': Region.objects.get(name_en='Akhziv')}
            for order, video, source_id, trip, species_item, matches in planned:
                region = regions[video['region']]
                reasons = []
                if not species_item:
                    reasons.append('סרטון כללי ללא מין יחיד; נדרשת החלטה על שיוך.')
                if not trip['שנה']:
                    reasons.append('שנה חסרה באקסל.')
                metadata = {'expedition_code': trip['קוד_תצפית'], 'expedition_row': trip['_row'], 'photographer': trip['צלם'], 'sample_rows': [r['_row'] for r in matches], 'missing': reasons}
                site = None
                depth = None
                if len(matches) == 1:
                    row = matches[0]
                    metadata.update(excel_sample_id=row['SampleID'], video_files=row['Video Files'])
                    if row.get('site'):
                        site, _ = Site.objects.get_or_create(region=region, name=str(row['site']))
                    if isinstance(row.get('depth'), (int, float)):
                        depth = row['depth']
                item = Sample(owner=owner, species=species_item, country=region.country, region=region, site=site, depth=depth,
                    year=trip['שנה'], month=trip['חודש'], title=video['title'], video_url='https://www.youtube.com/watch?v='+video['id'],
                    gallery_order=order, source_id=source_id, source_metadata=metadata)
                if not reasons:
                    item.save_reviewed(actor=owner, approve=True)
                else:
                    # Preserve incomplete legacy records as drafts, never bypass publication validation.
                    item.save()
                report.append({'id': item.pk, 'title': item.title, 'status': item.status, 'missing': reasons, 'matched_excel_rows': metadata['sample_rows']})
        path = backup.with_suffix('.samples.json')
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2))
        self.stdout.write(f'Imported {len(report)}. Published: {sum(r["status"] == "published" for r in report)}. Report: {path}')
