from importlib import import_module

from django.apps import apps
from django.test import TestCase

from .models import Species


class SpIdentificationTextsMigrationTests(TestCase):
    """Migration 0107 writes identification texts (Hebrew and English) for the gallery's "Genus sp. N" species from the
    accounts of Gosliner, Valdés & Behrens, each ending with the book, its edition, the page and the name the book uses
    (and, where the 3rd edition renamed the species, the 2nd edition's page and name too). It writes only
    where both identification fields are empty (an edited text is never overwritten) and skips a missing species;
    reversing it clears only its own texts."""

    def module(self):
        return import_module('observations.migrations.0107_sp_identification_texts')

    def test_writes_empty_fields_only(self):
        renamed = Species.objects.create(scientific_name='Eubranchus sp. 15', genus='Eubranchus', species='sp. 15')
        edited = Species.objects.create(scientific_name='Tenellia sp. 18', genus='Tenellia', species='sp. 18',
                                        identification_en='My own text')
        self.module().add(apps, None)
        renamed.refresh_from_db(); edited.refresh_from_db()
        self.assertIn('אינדונזיה', renamed.identification_he)
        self.assertTrue(renamed.identification_en.endswith(
            '(after Gosliner, Valdés & Behrens 2026, 3rd ed., pp. 320-321, as Eubranchus sp. 17; '
            'Gosliner, Valdés & Behrens 2018, 2nd ed., p. 279, as Eubranchus sp. 15)'))
        self.assertIn('מהדורה 3', renamed.identification_he)
        self.assertIn('מהדורה 2', renamed.identification_he)
        self.assertEqual((edited.identification_he, edited.identification_en), ('', 'My own text'))
        self.module().remove(apps, None)
        renamed.refresh_from_db()
        self.assertEqual((renamed.identification_he, renamed.identification_en), ('', ''))

    def test_unchanged_name_cites_one_edition(self):
        same = Species.objects.create(scientific_name='Tenellia sp. 29', genus='Tenellia', species='sp. 29')
        self.module().add(apps, None)
        same.refresh_from_db()
        self.assertTrue(same.identification_en.endswith('(after Gosliner, Valdés & Behrens 2026, 3rd ed., pp. 330-331, '
                                                        'as Tenellia sp. 29)'))

    def test_every_text_is_bilingual_and_sourced(self):
        for name, he, en, book, page, as_name in self.module().TEXTS:
            self.assertTrue(he.strip() and en.strip(), name)
            self.assertIn('Gosliner', book)
            self.assertTrue(page)
