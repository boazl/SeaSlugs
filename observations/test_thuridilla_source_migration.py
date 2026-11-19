from importlib import import_module

from django.apps import apps
from django.test import TestCase

from .models import Article

migration = import_module('observations.migrations.0108_fix_thuridilla_article_source')


class ThuridillaSourceMigrationTests(TestCase):
    """Migration 0108 fixes the broken accents copied from the PDF in the Thuridilla phylogeny article's author line
    ("Mart ın-Herv as" -> "Martín-Hervás"); only the exact broken text of that article changes."""

    def test_fixes_only_the_broken_text(self):
        broken = Article.objects.create(slug=migration.SLUG, title_he='a', source=migration.BROKEN + ' et al. / Cladistics')
        other = Article.objects.create(slug='other', title_he='b', source=migration.BROKEN)
        migration.fix(apps, None)
        broken.refresh_from_db(); other.refresh_from_db()
        self.assertEqual(broken.source, 'M. R. Martín-Hervás et al. / Cladistics')
        self.assertEqual(other.source, migration.BROKEN)
        migration.fix(apps, None)
        broken.refresh_from_db()
        self.assertEqual(broken.source, 'M. R. Martín-Hervás et al. / Cladistics')
