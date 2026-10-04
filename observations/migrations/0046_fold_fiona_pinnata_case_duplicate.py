# Data only. The catalog has "Fiona Pinnata" (capital P, no author, the Mediterranean card)
# next to the reference-list species "Fiona pinnata (Eschscholtz, 1831)" -- a case-typo
# duplicate. Fold the typo row into the proper one the same way 0044/0045 do: samples and
# SpeciesArea rows move to it (a redundant area row is dropped), catalog fields the proper
# row lacks are copied over, then the typo row is deleted. Without a proper twin the row is
# just renamed. Idempotent; the reverse does nothing (restore from the backup to undo).
from django.db import migrations

GENUS, WRONG, RIGHT = 'Fiona', 'Pinnata', 'pinnata'
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
            sp.save()
            continue
        for name in [f.name for f in Species._meta.concrete_fields if f.name not in KEEP]:
            if blank(getattr(twin, name)) and not blank(getattr(sp, name)): setattr(twin, name, getattr(sp, name))
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
        ('observations', '0045_fold_ocellatus_van_into_ocellatus'),
    ]

    operations = [
        migrations.RunPython(fold, migrations.RunPython.noop),
    ]
