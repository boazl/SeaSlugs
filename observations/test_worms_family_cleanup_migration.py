"""Migration 0066: families follow WoRMS -- synonyms merged, superfamilies corrected, species text columns aligned."""
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

BEFORE = [('observations', '0065_taxon_superfamilies_and_worms_suborders')]
AFTER = [('observations', '0066_worms_family_cleanup')]


class WormsFamilyCleanupMigrationTests(TransactionTestCase):
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
        Order, Family, Genus, Species = (apps.get_model('observations', n) for n in ('TaxonOrder', 'TaxonFamily', 'TaxonGenus', 'Species'))
        base = Order.objects.create(name='Nudibranchia', sub_order='', taxonomic_order='3')
        clado = Order.objects.create(name='Nudibranchia', sub_order='Cladobranchia', taxonomic_order='6')
        doridina = Order.objects.create(name='Nudibranchia', sub_order='Doridina', taxonomic_order='4')
        cephalaspidea = Order.objects.create(name='Cephalaspidea', taxonomic_order='2')
        fam = lambda name, order, sf='': Family.objects.create(name=name, order=order, superfamily=sf)
        flab, cory = fam('Flabellinidae', clado, 'Fionoidea'), fam('Coryphellidae', clado, 'Fionoidea')
        pise, unid = fam('Piseinotecidae', clado, 'Fionoidea'), fam('Unidentiidae', clado, 'Fionoidea')
        gast, gaste = fam('Gastropteridae', cephalaspidea, 'Philinoidea'), fam('Gasteropteridae', cephalaspidea, 'Philinoidea')
        poly, okad = fam('Polyceridae', doridina, 'Polyceroidea'), fam('Okadaiidae', base)
        dori, goni = fam('Doridomorphidae', clado, 'Arminoidea'), fam('Goniaeolididae', base)
        fam('Eubranchidae', clado, 'Fionoidea')
        fam('Heroidae', base)
        for name, family in (('Coryphella', cory), ('Flabellina', flab), ('Unidentia', unid), ('Piseinotecus', pise), ('Gasteropteron', gaste),
                             ('Gastropteron', gast), ('Vayssierea', okad), ('Polycera', poly), ('Doridomorpha', dori), ('Goniaeolis', goni)):
            Genus.objects.create(name=name, family=family)
        S = lambda genus, **kw: Species.objects.create(scientific_name=f'{genus} test', genus=genus, species='test', **kw)
        S('Coryphella', family='Coryphellidae', order='Doridida', superfamily='Fionoidea')
        S('Vayssierea', family='Okadaiidae', order='Nudibranchia')
        S('Gasteropteron', family='Gasteropteridae', order='Not assigned')
        S('Polycera', order='')
        S('Doridomorpha', family='Doridomorphidae', order='Nudibranchia', superfamily='Arminoidea')
        S('Annulorhina')

    def test_merges_superfamilies_and_species_text(self):
        self.build(self.migrate(BEFORE))
        new = self.migrate(AFTER)
        Family, Genus, Species, Superfamily = (new.get_model('observations', n) for n in ('TaxonFamily', 'TaxonGenus', 'Species', 'TaxonSuperfamily'))
        for gone in ('Coryphellidae', 'Unidentiidae', 'Gasteropteridae', 'Okadaiidae'):
            self.assertFalse(Family.objects.filter(name=gone).exists(), gone)
        self.assertEqual(Genus.objects.get(name='Coryphella').family.name, 'Flabellinidae')
        self.assertEqual(Genus.objects.get(name='Unidentia').family.name, 'Piseinotecidae')
        self.assertEqual(Genus.objects.get(name='Gasteropteron').family.name, 'Gastropteridae')
        self.assertEqual(Genus.objects.get(name='Vayssierea').family.name, 'Polyceridae')
        coryphella = Species.objects.get(genus='Coryphella')
        self.assertEqual((coryphella.order, coryphella.family, coryphella.superfamily), ('Nudibranchia', 'Flabellinidae', 'Fionoidea'))
        okadaia = Species.objects.get(genus='Vayssierea')
        self.assertEqual((okadaia.family, okadaia.superfamily), ('Polyceridae', 'Polyceroidea'))
        self.assertEqual(Species.objects.get(genus='Gasteropteron').order, 'Cephalaspidea')
        polycera = Species.objects.get(genus='Polycera')
        self.assertEqual((polycera.order, polycera.family), ('Nudibranchia', 'Polyceridae'))   # blank text filled from the genus

        heterodoridoidea = Family.objects.get(name='Doridomorphidae')
        self.assertEqual((heterodoridoidea.superfamily, heterodoridoidea.order.sub_order), ('Heterodoridoidea', 'Cladobranchia'))
        self.assertTrue(Superfamily.objects.filter(name='Heterodoridoidea').exists())
        goni = Family.objects.get(name='Goniaeolididae')
        self.assertEqual((goni.superfamily, goni.order.sub_order), ('Proctonotoidea', 'Cladobranchia'))
        self.assertEqual(Species.objects.get(genus='Doridomorpha').superfamily, 'Heterodoridoidea')
        self.assertEqual(Family.objects.get(name='Heroidae').order.sub_order, '')                # incertae sedis stays put
        annulorhina = Species.objects.get(genus='Annulorhina')
        self.assertEqual((annulorhina.family, annulorhina.order), ('Eubranchidae', 'Nudibranchia'))
