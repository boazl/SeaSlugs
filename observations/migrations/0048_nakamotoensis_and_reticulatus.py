# Data only, decisions made by the site owner after the WoRMS lookup (0047):
#  * "Okenia nakamotoensis" is an old, unaccepted combination; the accepted name is
#    "Ceratodoris nakamotoensis (Hamatani, 2001)". The old row is folded into the accepted one
#    (same procedure as 0044-0046: samples/areas move or are dropped when redundant, missing
#    catalog fields are copied over, the old row is deleted; no accepted row -> renamed).
#  * Goniobranchus reticulatus has two homonyms in WoRMS; the Indo-Pacific one photographed
#    here is "(Quoy & Gaimard, 1832)".
# Only EMPTY authors are filled. Idempotent; the reverse does nothing.
from django.db import migrations

OLD, NEW, NEW_AUTHOR = ('Okenia', 'nakamotoensis'), ('Ceratodoris', 'nakamotoensis'), '(Hamatani, 2001)'
RETICULATUS_AUTHOR = '(Quoy & Gaimard, 1832)'
KEEP = {'id', 'genus', 'species', 'scientific_name', 'full_species_name_with_order'}


def run(apps, schema_editor):
    Species = apps.get_model('observations', 'Species')
    Sample = apps.get_model('observations', 'Sample')
    SpeciesArea = apps.get_model('observations', 'SpeciesArea')
    blank = lambda v: v in ('', None)
    for sp in list(Species.objects.filter(genus=OLD[0], species=OLD[1])):
        twin = Species.objects.filter(genus=NEW[0], species=NEW[1]).exclude(pk=sp.pk).first()
        if twin is None:
            sp.genus, sp.species, sp.scientific_name = NEW[0], NEW[1], f'{NEW[0]} {NEW[1]}'
            sp.save()
            continue
        for name in [f.name for f in Species._meta.concrete_fields if f.name not in KEEP]:
            if blank(getattr(twin, name)) and not blank(getattr(sp, name)): setattr(twin, name, getattr(sp, name))
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
    Species.objects.filter(genus=NEW[0], species=NEW[1], author='').update(author=NEW_AUTHOR)
    Species.objects.filter(genus='Goniobranchus', species='reticulatus', author='').update(author=RETICULATUS_AUTHOR)


class Migration(migrations.Migration):

    dependencies = [
        ('observations', '0047_species_authors_from_worms'),
    ]

    operations = [
        migrations.RunPython(run, migrations.RunPython.noop),
    ]
