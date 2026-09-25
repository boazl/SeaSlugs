# Convenience data migration: pre-fill the new Reserve/Photographer lookup tables with every
# distinct, non-blank value already sitting in DiveTrip.reserve / DiveTrip.photographer (free
# text), so those values are immediately pickable from the new dropdowns instead of everyone
# having to retype them once through the admin's "+" button. Existing trips are left exactly
# as they are -- their reserve_fk/photographer_fk stay unset; this only seeds the tables.
from django.db import migrations


def prepopulate(apps, schema_editor):
    DiveTrip = apps.get_model('observations', 'DiveTrip')
    Reserve = apps.get_model('observations', 'Reserve')
    Photographer = apps.get_model('observations', 'Photographer')

    reserves = {v.strip() for v in DiveTrip.objects.exclude(reserve='').values_list('reserve', flat=True) if v.strip()}
    for name in sorted(reserves):
        Reserve.objects.get_or_create(name=name)

    photographers = {v.strip() for v in DiveTrip.objects.exclude(photographer='').values_list('photographer', flat=True) if v.strip()}
    for name in sorted(photographers):
        Photographer.objects.get_or_create(name=name)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ('observations', '0024_photographer_reserve_divetrip_sea_and_more'),
    ]
    operations = [
        migrations.RunPython(prepopulate, noop_reverse),
    ]
