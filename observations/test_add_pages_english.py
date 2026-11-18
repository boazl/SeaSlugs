"""The trips management page and the add pages the observation form links to -- a dive trip, a dive site (also its popup), a species, a guest
photographer -- in English (?lang=en): headings, explanations, labels, buttons, errors (the forms' and Django's) and the
messages after saving are English, and chosen values use their English names where they exist (regions, sites,
photographers). The links from the observation form and from the trip form's "+" keep the language. The Hebrew pages
are unchanged. The trips management page shows trips by their English place and date (a trip title is Hebrew
only) and places by their English names."""
import re

from django.contrib.auth.models import User
from django.test import TestCase

from .models import Country, DiveTrip, Profile, Region, Sea, Site

HEBREW = re.compile(r"[^<>\"'`\n]*[֐-׿][^<>\"'`\n]*")
PAGES = ('/observations/trips/add/', '/observations/sites/new/', '/observations/species/new/', '/observations/photographers/new/')


class AddPagesEnglishTests(TestCase):
    def setUp(self):
        country = Country.objects.create(name='ישראל', name_en='Israel')
        self.region = Region.objects.create(name='אכזיב', name_en='Akhziv', country=country,
                                            sea=Sea.objects.create(name='הים התיכון', name_en='Mediterranean Sea'))
        self.site = Site.objects.create(region=self.region, name='הקניון', name_en='Canyon')
        self.manager = User.objects.create_superuser('boss', 'b@example.org', 'a-valid-password-927', first_name='בועז', last_name='ליבס')
        Profile.objects.update_or_create(user=self.manager, defaults={'first_name_en': 'Boaz', 'last_name_en': 'Liebes'})
        from .photographers import mark_photographer
        mark_photographer(self.manager)
        self.client.force_login(self.manager)

    def hebrew_left(self, html):
        main = re.sub(r'<datalist.*?</datalist>', '', html.split('<main>', 1)[-1], flags=re.S)
        return {x.strip() for x in HEBREW.findall(main) if x.strip()}

    def test_pages_are_english(self):
        for page in PAGES:
            html = self.client.get(page + '?lang=en').content.decode()
            self.assertEqual(self.hebrew_left(html), set(), page)
        html = self.client.get('/observations/trips/add/?lang=en').content.decode()
        for text in ('Add a dive trip', '>Akhziv<', '>Canyon<', '>Boaz Liebes<', 'Save the trip', 'Dive site (optional)'):
            self.assertIn(text, html)
        self.assertIn('popup=1&amp;lang=en', html)              # the "+" keeps the language

    def test_hebrew_pages_unchanged(self):
        html = self.client.get('/observations/trips/add/?lang=he').content.decode()
        for text in ('הוספת מסע צלילה', '>אכזיב<', '>הקניון<', 'שמירת המסע'):
            self.assertIn(text, html)

    def test_errors_are_english(self):
        cases = (('/observations/trips/add/', {'month': '13'}, 'A month between 1 and 12.', True),
                 ('/observations/sites/new/', {'region': str(self.region.pk), 'name': 'canyon'},
                  'The site "Canyon" already exists in this region. Choose it from the dive sites list.', False),
                 ('/observations/species/new/', {'genus': 'Two words', 'species': 'x'}, 'The genus is one word.', False),
                 ('/observations/photographers/new/', {'phone': 'abc'}, 'Invalid phone number.', True))
        for page, data, message, required in cases:
            response = self.client.post(page + '?lang=en', data)
            errors = [m for messages in response.context['form'].errors.values() for m in messages]
            self.assertIn(message, errors, page)
            if required: self.assertIn('This field is required.', errors, page)       # Django's own message
            self.assertFalse(self.hebrew_left(' '.join(errors)), page)

    def test_messages_after_saving(self):
        response = self.client.post('/observations/sites/new/?lang=en', {'region': str(self.region.pk), 'name': 'חוף', 'name_en': 'Beach',
                                                                        'next': '/observations/trips/add/?lang=en'}, follow=True)
        self.assertContains(response, 'Dive site added: Beach.')
        response = self.client.post('/observations/trips/add/?lang=en', {'region': str(self.region.pk), 'site': str(self.site.pk), 'year': '2024',
                                                                        'month': '5', 'next': '/observations/'}, follow=True)
        trip = DiveTrip.objects.get()
        self.assertContains(response, f'Dive trip added: Canyon 5/2024 ({trip.code}).')
        popup = self.client.post('/observations/sites/new/?lang=en', {'region': str(self.region.pk), 'name': 'חדש', 'name_en': 'New', 'popup': '1'})
        self.assertContains(popup, '"name": "New"')
        self.assertContains(popup, 'Site added')

    def test_observation_form_links_keep_the_language(self):
        html = self.client.get('/observations/new/?lang=en').content.decode()
        for link in ('species-add-link', 'photographer-add-link', 'trip-add-link'):
            self.assertRegex(html, rf'id="{link}" href="[^"]*lang=en')

    def test_trips_management_page_is_english(self):
        DiveTrip.objects.create(title='קניון אכזיב 2026', code='I6', year=2026, month=8, country=self.region.country, region=self.region, site=self.site)
        html = self.client.get('/observations/trips/manage/?lang=en').content.decode()
        self.assertEqual(self.hebrew_left(html), set())
        for text in ('Manage dive trips', '>Code', 'Actions', '+ Add a trip', 'Canyon 8/2026', 'Akhziv · Canyon', 'Add observation', 'Edit'):
            self.assertIn(text, html)
        html = self.client.get('/observations/trips/manage/?lang=he').content.decode()
        for text in ('ניהול מסעות צלילה', 'קניון אכזיב 2026', 'אכזיב · הקניון', 'פעולות'):
            self.assertIn(text, html)
