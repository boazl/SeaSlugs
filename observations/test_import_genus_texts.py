import csv
import tempfile
from io import StringIO
from pathlib import Path
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from .models import TaxonGenus


class ImportGenusTextsTests(TestCase):
    def setUp(self):
        self.genus = TaxonGenus.objects.create(name='Hypselodoris')
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)

    def csv(self, rows, header=None):
        path = Path(self.dir.name) / 'texts.csv'
        header = header or list(rows[0].keys())
        with path.open('w', newline='', encoding='utf-8-sig') as handle:
            writer = csv.DictWriter(handle, fieldnames=header)
            writer.writeheader()
            writer.writerows(rows)
        return str(path)

    def run_command(self, path, apply=False):
        out = StringIO()
        call_command('import_genus_texts', path, *(['--apply'] if apply else []), stdout=out)
        return out.getvalue()

    def test_dry_run_reports_but_saves_nothing(self):
        path = self.csv([{'genus': 'Hypselodoris', 'description_he': 'תיאור'}])
        output = self.run_command(path)
        self.assertIn('1 genera to update', output)
        self.assertIn('Dry run', output)
        self.genus.refresh_from_db()
        self.assertEqual(self.genus.description_he, '')

    def test_apply_fills_blank_fields_including_sources_and_hebrew(self):
        path = self.csv([{'genus': 'Hypselodoris', 'description_he': 'תיאור בעברית', 'description_en': 'English text',
                          'identification_he': 'סימני זיהוי', 'identification_en': 'Key features',
                          'sources': 'https://www.marinespecies.org/\nGosliner 2015'}])
        self.run_command(path, apply=True)
        self.genus.refresh_from_db()
        self.assertEqual(self.genus.description_he, 'תיאור בעברית')
        self.assertEqual(self.genus.identification_en, 'Key features')
        self.assertEqual(self.genus.sources, 'https://www.marinespecies.org/\nGosliner 2015')

    def test_existing_text_is_never_overwritten(self):
        self.genus.description_he = 'הטקסט שלי'
        self.genus.save()
        path = self.csv([{'genus': 'Hypselodoris', 'description_he': 'טקסט אחר', 'description_en': 'New'}])
        output = self.run_command(path, apply=True)
        self.genus.refresh_from_db()
        self.assertEqual(self.genus.description_he, 'הטקסט שלי')
        self.assertEqual(self.genus.description_en, 'New')      # a blank field next to it is still filled
        self.assertIn('Hypselodoris: description_he', output)

    def test_same_text_is_not_a_conflict_and_blank_cells_are_ignored(self):
        self.genus.description_en = 'Same'
        self.genus.save()
        path = self.csv([{'genus': 'Hypselodoris', 'description_en': 'Same', 'description_he': ''}])
        output = self.run_command(path, apply=True)
        self.assertIn('0 genera updated', output)
        self.assertIn('Conflicts (kept the existing text): 0', output)

    def test_unknown_genus_is_reported_not_created(self):
        path = self.csv([{'genus': 'Nosuchgenus', 'description_he': 'x'}])
        output = self.run_command(path, apply=True)
        self.assertIn('Unmatched genus names: 1', output)
        self.assertFalse(TaxonGenus.objects.filter(name='Nosuchgenus').exists())

    def test_unknown_column_and_missing_genus_column_are_rejected(self):
        with self.assertRaises(CommandError):
            self.run_command(self.csv([{'genus': 'Hypselodoris', 'colour': 'blue'}]))
        with self.assertRaises(CommandError):
            self.run_command(self.csv([{'name': 'Hypselodoris'}]))
