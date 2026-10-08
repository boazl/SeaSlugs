from datetime import date
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from .models import Country, Sea, Region, Site, DiveTrip, Profile
from .trip_naming import (region_code_for, photographer_letter_for, suggest_title, suggest_code, photographer_letter,
                          region_code, MONTHS_EN)

NOW = date.today()


class Fixture(TestCase):
    def setUp(self):
        self.israel = Country.objects.create(name='ישראל', name_en='Israel')
        self.med = Sea.objects.create(name='הים התיכון', name_en='Mediterranean')
        self.red = Sea.objects.create(name='ים סוף', name_en='Red Sea')
        self.akhziv = Region.objects.create(name='אכזיב', name_en='Akhziv', country=self.israel, sea=self.med)
        self.dor = Region.objects.create(name='דור', name_en='Dor Habonim', country=self.israel, sea=self.med)
        self.eilat = Region.objects.create(name='אילת', name_en='Eilat', country=self.israel, sea=self.red)
        self.canyon = Site.objects.create(name='קניון אכזיב', name_en='Akhziv Canyon', region=self.akhziv)
        self.island = Site.objects.create(name='אי האהבה', name_en='Sgavion', region=self.akhziv)
        self.boaz = User.objects.create_user('boazl', password='pw', first_name='בעז', last_name='ליבס')
        self.bart = User.objects.create_user('bart.adams', password='pw', first_name='בארט', last_name='אדמס')
        Profile.objects.create(user=self.bart, first_name_en='Bart')
        self.manager = User.objects.create_superuser('root', 'r@example.com', 'pw')


class NamingRuleTests(Fixture):
    def test_region_codes(self):
        self.assertEqual(region_code_for('Akhziv', 'אכזיב', True, set()), 'I')                 # the old letter I
        self.assertEqual(region_code_for('Eilat', 'אילת', False, set()), 'J')                   # and J
        self.assertEqual(region_code_for('Ashkelon', 'אשקלון', True, {'I'}), 'IA')              # Israel's Mediterranean: I + letter
        self.assertEqual(region_code_for('Ashdod', 'אשדוד', True, {'I', 'IA'}), 'IAs')          # a clash grows by a letter
        self.assertEqual(region_code_for('Anilao', 'אנילאו', False, set()), 'A')
        self.assertEqual(region_code_for('Taba', 'טאבה', False, {'T'}), 'Ta')
        self.assertNotIn(region_code_for('Indonesia', 'x', False, set()), ('I', 'J'))           # I and J stay reserved

    def test_region_code_is_stored_only_when_asked(self):
        self.assertEqual(region_code(self.akhziv), 'I'); self.akhziv.refresh_from_db(); self.assertEqual(self.akhziv.trip_code, '')
        region_code(self.akhziv, persist=True); self.akhziv.refresh_from_db(); self.assertEqual(self.akhziv.trip_code, 'I')
        self.assertEqual(region_code(self.dor), 'ID')                                           # Israel Med + first letter
        self.assertEqual(region_code(self.eilat), 'J')

    def test_photographer_letter_is_empty_for_the_site_owner_only(self):
        self.assertEqual(photographer_letter(self.boaz), '')
        self.assertEqual(photographer_letter(self.bart), 'b')
        self.assertEqual(photographer_letter(self.bart, persist=True), 'b')
        self.assertEqual(Profile.objects.get(user=self.bart).trip_code, 'b')
        other = User.objects.create_user('bob', password='pw')                                  # no profile at all
        self.assertEqual(photographer_letter(other, persist=True), photographer_letter(other))
        self.assertNotEqual(photographer_letter(other), 'b')                                    # never the same letter as Bart
        self.assertEqual(photographer_letter_for('', 'x', set()), 'x')

    def test_code_is_photographer_region_year_month_without_day(self):
        self.assertEqual(suggest_code(self.boaz, self.akhziv, 2026, 8), 'I26Aug')
        self.assertEqual(suggest_code(self.bart, self.akhziv, 2026, 8), 'bI26Aug')
        self.assertEqual(suggest_code(self.boaz, self.eilat, 2025, 1, day=9), 'J25Jan')
        self.assertEqual(MONTHS_EN[1], 'Feb')

    def test_taken_code_gets_the_day_then_a_number(self):
        DiveTrip.objects.create(title='a', code='I26Aug', year=2026, month=8)
        self.assertEqual(suggest_code(self.boaz, self.akhziv, 2026, 8, day=23), 'I26Aug23')
        DiveTrip.objects.create(title='b', code='I26Aug23', year=2026, month=8)
        self.assertEqual(suggest_code(self.boaz, self.akhziv, 2026, 8, day=23), 'I26Aug-2')
        self.assertEqual(suggest_code(self.boaz, self.akhziv, 2026, 8), 'I26Aug-2')
        self.assertEqual(suggest_code(self.boaz, self.akhziv, 2026, 8, exclude_pk=DiveTrip.objects.get(code='I26Aug').pk), 'I26Aug')

    def test_title_adds_month_and_day_only_when_needed(self):
        self.assertEqual(suggest_title(self.boaz, self.akhziv, None, 2026, 8), 'בעז ליבס אכזיב 2026')
        self.assertEqual(suggest_title(self.boaz, self.akhziv, self.canyon, 2026, 8), 'בעז ליבס קניון אכזיב 2026')
        DiveTrip.objects.create(title='x', region=self.akhziv, site=self.canyon, year=2026, month=3)
        self.assertEqual(suggest_title(self.boaz, self.akhziv, self.canyon, 2026, 8), 'בעז ליבס קניון אכזיב 2026 אוגוסט')
        self.assertEqual(suggest_title(self.boaz, self.akhziv, self.island, 2026, 8), 'בעז ליבס אי האהבה 2026')      # another site: no clash
        DiveTrip.objects.create(title='y', region=self.akhziv, site=self.canyon, year=2026, month=8)
        self.assertEqual(suggest_title(self.boaz, self.akhziv, self.canyon, 2026, 8, day=23), 'בעז ליבס קניון אכזיב 2026 אוגוסט 23')
        self.assertEqual(suggest_title(self.boaz, self.akhziv, self.canyon, 2026, 8), 'בעז ליבס קניון אכזיב 2026 אוגוסט')   # no day given
        self.assertEqual(suggest_title(self.bart, self.eilat, None, 2026, 8), 'בארט אדמס אילת 2026')

    def test_region_trip_code_must_be_unique(self):
        self.akhziv.trip_code = 'I'; self.akhziv.save()
        self.dor.trip_code = 'I'
        with self.assertRaises(ValidationError): self.dor.full_clean()


class TripsPageTests(Fixture):
    def setUp(self):
        super().setUp()
        self.t1 = DiveTrip.objects.create(title='קניון אכזיב 2026', code='I6', region=self.akhziv, country=self.israel, site=self.canyon, year=2026, month=8)
        self.t2 = DiveTrip.objects.create(title='חוף אלמוג 2025', code='J5', region=self.eilat, country=self.israel, year=2025, month=1)
        self.t3 = DiveTrip.objects.create(title='אכזיב 2025', code='I5', region=self.akhziv, country=self.israel, year=2025, month=11)

    def test_login_is_required(self):
        for url in ('/observations/trips/manage/', '/observations/trips/add/', '/observations/trips/suggest/'):
            self.assertEqual(self.client.get(url).status_code, 302, url)

    def test_filters_and_add_button(self):
        self.client.force_login(self.boaz)
        page = self.client.get('/observations/trips/manage/')
        self.assertEqual({t.pk for t in page.context['trips']}, {self.t1.pk, self.t2.pk, self.t3.pk})
        page = self.client.get(f'/observations/trips/manage/?region={self.akhziv.pk}&year=2025')
        self.assertEqual([t.pk for t in page.context['trips']], [self.t3.pk])
        self.assertEqual(page.context['add_url'], f'/observations/trips/add/?region={self.akhziv.pk}&year=2025')
        page = self.client.get(f'/observations/trips/manage/?site={self.canyon.pk}')
        self.assertEqual([t.pk for t in page.context['trips']], [self.t1.pk])
        self.assertEqual(page.context['region'], self.akhziv)                       # a site implies its region
        self.assertIn(f'site={self.canyon.pk}', page.context['add_url'])
        self.assertContains(page, 'I6'); self.assertNotContains(page, 'J5')
        self.assertIn(NOW.year, page.context['years'])
        self.client.get('/observations/trips/manage/?region=abc&year=x')            # junk filters are ignored, not a 500

    def test_sample_counts_and_admin_link_for_managers(self):
        self.client.force_login(self.boaz)
        self.assertNotContains(self.client.get('/observations/trips/manage/'), '/admin/observations/divetrip/')
        self.client.force_login(self.manager)
        self.assertContains(self.client.get('/observations/trips/manage/'), f'/admin/observations/divetrip/{self.t1.pk}/change/')

    def test_nav_has_the_link(self):
        self.client.force_login(self.boaz)
        self.assertContains(self.client.get('/observations/trips/manage/'), 'href="/observations/trips/manage/"')


class AddTripTests(Fixture):
    def post(self, **data):
        base = {'region': str(self.akhziv.pk), 'year': str(NOW.year), 'month': str(NOW.month)}
        base.update({k: str(v) for k, v in data.items()})
        return self.client.post('/observations/trips/add/', base)

    def test_form_starts_from_filters_and_the_current_month(self):
        self.client.force_login(self.boaz)
        form = self.client.get(f'/observations/trips/add/?site={self.canyon.pk}').context['form']
        self.assertEqual(form.initial['region'], self.akhziv); self.assertEqual(form.initial['site'], self.canyon)
        self.assertEqual((form.initial['year'], form.initial['month']), (NOW.year, NOW.month))
        self.assertEqual(form.initial['photographer'], self.boaz)

    def test_blank_name_and_code_are_filled_by_the_server(self):
        self.client.force_login(self.boaz)
        response = self.post(site=self.canyon.pk)
        self.assertEqual(response.status_code, 302); self.assertEqual(response.url, '/observations/trips/manage/')
        trip = DiveTrip.objects.get()
        self.assertEqual(trip.title, f'בעז ליבס קניון אכזיב {NOW.year}')
        self.assertEqual(trip.code, f'I{NOW.year % 100:02d}{MONTHS_EN[NOW.month - 1]}')
        self.assertEqual((trip.region, trip.site, trip.country, trip.kind), (self.akhziv, self.canyon, self.israel, 'dive'))
        self.assertEqual(trip.country_name, 'Israel'); self.assertEqual(trip.region_name, 'Akhziv')
        self.akhziv.refresh_from_db(); self.assertEqual(self.akhziv.trip_code, 'I')            # the derived letter is now stored

    def test_day_and_typed_values_win(self):
        self.client.force_login(self.boaz)
        self.post(day=7, title='My name', code='MINE1', year=2026, month=3, duration_days=2)
        trip = DiveTrip.objects.get()
        self.assertEqual((trip.title, trip.code, trip.start_day, trip.duration_days, trip.month), ('My name', 'MINE1', 7, 2, 3))

    def test_second_trip_in_the_same_month_gets_a_distinct_code_and_a_longer_name(self):
        self.client.force_login(self.boaz)
        self.post(year=2026, month=8); self.post(year=2026, month=8, day=23)
        first, second = DiveTrip.objects.order_by('pk')
        self.assertEqual((first.code, second.code), ('I26Aug', 'I26Aug23'))
        self.assertEqual(second.title, 'בעז ליבס אכזיב 2026 אוגוסט 23')

    def test_other_photographers_carry_their_letter_and_name(self):
        self.client.force_login(self.manager)
        self.post(photographer=self.bart.pk, year=2026, month=8)
        trip = DiveTrip.objects.get()
        self.assertEqual(trip.code, 'bI26Aug'); self.assertTrue(trip.title.startswith('בארט אדמס'))
        self.assertEqual(Profile.objects.get(user=self.bart).trip_code, 'b')

    def test_a_regular_user_cannot_pick_another_photographer(self):
        self.client.force_login(self.bart)
        response = self.post(photographer=self.manager.pk, year=2026, month=8)
        self.assertEqual(response.status_code, 200)                                              # the choice is not valid for them
        self.post(year=2026, month=8)
        self.assertEqual(DiveTrip.objects.get().code, 'bI26Aug')

    def test_validation(self):
        self.client.force_login(self.boaz)
        self.assertEqual(self.post(site=self.canyon.pk, region=self.eilat.pk).status_code, 200)   # site of another region
        self.assertEqual(self.post(day=31, month=2, year=2025).status_code, 200)                  # no such date
        self.assertEqual(self.post(year=NOW.year + 1).status_code, 200)                           # future
        self.assertEqual(self.post(month=13).status_code, 200)
        DiveTrip.objects.create(title='t', code='TAKEN')
        self.assertEqual(self.post(code='TAKEN').status_code, 200)                                # typed code already used
        self.assertEqual(DiveTrip.objects.count(), 1)

    def test_next_is_followed_but_only_on_this_site(self):
        self.client.force_login(self.boaz)
        r = self.client.post('/observations/trips/add/', {'region': self.akhziv.pk, 'year': 2026, 'month': 8, 'next': '/observations/trips/manage/?year=2026'})
        self.assertEqual(r.url, '/observations/trips/manage/?year=2026')
        r = self.client.post('/observations/trips/add/', {'region': self.akhziv.pk, 'year': 2026, 'month': 9, 'next': 'https://evil.example/'})
        self.assertEqual(r.url, '/observations/trips/manage/')

    def test_suggest_endpoint_matches_what_saving_does(self):
        self.client.force_login(self.boaz)
        data = self.client.get('/observations/trips/suggest/', {'site': self.canyon.pk, 'year': 2026, 'month': 8}).json()
        self.assertEqual(data, {'title': 'בעז ליבס קניון אכזיב 2026', 'code': 'I26Aug'})
        self.post(site=self.canyon.pk, year=2026, month=8)
        data = self.client.get('/observations/trips/suggest/', {'site': self.canyon.pk, 'year': 2026, 'month': 8, 'day': 5}).json()
        self.assertEqual(data, {'title': 'בעז ליבס קניון אכזיב 2026 אוגוסט 5', 'code': 'I26Aug05'})
        self.assertEqual(self.client.get('/observations/trips/suggest/', {'year': 2026}).json(), {'title': '', 'code': ''})
        self.assertEqual(self.client.get('/observations/trips/suggest/', {'region': 'x', 'year': 'y', 'month': '99'}).json(), {'title': '', 'code': ''})

    def test_suggest_ignores_photographer_for_regular_users(self):
        self.client.force_login(self.bart)
        data = self.client.get('/observations/trips/suggest/', {'region': self.akhziv.pk, 'year': 2026, 'month': 8, 'photographer': self.boaz.pk}).json()
        self.assertEqual(data['code'], 'bI26Aug')

    def test_existing_trip_new_flow_is_unchanged(self):
        self.client.force_login(self.boaz)
        r = self.client.post('/observations/trips/new/?next=/observations/new/', {'title': 'Old way', 'country': str(self.israel.pk), 'region': str(self.akhziv.pk), 'year': '2026', 'next': '/observations/new/'})
        self.assertEqual(r.status_code, 302)
        self.assertTrue(DiveTrip.objects.filter(title='Old way').exists())
