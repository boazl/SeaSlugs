from importlib import import_module

from django.apps import apps
from django.contrib.auth.models import User
from django.test import TestCase

from .models import (Country, DiveTrip, IdentificationIssue, Region, Sample, Sea, Species, SpeciesArea,
                     TaxonFamily, TaxonGenus)

migration = import_module('observations.migrations.0122_book_edition_genus_moves')
OLD_TEXT_HE = ('מין שטרם תואר רשמית מהסוג Marionia (משפחת Tritoniidae), המופיע בספר ההגדרה של Gosliner, Valdés ו־Behrens '
               '(2018) בשם Marionia sp. 6. חשופיות עם זימים מסועפים לאורך שולי הגב.')
OLD_TEXT_EN = ('An undescribed species of Marionia (Tritoniidae), listed as Marionia sp. 6 in Gosliner, Valdés & Behrens '
               '(2018), Nudibranch & Sea Slug Identification – Indo-Pacific. Nudibranchs with branched gills along the edges '
               'of the back.')


class BookEditionGenusMovesTests(TestCase):
    """Migration 0122 (owner's decision on the book-edition issues #19, 26, 27, 28, 33): an undescribed species that the
    3rd edition of Gosliner et al. moves to another genus takes its 3rd-edition name in place -- same species row,
    observations (genus updated, same transfer id) and gallery card with the same slug; the name source becomes the 3rd
    edition, the texts give the 2nd edition's name, the sources cite the new genus in WoRMS and the 3rd edition; the old
    genus's defining sample is repaired; the open issue becomes "decided" with the catalogue done and the photo (and
    video when there is one) to fix. Runs once: a second run, or a catalogue that already has the new name, changes
    nothing."""

    def setUp(self):
        owner = User.objects.create_user('owner', password='x')
        ph = Country.objects.create(name='פיליפינים', name_en='Philippines')
        sea = Sea.objects.create(name='ים סין הדרומי', name_en='South China Sea', url_code='scs')
        trip = DiveTrip.objects.create(code='C', title='c', year=2023, month=1, country=ph,
                                       region=Region.objects.create(name='Anilao', country=ph, sea=sea))
        family = TaxonFamily.objects.create(name='Tritoniidae')
        self.marionia = TaxonGenus.objects.create(name='Marionia', family=family)
        TaxonGenus.objects.create(name='Marioniopsis', family=family)
        self.species = Species.objects.create(
            scientific_name='Marionia sp. 6', genus='Marionia', species='sp. 6', name_source=migration.NSSI2,
            description_he=OLD_TEXT_HE, description_en=OLD_TEXT_EN,
            identification_he='ירוק עז. במהדורה השלישית הועבר לסוג Marioniopsis. (לפי ...)',
            identification_en='Bright green. The 3rd edition places it in Marioniopsis. (after ...)',
            sources='https://www.marinespecies.org/aphia.php?p=taxdetails&id=138579\nGosliner (2018). 2nd ed. NWP.')
        self.sample = Sample(owner=owner, species=self.species, trip=trip, genus='Marionia',
                             video_url='https://youtu.be/30000000001')
        self.sample.save_reviewed()
        self.sample.refresh_from_db()
        self.area = SpeciesArea.objects.get(species=self.species)
        self.issue = IdentificationIssue.objects.create(
            kind='book_edition', status='checking', priority=1, species=self.species,
            transfer_id=migration.MOVES['Marionia sp. 6'][4])

    def test_renames_in_place(self):
        slug, transfer = self.area.slug, self.sample.transfer_id
        migration.forwards(apps, None)
        sp = Species.objects.get(pk=self.species.pk)
        self.assertEqual((sp.scientific_name, sp.genus, sp.species, sp.name_source),
                         ('Marioniopsis sp. 11', 'Marioniopsis', 'sp. 11', migration.NSSI3))
        self.assertTrue(sp.description_he.startswith('מין שטרם תואר רשמית מהסוג Marioniopsis (משפחת Tritoniidae)'))
        self.assertIn('בשם Marioniopsis sp. 11; במהדורה השנייה (2018) הופיע בשם Marionia sp. 6. חשופיות', sp.description_he)
        self.assertIn('lists it as Marionia sp. 6. Nudibranchs with branched gills', sp.description_en)
        self.assertIn('במהדורה השנייה הופיע בסוג Marionia.', sp.identification_he)
        self.assertIn('The 2nd edition placed it in Marionia.', sp.identification_en)
        self.assertEqual(sp.sources.splitlines(), [migration.WORMS.format(456341), migration.NSSI3_CITATION,
                                                   'Gosliner (2018). 2nd ed. NWP.'])
        sample = Sample.objects.get(pk=self.sample.pk)
        self.assertEqual((sample.genus, sample.transfer_id), ('Marioniopsis', transfer))
        self.assertEqual(SpeciesArea.objects.get(pk=self.area.pk).slug, slug)
        self.marionia.refresh_from_db()
        self.assertIsNone(self.marionia.defining_sample_id)
        self.assertEqual(TaxonGenus.objects.get(name='Marioniopsis').defining_sample_id, sample.pk)

    def test_issue_decided_with_actions(self):
        migration.forwards(apps, None)
        issue = IdentificationIssue.objects.get(pk=self.issue.pk)
        self.assertEqual((issue.status, issue.action_catalog, issue.action_photo, issue.action_video),
                         ('decided', 'done', 'needed', 'needed'))
        self.assertIn('Marioniopsis sp. 11', issue.decision)

    def test_runs_once(self):
        migration.forwards(apps, None)
        sp = Species.objects.get(pk=self.species.pk)
        texts = (sp.description_he, sp.description_en, sp.identification_he, sp.sources)
        migration.forwards(apps, None)
        sp.refresh_from_db()
        self.assertEqual((sp.description_he, sp.description_en, sp.identification_he, sp.sources), texts)

    def test_skips_when_new_name_exists(self):
        Species.objects.create(scientific_name='Marioniopsis sp. 11', genus='Marioniopsis', species='sp. 11')
        migration.forwards(apps, None)
        self.assertEqual(Species.objects.get(pk=self.species.pk).scientific_name, 'Marionia sp. 6')
        self.assertEqual(IdentificationIssue.objects.get(pk=self.issue.pk).status, 'checking')
