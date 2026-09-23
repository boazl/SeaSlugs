import json
from pathlib import Path

from django.db import migrations


def upgrade_family_order_links_to_specific_suborder_rows(apps, schema_editor):
    """Every TaxonFamily's order FK was, until now, only ever linked (by the OLD code) to a
    blank-sub_order "base" order row -- migration 0018's superfamily-based family->order linking
    only fills a family's order when it's still NULL, so it never touched these pre-existing,
    coarser assignments. Now that the curated taxon_order_reference gives Nudibranchia several
    specific suborder rows (Doridina TO=4/5, Cladobranchia TO=6/7/8), every family whose
    superfamily resolves to one of those specific rows gets upgraded from the generic base row
    to it. This only ever REFINES an assignment into a more specific row of the SAME order name
    -- it never moves a family to a genuinely different order, which stays a manual admin call.

    Also cleans up the "Doridida" row: a legacy synonym for Nudibranchia that the old order-text
    sync loop kept re-creating as its own bogus standalone TaxonOrder row (build_taxonomy_tables
    now normalizes this text before aggregating, so it won't recur). Any family still pointed at
    it is treated as a Nudibranchia family for the refinement above, then the row is deleted.
    """
    TaxonOrder = apps.get_model('observations', 'TaxonOrder')
    TaxonFamily = apps.get_model('observations', 'TaxonFamily')

    supplement_path = Path(__file__).resolve().parent.parent / 'management' / 'commands' / 'data' / 'taxonomy_excel_supplement.json'
    if not supplement_path.exists():
        return
    supplement = json.loads(supplement_path.read_text(encoding='utf-8'))

    superfamily_to_key = {}
    for entry in supplement.get('taxon_order_reference', []):
        key = (entry['order_name'], entry.get('sub_order', ''), entry.get('taxonomic_order', ''))
        for sf in entry.get('superfamilies', []):
            superfamily_to_key[sf] = key

    order_by_key = {(o.name, o.sub_order, o.taxonomic_order): o for o in TaxonOrder.objects.all()}

    # A legacy synonym for Nudibranchia -- any family still linked to that bogus standalone row
    # is treated the same as one linked to the real Nudibranchia base row for the refinement below.
    LEGACY_ORDER_NAME_ALIASES = {'Doridida': 'Nudibranchia'}

    for family in TaxonFamily.objects.exclude(superfamily='').select_related('order'):
        correct_key = superfamily_to_key.get(family.superfamily)
        if not correct_key:
            continue
        correct_order = order_by_key.get(correct_key)
        if not correct_order or correct_order.pk == family.order_id:
            continue
        current_order = family.order
        if current_order is None:
            continue
        current_name = LEGACY_ORDER_NAME_ALIASES.get(current_order.name, current_order.name)
        if current_name != correct_order.name:
            continue
        family.order_id = correct_order.pk
        family.save(update_fields=['order'])

    doridida = TaxonOrder.objects.filter(name='Doridida').first()
    if doridida and not TaxonFamily.objects.filter(order=doridida).exists():
        doridida.delete()


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('observations', '0018_remove_taxonorder_unique_taxonorder_name_sub_order_and_more'),
    ]

    operations = [
        migrations.RunPython(upgrade_family_order_links_to_specific_suborder_rows, noop_reverse),
    ]
