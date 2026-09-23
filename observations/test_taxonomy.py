import json
from pathlib import Path
from unittest.mock import patch
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase
from .models import Species, TaxonOrder, TaxonFamily, TaxonGenus, Sample, SampleKind


class TaxonomyTablesTests(TestCase):
    SUPPLEMENT_PATH = Path(__file__).resolve().parent / 'management' / 'commands' / 'data' / 'taxonomy_excel_supplement.json'

    def setUp(self):
        # create_backup() does real file I/O (backing up the live sqlite file) -- irrelevant to
        # the population logic under test here, and the test runner's in-memory database isn't
        # a real file to back up in the first place.
        patcher = patch('observations.management.commands.build_taxonomy_tables.create_backup', return_value=Path('backup-stub.sqlite3'))
        self.addCleanup(patcher.stop)
        patcher.start()

    def build(self, **kwargs):
        defaults = dict(order='', family='', genus='', superfamily='', phylogenetic_order='')
        defaults.update(kwargs)
        return Species.objects.create(scientific_name=kwargs.get('scientific_name', f"Sp {Species.objects.count()}"), **{k: v for k, v in defaults.items() if k != 'scientific_name'})

    def test_dry_run_makes_no_database_changes(self):
        self.build(scientific_name='A', order='Nudibranchia', family='Chromodorididae', genus='Chromodoris', phylogenetic_order='313')
        call_command('build_taxonomy_tables')
        self.assertEqual(TaxonOrder.objects.count(), 0)
        self.assertEqual(TaxonFamily.objects.count(), 0)
        self.assertEqual(TaxonGenus.objects.count(), 0)

    def test_apply_builds_full_hierarchy_with_taxonomic_order_from_species(self):
        self.build(scientific_name='A', order='Nudibranchia', family='Chromodorididae', genus='Chromodoris', phylogenetic_order='313')
        self.build(scientific_name='B', order='Nudibranchia', family='Chromodorididae', genus='Chromodoris', phylogenetic_order='320')
        call_command('build_taxonomy_tables', '--apply')

        order = TaxonOrder.objects.get(name='Nudibranchia', sub_order='')
        family = TaxonFamily.objects.get(name='Chromodorididae')
        genus = TaxonGenus.objects.get(name='Chromodoris')
        self.assertEqual(genus.family, family)
        # The order's taxonomic_order comes from the curated taxon_order_reference (its display
        # rank among the 16 order/suborder groups), NOT from Species.phylogenetic_order -- the
        # reference row is seeded first and is authoritative, so the species-derived value never
        # overwrites it (sync() only fills BLANK fields). Family/genus have no such reference
        # table, so their taxonomic_order still derives from the species data as before.
        self.assertEqual(order.taxonomic_order, '3')
        self.assertEqual(family.taxonomic_order, '313')
        self.assertEqual(genus.taxonomic_order, '313')

    def test_family_links_to_order_via_superfamily_crosswalk_even_with_no_usable_order_text(self):
        # Real-data shape: many species (especially Acteonoidea/Sacoglossa) have blank or
        # "Not assigned" order text, which the old order-text-majority-vote logic could never
        # resolve. The family_to_superfamily crosswalk fixes exactly this: Acteonidae's
        # superfamily (Acteonoidea) is looked up against taxon_order_reference and linked
        # straight to the Acteonoidea order row, with no order text involved at all.
        self.build(scientific_name='A', order='Not assigned', family='Acteonidae', genus='Acteon')
        self.build(scientific_name='B', order='', family='', genus='')
        call_command('build_taxonomy_tables', '--apply')
        # The 16 taxon_order_reference rows are seeded unconditionally, regardless of what
        # order text (if any) appears in Species -- same pattern as SampleKind's fixed choices.
        self.assertEqual(TaxonOrder.objects.count(), 16)
        family = TaxonFamily.objects.get(name='Acteonidae')
        self.assertEqual(family.superfamily, 'Acteonoidea')
        self.assertIsNotNone(family.order)
        self.assertEqual(family.order.name, 'Acteonoidea')
        genus = TaxonGenus.objects.get(name='Acteon')
        self.assertEqual(genus.family, family)

    def test_family_order_conflict_resolved_by_majority(self):
        # Mirrors real data: most species of this family are tagged with the modern order,
        # a couple still carry the legacy one -- the majority should win. (Discodorididae also
        # happens to resolve via the superfamily crosswalk to the same order name, so this
        # still passes either way -- see the dedicated superfamily-disambiguation tests below
        # for the case where crosswalk and order-text would actually disagree.)
        self.build(scientific_name='A', order='Nudibranchia', family='Discodorididae', genus='Discodoris')
        self.build(scientific_name='B', order='Nudibranchia', family='Discodorididae', genus='Discodoris')
        self.build(scientific_name='C', order='Doridida', family='Discodorididae', genus='Discodoris')
        call_command('build_taxonomy_tables', '--apply')
        family = TaxonFamily.objects.get(name='Discodorididae')
        self.assertEqual(family.order.name, 'Nudibranchia')

    def test_genus_hebrew_name_filled_from_excel_supplement(self):
        supplement = json.loads(self.SUPPLEMENT_PATH.read_text(encoding='utf-8'))
        genus_name, expected_he = next(iter(supplement['genus_hebrew_names'].items()))
        self.build(scientific_name='A', genus=genus_name, family='Some family', order='Nudibranchia')
        call_command('build_taxonomy_tables', '--apply')
        genus = TaxonGenus.objects.get(name=genus_name)
        self.assertEqual(genus.name_he, expected_he)

    def test_rerun_never_overwrites_a_manual_edit(self):
        self.build(scientific_name='A', order='Nudibranchia', family='Chromodorididae', genus='Chromodoris', phylogenetic_order='313')
        call_command('build_taxonomy_tables', '--apply')

        genus = TaxonGenus.objects.get(name='Chromodoris')
        genus.name_he = 'שם שהמשתמש קבע ידנית'
        genus.taxonomic_order = '999'
        genus.save()
        other_family = TaxonFamily.objects.create(name='Other family')
        genus.family = other_family
        genus.save()

        # A brand new species widens the source data but must not clobber the hand edits above.
        self.build(scientific_name='B', order='Nudibranchia', family='Chromodorididae', genus='Chromodoris', phylogenetic_order='100')
        call_command('build_taxonomy_tables', '--apply')

        genus.refresh_from_db()
        self.assertEqual(genus.name_he, 'שם שהמשתמש קבע ידנית')
        self.assertEqual(genus.taxonomic_order, '999')
        self.assertEqual(genus.family, other_family)

    def test_idempotent_rerun_does_not_duplicate_rows(self):
        self.build(scientific_name='A', order='Nudibranchia', family='Chromodorididae', genus='Chromodoris', phylogenetic_order='313')
        call_command('build_taxonomy_tables', '--apply')
        call_command('build_taxonomy_tables', '--apply')
        # All 16 taxon_order_reference rows are always seeded, regardless of the species data
        # present -- see test_taxon_order_reference_seeds_all_16_rows_unconditionally below.
        self.assertEqual(TaxonOrder.objects.count(), 16)
        self.assertEqual(TaxonFamily.objects.count(), 1)
        self.assertEqual(TaxonGenus.objects.count(), 1)

    def test_defining_sample_field_exists_and_defaults_to_blank(self):
        self.build(scientific_name='A', order='Nudibranchia', family='Chromodorididae', genus='Chromodoris')
        call_command('build_taxonomy_tables', '--apply')
        order = TaxonOrder.objects.get(name='Nudibranchia', sub_order='')
        family = TaxonFamily.objects.get(name='Chromodorididae')
        genus = TaxonGenus.objects.get(name='Chromodoris')
        self.assertIsNone(order.defining_sample_id)
        self.assertIsNone(family.defining_sample_id)
        self.assertIsNone(genus.defining_sample_id)

    def test_sample_kind_supports_the_new_taxon_level_values(self):
        # The whole point of these values existing is that a Sample can be created to
        # represent a genus/family/order heading rather than one specific species.
        self.assertEqual(Sample.Kind.GENUS, 'genus')
        self.assertEqual(Sample.Kind.FAMILY, 'family')
        self.assertEqual(Sample.Kind.ORDER, 'order')

    def test_dry_run_does_not_create_sample_kind_rows(self):
        call_command('build_taxonomy_tables')
        self.assertEqual(SampleKind.objects.count(), 0)

    def test_apply_populates_sample_kind_reference_table(self):
        call_command('build_taxonomy_tables', '--apply')
        codes = set(SampleKind.objects.values_list('code', flat=True))
        self.assertEqual(codes, {'species', 'collection', 'genus', 'family', 'order'})
        genus_kind = SampleKind.objects.get(code='genus')
        self.assertEqual(genus_kind.name, 'סוג')
        self.assertEqual(genus_kind.name_en, 'Genus')

    def test_sample_kind_rerun_does_not_overwrite_a_manual_edit(self):
        call_command('build_taxonomy_tables', '--apply')
        kind = SampleKind.objects.get(code='species')
        kind.name_en = 'A custom label the user typed'
        kind.save()
        call_command('build_taxonomy_tables', '--apply')
        kind.refresh_from_db()
        self.assertEqual(kind.name_en, 'A custom label the user typed')
        self.assertEqual(SampleKind.objects.filter(code='species').count(), 1)

    def test_order_can_have_several_rows_for_different_sub_orders(self):
        # A general check on any order (not Nudibranchia, which is covered by the curated
        # taxon_order_reference tests below): can be manually curated into several suborder
        # rows in admin -- (name, sub_order, taxonomic_order) is the unique triple, not name
        # alone (and not even (name, sub_order) alone -- see the uniqueness tests below).
        self.build(scientific_name='A', order='Testorderia', family='Chromodorididae', genus='Chromodoris')
        call_command('build_taxonomy_tables', '--apply')
        base = TaxonOrder.objects.get(name='Testorderia', sub_order='')

        TaxonOrder.objects.create(name='Testorderia', sub_order='Subgroup A')
        TaxonOrder.objects.create(name='Testorderia', sub_order='Subgroup B')
        self.assertEqual(TaxonOrder.objects.filter(name='Testorderia').count(), 3)

        # a rerun must not touch the hand-added suborder rows or duplicate the base row
        call_command('build_taxonomy_tables', '--apply')
        self.assertEqual(TaxonOrder.objects.filter(name='Testorderia').count(), 3)
        base.refresh_from_db()
        self.assertEqual(base.sub_order, '')

    def test_taxon_order_reference_seeds_all_16_rows_unconditionally(self):
        # taxon_order_reference is the curated, authoritative order/suborder list the user
        # supplied -- it's seeded in full every run, the same way sync_sample_kinds() always
        # populates all 5 SampleKind rows, regardless of what happens to be in Species yet.
        call_command('build_taxonomy_tables', '--apply')
        supplement = json.loads(self.SUPPLEMENT_PATH.read_text(encoding='utf-8'))
        reference = supplement['taxon_order_reference']
        self.assertEqual(TaxonOrder.objects.count(), len(reference))
        self.assertEqual(len(reference), 16)
        sacoglossa = TaxonOrder.objects.get(name='Sacoglossa', sub_order='')
        self.assertEqual(sacoglossa.name_he, 'עלעליות')
        self.assertEqual(sacoglossa.taxonomic_order, '12')

    def test_taxon_order_reference_disambiguates_same_name_sub_order_pair_by_taxonomic_order(self):
        # The real shape of the data the user supplied: Nudibranchia/Doridina alone covers TWO
        # distinct informal groups (taxonomic_order 4 and 5), each with its own Hebrew/English
        # name and superfamilies -- this is exactly why (name, sub_order) alone can no longer
        # be the unique key.
        call_command('build_taxonomy_tables', '--apply')
        cryptobranch = TaxonOrder.objects.get(name='Nudibranchia', sub_order='Doridina', taxonomic_order='4')
        radula_less = TaxonOrder.objects.get(name='Nudibranchia', sub_order='Doridina', taxonomic_order='5')
        self.assertEqual(cryptobranch.name_he, 'חשופיות נדן')
        self.assertEqual(radula_less.name_he, 'חסרי שן')
        self.assertNotEqual(cryptobranch.pk, radula_less.pk)
        # Same for the 3 Cladobranchia groups (armin/dendronotid/aeolid), taxonomic_order 6-8.
        cladobranchia_rows = TaxonOrder.objects.filter(name='Nudibranchia', sub_order='Cladobranchia')
        self.assertEqual(cladobranchia_rows.count(), 3)

    def test_rerun_does_not_duplicate_or_overwrite_taxon_order_reference_rows(self):
        call_command('build_taxonomy_tables', '--apply')
        radula_less = TaxonOrder.objects.get(name='Nudibranchia', sub_order='Doridina', taxonomic_order='5')
        radula_less.name_he = 'שם שהמשתמש קבע ידנית'
        radula_less.save()
        call_command('build_taxonomy_tables', '--apply')
        self.assertEqual(TaxonOrder.objects.filter(name='Nudibranchia', sub_order='Doridina').count(), 2)
        radula_less.refresh_from_db()
        self.assertEqual(radula_less.name_he, 'שם שהמשתמש קבע ידנית')

    def test_family_can_have_several_rows_for_different_sub_families(self):
        self.build(scientific_name='A', order='Nudibranchia', family='Facelinidae', genus='Facelina')
        call_command('build_taxonomy_tables', '--apply')
        base = TaxonFamily.objects.get(name='Facelinidae', sub_family='')

        TaxonFamily.objects.create(name='Facelinidae', sub_family='Facelinoidea')
        TaxonFamily.objects.create(name='Facelinidae', sub_family='Favorininae')
        self.assertEqual(TaxonFamily.objects.filter(name='Facelinidae').count(), 3)

        call_command('build_taxonomy_tables', '--apply')
        self.assertEqual(TaxonFamily.objects.filter(name='Facelinidae').count(), 3)
        base.refresh_from_db()
        self.assertEqual(base.sub_family, '')

    def test_taxonorder_name_sub_order_taxonomic_order_triple_must_be_unique(self):
        TaxonOrder.objects.create(name='Nudibranchia', sub_order='Cladobranchia', taxonomic_order='6')
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                TaxonOrder.objects.create(name='Nudibranchia', sub_order='Cladobranchia', taxonomic_order='6')

    def test_taxonorder_same_name_and_sub_order_can_repeat_with_different_taxonomic_order(self):
        # (name, sub_order) is deliberately NOT unique on its own -- see
        # test_taxon_order_reference_disambiguates_same_name_sub_order_pair_by_taxonomic_order.
        a = TaxonOrder.objects.create(name='Nudibranchia', sub_order='Cladobranchia', taxonomic_order='6')
        b = TaxonOrder.objects.create(name='Nudibranchia', sub_order='Cladobranchia', taxonomic_order='7')
        self.assertNotEqual(a.pk, b.pk)

    def test_family_superfamily_based_linking_disambiguates_among_shared_name_sub_order_rows(self):
        # Chromodorididae and Phyllidiidae are both Nudibranchia/Doridina families, but belong
        # to two DIFFERENT informal groups (taxonomic_order 4 vs 5) -- plain order-text majority
        # voting (both would just say "Nudibranchia") could never tell them apart; superfamily
        # can.
        self.build(scientific_name='A', order='Nudibranchia', family='Chromodorididae', genus='Chromodoris')
        self.build(scientific_name='B', order='Nudibranchia', family='Phyllidiidae', genus='Phyllidia')
        call_command('build_taxonomy_tables', '--apply')
        chromodorididae = TaxonFamily.objects.get(name='Chromodorididae')
        phyllidiidae = TaxonFamily.objects.get(name='Phyllidiidae')
        self.assertEqual(chromodorididae.order.taxonomic_order, '4')
        self.assertEqual(phyllidiidae.order.taxonomic_order, '5')
        self.assertEqual(chromodorididae.superfamily, 'Chromodoridoidea')
        self.assertEqual(phyllidiidae.superfamily, 'Phyllidioidea')

    def test_family_superfamily_based_linking_across_cladobranchia_groups(self):
        # Arminidae/Tritoniidae/Facelinidae are the 3 families standing in for the 3 old
        # "classic" Nudibranchia suborders (Armin/Dendronotid/Aeolid) -- all share
        # sub_order='Cladobranchia' but must resolve to 3 different taxonomic_order rows.
        self.build(scientific_name='A', order='Nudibranchia', family='Arminidae', genus='Armina')
        self.build(scientific_name='B', order='Nudibranchia', family='Tritoniidae', genus='Tritonia')
        self.build(scientific_name='C', order='Nudibranchia', family='Facelinidae', genus='Facelina')
        call_command('build_taxonomy_tables', '--apply')
        self.assertEqual(TaxonFamily.objects.get(name='Arminidae').order.taxonomic_order, '6')
        self.assertEqual(TaxonFamily.objects.get(name='Tritoniidae').order.taxonomic_order, '7')
        self.assertEqual(TaxonFamily.objects.get(name='Facelinidae').order.taxonomic_order, '8')

    def test_family_superfamily_prefers_species_data_over_crosswalk_and_is_never_overwritten(self):
        # Species.superfamily (when present) wins over the family_to_superfamily crosswalk --
        # and once set, a rerun never overwrites it, same as every other field this command fills.
        self.build(scientific_name='A', order='Nudibranchia', family='Chromodorididae', genus='Chromodoris', superfamily='Chromodoridoidea')
        call_command('build_taxonomy_tables', '--apply')
        family = TaxonFamily.objects.get(name='Chromodorididae')
        self.assertEqual(family.superfamily, 'Chromodoridoidea')
        family.superfamily = 'שם שהמשתמש קבע ידנית'
        family.save()
        self.build(scientific_name='B', order='Nudibranchia', family='Chromodorididae', genus='Chromodoris', superfamily='Chromodoridoidea')
        call_command('build_taxonomy_tables', '--apply')
        family.refresh_from_db()
        self.assertEqual(family.superfamily, 'שם שהמשתמש קבע ידנית')

    def test_placeholder_genus_family_inferred_for_haminoeid_and_discodorid(self):
        # A couple of species use an informal placeholder genus (not a real Latin name) with no
        # family text of their own -- their real family is inferred from the placeholder name
        # itself (flagged in build_taxonomy_tables as an explicit inference, not derived data).
        # The real family row needs to already exist from some other, properly-identified
        # species, exactly as it does in the live data.
        self.build(scientific_name='A', order='Cephalaspidea', family='Haminoeidae', genus='Haminoea')
        self.build(scientific_name='B (Haminoeid sp.)', order='Cephalaspidea', family='', genus='Haminoeid')
        call_command('build_taxonomy_tables', '--apply')
        placeholder_genus = TaxonGenus.objects.get(name='Haminoeid')
        self.assertIsNotNone(placeholder_genus.family)
        self.assertEqual(placeholder_genus.family.name, 'Haminoeidae')
