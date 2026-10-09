"""SEO phase 1: technical fixes that change no URL, record or visible layout --
the genus sitemap rule, /index.html, the language kept in navigation links, the place in
species titles and the data-built fallback description."""
from django.template import Context, Template

from .models import Country, Sea, Region, DiveTrip, Species, Sample, SpeciesArea, TaxonGenus
from .templatetags.seaslugs_i18n import with_lang
from .test_seo import SeoFixture, BASE


class SitemapGenusRuleTests(SeoFixture):
    def test_a_genus_with_species_but_no_photo_of_its_own_is_listed_because_its_page_is_live(self):
        # SeoFixture's genus has no defining sample of its own; its page still answers 200.
        self.assertEqual(self.client.get(f'/genus/{self.genus.name}/').status_code, 200)
        content = self.client.get('/sitemap.xml').content.decode()
        self.assertIn(f'<loc>{BASE}/genus/{self.genus.name}/</loc>', content)

    def test_a_genus_without_any_shown_species_is_not_listed(self):
        TaxonGenus.objects.create(name='Hypselodoris', family=self.family)
        self.assertEqual(self.client.get('/genus/Hypselodoris/').status_code, 404)
        self.assertNotIn('/genus/Hypselodoris/', self.client.get('/sitemap.xml').content.decode())

    def test_every_listed_genus_page_answers_200(self):
        import re
        content = self.client.get('/sitemap.xml').content.decode()
        genus_urls = re.findall(r'<loc>https://seaslugs.org.il(/genus/[^<]+)</loc>', content)
        self.assertTrue(genus_urls)
        for url in genus_urls:
            self.assertEqual(self.client.get(url).status_code, 200, url)


class IndexHtmlTests(SeoFixture):
    def test_index_html_redirects_permanently_to_the_root(self):
        response = self.client.get('/index.html')
        self.assertEqual((response.status_code, response['Location']), (301, '/'))

    def test_index_html_keeps_the_query_string(self):
        self.assertEqual(self.client.get('/index.html?lang=en')['Location'], '/?lang=en')

    def test_the_root_and_the_static_assets_still_serve(self):
        self.assertEqual(self.client.get('/').status_code, 200)
        for name in ('styles.css', 'app.js', 'catalog.js'):
            self.assertEqual(self.client.get(f'/{name}').status_code, 200, name)


class RobotsTests(SeoFixture):
    def test_trip_management_pages_are_disallowed_but_the_public_trips_list_is_not(self):
        rules = [line.split(': ', 1)[1] for line in self.client.get('/robots.txt').content.decode().splitlines()
                 if line.startswith('Disallow: ')]
        self.assertIn('/observations/trips/manage/', rules)
        self.assertIn('/observations/trips/add/', rules)
        self.assertNotIn('/observations/trips/', rules)


class WithLangFilterTests(SeoFixture):
    def test_unchanged_on_hebrew_and_suffixed_on_english(self):
        self.assertEqual(with_lang('/x/', 'he'), '/x/')
        self.assertEqual(with_lang('/x/', 'en'), '/x/?lang=en')
        self.assertEqual(with_lang('/x/?a=1', 'en'), '/x/?a=1&lang=en')
        self.assertEqual(with_lang('/x/#top', 'en'), '/x/?lang=en#top')
        self.assertEqual(with_lang('/x/?lang=en', 'en'), '/x/?lang=en')

    def test_english_species_page_navigation_keeps_the_language(self):
        html = self.page(f'/species/{self.area.slug}/?lang=en')
        self.assertIn('<a class="brand" href="/?lang=en"', html)
        self.assertIn('<a href="/?lang=en">', html)              # the "Gallery" breadcrumb
        self.assertIn('href="/observations/trips/?lang=en"', html)
        self.assertIn('href="/observations/login/?lang=en"', html)
        self.assertIn('href="/observations/signup/?lang=en"', html)

    def test_hebrew_species_page_navigation_is_unchanged(self):
        html = self.page(f'/species/{self.area.slug}/')
        self.assertIn('<a class="brand" href="/"', html)
        menu = html.split('class="language-switch"')[0].split('<header')[1]   # the language switch itself links to ?lang=en
        self.assertNotIn('?lang=en', menu)

    def test_genus_and_family_pages_keep_the_language_too(self):
        for url in (f'/genus/{self.genus.name}/', f'/family/{self.family.name}/', f'/order/{self.order.pk}/'):
            html = self.page(url + '?lang=en')
            self.assertIn('<a class="brand" href="/?lang=en"', html, url)


class SpeciesTitleAndDescriptionTests(SeoFixture):
    def make_population(self, country_name, country_en, sea_name, sea_en, region_en):
        country = Country.objects.get_or_create(name=country_name, defaults={'name_en': country_en})[0]
        sea = Sea.objects.get_or_create(name=sea_name, defaults={'name_en': sea_en})[0]
        region = Region.objects.create(name=region_en, name_en=region_en, country=country, sea=sea)
        trip = DiveTrip.objects.create(title=region_en, year=2025, country=country, region=region)
        Sample(owner=self.owner, trip=trip, species=self.species, video_url='https://youtu.be/bcdefghijkl').save_reviewed()
        return SpeciesArea.objects.get(species=self.species, country=country, sea=sea)

    def test_the_place_is_part_of_the_title(self):
        html = self.page(f'/species/{self.area.slug}/')
        self.assertIn('<title>Chromodoris annae — חינניית אנה · ישראל | SeaSlugs</title>', html)

    def test_populations_sharing_a_scientific_name_get_different_titles(self):
        # same species, a second population in another country: titles must differ
        other = self.make_population('פיליפינים', 'Philippines', 'דרום סין', 'South China Sea', 'Anilao')
        t1 = self.page(f'/species/{self.area.slug}/').split('<title>')[1].split('</title>')[0]
        t2 = self.page(f'/species/{other.slug}/').split('<title>')[1].split('</title>')[0]
        self.assertNotEqual(t1, t2)
        self.assertIn('פיליפינים', t2)
        # both URLs and both populations are untouched
        self.assertEqual(SpeciesArea.objects.filter(species=self.species).count(), 2)

    def test_two_seas_of_one_country_are_told_apart_by_the_sea(self):
        med = self.make_population('ישראל', 'Israel', 'ים התיכון', 'Mediterranean', 'Akhziv')
        titles = {self.page(f'/species/{a.slug}/').split('<title>')[1].split('</title>')[0]
                  for a in SpeciesArea.objects.filter(species=self.species)}
        self.assertEqual(len(titles), 2)
        self.assertTrue(any('ישראל, ים התיכון' in t for t in titles))

    def test_a_written_description_is_kept_as_is(self):
        html = self.page(f'/species/{self.area.slug}/')
        self.assertIn('<meta name="description" content="חינניה כחולה עם פסים שחורים.">', html)

    def test_a_species_without_a_description_gets_a_factual_one_built_from_its_data(self):
        self.species.description_he = ''
        self.species.save()
        html = self.page(f'/species/{self.area.slug}/')
        description = html.split('<meta name="description" content="')[1].split('">')[0]
        self.assertNotIn('תצפיות, תמונות ומידע מאתר', description)
        self.assertIn('Chromodoris annae', description)
        self.assertIn('חיננית ים', description)
        self.assertIn('Chromodorididae', description)
        self.assertIn('1 תצפיות', description)
        self.assertNotIn('מהגר', description)

    def test_the_migrant_sentence_only_appears_for_the_mediterranean_population(self):
        self.species.description_he = ''
        self.species.is_migrant = True
        self.species.first_observed_year = 2008
        self.species.save()
        med = self.make_population('ישראל', 'Israel', 'ים התיכון', 'Mediterranean', 'Akhziv')
        red = self.page(f'/species/{self.area.slug}/').split('<meta name="description" content="')[1].split('">')[0]
        mediterranean = self.page(f'/species/{med.slug}/').split('<meta name="description" content="')[1].split('">')[0]
        self.assertNotIn('מהגר', red)
        self.assertIn('מין מהגר בים התיכון, נרשם לראשונה בשנת 2008', mediterranean)

    def test_english_fallback_description(self):
        self.species.description_he = ''
        self.species.save()
        html = self.page(f'/species/{self.area.slug}/?lang=en')
        description = html.split('<meta name="description" content="')[1].split('">')[0]
        self.assertTrue(description.startswith('Chromodoris annae'))
        self.assertIn('A sea slug of the family Chromodorididae', description)
        self.assertIn('1 observation in Israel', description)


class HomePageLanguageTests(SeoFixture):
    """Phase 2: the home page's language, title, description, canonical and hreflang are in the HTML the
    server sends -- not only what app.js produces afterwards."""

    def tag(self, html, pattern):
        import re
        return re.search(pattern, html, re.S).group(1)

    def test_hebrew_home(self):
        html = self.page('/')
        self.assertIn('<html lang="he" dir="rtl">', html)
        title = self.tag(html, r'<title>(.*?)</title>')
        self.assertTrue(title.startswith('חינניות ים'))
        self.assertTrue(title.endswith('| SeaSlugs'))
        self.assertIn('חינניות ים (Sea Slugs)', self.tag(html, r'<meta name="description" content="(.*?)">'))
        self.assertIn('<meta property="og:locale" content="he_IL">', html)

    def test_english_home_is_server_rendered_in_english(self):
        html = self.page('/?lang=en')
        self.assertIn('<html lang="en" dir="ltr">', html)
        self.assertIn('<title>Sea Slugs &amp; Nudibranchs: Mediterranean Research Project and Photo Collection | SeaSlugs</title>', html)
        self.assertIn('Israeli research on sea slugs and nudibranchs', self.tag(html, r'<meta name="description" content="(.*?)">'))
        self.assertIn('<meta property="og:locale" content="en_US">', html)

    def test_a_remembered_language_cookie_does_not_change_the_address_into_english(self):
        self.client.cookies['seaslugs_lang'] = 'en'
        html = self.page('/')
        self.assertIn('<html lang="he" dir="rtl">', html)
        self.assertIn(f'<link rel="canonical" href="{BASE}/">', html)

    def test_explicit_hebrew_parameter_keeps_the_root_canonical(self):
        html = self.page('/?lang=he')
        self.assertIn('<html lang="he" dir="rtl">', html)
        self.assertIn(f'<link rel="canonical" href="{BASE}/">', html)

    def test_both_languages_are_available_to_the_language_button(self):
        import json
        html = self.page('/')
        data = json.loads(self.tag(html, r'<script id="seo-text" type="application/json">(.*?)</script>'))
        self.assertEqual(set(data), {'he', 'en'})
        self.assertTrue(data['he']['title'].startswith('חינניות ים'))
        self.assertTrue(data['en']['title'].startswith('Sea Slugs'))

    def test_the_old_description_naming_romblon_first_is_gone(self):
        for url in ('/', '/?lang=en'):
            self.assertNotIn('רומבלון', self.page(url).split('<body>')[0])

    def test_the_gallery_application_is_still_served(self):
        html = self.page('/')
        for needle in ('/catalog.js', '/app.js', '/styles.css', 'id="collectionTitle"'):
            self.assertIn(needle, html)
