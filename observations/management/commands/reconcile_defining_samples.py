"""Reconcile gallery species against the personal reference spreadsheet's 'samples' sheet.

For every species currently shown in the gallery (i.e. has a SpeciesArea row), walk the
photographer's own trip codes in priority order V (Romblon 2026) -> B (Anilao 2017) ->
C (Anilao 2023) -> H (Anilao 2025). The first trip in that order under which the species
appears in the spreadsheet is the trip that should define it:

  * If a real (media-having) Sample already exists in our DB for that species under that
    trip, it becomes SpeciesArea.defining_sample (repoint).
  * If no such Sample exists yet, a draft placeholder Sample is created under that trip so
    the correct attribution is recorded (source_metadata carries the spreadsheet row/SampleID
    for provenance) -- saved with plain .save() (bypassing full_clean, matching the existing
    project convention for incomplete legacy-style records) since it has no video/image yet.
    The current defining_sample is left untouched so the public gallery entry keeps working
    until real media is attached and someone repoints it (e.g. via the admin).
  * Species not found under any of V/B/C/H are left completely untouched and just reported,
    since the spreadsheet gives no guidance on what to do with them.

The extraction (JSON: {'samples': [...], 'Observations': [...]}) is produced separately from
the personal reference spreadsheet's 'samples' and 'Observations' sheets, one dict per row
with the same keys as the sheet's columns (plus '_row').
"""
import json
import re
from collections import defaultdict
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from observations.models import DiveTrip, Sample, SpeciesArea
from observations.table_transfer import create_backup

TRIP_CODES = ['V', 'B', 'C', 'H']


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


def species_struct_key(scientific_name, ignore_cf=False):
    name = re.sub(r'\s*\([^)]*\)\s*$', '', scientific_name).strip()
    parts = name.split()
    if not parts:
        return None
    genus = parts[0]
    rest = ' '.join(parts[1:])
    if ignore_cf:
        rest = re.sub(r'^cf\.?\s+', '', rest, flags=re.I)
    return norm(genus) + '|' + norm(rest)


def pick_best(qs):
    lst = list(qs)
    lst.sort(key=lambda s: (0 if s.image else 1, s.created_at))
    return lst[0] if lst else None


class Command(BaseCommand):
    help = 'Reconcile SpeciesArea.defining_sample against the V/B/C/H trip priority order. Local import only.'

    def add_arguments(self, parser):
        parser.add_argument('extraction')
        parser.add_argument('--owner', required=True)
        parser.add_argument('--apply', action='store_true')

    def handle(self, *args, **options):
        if settings.PRODUCTION:
            raise CommandError('Local import only.')
        source = json.loads(Path(options['extraction']).read_text())
        owner = get_user_model().objects.get(username=options['owner'])

        trips = {code: DiveTrip.objects.filter(code=code).first() for code in TRIP_CODES}
        missing_trips = [c for c, t in trips.items() if not t]
        if missing_trips:
            raise CommandError(f'Missing DiveTrip(s) for code(s): {missing_trips}')

        rows_freetext, rows_struct, rows_struct_nocf = defaultdict(list), defaultdict(list), defaultdict(list)
        for r in source['samples']:
            code = r.get('ObservationID')
            if not code:
                continue
            ft = r.get('species name')
            if ft:
                rows_freetext[(code, norm(ft))].append(r)
            sk = xlsx_struct_key(r)
            if sk:
                rows_struct[(code, sk)].append(r)
            sk2 = xlsx_struct_key(r, ignore_cf=True)
            if sk2:
                rows_struct_nocf[(code, sk2)].append(r)

        repoint, create_stub, already_correct, unmatched = [], [], [], []
        areas = SpeciesArea.objects.select_related('species', 'defining_sample', 'defining_sample__trip').all()
        seen = set()
        for area in areas:
            sp = area.species
            if sp.id in seen:
                continue
            seen.add(sp.id)
            ft_key = norm(sp.scientific_name)
            sk = species_struct_key(sp.scientific_name)
            sk_nocf = species_struct_key(sp.scientific_name, ignore_cf=True)
            found, matched_rows = None, None
            for code in TRIP_CODES:
                if (code, ft_key) in rows_freetext:
                    found, matched_rows = code, rows_freetext[(code, ft_key)]
                    break
            if not found:
                for code in TRIP_CODES:
                    if sk and (code, sk) in rows_struct:
                        found, matched_rows = code, rows_struct[(code, sk)]
                        break
            if not found:
                for code in TRIP_CODES:
                    if sk_nocf and (code, sk_nocf) in rows_struct_nocf:
                        found, matched_rows = code, rows_struct_nocf[(code, sk_nocf)]
                        break
            if not found:
                unmatched.append(area)
                continue
            trip = trips[found]
            best = pick_best(Sample.objects.filter(species=sp, trip=trip, deleted_at__isnull=True))
            if best:
                if area.defining_sample_id != best.id:
                    repoint.append((area, trip, best))
                else:
                    already_correct.append(area)
            else:
                create_stub.append((area, sp, trip, matched_rows))

        self.stdout.write(f'already_correct={len(already_correct)} repoint={len(repoint)} '
                           f'create_stub={len(create_stub)} unmatched(not in V/B/C/H)={len(unmatched)}')

        report = {
            'repoint': [{'species': a.species.scientific_name, 'trip': t.code, 'sample_id': s.id} for a, t, s in repoint],
            'create_stub': [{'species': sp.scientific_name, 'trip': t.code, 'excel_sample_ids': [r.get('SampleID') for r in rows]} for a, sp, t, rows in create_stub],
            'unmatched': [a.species.scientific_name for a in unmatched],
        }

        if not options['apply']:
            self.stdout.write('Dry run only; pass --apply to write changes.')
            return

        backup = create_backup()
        with transaction.atomic():
            # Trips B and H have no country/region of their own in the DB yet; both are the
            # same Anilao, Philippines dive site as trip C, so backfill from there.
            trip_c = trips['C']
            for code in ('B', 'H'):
                t = trips[code]
                changed = False
                if not t.country_id and trip_c.country_id:
                    t.country_id = trip_c.country_id
                    changed = True
                if not t.region_id and trip_c.region_id:
                    t.region_id = trip_c.region_id
                    changed = True
                if changed:
                    t.save(update_fields=['country', 'region'])

            for area, trip, sample in repoint:
                area.defining_sample = sample
                area.save(update_fields=['defining_sample'])

            created = []
            for area, sp, trip, rows in create_stub:
                item = Sample(
                    owner=owner, kind=Sample.Kind.SPECIES, species=sp, trip=trip,
                    source_metadata={
                        'reconciliation': 'defining_sample_trip_priority',
                        'excel_sample_ids': [r.get('SampleID') for r in rows],
                        'excel_rows': [r.get('_row') for r in rows],
                        'video_files': [r.get('Video Files') for r in rows if r.get('Video Files')],
                    },
                )
                item.save()
                created.append(item.pk)
            report['created_sample_ids'] = created

        path = backup.with_suffix('.reconcile.json')
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2))
        self.stdout.write(f'Applied. Repointed {len(repoint)}, created {len(created)} draft samples. Report: {path}')
