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
        self.assertIn('<a class="nav-item" href="/?lang=en" title="Home page"', html)
        self.assertIn('href="/observations/trips/?lang=en"', html)
        self.client.cookies.clear()
        hebrew = self.page('/observations/login/')
        self.assertIn('<a class="nav-item" href="/" title="דף הבית"', hebrew)


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


class CommunityPagesNavigationTests(SeoFixture):
    """Observations, trips, profile and partners pages share base.html's navigation: icon buttons, one language."""

    PAGES = ('/observations/', '/observations/trips/', '/observations/profile/', '/observations/partners/')

    def nav(self, url):
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200, url)
        return response.content.decode().split('<body>')[1].split('<main')[0]  # header, opening panel, tools row

    def test_every_nav_item_has_an_icon_on_each_page_in_both_languages(self):
        self.client.force_login(self.owner)
        for url in self.PAGES:
            for suffix in ('', '?lang=en'):
                self.client.cookies.clear()
                self.client.force_login(self.owner)
                nav = self.nav(url + suffix)
                self.assertEqual(nav.count('class="nav-icon"'), nav.count('nav-item'), url + suffix)
                self.assertGreaterEqual(nav.count('nav-item'), 8, url + suffix)

    def test_english_pages_show_only_english_labels(self):
        self.client.force_login(self.owner)
        for url in self.PAGES:
            self.client.cookies.clear()
            self.client.force_login(self.owner)
            visible = re.sub(r'<[^>]+>', ' ', self.nav(url + '?lang=en'))
            self.assertIn('Hello,', visible)
            self.assertIn('Logout', visible)
            self.assertIn('Add observation', visible)
            self.assertNotRegex(visible.replace('עברית', ''), r'[\u0590-\u05ff]', url)

    def test_the_gallery_item_is_marked_as_the_home_page(self):
        for lang, title in (('', 'דף הבית'), ('?lang=en', 'Home page')):
            self.client.cookies.clear()
            nav = self.nav('/observations/trips/' + lang)
            self.assertRegex(nav, r'<a class="nav-item" href="/(\?lang=en)?" title="%s"' % title)

    def test_english_pages_link_every_nav_item_with_the_language_and_hebrew_pages_stay_plain(self):
        self.client.force_login(self.owner)
        for url in self.PAGES:
            self.client.cookies.clear()
            self.client.force_login(self.owner)
            links = re.findall(r'<a class="nav-item" href="(/[^"]*)"', self.nav(url + '?lang=en'))
            self.assertGreaterEqual(len(links), 8, url)
            self.assertTrue(all('lang=en' in link for link in links), (url, links))
            self.client.cookies.clear()
            self.client.force_login(self.owner)
            links = re.findall(r'<a class="nav-item" href="(/[^"]*)"', self.nav(url + '?lang=he'))
            self.assertTrue(all('lang=' not in link for link in links), (url, links))

    def test_the_chosen_language_is_remembered_across_pages_and_an_explicit_choice_replaces_it(self):
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get('/observations/trips/?lang=en').cookies['seaslugs_lang'].value, 'en')
        self.assertIn('>Dive trips<', self.client.get('/observations/profile/').content.decode())  # no ?lang: cookie
        self.assertEqual(self.client.get('/observations/trips/?lang=he').cookies['seaslugs_lang'].value, 'he')
        hebrew = self.client.get('/observations/profile/').content.decode().split('<main')[0]
        self.assertNotIn('>Dive trips<', hebrew)
        self.assertIn('>מסעות צלילה<', hebrew)


class RedSeaNumbersTests(SeoFixture):
    """{red_sea} {eilat} {sinai} in the editable texts count species by where they were recorded."""

    def setUp(self):
        super().setUp()
        clear_cache()
        self.addCleanup(clear_cache)
        from .models import HomeText
        sinai = Country.objects.create(name='סיני', name_en='Sinai')
        red_sea = Sea.objects.get(name_en='Red Sea')
        region = Region.objects.create(name='דהב', name_en='Dahab', country=sinai, sea=red_sea)
        trip = DiveTrip.objects.create(title='Dahab', year=2024, country=sinai, region=region)
        for name, video in (('Hypselodoris infucata', 'cdefghijklm'), ('Nembrotha cristata', 'defghijklmn')):
            species = Species.objects.create(scientific_name=name, genus=name.split()[0])
            Sample(owner=self.owner, trip=trip, species=species, video_url=f'https://youtu.be/{video}').save_reviewed()
        HomeText.objects.create(key='collection_note', lang='he',
                                content='ים סוף {red_sea}, אילת {eilat}, סיני {sinai}, ים תיכון {israeli}')

    def test_each_variable_counts_its_own_place(self):
        html = self.page('/')
        note = re.search(r'collection-note[^>]*>(.*?)</p>', html, re.S).group(1)
        # the fixture's Eilat species (Chromodoris annae) is in the Red Sea too; the two Sinai species only in Sinai
        self.assertEqual(note, 'ים סוף 3, אילת 1, סיני 2, ים תיכון 0')


class SiteHeaderCssTests(SeoFixture):
    """dist/site-header.css (the header on the community pages) is a verbatim copy of rules in dist/styles.css."""

    @staticmethod
    def rules(css):
        css = re.sub(r'/\*.*?\*/', '', css, flags=re.S)
        out, i = [], 0
        while True:
            j = css.find('{', i)
            if j < 0:
                return out
            depth, k = 1, j + 1
            while depth:
                depth += {'{': 1, '}': -1}.get(css[k], 0)
                k += 1
            selector, body = css[i:j].strip(), css[j + 1:k - 1]
            if selector.startswith('@media'):
                out += [(f'{selector} {s}', b) for s, b in SiteHeaderCssTests.rules(body)]
            else:
                out.append((selector, body))
            i = k

    def test_every_copied_rule_still_matches_the_home_page_stylesheet(self):
        from django.conf import settings
        squash = lambda text: re.sub(r'\s+', '', text)
        home = {(squash(s), squash(b)) for s, b in self.rules((settings.BASE_DIR / 'dist/styles.css').read_text())}
        copied = self.rules((settings.BASE_DIR / 'dist/site-header.css').read_text())
        own = ('.intro .intro-title', '.hero-wrap', ':root', '.masthead a.brand', '.masthead,.hero-wrap', '.masthead a', '.masthead,.masthead *,.hero-wrap,.hero-wrap *')  # rules that exist only in site-header.css
        checked = 0
        for selector, body in copied:
            if selector in own:
                continue
            checked += 1
            self.assertIn((squash(selector), squash(body)), home, selector)
        self.assertGreater(checked, 25)

    def test_the_stylesheet_is_served(self):
        response = self.client.get('/site-header.css')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/css; charset=utf-8')


class MobileMenuScriptTests(SeoFixture):
    """The narrow-screen menu button needs a script on every page that has the header (it was missing on the
    species, genus and group pages, where the button did nothing)."""

    def test_pages_with_the_header_carry_the_menu_script(self):
        for url in ('/observations/trips/', '/observations/login/', f'/species/{self.area.slug}/',
                    '/genus/Chromodoris/', f'/order/{self.order.pk}/', '/family/Chromodorididae/'):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200, url)
            self.assertIn('.account-menu-toggle', response.content.decode(), url)


class CommunityPageLanguageAttributesTests(SeoFixture):
    def test_every_community_page_declares_its_language_and_direction(self):
        for url, lang, direction in (('/observations/login/?lang=en', 'en', 'ltr'), ('/observations/signup/?lang=en', 'en', 'ltr'),
                                     ('/observations/login/?lang=he', 'he', 'rtl'), ('/observations/trips/?lang=en', 'en', 'ltr')):
            self.client.cookies.clear()
            html = self.client.get(url).content.decode()
            self.assertIn(f'<html lang="{lang}" dir="{direction}">', html, url)
        # and the brand is drawn the way the home page draws it: the Latin wordmark in English, the Hebrew one in Hebrew
        self.client.cookies.clear()
        self.assertIn('<html lang="en"', self.client.get('/observations/login/?lang=en').content.decode())


class GalleryHeadingTests(SeoFixture):
    def test_the_gallery_heading_stays_for_screen_readers_but_is_not_drawn(self):
        from django.conf import settings
        html = self.page('/')
        self.assertIn('<h2 id="collectionTitle">', html)  # the "#collectionTitle" link target and the section's label
        css = (settings.BASE_DIR / 'dist/styles.css').read_text()
        self.assertIn('.collection-head h2{position:absolute;width:1px;height:1px', css)
