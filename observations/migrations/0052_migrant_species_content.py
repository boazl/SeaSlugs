# Data only, decided by the site owner: species-page content for the 34 Mediterranean
# migrant (non-indigenous) species, researched from the CIESM Atlas, Sea Slug Forum,
# opistobranquis.info, WoRMS, iNaturalist/GBIF and the primary literature (see each
# species' `sources`). The content lives in observations/data/migrant_species.json,
# keyed by genus + epithet (row ids differ between the local and production databases).
#
# * Years cover the whole Mediterranean: the first year is the earlier of the stored value
#   and the researched one, the last year the later of the two -- the owner's own known
#   records are never overwritten by a later "first" or an earlier "last".
# * Text and size/depth fields are filled only where still blank, so nothing typed in the
#   admin is overwritten (the migration is idempotent).
# * Anteaeolidiella: the Mediterranean animals are A. lurana (Carmona et al. 2013-2014), so
#   the migrant flag moves from A. indica (a valid Indo-Pacific species, kept) to A. lurana.
import json
from decimal import Decimal
from pathlib import Path

from django.db import migrations

DATA = Path(__file__).resolve().parent.parent / 'data' / 'migrant_species.json'
YEARS = ('first_observed_year', 'last_observed_year')
NUMBERS = ('size_from', 'size_to', 'size_max', 'depth_min', 'depth_max')


def run(apps, schema_editor):
    Species = apps.get_model('observations', 'Species')
    Species.objects.filter(genus='Anteaeolidiella', species='indica').update(is_migrant=False)
    for row in json.loads(DATA.read_text(encoding='utf-8')):
        genus, epithet = row.pop('genus'), row.pop('species')
        for sp in Species.objects.filter(genus=genus, species=epithet):
            sp.is_migrant = True
            first, last = row['first_observed_year'], row['last_observed_year']
            if first and (not sp.first_observed_year or first < sp.first_observed_year):
                sp.first_observed_year = first
            if last and (not sp.last_observed_year or last > sp.last_observed_year):
                sp.last_observed_year = last
            for name, value in row.items():
                if name in YEARS or value in (None, ''):
                    continue
                if getattr(sp, name) not in (None, ''):
                    continue
                if name in NUMBERS and name.startswith('size'):
                    value = Decimal(str(value))
                setattr(sp, name, value)
            sp.save()


class Migration(migrations.Migration):

    dependencies = [
        ('observations', '0051_species_page_content'),
    ]

    operations = [
        migrations.RunPython(run, migrations.RunPython.noop),
    ]
