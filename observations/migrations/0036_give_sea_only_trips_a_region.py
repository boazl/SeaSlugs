# Step 1 of 2 removing DiveTrip.sea in favour of region.sea (Region.sea is the single source
# of truth for a trip's sea).
#
# A trip that has observations, a country and a sea but NO region would lose its sea (and so
# its species-area / gallery entries) once the field is dropped. Give such a trip a region:
# the one existing region of that country+sea when there is exactly one, otherwise a region
# named after the sea itself (created if needed). Trips without observations, or without a
# country, are left as they are -- they contributed nothing to the gallery. Nothing is
# deleted; the column itself is dropped in the next migration (data and schema are split
# because PostgreSQL refuses to mix them in one transaction).

from django.db import migrations


def give_sea_only_trips_a_region(apps, schema_editor):
    DiveTrip = apps.get_model('observations', 'DiveTrip')
    Region = apps.get_model('observations', 'Region')
    Sample = apps.get_model('observations', 'Sample')
    for trip in DiveTrip.objects.filter(region__isnull=True, sea__isnull=False, country__isnull=False).select_related('sea'):
        if not Sample.objects.filter(trip_id=trip.pk).exists():
            continue
        regions = list(Region.objects.filter(country_id=trip.country_id, sea_id=trip.sea_id).order_by('pk')[:2])
        if len(regions) == 1:
            region = regions[0]
        else:
            region = Region.objects.filter(country_id=trip.country_id, sea_id=trip.sea_id, name=trip.sea.name).first() or \
                Region.objects.create(country_id=trip.country_id, sea_id=trip.sea_id, name=trip.sea.name, name_en=trip.sea.name_en)
        DiveTrip.objects.filter(pk=trip.pk).update(region=region)


def restore_trip_seas(apps, schema_editor):
    """Reverse: give every trip with a region back its own sea (the region's)."""
    DiveTrip = apps.get_model('observations', 'DiveTrip')
    for trip in DiveTrip.objects.filter(region__isnull=False, sea__isnull=True).select_related('region'):
        DiveTrip.objects.filter(pk=trip.pk).update(sea_id=trip.region.sea_id)


class Migration(migrations.Migration):

    dependencies = [
        ('observations', '0035_remove_trip_photographer'),
    ]

    operations = [
        migrations.RunPython(give_sea_only_trips_a_region, restore_trip_seas),
    ]
