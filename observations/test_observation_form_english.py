"""The observation form in English (?lang=en): one language on the page.

- Every label, help text, choice, link, button and script text is English (form_translations.py, merged into the
  template filter's TRANSLATIONS; SampleForm.localize in the view).
- The chosen values are shown by their English names where they have one, and keep the Hebrew name otherwise: dive
  sites, regions and countries (also in the trip filters), trips (place and date, as on the trips page), photographers
  (the profile's English name), the cf./juv. reference rows.
- Error messages (the form's, the model's and Django's built-in ones) and the messages after saving are English;
  messages that carry a value are matched by FORM_PATTERNS.
- The Hebrew page is unchanged.
"""
import re

from django.contrib.auth.models import User
from django.test import TestCase

from .form_translations import FORM_PATTERNS, FORM_TRANSLATIONS
from .models import Country, DiveTrip, Profile, Region, Sample, Sea, Site, Species
from .templatetags.seaslugs_i18n import TRANSLATIONS, t
from .views import trip_picker_data

HEBREW = re.compile(r"[^<>\"'`\n]*[֐-׿][^<>\"'`\n]*")


class ObservationFormEnglishTests(TestCase):
    def setUp(self):
        country = Country.objects.create(name='ישראל', name_en='Israel')
        sea = Sea.objects.create(name='הים התיכון', name_en='Mediterranean Sea')
        self.region = Region.objects.create(name='אכזיב', name_en='Akhziv', country=country, sea=sea)
        self.canyon = Site.objects.create(region=self.region, name='הקניון', name_en='Canyon')
        self.hebrew_only = Site.objects.create(region=self.region, name='בלי שם באנגלית')
        self.trip = DiveTrip.objects.create(title='קניון אכזיב 2025', code='I25Nov', year=2025, month=11, country=country,
                                            region=self.region, site=self.canyon)
        self.species = Species.objects.create(genus='Goniobranchus', species='annulatus', author='(Eliot, 1904)')
        self.manager = User.objects.create_superuser('boss', 'b@example.org', 'a-valid-password-927', first_name='בועז', last_name='ליבס')
        Profile.objects.update_or_create(user=self.manager, defaults={'first_name_en': 'Boaz', 'last_name_en': 'Liebes'})
        self.client.force_login(self.manager)

    def main(self, html):
        html = re.sub(r'<datalist.*?</datalist>', '', html, flags=re.S)
        return html.split('<main>', 1)[-1]

    def hebrew_left(self, html):
        return {x.strip() for x in HEBREW.findall(self.main(html)) if x.strip()}

    def test_new_and_edit_pages_are_english(self):
        sample = Sample.objects.create(kind='species', species=self.species, genus='Goniobranchus', trip=self.trip,
                                       owner=self.manager, video_url='https://youtu.be/12345678901')
        for url in ('/observations/new/?lang=en', f'/observations/{sample.pk}/edit/?lang=en'):
            html = self.client.get(url).content.decode()
            # only a site without an English name keeps its Hebrew name
            self.assertEqual(self.hebrew_left(html), {'בלי שם באנגלית'}, url)
            for text in ('Dive trip:', 'Dive site:', 'Observation type:', 'Single species', 'Other...', 'Choose…',
                         '>Canyon<', 'Pick from the gallery photos', 'All regions', 'Akhziv'):
                self.assertIn(text, html, url)
        self.assertIn('Canyon 11/2025 (Akhziv · Israel)', html)       # the trip: English place and date
        self.assertIn('>Boaz Liebes<', html)                           # the photographer's English name

    def test_hebrew_page_is_unchanged(self):
        html = self.client.get('/observations/new/?lang=he').content.decode()
        for text in ('מסע צלילה:', 'אתר צלילה:', 'אחר...', '>הקניון<', 'בחירה מתמונות הגלריה', 'כל האזורים'):
            self.assertIn(text, html)
        self.assertNotIn('Dive site:', html)

    def test_trip_filters_use_english_names(self):
        data = trip_picker_data('en')['filters']
        self.assertEqual([r['name'] for r in data['regions']], ['Akhziv'])
        self.assertEqual([c['name'] for c in data['countries']], ['Israel'])
        self.assertEqual([s['name'] for s in data['sites']], ['Canyon'])
        self.assertEqual([r['name'] for r in trip_picker_data()['filters']['regions']], ['אכזיב'])

    def test_errors_are_english(self):
        response = self.client.post('/observations/new/?lang=en', {'kind': 'species', 'site': 'other', 'create_trip': 'on',
                                                                    'video_url': 'not a link', 'next': '/'})
        errors = response.context['form'].errors
        self.assertEqual(errors['new_trip_region'], ['Choose the trip’s region.'])
        self.assertEqual(errors['site_other'], ['Enter the dive site’s Hebrew name.'])
        self.assertIn('Enter a valid URL.', errors['video_url'])             # Django's own message
        self.assertNotIn('trip', errors)                                     # the box replaces "choose a dive trip"
        self.assertFalse(self.hebrew_left(''.join(str(e) for e in errors.values())))

    def test_messages_after_saving_are_english(self):
        response = self.client.post('/observations/new/?lang=en', {
            'kind': 'species', 'genus': 'Goniobranchus', 'species': 'annulatus', 'create_trip': 'on',
            'new_trip_region': str(self.region.pk), 'new_trip_year': '2024', 'new_trip_month': '5', 'site': 'other',
            'site_other': 'חוף', 'site_other_en': 'Beach', 'video_url': 'https://youtu.be/12345678902', 'next': '/observations/'}, follow=True)
        notices = re.findall(r'<p class="notice[^"]*">([^<]*)</p>', response.content.decode())
        self.assertIn('Dive site added: Beach.', notices)
        self.assertTrue(any(n.startswith('A dive trip was created from the observation: Beach 5/2024 (') for n in notices), notices)
        self.assertIn('The observation was published.', notices)

    def test_every_form_text_is_in_the_table(self):
        for hebrew in FORM_TRANSLATIONS:
            self.assertIn(hebrew, TRANSLATIONS)
        self.assertEqual(t('הקובץ גדול מדי (עד 20MB).', 'en'), 'The file is too large (up to 20MB).')
        self.assertEqual(t('בועז (צלם אורח)', 'en'), 'בועז (guest photographer)')
        self.assertEqual(t('הקובץ גדול מדי (עד 20MB).', 'he'), 'הקובץ גדול מדי (עד 20MB).')
        self.assertTrue(all(p.pattern for p, _ in FORM_PATTERNS))
