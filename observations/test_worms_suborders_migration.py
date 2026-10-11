"""Migration 0065: Nudibranchia follows WoRMS -- informal groups removed, families on their WoRMS sub-order,
superfamily names with Hebrew names."""
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

BEFORE = [('observations', '0064_species_list_check_fixes')]
AFTER = [('observations', '0065_taxon_superfamilies_and_worms_suborders')]


class WormsSubordersMigrationTests(TransactionTestCase):
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
        Order, Family, Species = (apps.get_model('observations', n) for n in ('TaxonOrder', 'TaxonFamily', 'Species'))
        group = lambda he, sub, to, **kw: Order.objects.create(
            name='Nudibranchia', name_he=he, name_en='informal', sub_order=sub, taxonomic_order=to, description_he=f'text of {he}', **kw)
        rows = {
            'phanero': group('גלויי זים', '', '3'), 'crypto': group('חשופיות נדן', 'Doridina', '4'),
            'radula': group('חסרי שן', 'Doridina', '5'), 'armin': group('חשופיות מגן', 'Cladobranchia', '6'),
            'tree': group('חשופיות אילן', 'Cladobranchia', '7'), 'aeolid': group('חשופיות אונות', 'Cladobranchia', '8'),
        }
        fam = lambda name, row, sf: Family.objects.create(name=name, order=rows[row], superfamily=sf)
        families = {
            'Polyceridae': fam('Polyceridae', 'phanero', 'Polyceroidea'),
            'Doridoxidae': fam('Doridoxidae', 'phanero', 'Doridoxoidea'),
            'Heroidae': fam('Heroidae', 'phanero', '\\N'),
            'Chromodorididae': fam('Chromodorididae', 'crypto', 'Chromodoridoidea'),
            'Phyllidiidae': fam('Phyllidiidae', 'radula', 'Phyllidioidea'),
            'Arminidae': fam('Arminidae', 'armin', 'Arminoidea'),
            'Tritoniidae': fam('Tritoniidae', 'tree', 'Tritonioidea'),
            'Notaeolidiidae': fam('Notaeolidiidae', 'aeolid', 'Aeolidioidea'),     # WoRMS: Fionoidea
            'Embletoniidae': fam('Embletoniidae', 'aeolid', 'Fionoidea'),          # WoRMS: Embletonioidea
        }
        Species.objects.create(scientific_name='Notaeolidia test', genus='Notaeolidia', species='test', family='Notaeolidiidae', superfamily='Aeolidioidea')
        return rows, families

    def test_groups_are_removed_and_families_follow_their_worms_sub_order(self):
        old = self.migrate(BEFORE)
        self.build(old)
        new = self.migrate(AFTER)
        Order, Family, Species = (new.get_model('observations', n) for n in ('TaxonOrder', 'TaxonFamily', 'Species'))
        rows = {r.sub_order: r for r in Order.objects.filter(name='Nudibranchia')}
        self.assertEqual(sorted(rows), ['', 'Cladobranchia', 'Doridina'])
        self.assertEqual((rows[''].name_he, rows[''].name_en), ('חשופיות', 'Nudibranchs'))
        for row in rows.values():
            self.assertEqual(row.description_he, '')              # the groups' texts are gone
        sub = lambda name: Family.objects.get(name=name).order.sub_order
        for name in ('Polyceridae', 'Chromodorididae', 'Phyllidiidae'):
            self.assertEqual(sub(name), 'Doridina', name)
        for name in ('Arminidae', 'Tritoniidae', 'Notaeolidiidae', 'Embletoniidae'):
            self.assertEqual(sub(name), 'Cladobranchia', name)
        for name in ('Doridoxidae', 'Heroidae'):                  # WoRMS gives them no sub-order
            self.assertEqual(sub(name), '', name)

    def test_superfamilies_are_corrected_cleaned_and_named(self):
        old = self.migrate(BEFORE)
        self.build(old)
        new = self.migrate(AFTER)
        Family, Species, Superfamily = (new.get_model('observations', n) for n in ('TaxonFamily', 'Species', 'TaxonSuperfamily'))
        self.assertEqual(Family.objects.get(name='Notaeolidiidae').superfamily, 'Fionoidea')
        self.assertEqual(Species.objects.get(scientific_name='Notaeolidia test').superfamily, 'Fionoidea')
        self.assertEqual(Family.objects.get(name='Embletoniidae').superfamily, 'Embletonioidea')
        self.assertEqual(Family.objects.get(name='Heroidae').superfamily, '')            # the import artifact "\N"
        names = {s.name: s.name_he for s in Superfamily.objects.all()}
        self.assertNotIn('\\N', names)
        self.assertEqual(names['Phyllidioidea'], 'חסרי שן')                                # a group that covered one superfamily
        self.assertEqual(names['Arminoidea'], 'חשופיות מגן – ארמינואידאה')                 # group name + the superfamily in Hebrew letters
        self.assertEqual(names['Doridoxoidea'], '')

    def test_it_is_harmless_without_nudibranchia_rows(self):
        self.migrate(BEFORE)
        self.migrate(AFTER)
