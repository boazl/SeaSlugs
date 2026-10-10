"""Migration 0064: catalog fixes after checking the Israeli species list (pellucida duplicate, Cyerce family,
legacy taxonomy fields, Hebrew names, migrant flags)."""
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

BEFORE = [('observations', '0063_home_text')]
AFTER = [('observations', '0064_species_list_check_fixes')]


class SpeciesListCheckMigrationTests(TransactionTestCase):
    def migrate(self, targets):
        executor = MigrationExecutor(connection)
        executor.migrate(targets)
        return executor.loader.project_state(targets).apps

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def build(self, apps):
        M = lambda name: apps.get_model('observations', name)
        nudi = M('TaxonOrder').objects.create(name='Nudibranchia')
        saco = M('TaxonOrder').objects.create(name='Sacoglossa')
        chromo = M('TaxonFamily').objects.create(name='Hexabranchidae', order=nudi, superfamily='Chromodoridoidea')
        herm = M('TaxonFamily').objects.create(name='Hermaeidae', order=saco, superfamily='Plakobranchoidea', taxonomic_order='C05')
        M('TaxonGenus').objects.create(name='Hexabranchus', family=chromo)
        M('TaxonGenus').objects.create(name='Cyerce', family=herm)
        S = lambda sci, genus, species, **kw: M('Species').objects.create(
            scientific_name=sci, genus=genus, species=species, **kw)
        return {
            'hexa': S('Hexabranchus sanguineus', 'Hexabranchus', 'sanguineus'),
            'cyerce': S('Cyerce elegans', 'Cyerce', 'elegans'),
            'cyerce2': S('Cyerce nigra', 'Cyerce', 'nigra', family='Hermaeidae', order='Not assigned'),
            'okenia': S('Okenia pellucida', 'Okenia', 'pellucida', name_en='Translucent okenia'),
            'bermudella': S('Bermudella pellucida', 'Bermudella', 'pellucida'),
            'caloria': S('Caloria militaris', 'Caloria', 'militaris', name_he='קלוריה צבאית'),
            'cratena': S('Cratena peregrina', 'Cratena', 'peregrina', name_he='שם ידני'),
        }

    def test_everything_is_fixed(self):
        old = self.migrate(BEFORE)
        rows = self.build(old)
        new = self.migrate(AFTER)
        M = lambda name: new.get_model('observations', name)
        get = lambda key: M('Species').objects.get(pk=rows[key].pk)

        hexa = get('hexa')
        self.assertEqual((hexa.order, hexa.family, hexa.superfamily), ('Nudibranchia', 'Hexabranchidae', 'Chromodoridoidea'))
        self.assertEqual(hexa.name_he, 'רקדנית ספרדייה')
        self.assertTrue(hexa.is_migrant)

        cal = M('TaxonFamily').objects.get(name='Caliphyllidae')
        self.assertEqual(M('TaxonGenus').objects.get(name='Cyerce').family_id, cal.pk)
        self.assertEqual((cal.order.name, cal.superfamily, cal.taxonomic_order), ('Sacoglossa', 'Plakobranchoidea', 'C05'))
        for key in ('cyerce', 'cyerce2'):
            self.assertEqual(get(key).family, 'Caliphyllidae')
        self.assertEqual(get('cyerce').order, 'Sacoglossa')
        self.assertEqual(get('cyerce2').order, 'Not assigned')  # only the listed species are completed

    def test_the_okenia_duplicate_is_unified_into_bermudella(self):
        old = self.migrate(BEFORE)
        rows = self.build(old)
        new = self.migrate(AFTER)
        Species = new.get_model('observations', 'Species')
        self.assertFalse(Species.objects.filter(pk=rows['okenia'].pk).exists())
        kept = Species.objects.get(pk=rows['bermudella'].pk)
        self.assertEqual(kept.name_en, 'Translucent okenia')
        self.assertFalse(kept.is_migrant)  # no tropical record yet

    def test_hebrew_names_are_only_filled_or_renamed_where_expected(self):
        old = self.migrate(BEFORE)
        rows = self.build(old)
        new = self.migrate(AFTER)
        Species = new.get_model('observations', 'Species')
        self.assertEqual(Species.objects.get(pk=rows['caloria'].pk).name_he, 'חשופית צבאית')
        cratena = Species.objects.get(pk=rows['cratena'].pk)
        self.assertEqual(cratena.name_he, 'שם ידני')   # a hand-entered name is never overwritten
        self.assertFalse(cratena.is_migrant)           # temperate Atlantic-Mediterranean species

    def test_a_pellucida_row_that_is_still_referenced_is_kept(self):
        old = self.migrate(BEFORE)
        rows = self.build(old)
        M = lambda name: old.get_model('observations', name)
        owner = old.get_model('auth', 'User').objects.create(username='o')
        M('Sample').objects.create(owner=owner, species=rows['okenia'], title='x', kind='species', status='draft')
        new = self.migrate(AFTER)
        self.assertTrue(new.get_model('observations', 'Species').objects.filter(pk=rows['okenia'].pk).exists())
