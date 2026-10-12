"""Samples' own family / order text follows the taxonomy tables (the families merged in 0066 left some of it behind).

A species or genus observation stores the family and order of its genus as text. Migration 0066 aligned the species
rows and the family rows but not these copies, so e.g. a genus observation of Cyerce still said Hermaeidae while the
table says Caliphyllidae -- which blocks its import (the importer rejects a genus observation whose family is not
its genus' family). A family observation of a family that was merged is moved to the family it merged into.
Only the text columns are rewritten; nothing else about a sample changes.
"""
from django.db import migrations

MERGED_FAMILIES = {'Calmidae': 'Flabellinidae', 'Coryphellidae': 'Flabellinidae', 'Paracoryphellidae': 'Flabellinidae',
                   'Unidentiidae': 'Piseinotecidae', 'Gasteropteridae': 'Gastropteridae', 'Okadaiidae': 'Polyceridae'}


def follow_taxonomy(apps, schema_editor):
    Sample = apps.get_model('observations', 'Sample')
    TaxonGenus = apps.get_model('observations', 'TaxonGenus')
    TaxonFamily = apps.get_model('observations', 'TaxonFamily')
    for old, new in MERGED_FAMILIES.items():
        family = TaxonFamily.objects.filter(name=new).select_related('order').first()
        if family is not None:
            Sample.objects.filter(kind='family', family=old).update(family=new, order=family.order.name if family.order_id else '')
    for genus in TaxonGenus.objects.select_related('family__order').exclude(family__isnull=True):
        order = genus.family.order.name if genus.family.order_id else None
        samples = Sample.objects.filter(kind__in=['species', 'genus'], genus=genus.name).exclude(family=genus.family.name)
        samples.update(family=genus.family.name, **({'order': order} if order else {}))
        if order:
            Sample.objects.filter(kind__in=['species', 'genus'], genus=genus.name, family=genus.family.name).exclude(order=order).update(order=order)


class Migration(migrations.Migration):
    dependencies = [('observations', '0068_superfamilies_into_orders')]
    operations = [migrations.RunPython(follow_taxonomy, migrations.RunPython.noop)]
