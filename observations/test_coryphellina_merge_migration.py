"""Migration 0062: the Philippines spelling fix and the merge of the duplicate "Coryphellina sp. B"."""
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

BEFORE = [('observations', '0061_trip_codes')]
AFTER = [('observations', '0062_unify_coryphellina_sp_b_and_fix_philippines')]
OLD_SLUG = 'coryphellina-sp-b-phillipines-indo-pacific-south-china-sea-2'
KEPT_SLUG = 'coryphellina-sp-b-phillipines-indo-pacific-south-china-sea'


class CoryphellinaMergeMigrationTests(TransactionTestCase):
    def migrate(self, targets):
        executor = MigrationExecutor(connection)
        executor.migrate(targets)
        return executor.loader.project_state(targets).apps

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def build(self, apps, same_sea=True):
        M = lambda name: apps.get_model('observations', name)
        owner = apps.get_model('auth', 'User').objects.create(username='o')
        country = M('Country').objects.create(name='פיליפינים', name_en='Phillipines')
        sea = M('Sea').objects.create(name='Indo Pacific', name_en='Indo Pacific - South China Sea')
        other_sea = sea if same_sea else M('Sea').objects.create(name='Other', name_en='Other sea')
        region = M('Region').objects.create(name='Anilao', country=country, sea=sea)
        region2 = M('Region').objects.create(name='Elsewhere', country=country, sea=other_sea)
        trip = M('DiveTrip').objects.create(title='t1', country=country, region=region, year=2025)
        trip2 = M('DiveTrip').objects.create(title='t2', country=country, region=region2, year=2025)
        keep = M('Species').objects.create(scientific_name='Coryphellina sp. B', genus='Coryphellina', species='sp. B')
        dup = M('Species').objects.create(scientific_name='Coryphellina sp.', genus='Coryphellina', species='sp.')
        s_keep = M('Sample').objects.create(owner=owner, species=keep, trip=trip, title='a', kind='species', status='published')
        s_dup = M('Sample').objects.create(owner=owner, species=dup, trip=trip2, title='b', kind='species',
                                           status='published', undetermined_variant='B')
        a_keep = M('SpeciesArea').objects.create(species=keep, country=country, sea=sea, slug=KEPT_SLUG, defining_sample=s_keep)
        a_dup = M('SpeciesArea').objects.create(species=dup, country=country, sea=other_sea, undetermined_variant='B',
                                                slug=OLD_SLUG, defining_sample=s_dup)
        return country, keep, dup, s_keep, s_dup, a_keep, a_dup

    def test_the_variant_observation_joins_sp_b_and_the_duplicate_page_and_species_are_removed(self):
        old = self.migrate(BEFORE)
        country, keep, dup, s_keep, s_dup, a_keep, a_dup = self.build(old)
        new = self.migrate(AFTER)
        M = lambda name: new.get_model('observations', name)
        moved = M('Sample').objects.get(pk=s_dup.pk)
        self.assertEqual((moved.species_id, moved.undetermined_variant), (keep.pk, ''))
        self.assertFalse(M('SpeciesArea').objects.filter(pk=a_dup.pk).exists())
        self.assertFalse(M('Species').objects.filter(pk=dup.pk).exists())
        # the surviving population page and its original sample are untouched
        self.assertEqual(M('SpeciesArea').objects.get(species_id=keep.pk).slug, KEPT_SLUG)
        self.assertEqual(M('Sample').objects.get(pk=s_keep.pk).species_id, keep.pk)
        self.assertEqual(M('Country').objects.get(pk=country.pk).name_en, 'Philippines')

    def test_nothing_is_merged_when_the_target_page_for_that_country_and_sea_does_not_exist(self):
        old = self.migrate(BEFORE)
        country, keep, dup, s_keep, s_dup, a_keep, a_dup = self.build(old, same_sea=False)
        new = self.migrate(AFTER)
        M = lambda name: new.get_model('observations', name)
        self.assertEqual(M('Sample').objects.get(pk=s_dup.pk).species_id, dup.pk)
        self.assertTrue(M('Species').objects.filter(pk=dup.pk).exists())
        self.assertTrue(M('SpeciesArea').objects.filter(pk=a_dup.pk).exists())
        self.assertEqual(M('Country').objects.get(pk=country.pk).name_en, 'Philippines')   # the spelling fix is independent

    def test_a_database_without_these_rows_is_unchanged(self):
        self.migrate(BEFORE)
        new = self.migrate(AFTER)
        self.assertEqual(new.get_model('observations', 'Species').objects.count(), 0)
