"""SEO phase 3: the home page's readable content (hero, sections, numbers line, crawlable links) is in the
HTML the server sends, in the language of the URL, and both languages are embedded for the language button."""
import json
import re

from django.contrib.auth.models import User
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

    def test_the_links_block_is_collapsed_and_sits_after_the_text_panel(self):
        html = self.page('/').split('<body>')[1]
        block = html.split('data-home-section="browse"')[1].split('</main>')[0]
        self.assertIn('<details class="browse-details">', block)  # no "open" attribute: closed until opened
        self.assertIn('דפדוף לפי קבוצות ומינים מהים התיכון של ישראל', block)
        self.assertGreater(html.index('data-home-section="browse"'), html.index('data-home-section="contribute"'))

    def test_numbers_line_is_built_from_the_data(self):
        html = self.page('/')
        note = re.search(r'collection-note[^>]*>(.*?)</p>', html, re.S).group(1)
        self.assertIn('2 מינים', note)
        self.assertIn('2 תצפיות', note)
        self.assertIn('1 מהמינים תועדו בים התיכון של ישראל', note)
        self.assertNotIn('בעיקר ישראל', note)

    def test_the_israeli_mediterranean_list_has_only_mediterranean_species_and_links_to_their_pages(self):
        html = self.page('/')
        block = html.split('id="israel-species"')[1].split('</ul>')[0]
        self.assertIn(f'href="/species/{self.med_area.slug}/"', block)
        self.assertIn('Cuthona perca', block)
        self.assertNotIn('Chromodoris annae', block)  # the Red Sea species is not an Israeli Mediterranean one
        self.assertIn('(מהגר)', block)

    def test_the_english_links_keep_the_language(self):
        html = self.page('/?lang=en')
        self.assertIn(f'href="/species/{self.med_area.slug}/?lang=en"', html)
        self.assertIn(f'href="/order/{self.order.pk}/?lang=en"', html)
        self.assertIn('href="/family/Chromodorididae/?lang=en"', html)
        self.assertIn('Browse by group and by Israeli Mediterranean species', html)

    def test_the_hebrew_links_to_taxonomic_groups_are_plain(self):
        html = self.page('/')
        self.assertIn(f'href="/order/{self.order.pk}/"', html)
        self.assertIn('href="/family/Chromodorididae/"', html)

    def test_every_linked_page_answers_200(self):
        html = self.page('/')
        links = set(re.findall(r'href="(/(?:species|order|family)/[^"]+)"', html))
        self.assertTrue(links)
        for link in links:
            self.assertEqual(self.client.get(link).status_code, 200, link)

    def test_both_languages_of_the_links_block_are_embedded_for_the_language_button(self):
        html = self.page('/')
        data = json.loads(re.search(r'id="home-content" type="application/json">(.*?)</script>', html, re.S).group(1))
        self.assertIn('Browse by group', data['en']['browse'])
        self.assertIn('דפדוף לפי קבוצות', data['he']['browse'])

    def test_contribute_button_says_add_observation_and_depends_on_login(self):
        self.assertIn('class="btn btn-primary" href="/observations/signup/">הוספת תצפית</a>', self.page('/'))
        self.assertIn('class="btn btn-primary" href="/observations/signup/">Add an observation</a>', self.page('/?lang=en'))
        self.client.force_login(self.owner)
        html = self.page('/')
        self.assertIn('class="btn btn-primary" href="/observations/new/">הוספת תצפית</a>', html)
        self.assertNotIn('/observations/signup/', html.split('<body>')[1].split('id="player"')[0])

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


class MarkupTests(SeoFixture):
    def render(self, text, **kw):
        from .home_markup import render_markup
        return str(render_markup(text, {'species': 5, 'observations': 7, 'israeli': 2}, '/observations/new/', **kw))

    def test_blocks(self):
        html = self.render('~ small\n# Title\n## Head\nfirst line\nsecond line\n\n1. one\n2. two\n\n- a\n- b')
        self.assertEqual(html, '<p class="eyebrow">small</p>\n<h1>Title</h1>\n<h2>Head</h2>\n<p>first line second line</p>\n'
                               '<ol class="steps"><li>one</li><li>two</li></ol>\n<ul class="steps"><li>a</li><li>b</li></ul>')

    def test_inline_links_button_numbers_and_escaping(self):
        html = self.render('**bold** [x](contribute) [y](migrant) [z](https://e.org/?a=1&b=2) [bad](javascript:alert(1)) [[Go]] {species}/{observations}/{israeli} <script>')
        self.assertIn('<strong>bold</strong>', html)
        self.assertIn('<a href="/observations/new/">x</a>', html)
        self.assertIn('<a href="#collectionTitle" data-home-action="migrant">y</a>', html)
        self.assertIn('<a href="https://e.org/?a=1&amp;b=2">z</a>', html)
        self.assertIn('<a href="#">bad</a>', html)
        self.assertIn('<a class="btn btn-primary" href="/observations/new/">Go</a>', html)
        self.assertIn('5/7/2', html)
        self.assertIn('&lt;script&gt;', html)
        self.assertNotIn('<script>', html)

    def test_inline_mode_has_no_blocks(self):
        self.assertEqual(self.render('a\nb **c**', inline=True), 'a b <strong>c</strong>')


class HomeTextEditTests(SeoFixture):
    def setUp(self):
        super().setUp()
        clear_cache()
        self.addCleanup(clear_cache)
        self.url = '/observations/home-text/'

    def post(self, **values):
        from .home_defaults import DEFAULTS
        data = {f'{key}__{lang}': DEFAULTS[key][lang] for key in DEFAULTS for lang in ('he', 'en')}
        data.update(values)
        return self.client.post(self.url, data)

    def test_only_managers_can_open_it(self):
        self.assertEqual(self.client.get(self.url).status_code, 302)  # to the login page
        User.objects.create_user('plain', password='pw')
        self.client.login(username='plain', password='pw')
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self.client.post(self.url, {'what__he': 'x'}).status_code, 404)

    def test_the_screen_shows_every_section_in_both_languages_with_the_defaults(self):
        self.client.force_login(self.owner)
        html = self.page(self.url)
        for key in ('hero', 'what', 'project', 'contribute', 'collection_note', 'footer_invite', 'meta_title', 'meta_description'):
            for lang in ('he', 'en'):
                self.assertIn(f'name="{key}__{lang}"', html)
        self.assertIn('מה הן חינניות ים?', html)
        self.assertIn('[[הוספת תצפית]]', html)

    def test_an_edited_text_replaces_the_default_in_that_language_only(self):
        self.client.force_login(self.owner)
        response = self.post(what__he='## כותרת חדשה\nפסקה חדשה עם **הדגשה**.')
        self.assertEqual(response.status_code, 302)
        self.client.logout()
        he = self.page('/')
        self.assertIn('<h2>כותרת חדשה</h2>', he)
        self.assertIn('<p>פסקה חדשה עם <strong>הדגשה</strong>.</p>', he)
        self.assertNotIn('מה הן חינניות ים?', he.split('<body>')[1].split('<script')[0])
        self.assertIn('What are sea slugs?', self.page('/?lang=en'))
        import json, re
        data = json.loads(re.search(r'id="home-content" type="application/json">(.*?)</script>', he, re.S).group(1))
        self.assertIn('כותרת חדשה', data['he']['what'])

    def test_clearing_or_restoring_the_default_removes_the_override(self):
        from .models import HomeText
        self.client.force_login(self.owner)
        self.post(what__he='משהו אחר')
        self.assertEqual(HomeText.objects.filter(key='what').count(), 1)
        self.post(what__he='')
        self.assertEqual(HomeText.objects.count(), 0)
        self.assertIn('מה הן חינניות ים?', self.page('/'))

    def test_saving_the_untouched_form_stores_nothing(self):
        from .models import HomeText
        self.client.force_login(self.owner)
        self.post()
        self.assertEqual(HomeText.objects.count(), 0)

    def test_google_title_and_description_can_be_edited(self):
        self.client.force_login(self.owner)
        self.post(meta_title__he='כותרת חדשה | SeaSlugs', meta_description__en='My description')
        self.client.logout()
        he = self.page('/')
        self.assertIn('<title>כותרת חדשה | SeaSlugs</title>', he)
        self.assertIn('content="My description"', self.page('/?lang=en'))

    def test_the_account_menu_links_the_screen_for_managers_only(self):
        self.assertNotIn('/observations/home-text/', self.page('/'))
        self.client.force_login(self.owner)
        self.assertIn('/observations/home-text/', self.page('/'))


class BeforeMigrationTests(SeoFixture):
    def test_the_home_page_works_even_if_the_home_text_table_does_not_exist_yet(self):
        from unittest import mock
        from django.db import OperationalError
        clear_cache()
        with mock.patch('observations.models.HomeText.objects') as manager:
            manager.all.side_effect = OperationalError('no such table')
            manager.filter.side_effect = OperationalError('no such table')
            self.assertIn('מה הן חינניות ים?', self.page('/'))


class LanguageLinksTests(SeoFixture):
    def test_the_species_list_of_an_english_genus_page_keeps_the_language(self):
        html = self.page(f'/genus/{self.genus.name}/?lang=en')
        self.assertIn(f'href="/species/{self.area.slug}/?lang=en"', html)
        self.client.cookies.clear()  # the ?lang=en visit above is remembered in a cookie
        self.assertIn(f'href="/species/{self.area.slug}/"', self.page(f'/genus/{self.genus.name}/'))

    def test_the_community_pages_menu_keeps_the_language(self):
        html = self.page('/observations/login/?lang=en')
        self.assertIn('<a href="/?lang=en">', html)
        self.assertIn('href="/observations/trips/?lang=en"', html)
        self.client.cookies.clear()
        hebrew = self.page('/observations/login/')
        self.assertIn('<a href="/">', hebrew)


class MainNavigationTests(SeoFixture):
    """The main navigation shows one language at a time (the page's), with an icon on each item; the home page's
    language button swaps it using the data-he / data-en attributes."""

    def menu(self, url):
        html = self.client.get(url).content.decode()
        return html.split('<nav class="account-menu"')[1].split('</nav>')[0].partition('>')[2]

    def test_hebrew_menu_has_no_english_labels(self):
        self.client.force_login(self.owner)
        visible = re.sub(r'<[^>]+>', ' ', self.menu('/'))
        for hebrew in ('גלריה', 'מסעות צלילה', 'תצפיות', 'הפרופיל שלי', 'שלום', 'יציאה'):
            self.assertIn(hebrew, visible)
        for english in ('Gallery', 'Dive trips', 'Observations', 'Profile', 'Hello', 'Logout', ' / '):
            self.assertNotIn(english, visible)

    def test_english_menu_has_no_hebrew_labels_and_greets_with_hello_and_logout(self):
        self.client.force_login(self.owner)
        menu = self.menu('/?lang=en')
        visible = re.sub(r'<[^>]+>', ' ', menu)
        for english in ('Gallery', 'Dive trips', 'Observations', 'My profile', 'Hello,', 'Logout'):
            self.assertIn(english, visible)
        self.assertNotRegex(visible, r'[֐-׿]')
        self.assertIn('>Logout<', menu)

    def test_every_item_has_an_icon_and_both_languages_for_the_language_button(self):
        self.client.force_login(self.owner)
        menu = self.menu('/')
        self.assertEqual(menu.count('class="nav-icon"'), menu.count('nav-item'))
        self.assertIn('data-he="מסעות צלילה" data-en="Dive trips"', menu)
        self.assertIn('data-en="Hello, ', menu)

    def test_signed_out_menu_is_one_language_too(self):
        visible = re.sub(r'<[^>]+>', ' ', self.menu('/?lang=en'))
        for english in ('Gallery', 'Dive trips', 'Login', 'Sign up'):
            self.assertIn(english, visible)
        self.assertNotRegex(visible, r'[֐-׿]')
