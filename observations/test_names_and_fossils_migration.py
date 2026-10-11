"""Migration 0067: fossil family removed, empty Hebrew / English names filled (existing names untouched)."""
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

BEFORE = [('observations', '0066_worms_family_cleanup')]
AFTER = [('observations', '0067_names_and_fossils')]


class NamesAndFossilsMigrationTests(TransactionTestCase):
    def migrate(self, targets):
        executor = MigrationExecutor(connection)
        executor.migrate(targets)
        return executor.loader.project_state(targets).apps

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def test_fossils_removed_and_names_filled_without_overwriting(self):
        old = self.migrate(BEFORE)
        Order, Family, Genus, Species, Superfamily = (old.get_model('observations', n) for n in ('TaxonOrder', 'TaxonFamily', 'TaxonGenus', 'Species', 'TaxonSuperfamily'))
        acteon = Order.objects.create(name='Acteonoidea', taxonomic_order='12')
        doridina = Order.objects.create(name='Nudibranchia', sub_order='Doridina', taxonomic_order='4')
        fossil = Family.objects.create(name='Cylindrobullinidae', order=acteon, superfamily='Acteonoidea')
        Genus.objects.create(name='Ceritellopsis', family=fossil)
        Species.objects.create(scientific_name='Ceritellopsis parvula', genus='Ceritellopsis', species='parvula', family='Cylindrobullinidae')
        chromo = Family.objects.create(name='Chromodorididae', order=doridina, superfamily='Chromodoridoidea', name_he='זריות')
        Family.objects.create(name='Polyceridae', order=doridina, superfamily='Polyceroidea')
        Genus.objects.create(name='Biuve', family=chromo)
        Genus.objects.create(name='Hypselodoris', family=chromo, name_he='מתנה גבוהה')
        Superfamily.objects.create(name='Polyceroidea', name_he='גלויי זים – פוליצרואידאה')
        Superfamily.objects.create(name='Aplysioidea')

        new = self.migrate(AFTER)
        Order, Family, Genus, Species, Superfamily = (new.get_model('observations', n) for n in ('TaxonOrder', 'TaxonFamily', 'TaxonGenus', 'Species', 'TaxonSuperfamily'))
        self.assertFalse(Family.objects.filter(name='Cylindrobullinidae').exists())
        self.assertFalse(Genus.objects.filter(name='Ceritellopsis').exists())
        self.assertFalse(Species.objects.filter(genus='Ceritellopsis').exists())
        self.assertEqual(Family.objects.get(name='Chromodorididae').name_he, 'זריות')                  # kept
        self.assertEqual(Family.objects.get(name='Chromodorididae').name_en, 'Chromodorid nudibranchs')  # filled
        self.assertEqual(Family.objects.get(name='Polyceridae').name_he, 'פוליצרידים')
        self.assertEqual(Genus.objects.get(name='Hypselodoris').name_he, 'מתנה גבוהה')                  # kept
        self.assertEqual(Genus.objects.get(name='Biuve').name_he, 'ביובה')
        self.assertEqual(Superfamily.objects.get(name='Polyceroidea').name_he, 'גלויי זים – פוליצרואידאה')  # kept
        self.assertEqual(Superfamily.objects.get(name='Polyceroidea').name_en, 'Polycerid dorid nudibranchs')
        self.assertEqual(Superfamily.objects.get(name='Aplysioidea').name_he, 'ארנבים – אפליסיואידאה')
        self.assertEqual(Order.objects.get(name='Nudibranchia', sub_order='Doridina').name_en, 'Dorid nudibranchs')

    def test_fossil_species_without_observations_are_removed(self):
        old = self.migrate(BEFORE)
        Order, Family, Genus, Species = (old.get_model('observations', n) for n in ('TaxonOrder', 'TaxonFamily', 'TaxonGenus', 'Species'))
        acteon = Order.objects.create(name='Acteonoidea', taxonomic_order='12')
        fossil = Family.objects.create(name='Cylindrobullinidae', order=acteon)
        Genus.objects.create(name='Hamlinia', family=fossil)
        Species.objects.create(scientific_name='Hamlinia eliai', genus='Hamlinia', species='eliai', family='Cylindrobullinidae')
        new = self.migrate(AFTER)
        self.assertFalse(new.get_model('observations', 'Species').objects.filter(genus='Hamlinia').exists())
