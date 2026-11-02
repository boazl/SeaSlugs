"""Remove the stale gallery area "Goniobranchus geminus · Djibouti · Red Sea - Gulf of Eilat".

Djibouti is not on the Gulf of Eilat: the area was left behind when trip W (Djibouti 2022) was moved to the
Bab el-Mandeb region, and it kept pointing at that trip's observation, so genus/family/order pages showed the
species twice. Its observation belongs to the Bab el-Mandeb area. The old address 301-redirects there
(data/historical_species_redirects.json). Safe in both environments: the row is removed only if it has no
observation of its own (none of the species' published observations is in Djibouti + Gulf of Eilat)."""
from django.db import migrations

SLUG = 'goniobranchus-geminus-djibouti-red-sea-gulf-of-aqaba'


def forwards(apps, schema_editor):
    SpeciesArea = apps.get_model('observations', 'SpeciesArea')
    Sample = apps.get_model('observations', 'Sample')
    for area in SpeciesArea.objects.filter(slug=SLUG):
        own = Sample.objects.filter(kind='species', species_id=area.species_id, deleted_at__isnull=True,
                                    trip__country_id=area.country_id, trip__region__sea_id=area.sea_id,
                                    undetermined_variant=area.undetermined_variant).exists()
        if not own:
            area.delete()


class Migration(migrations.Migration):
    dependencies = [('observations', '0084_local_video_paths')]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
