"""Regression tests for migration 0032, which backfills a bare "[Genus] sp." catalog row for
every genus that doesn't already have one -- so folder-import and the observation form's
species-matching always have a fallback row to match a genus-only identification against,
exactly like the handful of genera that already had one by hand. These tests exercise the
migration's fix function directly (the same technique Django's own migration runner uses to
import a numbered migration module -- see test_species_areas.py's RegionCountryMismatchDataFixTests
and test_taxonomy.py for the same pattern) rather than replaying the whole migration history."""
import importlib

from django.apps import apps as live_apps
from django.test import TestCase

from .models import Species


class GenusPlaceholderMigrationTests(TestCase):
    def create(self, genus, species, order='', family='', superfamily='', phylogenetic_order=''):
        name = f'{genus} {species}'.strip()
        return Species.objects.create(scientific_name=name, genus=genus, species=species,
            order=order, family=family, superfamily=superfamily, phylogenetic_order=phylogenetic_order)

    def run_migration(self):
        module = importlib.import_module('observations.migrations.0032_create_missing_genus_sp_placeholders')
        module.create_missing_genus_sp_placeholders(live_apps, None)

    def test_creates_a_bare_placeholder_for_a_genus_that_has_none(self):
        self.create('Newgenus', 'alpha', order='Nudibranchia', family='Newfamilyidae')
        self.run_migration()
        placeholder = Species.objects.get(scientific_name='Newgenus sp.')
        self.assertEqual(placeholder.genus, 'Newgenus')
        self.assertEqual(placeholder.species, 'sp.')
        self.assertEqual(placeholder.order, 'Nudibranchia')
        self.assertEqual(placeholder.family, 'Newfamilyidae')

    def test_leaves_a_genus_alone_when_it_already_has_a_properly_columned_sp_row(self):
        self.create('Existing', 'alpha')
        self.create('Existing', 'sp.')
        self.run_migration()
        self.assertEqual(Species.objects.filter(genus='Existing').count(), 2)

    def test_does_not_duplicate_a_legacy_row_that_only_has_the_full_name_in_scientific_name(self):
        # A handful of legacy rows carry "<Genus> sp." as their scientific_name but have blank
        # genus/species columns (never backfilled) -- these already ARE that genus's
        # placeholder in every way a person or the site would recognise, so the migration must
        # not create a second, properly-columned "<Genus> sp." row alongside it.
        self.create('Legacy', 'alpha', order='Nudibranchia')
        Species.objects.create(scientific_name='Legacy sp.', genus='', species='')
        self.run_migration()
        self.assertEqual(Species.objects.filter(scientific_name='Legacy sp.').count(), 1)

    def test_ignores_rows_with_a_blank_genus(self):
        Species.objects.create(scientific_name='Unclassified thing', genus='', species='thing')
        self.run_migration()
        self.assertFalse(Species.objects.filter(scientific_name__iexact='sp.').exists())
        self.assertEqual(Species.objects.count(), 1)

    def test_derives_classification_fields_by_majority_vote_and_minimum_phylogenetic_order(self):
        # Three of a genus's own species disagree on order/family/superfamily (data-entry
        # drift in the source spreadsheet) -- majority vote should win, matching the technique
        # build_taxonomy_tables.py already uses to derive TaxonOrder/TaxonFamily/TaxonGenus from
        # Species. phylogenetic_order should take the minimum non-blank value (build_taxonomy_
        # tables.py's own _min_phylo), so the placeholder sorts alongside its genus-mates.
        self.create('Voting', 'one', order='Nudibranchia', family='Aeolidiidae', superfamily='Aeolidioidea', phylogenetic_order='305')
        self.create('Voting', 'two', order='Nudibranchia', family='Aeolidiidae', superfamily='Aeolidioidea', phylogenetic_order='310')
        self.create('Voting', 'three', order='Cephalaspidea', family='Aplysiidae', superfamily='', phylogenetic_order='')
        self.run_migration()
        placeholder = Species.objects.get(scientific_name='Voting sp.')
        self.assertEqual(placeholder.order, 'Nudibranchia')
        self.assertEqual(placeholder.family, 'Aeolidiidae')
        self.assertEqual(placeholder.superfamily, 'Aeolidioidea')
        self.assertEqual(placeholder.phylogenetic_order, '305')

    def test_creates_one_placeholder_per_genus_in_a_mixed_batch(self):
        self.create('Alpha', 'one')
        self.create('Alpha', 'two')
        self.create('Beta', 'one')
        self.create('Beta', 'sp.')  # Beta already has its placeholder
        self.run_migration()
        self.assertTrue(Species.objects.filter(scientific_name='Alpha sp.').exists())
        self.assertEqual(Species.objects.filter(genus='Beta').count(), 2)
