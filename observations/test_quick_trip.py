"""Adding a single observation without setting up a dive trip or a dive site first (the observation form):

- The dive site list starts with "אחר..." (right after "בחרו…"). Choosing it asks for the new site's Hebrew name (required)
  and English name; the save adds the site to the dive sites of the trip's region (a site of that region with the same
  name is used instead of a duplicate) and the observation points at it -- no free-text "other" value is left behind.
- A new observation can tick "יצירה אוטומטית של מסע מתצפית זו": the trip list is ignored, the new trip's region, year and
  month become required, and the save first adds a one-dive trip (named and coded like a trip from the trips page, after
  the observation's photographer, with the observation's site and day) and puts the observation in it.
- Nothing is added when the form is invalid: the validation runs in a transaction that is rolled back.
"""
from django.contrib.auth.models import User
from django.test import TestCase

from .forms import SampleForm, TRIP_HELP
from .models import Country, DiveTrip, Region, Sample, Sea, Site, Species


class QuickTripAndSiteTests(TestCase):
    def setUp(self):
        self.country = Country.objects.create(name='ישראל', name_en='Israel')
        sea = Sea.objects.create(name='הים התיכון', name_en='Mediterranean Sea')
        self.region = Region.objects.create(name='אכזיב', name_en='Akhziv', country=self.country, sea=sea)
        self.other_region = Region.objects.create(name='אילת', name_en='Eilat', country=self.country, sea=Sea.objects.create(name='ים סוף'))
        self.trip = DiveTrip.objects.create(title='אכזיב 2025', code='I25Nov', year=2025, month=11, country=self.country, region=self.region)
        self.species = Species.objects.create(genus='Goniobranchus', species='annulatus', author='(Eliot, 1904)')
        self.member = User.objects.create_user('member', password='a-valid-password-927')
        self.client.force_login(self.member)

    def post(self, **extra):
        data = {'kind': 'species', 'genus': 'Goniobranchus', 'species': 'annulatus', 'site': '', 'site_other': '',
                'video_url': 'https://youtu.be/12345678901', 'next': '/'}
        data.update(extra)
        return self.client.post('/observations/new/', data)

    def errors(self, response):
        return getattr(response, 'context', None) and response.context['form'].errors

    def test_other_is_first_in_the_site_list(self):
        Site.objects.create(region=self.region, name='אלף')
        choices = [value for value, _label in SampleForm().fields['site'].choices]
        self.assertEqual(choices[:2], ['', 'other'])
        self.assertEqual(dict(SampleForm().fields['site'].choices)['other'], 'אחר...')

    def test_the_form_shows_the_new_fields_and_help(self):
        html = self.client.get('/observations/new/').content.decode()
        for name in ('id_site_other_en', 'id_create_trip', 'id_new_trip_region', 'id_new_trip_year', 'id_new_trip_month'):
            self.assertIn(name, html)
        self.assertIn('ליצירה אוטומטית של מסע מתצפית זו', TRIP_HELP)
        self.assertNotIn('לא מוצא/ת את המסע?', html)
        self.assertIn('updateCreateTrip', html)

    def test_editing_has_no_create_trip_box(self):
        sample = Sample.objects.create(kind='species', species=self.species, trip=self.trip, owner=self.member, video_url='https://youtu.be/12345678901')
        self.assertNotIn('create_trip', SampleForm(instance=sample).fields)

    def test_other_site_is_added_to_the_trips_region(self):
        response = self.post(trip=str(self.trip.pk), site='other', site_other='  חוף  הסלע ', site_other_en='Rock Beach')
        self.assertEqual(response.status_code, 302, self.errors(response))
        site = Site.objects.get(name='חוף הסלע')
        self.assertEqual((site.region, site.name_en), (self.region, 'Rock Beach'))
        sample = Sample.objects.get()
        self.assertEqual((sample.site, sample.site_other), (site, ''))
        self.assertEqual(sample.status, 'published')

    def test_other_site_with_an_existing_name_reuses_it(self):
        site = Site.objects.create(region=self.region, name='המערות', name_en='Caves')
        response = self.post(trip=str(self.trip.pk), site='other', site_other='משהו', site_other_en='caves')
        self.assertEqual(response.status_code, 302, self.errors(response))
        self.assertEqual(Site.objects.count(), 1)
        self.assertEqual(Sample.objects.get().site, site)

    def test_other_site_needs_a_hebrew_name(self):
        response = self.post(trip=str(self.trip.pk), site='other', site_other_en='Rock Beach')
        self.assertEqual(response.status_code, 200)
        self.assertIn('site_other', response.context['form'].errors)
        self.assertFalse(Site.objects.exists())

    def test_other_site_needs_a_region(self):
        response = self.post(site='other', site_other='חוף')
        self.assertEqual(response.status_code, 200)
        self.assertIn('site', response.context['form'].errors)
        self.assertFalse(Site.objects.exists())

    def test_create_trip_from_the_observation(self):
        response = self.post(create_trip='on', new_trip_region=str(self.region.pk), new_trip_year='2024', new_trip_month='8',
                             day='14', site='other', site_other='קניון', site_other_en='Canyon')
        self.assertEqual(response.status_code, 302, self.errors(response))
        sample = Sample.objects.get()
        trip = sample.trip
        self.assertNotEqual(trip, self.trip)
        self.assertEqual((trip.region, trip.country, trip.year, trip.month, trip.start_day, trip.duration_days),
                         (self.region, self.country, 2024, 8, 14, 1))
        self.assertEqual(trip.site, Site.objects.get(name='קניון'))
        self.assertEqual(sample.site, trip.site)
        self.assertEqual(sample.day, 14)
        self.assertTrue(trip.code and trip.title)
        self.assertIn('קניון', trip.title)
        self.assertEqual(sample.status, 'published')

    def test_create_trip_wins_over_a_chosen_trip(self):
        response = self.post(create_trip='on', trip=str(self.trip.pk), new_trip_region=str(self.region.pk),
                             new_trip_year='2023', new_trip_month='7')
        self.assertEqual(response.status_code, 302, self.errors(response))
        self.assertEqual(Sample.objects.get().trip.year, 2023)
        self.assertEqual(DiveTrip.objects.count(), 2)

    def test_create_trip_requires_region_year_and_month(self):
        response = self.post(create_trip='on')
        self.assertEqual(response.status_code, 200)
        errors = response.context['form'].errors
        for name in ('new_trip_region', 'new_trip_year', 'new_trip_month'):
            self.assertIn(name, errors)
        self.assertEqual(DiveTrip.objects.count(), 1)

    def test_create_trip_site_must_be_in_its_region(self):
        site = Site.objects.create(region=self.other_region, name='המגדלור')
        response = self.post(create_trip='on', new_trip_region=str(self.region.pk), new_trip_year='2024', new_trip_month='8', site=str(site.pk))
        self.assertEqual(response.status_code, 200)
        self.assertIn('site', response.context['form'].errors)
        self.assertEqual(DiveTrip.objects.count(), 1)

    def test_nothing_is_added_when_the_observation_is_invalid(self):
        # no photo and no video: the model's own check fails after the site and the trip were made -- both rolled back
        response = self.post(create_trip='on', new_trip_region=str(self.region.pk), new_trip_year='2024', new_trip_month='8',
                             site='other', site_other='קניון', video_url='')
        self.assertEqual(response.status_code, 200)
        self.assertIn('video_url', response.context['form'].errors)
        self.assertEqual(DiveTrip.objects.count(), 1)
        self.assertFalse(Site.objects.exists())

    def test_bad_date_for_the_new_trip(self):
        response = self.post(create_trip='on', new_trip_region=str(self.region.pk), new_trip_year='2023', new_trip_month='2', day='30')
        self.assertEqual(response.status_code, 200)
        self.assertIn('day', response.context['form'].errors)
        self.assertEqual(DiveTrip.objects.count(), 1)

    def test_taxon_observation_ignores_the_box(self):
        manager = User.objects.create_superuser('boss', 'b@example.org', 'a-valid-password-927')
        self.client.force_login(manager)
        response = self.client.post('/observations/new/', {'kind': 'genus', 'genus': 'Goniobranchus', 'create_trip': 'on',
            'new_trip_region': str(self.region.pk), 'new_trip_year': '2024', 'new_trip_month': '8', 'next': '/'})
        self.assertEqual(response.status_code, 302, self.errors(response))
        self.assertEqual(DiveTrip.objects.filter(region=self.region).count(), 1)
