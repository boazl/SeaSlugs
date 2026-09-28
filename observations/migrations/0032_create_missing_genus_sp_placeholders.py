# 535 (of the 551 distinct genera then in the Species table) had every one of their catalogued
# species identified to species level, with no bare "[Genus] sp." row an operator can fall back
# on when a photographed specimen can only be identified to genus. This backfills that missing
# placeholder row for every genus that still lacks one at migration time, so folder-import and
# the observation form's species-matching (Species.find_by_name) always have a "[Genus] sp."
# entry to match against or offer, exactly like the 16 genera that already had one by hand.
#
# Each new row's classification fields (order/family/superfamily/phylogenetic_order) are derived
# from that genus's own existing species rows, using the same techniques
# build_taxonomy_tables.py already uses to derive TaxonOrder/TaxonFamily/TaxonGenus from Species:
# majority vote (most common non-blank value) for order/family/superfamily, and the minimum
# non-blank phylogenetic_order value (matching that command's _min_phylo helper) so the new row
# sorts alongside its genus-mates rather than at the very end of an unordered tail. A handful of
# genera disagree among their own species rows on these fields (data-entry drift in the source
# spreadsheet); majority vote picks the more common value in that case rather than blocking the
# whole backfill on manual review.
from collections import Counter, defaultdict

from django.db import migrations


def _majority(counter):
    return counter.most_common(1)[0][0] if counter else ''


def _min_phylo(values):
    values = [v for v in values if v]
    return min(values) if values else ''


def create_missing_genus_sp_placeholders(apps, schema_editor):
    Species = apps.get_model('observations', 'Species')

    rows_by_genus = defaultdict(list)
    for genus, species, order, family, superfamily, phylo in Species.objects.exclude(genus='').values_list(
            'genus', 'species', 'order', 'family', 'superfamily', 'phylogenetic_order'):
        rows_by_genus[genus].append((species, order, family, superfamily, phylo))

    # A genus already has its bare placeholder when SOME row's scientific_name literally
    # reads "<Genus> sp." -- checked against the whole table's scientific_name, not just rows
    # whose own genus/species fields happen to be filled in: a few legacy rows (e.g. "Ercolania
    # sp.", pk 47) carry that full text in scientific_name but have blank genus/species columns,
    # and would otherwise collide with a newly created, properly-columned duplicate.
    existing_names = {name.casefold() for name in Species.objects.values_list('scientific_name', flat=True)}

    created = []
    for genus, entries in rows_by_genus.items():
        if f'{genus} sp.'.casefold() in existing_names:
            continue
        order_votes = Counter(o for _, o, _, _, _ in entries if o)
        family_votes = Counter(f for _, _, f, _, _ in entries if f)
        superfamily_votes = Counter(sf for _, _, _, sf, _ in entries if sf)
        phylo_values = [p for _, _, _, _, p in entries]
        Species.objects.create(
            scientific_name=f'{genus} sp.',
            genus=genus,
            species='sp.',
            order=_majority(order_votes),
            family=_majority(family_votes),
            superfamily=_majority(superfamily_votes),
            phylogenetic_order=_min_phylo(phylo_values),
        )
        created.append(genus)

    if created:
        print(f'  Created {len(created)} "[Genus] sp." placeholder species row(s), '
              f'for genera that had no bare "sp." catalog entry yet.')


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ('observations', '0031_undetermined_variant_on_sample_and_speciesarea'),
    ]
    operations = [
        migrations.RunPython(create_missing_genus_sp_placeholders, noop_reverse),
    ]
