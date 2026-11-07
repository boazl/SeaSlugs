"""A visitor with no language in the address sees the site in their browser's language on a first visit: Hebrew only
when the browser's first-choice language is Hebrew, English otherwise. Once a language is chosen or carried in a
link (?lang=), it stays the same from page to page.

Rules:
- i18n.browser_lang reads Accept-Language: the highest-q language decides; "he" (or the old "iw"), with any region,
  is Hebrew, anything else English. No header, or a crawler / link-preview user agent, is Hebrew (the default).
- i18n.get_lang: ?lang= first, then the seaslugs_lang cookie (set by every ?lang= visit), then browser_lang.
- The home page "/" is Hebrew only: an English visitor is redirected (302) to "/?lang=en", other parameters kept.
  An explicit ?lang=he never redirects.
- Responses without ?lang= vary on Cookie and Accept-Language.
"""
from django.test import RequestFactory, SimpleTestCase, TestCase

from .i18n import browser_lang, get_lang


class BrowserLangTests(SimpleTestCase):
    def lang(self, header=None, agent=''):
        meta = {'HTTP_USER_AGENT': agent}
        if header is not None:
            meta['HTTP_ACCEPT_LANGUAGE'] = header
        return browser_lang(RequestFactory().get('/', **meta))

    def test_hebrew_browsers(self):
        for header in ('he', 'he-IL', 'he-IL,he;q=0.9,en-US;q=0.8,en;q=0.7', 'iw', 'HE-il'):
            with self.subTest(header=header):
                self.assertEqual(self.lang(header), 'he')

    def test_other_languages_are_english(self):
        for header in ('en-US,en;q=0.9', 'en-US,he;q=0.9', 'fr-FR', 'ru,he;q=0.8', 'de, he'):
            with self.subTest(header=header):
                self.assertEqual(self.lang(header), 'en')

    def test_the_highest_q_wins_not_the_first_listed(self):
        self.assertEqual(self.lang('en;q=0.5, he;q=0.9'), 'he')
        self.assertEqual(self.lang('he;q=0.3, fr;q=0.8'), 'en')

    def test_no_header_or_wildcard_is_hebrew(self):
        for header in (None, '', '*', 'xx;q=0'):
            with self.subTest(header=header):
                self.assertEqual(self.lang(header), 'he')

    def test_crawlers_get_hebrew(self):
        for agent in ('Mozilla/5.0 (compatible; Googlebot/2.1)', 'Mozilla/5.0 (compatible; bingbot/2.0)',
                      'facebookexternalhit/1.1', 'WhatsApp/2.23'):
            with self.subTest(agent=agent):
                self.assertEqual(self.lang('en-US', agent), 'he')


class GetLangTests(SimpleTestCase):
    def test_parameter_then_cookie_then_browser(self):
        rf = RequestFactory()
        self.assertEqual(get_lang(rf.get('/x/', {'lang': 'he'}, HTTP_ACCEPT_LANGUAGE='en')), 'he')
        request = rf.get('/x/', HTTP_ACCEPT_LANGUAGE='en')
        request.COOKIES['seaslugs_lang'] = 'he'
        self.assertEqual(get_lang(request), 'he')
        self.assertEqual(get_lang(rf.get('/x/', HTTP_ACCEPT_LANGUAGE='en-GB')), 'en')
        self.assertEqual(get_lang(rf.get('/x/', HTTP_ACCEPT_LANGUAGE='he-IL')), 'he')


class HomeRedirectTests(TestCase):
    def test_english_browser_goes_to_the_english_home(self):
        response = self.client.get('/', HTTP_ACCEPT_LANGUAGE='en-US,en;q=0.9')
        self.assertEqual((response.status_code, response['Location']), (302, '/?lang=en'))
        self.assertIn('Accept-Language', response['Vary'])

    def test_gallery_parameters_are_kept(self):
        response = self.client.get('/', {'area': 'med', 'sort': 'alpha'}, HTTP_ACCEPT_LANGUAGE='fr')
        self.assertEqual(response['Location'], '/?area=med&sort=alpha&lang=en')

    def test_hebrew_browser_and_no_header_stay_on_the_hebrew_home(self):
        for meta in ({'HTTP_ACCEPT_LANGUAGE': 'he-IL,he;q=0.9'}, {}):
            with self.subTest(meta=meta):
                response = self.client.get('/', **meta)
                self.assertEqual(response.status_code, 200)
                self.assertIn('<html lang="he" dir="rtl">', response.content.decode())

    def test_explicit_hebrew_never_redirects(self):
        response = self.client.get('/', {'lang': 'he'}, HTTP_ACCEPT_LANGUAGE='en-US')
        self.assertEqual(response.status_code, 200)
        self.assertIn('<html lang="he" dir="rtl">', response.content.decode())

    def test_a_chosen_hebrew_stays_for_an_english_browser(self):
        self.client.get('/', {'lang': 'he'}, HTTP_ACCEPT_LANGUAGE='en-US')   # sets the cookie
        self.assertEqual(self.client.get('/', HTTP_ACCEPT_LANGUAGE='en-US').status_code, 200)
        self.assertIn('>מסעות צלילה<', self.client.get('/observations/trips/', HTTP_ACCEPT_LANGUAGE='en-US').content.decode())

    def test_a_chosen_english_stays_for_a_hebrew_browser(self):
        self.client.get('/observations/trips/', {'lang': 'en'}, HTTP_ACCEPT_LANGUAGE='he-IL')
        self.assertEqual(self.client.get('/', HTTP_ACCEPT_LANGUAGE='he-IL')['Location'], '/?lang=en')
        self.assertIn('>Dive trips<', self.client.get('/observations/trips/', HTTP_ACCEPT_LANGUAGE='he-IL').content.decode())

    def test_other_pages_follow_the_browser_on_a_first_visit(self):
        self.assertIn('>Dive trips<', self.client.get('/observations/trips/', HTTP_ACCEPT_LANGUAGE='en-US').content.decode())
        self.assertIn('>מסעות צלילה<', self.client.get('/observations/trips/', HTTP_ACCEPT_LANGUAGE='he').content.decode())
        response = self.client.get('/observations/trips/')
        self.assertIn('Accept-Language', response['Vary'])
