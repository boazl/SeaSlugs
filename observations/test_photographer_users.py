"""The Photographer lookup table is gone: a trip's photographer is a user account.

Covers (1) the data migration that mapped every photographer onto a user, (2) the "a member
can only edit their own observations / every observation has an owner" guarantees the
credit fallback relies on, and (3) the places that used to read the table: trip form, list
filter, table transfer."""
from django.contrib.auth.models import User
from django.db import connection, IntegrityError, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from .forms import DiveTripForm
from .models import Country, Sea, Region, DiveTrip, Species, Sample, Profile


class PhotographerMigrationTests(TransactionTestCase):
    before = [('observations', '0034_divetrip_photographer_user')]
    after = [('observations', '0035_divetrip_photographer_to_users')]

    def migrate(self, targets):
        executor = MigrationExecutor(connection)
        executor.migrate(targets)
        return executor.loader.project_state(targets).apps

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def test_every_photographer_is_mapped_to_a_user_and_nothing_is_lost(self):
        old = self.migrate(self.before)
        U, P = old.get_model('auth', 'User'), old.get_model('observations', 'Profile')
        Ph, T = old.get_model('observations', 'Photographer'), old.get_model('observations', 'DiveTrip')
        boaz = U.objects.create(username='boazl', first_name='בעז', last_name='ליבס')
        P.objects.create(user=boaz, first_name_en='Boaz', last_name_en='Liebes')
        shevy = U.objects.create(username='rshevy', first_name='בת-שבע (שבי)', last_name='רוטמן')
        bart = U.objects.create(username='bart.adams', first_name='בארט', last_name='אדמס', is_active=False)
        P.objects.create(user=bart, first_name_en='Bart', last_name_en='Adams')
        ph_boaz = Ph.objects.create(name='בעז ליבס', name_en='Boaz Liebes')
        ph_shevy = Ph.objects.create(name='שבי רוטמן', name_en='Dr. Bat-Sheva (Shevy) Rothman')
        ph_jane = Ph.objects.create(name='ג׳יין דייבר', name_en='Jane Diver')
        t_both = T.objects.create(title='both', photographer='Boaz Liebes', photographer_fk=ph_boaz)
        t_fk_only = T.objects.create(title='fk only', photographer_fk=ph_shevy)
        t_text_only = T.objects.create(title='text only', photographer='Bart Adams')
        t_none = T.objects.create(title='none')
        t_guest_fk = T.objects.create(title='guest fk', photographer='Jane D.', photographer_fk=ph_jane)
        t_guest_text = T.objects.create(title='guest text', photographer='Unknown Person')

        new = self.migrate(self.after)
        T2, U2 = new.get_model('observations', 'DiveTrip'), new.get_model('auth', 'User')
        got = lambda t: T2.objects.get(pk=t.pk).photographer_user
        self.assertEqual(got(t_both).pk, boaz.pk)
        self.assertEqual(got(t_fk_only).pk, shevy.pk)   # "שבי רוטמן" -> the account "בת-שבע (שבי) רוטמן"
        self.assertEqual(got(t_text_only).pk, bart.pk)  # matched by the English profile name
        self.assertIsNone(got(t_none))
        # people nobody matches get an inactive account instead of losing the credit
        jane = got(t_guest_fk)
        self.assertFalse(jane.is_active); self.assertTrue(jane.password.startswith('!'))  # unusable password
        self.assertEqual((jane.first_name, jane.last_name), ('ג׳יין', 'דייבר'))
        unknown = got(t_guest_text)
        self.assertFalse(unknown.is_active); self.assertEqual(unknown.first_name, 'Unknown')
        # no existing account was duplicated for someone who already had one
        self.assertEqual(U2.objects.filter(last_name='רוטמן').count(), 1)
        self.assertEqual(U2.objects.filter(is_active=False).count(), 3)  # bart + the two new guests

    def test_final_migration_drops_the_table_and_the_old_columns(self):
        apps = self.migrate([('observations', '0036_remove_photographer_table')])
        names = {f.name for f in apps.get_model('observations', 'DiveTrip')._meta.get_fields()}
        self.assertIn('photographer', names)
        self.assertNotIn('photographer_fk', names); self.assertNotIn('photographer_user', names)
        with self.assertRaises(LookupError): apps.get_model('observations', 'Photographer')
        self.assertNotIn('observations_photographer', connection.introspection.table_names())
        self.assertTrue(apps.get_model('observations', 'DiveTrip')._meta.get_field('photographer').is_relation)

    def test_migration_can_be_reversed_back_to_the_lookup_table(self):
        new = self.migrate([('observations', '0036_remove_photographer_table')])
        U, T = new.get_model('auth', 'User'), new.get_model('observations', 'DiveTrip')
        user = U.objects.create(username='jane', first_name='ג׳יין', last_name='דייבר')
        trip = T.objects.create(title='t', photographer=user)
        old = self.migrate(self.before)  # reversing 0036 and then 0035's data step
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


class TripPhotographerUserTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user('owner', first_name='דנה', last_name='כהן')
        self.boaz = User.objects.create_user('boazl', first_name='בעז', last_name='ליבס')
        Profile.objects.create(user=self.boaz, first_name_en='Boaz', last_name_en='Liebes')
        self.guest = User.objects.create_user('bart.adams', first_name='בארט', last_name='אדמס', is_active=False)
        country = Country.objects.create(name='Israel'); sea = Sea.objects.create(name='Mediterranean')
        self.region = Region.objects.create(name='Akhziv', country=country, sea=sea)
        self.country = country
        self.with_boaz = DiveTrip.objects.create(title='With photographer', year=2026, country=country, region=self.region, photographer=self.boaz)
        self.without = DiveTrip.objects.create(title='No photographer', year=2025, country=country, region=self.region)
        for n, trip in enumerate([self.with_boaz, self.without]):
            Sample(owner=self.owner, kind='collection', trip=trip, title=f'c{n}', video_url=f'https://youtu.be/{n}0000000000'
                   ).save_reviewed(actor=self.owner, approve=True)
        self.client.force_login(self.owner)

    def test_trip_form_offers_users_as_photographers_including_guest_accounts(self):
        form = DiveTripForm()
        self.assertEqual(set(form.fields['photographer'].queryset), {self.owner, self.boaz, self.guest})
        self.assertEqual(form.fields['photographer'].label_from_instance(self.boaz), 'בעז ליבס (Boaz Liebes)')
        self.assertEqual(form.fields['photographer'].label_from_instance(self.guest), 'בארט אדמס')
        self.assertFalse(form.fields['photographer'].required)

    def test_new_trip_form_saves_the_chosen_user_as_photographer(self):
        response = self.client.post(reverse('trip-new'), {'title': 'New', 'country': self.country.pk, 'region': self.region.pk,
                                                          'year': 2026, 'photographer': self.guest.pk})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(DiveTrip.objects.get(title='New').photographer, self.guest)

    def test_list_filter_matches_the_trip_photographer_by_name_in_either_language(self):
        for term in ('ליבס', 'liebes', 'boazl'):
            response = self.client.get(reverse('observations'), {'photographer': term})
            self.assertContains(response, 'c0'); self.assertNotContains(response, '>c1<')

    def test_list_filter_also_finds_observations_credited_to_their_owner(self):
        response = self.client.get(reverse('observations'), {'photographer': 'כהן'})
        self.assertContains(response, 'c1'); self.assertNotContains(response, 'c0')

    def test_list_offers_the_credited_users_names_as_filter_options(self):
        response = self.client.get(reverse('observations'))
        self.assertEqual(response.context['photographers'], ['בעז ליבס', 'דנה כהן'])
        self.assertEqual(self.client.get(reverse('observations'), {'lang': 'en'}).context['photographers'], ['Boaz Liebes', 'דנה כהן'])

    def test_users_cannot_be_deleted_while_they_are_a_trips_photographer(self):
        from django.db.models import ProtectedError
        with self.assertRaises(ProtectedError): self.boaz.delete()
