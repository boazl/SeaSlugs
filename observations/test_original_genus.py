from importlib import import_module
from io import StringIO

from django.apps import apps
from django.core.management import call_command
from django.test import TestCase

from .models import Species

migration = import_module('observations.migrations.0131_species_original_genus')


class OriginalGenusTests(TestCase):
    """Species.original_genus records the genus a species was described in, so the authority's parentheses can be
    checked by the ICZN rule -- parentheses exactly when the species now stands in another genus
    (author_parentheses_ok; manage.py check_author_parentheses lists the disagreements and the gallery species without
    an original genus). Migration 0131 fills it from observations/data/original_genera.json (only empty values) and
    gives three authors WoRMS's parentheses. Undescribed "sp." species and unknown values are not judged."""

    def species(self, name, author, original='', accepted=''):
        genus, epithet = name.split(' ', 1)
        return Species.objects.create(scientific_name=name, genus=genus, species=epithet, author=author,
                                      original_genus=original, accepted_genus=accepted)

    def test_parentheses_rule(self):
        self.assertTrue(self.species('Thuridilla gracilis', '(Risbec, 1928)', 'Elysia').author_parentheses_ok())
        self.assertTrue(self.species('Phestilla minor', 'Rudman, 1981', 'Phestilla').author_parentheses_ok())
        self.assertFalse(self.species('Doris bertheloti', "(d'Orbigny, 1839)", 'Doris').author_parentheses_ok())
        self.assertFalse(self.species('Cylichna villersii', 'Audouin, 1826', 'Bulla').author_parentheses_ok())
        self.assertIsNone(self.species('Aegires villosus', 'Farran, 1905').author_parentheses_ok())
        self.assertIsNone(self.species('Aegires sp. 12', '', 'Aegires').author_parentheses_ok())

    def test_migration_fills_and_fixes_authors(self):
        filled = self.species('Thuridilla gracilis', '(Risbec, 1928)')
        kept = self.species('Phestilla minor', 'Rudman, 1981', 'Other')
        wrong = self.species('Doris bertheloti', "(d'Orbigny, 1839)")
        migration.fill(apps, None)
        filled.refresh_from_db(); kept.refresh_from_db(); wrong.refresh_from_db()
        self.assertEqual(filled.original_genus, 'Elysia')
        self.assertEqual(kept.original_genus, 'Other')
        self.assertEqual((wrong.author, wrong.original_genus), ("d'Orbigny, 1839", 'Doris'))
        self.assertTrue(wrong.author_parentheses_ok())

    def test_command_lists_disagreements(self):
        self.species('Cylichna villersii', 'Audouin, 1826', 'Bulla')
        out = StringIO()
        call_command('check_author_parentheses', stdout=out)
        self.assertIn('Cylichna villersii | Audouin, 1826 | original genus Bulla', out.getvalue())
        self.assertIn('Parentheses that disagree with the original genus: 1.', out.getvalue())
