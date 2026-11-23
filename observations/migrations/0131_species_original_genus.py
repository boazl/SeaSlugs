"""Species.original_genus: the genus a species was first described in. ICZN: the authority stands in parentheses
exactly when the species now belongs to another genus -- recording the original genus lets the parentheses be checked
(Species.author_parentheses_ok, manage.py check_author_parentheses) instead of copied.

Filled from observations/data/original_genera.json (built 2026-11-23 from WoRMS, for the catalogue's accepted species
names: the genus of the "original combination" among the species' synonyms, or -- when there is none and WoRMS's
authority has no parentheses -- the species' own genus; then, for gallery species WoRMS does not settle, the genus of
the original name in original_descriptions.json, and four set by hand: Dendrodoris tuberculosa (Doris), Longibranchus
putnami (Eubranchus), Phestilla minor (Phestilla), Samla riwo (Flabellina); the rest are left empty). Only empty values
are filled. The check found three authors that differ from WoRMS's parentheses; they take WoRMS's (the catalogue rule):
Cylichna villersii (Audouin, 1826); Doris bertheloti d'Orbigny, 1839; Volvatella elioti Evans, 1950."""
import json
from pathlib import Path

from django.db import migrations, models

AUTHORS = {  # name: (catalogue's author, WoRMS's parentheses)
    'Cylichna villersii': ('Audouin, 1826', '(Audouin, 1826)'),
    'Doris bertheloti': ("(d'Orbigny, 1839)", "d'Orbigny, 1839"),
    'Volvatella elioti': ('(Evans, 1950)', 'Evans, 1950'),
}


def fill(apps, schema_editor):
    Species = apps.get_model('observations', 'Species')
    genera = json.loads((Path(__file__).resolve().parent.parent / 'data' / 'original_genera.json').read_text(encoding='utf-8'))
    for species in Species.objects.filter(original_genus='', scientific_name__in=list(genera)):
        Species.objects.filter(pk=species.pk).update(original_genus=genera[species.scientific_name])
    for name, (old, new) in AUTHORS.items():
        Species.objects.filter(scientific_name=name, author=old).update(author=new)


class Migration(migrations.Migration):

    dependencies = [
        ('observations', '0130_aegires_sp12_and_cf_gracilis'),
    ]

    operations = [
        migrations.AddField(
            model_name='species',
            name='original_genus',
            field=models.CharField(blank=True, help_text='הסוג שבו תואר המין לראשונה. לפי ICZN: מחבר בסוגריים רק אם המין עבר מאז לסוג אחר.', max_length=150, verbose_name='סוג מקורי (Original genus)'),
        ),
        migrations.RunPython(fill, migrations.RunPython.noop),
    ]
