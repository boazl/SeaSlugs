"""Migration 0068: the superfamilies move into the orders table (one row each, under their order / sub-order,
with their names) and every row gets its rank."""
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

BEFORE = [('observations', '0067_names_and_fossils')]
AFTER = [('observations', '0068_superfamilies_into_orders')]


class SuperfamiliesIntoOrdersMigrationTests(TransactionTestCase):
    def migrate(self, targets):
        executor = MigrationExecutor(connection)
        executor.migrate(targets)
        return executor.loader.project_state(targets).apps

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def test_each_superfamily_becomes_a_row_under_its_sub_order_with_its_names_and_rank(self):
        old = self.migrate(BEFORE)
        Order, Family, Superfamily = (old.get_model('observations', n) for n in ('TaxonOrder', 'TaxonFamily', 'TaxonSuperfamily'))
        base = Order.objects.create(name='Nudibranchia', taxonomic_order='3')
        doridina = Order.objects.create(name='Nudibranchia', sub_order='Doridina', taxonomic_order='4')
        sacoglossa = Order.objects.create(name='Sacoglossa', taxonomic_order='12')
        Family.objects.create(name='Chromodorididae', order=doridina, superfamily='Chromodoridoidea')
        Family.objects.create(name='Doridoxidae', order=base, superfamily='Doridoxoidea')
        Family.objects.create(name='Plakobranchidae', order=sacoglossa, superfamily='Plakobranchoidea')
        Superfamily.objects.create(name='Chromodoridoidea', name_he='חשופיות נדן', name_en='Chromodorid dorid nudibranchs')
        Superfamily.objects.create(name='Doridoxoidea', name_he='דורידוקסואידאה')
        Superfamily.objects.create(name='Plakobranchoidea')
        Superfamily.objects.create(name='Orphanoidea')              # no family: no place in the tree

        new = self.migrate(AFTER)
        Order = new.get_model('observations', 'TaxonOrder')
        rows = {(o.name, o.sub_order, o.superfamily): o for o in Order.objects.all()}
        self.assertEqual(set(rows), {('Nudibranchia', '', ''), ('Nudibranchia', 'Doridina', ''), ('Sacoglossa', '', ''),
                                     ('Nudibranchia', 'Doridina', 'Chromodoridoidea'), ('Nudibranchia', '', 'Doridoxoidea'),
                                     ('Sacoglossa', '', 'Plakobranchoidea')})
        chromodoris = rows[('Nudibranchia', 'Doridina', 'Chromodoridoidea')]
        self.assertEqual((chromodoris.rank, chromodoris.name_he, chromodoris.name_en, chromodoris.taxonomic_order),
                         ('superfamily', 'חשופיות נדן', 'Chromodorid dorid nudibranchs', '4'))
        self.assertEqual(rows[('Nudibranchia', 'Doridina', '')].rank, 'suborder')
        self.assertEqual(rows[('Nudibranchia', '', '')].rank, 'order')
        self.assertEqual(rows[('Nudibranchia', '', 'Doridoxoidea')].taxonomic_order, '3')
        self.assertEqual(new.get_model('observations', 'TaxonFamily').objects.get(name='Chromodorididae').order_id, rows[('Nudibranchia', 'Doridina', '')].pk)
        with self.assertRaises(LookupError):
            new.get_model('observations', 'TaxonSuperfamily')      # the old table is gone

    def test_going_back_restores_the_superfamily_table(self):
        old = self.migrate(BEFORE)
        Order, Family = old.get_model('observations', 'TaxonOrder'), old.get_model('observations', 'TaxonFamily')
        Family.objects.create(name='Aplysiidae', order=Order.objects.create(name='Aplysiida'), superfamily='Aplysioidea')
        old.get_model('observations', 'TaxonSuperfamily').objects.create(name='Aplysioidea', name_he='ארנבים')
        self.migrate(AFTER)
        back = self.migrate(BEFORE)
        self.assertEqual(list(back.get_model('observations', 'TaxonSuperfamily').objects.values_list('name', 'name_he')), [('Aplysioidea', 'ארנבים')])
        self.assertEqual(list(back.get_model('observations', 'TaxonOrder').objects.values_list('name', 'sub_order')), [('Aplysiida', '')])
