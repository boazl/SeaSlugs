import re
from pathlib import Path

from django.test import TestCase

from .templatetags.seaslugs_i18n import TRANSLATIONS


class TemplateTranslationTests(TestCase):
    def test_every_hebrew_literal_run_through_the_t_filter_has_an_english_translation(self):
        # A Hebrew string piped through |t:lang that has no TRANSLATIONS entry silently stays
        # Hebrew on the English pages (it did for "מינים בסוג זה" and the meta description).
        templates = Path(__file__).resolve().parent / 'templates'
        pattern = re.compile(r'''(?:"([^"{}]*[֐-׿][^"{}]*)"|'([^'{}]*[֐-׿][^'{}]*)')\|t:lang''')
        missing = {}
        for path in templates.rglob('*.html'):
            for match in pattern.finditer(path.read_text(encoding='utf-8')):
                text = match.group(1) or match.group(2)
                if text not in TRANSLATIONS:
                    missing.setdefault(text, path.name)
        self.assertEqual(missing, {})
