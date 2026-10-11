"""Families follow WoRMS (checked family by family on 2026-10-11).

1. Families WoRMS does not accept are merged into the accepted one: Calmidae, Coryphellidae and
   Paracoryphellidae -> Flabellinidae; Unidentiidae -> Piseinotecidae; Gasteropteridae -> Gastropteridae
   (an unaccepted spelling that existed next to the accepted family); Okadaiidae -> Polyceridae
   (WoRMS: Okadaiinae, a subfamily of Polyceridae). Genera and species move with them.
2. Superfamilies WoRMS gives differently: Doridomorphidae and Heterodorididae -> Heterodoridoidea (new
   superfamily row, Cladobranchia), Goniaeolididae -> Proctonotoidea (Cladobranchia). Heroidae and
   Doridoxidae stay on the order's own row (WoRMS: Nudibranchia incertae sedis).
3. Genus Annulorhina (Eubranchidae in WoRMS) is added.
4. The old order / family / superfamily text columns of every species are brought in line with the genus
   it belongs to ("Doridida", "Not assigned" and blanks disappear).
"""
from django.db import migrations

MERGE = {
    'Calmidae': 'Flabellinidae', 'Coryphellidae': 'Flabellinidae', 'Paracoryphellidae': 'Flabellinidae',
    'Unidentiidae': 'Piseinotecidae', 'Gasteropteridae': 'Gastropteridae', 'Okadaiidae': 'Polyceridae',
}
SUPERFAMILY_OF = {'Doridomorphidae': 'Heterodoridoidea', 'Heterodorididae': 'Heterodoridoidea', 'Goniaeolididae': 'Proctonotoidea'}


def forwards(apps, schema_editor):
    Order = apps.get_model('observations', 'TaxonOrder')
    Family = apps.get_model('observations', 'TaxonFamily')
    Genus = apps.get_model('observations', 'TaxonGenus')
    Species = apps.get_model('observations', 'Species')
    Superfamily = apps.get_model('observations', 'TaxonSuperfamily')

    for source, target in MERGE.items():
        src = Family.objects.filter(name=source, sub_family='').first()
        dst = Family.objects.filter(name=target, sub_family='').first()
        if src is None or dst is None or src.pk == dst.pk:
            continue
        Genus.objects.filter(family=src).update(family=dst)
        Species.objects.filter(family=source).update(family=target)
        src.delete()

    cladobranchia = Order.objects.filter(name='Nudibranchia', sub_order='Cladobranchia').first()
    for family, superfamily in SUPERFAMILY_OF.items():
        row = Family.objects.filter(name=family).first()
        if row is None:
            continue
        Superfamily.objects.get_or_create(name=superfamily)
        row.superfamily = superfamily
        if cladobranchia is not None:
            row.order = cladobranchia
        row.save(update_fields=['superfamily', 'order'])

    eubranchidae = Family.objects.filter(name='Eubranchidae', sub_family='').first()
    if eubranchidae is not None:
        Genus.objects.get_or_create(name='Annulorhina', defaults={'family': eubranchidae})

    genera = {g.name: g for g in Genus.objects.select_related('family__order') if g.family_id}
    changed = []
    for sp in Species.objects.all().only('id', 'scientific_name', 'genus', 'order', 'family', 'superfamily'):
        genus = genera.get(sp.genus or (sp.scientific_name.split()[0] if sp.scientific_name else ''))
        if genus is None:
            continue
        fam = genus.family
        order_name = fam.order.name if fam.order_id else sp.order
        if (sp.order, sp.family, sp.superfamily) != (order_name, fam.name, fam.superfamily):
            sp.order, sp.family, sp.superfamily = order_name, fam.name, fam.superfamily
            changed.append(sp)
    Species.objects.bulk_update(changed, ['order', 'family', 'superfamily'], batch_size=500)


class Migration(migrations.Migration):

    dependencies = [
        ('observations', '0065_taxon_superfamilies_and_worms_suborders'),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
