from importlib import import_module

from django.apps import apps
from django.contrib.auth.models import User
from django.test import TestCase

from .models import (Article, Country, DiveTrip, IdentificationIssue, Region, Sample, Sea, Species, SpeciesArea,
                     SpeciesPublicationName, TaxonGenus)

migration = import_module('observations.migrations.0132_tritonia_sp3_marioniopsis_sp23')


class TritoniaSp3Tests(TestCase):
    """Migration 0132 (owner's decisions on issues #40, #89): Tritonia sp. 3 (2nd edition) becomes Marioniopsis sp. 23
    (3rd edition) in place -- same rows, slug and transfer id, name source NSSI-3, texts and identification from the book,
    the 3rd-edition name in that publication; the genus observation of Tritonia is deleted (soft); #40 is decided with the
    photo label to fix, #89 fixed; the Tritonia genus loses its defining sample. Runs once."""

    def test_rename_and_genus_observation_deleted(self):
        owner = User.objects.create_user('owner', password='x')
        ph = Country.objects.create(name='פיליפינים', name_en='Philippines')
        sea = Sea.objects.create(name='ים סין הדרומי', name_en='South China Sea')
        trip = DiveTrip.objects.create(code='V', title='v', year=2026, month=1, country=ph,
                                       region=Region.objects.create(name='Romblon', country=ph, sea=sea))
        nssi3 = Article.objects.create(slug=migration.NSSI3_SLUG, title_he='NSSI-3')
        tritonia = TaxonGenus.objects.create(name='Tritonia')
        TaxonGenus.objects.create(name='Marioniopsis')
        sp = Species.objects.create(scientific_name='Tritonia sp. 3', genus='Tritonia', species='sp. 3', name_source=migration.NSSI2,
                                    description_he='מין שטרם תואר רשמית מהסוג Tritonia ...')
        obs = Sample(owner=owner, species=sp, trip=trip, genus='Tritonia', video_url='https://youtu.be/30000000001')
        obs.save_reviewed()
        library = DiveTrip.objects.create(code='Genera', title='g', year=2026, month=1, country=ph, region=trip.region)
        genus_obs = Sample(owner=owner, kind='genus', genus='Tritonia', trip=library, status='published',
                           image='observations/genera-tritonia.jpg')
        Sample.objects.bulk_create([genus_obs])
        Sample.objects.filter(kind='genus').update(transfer_id=migration.GENUS_OBSERVATION)
        i40 = IdentificationIssue.objects.create(kind='misidentified', status='checking', transfer_id=migration.ISSUE_40)
        i89 = IdentificationIssue.objects.create(kind='other', status='open', transfer_id=migration.ISSUE_89,
                                                 action_observation='needed', action_photo='needed')
        slug = SpeciesArea.objects.get(species=sp).slug
        migration.forwards(apps, None)
        migration.forwards(apps, None)
        sp.refresh_from_db()
        self.assertEqual((sp.scientific_name, sp.genus, sp.name_source), ('Marioniopsis sp. 23', 'Marioniopsis', migration.NSSI3))
        self.assertIn('Paralemnalia', sp.identification_he)
        self.assertEqual(SpeciesPublicationName.objects.get(species=sp, article=nssi3).name, 'Marioniopsis sp. 23')
        self.assertEqual(Sample.objects.get(pk=obs.pk).genus, 'Marioniopsis')
        self.assertEqual(SpeciesArea.objects.get(species=sp).slug, slug)
        self.assertIsNotNone(Sample.objects.get(kind='genus').deleted_at)
        i40.refresh_from_db(); i89.refresh_from_db()
        self.assertEqual((i40.status, i40.action_photo, i40.corrected_species_id), ('decided', 'needed', sp.pk))
        self.assertEqual((i89.status, i89.action_observation, i89.action_photo), ('fixed', 'done', ''))
        tritonia.refresh_from_db()
        self.assertIsNone(tritonia.defining_sample_id)
