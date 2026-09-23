import json
from pathlib import Path
from unittest.mock import patch
from django.core.management import call_command
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
        defaults = dict(order='', family='', genus='', phylogenetic_order='')
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

        order = TaxonOrder.objects.get(name='Nudibranchia')
        family = TaxonFamily.objects.get(name='Chromodorididae')
        genus = TaxonGenus.objects.get(name='Chromodoris')
        self.assertEqual(family.order, order)
        self.assertEqual(genus.family, family)
        # taxonomic_order takes the lowest (earliest) value seen among the group's species
        self.assertEqual(order.taxonomic_order, '313')
        self.assertEqual(family.taxonomic_order, '313')
        self.assertEqual(genus.taxonomic_order, '313')

    def test_blank_and_not_assigned_order_values_are_skipped(self):
        self.build(scientific_name='A', order='Not assigned', family='Acteonidae', genus='Acteon')
        self.build(scientific_name='B', order='', family='', genus='')
        call_command('build_taxonomy_tables', '--apply')
        self.assertEqual(TaxonOrder.objects.count(), 0)
        family = TaxonFamily.objects.get(name='Acteonidae')
        self.assertIsNone(family.order)
        genus = TaxonGenus.objects.get(name='Acteon')
        self.assertEqual(genus.family, family)

    def test_family_order_conflict_resolved_by_majority(self):
        # Mirrors real data: most species of this family are tagged with the modern order,
        # a couple still carry the legacy one -- the majority should win.
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
        order = TaxonOrder.objects.get(name='Nudibranchia')
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
        self.assertEqual(TaxonOrder.objects.count(), 1)
        self.assertEqual(TaxonFamily.objects.count(), 1)
        self.assertEqual(TaxonGenus.objects.count(), 1)

    def test_defining_sample_field_exists_and_defaults_to_blank(self):
        self.build(scientific_name='A', order='Nudibranchia', family='Chromodorididae', genus='Chromodoris')
        call_command('build_taxonomy_tables', '--apply')
        order = TaxonOrder.objects.get(name='Nudibranchia')
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

