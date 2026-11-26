"""Observation #502 (Phyllidia cf. alyta, Papua New Guinea 1998) is a juvenile -- its photo label says "juv." -- but the
life stage was not recorded; it is set, so the species page and cards show "juv." as the label does. Safe in both
environments: found by transfer id, only while empty."""
from django.db import migrations

SAMPLE = '7fcf3c06-5e32-49fe-bca2-8be4dfc00904'


def forwards(apps, schema_editor):
    Sample = apps.get_model('observations', 'Sample')
    LifeStage = apps.get_model('observations', 'LifeStage')
    if LifeStage.objects.filter(code='juv.').exists():
        Sample.objects.filter(transfer_id=SAMPLE, life_stage='').update(life_stage='juv.')


class Migration(migrations.Migration):
    dependencies = [('observations', '0135_goniodoridella_66_cf')]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
