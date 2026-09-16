"""After redistribute_philippines_samples reshuffles existing media onto its correct trip,
some spreadsheet-listed species for V/B/C/H still have no Sample at all in our DB (never
imported under any trip). This creates a media-less draft placeholder Sample for each such
gap, so every trip's sample count can reach exactly the spreadsheet's count once real photos
or videos are attached later.

Species are matched against our catalog the same way as the other reconciliation commands
(exact free-text 'species name' first, then a Genus/(cf.)/Species-or-accepted structured key,
ignoring a trailing '?' uncertainty marker and a stray cf. qualifier as a last resort).
Free-text entries that still don't match any catalog species (unidentified placeholders like
"tiny white") are reported and skipped -- there is nothing to attach them to.
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

PRIORITY = ['V', 'B', 'C', 'H']


def norm(s):
    if not s:
        return ''
    return re.sub(r'\s+', ' ', str(s)).strip().lower()


def clean_freetext(s):
    return norm(re.sub(r'[?!]+$', '', str(s or '')).strip())


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
    help = 'Create draft placeholder samples for V/B/C/H species missing from our DB. Local import only.'

    def add_arguments(self, parser):
        parser.add_argument('extraction')
        parser.add_argument('--owner', required=True)
        parser.add_argument('--apply', action='store_true')

    def handle(self, *args, **options):
        if settings.PRODUCTION:
            raise CommandError('Local import only.')
        source = json.loads(Path(options['extraction']).read_text())
        owner = get_user_model().objects.get(username=options['owner'])
        trips = {c: DiveTrip.objects.filter(code=c).first() for c in PRIORITY}
        missing_trips = [c for c, t in trips.items() if not t]
        if missing_trips:
            raise CommandError(f'Missing DiveTrip(s) for code(s): {missing_trips}')

        groups = defaultdict(list)
        for r in source['samples']:
            code = r.get('ObservationID')
            if code not in PRIORITY:
                continue
            ft = clean_freetext(r.get('species name'))
            if not ft:
                continue
            groups[(code, ft)].append(r)

        by_ft, by_struct, by_struct_nocf = defaultdict(list), defaultdict(list), defaultdict(list)
        for sp in Species.objects.all():
            by_ft[norm(sp.scientific_name)].append(sp)
            name = re.sub(r'\s*\([^)]*\)\s*$', '', sp.scientific_name).strip()
            parts = name.split()
            if parts:
                sk = norm(parts[0]) + '|' + norm(' '.join(parts[1:]))
                by_struct[sk].append(sp)
                rest_nocf = re.sub(r'^cf\.?\s+', '', ' '.join(parts[1:]), flags=re.I)
                by_struct_nocf[norm(parts[0]) + '|' + norm(rest_nocf)].append(sp)

        to_create, unmatched = [], []
        for (code, ft), rows in groups.items():
            trip = trips[code]
            row = rows[0]
            cands = by_ft.get(ft)
            if not cands:
                sk = xlsx_struct_key(row)
                cands = by_struct.get(sk) if sk else None
            if not cands:
                sk2 = xlsx_struct_key(row, ignore_cf=True)
                cands = by_struct_nocf.get(sk2) if sk2 else None
            if not cands:
                unmatched.append({'trip': code, 'name': row.get('species name')})
                continue
            sp = cands[0]
            if Sample.objects.filter(species=sp, trip=trip, deleted_at__isnull=True).exists():
                continue
            to_create.append((sp, trip, rows))

        self.stdout.write(f'to_create={len(to_create)} unmatched_to_catalog={len(unmatched)}')
        from collections import Counter
        self.stdout.write('by trip: ' + str(Counter(t.code for _, t, _ in to_create)))

        report = {
            'to_create': [{'species': sp.scientific_name, 'trip': t.code,
                            'excel_sample_ids': [r.get('SampleID') for r in rows]} for sp, t, rows in to_create],
            'unmatched_to_catalog': unmatched,
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
                        'reconciliation': 'philippines_trip_gap_fill',
                        'excel_sample_ids': [r.get('SampleID') for r in rows],
                        'excel_rows': [r.get('_row') for r in rows],
                    },
                )
                item.save()
                created.append(item.pk)
        report['created_sample_ids'] = created
        path = backup.with_suffix('.gap-fill.json')
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2))
        self.stdout.write(f'Applied. Created {len(created)} draft samples. Report: {path}')
