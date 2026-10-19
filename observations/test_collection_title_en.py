"""A collection's gallery title has an English version, shown on the English site; the trip filter's
year list offers only the years of the trips in the chosen place."""
import json
from django.contrib.auth.models import User
from django.test import TestCase

from .models import Country, DiveTrip, Region, Sample, Sea
from .table_transfer import TABLES, export_table


class CollectionTitleEnTests(TestCase):
    def setUp(self):
        self.country = Country.objects.create(name='Israel')
        self.region = Region.objects.create(name='Eilat', country=self.country, sea=Sea.objects.create(name='Red Sea'))
        self.trip = DiveTrip.objects.create(title='Eilat', code='E26', year=2026, month=3, country=self.country, region=self.region)
        owner = User.objects.create_superuser('boss', 'b@example.org', 'a-valid-password-927')
        self.sample = Sample(owner=owner, kind='collection', title='צלילת לילה', title_en='Night dive', trip=self.trip,
                             video_url='https://youtu.be/12345678901')
        self.sample.save_reviewed(actor=owner, approve=True)

    def test_the_trips_page_shows_the_english_title_in_english(self):
        self.assertContains(self.client.get('/observations/trips/?lang=en'), 'Night dive')
        page = self.client.get('/observations/trips/?lang=he')
        self.assertContains(page, 'צלילת לילה'); self.assertNotContains(page, 'Night dive')

    def test_the_english_title_travels_with_the_samples_table(self):
        self.assertIn('title_en', TABLES['samples'][1])
        row = export_table('samples')['rows'][0]
        self.assertEqual(row['title_en'], 'Night dive')

    def test_the_trip_filter_knows_each_trips_place_and_year(self):
        other = Region.objects.create(name='Akhziv', country=self.country, sea=Sea.objects.create(name='Mediterranean'))
        DiveTrip.objects.create(title='Akhziv', code='A23', year=2023, month=7, country=self.country, region=other)
        self.client.force_login(User.objects.get(username='boss'))
        page = self.client.get('/observations/trips/manage/')
        places = page.context['trip_places']
        self.assertIn({'country_id': self.country.pk, 'region_id': self.region.pk, 'site_id': None, 'year': 2026}, places)
        self.assertIn({'country_id': self.country.pk, 'region_id': other.pk, 'site_id': None, 'year': 2023}, places)
        self.assertContains(page, 'id="trip-places"')

    def test_the_only_title_there_is_shows_in_either_language(self):
        self.assertEqual((self.sample.gallery_title('he'), self.sample.gallery_title('en')), ('צלילת לילה', 'Night dive'))
        self.sample.title_en = ''
        self.assertEqual(self.sample.gallery_title('en'), 'צלילת לילה')
        self.sample.title, self.sample.title_en = '', 'Night dive'
        self.assertEqual(self.sample.gallery_title('he'), 'Night dive')

    def test_the_observations_list_shows_the_title_in_the_pages_language(self):
        self.client.force_login(User.objects.get(username='boss'))
        self.assertContains(self.client.get('/observations/?lang=en'), 'Night dive')
        self.assertContains(self.client.get('/observations/?lang=he'), 'צלילת לילה')
        Sample.objects.filter(pk=self.sample.pk).update(title_en='')
        self.assertContains(self.client.get('/observations/?lang=en'), 'צלילת לילה')

    def test_the_gallery_catalog_carries_both_titles(self):
        catalog = json.loads(self.client.get('/catalog.js').content.decode().split('=', 1)[1].strip().rstrip(';'))
        collection = next(c for c in catalog['collections'] if c['sample_id'] == self.sample.pk)
        self.assertEqual((collection['title'], collection['title_en']), ('צלילת לילה', 'Night dive'))


class CollectionOrderTests(TestCase):
    def test_collections_sort_by_country_then_year_in_every_sort(self):
        from pathlib import Path
        root = Path(__file__).resolve().parent.parent
        js = (root / 'dist' / 'app.js').read_text(encoding='utf-8')
        self.assertIn('collectionsList.filter(c => collectionMatches(c, q)).sort(collectionCompare)', js)
        body = js.split('function collectionCompare(a, b) {')[1].split('\n}')[0]
        self.assertLess(body.index('a.country'), body.index('a.year'))
        self.assertIn("'country_en':", (root / 'config' / 'views.py').read_text(encoding='utf-8'))
