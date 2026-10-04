# Data only (the tables are created in 0042): the starting values of the two reference tables
# behind Sample.identification_qualifier / Sample.life_stage -- cf., aff. and juv. -- plus a row
# for any other value a sample already carries, so no existing sample points at a missing row.
from django.db import migrations

QUALIFIERS = [('cf.', 'דומה ל…', 'compare with (cf.)'), ('aff.', 'קרוב ל…', 'close to (affinis)')]
LIFE_STAGES = [('juv.', 'צעיר', 'juvenile')]


def seed(apps, schema_editor):
    Sample = apps.get_model('observations', 'Sample')
    for model_name, field, rows in (('IdentificationQualifier', 'identification_qualifier', QUALIFIERS), ('LifeStage', 'life_stage', LIFE_STAGES)):
        Model = apps.get_model('observations', model_name)
        for code, name, name_en in rows:
            Model.objects.get_or_create(code=code, defaults={'name': name, 'name_en': name_en})
        for code in Sample.objects.exclude(**{field: ''}).values_list(field, flat=True).distinct():
            Model.objects.get_or_create(code=code, defaults={'name': code})


class Migration(migrations.Migration):

    dependencies = [
        ('observations', '0042_qualifier_and_life_stage_tables'),
    ]

    operations = [
        # The reverse leaves the rows in place (the tables are dropped by reversing 0042).
        migrations.RunPython(seed, migrations.RunPython.noop),
    ]
