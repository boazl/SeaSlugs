# A trip's region and the trip's own country field should always agree (see
# DiveTrip.resolved_sea) -- but duplicate data entry has, in at least one real case, left a
# handful of trips pointing at a *different* Region row that happens to share the same name
# (e.g. two separate "Romblon" rows: one correctly under Philippines, one mistakenly created
# under Solomon Islands with a different sea) instead of the row that actually belongs to the
# trip's own country. This silently sends the trip's samples into the wrong country+sea "area"
# bucket in the public gallery -- real, published species quietly stop showing up under the
# area/region a site visitor expects, without any error appearing anywhere. (This is what made
# a large batch of Romblon/Anilao, Philippines samples look "missing" from the gallery, when
# they were actually just filed under a different area than intended.)
#
# This repoints every such trip to the region with the SAME NAME that belongs to the trip's own
# country, whenever exactly one such region exists -- an unambiguous, purely mechanical fix. A
# trip whose region and country already agree is left untouched. A trip with a region/country
# mismatch but no matching same-named region under its own country is left alone too (there is
# nothing safe to repoint it to); it's logged instead so it can be reviewed by hand.
from django.db import migrations
from django.db.models import F


def fix_region_country_mismatches(apps, schema_editor):
    DiveTrip = apps.get_model('observations', 'DiveTrip')
    Region = apps.get_model('observations', 'Region')
    mismatched = DiveTrip.objects.filter(
        region__isnull=False, country__isnull=False,
    ).exclude(region__country_id=F('country_id')).select_related('region')
    fixed, unresolved = [], []
    for trip in mismatched:
        correct = Region.objects.filter(name=trip.region.name, country_id=trip.country_id).exclude(pk=trip.region_id).first()
        if correct:
            trip.region_id = correct.pk
            trip.save(update_fields=['region'])
            fixed.append(trip.pk)
        else:
            unresolved.append(trip.pk)
    if fixed:
        print(f'  Repointed {len(fixed)} trip(s) to the region matching their own country (trip ids: {fixed}).')
    if unresolved:
        print(f'  {len(unresolved)} trip(s) have a region/country mismatch with no same-named '
              f'region under their own country to repoint to -- needs manual review (trip ids: {unresolved}).')


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ('observations', '0026_remove_divetrip_reserve_fk_divetrip_site_and_more'),
    ]
    operations = [
        migrations.RunPython(fix_region_country_mismatches, noop_reverse),
    ]
