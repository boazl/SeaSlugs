"""The gallery's Photographer filter shows each name in the page's language: on the English site a
registered photographer appears by their English name (photographer_en in catalog.js), not the
Hebrew one. The checkbox value stays the language-invariant credit (entry.photographer), so a
filter chosen in one language keeps working in the other."""
import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

APP_JS = Path(settings.BASE_DIR) / 'dist' / 'app.js'


def _function_source(source, name):
    start = source.index(f'function {name}(')
    depth, i = 0, source.index('{', start)
    while True:
        if source[i] == '{':
            depth += 1
        elif source[i] == '}':
            depth -= 1
            if depth == 0:
                return source[start:i + 1]
        i += 1


@unittest.skipUnless(shutil.which('node'), 'node is needed to run app.js code')
class PhotographerFilterLanguageTests(SimpleTestCase):
    def run_options(self, language):
        source = APP_JS.read_text(encoding='utf-8')
        script = '\n'.join([
            f'const language = {json.dumps(language)};',
            'const state = {regions: new Set(), sites: new Set(), years: new Set()};',
            'const matchesAreaFilter = () => true, collectionMatchesArea = () => true;',
            'const speciesList = [{samples: [{region: 1, photographer: "בעז ליבס",'
            ' photographer_he: "בעז ליבס", photographer_en: "Boaz Liebes"}]}];',
            'const collectionsList = [{region: 1, photographer: "דנה כהן", photographer_he: "דנה כהן"}];',
            _function_source(source, 'photographerLabel'),
            _function_source(source, 'optionsForArea'),
            'const o = optionsForArea("all");',
            'console.log(JSON.stringify({values: [...o.photographers], labels: Object.fromEntries(o.photographerLabels)}));',
        ])
        out = subprocess.run(['node', '-e', script], capture_output=True, text=True, check=True).stdout
        return json.loads(out)

    def test_english_site_labels_a_photographer_by_the_english_name(self):
        result = self.run_options('en')
        self.assertEqual(result['labels']['בעז ליבס'], 'Boaz Liebes')

    def test_hebrew_site_keeps_the_hebrew_name(self):
        self.assertEqual(self.run_options('he')['labels']['בעז ליבס'], 'בעז ליבס')

    def test_a_name_without_an_english_version_falls_back_to_the_credit(self):
        self.assertEqual(self.run_options('en')['labels']['דנה כהן'], 'דנה כהן')

    def test_the_filter_value_stays_the_language_invariant_credit(self):
        self.assertEqual(sorted(self.run_options('en')['values']), sorted(['בעז ליבס', 'דנה כהן']))

    def test_the_sidebar_shows_the_label_not_the_raw_value(self):
        source = APP_JS.read_text(encoding='utf-8')
        self.assertTrue(re.search(r"\.map\(name => \[name, opts\.photographerLabels\.get\(name\) \|\| name", source))
