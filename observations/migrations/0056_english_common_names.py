# Data only, requested by the site owner: English common names for gallery taxa, taken
# only where a reputable source attests one (iNaturalist, WoRMS vernaculars, Wikipedia);
# taxa with no established English name are left blank. From
# observations/data/english_names.json; fills name_en only where it is still empty.
import json
from pathlib import Path

from django.db import migrations

DATA = Path(__file__).resolve().parent.parent / 'data' / 'english_names.json'


def run(apps, schema_editor):
    data = json.loads(DATA.read_text(encoding='utf-8'))
    Species = apps.get_model('observations', 'Species')
    for model, rank in (('TaxonFamily', 'family'), ('TaxonGenus', 'genus')):
        Model = apps.get_model('observations', model)
        for name, name_en in data[rank].items():
            Model.objects.filter(name=name, name_en='').update(name_en=name_en)
    for name, name_en in data['species'].items():
        genus, _, epithet = name.partition(' ')
        Species.objects.filter(genus=genus, species=epithet, name_en='').update(name_en=name_en)


class Migration(migrations.Migration):

    dependencies = [
        ('observations', '0055_taxa_content'),
    ]

    operations = [
        migrations.RunPython(run, migrations.RunPython.noop),
    ]
