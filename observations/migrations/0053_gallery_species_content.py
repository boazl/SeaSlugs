# Data only, requested by the site owner: species-page content (description,
# identification, similar species, habitat, diet, native range, size, depth, sources -- in
# Hebrew and English) for the 171 identified, non-migrant species shown in the gallery.
# Researched from Sea Slug Forum, seaslug.world, Sea Slugs of Hawaii, opistobranquis.info,
# WoRMS and the original descriptions/revisions (see each species' `sources`). sp./cf./aff.
# entries are deliberately left out (their identity is open).
#
# The content lives in observations/data/gallery_species_content.json, keyed by genus +
# epithet. Fields are filled only where still blank, so nothing typed in the admin is
# overwritten; the migration is idempotent and does not touch migrant flags or years.
import json
from decimal import Decimal
from pathlib import Path

from django.db import migrations

DATA = Path(__file__).resolve().parent.parent / 'data' / 'gallery_species_content.json'
SIZES = ('size_from', 'size_to', 'size_max')


def run(apps, schema_editor):
    Species = apps.get_model('observations', 'Species')
    for row in json.loads(DATA.read_text(encoding='utf-8')):
        genus, epithet = row.pop('genus'), row.pop('species')
        for sp in Species.objects.filter(genus=genus, species=epithet):
            changed = False
            for name, value in row.items():
                if value in (None, '') or getattr(sp, name) not in (None, ''):
                    continue
                if name in SIZES:
                    value = Decimal(str(value))
                setattr(sp, name, value)
                changed = True
            # Keep the size fields consistent with Species.clean(): drop a max that a
            # pre-existing typical range would make invalid.
            if sp.size_max is not None and sp.size_to is not None and sp.size_max < sp.size_to:
                sp.size_max = None
            if sp.size_from is not None and sp.size_to is not None and sp.size_from > sp.size_to:
                sp.size_from = None
            if changed:
                sp.save()


class Migration(migrations.Migration):

    dependencies = [
        ('observations', '0052_migrant_species_content'),
    ]

    operations = [
        migrations.RunPython(run, migrations.RunPython.noop),
    ]
