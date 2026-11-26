from importlib import import_module

from django.apps import apps
from django.contrib.auth.models import User
from django.test import TestCase

from .models import Country, DiveTrip, IdentificationIssue, Region, Sample, Sea, Species, SpeciesArea

migration = import_module('observations.migrations.0134_hypselodoris_240_skyleri')


class HypselodorisSkyleriTests(TestCase):
    """Migration 0134 (owner's decision on issue #9): the Anilao observation filed as Hypselodoris carnea moves in place
    to H. skyleri and joins its Philippines card; the emptied H. carnea card is deleted (its URL redirects,
    historical_species_redirects.json); H. carnea stays in the catalogue; the issue is decided. Runs once."""

    def test_moves_to_skyleri(self):
        owner = User.objects.create_user('owner', password='x')
        ph = Country.objects.create(name='פיליפינים', name_en='Philippines')
        sea = Sea.objects.create(name='ים סין הדרומי', name_en='South China Sea')
        region = Region.objects.create(name='Anilao', country=ph, sea=sea)
        trips = [DiveTrip.objects.create(code=c, title=c, year=2023, month=1, country=ph, region=region) for c in ('C', 'V')]
        carnea = Species.objects.create(scientific_name='Hypselodoris carnea', genus='Hypselodoris', species='carnea')
        skyleri = Species.objects.create(scientific_name='Hypselodoris skyleri', genus='Hypselodoris', species='skyleri')
        Sample(owner=owner, species=skyleri, trip=trips[1], video_url='https://youtu.be/30000000001').save_reviewed()
        moved = Sample(owner=owner, species=carnea, trip=trips[0], video_url='https://youtu.be/30000000002')
        moved.save_reviewed()
        Sample.objects.filter(pk=moved.pk).update(transfer_id=migration.SAMPLE)
        SpeciesArea.objects.filter(species=carnea).update(slug=migration.OLD_SLUG)
        issue = IdentificationIssue.objects.create(kind='range', status='checking', species=carnea, transfer_id=migration.ISSUE)
        migration.forwards(apps, None)
        migration.forwards(apps, None)
        self.assertEqual(Sample.objects.get(pk=moved.pk).species_id, skyleri.pk)
        self.assertFalse(SpeciesArea.objects.filter(slug=migration.OLD_SLUG).exists())
        self.assertEqual(SpeciesArea.objects.filter(species=skyleri).count(), 1)
        self.assertTrue(Species.objects.filter(pk=carnea.pk).exists())
        issue.refresh_from_db()
        self.assertEqual((issue.status, issue.corrected_species_id, issue.action_photo), ('decided', skyleri.pk, 'needed'))


class Goniodoridella66CfTests(TestCase):
    """Migration 0135 (owner's decision on issue #10): the Romblon Goniodoridella savignyi observation is marked cf. with a
    note on the species complex; a note the owner wrote is kept; the issue is decided with the photo label to fix."""

    def test_cf_and_note(self):
        m = import_module('observations.migrations.0135_goniodoridella_66_cf')
        owner = User.objects.create_user('owner', password='x')
        ph = Country.objects.create(name='פיליפינים', name_en='Philippines')
        sea = Sea.objects.create(name='ים סין הדרומי', name_en='South China Sea')
        trip = DiveTrip.objects.create(code='V', title='v', year=2026, month=1, country=ph,
                                       region=Region.objects.create(name='Romblon', country=ph, sea=sea))
        sp = Species.objects.create(scientific_name='Goniodoridella savignyi', genus='Goniodoridella', species='savignyi')
        s = Sample(owner=owner, species=sp, trip=trip, video_url='https://youtu.be/30000000001')
        s.save_reviewed()
        Sample.objects.filter(pk=s.pk).update(transfer_id=m.SAMPLE, note_en='mine')
        issue = IdentificationIssue.objects.create(kind='range', status='checking', species=sp, transfer_id=m.ISSUE)
        m.forwards(apps, None)
        s.refresh_from_db(); issue.refresh_from_db()
        self.assertEqual((s.identification_qualifier, s.note_en), ('cf.', 'mine'))
        self.assertIn('Paz-Sedano', s.note_he)
        self.assertEqual((issue.status, issue.action_photo), ('decided', 'needed'))
