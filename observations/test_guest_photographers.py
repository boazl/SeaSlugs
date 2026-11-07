"""Guest photographers: an observation always belongs to a user (its photographer), and a manager can add
observations for photographers who are not active members of the site.

Rules:
- A guest photographer is an inactive user in the "Macro photographer" group; migration 0092 puts the existing
  inactive users (the former photographer table) in it. photographer_users() = every active user + the guests.
- A manager sets one up on /observations/photographers/new/ (no password, cannot sign in; English names give the
  username) and returns to the observation form with them chosen (?photographer=).
- On the observation form a manager chooses the photographer (first field; guests marked "צלם אורח"); a new
  observation starts with the manager or ?photographer=; saving records the observation under that user. Members
  never see the field and their observations stay their own. A manager's post without the field keeps the
  observation's current photographer.
- The quick trip form's photographer (it names the trip) offers the same users to a manager, ?photographer= first.
- The news page's photographers table lists guests too, marked.
"""
import importlib
import tempfile

from django.apps import apps as django_apps
from django.contrib.auth.models import Group, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from .models import Country, DiveTrip, Profile, Region, Sample, Sea, Species
from .photographers import PHOTOGRAPHER_GROUP, guest_username, photographer_users

STORAGES = {'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
            'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}}


@override_settings(STORAGES=STORAGES)
class GuestPhotographerTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_superuser('boss', 'b@example.com', 'a-valid-password-927', first_name='בעז', last_name='ליבס')
        self.member = User.objects.create_user('member', password='a-valid-password-927', first_name='דנה', last_name='ים')
        self.group = Group.objects.get_or_create(name=PHOTOGRAPHER_GROUP)[0]
        self.guest = User.objects.create_user('oren.kline', first_name='אורן', last_name='קליין', is_active=False)
        self.guest.groups.add(self.group)
        self.blocked = User.objects.create_user('blocked', first_name='חסום', is_active=False)   # inactive, not a photographer
        country = Country.objects.create(name='ישראל', name_en='Israel')
        region = Region.objects.create(name='אכזיב', country=country, sea=Sea.objects.create(name='הים התיכון'))
        self.trip = DiveTrip.objects.create(title='Akhziv', code='I26Aug', year=2026, month=8, country=country, region=region)
        Species.objects.create(scientific_name='Flabellina affinis', genus='Flabellina', species='affinis', author='(Gmelin, 1791)')
        media = tempfile.TemporaryDirectory()
        self.addCleanup(media.cleanup)
        override = override_settings(MEDIA_ROOT=media.name)
        override.enable()
        self.addCleanup(override.disable)

    def post_observation(self, **extra):
        data = {'species': 'Flabellina affinis', 'trip': str(self.trip.pk), 'site': '', 'kind': 'species',
                'video_url': 'https://youtu.be/abcdefghijk'}
        data.update(extra)
        return self.client.post('/observations/new/', data)

    def test_photographer_users_are_members_and_guests(self):
        users = set(photographer_users())
        self.assertTrue({self.manager, self.member, self.guest} <= users)
        self.assertNotIn(self.blocked, users)

    def test_migration_makes_existing_inactive_users_guests(self):
        self.guest.groups.clear()
        migration = importlib.import_module('observations.migrations.0092_guest_photographers_group')
        migration.add_guests(django_apps, None)
        self.assertTrue(self.guest.groups.filter(name=PHOTOGRAPHER_GROUP).exists())
        self.assertFalse(self.member.groups.filter(name=PHOTOGRAPHER_GROUP).exists())

    def test_manager_form_offers_the_photographers(self):
        self.client.force_login(self.manager)
        page = self.client.get('/observations/new/')
        field = page.context['form'].fields['photographer']
        self.assertEqual(list(page.context['form'].fields)[0], 'photographer')
        self.assertEqual(page.context['form'].initial['photographer'], self.manager.pk)
        self.assertContains(page, 'אורן קליין (צלם אורח)')
        self.assertNotContains(page, 'חסום')
        self.assertContains(page, 'id="photographer-add-link"')
        self.assertIn(self.guest, field.queryset)

    def test_photographer_in_the_address_is_preselected(self):
        self.client.force_login(self.manager)
        page = self.client.get(f'/observations/new/?photographer={self.guest.pk}')
        self.assertEqual(page.context['form'].initial['photographer'], self.guest.pk)
        page = self.client.get(f'/observations/new/?photographer={self.blocked.pk}')   # not a photographer: ignored
        self.assertEqual(page.context['form'].initial['photographer'], self.manager.pk)

    def test_manager_adds_an_observation_for_a_guest(self):
        self.client.force_login(self.manager)
        response = self.post_observation(photographer=str(self.guest.pk))
        self.assertEqual(response.status_code, 302)
        sample = Sample.objects.get()
        self.assertEqual(sample.owner, self.guest)
        self.assertEqual(sample.status, 'published')
        self.assertEqual(sample.photographer_name, 'אורן קליין')

    def test_manager_moves_an_observation_to_another_photographer(self):
        self.client.force_login(self.manager)
        self.post_observation(photographer=str(self.manager.pk))
        sample = Sample.objects.get()
        page = self.client.get(f'/observations/{sample.pk}/edit/')
        self.assertEqual(page.context['form'].initial['photographer'], self.manager.pk)
        self.client.post(f'/observations/{sample.pk}/edit/', {'species': 'Flabellina affinis', 'trip': str(self.trip.pk),
            'site': '', 'kind': 'species', 'video_url': 'https://youtu.be/abcdefghijk', 'photographer': str(self.guest.pk)})
        sample.refresh_from_db()
        self.assertEqual(sample.owner, self.guest)

    def test_a_post_without_the_field_keeps_the_photographer(self):
        self.client.force_login(self.manager)
        self.post_observation()
        self.assertEqual(Sample.objects.get().owner, self.manager)

    def test_a_non_photographer_cannot_be_chosen(self):
        self.client.force_login(self.manager)
        response = self.post_observation(photographer=str(self.blocked.pk))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Sample.objects.exists())

    def test_members_have_no_photographer_field_and_keep_their_observations(self):
        self.client.force_login(self.member)
        page = self.client.get('/observations/new/')
        self.assertNotIn('photographer', page.context['form'].fields)
        self.assertNotContains(page, 'photographer-add-link')
        self.post_observation(photographer=str(self.guest.pk))
        self.assertEqual(Sample.objects.get().owner, self.member)
        self.assertEqual(self.client.get('/observations/photographers/new/').status_code, 404)

    def test_manager_sets_up_a_guest_photographer(self):
        self.client.force_login(self.manager)
        self.assertContains(self.client.get('/observations/photographers/new/?next=/observations/new/'), 'הוספת צלם אורח')
        response = self.client.post('/observations/photographers/new/', {
            'first_name': 'יגאל', 'last_name': 'שטסל', 'first_name_en': 'Igal', 'last_name_en': 'Chtesle',
            'email': 'igal@example.com', 'phone': '050-1234567', 'next': '/observations/new/?trip=5&photographer=1'})
        guest = User.objects.get(email='igal@example.com')
        self.assertEqual(response['Location'], f'/observations/new/?trip=5&photographer={guest.pk}')
        self.assertEqual(guest.username, 'igal.chtesle')
        self.assertFalse(guest.is_active)
        self.assertFalse(guest.has_usable_password())
        self.assertTrue(guest.groups.filter(name=PHOTOGRAPHER_GROUP).exists())
        profile = Profile.objects.get(user=guest)
        self.assertEqual((profile.first_name_en, profile.last_name_en, profile.phone), ('Igal', 'Chtesle', '050-1234567'))
        self.assertIn(guest, photographer_users())

    def test_guest_email_must_be_new_and_usernames_are_unique(self):
        self.client.force_login(self.manager)
        response = self.client.post('/observations/photographers/new/', {'first_name': 'א', 'last_name': 'ב', 'email': 'B@example.com'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'כבר קיים משתמש עם כתובת הדואר הזו')
        self.assertEqual(guest_username('Oren', 'Kline'), 'oren.kline-2')
        self.assertEqual(guest_username('', ''), 'photographer')

    def test_trip_form_offers_guests_and_takes_the_chosen_photographer(self):
        self.client.force_login(self.manager)
        page = self.client.get(f'/observations/trips/add/?photographer={self.guest.pk}')
        form = page.context['form']
        self.assertIn(self.guest, form.fields['photographer'].queryset)
        self.assertEqual(form.initial['photographer'], self.guest)
        self.assertContains(page, 'אורן קליין (צלם אורח)')

    def test_news_lists_guests(self):
        self.client.force_login(self.manager)
        html = self.client.get('/news/').content.decode()
        table = html[html.index('id="photographers"'):]
        self.assertIn('אורן קליין <span class="badge">צלם אורח</span>', table)
        self.assertNotIn('חסום', table)
