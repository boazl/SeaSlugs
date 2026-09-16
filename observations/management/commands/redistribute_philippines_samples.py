"""Redistribute the photographer's own Philippines-trip media (trips V/B/C/H) so each trip
ends up with exactly the species the personal reference spreadsheet says belongs to it.

Many of the photo samples imported earlier (via the folder-image importer, with no per-photo
trip metadata) were bulk-assigned to trip V regardless of which actual expedition they came
from. Per the photographer's own priority rule: species are assigned to V (the most recent
Romblon trip) first; a species not observed on V is assigned to whichever of B, C, H (in that
order) the spreadsheet's 'samples' sheet shows it on.

This only reshuffles Sample rows that are ALREADY on one of V/B/C/H -- it moves each species'
best sample (preferring one with real video/image over a media-less draft) to its correct
trip, and soft-deletes any now-redundant duplicate for that species within the V/B/C/H pool.
SpeciesArea.defining_sample is repointed to the (possibly moved) sample so the public gallery
reflects the correct trip. Species whose spreadsheet entry doesn't match V, B, C, or H at all
are left completely untouched and just reported -- the spreadsheet gives no home for them
within this algorithm.
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

PRIORITY = ['V', 'B', 'C', 'H']


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


def species_keys(scientific_name):
    ft = norm(scientific_name)
    name = re.sub(r'\s*\([^)]*\)\s*$', '', scientific_name).strip()
    parts = name.split()
    struct = norm(parts[0]) + '|' + norm(' '.join(parts[1:])) if parts else None
    struct_nocf = None
    if parts:
        rest = ' '.join(parts[1:])
        rest = re.sub(r'^cf\.?\s+', '', rest, flags=re.I)
        struct_nocf = norm(parts[0]) + '|' + norm(rest)
    return ft, struct, struct_nocf


def pick_survivor(samples, correct_trip_id):
    at_correct = [s for s in samples if s.trip_id == correct_trip_id]
    pool = at_correct if at_correct else samples
    return sorted(pool, key=lambda s: (0 if s.video_url else 1, 0 if s.image else 1, s.created_at))[0]


class Command(BaseCommand):
    help = 'Redistribute V/B/C/H Philippines samples to their correct trip. Local import only.'

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
        missing = [c for c, t in trips.items() if not t]
        if missing:
            raise CommandError(f'Missing DiveTrip(s) for code(s): {missing}')
        trip_ids = {c: t.id for c, t in trips.items()}

        ft_by_code, struct_by_code, struct_nocf_by_code = defaultdict(set), defaultdict(set), defaultdict(set)
        for r in source['samples']:
            code = r.get('ObservationID')
            if code not in PRIORITY:
                continue
            ft = r.get('species name')
            if ft:
                ft_by_code[code].add(norm(ft))
            sk = xlsx_struct_key(r)
            if sk:
                struct_by_code[code].add(sk)
            sk2 = xlsx_struct_key(r, ignore_cf=True)
            if sk2:
                struct_nocf_by_code[code].add(sk2)

        pool = list(Sample.objects.filter(trip_id__in=trip_ids.values(), deleted_at__isnull=True).select_related('species'))
        groups = defaultdict(list)
        no_species = []
        for s in pool:
            if s.species_id:
                groups[s.species_id].append(s)
            else:
                no_species.append(s)

        moved, deduped, orphans, unchanged = [], [], [], []
        plan = []  # (species_id, survivor, correct_trip_code, others_to_remove)
        for species_id, samples in groups.items():
            sp = samples[0].species
            ft, sk, sk_nocf = species_keys(sp.scientific_name)
            correct_code = None
            for code in PRIORITY:
                if ft in ft_by_code.get(code, set()):
                    correct_code = code
                    break
            if not correct_code:
                for code in PRIORITY:
                    if sk and sk in struct_by_code.get(code, set()):
                        correct_code = code
                        break
            if not correct_code:
                for code in PRIORITY:
                    if sk_nocf and sk_nocf in struct_nocf_by_code.get(code, set()):
                        correct_code = code
                        break
            if not correct_code:
                orphans.append({'species': sp.scientific_name, 'sample_ids': [s.id for s in samples],
                                 'current_trips': sorted(set(s.trip.code for s in samples))})
                continue
            survivor = pick_survivor(samples, trip_ids[correct_code])
            others = [s for s in samples if s.id != survivor.id]
            plan.append((species_id, sp.scientific_name, survivor, correct_code, others))
            if survivor.trip_id != trip_ids[correct_code]:
                moved.append({'species': sp.scientific_name, 'sample_id': survivor.id,
                               'from_trip': survivor.trip.code, 'to_trip': correct_code})
            else:
                unchanged.append(sp.scientific_name)
            for o in others:
                deduped.append({'species': sp.scientific_name, 'removed_sample_id': o.id, 'trip': o.trip.code})

        self.stdout.write(f'species_groups={len(groups)} moved={len(moved)} unchanged_already_correct={len(unchanged)} '
                           f'duplicates_to_remove={len(deduped)} orphans(no V/B/C/H match)={len(orphans)} no_species_samples={len(no_species)}')
        by_trip_after = defaultdict(int)
        for species_id, name, survivor, code, others in plan:
            by_trip_after[code] += 1
        self.stdout.write('resulting counts per trip: ' + ', '.join(f'{c}={by_trip_after.get(c,0)}' for c in PRIORITY))

        report = {
            'moved': moved,
            'duplicates_removed': deduped,
            'orphans_left_untouched': orphans,
            'resulting_counts': dict(by_trip_after),
        }

        if not options['apply']:
            self.stdout.write('Dry run only; pass --apply to write changes.')
            return

        backup = create_backup()
        with transaction.atomic():
            for species_id, name, survivor, code, others in plan:
                if survivor.trip_id != trip_ids[code]:
                    survivor.trip_id = trip_ids[code]
                    survivor.save(update_fields=['trip'])
                for o in others:
                    if not o.deleted_at:
                        o.soft_delete(owner)
                area = SpeciesArea.objects.filter(species_id=species_id).first()
                if area and area.defining_sample_id != survivor.id:
                    area.defining_sample = survivor
                    area.save(update_fields=['defining_sample'])

        path = backup.with_suffix('.redistribute.json')
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2))
        self.stdout.write(f'Applied. Moved {len(moved)}, removed {len(deduped)} duplicates. Report: {path}')
