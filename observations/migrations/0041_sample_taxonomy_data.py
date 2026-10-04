# Step 2 of the Sample taxonomy change (0040 added the columns): move the data.
#
# Until now a taxon-level sample (kind genus / family / order) kept its identification as free
# text in `species_other`. It now lives in the field that matches its kind -- `genus`, `family`
# or `order` -- and the higher levels are filled in from the taxonomy tables (a genus knows its
# family, a family its order). Species-kind samples with a catalogued species get their genus /
# family / order copied from the species. `species_other` stays only for a species that is not
# in the catalog yet. Data only (schema is 0040); reversible: the reverse puts the kind's own
# name back into `species_other`.

from django.db import migrations


def families_orders(apps):
    TaxonFamily = apps.get_model('observations', 'TaxonFamily')
    by_family = {}
    for fam in TaxonFamily.objects.select_related('order'):
        if fam.order_id: by_family.setdefault(fam.name, set()).add(fam.order.name)
    return by_family


def forwards(apps, schema_editor):
    Sample = apps.get_model('observations', 'Sample')
    TaxonGenus = apps.get_model('observations', 'TaxonGenus')
    order_of_family = families_orders(apps)
    genus_chain = {g.name: (g.family.name if g.family_id else '',
                            g.family.order.name if g.family_id and g.family.order_id else '')
                   for g in TaxonGenus.objects.select_related('family__order')}

    def order_for(family, current=''):
        orders = order_of_family.get(family, set())
        return next(iter(orders)) if len(orders) == 1 else current

    for sample in Sample.objects.select_related('species'):
        sp = sample.species
        name = (sample.species_other or '').strip()
        order = family = genus = ''
        update = {}
        if sample.kind == 'collection':
            continue
        if sample.kind == 'order':
            order = name or (sp.order if sp else '')
            update = {'order': order, 'species_other': '', 'species_id': None}
        elif sample.kind == 'family':
            family = name or (sp.family if sp else '')
            update = {'family': family, 'order': order_for(family), 'species_other': '', 'species_id': None}
        elif sample.kind == 'genus':
            genus = name or (sp.genus if sp else '')
            family, order = genus_chain.get(genus, ('', ''))
            family = family or (sp.family if sp else '')
            update = {'genus': genus, 'family': family, 'order': order or order_for(family, sp.order if sp else ''),
                      'species_other': '', 'species_id': None}
        elif sp is not None:
            # family/order through the genus in the taxonomy tables; the species' own text
            # columns are only a fallback (its `order` can be a different classification
            # level than TaxonOrder's names).
            family, order = genus_chain.get(sp.genus, ('', ''))
            family = family or sp.family
            update = {'genus': sp.genus or '', 'family': family, 'order': order or order_for(family, sp.order or '')}
        if update: Sample.objects.filter(pk=sample.pk).update(**update)


def backwards(apps, schema_editor):
    Sample = apps.get_model('observations', 'Sample')
    for kind, field in (('order', 'order'), ('family', 'family'), ('genus', 'genus')):
        for sample in Sample.objects.filter(kind=kind):
            Sample.objects.filter(pk=sample.pk).update(species_other=getattr(sample, field) or sample.species_other)


class Migration(migrations.Migration):

    dependencies = [
        ('observations', '0040_sample_taxonomy_fields'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
