import uuid
from collections import defaultdict
from django.db import migrations


def backfill(apps, schema_editor):
    DiveTrip = apps.get_model('observations', 'DiveTrip')
    Sample = apps.get_model('observations', 'Sample')
    SpeciesArea = apps.get_model('observations', 'SpeciesArea')

    # 1) Backfill DiveTrip.country/region from its samples' existing country/region FKs,
    #    when the trip doesn't have its own value yet and all of its samples agree.
    for trip in DiveTrip.objects.all():
        samples = list(Sample.objects.filter(trip=trip, deleted_at__isnull=True))
        if not samples:
            continue
        countries = {s.country_id for s in samples if s.country_id}
        regions = {s.region_id for s in samples if s.region_id}
        changed = False
        if trip.country_id is None and len(countries) == 1:
            trip.country_id = next(iter(countries))
            changed = True
        if trip.region_id is None and len(regions) == 1:
            trip.region_id = next(iter(regions))
            changed = True
        if changed:
            trip.save()

    # 2) A DiveTrip is meant to be a single dated excursion. Split any trip whose samples
    #    span more than one distinct (year, month): the earliest (year, month) stays on the
    #    original trip, and every other (year, month) group gets its own new DiveTrip
    #    (cloned from the original) with its samples reassigned to it.
    for trip in list(DiveTrip.objects.all()):
        samples = list(Sample.objects.filter(trip=trip, deleted_at__isnull=True))
        if not samples:
            continue
        yms = sorted({(s.year, s.month) for s in samples if s.year is not None})
        if len(yms) <= 1:
            if trip.year is None and yms:
                trip.year, trip.month = yms[0]
                trip.save()
            continue
        keep_year, keep_month = yms[0]
        trip.year, trip.month = keep_year, keep_month
        trip.save()
        for year, month in yms[1:]:
            clone = DiveTrip.objects.create(
                code=str(uuid.uuid4()), title=trip.title, source_sort=trip.source_sort,
                year=year, month=month, start_day=None, duration_days=None,
                country_name=trip.country_name, region_name=trip.region_name,
                reserve=trip.reserve, sea_name=trip.sea_name, photographer=trip.photographer,
                species_count=None, source_metadata={},
                country_id=trip.country_id, region_id=trip.region_id,
            )
            Sample.objects.filter(trip=trip, year=year, month=month, deleted_at__isnull=True).update(trip=clone)

    # 3) Build SpeciesArea rows for every (species, country, sea) among currently published
    #    species-kind samples, choosing a defining_sample: prefer one with an uploaded image
    #    over a video-only one, tie-broken by whichever was created first.
    groups = defaultdict(list)
    qs = Sample.objects.filter(
        kind='species', status='published', deleted_at__isnull=True,
        species__isnull=False, country__isnull=False, region__isnull=False,
    ).select_related('region', 'region__sea').order_by('created_at', 'pk')
    for s in qs:
        key = (s.species_id, s.country_id, s.region.sea_id)
        groups[key].append(s)
    for (species_id, country_id, sea_id), items in groups.items():
        with_image = [s for s in items if s.image]
        defining = (with_image or items)[0]
        SpeciesArea.objects.get_or_create(
            species_id=species_id, country_id=country_id, sea_id=sea_id,
            defaults={'defining_sample_id': defining.pk},
        )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ('observations', '0011_species_area_and_trip_location'),
    ]
    operations = [
        migrations.RunPython(backfill, noop),
    ]
