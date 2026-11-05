from pathlib import Path
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import TestCase

from .models import Species
from .table_transfer import TABLES, export_table, plan, fingerprint, apply

PAGE_TEXT = {
    'habitat_en': 'Coral reefs', 'food_en': 'Soft corals',
    'identification_he': 'סימני זיהוי', 'identification_en': 'Identification',
    'similar_species_he': 'מינים דומים', 'similar_species_en': 'Similar species',
    'native_range_he': 'מערב האוקיינוס השקט', 'native_range_en': 'Western Pacific',
    'introduction_route_he': 'תעלת סואץ', 'introduction_route_en': 'Suez Canal',
    'med_status_he': 'מבוסס', 'med_status_en': 'Established',
    'first_record_place_he': 'מכמורת', 'first_record_place_en': 'Mikhmoret',
    'last_record_place_he': 'אכזיב', 'last_record_place_en': 'Achziv',
    'sources': 'https://example.com/a\nhttps://example.com/b',
}


class SpeciesPageTextTransferTests(TestCase):
    """The species table transfer carries every species-page field (identification, similar
    species, native range, depth, the English habitat/food, the migrant fields and sources),
    not just the description: a species page filled on the Mac must look the same on the live
    site after transferring the species table. A file exported before these fields existed is
    still accepted and the target keeps its own values for them."""

    def setUp(self):
        self.species = Species.objects.create(scientific_name='Phyllodesmium colemani', genus='Phyllodesmium',
                                              species='colemani', author='Rudman, 1991', source_id='X1')

    def test_all_page_fields_are_in_the_species_table(self):
        fields = TABLES['species'][1]
        for field in list(PAGE_TEXT) + ['depth_min', 'depth_max', 'description_he', 'description_en',
                                        'habitat', 'food', 'size_from', 'size_to', 'size_max']:
            self.assertIn(field, fields)

    def test_page_fields_roundtrip(self):
        for k, v in PAGE_TEXT.items(): setattr(self.species, k, v)
        self.species.depth_min, self.species.depth_max = 2, 15
        self.species.save()
        doc = export_table('species')
        row = doc['rows'][0]
        self.assertEqual(row['identification_en'], 'Identification')
        self.assertEqual(row['depth_max'], 15)
        self.assertEqual(plan(doc)[0]['action'], 'same')
        Species.objects.filter(pk=self.species.pk).update(identification_he='', native_range_en='', sources='',
                                                          depth_min=None, depth_max=None)
        with patch('observations.table_transfer.create_backup', return_value=Path('test.sqlite3')):
            apply(doc, fingerprint())
        self.species.refresh_from_db()
        for k, v in PAGE_TEXT.items(): self.assertEqual(getattr(self.species, k), v)
        self.assertEqual((self.species.depth_min, self.species.depth_max), (2, 15))

    def test_depth_must_be_integer(self):
        doc = export_table('species')
        doc['rows'][0]['depth_max'] = '15'
        with self.assertRaises(ValidationError):
            plan(doc)

    def test_older_file_keeps_target_page_fields(self):
        doc = export_table('species')
        for f in list(PAGE_TEXT) + ['depth_min', 'depth_max']:
            del doc['rows'][0][f]
        doc['rows'][0]['description_en'] = 'New description'
        self.species.identification_he = 'נשאר'; self.species.depth_max = 30; self.species.save()
        with patch('observations.table_transfer.create_backup', return_value=Path('test.sqlite3')):
            apply(doc, fingerprint())
        self.species.refresh_from_db()
        self.assertEqual(self.species.description_en, 'New description')
        self.assertEqual(self.species.identification_he, 'נשאר')
        self.assertEqual(self.species.depth_max, 30)
