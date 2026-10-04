"""A trip has no photographer: the photographer of an observation is always its creator
(Sample.owner), and a guest photographer is simply an inactive user who owns their own
observations. The Photographer lookup table is gone.

Covers (1) the data migration that handed each trip's samples to its former photographer's
user, (2) the "a member can only edit their own observations / every observation has an
owner" guarantees the credit relies on, and (3) the places that used to read the table."""
from django.contrib.auth.models import User
from django.db import connection, IntegrityError, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from .models import Country, Sea, Region, DiveTrip, Species, Sample, Profile


class PhotographerMigrationTests(TransactionTestCase):
    before = [('observations', '0033_species_size_from_species_size_max_species_size_to')]
    after = [('observations', '0034_assign_trip_samples_to_trip_photographer')]
    final = [('observations', '0035_remove_trip_photographer')]

    def migrate(self, targets):
        executor = MigrationExecutor(connection)
        executor.migrate(targets)
        return executor.loader.project_state(targets).apps

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def test_every_trips_samples_go_to_its_photographers_user_and_nothing_is_lost(self):
        old = self.migrate(self.before)
        U, P = old.get_model('auth', 'User'), old.get_model('observations', 'Profile')
        Ph, T, S = (old.get_model('observations', n) for n in ('Photographer', 'DiveTrip', 'Sample'))
        admin = U.objects.create(username='admin', first_name='מנהל', last_name='ראשי')
        boaz = U.objects.create(username='boazl', first_name='בעז', last_name='ליבס')
        P.objects.create(user=boaz, first_name_en='Boaz', last_name_en='Liebes')
        shevy = U.objects.create(username='rshevy', first_name='בת-שבע (שבי)', last_name='רוטמן')
        bart = U.objects.create(username='bart.adams', first_name='בארט', last_name='אדמס', is_active=False)
        P.objects.create(user=bart, first_name_en='Bart', last_name_en='Adams')
        ph_boaz = Ph.objects.create(name='בעז ליבס', name_en='Boaz Liebes')
        ph_shevy = Ph.objects.create(name='שבי רוטמן', name_en='Dr. Bat-Sheva (Shevy) Rothman')
        ph_jane = Ph.objects.create(name='ג׳יין דייבר', name_en='Jane Diver')
        trips = {
            'both': T.objects.create(title='both', photographer='Boaz Liebes', photographer_fk=ph_boaz),
            'fk_only': T.objects.create(title='fk only', photographer_fk=ph_shevy),
            'text_only': T.objects.create(title='text only', photographer='Bart Adams'),
            'none': T.objects.create(title='none'),
            'guest_fk': T.objects.create(title='guest fk', photographer='Jane D.', photographer_fk=ph_jane),
            'guest_text': T.objects.create(title='guest text', photographer='Unknown Person'),
        }
        samples = {k: S.objects.create(owner=admin, trip=t, title=k, kind='collection') for k, t in trips.items()}
        samples['both_deleted'] = S.objects.create(owner=admin, trip=trips['both'], title='gone', kind='collection')

        new = self.migrate(self.after)
        S2, U2 = new.get_model('observations', 'Sample'), new.get_model('auth', 'User')
        owner = lambda k: S2.objects.get(pk=samples[k].pk).owner
        self.assertEqual(owner('both').pk, boaz.pk)
        self.assertEqual(owner('both_deleted').pk, boaz.pk)   # soft-deleted rows follow too
        self.assertEqual(owner('fk_only').pk, shevy.pk)       # "שבי רוטמן" -> the account "בת-שבע (שבי) רוטמן"
        self.assertEqual(owner('text_only').pk, bart.pk)      # matched by the English profile name
        self.assertEqual(owner('none').pk, admin.pk)          # a trip with no photographer changes nothing
        # people nobody matches get an inactive account instead of losing the credit
        jane = owner('guest_fk')
        self.assertFalse(jane.is_active); self.assertTrue(jane.password.startswith('!'))  # unusable password
        self.assertEqual((jane.first_name, jane.last_name), ('ג׳יין', 'דייבר'))
        unknown = owner('guest_text')
        self.assertFalse(unknown.is_active); self.assertEqual(unknown.first_name, 'Unknown')
        # no existing account was duplicated for someone who already had one
        self.assertEqual(U2.objects.filter(last_name='רוטמן').count(), 1)
        self.assertEqual(U2.objects.filter(is_active=False).count(), 3)  # bart + the two new guests

    def test_final_migration_drops_the_table_and_the_trip_photographer_columns(self):
        apps = self.migrate(self.final)
        names = {f.name for f in apps.get_model('observations', 'DiveTrip')._meta.get_fields()}
        self.assertFalse([n for n in names if 'photographer' in n])
        with self.assertRaises(LookupError): apps.get_model('observations', 'Photographer')
        self.assertNotIn('observations_photographer', connection.introspection.table_names())

    def test_migration_can_be_reversed_back_to_the_lookup_table(self):
        new = self.migrate(self.final)
        U, T, S = (new.get_model(*n) for n in (('auth', 'User'), ('observations', 'DiveTrip'), ('observations', 'Sample')))
        user = U.objects.create(username='jane', first_name='ג׳יין', last_name='דייבר')
        trip = T.objects.create(title='t')
        S.objects.create(owner=user, trip=trip, title='s', kind='collection')
        old = self.migrate(self.before)
        T1, Ph = old.get_model('observations', 'DiveTrip'), old.get_model('observations', 'Photographer')
        trip = T1.objects.get(pk=trip.pk)
        self.assertEqual(Ph.objects.get(pk=trip.photographer_fk_id).name, 'ג׳יין דייבר')
        self.assertEqual(trip.photographer, 'ג׳יין דייבר')


class ObservationOwnershipTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user('alice', password='pw')
        self.bob = User.objects.create_user('bob', password='pw')
        self.manager = User.objects.create_superuser('manager', password='pw')
        country = Country.objects.create(name='Israel'); sea = Sea.objects.create(name='Mediterranean')
        region = Region.objects.create(name='Akhziv', country=country, sea=sea)
        self.trip = DiveTrip.objects.create(title='T', year=2026, country=country, region=region)
        self.item = Sample(owner=self.alice, kind='collection', trip=self.trip, title='Alice video',
                           video_url='https://youtu.be/11111111111')
        self.item.save_reviewed()

    def test_every_observation_must_have_an_owner(self):
        self.assertFalse(Sample._meta.get_field('owner').null)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Sample.objects.create(kind='collection', trip=self.trip, title='Orphan', video_url='https://youtu.be/22222222222')

    def test_a_member_can_open_and_remove_only_their_own_observation(self):
        edit, remove = reverse('observation-edit', args=[self.item.pk]), reverse('observation-remove', args=[self.item.pk])
        self.client.force_login(self.bob)
        self.assertEqual(self.client.get(edit).status_code, 404)
        self.assertEqual(self.client.post(remove).status_code, 404)
        self.client.force_login(self.alice)
        self.assertEqual(self.client.get(edit).status_code, 200)

    def test_the_owner_cannot_be_changed_through_the_edit_form(self):
        self.client.force_login(self.alice)
        self.client.post(reverse('observation-edit', args=[self.item.pk]), {
            'title': 'Renamed', 'kind': 'collection', 'trip': self.trip.pk, 'video_url': 'https://youtu.be/11111111111',
            'owner': self.bob.pk})
        self.item.refresh_from_db()
        self.assertEqual(self.item.owner, self.alice)

    def test_a_manager_may_open_any_observation(self):
        self.client.force_login(self.manager)
        self.assertEqual(self.client.get(reverse('observation-edit', args=[self.item.pk])).status_code, 200)


class PhotographerIsTheOwnerTests(TestCase):
    def setUp(self):
        self.dana = User.objects.create_user('dana', first_name='דנה', last_name='כהן')
        self.boaz = User.objects.create_user('boazl', first_name='בעז', last_name='ליבס')
        Profile.objects.create(user=self.boaz, first_name_en='Boaz', last_name_en='Liebes')
        self.guest = User.objects.create_user('bart.adams', first_name='בארט', last_name='אדמס', is_active=False)
        country = Country.objects.create(name='Israel'); sea = Sea.objects.create(name='Mediterranean')
        self.region = Region.objects.create(name='Akhziv', country=country, sea=sea)
        self.country = country
        self.trip = DiveTrip.objects.create(title='Shared trip', year=2026, country=country, region=self.region)
        for n, owner in enumerate([self.dana, self.boaz]):
            Sample(owner=owner, kind='collection', trip=self.trip, title=f'c{n}', video_url=f'https://youtu.be/{n}0000000000'
                   ).save_reviewed(actor=self.dana, approve=True)
        self.manager = User.objects.create_superuser('manager', password='pw')

    def test_a_trip_has_no_photographer_field_and_the_form_has_no_photographer(self):
        from .forms import DiveTripForm
        self.assertFalse([f.name for f in DiveTrip._meta.get_fields() if 'photographer' in f.name])
        self.assertNotIn('photographer', DiveTripForm().fields)

    def test_credit_is_the_owner_even_on_a_trip_shared_by_several_owners(self):
        by_title = {s.title: s for s in Sample.objects.all()}
        self.assertEqual(by_title['c0'].photographer_display_name('he'), 'דנה כהן')
        self.assertEqual(by_title['c1'].photographer_display_name('en'), 'Boaz Liebes')

    def test_list_filter_matches_the_owner_by_name_in_either_language_or_username(self):
        self.client.force_login(self.manager)
        for term in ('ליבס', 'liebes', 'boazl'):
            response = self.client.get(reverse('observations'), {'photographer': term})
            self.assertContains(response, 'c1'); self.assertNotContains(response, '>c0<')

    def test_list_offers_the_owners_names_as_filter_options(self):
        self.client.force_login(self.manager)
        self.assertEqual(self.client.get(reverse('observations')).context['photographers'], ['בעז ליבס', 'דנה כהן'])
        self.assertEqual(self.client.get(reverse('observations'), {'lang': 'en'}).context['photographers'], ['Boaz Liebes', 'דנה כהן'])

    def test_a_guest_photographer_is_an_inactive_user_who_cannot_log_in(self):
        self.assertFalse(self.client.login(username='bart.adams', password='anything'))
        item = Sample(owner=self.guest, kind='collection', trip=self.trip, title='Bart', video_url='https://youtu.be/99999999999')
        self.assertEqual(item.photographer_name, 'בארט אדמס')
