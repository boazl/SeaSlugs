"""The Mediterranean bounty banner on the home page: a small link under the opening photo offering ₪200 for a photo of
a Mediterranean species the site doesn't have yet.

Rules:
- It sits beside the controls panel (dist/index.html .controls-row, [data-bounty]) in both languages, hidden until
  app.js fills it: in one line with the panel on a computer, above it on a phone.
- Its number is the Mediterranean's live species count (areaSpeciesCount of the area whose code is "med"), so it
  follows new observations; with no such area it stays hidden.
- A second, smaller line says the photos are for scientific publication (such as an identification guide) and
  that the photographer is credited.
- It links to the Mediterranean species alphabetically without the dive-trip collections
  (/?area=med&sort=alpha&trips=hide, + lang=en in English) and opens that view in place (applyGalleryQuery).
"""
import json
import shutil
import subprocess
import unittest
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase, TestCase

from .test_gallery_links import _function_source, _const_line

APP_JS = Path(settings.BASE_DIR) / 'dist' / 'app.js'


class BountyBannerPageTests(TestCase):
    def test_page_carries_the_hidden_banner_beside_the_panel_in_both_languages(self):
        for lang, href in (('he', '/?area=med&amp;sort=alpha&amp;trips=hide"'),
                           ('en', '/?area=med&amp;sort=alpha&amp;trips=hide&amp;lang=en"')):
            with self.subTest(lang=lang):
                html = self.client.get('/', {'lang': lang}).content.decode()
                self.assertIn('class="bounty-banner" data-bounty hidden', html)
                row = html[html.index('<div class="controls-row">'):html.index('class="gallery-layout"')]
                self.assertIn('class="controls-panel"', row)
                self.assertIn('data-bounty', row)
                self.assertNotIn('data-bounty', html[:html.index('<div class="controls-row">')])   # not in the hero
                self.assertIn(href, html)


@unittest.skipUnless(shutil.which('node'), 'node is needed to run app.js code')
class BountyBannerScriptTests(SimpleTestCase):
    def fill(self, language, areas, count):
        source = APP_JS.read_text(encoding='utf-8')
        script = '\n'.join([
            f'let language = {json.dumps(language)};',
            f'const areaLabelsData = {json.dumps(areas)};',
            f'const areaSpeciesCount = key => ({{species: {count}}});',
            'const link = {hidden: true, textContent: "", href: "", replaceChildren(...parts) {'
            ' this.textContent = parts.map(p => typeof p === "string" ? p : p.textContent).join("|"); }};',
            'const document = {querySelectorAll: () => [link], addEventListener() {}, createElement: () => ({textContent: ""})};',
            _const_line(source, 'AREA_PSEUDO_CODES'),
            _function_source(source, 'areaFromCode'),
            _const_line(source, 'BOUNTY_AREA_CODE'),
            _function_source(source, 'bountyText'),
            _function_source(source, 'bountyNote'),
            _function_source(source, 'fillBountyBanners'),
            'fillBountyBanners(); console.log(JSON.stringify(link));',
        ])
        return json.loads(subprocess.run(['node', '-e', script], capture_output=True, text=True, check=True).stdout)

    def test_hebrew_banner_shows_the_live_count(self):
        link = self.fill('he', {'sea-1': {'label': 'הים התיכון', 'code': 'med'}}, 23)
        self.assertFalse(link['hidden'])
        main, note = link['textContent'].split('|')
        self.assertEqual(main, 'תשלום של 200 ש״ח למי שיוסיף תצלום של מין מהים התיכון שאינו מופיע ב-23 התצפיות באתר')
        self.assertEqual(note, 'התצלומים מיועדים לפרסום מדעי, כגון מגדיר חינניות ים, והצלם יוזכר בפרסומים.')
        self.assertEqual(link['href'], '/?area=med&sort=alpha&trips=hide')

    def test_english_banner(self):
        link = self.fill('en', {'sea-1': {'label': 'הים התיכון', 'code': 'med'}}, 19)
        self.assertIn('not among the 19 observations', link['textContent'])
        self.assertIn('the photographer will be credited', link['textContent'])
        self.assertEqual(link['href'], '/?area=med&sort=alpha&trips=hide&lang=en')

    def test_hidden_without_a_mediterranean_area(self):
        self.assertTrue(self.fill('he', {'sea-2': {'label': 'ים סוף', 'code': 'eilat'}}, 5)['hidden'])

    def test_click_opens_the_view_in_place(self):
        source = APP_JS.read_text(encoding='utf-8')
        start = source.index("const link = event.target.closest('[data-bounty]');")
        handler = source[start:source.index('});', start)]
        self.assertIn('event.preventDefault();', handler)
        self.assertIn('applyGalleryQuery(', handler)

    def test_refilled_when_the_language_changes(self):
        body = _function_source(APP_JS.read_text(encoding='utf-8'), 'setLanguage')
        self.assertLess(body.index('applyHomeSections();'), body.index('fillBountyBanners();'))
