"""Migration 0069: samples' family / order text follows the taxonomy tables."""
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

BEFORE = [('observations', '0068_superfamilies_into_orders')]
AFTER = [('observations', '0069_samples_follow_taxonomy')]


class SamplesFollowTaxonomyMigrationTests(TransactionTestCase):
    def migrate(self, targets):
        executor = MigrationExecutor(connection)
        executor.migrate(targets)
        return executor.loader.project_state(targets).apps

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def test_genus_species_and_merged_family_samples_are_updated(self):
        old = self.migrate(BEFORE)
        Order, Family, Genus, Sample, User = (old.get_model(a, n) for a, n in (('observations', 'TaxonOrder'), ('observations', 'TaxonFamily'), ('observations', 'TaxonGenus'), ('observations', 'Sample'), ('auth', 'User')))
        sacoglossa = Order.objects.create(name='Sacoglossa')
        nudi = Order.objects.create(name='Nudibranchia')
        Genus.objects.create(name='Cyerce', family=Family.objects.create(name='Caliphyllidae', order=sacoglossa))
        Family.objects.create(name='Flabellinidae', order=nudi)
        owner = User.objects.create(username='u')
        stale_genus = Sample.objects.create(owner=owner, kind='genus', genus='Cyerce', family='Hermaeidae', order='Sacoglossa')
        stale_species = Sample.objects.create(owner=owner, kind='species', genus='Cyerce', family='Hermaeidae', order='')
        merged = Sample.objects.create(owner=owner, kind='family', family='Calmidae', order='Nudibranchia')
        other = Sample.objects.create(owner=owner, kind='genus', genus='Unknownus', family='Whatever', order='Nowhere')

        new = self.migrate(AFTER)
        Sample = new.get_model('observations', 'Sample')
        get = lambda s: Sample.objects.values_list('family', 'order').get(pk=s.pk)
        self.assertEqual(get(stale_genus), ('Caliphyllidae', 'Sacoglossa'))
        self.assertEqual(get(stale_species), ('Caliphyllidae', 'Sacoglossa'))
        self.assertEqual(get(merged), ('Flabellinidae', 'Nudibranchia'))
        self.assertEqual(get(other), ('Whatever', 'Nowhere'))          # a genus with no row is left alone
