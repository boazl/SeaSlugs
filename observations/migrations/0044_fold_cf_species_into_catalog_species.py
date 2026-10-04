# Data only. "cf." / "aff." is a property of an identification, so it now lives on the sample
# (Sample.identification_qualifier), not in the catalog species. Stage 1 had left catalog rows
# whose epithet starts with it ("Chromodoris cf. strigata"), next to the plain species
# ("Chromodoris strigata") that already exists in the catalog. This folds each such row into
# the plain species:
#   * its samples point at the plain species and get the qualifier (when they had none);
#   * its SpeciesArea rows move to the plain species -- or, when the plain species already has
#     a row for the same country + sea + variant, the redundant one is dropped (the plain
#     species' own row, and its defining sample, win);
#   * catalog fields that the plain species lacks (e.g. the phylogenetic order) are copied over;
#   * the now unused cf. row is deleted. A cf. row with no plain twin is just renamed.
# SpeciesArea slugs that move keep their slug, so published URLs stay valid. Idempotent;
# irreversible in data terms (the reverse does nothing -- restore from the backup to undo).
import re
from django.db import migrations

PREFIX = re.compile(r'^(cf|aff)\.\s+(?=\S)')
KEEP = {'id', 'genus', 'species', 'scientific_name', 'full_species_name_with_order'}


def fold(apps, schema_editor):
    Species = apps.get_model('observations', 'Species')
    Sample = apps.get_model('observations', 'Sample')
    SpeciesArea = apps.get_model('observations', 'SpeciesArea')
    fields = [f.name for f in Species._meta.concrete_fields if f.name not in KEEP]
    blank = lambda v: v in ('', None)
    for sp in list(Species.objects.filter(species__regex=r'^(cf|aff)\.\s')):
        match = PREFIX.match(sp.species)
        qualifier = match.group(1) + '.'
        clean = sp.species[match.end():].strip()
        twin = Species.objects.filter(genus=sp.genus, species=clean).exclude(pk=sp.pk).first()
        if twin is None:
            sp.species, sp.scientific_name = clean, f'{sp.genus} {clean}'.strip()
            sp.save(update_fields=['species', 'scientific_name'])
            Sample.objects.filter(species=sp, identification_qualifier='').update(identification_qualifier=qualifier)
            continue
        for name in fields:
            if blank(getattr(twin, name)) and not blank(getattr(sp, name)): setattr(twin, name, getattr(sp, name))
        if blank(twin.full_species_name_with_order) and not blank(twin.phylogenetic_order):
            author = twin.formatted_author or twin.author
            twin.full_species_name_with_order = f'{twin.phylogenetic_order}-{twin.genus} {twin.species} {author}'.strip()
        twin.save()
        Sample.objects.filter(species=sp, identification_qualifier='').update(identification_qualifier=qualifier)
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
        ('observations', '0043_seed_qualifier_and_life_stage'),
    ]

    operations = [
        migrations.RunPython(fold, migrations.RunPython.noop),
    ]
