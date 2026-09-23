"""Build/refresh the taxonomy lookup tables (order, family, genus) from the Species table.

The Species table already carries free-text order/family/genus/phylogenetic_order columns
per species; this command derives the normalized TaxonOrder -> TaxonFamily -> TaxonGenus
hierarchy from that data (majority vote per family/genus when a couple of species disagree,
e.g. legacy "Doridida" vs current "Nudibranchia" labelling), and fills in Hebrew genus names
from a small extracted supplement (data/taxonomy_excel_supplement.json) for genera the personal
reference spreadsheet already has a Hebrew name for.

Safe to re-run: existing rows are matched by name and only their BLANK fields are filled in --
any value the user has since edited by hand (name_he, taxonomic_order, sub_order/sub_family,
or a reassigned FK) is left untouched.
"""
import json
from collections import Counter, defaultdict
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction

from observations.models import Species, TaxonOrder, TaxonFamily, TaxonGenus, Sample, SampleKind
from observations.table_transfer import create_backup

IGNORED_ORDER_VALUES = {'', 'Not assigned'}


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

        rows = list(Species.objects.order_by().values_list('order', 'family', 'genus', 'phylogenetic_order'))

        order_phylo = defaultdict(list)
        family_phylo = defaultdict(list)
        genus_phylo = defaultdict(list)
        family_order_votes = defaultdict(Counter)
        genus_family_votes = defaultdict(Counter)
        order_names = set()
        family_names = set()
        genus_names = set()

        for order, family, genus, phylo in rows:
            if order and order not in IGNORED_ORDER_VALUES:
                order_names.add(order)
                order_phylo[order].append(phylo)
            if family:
                family_names.add(family)
                family_phylo[family].append(phylo)
                if order and order not in IGNORED_ORDER_VALUES:
                    family_order_votes[family][order] += 1
            if genus:
                genus_names.add(genus)
                genus_phylo[genus].append(phylo)
                if family:
                    genus_family_votes[genus][family] += 1

        created = {'order': 0, 'family': 0, 'genus': 0}
        updated = {'order': 0, 'family': 0, 'genus': 0}
        name_he_filled = 0

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

        def run():
            order_objs = {}
            for name in sorted(order_names):
                obj = sync(TaxonOrder, name, {'taxonomic_order': _min_phylo(order_phylo[name])}, 'order', sub_field='sub_order')
                order_objs[name] = obj
                if obj:
                    fill_defining_sample(obj, 'order', species__order=name)

            family_objs = {}
            for name in sorted(family_names):
                order_name = _majority(family_order_votes[name])
                defaults = {'taxonomic_order': _min_phylo(family_phylo[name])}
                obj = sync(TaxonFamily, name, defaults, 'family', sub_field='sub_family')
                family_objs[name] = obj
                if apply and order_name and obj.order_id is None:
                    order_obj = TaxonOrder.objects.filter(name=order_name, sub_order='').first()
                    if order_obj:
                        obj.order = order_obj
                        obj.save(update_fields=['order'])
                if obj:
                    fill_defining_sample(obj, 'family', species__family=name)

            for name in sorted(genus_names):
                family_name = _majority(genus_family_votes[name])
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
            f"families: {created['family']} to create, {updated['family']} existing "
            f"(of {len(family_names)} distinct)"
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
