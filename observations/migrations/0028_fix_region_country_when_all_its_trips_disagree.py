# Companion to 0027. That migration repoints a trip to an ALTERNATE region with the same name
# that already exists under the trip's own country -- which is what fixed the live/production
# database, since it had duplicate "Romblon"/"Anilao" region rows (one under each country). On
# a database with only ONE such region row (tagged with the wrong country altogether, no
# duplicate to repoint to), 0027 correctly declines to touch it, and reports it as needing
# manual review.
#
# This migration handles that second case safely and generically: a Region whose own
# `country` field doesn't match ANY of the countries used by the trips that reference it,
# where every one of those trips agrees with each other on a single different country. That
# unanimous agreement from the trip side (which the user edits directly and far more often
# than the shared lookup tables) is the safe signal that the *region's* own country field is
# the actual mistake, so it's corrected to match -- rather than guessing per trip. A region
# whose referencing trips give conflicting countries (some agree with it, some don't, or they
# disagree with each other) is left alone; that's a real human decision, not a mechanical one.
from django.db import migrations


def fix_region_country_when_its_trips_unanimously_disagree(apps, schema_editor):
    Region = apps.get_model('observations', 'Region')
    DiveTrip = apps.get_model('observations', 'DiveTrip')
    fixed = []
    for region in Region.objects.all():
        trip_countries = set(
            DiveTrip.objects.filter(region=region, country__isnull=False)
            .values_list('country_id', flat=True).distinct()
        )
        if len(trip_countries) == 1 and region.country_id not in trip_countries:
            (new_country_id,) = trip_countries
            region.country_id = new_country_id
            region.save(update_fields=['country'])
            fixed.append(region.pk)
    if fixed:
        print(f'  Corrected {len(fixed)} region(s) whose own country disagreed with every '
              f'trip that uses them (region ids: {fixed}).')


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ('observations', '0027_fix_trips_pointing_at_a_region_under_the_wrong_country'),
    ]
    operations = [
        migrations.RunPython(fix_region_country_when_its_trips_unanimously_disagree, noop_reverse),
    ]
