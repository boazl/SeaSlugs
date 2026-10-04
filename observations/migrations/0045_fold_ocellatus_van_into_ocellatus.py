# Data only. The catalog row "Plakobranchus ocellatus-van" came in from the original species
# list with the first word of the author ("van Hasselt, 1824" -- van is part of the
# researcher's name) glued onto the epithet. It is the same species as "Plakobranchus
# ocellatus", so it is folded into that row exactly like the cf. rows in 0044: its samples
# and (redundant or moved) SpeciesArea rows go to the plain species, catalog fields the plain
# row lacks are copied over, the plain row gets the author "van Hasselt, 1824" when it has
# none, and the wrong row is deleted. Without a plain twin the row is just renamed.
# Idempotent; the reverse does nothing (restore from the backup to undo).
from django.db import migrations

GENUS, WRONG, RIGHT, AUTHOR = 'Plakobranchus', 'ocellatus-van', 'ocellatus', 'van Hasselt, 1824'
KEEP = {'id', 'genus', 'species', 'scientific_name', 'full_species_name_with_order'}


def fold(apps, schema_editor):
    Species = apps.get_model('observations', 'Species')
    Sample = apps.get_model('observations', 'Sample')
    SpeciesArea = apps.get_model('observations', 'SpeciesArea')
    blank = lambda v: v in ('', None)
    for sp in list(Species.objects.filter(genus=GENUS, species=WRONG)):
        twin = Species.objects.filter(genus=GENUS, species=RIGHT).exclude(pk=sp.pk).first()
        if twin is None:
            sp.species, sp.scientific_name = RIGHT, f'{GENUS} {RIGHT}'
            if blank(sp.author): sp.author = AUTHOR
            sp.save()
            continue
        for name in [f.name for f in Species._meta.concrete_fields if f.name not in KEEP]:
            if blank(getattr(twin, name)) and not blank(getattr(sp, name)): setattr(twin, name, getattr(sp, name))
        if blank(twin.author): twin.author = AUTHOR
        if blank(twin.full_species_name_with_order) and not blank(twin.phylogenetic_order):
            twin.full_species_name_with_order = f'{twin.phylogenetic_order}-{twin.genus} {twin.species} {twin.formatted_author or twin.author}'.strip()
        twin.save()
        Sample.objects.filter(species=sp).update(species=twin)
        for area in SpeciesArea.objects.filter(species=sp):
            same = SpeciesArea.objects.filter(species=twin, country_id=area.country_id, sea_id=area.sea_id,
                                              undetermined_variant=area.undetermined_variant).exists()
            if same: area.delete()
            else:
                area.species = twin
                area.save(update_fields=['species'])
        sp.delete()


class Migration(migrations.Migration):

    dependencies = [
        ('observations', '0044_fold_cf_species_into_catalog_species'),
    ]

    operations = [
        migrations.RunPython(fold, migrations.RunPython.noop),
    ]
