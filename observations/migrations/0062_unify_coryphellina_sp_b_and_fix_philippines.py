"""Two small data fixes, both conditional so they are harmless on a database that lacks the rows:

1. The country "פיליפינים" had its English name misspelled "Phillipines" (it shows in English titles).
   Existing species URLs keep their stored slugs -- only the displayed name changes.
2. "Coryphellina sp. B" existed twice: as its own species row, and as the open-ended "Coryphellina sp."
   marked with the undetermined-variant letter B. The observation under the variant row moves to the
   "sp. B" species row, so one population has one page; the now-empty variant area and species row go.
   The retired page address (…-sp-b-…-2) is redirected by data/historical_species_redirects.json.
"""
from django.db import migrations

KEEP_NAME, DUPLICATE_NAME, VARIANT = 'Coryphellina sp. B', 'Coryphellina sp.', 'B'


def fix_country_spelling(apps):
    apps.get_model('observations', 'Country').objects.filter(name_en='Phillipines').update(name_en='Philippines')


def unify_coryphellina_sp_b(apps):
    Species = apps.get_model('observations', 'Species')
    Sample = apps.get_model('observations', 'Sample')
    SpeciesArea = apps.get_model('observations', 'SpeciesArea')
    keep = Species.objects.filter(scientific_name=KEEP_NAME).first()
    duplicate = Species.objects.filter(scientific_name=DUPLICATE_NAME).first()
    if not keep or not duplicate:
        return
    moved = list(Sample.objects.filter(species=duplicate, undetermined_variant=VARIANT).select_related('trip', 'trip__region'))
    if not moved:
        return
    # Every moved observation must land in an existing "sp. B" page of the same country and sea;
    # otherwise leave the data alone rather than guess.
    for sample in moved:
        trip = sample.trip
        if not trip or not trip.region_id or not SpeciesArea.objects.filter(
                species=keep, country_id=trip.country_id, sea_id=trip.region.sea_id, undetermined_variant='').exists():
            return
    Sample.objects.filter(pk__in=[s.pk for s in moved]).update(species=keep, undetermined_variant='')
    SpeciesArea.objects.filter(species=duplicate, undetermined_variant=VARIANT).delete()
    still_used = any(rel.related_model.objects.filter(**{rel.field.name: duplicate}).exists()
                     for rel in duplicate._meta.related_objects)
    if not still_used:
        duplicate.delete()


def forwards(apps, schema_editor):
    fix_country_spelling(apps)
    unify_coryphellina_sp_b(apps)


class Migration(migrations.Migration):
    dependencies = [('observations', '0061_trip_codes')]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
