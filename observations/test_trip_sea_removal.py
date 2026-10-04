"""DiveTrip.sea is gone -- a trip's sea is its region's sea (Region.sea is the single source of
truth). Covers the data migration that keeps sea-only trips that have observations in the
gallery, and the schema step that drops the column."""
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class TripSeaRemovalMigrationTests(TransactionTestCase):
    before = [('observations', '0035_remove_trip_photographer')]
    after = [('observations', '0036_give_sea_only_trips_a_region')]
    final = [('observations', '0037_remove_divetrip_sea')]

    def migrate(self, targets):
        executor = MigrationExecutor(connection)
        executor.migrate(targets)
        return executor.loader.project_state(targets).apps

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def test_sea_only_trips_with_observations_get_a_region_and_nothing_else_changes(self):
        old = self.migrate(self.before)
        U = old.get_model('auth', 'User')
        Country, Sea, Region = (old.get_model('observations', n) for n in ('Country', 'Sea', 'Region'))
        T, S = old.get_model('observations', 'DiveTrip'), old.get_model('observations', 'Sample')
        owner = U.objects.create(username='o')
        fiji, israel = Country.objects.create(name='פיג׳י'), Country.objects.create(name='ישראל')
        coral, med = Sea.objects.create(name='ים קורו', name_en='Koro Sea'), Sea.objects.create(name='הים התיכון')
        akhziv = Region.objects.create(name='אכזיב', country=israel, sea=med)
        # (a) sea only, with observations, no region in that country+sea -> a region named after the sea
        a = T.objects.create(title='a', country=fiji, sea=coral)
        sa = S.objects.create(owner=owner, trip=a, title='a', kind='collection')
        # (b) sea only, observations, exactly one region of that country+sea -> that region
        b = T.objects.create(title='b', country=israel, sea=med)
        sb = S.objects.create(owner=owner, trip=b, title='b', kind='collection')
        # (c) sea only but no observations -> left alone (no pointless region)
        c = T.objects.create(title='c', country=fiji, sea=coral)
        # (d) already has a region -> untouched; (e) no sea, no country -> untouched
        d = T.objects.create(title='d', country=israel, region=akhziv, sea=med)
        e = T.objects.create(title='e')
        regions_before = Region.objects.count()

        new = self.migrate(self.after)
        T2, R2 = new.get_model('observations', 'DiveTrip'), new.get_model('observations', 'Region')
        got = lambda t: T2.objects.get(pk=t.pk).region
        ra = got(a)
        self.assertEqual((ra.country_id, ra.sea_id, ra.name, ra.name_en), (fiji.pk, coral.pk, 'ים קורו', 'Koro Sea'))
        self.assertEqual(got(b).pk, akhziv.pk)
        self.assertIsNone(got(c)); self.assertEqual(got(d).pk, akhziv.pk); self.assertIsNone(got(e))
        self.assertEqual(R2.objects.count(), regions_before + 1)
        # still one region of that country+sea when the same sea-only situation recurs
        self.assertEqual(R2.objects.filter(country_id=fiji.pk, sea_id=coral.pk).count(), 1)

    def test_final_migration_drops_the_column_and_a_trips_sea_is_its_regions(self):
        apps = self.migrate(self.final)
        self.assertNotIn('sea', [f.name for f in apps.get_model('observations', 'DiveTrip')._meta.concrete_fields])
        columns = [c.name for c in connection.introspection.get_table_description(connection.cursor(), 'dive_trips')]
        self.assertNotIn('sea_id', columns)

    def test_migration_can_be_reversed_and_gives_trips_their_regions_sea_back(self):
        new = self.migrate(self.final)
        Country, Sea, Region = (new.get_model('observations', n) for n in ('Country', 'Sea', 'Region'))
        T = new.get_model('observations', 'DiveTrip')
        israel, med = Country.objects.create(name='ישראל'), Sea.objects.create(name='הים התיכון')
        trip = T.objects.create(title='t', country=israel, region=Region.objects.create(name='אכזיב', country=israel, sea=med))
        old = self.migrate(self.before)
        self.assertEqual(old.get_model('observations', 'DiveTrip').objects.get(pk=trip.pk).sea_id, med.pk)
