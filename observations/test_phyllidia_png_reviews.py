from importlib import import_module

from django.apps import apps
from django.contrib.auth.models import User
from django.test import TestCase

from .models import Country, DiveTrip, IdentificationIssue, Region, Sample, Sea, Species, SpeciesArea

migration = import_module('observations.migrations.0133_phyllidia_png_reviews')


class PhyllidiaPngReviewsTests(TestCase):
    """Migration 0133 (owner's decisions on issues #7, #8): the Papua New Guinea observation filed as Phyllidia rueppelii
    moves in place to Phyllidia picta with its card (same slug), P. rueppelii stays in the catalogue; the P. alyta
    observation is marked cf. with a note on the range; both issues decided with the photo label to fix. Runs once."""

    def test_decisions(self):
        owner = User.objects.create_user('owner', password='x')
        png = Country.objects.create(name='פפואה גינאה החדשה', name_en='Papua New Guinea')
        sea = Sea.objects.create(name='ים ביסמרק', name_en='Bismarck Sea')
        trip = DiveTrip.objects.create(code='Z2', title='z2', year=1998, month=1, country=png,
                                       region=Region.objects.create(name='Madang', country=png, sea=sea))
        rueppelii = Species.objects.create(scientific_name='Phyllidia rueppelii', genus='Phyllidia', species='rueppelii')
        picta = Species.objects.create(scientific_name='Phyllidia picta', genus='Phyllidia', species='picta')
        alyta = Species.objects.create(scientific_name='Phyllidia alyta', genus='Phyllidia', species='alyta')
        rows = {}
        for n, (species, transfer) in enumerate(((rueppelii, migration.PICTA_SAMPLE), (alyta, migration.ALYTA_SAMPLE)), 1):
            s = Sample(owner=owner, species=species, trip=trip, video_url=f'https://youtu.be/3000000000{n}')
            s.save_reviewed()
            Sample.objects.filter(pk=s.pk).update(transfer_id=transfer)
            rows[transfer] = s.pk
        slug = SpeciesArea.objects.get(species=rueppelii).slug
        i7 = IdentificationIssue.objects.create(kind='range', status='checking', species=rueppelii, transfer_id=migration.ISSUE_7)
        i8 = IdentificationIssue.objects.create(kind='range', status='checking', species=alyta, transfer_id=migration.ISSUE_8)
        migration.forwards(apps, None)
        migration.forwards(apps, None)
        self.assertEqual(Sample.objects.get(pk=rows[migration.PICTA_SAMPLE]).species_id, picta.pk)
        self.assertEqual(SpeciesArea.objects.get(slug=slug).species_id, picta.pk)
        self.assertTrue(Species.objects.filter(pk=rueppelii.pk).exists())
        moved = Sample.objects.get(pk=rows[migration.ALYTA_SAMPLE])
        self.assertEqual((moved.species_id, moved.identification_qualifier), (alyta.pk, 'cf.'))
        self.assertIn('האוקיינוס ההודי', moved.note_he)
        i7.refresh_from_db(); i8.refresh_from_db()
        self.assertEqual((i7.status, i7.corrected_species_id, i7.action_photo), ('decided', picta.pk, 'needed'))
        self.assertEqual((i8.status, i8.action_observation, i8.action_photo), ('decided', 'done', 'needed'))
