from importlib import import_module

from django.apps import apps
from django.contrib.auth.models import User
from django.test import TestCase

from .models import (Article, Country, DiveTrip, IdentificationIssue, Region, Sample, Sea, Species,
                     SpeciesPublicationName)

migration = import_module('observations.migrations.0125_aegires_sp7_cf')


class AegiresSp7CfTests(TestCase):
    """Migration 0125 (owner's decision on issue #37): the observation of Aegires sp. 7 keeps its species with "cf." and
    a note on the white tubercles; the species gets its 3rd-edition name (Aegires sp. 12, pp. 28-29) as a name in that
    publication, identification texts from both editions, the 3rd edition in its texts and sources; the issue is
    "decided" with catalogue and observation done, photo and video to fix. Existing values are kept; runs once."""

    def setUp(self):
        owner = User.objects.create_user('owner', password='x')
        ph = Country.objects.create(name='פיליפינים', name_en='Philippines')
        sea = Sea.objects.create(name='ים סין הדרומי', name_en='South China Sea', url_code='scs')
        trip = DiveTrip.objects.create(code='V', title='v', year=2026, month=1, country=ph,
                                       region=Region.objects.create(name='Romblon', country=ph, sea=sea))
        self.nssi3 = Article.objects.create(slug=migration.NSSI3_SLUG, title_he='NSSI-3')
        self.species = Species.objects.create(scientific_name='Aegires sp. 7', genus='Aegires', species='sp. 7',
                                              description_he='מין.', description_en='A species.',
                                              sources='https://worms\nGosliner (2018). 2nd ed. NWP.')
        self.sample = Sample(owner=owner, species=self.species, trip=trip, video_url='https://youtu.be/30000000001')
        self.sample.save_reviewed()
        Sample.objects.filter(pk=self.sample.pk).update(transfer_id=migration.SAMPLE)
        self.issue = IdentificationIssue.objects.create(kind='misidentified', status='open', priority=1,
                                                        species=self.species, transfer_id=migration.ISSUE)

    def test_cf_and_third_edition(self):
        migration.forwards(apps, None)
        migration.forwards(apps, None)
        sample = Sample.objects.get(pk=self.sample.pk)
        self.assertEqual(sample.identification_qualifier, 'cf.')
        self.assertIn('לבנות', sample.note_he)
        pub = SpeciesPublicationName.objects.get(species=self.species)
        self.assertEqual((pub.article_id, pub.name, pub.pages), (self.nssi3.pk, 'Aegires sp. 12', '28-29'))
        sp = Species.objects.get(pk=self.species.pk)
        self.assertEqual(sp.description_he.count('Aegires sp. 12'), 1)
        self.assertIn('בשם Aegires sp. 12', sp.identification_he)
        self.assertEqual(sp.sources.splitlines(), ['https://worms', migration.NSSI3, 'Gosliner (2018). 2nd ed. NWP.'])
        self.assertIn(self.nssi3, sp.articles.all())
        issue = IdentificationIssue.objects.get(pk=self.issue.pk)
        self.assertEqual((issue.status, issue.action_catalog, issue.action_observation, issue.action_photo,
                          issue.action_video), ('decided', 'done', 'done', 'needed', 'needed'))

    def test_keeps_existing_values(self):
        Sample.objects.filter(pk=self.sample.pk).update(note_he='שלי')
        Species.objects.filter(pk=self.species.pk).update(identification_he='קיים')
        migration.forwards(apps, None)
        self.assertEqual(Sample.objects.get(pk=self.sample.pk).note_he, 'שלי')
        self.assertEqual(Species.objects.get(pk=self.species.pk).identification_he, 'קיים')


class AegiresSp12Tests(TestCase):
    """Migration 0130 (owner's decisions): "Aegires sp. 7" (2nd edition) takes its 3rd-edition name Aegires sp. 12 with
    the 3rd edition as source (same row, the observation keeps cf., its note follows); observation #234 becomes
    Thuridilla cf. gracilis; the issues record it. Runs once."""

    new = import_module('observations.migrations.0130_aegires_sp12_and_cf_gracilis')

    def test_rename_and_cf(self):
        owner = User.objects.create_user('owner', password='x')
        ph = Country.objects.create(name='פיליפינים', name_en='Philippines')
        sea = Sea.objects.create(name='ים סין הדרומי', name_en='South China Sea', url_code='scs')
        trip = DiveTrip.objects.create(code='V', title='v', year=2026, month=1, country=ph,
                                       region=Region.objects.create(name='Romblon', country=ph, sea=sea))
        aegires = Species.objects.create(scientific_name='Aegires sp. 7', genus='Aegires', species='sp. 7',
                                         name_source='NSSI-2 Gosliner, Valdés & Behrens, 2018',
                                         description_he='מין שטרם תואר רשמית מהסוג Aegires ...')
        gracilis = Species.objects.create(scientific_name='Thuridilla gracilis', genus='Thuridilla', species='gracilis')
        rows = []
        for n, (species, transfer) in enumerate(((aegires, self.new.AEGIRES_SAMPLE), (gracilis, self.new.GRACILIS_SAMPLE)), 1):
            s = Sample(owner=owner, species=species, trip=trip, video_url=f'https://youtu.be/3000000000{n}')
            s.save_reviewed()
            Sample.objects.filter(pk=s.pk).update(transfer_id=transfer, identification_qualifier='cf.' if n == 1 else '',
                                                  note_he='זיהוי לא ודאי (cf.): המבנה תואם את Aegires sp. 7, אבל.' if n == 1 else '')
            rows.append(s.pk)
        issue = IdentificationIssue.objects.create(kind='misidentified', status='decided', decision='הוחלט.',
                                                   transfer_id=self.new.ISSUE_37)
        self.new.forwards(apps, None)
        self.new.forwards(apps, None)
        aegires.refresh_from_db()
        self.assertEqual((aegires.scientific_name, aegires.species, aegires.name_source),
                         ('Aegires sp. 12', 'sp. 12', self.new.NSSI3))
        self.assertEqual(aegires.description_he, self.new.DESC_HE)
        first, second = Sample.objects.get(pk=rows[0]), Sample.objects.get(pk=rows[1])
        self.assertEqual(first.identification_qualifier, 'cf.')
        self.assertIn('Aegires sp. 12', first.note_he)
        self.assertEqual(second.identification_qualifier, 'cf.')
        self.assertEqual(IdentificationIssue.objects.get(pk=issue.pk).decision.count('0130'), 1)
