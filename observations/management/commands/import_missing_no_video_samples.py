"""Add draft Sample rows for species that were observed (photographed, never filmed) on one
of the photographer's own trips or an Israel trip, and are not yet represented in our DB.

For every dive trip in the personal reference spreadsheet's 'Observations' sheet where the
photographer is Boaz Liebes or the country is Israel, this looks at the 'samples' sheet rows
for that trip, groups them by species (matched the same way as reconcile_defining_samples:
exact free-text 'species name' first, then a Genus/(cf.)/Species-or-accepted structured key),
and finds species groups where none of the matching rows have a 'Video Files' entry (i.e. no
footage was ever shot, just a photograph/sighting) and no Sample already exists in our DB for
that species under that trip.

Each such gap gets one draft Sample: kind=species, no video_url/image (so it is saved with a
plain .save(), bypassing full_clean, same convention as the incomplete-record path in the
older import commands), status stays 'pending', and source_metadata carries the spreadsheet
provenance (SampleID(s)/row(s)) so it can be found and completed later with real media.

The extraction (JSON: {'samples': [...], 'Observations': [...]}) is the same one
reconcile_defining_samples takes, produced separately from the personal reference
spreadsheet's 'samples' and 'Observations' sheets.
"""
import json
import re
from collections import defaultdict
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from observations.models import DiveTrip, Sample, Species
from observations.table_transfer import create_backup


def norm(s):
    if not s:
        return ''
    return re.sub(r'\s+', ' ', str(s)).strip().lower()


def xlsx_struct_key(row, ignore_cf=False):
    genus = row.get('accepted_genus') or row.get('Genus')
    sp = row.get('accepted_species') or row.get('Species')
    cf = bool(row.get('cf')) and not ignore_cf
    if not genus:
        return None
    genus = str(genus).strip()
    if sp and str(sp).strip() and str(sp).strip().lower() not in ('spp.', 'spp', 'sp.', 'sp'):
        rest = ('cf. ' if cf else '') + str(sp).strip()
    else:
        nip = row.get('NIPID')
        if nip:
            rest = f'sp. {nip}'
        else:
            return None
    return norm(genus) + '|' + norm(rest)


class Command(BaseCommand):
    help = 'Add draft samples for no-video Boaz/Israel observations missing from our DB. Local import only.'

    def add_arguments(self, parser):
        parser.add_argument('extraction')
        parser.add_argument('--owner', required=True)
        parser.add_argument('--apply', action='store_true')

    def handle(self, *args, **options):
        if settings.PRODUCTION:
            raise CommandError('Local import only.')
        source = json.loads(Path(options['extraction']).read_text())
        owner = get_user_model().objects.get(username=options['owner'])
        observations = {o['קוד_תצפית']: o for o in source['Observations']}
        qualifying = [c for c, o in observations.items()
                      if o.get('צלם') == 'Boaz Liebes' or o.get('מדינה') == 'Israel']

        trips = {c: DiveTrip.objects.filter(code=c).first() for c in qualifying}
        missing_trips = [c for c, t in trips.items() if not t]
        if missing_trips:
            raise CommandError(f'Missing DiveTrip(s) for code(s): {missing_trips}')

        groups = defaultdict(list)
        for r in source['samples']:
            code = r.get('ObservationID')
            if code not in qualifying:
                continue
            key = xlsx_struct_key(r)
            ft = norm(r.get('species name'))
            if not key and not ft:
                continue
            groups[(code, key or ft, ft)].append(r)

        by_struct, by_freetext = defaultdict(list), defaultdict(list)
        for sp in Species.objects.all():
            name = re.sub(r'\s*\([^)]*\)\s*$', '', sp.scientific_name).strip()
            parts = name.split()
            if parts:
                by_struct[norm(parts[0]) + '|' + norm(' '.join(parts[1:]))].append(sp)
            by_freetext[norm(sp.scientific_name)].append(sp)

        to_create, skipped_has_video, skipped_exists, unmatched = [], 0, 0, []
        for (code, key, ft), rows in groups.items():
            if any(r.get('Video Files') for r in rows):
                skipped_has_video += 1
                continue
            cands = by_freetext.get(ft) or (by_struct.get(key) if key else None) or []
            trip = trips[code]
            if not cands:
                unmatched.append({'trip': code, 'name': rows[0].get('species name'), 'rows': len(rows)})
                continue
            sp = cands[0]
            if Sample.objects.filter(species=sp, trip=trip, deleted_at__isnull=True).exists():
                skipped_exists += 1
                continue
            to_create.append((sp, trip, rows))

        self.stdout.write(f'to_create={len(to_create)} skipped_has_video={skipped_has_video} '
                           f'skipped_already_exists={skipped_exists} unmatched_species={len(unmatched)}')

        report = {
            'to_create': [{'species': sp.scientific_name, 'trip': t.code,
                            'excel_sample_ids': [r.get('SampleID') for r in rows]} for sp, t, rows in to_create],
            'unmatched_species': unmatched,
        }

        if not options['apply']:
            self.stdout.write('Dry run only; pass --apply to write changes.')
            return

        backup = create_backup()
        created = []
        with transaction.atomic():
            for sp, trip, rows in to_create:
                item = Sample(
                    owner=owner, kind=Sample.Kind.SPECIES, species=sp, trip=trip,
                    source_metadata={
                        'reconciliation': 'missing_no_video_boaz_or_israel',
                        'excel_sample_ids': [r.get('SampleID') for r in rows],
                        'excel_rows': [r.get('_row') for r in rows],
                    },
                )
                item.save()
                created.append(item.pk)
        report['created_sample_ids'] = created
        path = backup.with_suffix('.no-video-import.json')
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2))
        self.stdout.write(f'Applied. Created {len(created)} draft samples. Report: {path}')
