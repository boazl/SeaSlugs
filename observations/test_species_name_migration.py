"""Migration 0038: scientific_name becomes exactly "<genus> <species>" for every species row."""
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class SpeciesNameMigrationTests(TransactionTestCase):
    before = [('observations', '0037_remove_divetrip_sea')]
    after = [('observations', '0038_species_name_from_genus_and_species')]

    def migrate(self, targets):
        executor = MigrationExecutor(connection)
        executor.migrate(targets)
        return executor.loader.project_state(targets).apps

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def test_names_are_made_consistent_and_duplicates_merged_without_losing_references(self):
        old = self.migrate(self.before)
        Sp, S = old.get_model('observations', 'Species'), old.get_model('observations', 'Sample')
        U = old.get_model('auth', 'User')
        owner = U.objects.create(username='o')
        trip = old.get_model('observations', 'DiveTrip').objects.create(title='t')
        blank = Sp.objects.create(scientific_name='Cyerce basi')                       # genus/species blank
        sp_open = Sp.objects.create(scientific_name='Ercolania sp.')
        cf = Sp.objects.create(scientific_name='Chromodoris cf. strigata', genus='Chromodoris', species='strigata', author='Rudman, 1982')
        plain = Sp.objects.create(scientific_name='Chromodoris strigata', genus='Chromodoris', species='strigata', author='Rudman, 1982')
        S.objects.create(owner=owner, species=cf, trip=trip, title='x', kind='species')
        S.objects.create(owner=owner, species=plain, trip=trip, title='y', kind='species')
        withauthor = Sp.objects.create(scientific_name='Berthellina delicata (Pease, 1861)', genus='Berthellina', species='delicata',
                                       author='(Pease, 1861)', source_id='16705')
        S.objects.create(owner=owner, species=withauthor, trip=trip, title='z', kind='species')
        dup = Sp.objects.create(scientific_name='Berthellina delicata', genus='Berthellina', species='delicata',
                                author='(Pease, 1861)', name_he='שם בעברית')
        sp4 = Sp.objects.create(scientific_name='Thuridilla sp. 4 (2021)', genus='Thuridilla', species='sp. 4 (2021)')

        new = self.migrate(self.after)
        Sp2 = new.get_model('observations', 'Species')
        row = lambda s: Sp2.objects.get(pk=s.pk)
        self.assertEqual((row(blank).genus, row(blank).species), ('Cyerce', 'basi'))
        self.assertEqual((row(sp_open).genus, row(sp_open).species), ('Ercolania', 'sp.'))
        # the cf. qualifier moves into the species field and the name stays unique
        self.assertEqual((row(cf).species, row(cf).scientific_name), ('cf. strigata', 'Chromodoris cf. strigata'))
        self.assertEqual(row(plain).scientific_name, 'Chromodoris strigata')
        # author embedded in the name is dropped; the referenced row is kept, the unreferenced twin merged into it
        kept = row(withauthor)
        self.assertEqual((kept.scientific_name, kept.species, kept.source_id, kept.name_he), ('Berthellina delicata', 'delicata', '16705', 'שם בעברית'))
        self.assertFalse(Sp2.objects.filter(pk=dup.pk).exists())
        self.assertEqual(row(sp4).scientific_name, 'Thuridilla sp. 4 (2021)')
        # every row now satisfies name == genus + " " + species, and no name repeats
        for s in Sp2.objects.all():
            self.assertEqual(s.scientific_name, f'{s.genus} {s.species}'.strip())
        names = list(Sp2.objects.values_list('scientific_name', flat=True))
        self.assertEqual(len(names), len(set(names)))
        # samples still point at their species
        self.assertEqual(new.get_model('observations', 'Sample').objects.filter(species_id__in=[cf.pk, plain.pk, withauthor.pk]).count(), 3)
