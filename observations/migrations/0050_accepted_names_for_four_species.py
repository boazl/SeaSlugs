# Data only, decided by the site owner: the catalog always carries the ACCEPTED (WoRMS) name.
#   Marionia arborescens        -> Marioniopsis arborescens   (fold into the existing row)
#   Okenia brunneomaculata      -> Bermudella brunneomaculata (fold into the existing row)
#   Tenellia minor              -> Phestilla minor            (fold into the existing row)
#   Eubranchus mandapamensis    -> Annulorhina mandapamensis  (no accepted row: renamed, author K. P. Rao, 1968)
# Same procedure as 0044-0048 (blank catalog fields copied to the accepted row, samples moved,
# areas moved keeping their slug or dropped when redundant, old row deleted). On top of that the
# moved samples' own genus/family/order TEXT is refreshed -- the historical models have no
# save() that would do it (Sample.sync_taxonomy). Idempotent; the reverse does nothing.
from django.db import migrations

PAIRS = [
    # (old genus, old epithet, new genus, new epithet, author to set on a RENAMED row)
    ('Marionia', 'arborescens', 'Marioniopsis', 'arborescens', None),
    ('Okenia', 'brunneomaculata', 'Bermudella', 'brunneomaculata', None),
    ('Tenellia', 'minor', 'Phestilla', 'minor', None),
    ('Eubranchus', 'mandapamensis', 'Annulorhina', 'mandapamensis', 'K. P. Rao, 1968'),
]
KEEP = {'id', 'genus', 'species', 'scientific_name', 'full_species_name_with_order'}


def refresh_sample_taxonomy(apps, species):
    """genus from the species; family/order from the taxonomy tables when the genus is known there."""
    Sample, TaxonGenus = apps.get_model('observations', 'Sample'), apps.get_model('observations', 'TaxonGenus')
    tg = TaxonGenus.objects.select_related('family__order').filter(name=species.genus).first()
    for sample in Sample.objects.filter(species=species):
        sample.genus = species.genus
        if tg and tg.family_id:
            sample.family = tg.family.name
            if tg.family.order_id: sample.order = tg.family.order.name
        sample.save(update_fields=['genus', 'family', 'order'])


def run(apps, schema_editor):
    Species = apps.get_model('observations', 'Species')
    Sample = apps.get_model('observations', 'Sample')
    SpeciesArea = apps.get_model('observations', 'SpeciesArea')
    blank = lambda v: v in ('', None)
    for old_genus, old_epithet, genus, epithet, rename_author in PAIRS:
        for sp in list(Species.objects.filter(genus=old_genus, species=old_epithet)):
            twin = Species.objects.filter(genus=genus, species=epithet).exclude(pk=sp.pk).first()
            if twin is None:
                sp.genus, sp.species, sp.scientific_name = genus, epithet, f'{genus} {epithet}'
                if rename_author:
                    sp.author = rename_author
                    if sp.formatted_author: sp.formatted_author = rename_author
                sp.full_species_name_with_order = sp.full_species_name_with_order.replace(f'{old_genus} {old_epithet}', f'{genus} {epithet}')
                sp.save()
                refresh_sample_taxonomy(apps, sp)
                continue
            for name in [f.name for f in Species._meta.concrete_fields if f.name not in KEEP]:
                if blank(getattr(twin, name)) and not blank(getattr(sp, name)): setattr(twin, name, getattr(sp, name))
            if blank(twin.full_species_name_with_order) and not blank(twin.phylogenetic_order):
                author = twin.formatted_author or twin.author
                twin.full_species_name_with_order = f'{twin.phylogenetic_order}-{genus} {epithet} {author}'.strip()
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
            refresh_sample_taxonomy(apps, twin)


class Migration(migrations.Migration):

    dependencies = [
        ('observations', '0049_species_authors_from_worms_match'),
    ]

    operations = [
        migrations.RunPython(run, migrations.RunPython.noop),
    ]
