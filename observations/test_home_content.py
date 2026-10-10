"""SEO phase 3: the home page's readable content (hero, sections, numbers line, crawlable links) is in the
HTML the server sends, in the language of the URL, and both languages are embedded for the language button."""
import json
import re

from django.core.cache import cache

from .home_content import clear_cache
from .models import Country, Sea, Region, DiveTrip, Species, Sample, SpeciesArea
from .test_seo import SeoFixture

class HomeContentTests(SeoFixture):
    def setUp(self):
        super().setUp()
        clear_cache()
        self.addCleanup(clear_cache)
        self.israel = Country.objects.get(name_en='Israel')
        sea = Sea.objects.create(name='הים התיכון', name_en='Mediterranean')
        region = Region.objects.create(name='חיפה', name_en='Haifa', country=self.israel, sea=sea)
        trip = DiveTrip.objects.create(title='Haifa', year=2025, country=self.israel, region=region)
        self.migrant = Species.objects.create(scientific_name='Cuthona perca', genus='Cuthona', name_he='חינניית ים מהגרת',
                                              is_migrant=True)
        Sample(owner=self.owner, trip=trip, species=self.migrant, video_url='https://youtu.be/bcdefghijkl').save_reviewed()
        self.med_area = SpeciesArea.objects.get(species=self.migrant)

    def test_hebrew_home_has_the_content_without_javascript(self):
        html = self.page('/')
        for text in ('חינניות ים: מידע, תמונות ומיזם מחקר בים התיכון', 'מה הן חינניות ים?',
                     'המיזם: חינניות ים בים התיכון של ישראל', 'איך תורמים תצפית?', 'תרמו תצפית',
                     'בעיקר מהפיליפינים'):
            self.assertIn(text, html)
        self.assertEqual(html.count('<h1>'), 1)

    def test_english_home_is_in_english(self):
        html = self.page('/?lang=en')
        self.assertIn('Sea slugs: information, photos and a Mediterranean research project', html)
        self.assertIn('What are sea slugs?', html)
        self.assertIn('How do you contribute an observation?', html)
        self.assertEqual(html.count('<h1>'), 1)
        self.assertNotIn('איך תורמים תצפית?', html.split('<body>')[1])

    def test_the_hero_has_no_buttons_or_search_because_the_page_shows_them_right_below(self):
        html = self.page('/')
        hero = html.split('data-home-section="hero"')[1].split('</section>')[0]
        for needle in ('class="btn', 'heroSearch', 'hero-actions'):
            self.assertNotIn(needle, hero)
        # the one contribute button is at the end of the how-to-contribute section
        contribute = html.split('data-home-section="contribute"')[1].split('</section>')[0]
        self.assertIn('class="btn btn-primary"', contribute)

    def test_the_bottom_link_block_is_gone(self):
        html = self.page('/')
        self.assertNotIn('id="israel-species"', html)
        self.assertNotIn('דפדוף לפי קבוצות', html)
        self.assertNotIn('home-links', html)

    def test_numbers_line_is_built_from_the_data(self):
        html = self.page('/')
        note = re.search(r'collection-note[^>]*>(.*?)</p>', html, re.S).group(1)
        self.assertIn('2 מינים', note)
        self.assertIn('2 תצפיות', note)
        self.assertIn('1 מהמינים תועדו בים התיכון של ישראל', note)
        self.assertNotIn('בעיקר ישראל', note)

    def test_contribute_button_depends_on_login(self):
        self.assertIn('href="/observations/signup/">תרמו תצפית', self.page('/'))
        self.client.force_login(self.owner)
        html = self.page('/')
        self.assertIn('href="/observations/new/">תרמו תצפית', html)
        self.assertNotIn('/observations/signup/">תרמו', html)

    def test_footer_keeps_the_credit_and_adds_the_invitation(self):
        html = self.page('/')
        footer = html.split('<footer>')[1]
        self.assertIn('צילום: בועז ליבס', footer)
        self.assertIn('יש לכם תמונה של חיננית ים?', footer)
        self.assertIn('Have a photo of a sea slug?', self.page('/?lang=en').split('<footer>')[1])

    def test_both_languages_are_embedded_for_the_language_button(self):
        html = self.page('/')
        data = json.loads(re.search(r'<script id="home-content" type="application/json">(.*?)</script>', html, re.S).group(1))
        self.assertEqual(set(data), {'he', 'en'})
        self.assertEqual(set(data['he']), set(data['en']))
        self.assertIn('What are sea slugs?', data['en']['what'])
        self.assertIn('מה הן חינניות ים?', data['he']['what'])

    def test_the_gallery_hooks_the_script_needs_are_still_there(self):
        html = self.page('/')
        for needle in ('id="collectionTitle"', 'id="search"', 'id="areaFilters"',
                       'data-home-action="migrant"', 'class="footer-tagline"'):
            self.assertIn(needle, html)

    def test_the_counts_are_cached_for_a_while(self):
        self.page('/')
        Sample(owner=self.owner, trip=self.trip, species=Species.objects.create(
            scientific_name='Hypselodoris infucata', genus='Hypselodoris'),
            video_url='https://youtu.be/cdefghijklm').save_reviewed()
        self.assertIn('2 מינים', self.page('/'))
        clear_cache()
        self.assertIn('3 מינים', self.page('/'))


class AreaFilterTests(SeoFixture):
    """The gallery's area buttons are per sea: the Red Sea is one button however many countries' coasts it was
    observed from."""

    def catalog(self):
        text = self.client.get('/catalog.js').content.decode()
        return json.loads(text[len('window.SEASLUGS = '):-1])

    def test_two_countries_on_one_sea_make_one_area_named_after_the_sea(self):
        sinai = Country.objects.create(name='סיני', name_en='Sinai')
        red_sea = Sea.objects.get(name_en='Red Sea')
        region = Region.objects.create(name='דהב', name_en='Dahab', country=sinai, sea=red_sea)
        trip = DiveTrip.objects.create(title='Dahab', year=2024, country=sinai, region=region)
        other = Species.objects.create(scientific_name='Hypselodoris infucata', genus='Hypselodoris')
        Sample(owner=self.owner, trip=trip, species=other, video_url='https://youtu.be/cdefghijklm').save_reviewed()
        data = self.catalog()
        self.assertEqual(data['areas'], {f'sea-{red_sea.pk}': {'label': 'ים סוף', 'label_en': 'Red Sea'}})
        self.assertEqual({sp['area'] for sp in data['species']}, {f'sea-{red_sea.pk}'})
