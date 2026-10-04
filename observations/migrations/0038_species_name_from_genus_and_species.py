# Step 1 of 2 making Species.genus / species / author the authoritative fields, with
# scientific_name derived ("<genus> <species>").
#
# Data only (the column itself is unchanged -- 0039 just marks it non-editable):
#  * rows with a blank genus/species (8 in production) get them split out of scientific_name;
#  * a name that carries open-nomenclature text or the author ("Chromodoris cf. strigata",
#    "Berthellina delicata (Pease, 1861)") keeps its qualifier in the species field
#    ("cf. strigata") but loses an author that is duplicated in the name, so that
#    scientific_name == genus + " " + species holds for every row;
#  * a row that then collides with another row of the SAME name (the author-embedded
#    "Berthellina delicata (Pease, 1861)" vs plain "Berthellina delicata") is merged: blank
#    fields of the kept row are filled from the other, and the other is deleted only when
#    nothing references it. A collision involving referenced rows on both sides is left as is
#    (no data is ever re-pointed or lost here).

from django.db import migrations

COPYABLE = ['name_he', 'name_en', 'source_id', 'family', 'order', 'superfamily', 'accepted_genus', 'accepted_species',
            'common_name', 'transliteration', 'language', 'formatted_author', 'distribution', 'phylogenetic_order',
            'full_species_name_with_order', 'reference_author', 'habitat', 'food', 'description_he', 'description_en', 'link']


def split_name(row):
    name = ' '.join((row.scientific_name or '').split())
    author = (row.author or '').strip()
    if author and name.endswith(author) and len(name) > len(author):
        name = name[:-len(author)].strip()
    genus = (row.genus or '').strip()
    if genus and (name == genus or name.startswith(genus + ' ')):
        return genus, name[len(genus):].strip()
    genus, _, epithet = name.partition(' ')
    return genus, epithet


def references(apps, species):
    Sample = apps.get_model('observations', 'Sample')
    SpeciesArea = apps.get_model('observations', 'SpeciesArea')
    return Sample.objects.filter(species_id=species.pk).exists() or SpeciesArea.objects.filter(species_id=species.pk).exists()


def derive_names(apps, schema_editor):
    Species = apps.get_model('observations', 'Species')
    for row in Species.objects.order_by('pk'):
        genus, epithet = split_name(row)
        name = f'{genus} {epithet}'.strip()
        if (row.genus, row.species, row.scientific_name) != (genus, epithet, name):
            Species.objects.filter(pk=row.pk).update(genus=genus, species=epithet, scientific_name=name)
    seen = {}
    for row in Species.objects.order_by('pk'):
        seen.setdefault(row.scientific_name, []).append(row)
    for name, rows in seen.items():
        if len(rows) < 2: continue
        rows.sort(key=lambda r: (not references(apps, r), r.pk))   # a referenced row is kept first
        keep = rows[0]
        for other in rows[1:]:
            if references(apps, other): continue
            fill = {f: getattr(other, f) for f in COPYABLE if not getattr(keep, f) and getattr(other, f)}
            if not keep.author and other.author: fill['author'] = other.author
            if fill: Species.objects.filter(pk=keep.pk).update(**fill)
            other.delete()


class Migration(migrations.Migration):

    dependencies = [
        ('observations', '0037_remove_divetrip_sea'),
    ]

    operations = [
        # Not reversible in detail (the original free-form names are not kept); a no-op reverse
        # leaves the corrected, consistent data in place.
        migrations.RunPython(derive_names, migrations.RunPython.noop),
    ]
