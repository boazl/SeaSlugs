"""Build/refresh the taxonomy lookup tables (order, family, genus) from the Species table.

The Species table already carries free-text order/family/genus/superfamily/phylogenetic_order
columns per species; this command derives the normalized TaxonOrder -> TaxonFamily -> TaxonGenus
hierarchy from that data, and fills in Hebrew/English names from a curated supplement file
(data/taxonomy_excel_supplement.json):

- genus_hebrew_names: Hebrew names for genera, from the personal reference spreadsheet.
- taxon_order_reference: the curated, authoritative list of order/suborder groups (Hebrew name,
  English name, taxonomic display order, and the superfamilies each group covers). Every one of
  these rows is seeded as its own TaxonOrder row, matched by the (name, sub_order, taxonomic_order)
  triple -- note the SAME (name, sub_order) pair can legitimately repeat across several rows
  (e.g. Nudibranchia/Doridina covers both a "cryptobranch dorids" and a "radula-less dorids"
  group), which taxonomic_order alone disambiguates.
- family_to_superfamily: an externally-sourced family->superfamily crosswalk (from the user's
  reference spreadsheet's taxonomic database export), used as a fallback wherever the Species
  table's own (mostly blank) superfamily column doesn't cover a family.

Family -> order linking prefers superfamily: a family's superfamily (majority-voted from
Species.superfamily, falling back to the family_to_superfamily crosswalk) is looked up against
the superfamilies each taxon_order_reference group covers, and the family is linked to that
specific order row. This resolves cases plain order-text majority voting cannot (most
Sacoglossa/Acteonoidea species have blank order text) and picks the correct specific row among
several sharing the same order name/sub_order. Families whose superfamily can't be resolved fall
back to the old order-text majority vote, linked to that order's blank-sub_order "base" row.

Safe to re-run: existing rows are matched by their identifying key and only their BLANK fields
are filled in -- any value the user has since edited by hand (name_he, taxonomic_order,
sub_order/sub_family/superfamily, or a reassigned FK) is left untouched.
"""
import json
from collections import Counter, defaultdict
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction

from observations.models import Species, TaxonOrder, TaxonFamily, TaxonGenus, Sample, SampleKind
from observations.table_transfer import create_backup

IGNORED_ORDER_VALUES = {'', 'Not assigned'}

# A couple of species use an informal placeholder genus name (not a real Latin genus) that the
# spreadsheet never gave a family for via genus->family text voting. Their real family is
# unambiguous from the placeholder name itself -- flagged here as an explicit inference, not
# something derived from the data, for the user to double-check in admin.
PLACEHOLDER_GENUS_FAMILY = {
    'Haminoeid': 'Haminoeidae',
    'Discodorid': 'Discodorididae',
}


def _min_phylo(values):
    values = [v for v in values if v]
    return min(values) if values else ''


def _majority(counter):
    if not counter:
        return None
    return counter.most_common(1)[0][0]


def _pick_defining_sample(queryset):
    """Same spirit as SpeciesArea.pick_defining_sample: among published, non-deleted
    species-kind samples for this taxon that actually have media, prefer one with an
    uploaded image over a video-only one, tie-broken by whichever was created first."""
    candidates = [s for s in queryset.order_by('created_at', 'pk') if s.image or s.video_url]
    if not candidates:
        return None
    with_image = [c for c in candidates if c.image]
    return (with_image or candidates)[0]



KIND_EN_NAMES = {
    'species': 'Species',
    'collection': 'Collection (dive trip)',
    'genus': 'Genus',
    'family': 'Family',
    'order': 'Order',
}

class Command(BaseCommand):
    help = 'Build/refresh TaxonOrder, TaxonFamily, TaxonGenus (from Species) and SampleKind (from Sample.Kind).'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='Actually write to the database (default: dry run report only).')

    def handle(self, *args, **options):
        apply = options['apply']
        supplement_path = Path(__file__).resolve().parent / 'data' / 'taxonomy_excel_supplement.json'
        supplement = json.loads(supplement_path.read_text(encoding='utf-8')) if supplement_path.exists() else {}
        genus_hebrew_names = supplement.get('genus_hebrew_names', {})
        taxon_order_reference = supplement.get('taxon_order_reference', [])
        family_to_superfamily_supplement = supplement.get('family_to_superfamily', {})

        # superfamily name -> (order_name, sub_order, taxonomic_order) identifying the specific
        # taxon_order_reference row that covers it.
        superfamily_to_order_key = {}
        for entry in taxon_order_reference:
            key = (entry['order_name'], entry.get('sub_order', ''), entry.get('taxonomic_order', ''))
            for sf in entry.get('superfamilies', []):
                superfamily_to_order_key[sf] = key

        rows = list(Species.objects.order_by().values_list('order', 'family', 'genus', 'superfamily', 'phylogenetic_order'))

        order_phylo = defaultdict(list)
        family_phylo = defaultdict(list)
        genus_phylo = defaultdict(list)
        family_order_votes = defaultdict(Counter)
        family_superfamily_votes = defaultdict(Counter)
        genus_family_votes = defaultdict(Counter)
        order_names = set()
        family_names = set()
        genus_names = set()

        for order, family, genus, superfamily, phylo in rows:
            if order and order not in IGNORED_ORDER_VALUES:
                order_names.add(order)
                order_phylo[order].append(phylo)
            if family:
                family_names.add(family)
                family_phylo[family].append(phylo)
                if order and order not in IGNORED_ORDER_VALUES:
                    family_order_votes[family][order] += 1
                if superfamily:
                    family_superfamily_votes[family][superfamily] += 1
            if genus:
                genus_names.add(genus)
                genus_phylo[genus].append(phylo)
                if family:
                    genus_family_votes[genus][family] += 1

        created = {'order': 0, 'family': 0, 'genus': 0}
        updated = {'order': 0, 'family': 0, 'genus': 0}

        def sync(model, name, defaults, level, sub_field=None):
            # A name can have several rows distinguished by sub_field (sub_order/sub_family),
            # hand-curated in admin -- this command only ever creates/updates the "base" row
            # with a blank sub_field, matched by (name, sub_field='').  Suborder/subfamily-
            # specific rows the user added by hand are left completely untouched.
            lookup = {'name': name}
            if sub_field:
                lookup[sub_field] = ''
            if apply:
                obj, was_created = model.objects.get_or_create(defaults=defaults, **lookup)
            else:
                obj, was_created = None, name not in existing_names[level]
            if was_created:
                created[level] += 1
                return obj
            updated[level] += 1
            if apply:
                changed = []
                for field, value in defaults.items():
                    if value and not getattr(obj, field):
                        setattr(obj, field, value)
                        changed.append(field)
                if changed:
                    obj.save(update_fields=changed)
            return obj

        existing_names = {
            'order': set(TaxonOrder.objects.filter(sub_order='').values_list('name', flat=True)),
            'family': set(TaxonFamily.objects.filter(sub_family='').values_list('name', flat=True)),
            'genus': set(TaxonGenus.objects.values_list('name', flat=True)),
        }

        existing_kind_codes = set(SampleKind.objects.values_list('code', flat=True))

        def sync_sample_kinds():
            kind_created = kind_updated = 0
            for code, name_he in Sample.Kind.choices:
                if not apply:
                    if code in existing_kind_codes:
                        kind_updated += 1
                    else:
                        kind_created += 1
                    continue
                obj, was_created = SampleKind.objects.get_or_create(
                    code=code, defaults={'name': name_he, 'name_en': KIND_EN_NAMES.get(code, '')})
                if was_created:
                    kind_created += 1
                    continue
                kind_updated += 1
                changed = []
                if not obj.name:
                    obj.name = name_he; changed.append('name')
                if not obj.name_en and KIND_EN_NAMES.get(code):
                    obj.name_en = KIND_EN_NAMES[code]; changed.append('name_en')
                if changed:
                    obj.save(update_fields=changed)
            return kind_created, kind_updated

        defining_counts = {'order': 0, 'family': 0, 'genus': 0}

        def base_species_samples(**filters):
            return Sample.objects.filter(
                kind='species', status='published', deleted_at__isnull=True, species_other='', **filters)

        def fill_defining_sample(obj, level, **filters):
            if not apply or obj.defining_sample_id is not None:
                return
            picked = _pick_defining_sample(base_species_samples(**filters))
            if picked:
                obj.defining_sample = picked
                obj.save(update_fields=['defining_sample'])
                defining_counts[level] += 1

        order_reference_counts = [0, 0]
        family_order_link_counts = {'superfamily': 0, 'order_text': 0, 'unresolved': 0}

        def seed_order_reference():
            """Seed every row from the curated taxon_order_reference list, matched by the full
            (name, sub_order, taxonomic_order) triple -- several rows can share the same
            (name, sub_order) pair, disambiguated only by taxonomic_order. Returns a dict keyed
            by that same triple, for family->order linking below."""
            order_by_key = {}
            for entry in taxon_order_reference:
                name = entry['order_name']
                sub_order = entry.get('sub_order', '')
                taxonomic_order = entry.get('taxonomic_order', '')
                key = (name, sub_order, taxonomic_order)
                lookup = {'name': name, 'sub_order': sub_order, 'taxonomic_order': taxonomic_order}
                defaults = {'name_he': entry.get('order_name_he', ''), 'name_en': entry.get('order_name_en', '')}
                if not apply:
                    exists = TaxonOrder.objects.filter(**lookup).exists()
                    order_reference_counts[1 if exists else 0] += 1
                    continue
                obj, was_created = TaxonOrder.objects.get_or_create(defaults=defaults, **lookup)
                order_by_key[key] = obj
                if was_created:
                    order_reference_counts[0] += 1
                    continue
                order_reference_counts[1] += 1
                changed = []
                for field, value in defaults.items():
                    if value and not getattr(obj, field):
                        setattr(obj, field, value)
                        changed.append(field)
                if changed:
                    obj.save(update_fields=changed)
            return order_by_key

        def run():
            # Seed the curated order/suborder reference rows FIRST, so their authoritative
            # taxonomic_order (e.g. Nudibranchia's base row is "3") is what the plain order-text
            # sync below matches against and fills in around -- doing it the other way round
            # would let the species-derived base row grab a different taxonomic_order (from
            # Species.phylogenetic_order) and then seed_order_reference would fail to match it
            # (lookup includes taxonomic_order) and create a duplicate row instead.
            order_by_key = seed_order_reference()

            order_objs = {}
            for name in sorted(order_names):
                defaults = {'taxonomic_order': _min_phylo(order_phylo[name])}
                obj = sync(TaxonOrder, name, defaults, 'order', sub_field='sub_order')
                order_objs[name] = obj
                if obj:
                    fill_defining_sample(obj, 'order', species__order=name)

            family_objs = {}
            for name in sorted(family_names):
                superfamily = _majority(family_superfamily_votes[name]) or family_to_superfamily_supplement.get(name, '')
                defaults = {'taxonomic_order': _min_phylo(family_phylo[name])}
                if superfamily:
                    defaults['superfamily'] = superfamily
                obj = sync(TaxonFamily, name, defaults, 'family', sub_field='sub_family')
                family_objs[name] = obj
                if apply and obj.order_id is None:
                    order_obj = None
                    if superfamily and superfamily in superfamily_to_order_key:
                        order_obj = order_by_key.get(superfamily_to_order_key[superfamily])
                        if order_obj:
                            family_order_link_counts['superfamily'] += 1
                    if order_obj is None:
                        order_name = _majority(family_order_votes[name])
                        if order_name:
                            order_obj = TaxonOrder.objects.filter(name=order_name, sub_order='').first()
                            if order_obj:
                                family_order_link_counts['order_text'] += 1
                    if order_obj:
                        obj.order = order_obj
                        obj.save(update_fields=['order'])
                    else:
                        family_order_link_counts['unresolved'] += 1
                if obj:
                    fill_defining_sample(obj, 'family', species__family=name)

            for name in sorted(genus_names):
                family_name = _majority(genus_family_votes[name]) or PLACEHOLDER_GENUS_FAMILY.get(name)
                defaults = {'taxonomic_order': _min_phylo(genus_phylo[name])}
                he = genus_hebrew_names.get(name)
                if he:
                    defaults['name_he'] = he
                obj = sync(TaxonGenus, name, defaults, 'genus')
                if apply and family_name and obj.family_id is None:
                    family_obj = TaxonFamily.objects.filter(name=family_name, sub_family='').first()
                    if family_obj:
                        obj.family = family_obj
                        obj.save(update_fields=['family'])
                if obj:
                    fill_defining_sample(obj, 'genus', species__genus=name)

        kind_counts = [0, 0]

        def run_all():
            kind_counts[0], kind_counts[1] = sync_sample_kinds()
            run()

        if apply:
            backup = create_backup()
            with transaction.atomic():
                run_all()
            self.stdout.write(f'Backup created: {backup.name}')
        else:
            run_all()

        self.stdout.write(
            f"orders: {created['order']} to create, {updated['order']} existing "
            f"(of {len(order_names)} distinct)"
        )
        self.stdout.write(
            f"taxon_order_reference rows: {order_reference_counts[0]} to create, "
            f"{order_reference_counts[1]} existing (of {len(taxon_order_reference)} defined)"
        )
        self.stdout.write(
            f"families: {created['family']} to create, {updated['family']} existing "
            f"(of {len(family_names)} distinct)"
        )
        if apply:
            self.stdout.write(
                f"family->order links: {family_order_link_counts['superfamily']} via superfamily, "
                f"{family_order_link_counts['order_text']} via order-text fallback, "
                f"{family_order_link_counts['unresolved']} unresolved"
            )
        self.stdout.write(
            f"genera: {created['genus']} to create, {updated['genus']} existing "
            f"(of {len(genus_names)} distinct; {len(genus_hebrew_names)} have a Hebrew name in the supplement file)"
        )
        self.stdout.write(f'sample kinds: {kind_counts[0]} to create, {kind_counts[1]} existing (of {len(Sample.Kind.choices)} defined)')
        if apply:
            self.stdout.write(
                f"defining samples newly picked: {defining_counts['order']} orders, "
                f"{defining_counts['family']} families, {defining_counts['genus']} genera"
            )
        if not apply:
            self.stdout.write('Dry run only -- pass --apply to write to the database.')
