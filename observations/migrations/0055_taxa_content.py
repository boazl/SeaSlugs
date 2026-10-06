# Data only, requested by the site owner: description and identification text (Hebrew and
# English) for every order group and family shown in the gallery, from
# observations/data/taxa_content.json. Order rows are matched by name + sub_order +
# taxonomic_order (one order name can have several rows), families by name. Fields are
# filled only where still blank, so text typed in the admin is never overwritten.
import json
from pathlib import Path

from django.db import migrations

DATA = Path(__file__).resolve().parent.parent / 'data' / 'taxa_content.json'
TEXT = ('name_he', 'description_he', 'description_en', 'identification_he', 'identification_en', 'sources')


def fill(obj, row):
    changed = False
    for name in TEXT:
        value = (row.get(name) or '').strip()
        if value and not getattr(obj, name):
            setattr(obj, name, value)
            changed = True
    if changed:
        obj.save()


def run(apps, schema_editor):
    TaxonOrder = apps.get_model('observations', 'TaxonOrder')
    TaxonFamily = apps.get_model('observations', 'TaxonFamily')
    data = json.loads(DATA.read_text(encoding='utf-8'))
    for row in data['orders']:
        for obj in TaxonOrder.objects.filter(name=row['name'], sub_order=row['sub_order'], taxonomic_order=row['taxonomic_order']):
            fill(obj, row)
    for row in data['families']:
        for obj in TaxonFamily.objects.filter(name=row['name']):
            fill(obj, row)


class Migration(migrations.Migration):

    dependencies = [
        ('observations', '0054_taxon_page_content'),
    ]

    operations = [
        migrations.RunPython(run, migrations.RunPython.noop),
    ]
